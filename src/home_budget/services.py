from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from .db import connect


def _to_iso(d: date) -> str:
    return d.isoformat()


def _to_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _months_between(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def _last_day_of_month(year: int, month: int) -> int:
    return int(calendar.monthrange(year, month)[1])


def _recurs_in_month(anchor: date, cadence: str, target_year: int, target_month: int) -> bool:
    target_period = date(target_year, target_month, 1)
    anchor_period = date(anchor.year, anchor.month, 1)
    if target_period < anchor_period:
        return False
    if cadence == "monthly":
        return True
    if cadence == "quarterly":
        return _months_between(target_period, anchor_period) % 3 == 0
    if cadence == "annual":
        return target_month == anchor.month
    return False


def upsert_category(db_path: str | Path, name: str, is_savings_goal: bool = False) -> int:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO category (name, is_savings_goal)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET is_savings_goal = excluded.is_savings_goal
            """,
            (name.strip(), 1 if is_savings_goal else 0),
        )
        row = conn.execute("SELECT id FROM category WHERE name = ?", (name.strip(),)).fetchone()
        conn.commit()
    return int(row[0])


def classify_transaction(
    db_path: str | Path,
    transaction_id: int,
    category_id: int,
    is_recurring: bool,
    recurrence_cadence: str | None,
    recurrence_day_of_month: int | None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE bank_transaction
            SET category_id = ?,
                is_recurring = ?,
                recurrence_cadence = ?,
                recurrence_day_of_month = ?
            WHERE id = ?
            """,
            (
                category_id,
                1 if is_recurring else 0,
                recurrence_cadence,
                recurrence_day_of_month,
                transaction_id,
            ),
        )
        conn.commit()


def get_transaction(db_path: str | Path, transaction_id: int) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, normalized_description
            FROM bank_transaction
            WHERE id = ?
            """,
            (transaction_id,),
        ).fetchone()
    return dict(row) if row else None


def create_transaction_rule(
    db_path: str | Path,
    match_type: str,
    pattern: str,
    category_id: int,
    is_recurring: bool,
    recurrence_cadence: str | None,
    recurrence_day_of_month: int | None,
    priority: int = 100,
) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO transaction_rule (
                match_type,
                pattern,
                category_id,
                is_recurring,
                recurrence_cadence,
                recurrence_day_of_month,
                priority,
                active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                match_type,
                pattern.strip().lower(),
                category_id,
                1 if is_recurring else 0,
                recurrence_cadence,
                recurrence_day_of_month,
                priority,
            ),
        )
        conn.commit()
    return int(cur.lastrowid)


def apply_classification_rules(db_path: str | Path) -> int:
    updates = 0
    with connect(db_path) as conn:
        txns = conn.execute(
            """
            SELECT id, normalized_description
            FROM bank_transaction
            WHERE category_id IS NULL
            ORDER BY id
            """
        ).fetchall()

        rules = conn.execute(
            """
            SELECT
                id,
                match_type,
                pattern,
                category_id,
                is_recurring,
                recurrence_cadence,
                recurrence_day_of_month
            FROM transaction_rule
            WHERE active = 1
            ORDER BY priority ASC, id ASC
            """
        ).fetchall()

        for txn in txns:
            normalized = txn["normalized_description"]
            matched_rule = None
            for rule in rules:
                match_type = rule["match_type"]
                pattern = rule["pattern"]
                if match_type == "exact" and normalized == pattern:
                    matched_rule = rule
                    break
                if match_type == "contains" and pattern in normalized:
                    matched_rule = rule
                    break

            if matched_rule is None:
                continue

            conn.execute(
                """
                UPDATE bank_transaction
                SET category_id = ?,
                    is_recurring = ?,
                    recurrence_cadence = ?,
                    recurrence_day_of_month = ?
                WHERE id = ?
                """,
                (
                    int(matched_rule["category_id"]),
                    matched_rule["is_recurring"],
                    matched_rule["recurrence_cadence"],
                    matched_rule["recurrence_day_of_month"],
                    int(txn["id"]),
                ),
            )
            updates += 1

        conn.commit()

    return updates


def set_monthly_goal(
    db_path: str | Path,
    category_id: int,
    year: int,
    month: int,
    amount_cents: int,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO category_monthly_goal (category_id, year, month, amount_cents)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(category_id, year, month)
            DO UPDATE SET amount_cents = excluded.amount_cents
            """,
            (category_id, year, month, amount_cents),
        )
        conn.commit()


def add_planned_expense(
    db_path: str | Path,
    planned_date: str,
    category_id: int,
    amount_cents: int,
    note: str | None = None,
) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO planned_expense (planned_date, category_id, amount_cents, note, source)
            VALUES (?, ?, ?, ?, 'manual')
            """,
            (planned_date, category_id, amount_cents, note),
        )
        conn.commit()
    return int(cur.lastrowid)


def add_transfer(
    db_path: str | Path,
    transfer_date: str,
    from_account: str,
    to_account: str,
    amount_cents: int,
    note: str | None = None,
) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO transfer_entry (transfer_date, from_account, to_account, amount_cents, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (transfer_date, from_account.strip(), to_account.strip(), amount_cents, note),
        )
        conn.commit()
    return int(cur.lastrowid)


def list_unclassified_transactions(db_path: str | Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, posted_date, account, description, amount_cents
            FROM bank_transaction
            WHERE category_id IS NULL
            ORDER BY posted_date, id
            """
        ).fetchall()
    return [dict(r) for r in rows]


def list_categories(db_path: str | Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, name, is_savings_goal
            FROM category
            ORDER BY name
            """
        ).fetchall()
    return [dict(r) for r in rows]


def list_income_forecasts(db_path: str | Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                forecast_date,
                forecast_amount_cents,
                note,
                actual_received_date,
                actual_amount_cents
            FROM income_forecast
            ORDER BY forecast_date, id
            """
        ).fetchall()
    return [dict(r) for r in rows]


def list_planned_expenses(db_path: str | Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.planned_date, c.name AS category, p.amount_cents, p.note
            FROM planned_expense p
            JOIN category c ON c.id = p.category_id
            ORDER BY p.planned_date, p.id
            """
        ).fetchall()
    return [dict(r) for r in rows]


def list_transfers(db_path: str | Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, transfer_date, from_account, to_account, amount_cents, note
            FROM transfer_entry
            ORDER BY transfer_date, id
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _transfer_net_by_day(
    conn,
    account: str,
    start_date: str,
    end_date: str,
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT transfer_date, from_account, to_account, amount_cents
        FROM transfer_entry
        WHERE transfer_date >= ? AND transfer_date <= ?
        """,
        (start_date, end_date),
    ).fetchall()
    net_by_day: dict[str, int] = {}
    for row in rows:
        day = str(row["transfer_date"])
        amount = int(row["amount_cents"])
        net = 0
        if row["to_account"] == account:
            net += amount
        if row["from_account"] == account:
            net -= amount
        if net:
            net_by_day[day] = net_by_day.get(day, 0) + net
    return net_by_day


def _expected_expense_by_day(
    conn,
    start_date: str,
    end_date: str,
) -> dict[str, int]:
    by_day: dict[str, int] = {}

    planned_rows = conn.execute(
        """
        SELECT planned_date, amount_cents
        FROM planned_expense
        WHERE planned_date >= ? AND planned_date <= ?
        """,
        (start_date, end_date),
    ).fetchall()
    for row in planned_rows:
        day = row["planned_date"]
        by_day[day] = by_day.get(day, 0) + int(row["amount_cents"])

    recurring_rows = conn.execute(
        """
        SELECT posted_date, amount_cents, recurrence_cadence, recurrence_day_of_month
        FROM bank_transaction
        WHERE is_recurring = 1
          AND category_id IS NOT NULL
          AND recurrence_cadence IS NOT NULL
        """
    ).fetchall()

    start = _to_date(start_date)
    end = _to_date(end_date)
    for row in recurring_rows:
        anchor = _to_date(row["posted_date"])
        cadence = str(row["recurrence_cadence"])
        configured_day = row["recurrence_day_of_month"]
        target = date(start.year, start.month, 1)
        while target <= end:
            if _recurs_in_month(anchor, cadence, target.year, target.month):
                schedule_day = int(configured_day) if configured_day else anchor.day
                day = min(schedule_day, _last_day_of_month(target.year, target.month))
                instance = date(target.year, target.month, day)
                if start <= instance <= end:
                    by_day[instance.isoformat()] = by_day.get(instance.isoformat(), 0) + abs(
                        int(row["amount_cents"])
                    )
            if target.month == 12:
                target = date(target.year + 1, 1, 1)
            else:
                target = date(target.year, target.month + 1, 1)

    return by_day


def _actual_expense_by_day(
    conn,
    start_date: str,
    end_date: str,
) -> dict[str, int]:
    by_day: dict[str, int] = {}
    txn_rows = conn.execute(
        """
        SELECT posted_date, amount_cents
        FROM bank_transaction
        WHERE posted_date >= ? AND posted_date <= ?
        """,
        (start_date, end_date),
    ).fetchall()
    for row in txn_rows:
        day = row["posted_date"]
        amount = int(row["amount_cents"])
        if amount < 0:
            by_day[day] = by_day.get(day, 0) + abs(amount)
    return by_day


def set_actual_income(
    db_path: str | Path,
    income_id: int,
    actual_received_date: str,
    actual_amount_cents: int,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE income_forecast
            SET actual_received_date = ?, actual_amount_cents = ?
            WHERE id = ?
            """,
            (actual_received_date, actual_amount_cents, income_id),
        )
        conn.commit()


def set_balance_snapshot(
    db_path: str | Path,
    account: str,
    snapshot_date: str,
    balance_cents: int,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO bank_balance_snapshot (account, snapshot_date, balance_cents)
            VALUES (?, ?, ?)
            ON CONFLICT(account, snapshot_date)
            DO UPDATE SET balance_cents = excluded.balance_cents
            """,
            (account, snapshot_date, balance_cents),
        )
        conn.commit()


def calculate_daily_cashflow(
    db_path: str | Path,
    start_date: str,
    end_date: str,
    opening_balance_cents: int,
    expense_mode: Literal["actual", "expected"] = "actual",
    account: str = "household",
) -> list[dict]:
    start = _to_date(start_date)
    end = _to_date(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    income_by_day: dict[str, int] = {}
    expense_by_day: dict[str, int]
    transfer_net_by_day: dict[str, int]

    with connect(db_path) as conn:
        income_rows = conn.execute(
            """
            SELECT
              COALESCE(actual_received_date, forecast_date) AS income_date,
              COALESCE(actual_amount_cents, forecast_amount_cents) AS amount_cents
            FROM income_forecast
            """
        ).fetchall()
        for row in income_rows:
            income_by_day[row["income_date"]] = income_by_day.get(row["income_date"], 0) + int(
                row["amount_cents"]
            )

        if expense_mode == "expected":
            expense_by_day = _expected_expense_by_day(conn, start_date, end_date)
        else:
            expense_by_day = _actual_expense_by_day(conn, start_date, end_date)

        transfer_net_by_day = _transfer_net_by_day(conn, account, start_date, end_date)

    running = opening_balance_cents
    output: list[dict] = []
    cursor = start
    while cursor <= end:
        iso = _to_iso(cursor)
        income = income_by_day.get(iso, 0)
        expense = expense_by_day.get(iso, 0)
        transfer_net = transfer_net_by_day.get(iso, 0)
        running += income - expense + transfer_net
        output.append(
            {
                "date": iso,
                "income_cents": income,
                "expense_cents": expense,
                "transfer_net_cents": transfer_net,
                "projected_balance_cents": running,
            }
        )
        cursor += timedelta(days=1)

    return output


def calculate_daily_category_cashflow(
    db_path: str | Path,
    start_date: str,
    end_date: str,
) -> list[dict]:
    start = _to_date(start_date)
    end = _to_date(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    expected: dict[tuple[str, int], int] = {}
    actual: dict[tuple[str, int], int] = {}

    with connect(db_path) as conn:
        categories = conn.execute("SELECT id, name FROM category ORDER BY name").fetchall()
        category_names = {int(row["id"]): str(row["name"]) for row in categories}

        planned_rows = conn.execute(
            """
            SELECT planned_date, category_id, amount_cents
            FROM planned_expense
            WHERE planned_date >= ? AND planned_date <= ?
            """,
            (start_date, end_date),
        ).fetchall()
        for row in planned_rows:
            key = (str(row["planned_date"]), int(row["category_id"]))
            expected[key] = expected.get(key, 0) + int(row["amount_cents"])

        recurring_rows = conn.execute(
            """
            SELECT posted_date, amount_cents, recurrence_cadence, recurrence_day_of_month, category_id
            FROM bank_transaction
            WHERE is_recurring = 1
              AND category_id IS NOT NULL
              AND recurrence_cadence IS NOT NULL
            """
        ).fetchall()
        for row in recurring_rows:
            anchor = _to_date(row["posted_date"])
            cadence = str(row["recurrence_cadence"])
            category_id = int(row["category_id"])
            configured_day = row["recurrence_day_of_month"]
            target = date(start.year, start.month, 1)
            while target <= end:
                if _recurs_in_month(anchor, cadence, target.year, target.month):
                    schedule_day = int(configured_day) if configured_day else anchor.day
                    day = min(schedule_day, _last_day_of_month(target.year, target.month))
                    instance = date(target.year, target.month, day)
                    if start <= instance <= end:
                        key = (instance.isoformat(), category_id)
                        expected[key] = expected.get(key, 0) + abs(int(row["amount_cents"]))
                if target.month == 12:
                    target = date(target.year + 1, 1, 1)
                else:
                    target = date(target.year, target.month + 1, 1)

        actual_rows = conn.execute(
            """
            SELECT posted_date, category_id, amount_cents
            FROM bank_transaction
            WHERE posted_date >= ? AND posted_date <= ?
              AND category_id IS NOT NULL
            """,
            (start_date, end_date),
        ).fetchall()
        for row in actual_rows:
            amount = int(row["amount_cents"])
            if amount >= 0:
                continue
            key = (str(row["posted_date"]), int(row["category_id"]))
            actual[key] = actual.get(key, 0) + abs(amount)

    rows: list[dict] = []
    cursor = start
    category_ids = sorted(category_names.keys())
    while cursor <= end:
        day = cursor.isoformat()
        for category_id in category_ids:
            key = (day, category_id)
            expected_cents = expected.get(key, 0)
            actual_cents = actual.get(key, 0)
            if expected_cents == 0 and actual_cents == 0:
                continue
            rows.append(
                {
                    "date": day,
                    "category_id": category_id,
                    "category": category_names[category_id],
                    "expected_expense_cents": expected_cents,
                    "actual_expense_cents": actual_cents,
                    "variance_cents": actual_cents - expected_cents,
                }
            )
        cursor += timedelta(days=1)

    return rows


def category_month_status(db_path: str | Path, year: int, month: int) -> list[dict]:
    month_start = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
              c.id AS category_id,
              c.name AS category,
              c.is_savings_goal,
              COALESCE(g.amount_cents, 0) AS goal_cents,
              COALESCE(SUM(CASE WHEN bt.amount_cents < 0 THEN ABS(bt.amount_cents) ELSE 0 END), 0) AS actual_spend_cents
            FROM category c
            LEFT JOIN category_monthly_goal g
              ON g.category_id = c.id AND g.year = ? AND g.month = ?
            LEFT JOIN bank_transaction bt
              ON bt.category_id = c.id
             AND bt.posted_date >= ?
             AND bt.posted_date < ?
            GROUP BY c.id, c.name, c.is_savings_goal, g.amount_cents
            ORDER BY c.name
            """,
            (year, month, month_start.isoformat(), next_month.isoformat()),
        ).fetchall()

    output: list[dict] = []
    for row in rows:
        goal = int(row["goal_cents"])
        actual_spend = int(row["actual_spend_cents"])
        output.append(
            {
                "category_id": int(row["category_id"]),
                "category": row["category"],
                "is_savings_goal": bool(row["is_savings_goal"]),
                "goal_cents": goal,
                "actual_spend_cents": actual_spend,
                "remaining_cents": goal - actual_spend,
            }
        )

    return output


def detect_balance_variance(
    db_path: str | Path,
    account: str,
    cashflow: list[dict],
) -> list[dict]:
    projected_by_day = {row["date"]: row["projected_balance_cents"] for row in cashflow}
    with connect(db_path) as conn:
        snapshots = conn.execute(
            """
            SELECT snapshot_date, balance_cents
            FROM bank_balance_snapshot
            WHERE account = ?
            ORDER BY snapshot_date
            """,
            (account,),
        ).fetchall()

    variances: list[dict] = []
    for row in snapshots:
        day = row["snapshot_date"]
        if day not in projected_by_day:
            continue
        actual = int(row["balance_cents"])
        projected = int(projected_by_day[day])
        variances.append(
            {
                "date": day,
                "actual_balance_cents": actual,
                "projected_balance_cents": projected,
                "variance_cents": actual - projected,
            }
        )
    return variances


def generate_monthly_forecast(
    db_path: str | Path,
    year: int,
    month: int,
) -> dict:
    period_start = date(year, month, 1)
    if month == 12:
        period_end = date(year + 1, 1, 1)
    else:
        period_end = date(year, month + 1, 1)

    recurring_total = 0
    recurring_rows: list[dict] = []

    with connect(db_path) as conn:
        recurring = conn.execute(
            """
            SELECT
              bt.id,
              bt.posted_date,
              bt.description,
              bt.amount_cents,
              bt.recurrence_cadence,
              c.name AS category_name
            FROM bank_transaction bt
            LEFT JOIN category c ON c.id = bt.category_id
            WHERE bt.is_recurring = 1
              AND bt.category_id IS NOT NULL
            ORDER BY bt.id
            """
        ).fetchall()

        for row in recurring:
            cadence = row["recurrence_cadence"]
            anchor = _to_date(row["posted_date"])
            include = False
            if cadence == "monthly":
                include = period_start >= date(anchor.year, anchor.month, 1)
            elif cadence == "quarterly":
                month_diff = _months_between(period_start, date(anchor.year, anchor.month, 1))
                include = month_diff >= 0 and month_diff % 3 == 0
            elif cadence == "annual":
                include = period_start.month == anchor.month and period_start >= date(anchor.year, anchor.month, 1)

            if include:
                expense = abs(int(row["amount_cents"]))
                recurring_total += expense
                recurring_rows.append(
                    {
                        "transaction_id": int(row["id"]),
                        "category": row["category_name"],
                        "description": row["description"],
                        "cadence": cadence,
                        "amount_cents": expense,
                    }
                )

        income_rows = conn.execute(
            """
            SELECT
              COALESCE(actual_amount_cents, forecast_amount_cents) AS amount_cents
            FROM income_forecast
            WHERE COALESCE(actual_received_date, forecast_date) >= ?
              AND COALESCE(actual_received_date, forecast_date) < ?
            """,
            (period_start.isoformat(), period_end.isoformat()),
        ).fetchall()
        income_total = sum(int(r["amount_cents"]) for r in income_rows)

        goals = conn.execute(
            """
            SELECT c.name AS category_name, g.amount_cents
            FROM category_monthly_goal g
            JOIN category c ON c.id = g.category_id
            WHERE g.year = ? AND g.month = ?
            ORDER BY c.name
            """,
            (year, month),
        ).fetchall()

    net_cents = income_total - recurring_total
    return {
        "period": f"{year:04d}-{month:02d}",
        "income_total_cents": income_total,
        "recurring_expense_total_cents": recurring_total,
        "net_before_variable_cents": net_cents,
        "recurring_items": recurring_rows,
        "category_goals": [
            {"category": row["category_name"], "amount_cents": int(row["amount_cents"])}
            for row in goals
        ],
    }


def recommend_goal_adjustments(
    db_path: str | Path,
    year: int,
    month: int,
    account: str,
    cashflow: list[dict],
    negative_variance_threshold_cents: int = 1000,
) -> list[dict]:
    recommendations: list[dict] = []

    variances = detect_balance_variance(db_path, account, cashflow)
    significant_negative = [
        v for v in variances if int(v["variance_cents"]) <= -abs(negative_variance_threshold_cents)
    ]
    if significant_negative:
        worst = min(significant_negative, key=lambda item: int(item["variance_cents"]))
        recommendations.append(
            {
                "type": "cashflow_variance",
                "priority": "high",
                "date": worst["date"],
                "message": (
                    "Actual bank balance is below projection. "
                    "Review income timing, transfers, and discretionary category goals."
                ),
                "variance_cents": int(worst["variance_cents"]),
            }
        )

    statuses = category_month_status(db_path, year, month)
    overspent = [s for s in statuses if int(s["remaining_cents"]) < 0]
    for status in sorted(overspent, key=lambda s: int(s["remaining_cents"])):
        recommendations.append(
            {
                "type": "category_overspend",
                "priority": "medium",
                "category": status["category"],
                "message": "Category is over monthly goal. Consider increasing goal or reducing spend.",
                "remaining_cents": int(status["remaining_cents"]),
                "goal_cents": int(status["goal_cents"]),
                "actual_spend_cents": int(status["actual_spend_cents"]),
            }
        )

    savings_with_room = [
        s
        for s in statuses
        if bool(s["is_savings_goal"]) and int(s["remaining_cents"]) > 0
    ]
    if significant_negative and savings_with_room:
        top = sorted(savings_with_room, key=lambda s: int(s["remaining_cents"]), reverse=True)[:3]
        for item in top:
            recommendations.append(
                {
                    "type": "reallocate_savings",
                    "priority": "medium",
                    "category": item["category"],
                    "message": (
                        "Savings goal has remaining room. Consider temporary reallocation "
                        "to cover near-term cash deficit."
                    ),
                    "remaining_cents": int(item["remaining_cents"]),
                }
            )

    if not recommendations:
        recommendations.append(
            {
                "type": "healthy",
                "priority": "low",
                "message": "No major variance or category overspend issues detected for this period.",
            }
        )

    return recommendations
