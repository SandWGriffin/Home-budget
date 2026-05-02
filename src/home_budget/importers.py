from __future__ import annotations

import csv
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from .db import connect, create_import_batch


BANK_REQUIRED_COLUMNS = {"posted_date", "description", "amount"}
INCOME_REQUIRED_COLUMNS = {"date", "amount"}
EXISTING_EXPORT_REQUIRED_COLUMNS = {"Date", "Description", "Amount", "Balance", "Ref/Check"}

BANK_COLUMN_ALIASES = {
    "posted_date": ("posted_date", "Date", "date"),
    "description": ("description", "Description"),
    "amount": ("amount", "Amount"),
    "bank_reference": ("bank_reference", "Ref/Check", "ref/check", "reference"),
    "balance": ("balance", "Balance"),
}

DEFAULT_ACCOUNT_NAMES_BY_SUFFIX = {
    "535": "personal_checking_6535",
    "448": "business_4448",
}


def _to_cents(amount_text: str) -> int:
    cleaned = amount_text.replace("$", "").replace(",", "").strip()
    return int(round(float(cleaned) * 100))


def _normalize_description(value: str) -> str:
    return " ".join(value.lower().split())


def _to_iso_date_mdy(value: str) -> str:
    return datetime.strptime(value.strip(), "%m/%d/%Y").date().isoformat()


def _to_iso_date(value: str) -> str:
    raw = value.strip()
    for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, date_format).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value}")


def _resolve_column_name(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    by_lower = {name.strip().lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
        resolved = by_lower.get(candidate.strip().lower())
        if resolved:
            return resolved
    return None


def _normalize_ref(value: str | None) -> str:
    raw = (value or "").strip()
    return raw or ""


def _looks_like_non_transaction(description: str, amount_text: str) -> bool:
    normalized = _normalize_description(description)
    if normalized.startswith("daily ledger bal"):
        return True
    if normalized.startswith("pending:"):
        return True
    if (amount_text or "").strip() == "":
        return True
    return False


def _infer_account_suffix_from_transfer(description: str, amount_cents: int) -> str | None:
    normalized = _normalize_description(description)
    if "from *448 to *535" in normalized:
        return "535" if amount_cents > 0 else "448"
    if "from *535 to *448" in normalized:
        return "448" if amount_cents > 0 else "535"
    return None


def _resolve_account_name(
    suffix: str,
    account_names_by_suffix: dict[str, str] | None,
) -> str:
    mapping = account_names_by_suffix or DEFAULT_ACCOUNT_NAMES_BY_SUFFIX
    if suffix in mapping:
        return mapping[suffix]
    return f"account_{suffix}"


def _dedupe_key(
    account: str,
    posted_date: str,
    amount_cents: int,
    normalized_description: str,
    bank_reference: str,
) -> str:
    raw = "|".join(
        [account, posted_date, str(amount_cents), normalized_description, bank_reference]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def import_bank_csv(db_path: str | Path, csv_path: str | Path, account: str) -> dict[str, int]:
    csv_file = Path(csv_path)
    with csv_file.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        column_map: dict[str, str] = {}
        for canonical, aliases in BANK_COLUMN_ALIASES.items():
            resolved = _resolve_column_name(fieldnames, aliases)
            if resolved:
                column_map[canonical] = resolved

        missing = BANK_REQUIRED_COLUMNS - set(column_map.keys())
        if missing:
            missing_csv = ", ".join(sorted(missing))
            raise ValueError(f"Bank CSV missing required columns: {missing_csv}")

        inserted = 0
        duplicates = 0

        with connect(db_path) as conn:
            batch_id = create_import_batch(conn, csv_file.name)
            for row in reader:
                posted_date = _to_iso_date((row.get(column_map["posted_date"]) or "").strip())
                description = (row.get(column_map["description"]) or "").strip()
                amount_cents = _to_cents((row.get(column_map["amount"]) or "0").strip())
                normalized = _normalize_description(description)
                bank_reference = (
                    row.get(column_map.get("bank_reference", "bank_reference")) or ""
                ).strip()
                balance_raw = (row.get(column_map.get("balance", "balance")) or "").strip()
                balance_cents = _to_cents(balance_raw) if balance_raw else None
                key = _dedupe_key(
                    account=account,
                    posted_date=posted_date,
                    amount_cents=amount_cents,
                    normalized_description=normalized,
                    bank_reference=bank_reference,
                )

                try:
                    conn.execute(
                        """
                        INSERT INTO bank_transaction (
                            import_batch_id,
                            account,
                            posted_date,
                            description,
                            normalized_description,
                            amount_cents,
                            balance_cents,
                            bank_reference,
                            dedupe_key
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            batch_id,
                            account,
                            posted_date,
                            description,
                            normalized,
                            amount_cents,
                            balance_cents,
                            bank_reference,
                            key,
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    duplicates += 1

            conn.commit()

    return {"inserted": inserted, "duplicates": duplicates}


def import_existing_bank_export_csv(
    db_path: str | Path,
    csv_path: str | Path,
    account_names_by_suffix: dict[str, str] | None = None,
    fallback_account: str | None = None,
    include_pending: bool = False,
) -> dict[str, int | str]:
    csv_file = Path(csv_path)
    with csv_file.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        missing = EXISTING_EXPORT_REQUIRED_COLUMNS - headers
        if missing:
            missing_csv = ", ".join(sorted(missing))
            raise ValueError(f"Existing export CSV missing required columns: {missing_csv}")

        rows = list(reader)

    account_suffix: str | None = None
    for row in rows:
        description = (row.get("Description") or "").strip()
        amount_text = (row.get("Amount") or "").strip()
        if _looks_like_non_transaction(description, amount_text):
            if not include_pending:
                continue
        amount_cents = _to_cents(amount_text or "0")
        inferred = _infer_account_suffix_from_transfer(description, amount_cents)
        if inferred:
            account_suffix = inferred
            break

    if account_suffix is None:
        if fallback_account:
            account_name = fallback_account
        else:
            raise ValueError(
                "Could not infer account from transfer lines. Provide fallback_account."
            )
    else:
        account_name = _resolve_account_name(account_suffix, account_names_by_suffix)

    inserted = 0
    duplicates = 0

    with connect(db_path) as conn:
        batch_id = create_import_batch(conn, csv_file.name)
        for row in rows:
            description = (row.get("Description") or "").strip()
            amount_text = (row.get("Amount") or "").strip()
            if _looks_like_non_transaction(description, amount_text):
                if include_pending and _normalize_description(description).startswith("pending:"):
                    pass
                else:
                    continue

            posted_date = _to_iso_date((row.get("Date") or "").strip())
            amount_cents = _to_cents(amount_text or "0")
            normalized = _normalize_description(description)
            bank_reference = _normalize_ref(row.get("Ref/Check"))
            balance_raw = (row.get("Balance") or "").strip()
            balance_cents = _to_cents(balance_raw) if balance_raw else None
            key = _dedupe_key(
                account=account_name,
                posted_date=posted_date,
                amount_cents=amount_cents,
                normalized_description=normalized,
                bank_reference=bank_reference,
            )

            try:
                conn.execute(
                    """
                    INSERT INTO bank_transaction (
                        import_batch_id,
                        account,
                        posted_date,
                        description,
                        normalized_description,
                        amount_cents,
                        balance_cents,
                        bank_reference,
                        dedupe_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_id,
                        account_name,
                        posted_date,
                        description,
                        normalized,
                        amount_cents,
                        balance_cents,
                        bank_reference,
                        key,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                duplicates += 1

        conn.commit()

    return {
        "account": account_name,
        "inserted": inserted,
        "duplicates": duplicates,
    }


def import_income_forecast_csv(db_path: str | Path, csv_path: str | Path) -> int:
    csv_file = Path(csv_path)
    with csv_file.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        missing = INCOME_REQUIRED_COLUMNS - headers
        if missing:
            missing_csv = ", ".join(sorted(missing))
            raise ValueError(f"Income CSV missing required columns: {missing_csv}")

        inserted = 0
        with connect(db_path) as conn:
            for row in reader:
                note = (row.get("note") or "").strip() or None
                conn.execute(
                    """
                    INSERT INTO income_forecast (forecast_date, forecast_amount_cents, note)
                    VALUES (?, ?, ?)
                    """,
                    (
                        (row.get("date") or "").strip(),
                        _to_cents((row.get("amount") or "0").strip()),
                        note,
                    ),
                )
                inserted += 1
            conn.commit()

    return inserted
