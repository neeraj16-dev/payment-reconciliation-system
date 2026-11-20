"""End-to-end check against datasets/expected_discrepancies.csv.

The ground-truth file is read ONLY here. The engine never sees it.
"""

import csv
from decimal import Decimal

import pytest

from tests.conftest import DATASETS_DIR

# Ground truth lists each rounding contributor as AGGREGATE_ROUNDING_DIFFERENCE; the
# engine reports them as SUB_PAISE_VARIANCE rows plus one aggregate finding.
TYPE_MAP = {
    "LATE_SETTLEMENT": "LATE_SETTLEMENT",
    "DUPLICATE_ENTRY": "DUPLICATE_ENTRY",
    "UNMATCHED_REFUND": "UNMATCHED_REFUND",
    "AGGREGATE_ROUNDING_DIFFERENCE": "SUB_PAISE_VARIANCE",
}


@pytest.fixture(scope="module")
def expected():
    with open(DATASETS_DIR / "expected_discrepancies.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def test_flagged_transactions_match_ground_truth_exactly(dataset_report, expected):
    expected_pairs = {(TYPE_MAP[r["discrepancy_type"]], r["transaction_id"]) for r in expected}
    actual_pairs = {(d.issue_type.value, d.transaction_id) for d in dataset_report.discrepancies
                    if d.transaction_id is not None}
    assert actual_pairs == expected_pairs  # nothing missed, nothing extra


def test_amounts_and_dates_match_ground_truth(dataset_report, expected):
    actual = {(d.issue_type.value, d.transaction_id): d for d in dataset_report.discrepancies}
    for row in expected:
        d = actual[(TYPE_MAP[row["discrepancy_type"]], row["transaction_id"])]
        assert d.platform_amount == Decimal(row["platform_amount"]), row["transaction_id"]
        assert d.bank_amount == Decimal(row["bank_amount"]), row["transaction_id"]
        assert d.amount_difference == Decimal(row["amount_difference"]), row["transaction_id"]
        assert d.settlement_id == row["settlement_id"]
        assert str(d.transaction_date) == row["transaction_date"]
        assert str(d.settlement_date) == row["settlement_date"]
        assert d.source_dataset.value == row["source_dataset"]


def test_aggregate_rounding_matches_ground_truth(dataset_report, expected):
    rounding_rows = [r for r in expected if r["discrepancy_type"] == "AGGREGATE_ROUNDING_DIFFERENCE"]
    [aggregate] = [d for d in dataset_report.discrepancies
                   if d.issue_type.value == "AGGREGATE_ROUNDING_DIFFERENCE"]
    assert set(aggregate.related_transaction_ids) == {r["transaction_id"] for r in rounding_rows}
    assert aggregate.amount_difference == sum(Decimal(r["amount_difference"]) for r in rounding_rows)
    assert aggregate.amount_difference == Decimal("0.120")


def test_summary_totals(dataset_report):
    s = dataset_report.summary
    assert (s.total_platform_records, s.unique_platform_transactions, s.total_bank_settlements) == (172, 171, 171)
    assert (s.matched_transactions, s.unmatched_transactions) == (171, 0)
    assert (s.duplicate_records, s.late_settlements, s.unmatched_refunds) == (1, 1, 1)
    assert s.aggregate_platform_amount == Decimal("213946.540")
    assert s.aggregate_bank_amount == Decimal("212696.42")
    assert s.aggregate_bank_amount_at_cutoff == Decimal("207946.42")
    assert s.total_variance == Decimal("1250.120")       # duplicate 1250.00 + rounding 0.120
    assert s.variance_at_cutoff == Decimal("6000.120")   # + late settlement 4750.00
    assert s.variance_fully_explained


def test_variance_breakdown_sums_exactly(dataset_report):
    s = dataset_report.summary
    assert sum(c.amount for c in dataset_report.variance_breakdown) == s.total_variance
    assert sum(c.amount for c in dataset_report.cutoff_variance_breakdown) == s.variance_at_cutoff
