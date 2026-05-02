from pathlib import Path

from src.home_budget.db import connect, init_db
from src.home_budget.importers import import_bank_csv, import_income_forecast_csv
from src.home_budget.services import (
    add_planned_expense,
    calculate_daily_cashflow,
    calculate_daily_category_cashflow,
    category_month_status,
    set_monthly_goal,
    set_balance_snapshot,
    upsert_category,
    detect_balance_variance,
)


def test_expected_cashflow_and_variance(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    food_id = upsert_category(db_path, "Food")

    income_csv = tmp_path / "income.csv"
    income_csv.write_text(
        "date,amount,note\n"
        "2026-04-01,1000.00,Client\n",
        encoding="utf-8",
    )
    import_income_forecast_csv(db_path, income_csv)

    add_planned_expense(db_path, "2026-04-02", food_id, 30000, "Groceries")
    set_balance_snapshot(db_path, "household", "2026-04-02", 65000)

    flow = calculate_daily_cashflow(
        db_path,
        start_date="2026-04-01",
        end_date="2026-04-03",
        opening_balance_cents=0,
        expense_mode="expected",
    )

    assert flow[0]["projected_balance_cents"] == 100000
    assert flow[1]["projected_balance_cents"] == 70000

    variance = detect_balance_variance(db_path, "household", flow)
    assert len(variance) == 1
    assert variance[0]["variance_cents"] == -5000


def test_category_month_status_and_daily_category_cashflow(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    food_id = upsert_category(db_path, "Food")
    set_monthly_goal(db_path, food_id, 2026, 4, 80000)

    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "posted_date,description,amount,bank_reference\n"
        "2026-04-03,Store A,-12.34,ref-1\n",
        encoding="utf-8",
    )
    import_bank_csv(db_path, bank_csv, account="household")

    with connect(db_path) as conn:
        conn.execute("UPDATE bank_transaction SET category_id = ?", (food_id,))
        conn.commit()

    add_planned_expense(db_path, "2026-04-03", food_id, 2000, "cash plan")

    status = category_month_status(db_path, 2026, 4)
    assert status[0]["goal_cents"] == 80000
    assert status[0]["actual_spend_cents"] == 1234
    assert status[0]["remaining_cents"] == 78766

    by_category = calculate_daily_category_cashflow(db_path, "2026-04-03", "2026-04-03")
    assert len(by_category) == 1
    assert by_category[0]["category"] == "Food"
    assert by_category[0]["expected_expense_cents"] == 2000
    assert by_category[0]["actual_expense_cents"] == 1234


def test_income_import_accepts_customer_date_income_schema(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    income_csv = tmp_path / "income_customer_schema.csv"
    income_csv.write_text(
        "Customer,Date,Income\n"
        "New Growth Press,5/5/26,4300\n",
        encoding="utf-8",
    )

    import_income_forecast_csv(db_path, income_csv)

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT forecast_date, forecast_amount_cents, note FROM income_forecast LIMIT 1"
        ).fetchone()

    assert row["forecast_date"] == "2026-05-05"
    assert row["forecast_amount_cents"] == 430000
    assert row["note"] == "New Growth Press"
