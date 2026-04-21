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
