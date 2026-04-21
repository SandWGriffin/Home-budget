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
- Confirm actual income receipts against income forecast rows.
- Generate monthly forecast and day-by-day cashflow in:
	- `expected` mode (planned + recurring expenses)
	- `actual` mode (posted bank transaction expenses)
- View category goal performance and variance against bank balance snapshots.

## CSV Formats

Bank import required columns:

- posted_date (YYYY-MM-DD)
- description
- amount

Optional bank columns:

- bank_reference
- balance

Income forecast required columns:

- date (YYYY-MM-DD)
- amount

Optional income column:

- note

## Test

```bash
pytest -q
```
