from pathlib import Path

from src.home_budget.db import connect, init_db
from src.home_budget.importers import import_existing_bank_export_csv


def test_existing_export_detects_personal_6535_and_skips_daily_ledger(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    csv_path = tmp_path / "personal.csv"
    csv_path.write_text(
        '"Date","Ref/Check","Description","Amount","Balance","Memo","Category"\n'
        '04/20/2026,,"Daily Ledger Bal",,2389.79,,\n'
        '04/20/2026,,"OLB Transfer from *448 to *535 Transfer",800,956.01,,\n'
        '04/19/2026,,"WHOLEFDS WIN 101",-161.52,176.12,,\n',
        encoding="utf-8",
    )

    stats = import_existing_bank_export_csv(db_path, csv_path)

    assert stats["account"] == "personal_checking_6535"
    assert stats["inserted"] == 2
    assert stats["duplicates"] == 0

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT posted_date, account, description FROM bank_transaction ORDER BY posted_date"
        ).fetchall()

    assert rows[0]["posted_date"] == "2026-04-19"
    assert rows[0]["account"] == "personal_checking_6535"


def test_existing_export_detects_business_4448(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    csv_path = tmp_path / "business.csv"
    csv_path.write_text(
        '"Date","Ref/Check","Description","Amount","Balance","Memo","Category"\n'
        '04/20/2026,,"OLB Transfer from *448 to *535 Transfer",-800,2389.79,,\n'
        '04/17/2026,,"DAIEI AMERICA CORP PAY",2125,3189.79,,\n',
        encoding="utf-8",
    )

    stats = import_existing_bank_export_csv(db_path, csv_path)

    assert stats["account"] == "business_4448"
    assert stats["inserted"] == 2


def test_existing_export_requires_fallback_when_no_transfer_hint(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    csv_path = tmp_path / "unknown.csv"
    csv_path.write_text(
        '"Date","Ref/Check","Description","Amount","Balance","Memo","Category"\n'
        '04/20/2026,,"Some Merchant",-10,100,,\n',
        encoding="utf-8",
    )

    stats = import_existing_bank_export_csv(
        db_path,
        csv_path,
        fallback_account="household_manual",
    )

    assert stats["account"] == "household_manual"
    assert stats["inserted"] == 1
