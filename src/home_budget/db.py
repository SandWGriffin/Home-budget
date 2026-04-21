from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS import_batch (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                imported_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS category (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                is_savings_goal INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bank_transaction (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id INTEGER NOT NULL,
                account TEXT NOT NULL,
                posted_date TEXT NOT NULL,
                description TEXT NOT NULL,
                normalized_description TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                balance_cents INTEGER,
                bank_reference TEXT,
                dedupe_key TEXT NOT NULL UNIQUE,
                category_id INTEGER,
                is_recurring INTEGER,
                recurrence_cadence TEXT,
                recurrence_day_of_month INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (import_batch_id) REFERENCES import_batch(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES category(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS transaction_rule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_type TEXT NOT NULL,
                pattern TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                is_recurring INTEGER,
                recurrence_cadence TEXT,
                recurrence_day_of_month INTEGER,
                priority INTEGER NOT NULL DEFAULT 100,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (category_id) REFERENCES category(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS category_monthly_goal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                UNIQUE(category_id, year, month),
                FOREIGN KEY (category_id) REFERENCES category(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS planned_expense (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                planned_date TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                note TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (category_id) REFERENCES category(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS income_forecast (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                forecast_date TEXT NOT NULL,
                forecast_amount_cents INTEGER NOT NULL,
                note TEXT,
                actual_received_date TEXT,
                actual_amount_cents INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bank_balance_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                balance_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(account, snapshot_date)
            );
            """
        )


def create_import_batch(conn: sqlite3.Connection, source_name: str) -> int:
    cur = conn.execute(
        "INSERT INTO import_batch (source_name) VALUES (?)",
        (source_name,),
    )
    return int(cur.lastrowid)
