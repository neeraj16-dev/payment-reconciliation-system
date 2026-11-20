"""Late settlement (2), aggregate rounding (3), refunds (6 & 9)."""

from datetime import date
from decimal import Decimal

from tests.conftest import bset, of_type, ptxn, run

# --- Scenario 2: late settlement --------------------------------------------


def test_late_settlement_is_timing_difference_not_missing():
    report = run(
        [ptxn("TXN0171", "4750.00", day="2026-10-31"), ptxn("TXN0001", "100.00")],
        [bset("TXN0171", "4750.00", day="2026-11-02"), bset("TXN0001", "100.00")],
    )
    [late] = of_type(report, "LATE_SETTLEMENT")
    assert late.transaction_id == "TXN0171"
    assert late.classification == "TIMING_DIFFERENCE"
    assert late.settlement_date == date(2026, 11, 2)
    assert late.amount_difference == Decimal("0.00")
    assert not of_type(report, "MISSING_SETTLEMENT")
    s = report.summary
    assert s.matched_transactions == 2 and s.late_settlements == 1
    assert s.total_variance == 0
    assert s.variance_at_cutoff == Decimal("4750.00")
    assert s.aggregate_bank_amount_at_cutoff == Decimal("100.00")
    assert s.variance_fully_explained


def test_settled_on_cutoff_day_is_not_late():
    report = run([ptxn("TXN0001", "10.00", day="2026-10-30")], [bset("TXN0001", "10.00", day="2026-10-31")])
    assert not of_type(report, "LATE_SETTLEMENT")


def test_cutoff_is_configurable():
    rows = ([ptxn("TXN0001", "10.00", day="2026-10-14")], [bset("TXN0001", "10.00", day="2026-10-16")])
    assert of_type(run(*rows, cutoff=date(2026, 10, 15)), "LATE_SETTLEMENT")
    assert not of_type(run(*rows, cutoff=date(2026, 10, 31)), "LATE_SETTLEMENT")


def test_never_settled_is_missing_not_late():
    report = run([ptxn("TXN0001", "10.00", day="2026-10-31"), ptxn("TXN0002", "5.00")],
                 [bset("TXN0002", "5.00")])
    assert of_type(report, "MISSING_SETTLEMENT") and not of_type(report, "LATE_SETTLEMENT")


def test_transactions_after_cutoff_are_out_of_period():
    report = run(
        [ptxn("TXN0001", "10.00"), ptxn("TXN0002", "20.00", day="2026-11-01")],
        [bset("TXN0001", "10.00"), bset("TXN0002", "20.00", day="2026-11-02")],
    )
    [oop] = of_type(report, "OUT_OF_PERIOD")
    assert oop.transaction_id == "TXN0002"
    s = report.summary
    assert s.total_platform_records == 1 and s.aggregate_platform_amount == Decimal("10.00")
    assert s.aggregate_bank_amount == Decimal("10.00")
    assert s.variance_fully_explained


def test_cutoff_derived_when_not_provided():
    from app.services.csv_loader import load_bank, load_platform
    from app.services.reconciler import reconcile
    from tests.conftest import BANK_HEADER, PLATFORM_HEADER, to_csv
    report = reconcile(load_platform(to_csv(PLATFORM_HEADER, [ptxn("TXN0001", "1.00", day="2026-10-07")])),
                       load_bank(to_csv(BANK_HEADER, [bset("TXN0001", "1.00")])))
    assert report.parameters.cutoff_date == date(2026, 10, 31)
    assert report.parameters.cutoff_source == "derived"


# --- Scenario 3: aggregate rounding difference ------------------------------

def _rounding_rows(n: int):
    platform, bank = [], []
    for k in range(n):
        amount = Decimal(f"{100 + k}.{10 + 2 * k:02d}5")  # even hundredths digit + 5
        platform.append(ptxn(f"TXN{k:04d}", str(amount)))
        bank.append(bset(f"TXN{k:04d}", str(amount.quantize(Decimal("0.01")))))
    return platform, bank


def test_aggregate_rounding_difference_detected():
    report = run(*_rounding_rows(24))
    sub_paise = of_type(report, "SUB_PAISE_VARIANCE")
    [aggregate] = of_type(report, "AGGREGATE_ROUNDING_DIFFERENCE")
    assert len(sub_paise) == 24
    assert all(d.amount_difference == Decimal("0.005") for d in sub_paise)
    assert aggregate.amount_difference == Decimal("0.120")
    assert len(aggregate.related_transaction_ids) == 24
    s = report.summary
    # Comparing individually rounded amounts hides the difference completely.
    assert s.individually_rounded_difference == 0
    assert s.aggregate_rounding_difference == Decimal("0.120")
    assert s.rounding_threshold_breached
    assert s.total_variance == Decimal("0.120")
    assert not of_type(report, "AMOUNT_MISMATCH")


def test_rounding_below_threshold_not_escalated():
    report = run(*_rounding_rows(10))  # 10 * 0.005 = 0.050 < 0.10
    assert len(of_type(report, "SUB_PAISE_VARIANCE")) == 10
    assert not of_type(report, "AGGREGATE_ROUNDING_DIFFERENCE")
    assert report.summary.aggregate_rounding_difference == Decimal("0.050")


def test_threshold_is_configurable():
    report = run(*_rounding_rows(10), materiality_threshold=Decimal("0.05"))
    assert of_type(report, "AGGREGATE_ROUNDING_DIFFERENCE")


def test_no_float_drift_in_aggregates():
    # 0.1 + 0.2 style amounts would drift with floats.
    rows = [ptxn(f"TXN{i:04d}", "0.10") for i in range(3)] + [ptxn("TXN0099", "0.20")]
    report = run(rows, [bset(r["transaction_id"], "0.10" if r["gross_amount"] == "0.10" else "0.20") for r in rows])
    assert report.summary.aggregate_platform_amount == Decimal("0.50")
    assert report.summary.total_variance == 0


# --- Scenario 6: unmatched refund -------------------------------------------

def test_refund_referencing_nonexistent_original():
    report = run(
        [ptxn("TXN0001", "850.00"), ptxn("TXN0152", "-850.00", txn_type="REFUND", original="TXN9999")],
        [bset("TXN0001", "850.00"), bset("TXN0152", "-850.00", txn_type="REFUND")],
    )
    [orphan] = of_type(report, "UNMATCHED_REFUND")
    assert orphan.transaction_id == "TXN0152"
    assert orphan.classification == "ORPHAN_REFUND"
    assert orphan.bank_amount == Decimal("-850.00")
    assert "TXN9999" in orphan.explanation
    # Still matched to its bank debit; this is a linkage failure, not a cash variance.
    assert report.summary.matched_transactions == 2
    assert report.summary.unmatched_refunds == 1
    assert report.summary.total_variance == 0


def test_refund_without_reference_or_referencing_a_refund():
    report = run(
        [ptxn("TXN0001", "100.00"),
         ptxn("TXN0002", "-50.00", txn_type="REFUND", original="TXN0001"),
         ptxn("TXN0003", "-10.00", txn_type="REFUND", original=""),
         ptxn("TXN0004", "-10.00", txn_type="REFUND", original="TXN0002")],
        [bset("TXN0001", "100.00")],
    )
    by_id = {d.transaction_id: d.classification for d in of_type(report, "UNMATCHED_REFUND")}
    assert by_id == {"TXN0003": "MISSING_REFERENCE", "TXN0004": "INVALID_REFERENCE"}


def test_invalid_refunds_date_amount_and_cumulative():
    report = run(
        [ptxn("TXN0001", "100.00", day="2026-10-10"),
         ptxn("TXN0002", "-10.00", day="2026-10-05", txn_type="REFUND", original="TXN0001"),
         ptxn("TXN0003", "-150.00", day="2026-10-12", txn_type="REFUND", original="TXN0001"),
         ptxn("TXN0004", "200.00", day="2026-10-10"),
         ptxn("TXN0005", "-120.00", day="2026-10-11", txn_type="REFUND", original="TXN0004"),
         ptxn("TXN0006", "-100.00", day="2026-10-12", txn_type="REFUND", original="TXN0004")],
        [bset("TXN0001", "100.00")],
    )
    invalid = {d.transaction_id: d.explanation for d in of_type(report, "INVALID_REFUND")}
    assert set(invalid) == {"TXN0002", "TXN0003", "TXN0006"}
    assert "before the original" in invalid["TXN0002"]
    assert "exceeds the original" in invalid["TXN0003"]
    assert "cumulative" in invalid["TXN0006"]


# --- Scenario 9: legitimate refunds -----------------------------------------

def test_legitimate_full_and_partial_refunds_not_flagged():
    report = run(
        [ptxn("TXN0005", "249.00", day="2026-10-01"),
         ptxn("TXN0030", "-249.00", day="2026-10-05", txn_type="REFUND", original="TXN0005"),
         ptxn("TXN0010", "1000.00", day="2026-10-01"),
         ptxn("TXN0011", "-400.00", day="2026-10-01", txn_type="REFUND", original="TXN0010"),
         ptxn("TXN0012", "-600.00", day="2026-10-03", txn_type="REFUND", original="TXN0010")],
        [bset("TXN0005", "249.00", day="2026-10-02"),
         bset("TXN0030", "-249.00", day="2026-10-06", txn_type="REFUND"),
         bset("TXN0010", "1000.00", day="2026-10-02"),
         bset("TXN0011", "-400.00", day="2026-10-02", txn_type="REFUND"),
         bset("TXN0012", "-600.00", day="2026-10-04", txn_type="REFUND")],
    )
    assert report.discrepancies == []
    assert report.summary.aggregate_platform_amount == Decimal("0.00")


def test_dataset_legitimate_refunds_not_flagged(dataset_report, platform_bytes):
    from app.services.csv_loader import load_platform
    platform = load_platform(platform_bytes)
    refund_ids = set(platform.loc[platform["transaction_type"] == "REFUND", "transaction_id"])
    flagged = {d.transaction_id for d in dataset_report.discrepancies
               if d.issue_type.value in ("UNMATCHED_REFUND", "INVALID_REFUND")}
    assert len(refund_ids) == 11
    assert flagged == {"TXN0152"}
