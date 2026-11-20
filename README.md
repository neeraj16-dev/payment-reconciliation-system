# Payment Reconciliation System

Reconciles platform transaction records against bank settlement records at month-end,
and explains every rupee of difference.

- **Backend:** FastAPI + pandas + `decimal.Decimal` + Pydantic (`backend/`)
- **Frontend:** React (Vite) dashboard (`frontend/`)
- **Data:** synthetic October 2026 INR datasets and assumptions (`datasets/`, read-only)

## Running

```bash
# Backend (http://127.0.0.1:8000, docs at /docs)
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (http://localhost:5173; /api is proxied to the backend)
cd frontend
npm install
npm run dev
```

Tests: `cd backend && python -m pytest`

## API

`POST /api/reconcile` (multipart form)

| Field | Required | Notes |
|---|---|---|
| `platform_file` | yes | CSV: `transaction_id, transaction_date, transaction_type, status, currency, gross_amount, original_transaction_id` (extra columns ignored) |
| `bank_file` | yes | CSV: `settlement_id, transaction_id, settlement_date, transaction_type, status, currency, settlement_amount` |
| `cutoff_date` | no | `YYYY-MM-DD`. Defaults to the month-end of the latest platform transaction. |
| `materiality_threshold` | no | Aggregate rounding threshold in INR. Default `0.10`. |

Returns a `ReconciliationReport`: parameters, summary counts and totals, two variance
breakdowns (all-time and at the cutoff), and the detailed discrepancy list. All amounts
are JSON **strings** so that precision such as `100.105` is kept exactly.

If validation fails, the API returns `422` with `{"detail": {"message", "total_errors", "errors": [{dataset, row, column, value, message}]}}`.
Both files are validated before responding, so every problem is reported at once.

## Algorithm

| Step | Module | Rule |
|---|---|---|
| Load | `services/csv_loader.py` | Every cell is read as a string and amounts are parsed into `Decimal` (never float). Checks: required columns, missing values, ISO dates, plain decimal amounts, known enum values, INR only, sign matches type (PAYMENT > 0, REFUND < 0), bank amounts ≤ 2dp. A file with any error is rejected whole. |
| Period | `services/timing.py` | Platform rows with `transaction_date > cutoff` are excluded as `OUT_OF_PERIOD`, along with their settlements. |
| Duplicates | `services/duplicates.py` | Rows are grouped by `transaction_id` only (date and amount are never used). If the financial attributes are identical, the group is an `EXACT_DUPLICATE`: one row is matched and the extra rows count as an overstatement. If they differ, it is a `CONFLICTING_DUPLICATE`: the ID is left unmatched. Bank `settlement_id` reuse across different transactions is also reported. |
| Matching | `services/matching.py` | One-to-one inner join on `transaction_id` (`validate="one_to_one"`). Unmatched rows on either side become `MISSING_SETTLEMENT` or `UNMATCHED_SETTLEMENT`. |
| Timing | `services/timing.py` | `transaction_date ≤ cutoff < settlement_date` is a `LATE_SETTLEMENT` (timing difference). No settlement anywhere in the bank file is a `MISSING_SETTLEMENT`. |
| Amounts | `services/rounding.py` | `Δ = platform − bank`, computed exactly. If `Δ ≠ 0` and `round_half_even(platform, 2dp) == bank`, the row is a `SUB_PAISE_VARIANCE`; any other non-zero Δ is an `AMOUNT_MISMATCH`. The sub-paise Δs are summed without rounding. If the absolute sum is ≥ the threshold, an `AGGREGATE_ROUNDING_DIFFERENCE` is raised. |
| Refunds | `services/refunds.py` | The original payment must exist as a PAYMENT, otherwise `UNMATCHED_REFUND`. The refund must not be dated before the original, must not exceed it, and cumulative refunds must not exceed it, otherwise `INVALID_REFUND`. |
| Report | `services/reconciler.py` | Every row of both files falls into exactly one variance bucket. The buckets are summed and checked against the total variance (`variance_fully_explained`). |

### Reporting conventions

- **Matched** means a bank record exists for the transaction. Issue categories are tags
  that can overlap. For example, `TXN0171` is both matched and late, and `TXN0152` is
  both matched and an unmatched refund.
- **Total variance** = platform total − all bank settlements.
  **Variance at cutoff** = platform total − bank settlements dated on or before the cutoff.
- Platform totals include duplicate rows, because the overstated ledger is itself the finding.
- Refund originals are searched only in the uploaded platform file. A refund of a payment
  from an earlier period is described as "not found in the uploaded file".

## Result on the supplied dataset (cutoff 2026-10-31)

| Metric | Value |
|---|---|
| Platform / bank records | 172 / 171 |
| Matched / unmatched | 171 / 0 |
| Duplicate records | 1 (`TXN0085`, +₹1,250.00) |
| Late settlements | 1 (`TXN0171`, ₹4,750.00 settled 2026-11-02) |
| Unmatched refunds | 1 (`TXN0152` → nonexistent `TXN9999`) |
| Aggregate rounding | ₹0.120 across 24 transactions (₹0.00 if each amount is rounded first) |
| Platform / bank totals | ₹2,13,946.540 / ₹2,12,696.42 (₹2,07,946.42 by cutoff) |
| Total variance | ₹1,250.120 (duplicate + rounding) |
| Variance at cutoff | ₹6,000.120 (+ late settlement) |

`tests/test_ground_truth.py` checks that these findings match
`datasets/expected_discrepancies.csv` exactly. That file is read only by the tests,
never by the engine.
