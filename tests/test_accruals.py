from pathlib import Path

from src.home_budget.db import connect, init_db
from src.home_budget.services import (
    category_month_status,
    generate_monthly_forecast,
    non_monthly_accrual_targets,
    upsert_category,
)


def test_non_monthly_accrual_targets_for_quarterly_and_annual(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    home_id = upsert_category(db_path, "Home")
    insurance_id = upsert_category(db_path, "Insurance")

    with connect(db_path) as conn:
        conn.execute("INSERT INTO import_batch (source_name) VALUES ('manual')")
        batch_id = int(conn.execute("SELECT id FROM import_batch LIMIT 1").fetchone()[0])
        conn.execute(
            """
            INSERT INTO bank_transaction (
              import_batch_id, account, posted_date, description, normalized_description,
              amount_cents, dedupe_key, category_id, is_recurring, recurrence_cadence, recurrence_day_of_month
            ) VALUES (?, 'household', '2026-01-15', 'Quarterly service', 'quarterly service', -30000, 'q1', ?, 1, 'quarterly', 15)
            """,
            (batch_id, home_id),
        )
        conn.execute(
            """
            INSERT INTO bank_transaction (
              import_batch_id, account, posted_date, description, normalized_description,
              amount_cents, dedupe_key, category_id, is_recurring, recurrence_cadence, recurrence_day_of_month
            ) VALUES (?, 'household', '2026-02-01', 'Annual insurance', 'annual insurance', -120000, 'a1', ?, 1, 'annual', 1)
            """,
            (batch_id, insurance_id),
        )
        conn.commit()

    accruals = non_monthly_accrual_targets(db_path, 2026, 4)
    by_category = {item["category"]: item for item in accruals}

    assert by_category["Home"]["monthly_accrual_cents"] == 10000
    assert by_category["Insurance"]["monthly_accrual_cents"] == 10000


def test_month_status_includes_accrual_fields(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    home_id = upsert_category(db_path, "Home")

    with connect(db_path) as conn:
        conn.execute("INSERT INTO import_batch (source_name) VALUES ('manual')")
        batch_id = int(conn.execute("SELECT id FROM import_batch LIMIT 1").fetchone()[0])
        conn.execute(
            """
            INSERT INTO category_monthly_goal (category_id, year, month, amount_cents)
            VALUES (?, 2026, 4, 50000)
            """,
            (home_id,),
        )
        conn.execute(
            """
            INSERT INTO bank_transaction (
              import_batch_id, account, posted_date, description, normalized_description,
              amount_cents, dedupe_key, category_id, is_recurring, recurrence_cadence, recurrence_day_of_month
            ) VALUES (?, 'household', '2026-01-10', 'Quarterly service', 'quarterly service', -30000, 'q2', ?, 1, 'quarterly', 10)
            """,
            (batch_id, home_id),
        )
        conn.commit()

    status = category_month_status(db_path, 2026, 4)
    home = [row for row in status if row["category"] == "Home"][0]

    assert home["accrual_target_cents"] == 10000
    assert home["remaining_after_accrual_cents"] == 40000


def test_monthly_forecast_includes_accrual_totals(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    home_id = upsert_category(db_path, "Home")

    with connect(db_path) as conn:
        conn.execute("INSERT INTO import_batch (source_name) VALUES ('manual')")
        batch_id = int(conn.execute("SELECT id FROM import_batch LIMIT 1").fetchone()[0])
        conn.execute(
            """
            INSERT INTO income_forecast (forecast_date, forecast_amount_cents, note)
            VALUES ('2026-04-02', 200000, 'income')
            """
        )
        conn.execute(
            """
            INSERT INTO bank_transaction (
              import_batch_id, account, posted_date, description, normalized_description,
              amount_cents, dedupe_key, category_id, is_recurring, recurrence_cadence, recurrence_day_of_month
            ) VALUES (?, 'household', '2026-01-10', 'Quarterly service', 'quarterly service', -30000, 'q3', ?, 1, 'quarterly', 10)
            """,
            (batch_id, home_id),
        )
        conn.commit()

    forecast = generate_monthly_forecast(db_path, 2026, 4)

    assert forecast["non_monthly_accrual_total_cents"] == 10000
    assert forecast["net_after_accrual_cents"] == forecast["net_before_variable_cents"] - 10000
    assert len(forecast["accrual_items"]) == 1
