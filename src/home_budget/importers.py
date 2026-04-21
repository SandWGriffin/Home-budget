from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path

from .db import connect, create_import_batch


BANK_REQUIRED_COLUMNS = {"posted_date", "description", "amount"}
INCOME_REQUIRED_COLUMNS = {"date", "amount"}


def _to_cents(amount_text: str) -> int:
    cleaned = amount_text.replace("$", "").replace(",", "").strip()
    return int(round(float(cleaned) * 100))


def _normalize_description(value: str) -> str:
    return " ".join(value.lower().split())


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
        headers = set(reader.fieldnames or [])
        missing = BANK_REQUIRED_COLUMNS - headers
        if missing:
            missing_csv = ", ".join(sorted(missing))
            raise ValueError(f"Bank CSV missing required columns: {missing_csv}")

        inserted = 0
        duplicates = 0

        with connect(db_path) as conn:
            batch_id = create_import_batch(conn, csv_file.name)
            for row in reader:
                posted_date = (row.get("posted_date") or "").strip()
                description = (row.get("description") or "").strip()
                amount_cents = _to_cents((row.get("amount") or "0").strip())
                normalized = _normalize_description(description)
                bank_reference = (row.get("bank_reference") or "").strip()
                balance_raw = (row.get("balance") or "").strip()
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
