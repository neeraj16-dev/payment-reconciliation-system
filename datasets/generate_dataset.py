"""
Synthetic Payment Reconciliation Dataset Generator & Validator
==============================================================
Generates reproducible, financially exact synthetic datasets for testing a
month-end payment reconciliation system (October 2026 activity with settlements
extending into November 2026).

Outputs:
    - platform_transactions.csv (172 rows: 171 unique TXNs + 1 intentional duplicate)
    - bank_settlements.csv      (171 rows: 171 unique settlements)
    - expected_discrepancies.csv (27 rows covering exactly 4 planted anomaly types)

All financial calculations use decimal.Decimal (never binary floating-point).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
import random
from typing import Dict, List, Tuple

import pandas as pd

# Fixed seed for deterministic, cross-platform reproducibility
SEED = 42
random.seed(SEED)

# Deterministic lookup palettes with pairwise coprime lengths (13, 5, 19, 80)
PAYMENT_METHODS: List[str] = [
    "UPI", "CARD", "UPI", "NETBANKING", "UPI", "WALLET",
    "CARD", "UPI", "CARD", "UPI", "NETBANKING", "UPI", "WALLET",
]

MERCHANT_IDS: List[str] = ["MCH001", "MCH002", "MCH003", "MCH004", "MCH005"]

AMOUNT_PALETTE: List[Decimal] = [
    Decimal("249.00"), Decimal("499.00"), Decimal("799.00"), Decimal("1250.00"),
    Decimal("1499.00"), Decimal("350.50"), Decimal("2199.00"), Decimal("625.25"),
    Decimal("3450.00"), Decimal("899.00"), Decimal("1750.50"), Decimal("420.00"),
    Decimal("5999.00"), Decimal("1120.75"), Decimal("649.00"), Decimal("2850.00"),
    Decimal("999.00"), Decimal("4100.00"), Decimal("1580.25"),
]

# Anomaly configuration constants
TOTAL_UNIQUE_TRANSACTIONS = 171
ROUNDING_INDICES: List[int] = list(range(9, 148, 6))  # 24 transactions (Days 2..25)
LEGIT_REFUND_MAP: Dict[int, int] = {
    30: 5,
    42: 14,
    54: 26,
    66: 38,
    78: 52,
    96: 68,
    108: 80,
    120: 92,
    138: 110,
    156: 134,
}
DUPLICATE_TXN_IDX = 85
SAME_AMOUNT_PAIR_INDICES = {46, 47}
DUPLICATE_TWIN_LEGIT_IDX = 86
ORPHAN_REFUND_IDX = 152
ORPHAN_ORIGINAL_TXN_ID = "TXN9999"
LATE_SETTLEMENT_IDX = 171


def get_transaction_date(idx: int) -> date:
    """Return monotonically non-decreasing October 2026 transaction dates."""
    if 1 <= idx <= 150:
        day = (idx - 1) // 6 + 1
    elif 151 <= idx <= 170:
        day = 26 + (idx - 151) // 4
    elif idx == 171:
        day = 31
    else:
        raise ValueError(f"Index out of bounds: {idx}")
    return date(2026, 10, day)


def get_settlement_lag_days(idx: int) -> int:
    """
    Return T+1 or T+2 settlement lag.
    Ensures every transaction except TXN0171 settles on or before 2026-10-31.
    """
    if idx == LATE_SETTLEMENT_IDX:
        return 2  # 2026-10-31 + 2 days = 2026-11-02
    if 167 <= idx <= 170:
        return 1  # 2026-10-30 + 1 day = 2026-10-31
    return 1 if (idx % 2 == 0) else 2


def base_attributes(idx: int) -> Tuple[Decimal, str, str, str]:
    """Deterministic seeded attributes for standard payment records."""
    amount = AMOUNT_PALETTE[(idx * 3 + SEED) % len(AMOUNT_PALETTE)]
    payment_method = PAYMENT_METHODS[(idx + SEED) % len(PAYMENT_METHODS)]
    merchant_id = MERCHANT_IDS[(idx * 2 + SEED) % len(MERCHANT_IDS)]
    customer_id = f"CUST{1001 + ((idx * 7 + SEED) % 80):04d}"
    return amount, payment_method, merchant_id, customer_id


def build_datasets() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build platform_transactions, bank_settlements, and expected_discrepancies DataFrames."""
    platform_rows: List[Dict[str, str]] = []
    bank_rows: List[Dict[str, str]] = []
    discrepancy_rows: List[Dict[str, str]] = []

    rounding_pos_map: Dict[int, int] = {
        idx: pos for pos, idx in enumerate(ROUNDING_INDICES)
    }
    generated_payments: Dict[int, Dict[str, str]] = {}
    disc_counter = 1

    for idx in range(1, TOTAL_UNIQUE_TRANSACTIONS + 1):
        txn_id = f"TXN{idx:04d}"
        set_id = f"SET{idx:04d}"
        txn_date = get_transaction_date(idx)
        set_date = txn_date + timedelta(days=get_settlement_lag_days(idx))
        utr = f"UTR{set_date.strftime('%Y%m%d')}{idx:05d}"

        gross_amount, payment_method, merchant_id, customer_id = base_attributes(idx)
        txn_type = "PAYMENT"
        orig_txn_id = ""
        settlement_amount = gross_amount

        # Apply intentional cohort logic
        if idx in SAME_AMOUNT_PAIR_INDICES:
            gross_amount = Decimal("999.00")
            settlement_amount = gross_amount

        elif idx == DUPLICATE_TXN_IDX:
            gross_amount = Decimal("1250.00")
            settlement_amount = gross_amount
            payment_method = "UPI"
            merchant_id = "MCH002"
            customer_id = "CUST1025"

        elif idx == DUPLICATE_TWIN_LEGIT_IDX:
            gross_amount = Decimal("1250.00")
            settlement_amount = gross_amount

        elif idx in rounding_pos_map:
            k = rounding_pos_map[idx]
            rupees = 100 + k * 45
            even_paise = 10 + k * 2  # Always even hundredths -> ROUND_HALF_EVEN rounds down
            gross_amount = Decimal(f"{rupees}.{even_paise:02d}5")
            settlement_amount = gross_amount.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            )

            discrepancy_rows.append(
                {
                    "discrepancy_id": f"DISC{disc_counter:03d}",
                    "discrepancy_group": "ROUNDING_AGG_001",
                    "discrepancy_type": "AGGREGATE_ROUNDING_DIFFERENCE",
                    "classification": "ROUNDING_VARIANCE",
                    "source_dataset": "BOTH",
                    "transaction_id": txn_id,
                    "settlement_id": set_id,
                    "transaction_date": txn_date.isoformat(),
                    "settlement_date": set_date.isoformat(),
                    "platform_amount": f"{gross_amount:.3f}",
                    "bank_amount": f"{settlement_amount:.2f}",
                    "amount_difference": f"{(gross_amount - settlement_amount):.3f}",
                    "expected_resolution": (
                        "Sub-paise rounding variance (0.005 INR); identical when rounded "
                        "via ROUND_HALF_EVEN, but aggregates to 0.120 INR across 24 transactions."
                    ),
                }
            )
            disc_counter += 1

        elif idx in LEGIT_REFUND_MAP:
            orig_idx = LEGIT_REFUND_MAP[idx]
            orig_rec = generated_payments[orig_idx]
            txn_type = "REFUND"
            gross_amount = -Decimal(orig_rec["gross_amount"])
            settlement_amount = gross_amount
            payment_method = orig_rec["payment_method"]
            merchant_id = orig_rec["merchant_id"]
            customer_id = orig_rec["customer_id"]
            orig_txn_id = orig_rec["transaction_id"]

        elif idx == ORPHAN_REFUND_IDX:
            txn_type = "REFUND"
            gross_amount = Decimal("-850.00")
            settlement_amount = gross_amount
            payment_method = "CARD"
            merchant_id = "MCH003"
            customer_id = "CUST1045"
            orig_txn_id = ORPHAN_ORIGINAL_TXN_ID

            discrepancy_rows.append(
                {
                    "discrepancy_id": f"DISC{disc_counter:03d}",
                    "discrepancy_group": "ORPHAN_REF_001",
                    "discrepancy_type": "UNMATCHED_REFUND",
                    "classification": "ORPHAN_REFUND",
                    "source_dataset": "PLATFORM",
                    "transaction_id": txn_id,
                    "settlement_id": set_id,
                    "transaction_date": txn_date.isoformat(),
                    "settlement_date": set_date.isoformat(),
                    "platform_amount": f"{gross_amount:.2f}",
                    "bank_amount": f"{settlement_amount:.2f}",
                    "amount_difference": "0.00",
                    "expected_resolution": (
                        f"Refund references nonexistent original_transaction_id "
                        f"{ORPHAN_ORIGINAL_TXN_ID}; escalate for manual refund audit."
                    ),
                }
            )
            disc_counter += 1

        elif idx == LATE_SETTLEMENT_IDX:
            gross_amount = Decimal("4750.00")
            settlement_amount = gross_amount
            payment_method = "NETBANKING"
            merchant_id = "MCH001"
            customer_id = "CUST1071"

            discrepancy_rows.append(
                {
                    "discrepancy_id": f"DISC{disc_counter:03d}",
                    "discrepancy_group": "LATE_001",
                    "discrepancy_type": "LATE_SETTLEMENT",
                    "classification": "TIMING_DIFFERENCE",
                    "source_dataset": "BOTH",
                    "transaction_id": txn_id,
                    "settlement_id": set_id,
                    "transaction_date": txn_date.isoformat(),
                    "settlement_date": set_date.isoformat(),
                    "platform_amount": f"{gross_amount:.2f}",
                    "bank_amount": f"{settlement_amount:.2f}",
                    "amount_difference": "0.00",
                    "expected_resolution": (
                        "Month-end cutoff timing difference (in-transit at 2026-10-31); "
                        "settled legitimately on 2026-11-02."
                    ),
                }
            )
            disc_counter += 1

        amount_str = f"{gross_amount:.3f}" if idx in rounding_pos_map else f"{gross_amount:.2f}"
        platform_record = {
            "transaction_id": txn_id,
            "transaction_date": txn_date.isoformat(),
            "transaction_type": txn_type,
            "status": "SUCCESS",
            "currency": "INR",
            "gross_amount": amount_str,
            "payment_method": payment_method,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "original_transaction_id": orig_txn_id,
        }
        platform_rows.append(platform_record)

        if txn_type == "PAYMENT":
            generated_payments[idx] = platform_record

        # Inject exactly one intentional duplicate row in platform_transactions
        if idx == DUPLICATE_TXN_IDX:
            platform_rows.append(dict(platform_record))
            discrepancy_rows.append(
                {
                    "discrepancy_id": f"DISC{disc_counter:03d}",
                    "discrepancy_group": "DUP_001",
                    "discrepancy_type": "DUPLICATE_ENTRY",
                    "classification": "DATA_INTEGRITY_DUPLICATE",
                    "source_dataset": "PLATFORM",
                    "transaction_id": txn_id,
                    "settlement_id": set_id,
                    "transaction_date": txn_date.isoformat(),
                    "settlement_date": set_date.isoformat(),
                    "platform_amount": f"{(gross_amount * 2):.2f}",
                    "bank_amount": f"{settlement_amount:.2f}",
                    "amount_difference": f"{gross_amount:.2f}",
                    "expected_resolution": (
                        "Exact duplicate transaction_id in platform_transactions.csv; "
                        "bank settled once. Remove duplicate platform ledger entry."
                    ),
                }
            )
            disc_counter += 1

        bank_rows.append(
            {
                "settlement_id": set_id,
                "transaction_id": txn_id,
                "settlement_date": set_date.isoformat(),
                "transaction_type": txn_type,
                "status": "SETTLED",
                "currency": "INR",
                "settlement_amount": f"{settlement_amount:.2f}",
                "bank_reference": utr,
            }
        )

    platform_df = pd.DataFrame(platform_rows)
    bank_df = pd.DataFrame(bank_rows)
    discrepancy_df = pd.DataFrame(discrepancy_rows)
    return platform_df, bank_df, discrepancy_df


def validate_datasets(
    platform_df: pd.DataFrame,
    bank_df: pd.DataFrame,
    discrepancy_df: pd.DataFrame,
) -> None:
    """
    Execute strict financial & structural assertions confirming all 6 validation criteria.
    Uses Decimal exclusively for monetary checks.
    """
    # Check 0: Basic volume and schema integrity
    assert 150 <= len(platform_df) <= 200, f"Unexpected platform row count: {len(platform_df)}"
    assert 150 <= len(bank_df) <= 200, f"Unexpected bank row count: {len(bank_df)}"
    assert bank_df["settlement_id"].is_unique, "Bank settlement_ids must be unique"
    assert bank_df["transaction_id"].is_unique, "Bank transaction_ids must be unique"
    assert (platform_df["currency"] == "INR").all(), "All platform records must be INR"
    assert (bank_df["currency"] == "INR").all(), "All bank records must be INR"

    # Check 3: Exactly one intentional duplicate entry exists (in ONE dataset)
    platform_counts = platform_df["transaction_id"].value_counts()
    dup_ids = platform_counts[platform_counts > 1].index.tolist()
    assert len(dup_ids) == 1, f"Expected exactly 1 duplicate transaction_id, found {dup_ids}"
    dup_id = dup_ids[0]
    assert platform_counts[dup_id] == 2, f"Expected duplicate count=2 for {dup_id}"
    dup_rows = platform_df[platform_df["transaction_id"] == dup_id]
    assert dup_rows.iloc[0].equals(dup_rows.iloc[1]), "Duplicate rows must be identical"
    assert (bank_df["transaction_id"] == dup_id).sum() == 1, "Bank must have 1 legitimate record"

    # Deduplicate platform for 1-to-1 settlement alignment checks
    platform_unique = platform_df.drop_duplicates(subset=["transaction_id"], keep="first")
    merged = platform_unique.merge(
        bank_df,
        on="transaction_id",
        how="outer",
        suffixes=("_platform", "_bank"),
        indicator=True,
    )
    assert (merged["_merge"] == "both").all(), "Every unique transaction must have a bank settlement"

    # Check 1: Exactly one intentional late-settlement scenario exists (Oct txn -> Nov settlement)
    late_mask = (
        merged["transaction_date"].str.startswith("2026-10")
        & merged["settlement_date"].str.startswith("2026-11")
    )
    late_rows = merged[late_mask]
    assert len(late_rows) == 1, f"Expected exactly 1 late settlement, found {len(late_rows)}"
    assert late_rows.iloc[0]["transaction_date"] == "2026-10-31", "Late txn must occur on Oct 31"
    assert late_rows.iloc[0]["transaction_type_platform"] == "PAYMENT", "Late txn must be PAYMENT"
    assert Decimal(late_rows.iloc[0]["gross_amount"]) == Decimal(late_rows.iloc[0]["settlement_amount"])

    # Check 2: Aggregate rounding discrepancy >= INR 0.10, individually identical to 2dp (ROUND_HALF_EVEN)
    rounding_txns: List[str] = []
    aggregate_rounding_diff = Decimal("0.000")
    for _, row in merged.iterrows():
        p_amt = Decimal(row["gross_amount"])
        b_amt = Decimal(row["settlement_amount"])
        diff = p_amt - b_amt
        if diff != Decimal("0"):
            rounded_p = p_amt.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            assert rounded_p == b_amt, (
                f"Rounding txn {row['transaction_id']} differs when rounded to 2dp: "
                f"{rounded_p} vs {b_amt}"
            )
            rounding_txns.append(row["transaction_id"])
            aggregate_rounding_diff += diff

    assert len(rounding_txns) == 24, f"Expected 24 rounding txns, found {len(rounding_txns)}"
    assert aggregate_rounding_diff >= Decimal("0.10"), (
        f"Aggregate rounding diff {aggregate_rounding_diff} is below INR 0.10"
    )
    assert aggregate_rounding_diff == Decimal("0.120"), (
        f"Expected exact aggregate rounding diff 0.120, got {aggregate_rounding_diff}"
    )

    # Check 4: At least one refund references a nonexistent original transaction
    refunds = platform_unique[platform_unique["transaction_type"] == "REFUND"]
    all_payment_ids = set(
        platform_unique[platform_unique["transaction_type"] == "PAYMENT"]["transaction_id"]
    )
    orphan_refunds = refunds[~refunds["original_transaction_id"].isin(all_payment_ids)]
    assert len(orphan_refunds) == 1, f"Expected 1 orphan refund, found {len(orphan_refunds)}"

    legit_refunds = refunds[refunds["original_transaction_id"].isin(all_payment_ids)]
    assert len(legit_refunds) == 10, f"Expected 10 legitimate refunds, found {len(legit_refunds)}"
    payment_lookup = platform_unique.set_index("transaction_id")
    for _, ref_row in legit_refunds.iterrows():
        orig = payment_lookup.loc[ref_row["original_transaction_id"]]
        assert ref_row["transaction_date"] >= orig["transaction_date"], "Refund precedes original payment"
        assert abs(Decimal(ref_row["gross_amount"])) <= Decimal(orig["gross_amount"])

    # Check 5: All other ordinary transactions have exact matching legitimate settlements in Oct 2026
    anomalous_ids = (
        set(late_rows["transaction_id"])
        | set(rounding_txns)
        | {dup_id}
        | set(orphan_refunds["transaction_id"])
    )
    ordinary = merged[~merged["transaction_id"].isin(anomalous_ids)]
    assert len(ordinary) == 144, f"Expected 144 ordinary reconciled records, found {len(ordinary)}"
    for _, row in ordinary.iterrows():
        assert Decimal(row["gross_amount"]) == Decimal(row["settlement_amount"]), (
            f"Ordinary txn {row['transaction_id']} amount mismatch"
        )
        t_date = date.fromisoformat(row["transaction_date"])
        s_date = date.fromisoformat(row["settlement_date"])
        lag = (s_date - t_date).days
        assert 1 <= lag <= 2, f"Ordinary txn {row['transaction_id']} invalid lag: {lag}"
        assert row["settlement_date"].startswith("2026-10"), (
            f"Ordinary txn {row['transaction_id']} settled outside October 2026"
        )

    # Check 6: Expected discrepancy manifest matches all planted anomalies
    expected_types = {
        "LATE_SETTLEMENT",
        "AGGREGATE_ROUNDING_DIFFERENCE",
        "DUPLICATE_ENTRY",
        "UNMATCHED_REFUND",
    }
    assert set(discrepancy_df["discrepancy_type"].unique()) == expected_types
    assert set(
        discrepancy_df[discrepancy_df["discrepancy_type"] == "LATE_SETTLEMENT"]["transaction_id"]
    ) == set(late_rows["transaction_id"])
    assert set(
        discrepancy_df[
            discrepancy_df["discrepancy_type"] == "AGGREGATE_ROUNDING_DIFFERENCE"
        ]["transaction_id"]
    ) == set(rounding_txns)
    assert set(
        discrepancy_df[discrepancy_df["discrepancy_type"] == "DUPLICATE_ENTRY"]["transaction_id"]
    ) == {dup_id}
    assert set(
        discrepancy_df[discrepancy_df["discrepancy_type"] == "UNMATCHED_REFUND"]["transaction_id"]
    ) == set(orphan_refunds["transaction_id"])

    manifest_rounding_sum = sum(
        (
            Decimal(x)
            for x in discrepancy_df[
                discrepancy_df["discrepancy_type"] == "AGGREGATE_ROUNDING_DIFFERENCE"
            ]["amount_difference"]
        ),
        Decimal("0.000"),
    )
    assert manifest_rounding_sum == aggregate_rounding_diff

    # Summary print using exact Decimal sums
    total_platform_raw = sum((Decimal(x) for x in platform_df["gross_amount"]), Decimal("0.000"))
    total_bank_all = sum((Decimal(x) for x in bank_df["settlement_amount"]), Decimal("0.00"))
    total_bank_oct = sum(
        (
            Decimal(row["settlement_amount"])
            for _, row in bank_df.iterrows()
            if row["settlement_date"].startswith("2026-10")
        ),
        Decimal("0.00"),
    )
    raw_variance = total_platform_raw - total_bank_all
    oct_cutoff_variance = total_platform_raw - total_bank_oct

    print("ALL 6 VALIDATION CHECKS PASSED SUCCESSFULLY!")
    print(f"  Platform rows (raw)            : {len(platform_df)}")
    print(f"  Bank settlement rows (all)     : {len(bank_df)}")
    print(f"  Expected discrepancy manifest  : {len(discrepancy_df)} rows (4 anomaly groups)")
    print(f"  Platform Total (raw)           : INR {total_platform_raw:.3f}")
    print(f"  Bank Total (all incl. Nov)     : INR {total_bank_all:.2f}")
    print(f"  Bank Total (Oct 31 cutoff)     : INR {total_bank_oct:.2f}")
    print(f"  Variance (all-time)            : INR {raw_variance:.3f} (Dup 1250.00 + Rounding 0.120)")
    print(
        f"  Variance (Oct 31 cutoff)       : INR {oct_cutoff_variance:.3f} "
        f"(Dup 1250.00 + Rounding 0.120 + Late 4750.00)"
    )


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    platform_df, bank_df, discrepancy_df = build_datasets()

    validate_datasets(platform_df, bank_df, discrepancy_df)

    platform_df.to_csv(out_dir / "platform_transactions.csv", index=False)
    bank_df.to_csv(out_dir / "bank_settlements.csv", index=False)
    discrepancy_df.to_csv(out_dir / "expected_discrepancies.csv", index=False)
    print(f"Wrote CSV datasets to: {out_dir}")


if __name__ == "__main__":
    main()