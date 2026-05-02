from pathlib import Path

from src.home_budget.db import connect, init_db
from src.home_budget.importers import import_bank_csv


def test_bank_import_deduplicates_overlapping_rows(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    first = tmp_path / "bank_first.csv"
    first.write_text(
        "posted_date,description,amount,bank_reference\n"
        "2026-04-01,Store A,-12.34,ref-1\n"
        "2026-04-02,Store B,-20.00,ref-2\n",
        encoding="utf-8",
    )

    second = tmp_path / "bank_second.csv"
    second.write_text(
        "posted_date,description,amount,bank_reference\n"
        "2026-04-01,Store A,-12.34,ref-1\n"
        "2026-04-02,Store B,-20.00,ref-2\n"
        "2026-04-03,Store C,-5.00,ref-3\n",
        encoding="utf-8",
    )

    first_stats = import_bank_csv(db_path, first, account="household")
    second_stats = import_bank_csv(db_path, second, account="household")

    assert first_stats == {"inserted": 2, "duplicates": 0}
    assert second_stats == {"inserted": 1, "duplicates": 2}

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM bank_transaction").fetchone()[0]

    assert count == 3


def test_bank_import_accepts_existing_export_headers(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    csv_path = tmp_path / "bank_existing_headers.csv"
    csv_path.write_text(
        "Date,Ref/Check,Description,Amount,Balance\n"
        "5/2/26,,Coffee Shop,-4.50,100.00\n"
        "5/2/26,1234,Payroll,1000.00,1100.00\n",
        encoding="utf-8",
    )

    stats = import_bank_csv(db_path, csv_path, account="household")

    assert stats == {"inserted": 2, "duplicates": 0}

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT posted_date, amount_cents, bank_reference FROM bank_transaction ORDER BY id"
        ).fetchall()

    assert rows[0]["posted_date"] == "2026-05-02"
    assert rows[0]["amount_cents"] == -450
    assert rows[0]["bank_reference"] == ""
    assert rows[1]["bank_reference"] == "1234"
