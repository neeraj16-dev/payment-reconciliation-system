# Payment Reconciliation Synthetic Dataset — Financial Assumptions & Design Specification

## 1. Purpose & Reconciliation Scope

These synthetic datasets validate an automated month-end payment reconciliation engine for an Indian payments company operating in **INR**. The reporting period covers platform transaction activity from **2026-10-01 through 2026-10-31**, reconciled against bank settlement records spanning **2026-10-02 through 2026-11-02** (incorporating a standard $T+1$ to $T+2$ calendar-day settlement window).

---

## 2. Core Financial & Accounting Assumptions

### 2.1 Reconciliation Date Basis (Transaction Date vs. Settlement Date)
* **Primary Population Scope (`transaction_date`):** Month-end revenue and ledger completeness are anchored on the platform's **`transaction_date`** (`2026-10-01` to `2026-10-31`), reflecting accrual accounting principles where customer payments are recognized upon capture.
* **Cash Matching Basis (`settlement_date`):** Bank clearing is evaluated against **`settlement_date`**. To distinguish true missing settlements from normal clearing lags, the reconciliation engine must ingest a **subsequent-period lookahead window** (at least $T+2$ days into November 2026, i.e., through `2026-11-02`).

### 2.2 Classification of Next-Month Settlements (Timing Differences)
* Transactions captured in October 2026 (`transaction_date <= 2026-10-31`) whose corresponding bank settlement occurs in November 2026 (`settlement_date >= 2026-11-01`) are classified as **`LATE_SETTLEMENT` (`TIMING_DIFFERENCE`)**, **not** permanently missing settlements.
* On the October 31 balance sheet, these represent **Cash in Transit / Settlement Receivable**.
* In this dataset, **exactly one** transaction (`TXN0171`, `2026-10-31`, INR `4,750.00`) settles in November (`SET0171`, `2026-11-02`). All other 170 unique transactions settle on or before `2026-10-31`.

### 2.3 Rounding Difference Calculation & Precision Model
* **Platform Precision:** Certain platform transactions retain **3 decimal places** (sub-paise precision, e.g., `100.105` INR), which commonly occurs in production systems due to tax/GST splits, promotional percentage discounts, or multi-currency conversions.
* **Bank Precision:** The settlement bank clears funds in standard 2-decimal INR (paise) using **Banker's Rounding (`ROUND_HALF_EVEN`)** (equivalent here to 2-decimal truncation because all 24 planted amounts have an even hundredths digit followed by `5`).
* **Calculation Rule:** All monetary arithmetic is performed strictly using exact `decimal.Decimal` representation—never IEEE-754 binary floating-point.
  * Individual variance: $\Delta_i = \text{gross\_amount}_i - \text{settlement\_amount}_i = 0.005\text{ INR}$.
  * Display-rounded comparison: $\text{quantize}(\text{gross\_amount}_i, 0.01, \text{ROUND\_HALF\_EVEN}) - \text{settlement\_amount}_i = 0.00\text{ INR}$ (individually invisible at 2 decimal places).
  * Aggregate variance: $\sum_{i=1}^{24} \Delta_i = 24 \times 0.005 = 0.120\text{ INR}$ (`INR 0.12`), breaching the `INR 0.10` materiality threshold.

### 2.4 Duplicate Record Detection
* **Primary Key Rule:** `transaction_id` must be unique within `platform_transactions.csv`, and both `settlement_id` and `transaction_id` must be unique within `bank_settlements.csv`.
* **Detection Logic:** Duplicates are detected by grouping on `transaction_id` (and verifying identical financial attributes) rather than heuristic matching on `(transaction_date, gross_amount)`.
* **False-Positive Guardrails:** The dataset intentionally contains legitimate distinct transactions sharing the exact same date and amount:
  * `TXN0046` and `TXN0047` (both `2026-10-08`, INR `999.00`) — both legitimately settled (`SET0046`, `SET0047`).
  * `TXN0085` (duplicated in platform) and `TXN0086` (legitimate single record) — both `2026-10-15`, INR `1,250.00`. A correct engine flags only `TXN0085` as a duplicate and leaves `TXN0086` clean.

### 2.5 Refund Linkage & Signed Amount Convention
* **Signed Ledger Amounts:** `PAYMENT` records carry positive amounts (`> 0`); `REFUND` records carry negative amounts (`< 0`) in both `platform_transactions.csv` and `bank_settlements.csv`. This allows direct net summation across ledgers without conditional sign flipping.
* **Referential Integrity:** Every `REFUND` must populate `original_transaction_id` pointing to an existing `PAYMENT` transaction in `platform_transactions.csv` such that:
  1. `original_transaction_id` exists as a `PAYMENT` record.
  2. `refund.transaction_date >= original.transaction_date`.
  3. $|\text{refund.gross\_amount}| \le \text{original.gross\_amount}$.
* **Unmatched (Orphan) Refund:** `TXN0152` (`2026-10-26`, INR `-850.00`) references `original_transaction_id = TXN9999`, which does not exist in `platform_transactions.csv`. It does have a matching bank debit (`SET0152`, `2026-10-27`, INR `-850.00`) so that it isolates the referential-integrity failure without introducing an unintended missing-settlement anomaly.

### 2.6 Gross Payment Amounts vs. Net Settlement Amounts
* Both `platform_transactions.csv` (`gross_amount`) and `bank_settlements.csv` (`settlement_amount`) represent **gross transaction values** (100% pass-through principal without Merchant Discount Rate (MDR), payment gateway fees, interchange, or GST deductions).
* Under this gross-settlement assumption (typical of monthly-invoiced fee models rather than net-deducted settlement models), every clean transaction reconciles $1:1$ (`gross_amount == settlement_amount`).

---

## 3. Dataset Schemas

### 3.1 `platform_transactions.csv` (172 rows)
| Column | Type | Description |
|---|---|---|
| `transaction_id` | String | Platform transaction ID (`TXN0001`–`TXN0171`; `TXN0085` duplicated once) |
| `transaction_date` | ISO Date | Capture date (`YYYY-MM-DD`, October 2026) |
| `transaction_type` | Enum | `PAYMENT` or `REFUND` |
| `status` | Enum | `SUCCESS` |
| `currency` | String | `INR` |
| `gross_amount` | Decimal | Signed gross amount (2dp standard; 3dp for rounding cohort) |
| `payment_method` | Enum | `UPI`, `CARD`, `NETBANKING`, `WALLET` |
| `merchant_id` | String | Merchant identifier (`MCH001`–`MCH005`) |
| `customer_id` | String | Customer identifier (`CUST1001`–`CUST1080`) |
| `original_transaction_id` | String | Parent `PAYMENT` ID for refunds; empty for payments |

### 3.2 `bank_settlements.csv` (171 rows)
| Column | Type | Description |
|---|---|---|
| `settlement_id` | String | Unique bank settlement ID (`SET0001`–`SET0171`) |
| `transaction_id` | String | Corresponding platform transaction ID (`TXN0001`–`TXN0171`) |
| `settlement_date` | ISO Date | Bank settlement date (`2026-10-02` to `2026-11-02`) |
| `transaction_type` | Enum | `PAYMENT` or `REFUND` |
| `status` | Enum | `SETTLED` |
| `currency` | String | `INR` |
| `settlement_amount` | Decimal | Signed 2-decimal settled amount in INR |
| `bank_reference` | String | Unique bank UTR reference (`UTRYYYYMMDDNNNNN`) |

### 3.3 `expected_discrepancies.csv` (27 rows / 4 anomaly groups)
Provides programmatic ground truth mapping each affected `transaction_id` and `settlement_id` to its `discrepancy_group`, `discrepancy_type`, `classification`, exact `Decimal` amounts, `amount_difference`, and `expected_resolution`.

---

## 4. Planted Anomalies Summary

| Group ID | Discrepancy Type | Count | Affected IDs | Financial Impact (INR) |
|---|---|---|---|---|
| `LATE_001` | `LATE_SETTLEMENT` | 1 | `TXN0171` / `SET0171` | `4,750.00` timing difference at Oct 31 cutoff (`0.00` all-time) |
| `ROUNDING_AGG_001` | `AGGREGATE_ROUNDING_DIFFERENCE` | 24 | `TXN0009`, `TXN0015`, ..., `TXN0147` (step 6) | `+0.005` each; **`+0.120` aggregate** |
| `DUP_001` | `DUPLICATE_ENTRY` | 1 | `TXN0085` (2 platform rows, 1 bank row `SET0085`) | **`+1,250.00`** overstated platform ledger |
| `ORPHAN_REF_001` | `UNMATCHED_REFUND` | 1 | `TXN0152` (`original_transaction_id = TXN9999`) | `-850.00` audit exposure (`0.00` bank cash variance) |

---

## 5. Limitations of Synthetic Data

1. **No Gateway Fees / MDR / GST Deductions:** Real bank settlement files frequently settle *net* of MDR and 18% GST on MDR, requiring a three-way reconciliation (`Gross - Fee - Tax = Net Bank Credit`).
2. **Single-Record Settlement Mapping:** Production banks often bundle hundreds of UPI/card transactions into a single lump-sum NEFT/RTGS payout batch (many-to-one matching) rather than 1-to-1 settlement rows.
3. **No Failed, Pending, Chargeback, or Reversal States:** All transactions are `SUCCESS`/`SETTLED` to isolate the four requested reconciliation problems without introducing extraneous state noise.
4. **No Cross-Month Legitimate Refunds:** In production, an October refund could legitimately reference a September payment that lies outside an October-only extract; production reconciliation engines must query historical payment archives before classifying a refund as permanently orphaned.
5. **Calendar Days vs. Banking Business Days:** Settlement lags use $T+1$ and $T+2$ calendar days rather than RBI banking holiday/NEFT clearing calendars.