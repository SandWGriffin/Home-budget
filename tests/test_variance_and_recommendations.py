from pathlib import Path

from src.home_budget.db import connect, init_db
from src.home_budget.importers import import_income_forecast_csv
from src.home_budget.services import (
    calculate_daily_cashflow,
    recommend_goal_adjustments,
    set_balance_snapshot,
    set_monthly_goal,
    upsert_category,
    add_transfer,
)


def test_transfer_affects_household_cashflow(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    income_csv = tmp_path / "income.csv"
    income_csv.write_text(
        "date,amount,note\n"
        "2026-04-01,100.00,seed\n",
        encoding="utf-8",
    )
    import_income_forecast_csv(db_path, income_csv)

    add_transfer(
        db_path=db_path,
        transfer_date="2026-04-02",
        from_account="business",
        to_account="household",
        amount_cents=5000,
        note="owner draw",
    )

    flow = calculate_daily_cashflow(
        db_path=db_path,
        start_date="2026-04-01",
        end_date="2026-04-03",
        opening_balance_cents=0,
        expense_mode="expected",
        account="household",
    )

    assert flow[0]["projected_balance_cents"] == 10000
    assert flow[1]["transfer_net_cents"] == 5000
    assert flow[1]["projected_balance_cents"] == 15000


def test_recommendations_flag_variance_and_overspend(tmp_path: Path):
    db_path = tmp_path / "budget.db"
    init_db(db_path)

    food_id = upsert_category(db_path, "Food")
    savings_id = upsert_category(db_path, "Retirement", is_savings_goal=True)
    set_monthly_goal(db_path, food_id, 2026, 4, 1000)
    set_monthly_goal(db_path, savings_id, 2026, 4, 10000)

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO import_batch (source_name) VALUES ('manual')
            """
        )
        batch_id = int(conn.execute("SELECT id FROM import_batch LIMIT 1").fetchone()[0])
        conn.execute(
            """
            INSERT INTO bank_transaction (
                import_batch_id, account, posted_date, description, normalized_description,
                amount_cents, dedupe_key, category_id
            ) VALUES (?, 'household', '2026-04-02', 'Groceries', 'groceries', -2500, 'k1', ?)
            """,
            (batch_id, food_id),
        )
        conn.commit()

    flow = [
        {
            "date": "2026-04-02",
            "projected_balance_cents": 5000,
            "income_cents": 0,
            "expense_cents": 0,
            "transfer_net_cents": 0,
        }
    ]
    set_balance_snapshot(db_path, "household", "2026-04-02", 2000)

    recs = recommend_goal_adjustments(
        db_path=db_path,
        year=2026,
        month=4,
        account="household",
        cashflow=flow,
        negative_variance_threshold_cents=1000,
    )

    rec_types = {r["type"] for r in recs}
    assert "cashflow_variance" in rec_types
    assert "category_overspend" in rec_types
