# Home Budget

Starter implementation for a home budget tool focused on:

- Overlapping bank export deduplication
- Income forecast imports
- Category and recurring metadata capture
- Rule-based auto-classification for new transactions
- Income confirmation (forecast vs actual)
- Monthly recurring + income forecast summary
- Planned expenses by date for expected spend tracking
- Category goal performance (goal vs actual vs remaining)
- Day-by-day category cashflow with expected vs actual variance
- Transfer tracking between business and household accounts
- Recommendation panel for goal adjustments when variance or overspend is detected
- Non-monthly recurring expense accrual targets (quarterly/annual)
- Daily cashflow projection
- Variance checks against actual balance snapshots

## Setup

```bash
python -m pip install -e .
python -m pip install pytest
```

## Initialize and Run UI

```bash
python -m src.main
streamlit run src/home_budget/ui.py
```

## Key UI Workflows

- Import overlapping bank CSV exports and skip duplicate transactions.
- Classify new transactions and optionally create reusable auto-rules.
- Enter monthly category goals (including savings categories).
- Enter planned expense items by date for expected-cash planning.
- Record transfers between business and household accounts.
- Confirm actual income receipts against income forecast rows.
- Generate monthly forecast and day-by-day cashflow in:
	- `expected` mode (planned + recurring expenses)
	- `actual` mode (posted bank transaction expenses)
- View category goal performance and variance against bank balance snapshots.
- Generate recommendation output to help adjust category goals when cashflow variance appears.
- For quarterly/annual recurring expenses, use monthly accrual targets shown in forecast/status to set aside funds before due month.

## CSV Formats

Bank import required columns:

- posted_date (YYYY-MM-DD)
- description
- amount

Optional bank columns:

- bank_reference
- balance

Existing bank export format supported (the download format you provided):

- `Date`, `Ref/Check`, `Description`, `Amount`, `Balance`, `Memo`, `Category`
- Date format: `MM/DD/YYYY`
- Importer skips `Daily Ledger Bal` rows
- Pending rows are skipped by default (optional in UI)

Existing export account detection:

- Transfer text `from *448 to *535` with positive amount maps file account to personal checking (`...6535`)
- Transfer text `from *448 to *535` with negative amount maps file account to business (`...4448`)
- Transfer text `from *535 to *448` is interpreted inversely

Income forecast required columns:

- date (YYYY-MM-DD)
- amount

Optional income column:

- note

## Test

```bash
pytest -q
```
