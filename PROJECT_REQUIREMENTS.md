# Home Budget Project Requirements

## Purpose
Build a home budget application that supports irregular income, category-based budgeting, recurring expense forecasting, and variance detection against real bank balances.

## Data Sources

### 1) Bank Exports
- Input files exported from the bank.
- Exports will overlap across days (for example, an export today and another export 4 days later may include the same transactions).
- The system must track line items across imports and deduplicate so previously seen transactions are not treated as new.

### 2) Income Forecast File
- User-provided forecast of income by date.
- Income is irregular and may be received in variable amounts.
- Income may come into a business account at the same bank.
- For now, transfers between business and home accounts are handled manually outside the app.

## Transaction Classification Requirements
- When a new cost item appears in bank input, user must be able to classify it.
- Classification includes:
  - Category
  - Recurring or non-recurring
  - If recurring:
    - Recurrence cadence: monthly, quarterly, annual
    - Day-of-month the recurring cost is incurred

## Categories and Goals
- Budget items are organized by category.
- User can set monthly goal/target values for each category.
- Some categories are savings-goal categories.
- Example savings goals:
  - Car expense rainy day fund
  - Wood floors
  - Retirement savings

## Recurring Expenses and Forecasting
- System must maintain recurring expenses by category.
- System must generate monthly forecast using:
  - Recurring costs
  - Income forecast
- Category goals act as bucket allocations.
- Actual bank line items mapped to a category should deduct from that category's budget.

### Example
- Food category target: $800 per month.
- Grocery transactions reduce the remaining amount in Food.
- Cash withdrawal use case must be supported:
  - User may withdraw cash intended for a category budget.
  - The system should still correctly account for spending against that category.

## Cash Flow Planning
- System must produce a day-by-day budget cash flow by category.
- Spending should be constrained by projected cash available on each date, based on forecasted income and expected expenses.

## Income Confirmation / Reconciliation
- System must provide a way to confirm forecasted income outcomes:
  - Whether income was actually received
  - Actual amount received
- This confirmation should feed into updated cash flow and budget planning.

## Variance Detection
- System must identify variance between expected budget position and actual bank position.
- Variance should be flagged for user review and potential goal adjustment.

### Example
- Expected amount on a date: $900
- Actual bank balance: $700
- Variance: -$200 (flag this)

## UI Requirement
- Project requires a user interface for entering, reviewing, and managing the above data and outcomes.

## Notes for Future Ingestion
This file is intended to be a canonical requirements source and can be ingested by future prompts or implementation phases.
