from pathlib import Path

from src.home_budget.db import connect, init_db
from src.home_budget.importers import import_bank_csv
from src.home_budget.services import (
    apply_classification_rules,
    create_transaction_rule,
    generate_monthly_forecast,
    set_monthly_goal,
    upsert_category,
)


def test_rule_auto_classifies_transaction(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    category_id = upsert_category(db_path, "Food")
    create_transaction_rule(
        db_path=db_path,
        match_type="contains",
        pattern="store a",
        category_id=category_id,
        is_recurring=True,
        recurrence_cadence="monthly",
        recurrence_day_of_month=5,
    )

    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "posted_date,description,amount,bank_reference\n"
        "2026-01-05,Store A Market,-12.34,ref-100\n",
        encoding="utf-8",
    )

    import_bank_csv(db_path, bank_csv, account="household")
    updates = apply_classification_rules(db_path)
    assert updates == 1

    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT category_id, is_recurring, recurrence_cadence, recurrence_day_of_month
            FROM bank_transaction
            """
        ).fetchone()

    assert int(row["category_id"]) == category_id
    assert int(row["is_recurring"]) == 1
    assert row["recurrence_cadence"] == "monthly"
    assert int(row["recurrence_day_of_month"]) == 5


def test_monthly_forecast_uses_recurring_and_income(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    category_id = upsert_category(db_path, "Food")

    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "posted_date,description,amount,bank_reference\n"
        "2026-01-05,Store A Market,-12.34,ref-100\n",
        encoding="utf-8",
    )
    import_bank_csv(db_path, bank_csv, account="household")

    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE bank_transaction
            SET category_id = ?, is_recurring = 1, recurrence_cadence = 'monthly', recurrence_day_of_month = 5
            """,
            (category_id,),
        )
        conn.execute(
            """
            INSERT INTO income_forecast (forecast_date, forecast_amount_cents, note)
            VALUES ('2026-04-02', 300000, 'Client payment')
            """
        )
        conn.commit()

    set_monthly_goal(db_path, category_id=category_id, year=2026, month=4, amount_cents=80000)

    forecast = generate_monthly_forecast(db_path, year=2026, month=4)

    assert forecast["income_total_cents"] == 300000
    assert forecast["recurring_expense_total_cents"] == 1234
    assert forecast["net_before_variable_cents"] == 298766
    assert len(forecast["recurring_items"]) == 1
    assert len(forecast["category_goals"]) == 1
