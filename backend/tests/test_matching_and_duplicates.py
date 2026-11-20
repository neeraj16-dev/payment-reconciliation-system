"""Matching and duplicate detection (scenarios 1, 4, 5, 10)."""

from decimal import Decimal

from tests.conftest import bset, of_type, ptxn, run


# --- Scenario 1: normal matched transactions --------------------------------

def test_normal_matched_transactions_produce_no_discrepancies():
    report = run(
        [ptxn("TXN0001", "499.00"), ptxn("TXN0002", "1250.00")],
        [bset("TXN0001", "499.00"), bset("TXN0002", "1250.00")],
    )
    s = report.summary
    assert s.matched_transactions == 2
    assert s.unmatched_transactions == 0
    assert report.discrepancies == []
    assert s.total_variance == 0 and s.variance_at_cutoff == 0
    assert s.variance_fully_explained


def test_platform_only_and_bank_only_are_unmatched():
    report = run(
        [ptxn("TXN0001", "100.00"), ptxn("TXN0002", "200.00")],
        [bset("TXN0001", "100.00"), bset("TXN0003", "300.00")],
    )
    s = report.summary
    assert (s.matched_transactions, s.unmatched_platform_transactions, s.unmatched_bank_settlements) == (1, 1, 1)
    [missing] = of_type(report, "MISSING_SETTLEMENT")
    [orphan_bank] = of_type(report, "UNMATCHED_SETTLEMENT")
    assert missing.transaction_id == "TXN0002" and missing.bank_amount is None
    assert orphan_bank.transaction_id == "TXN0003"
    assert s.total_variance == Decimal("-100.00")
    assert s.variance_fully_explained


def test_amount_mismatch_is_not_reported_as_rounding():
    report = run([ptxn("TXN0001", "100.00")], [bset("TXN0001", "99.00")])
    [mismatch] = of_type(report, "AMOUNT_MISMATCH")
    assert mismatch.amount_difference == Decimal("1.00")
    assert not of_type(report, "SUB_PAISE_VARIANCE")


def test_type_mismatch_reported():
    report = run(
        [ptxn("TXN0001", "100.00"), ptxn("TXN0002", "-100.00", txn_type="REFUND", original="TXN0001")],
        [bset("TXN0001", "100.00"), bset("TXN0002", "100.00", txn_type="PAYMENT")],
    )
    assert [d.transaction_id for d in of_type(report, "TYPE_MISMATCH")] == ["TXN0002"]


# --- Scenario 4: duplicate platform entry -----------------------------------

def test_duplicate_platform_entry():
    report = run(
        [ptxn("TXN0085", "1250.00"), ptxn("TXN0085", "1250.00"), ptxn("TXN0086", "1250.00")],
        [bset("TXN0085", "1250.00"), bset("TXN0086", "1250.00")],
    )
    [dup] = of_type(report, "DUPLICATE_ENTRY")
    assert dup.transaction_id == "TXN0085"
    assert dup.source_dataset.value == "PLATFORM"
    assert dup.classification == "EXACT_DUPLICATE"
    assert dup.platform_amount == Decimal("2500.00")
    assert dup.bank_amount == Decimal("1250.00")
    assert dup.amount_difference == Decimal("1250.00")
    assert dup.platform_rows == [2, 3]
    # The duplicate does not create a second match.
    assert report.summary.matched_transactions == 2
    assert report.summary.duplicate_records == 1
    assert report.summary.total_variance == Decimal("1250.00")
    assert report.summary.variance_fully_explained


# --- Scenario 5: duplicate bank entry ---------------------------------------

def test_duplicate_bank_entry():
    report = run(
        [ptxn("TXN0001", "500.00")],
        [bset("TXN0001", "500.00", settlement_id="SET0001"),
         bset("TXN0001", "500.00", day="2026-10-12", settlement_id="SET0001B")],
    )
    [dup] = of_type(report, "DUPLICATE_ENTRY")
    assert dup.source_dataset.value == "BANK"
    assert dup.classification == "EXACT_DUPLICATE"
    assert dup.bank_amount == Decimal("1000.00")
    assert dup.amount_difference == Decimal("-500.00")
    assert dup.bank_rows == [2, 3]
    assert report.summary.matched_transactions == 1
    assert report.summary.total_variance == Decimal("-500.00")
    assert report.summary.variance_fully_explained


def test_conflicting_duplicate_is_not_matched():
    report = run(
        [ptxn("TXN0001", "500.00"), ptxn("TXN0001", "700.00")],
        [bset("TXN0001", "500.00")],
    )
    [dup] = of_type(report, "DUPLICATE_ENTRY")
    assert dup.classification == "CONFLICTING_DUPLICATE"
    s = report.summary
    assert s.matched_transactions == 0
    assert s.unresolved_duplicate_ids == 1
    assert dup.amount_difference == Decimal("700.00")
    assert s.variance_fully_explained


def test_settlement_id_reused_across_transactions():
    report = run(
        [ptxn("TXN0001", "10.00"), ptxn("TXN0002", "20.00")],
        [bset("TXN0001", "10.00", settlement_id="SETX"), bset("TXN0002", "20.00", settlement_id="SETX")],
    )
    [dup] = of_type(report, "DUPLICATE_ENTRY")
    assert dup.classification == "DUPLICATE_SETTLEMENT_ID"
    assert report.summary.matched_transactions == 2


# --- Scenario 10: identical amounts, different IDs --------------------------

def test_identical_amount_and_date_different_ids_not_flagged():
    report = run(
        [ptxn("TXN0046", "999.00", day="2026-10-08"), ptxn("TXN0047", "999.00", day="2026-10-08")],
        [bset("TXN0046", "999.00", day="2026-10-09"), bset("TXN0047", "999.00", day="2026-10-09")],
    )
    assert report.discrepancies == []
    assert report.summary.matched_transactions == 2
    assert report.summary.duplicate_records == 0


def test_dataset_same_amount_decoys_are_clean(dataset_report):
    flagged = {d.transaction_id for d in dataset_report.discrepancies}
    assert {"TXN0046", "TXN0047", "TXN0086"}.isdisjoint(flagged)
