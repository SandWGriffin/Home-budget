from __future__ import annotations

from pathlib import Path

import streamlit as st

from .db import init_db
from .importers import import_bank_csv, import_income_forecast_csv
from .services import (
    add_planned_expense,
    apply_classification_rules,
    calculate_daily_cashflow,
    calculate_daily_category_cashflow,
    category_month_status,
    classify_transaction,
    create_transaction_rule,
    detect_balance_variance,
    generate_monthly_forecast,
    get_transaction,
    list_categories,
    list_income_forecasts,
    list_planned_expenses,
    list_unclassified_transactions,
    set_actual_income,
    set_balance_snapshot,
    set_monthly_goal,
    upsert_category,
)


DEFAULT_DB = Path("data/home_budget.db")


def _money_to_cents(amount: float) -> int:
    return int(round(amount * 100))


def _cents_to_money(amount_cents: int) -> float:
    return round(amount_cents / 100.0, 2)


def run() -> None:
    st.set_page_config(page_title="Home Budget", layout="wide")
    st.title("Home Budget")

    db_path = st.text_input("Database path", str(DEFAULT_DB))
    init_db(db_path)

    if st.button("Initialize database"):
        init_db(db_path)
        st.success("Database initialized")

    st.header("Import Bank Transactions")
    bank_file = st.file_uploader("Bank CSV", type=["csv"], key="bank_file")
    account = st.text_input("Account name", value="household")
    if st.button("Import bank CSV") and bank_file is not None:
        tmp_path = Path("data/_bank_upload.csv")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(bank_file.getvalue())
        stats = import_bank_csv(db_path, tmp_path, account)
        auto = apply_classification_rules(db_path)
        st.success(
            f"Imported: {stats['inserted']} new, {stats['duplicates']} duplicates skipped"
        )
        st.info(f"Auto-classified {auto} transactions from saved rules")

    st.header("Import Income Forecast")
    income_file = st.file_uploader("Income CSV", type=["csv"], key="income_file")
    if st.button("Import income CSV") and income_file is not None:
        tmp_path = Path("data/_income_upload.csv")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(income_file.getvalue())
        count = import_income_forecast_csv(db_path, tmp_path)
        st.success(f"Imported {count} income forecast rows")

    st.header("Create Category")
    category_name = st.text_input("Category name")
    is_savings = st.checkbox("Savings goal category")
    if st.button("Save category") and category_name.strip():
        cat_id = upsert_category(db_path, category_name.strip(), is_savings)
        st.success(f"Saved category #{cat_id}")

    categories = list_categories(db_path)
    if categories:
        st.caption("Existing categories")
        st.dataframe(categories, use_container_width=True)

    st.header("Auto-Classification Rules")
    if st.button("Apply rules to unclassified transactions"):
        updates = apply_classification_rules(db_path)
        st.success(f"Applied rules to {updates} transactions")

    rule_match_type = st.selectbox("Rule match type", ["contains", "exact"])
    rule_pattern = st.text_input("Rule pattern (normalized text)")
    rule_category_id = st.number_input("Rule Category ID", min_value=1, step=1, key="rule_cat")
    rule_is_recurring = st.checkbox("Rule marks recurring")
    rule_cadence = st.selectbox(
        "Rule cadence",
        ["", "monthly", "quarterly", "annual"],
        index=0,
        disabled=not rule_is_recurring,
    )
    rule_day = st.number_input(
        "Rule day of month",
        min_value=1,
        max_value=31,
        value=1,
        disabled=not rule_is_recurring,
        key="rule_day",
    )
    if st.button("Save rule") and rule_pattern.strip():
        rule_id = create_transaction_rule(
            db_path=db_path,
            match_type=rule_match_type,
            pattern=rule_pattern.strip(),
            category_id=int(rule_category_id),
            is_recurring=rule_is_recurring,
            recurrence_cadence=rule_cadence or None,
            recurrence_day_of_month=int(rule_day) if rule_is_recurring else None,
        )
        st.success(f"Saved rule #{rule_id}")

    st.header("Classify New Transactions")
    unclassified = list_unclassified_transactions(db_path)
    st.write(f"Unclassified transactions: {len(unclassified)}")
    if unclassified:
        st.dataframe(unclassified, use_container_width=True)
        tx_id = st.number_input("Transaction ID", min_value=1, step=1)
        category_id = st.number_input("Category ID", min_value=1, step=1, key="cat_id")
        recurring = st.checkbox("Recurring")
        create_rule_from_tx = st.checkbox("Create auto-rule from this transaction")
        cadence = st.selectbox(
            "Cadence",
            ["", "monthly", "quarterly", "annual"],
            index=0,
            disabled=not recurring,
        )
        day_of_month = st.number_input(
            "Day of month",
            min_value=1,
            max_value=31,
            value=1,
            disabled=not recurring,
        )
        if st.button("Apply classification"):
            classify_transaction(
                db_path=db_path,
                transaction_id=int(tx_id),
                category_id=int(category_id),
                is_recurring=recurring,
                recurrence_cadence=cadence or None,
                recurrence_day_of_month=int(day_of_month) if recurring else None,
            )
            if create_rule_from_tx:
                tx = get_transaction(db_path, int(tx_id))
                if tx:
                    create_transaction_rule(
                        db_path=db_path,
                        match_type="contains",
                        pattern=str(tx["normalized_description"]),
                        category_id=int(category_id),
                        is_recurring=recurring,
                        recurrence_cadence=cadence or None,
                        recurrence_day_of_month=int(day_of_month) if recurring else None,
                    )
            st.success("Transaction classified")

    st.header("Set Monthly Category Goal")
    goal_category_id = st.number_input("Goal Category ID", min_value=1, step=1, key="goal_cat")
    goal_year = st.number_input("Year", min_value=2020, max_value=2100, value=2026)
    goal_month = st.number_input("Month", min_value=1, max_value=12, value=1)
    goal_amount = st.number_input("Amount", value=0.0, step=10.0)
    if st.button("Save monthly goal"):
        set_monthly_goal(
            db_path=db_path,
            category_id=int(goal_category_id),
            year=int(goal_year),
            month=int(goal_month),
            amount_cents=_money_to_cents(goal_amount),
        )
        st.success("Goal saved")

    st.header("Planned Expense by Date")
    planned_date = st.text_input("Planned date (YYYY-MM-DD)")
    planned_category_id = st.number_input(
        "Planned Category ID", min_value=1, step=1, key="planned_cat"
    )
    planned_amount = st.number_input("Planned amount", value=0.0, step=10.0)
    planned_note = st.text_input("Planned note")
    if st.button("Save planned expense") and planned_date:
        planned_id = add_planned_expense(
            db_path=db_path,
            planned_date=planned_date,
            category_id=int(planned_category_id),
            amount_cents=_money_to_cents(planned_amount),
            note=planned_note.strip() or None,
        )
        st.success(f"Planned expense saved #{planned_id}")

    planned_expenses = list_planned_expenses(db_path)
    if planned_expenses:
        st.dataframe(planned_expenses, use_container_width=True)

    st.header("Balance Snapshot")
    snapshot_account = st.text_input("Snapshot account", value="household")
    snapshot_date = st.text_input("Snapshot date (YYYY-MM-DD)")
    snapshot_balance = st.number_input("Snapshot balance", value=0.0, step=10.0)
    if st.button("Save balance snapshot") and snapshot_date:
        set_balance_snapshot(
            db_path=db_path,
            account=snapshot_account,
            snapshot_date=snapshot_date,
            balance_cents=_money_to_cents(snapshot_balance),
        )
        st.success("Snapshot saved")

    st.header("Income Confirmation")
    income_rows = list_income_forecasts(db_path)
    if income_rows:
        st.dataframe(income_rows, use_container_width=True)
    income_id = st.number_input("Income row ID", min_value=1, step=1, key="income_id")
    income_received_date = st.text_input("Actual received date (YYYY-MM-DD)")
    income_received_amount = st.number_input("Actual received amount", value=0.0, step=50.0)
    if st.button("Confirm actual income") and income_received_date:
        set_actual_income(
            db_path=db_path,
            income_id=int(income_id),
            actual_received_date=income_received_date,
            actual_amount_cents=_money_to_cents(income_received_amount),
        )
        st.success("Income confirmation saved")

    st.header("Monthly Forecast")
    forecast_year = st.number_input("Forecast year", min_value=2020, max_value=2100, value=2026)
    forecast_month = st.number_input("Forecast month", min_value=1, max_value=12, value=1)
    if st.button("Generate monthly forecast"):
        forecast = generate_monthly_forecast(db_path, int(forecast_year), int(forecast_month))
        st.write(
            {
                "period": forecast["period"],
                "income_total": _cents_to_money(forecast["income_total_cents"]),
                "recurring_expense_total": _cents_to_money(
                    forecast["recurring_expense_total_cents"]
                ),
                "net_before_variable": _cents_to_money(
                    forecast["net_before_variable_cents"]
                ),
            }
        )
        st.subheader("Recurring Items Included")
        st.dataframe(forecast["recurring_items"], use_container_width=True)
        st.subheader("Category Monthly Goals")
        st.dataframe(forecast["category_goals"], use_container_width=True)

    st.header("Category Goal Performance")
    status_year = st.number_input("Status year", min_value=2020, max_value=2100, value=2026)
    status_month = st.number_input("Status month", min_value=1, max_value=12, value=1)
    if st.button("Show category status"):
        status = category_month_status(db_path, int(status_year), int(status_month))
        st.dataframe(status, use_container_width=True)

    st.header("Daily Cash Flow")
    start_date = st.text_input("Start date (YYYY-MM-DD)")
    end_date = st.text_input("End date (YYYY-MM-DD)")
    opening_balance = st.number_input("Opening balance", value=0.0, step=50.0)
    forecast_account = st.text_input("Account for variance", value="household")
    expense_mode = st.selectbox(
        "Expense mode",
        ["expected", "actual"],
        help="Expected mode uses planned expenses and recurring schedules. Actual mode uses bank transactions.",
    )

    if st.button("Generate cash flow") and start_date and end_date:
        cashflow = calculate_daily_cashflow(
            db_path=db_path,
            start_date=start_date,
            end_date=end_date,
            opening_balance_cents=_money_to_cents(opening_balance),
            expense_mode=expense_mode,
        )
        st.subheader("Projected Cash Flow")
        st.dataframe(cashflow, use_container_width=True)

        category_daily = calculate_daily_category_cashflow(db_path, start_date, end_date)
        st.subheader("Daily Cash Flow by Category")
        st.dataframe(category_daily, use_container_width=True)

        variances = detect_balance_variance(db_path, forecast_account, cashflow)
        st.subheader("Variance vs Actual Snapshot")
        st.dataframe(variances, use_container_width=True)


if __name__ == "__main__":
    run()
