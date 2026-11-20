"""Reconciliation orchestration.

Pipeline:
  1. Split both files into the reporting period (platform transaction_date <= cutoff).
  2. Detect duplicates per dataset; set aside excess copies and conflicting IDs.
  3. Match the remaining one-row-per-ID records on transaction_id.
  4. Timing: late settlements, missing settlements, unmatched bank settlements.
  5. Amounts: sub-paise variances, aggregate rounding, true mismatches.
  6. Refund linkage.
  7. Variance breakdown. Every row of both files falls in exactly one bucket, so the
     components must sum exactly to the total variance. This is checked.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd

from app.config import DEFAULT_MATERIALITY_THRESHOLD
from app.models import (
    ISSUE_ORDER,
    Discrepancy,
    IssueType,
    ReconciliationParameters,
    ReconciliationReport,
    ReconciliationSummary,
    SourceDataset,
    VarianceComponent,
)
from app.services import duplicates, matching, refunds, rounding, timing

ZERO = Decimal("0.00")  # empty sums display as 0.00 (bank precision)


def _total(frame: pd.DataFrame) -> Decimal:
    return sum(frame["amount"], ZERO)


def _duplicate_findings(groups: list[duplicates.DuplicateGroup], platform: pd.DataFrame,
                        bank: pd.DataFrame) -> list[Discrepancy]:
    """One finding per duplicate group. ``amount_difference`` is the group's effect
    on total variance (platform minus bank)."""
    platform_by_id = {k: g for k, g in platform.groupby("transaction_id")}
    bank_by_id = {k: g for k, g in bank.groupby("transaction_id")}
    findings = []
    for g in groups:
        first = g.rows.iloc[0]
        if g.classification == duplicates.SETTLEMENT_ID_REUSE:
            findings.append(Discrepancy(
                issue_type=IssueType.DUPLICATE_ENTRY, classification=g.classification,
                source_dataset=SourceDataset.BANK, settlement_id=g.key,
                settlement_date=first["date"], bank_amount=g.total_amount,
                explanation=(f"settlement_id {g.key} appears on {len(g.rows)} bank rows for different "
                             f"transactions ({', '.join(g.rows['transaction_id'])}). settlement_id must "
                             f"be unique; matching is unaffected because it uses transaction_id."),
                bank_rows=g.row_numbers, related_transaction_ids=list(g.rows["transaction_id"]),
            ))
            continue

        p_rows = platform_by_id.get(g.key, platform.iloc[0:0])
        b_rows = bank_by_id.get(g.key, bank.iloc[0:0])
        p_total, b_total = _total(p_rows), _total(b_rows)
        dataset_name = "platform_transactions" if g.dataset == SourceDataset.PLATFORM else "bank_settlements"
        n = len(g.rows)

        if g.is_conflicting:
            difference = p_total - b_total
            explanation = (f"transaction_id {g.key} appears {n} times in {dataset_name} with differing "
                           f"amounts, dates or types. The correct record cannot be determined, so it was "
                           f"not matched; all its rows count as unresolved.")
        else:
            difference = g.excess_amount if g.dataset == SourceDataset.PLATFORM else -g.excess_amount
            other = "bank settled it" if g.dataset == SourceDataset.PLATFORM else "platform recorded it"
            other_count = len(b_rows) if g.dataset == SourceDataset.PLATFORM else len(p_rows)
            explanation = (f"transaction_id {g.key} appears {n} times in {dataset_name} with identical "
                           f"financial details; {other} {other_count} time(s). One row was matched; "
                           f"the {n - 1} extra row(s) overstate the {g.dataset.value.lower()} ledger by "
                           f"INR {g.excess_amount}.")

        findings.append(Discrepancy(
            issue_type=IssueType.DUPLICATE_ENTRY, classification=g.classification,
            source_dataset=g.dataset, transaction_id=g.key,
            settlement_id=b_rows.iloc[0]["settlement_id"] if len(b_rows) else None,
            transaction_date=p_rows.iloc[0]["date"] if len(p_rows) else None,
            settlement_date=b_rows.iloc[0]["date"] if len(b_rows) else None,
            platform_amount=p_total if len(p_rows) else None,
            bank_amount=b_total if len(b_rows) else None,
            amount_difference=difference, explanation=explanation,
            platform_rows=[int(r) for r in p_rows["row_number"]],
            bank_rows=[int(r) for r in b_rows["row_number"]],
        ))
    return findings


def reconcile(
    platform: pd.DataFrame,
    bank: pd.DataFrame,
    cutoff: date | None = None,
    materiality_threshold: Decimal = DEFAULT_MATERIALITY_THRESHOLD,
) -> ReconciliationReport:
    cutoff_source = "provided"
    if cutoff is None:
        cutoff, cutoff_source = timing.derive_cutoff(platform), "derived"

    # 1. Reporting period
    period = timing.split_period(platform, bank, cutoff)
    p, b = period.platform, period.bank

    # 2. Duplicates
    p_groups = duplicates.find_transaction_duplicates(p, SourceDataset.PLATFORM)
    b_groups = duplicates.find_transaction_duplicates(b, SourceDataset.BANK)
    sid_groups = duplicates.find_settlement_id_reuse(b)
    unresolved_ids = {g.key for g in p_groups + b_groups if g.is_conflicting}
    p_canon, p_excess, p_unresolved = duplicates.split_for_matching(p, p_groups, unresolved_ids)
    b_canon, b_excess, b_unresolved = duplicates.split_for_matching(b, b_groups, unresolved_ids)

    # 3. Matching
    match = matching.match_transactions(p_canon, b_canon)

    # 4. Timing
    late = timing.late_settlement_findings(match.matched, cutoff)
    missing = timing.missing_settlement_findings(match.platform_only, cutoff)
    unmatched_bank = timing.unmatched_settlement_findings(match.bank_only)

    # 5. Amounts
    amounts = rounding.analyse_amounts(match.matched, materiality_threshold)

    # 6. Refunds
    refund_findings = refunds.validate_refunds(p, platform, b)

    # 7. Totals and variance breakdown
    platform_total = _total(p)
    bank_total = _total(b)
    after_cutoff = b["date"].map(lambda d: d > cutoff).astype(bool)
    bank_total_at_cutoff = _total(b[~after_cutoff])
    total_variance = platform_total - bank_total
    variance_at_cutoff = platform_total - bank_total_at_cutoff

    late_amount = sum((d.bank_amount for d in late), ZERO)
    other_after_cutoff = _total(b[after_cutoff]) - late_amount

    breakdown = [
        VarianceComponent(key="platform_duplicate_excess", label="Duplicate platform entries",
                          amount=_total(p_excess), record_count=len(p_excess)),
        VarianceComponent(key="bank_duplicate_excess", label="Duplicate bank settlements",
                          amount=-_total(b_excess), record_count=len(b_excess)),
        VarianceComponent(key="unresolved_duplicates", label="Conflicting duplicates (unmatched)",
                          amount=_total(p_unresolved) - _total(b_unresolved),
                          record_count=len(p_unresolved) + len(b_unresolved)),
        VarianceComponent(key="missing_settlements", label="Platform transactions never settled",
                          amount=_total(match.platform_only), record_count=len(match.platform_only)),
        VarianceComponent(key="unmatched_settlements", label="Bank settlements without a transaction",
                          amount=-_total(match.bank_only), record_count=len(match.bank_only)),
        VarianceComponent(key="amount_mismatches", label="Matched amount mismatches",
                          amount=amounts.mismatch_difference, record_count=len(amounts.mismatches)),
        VarianceComponent(key="rounding", label="Sub-paise rounding (aggregate)",
                          amount=amounts.aggregate_difference, record_count=len(amounts.sub_paise)),
    ]
    cutoff_breakdown = breakdown + [
        VarianceComponent(key="late_settlements", label="Settled after cutoff (in transit)",
                          amount=late_amount, record_count=len(late)),
        VarianceComponent(key="other_after_cutoff", label="Other bank activity after cutoff",
                          amount=other_after_cutoff,
                          record_count=int(after_cutoff.sum()) - len(late)),
    ]
    explained = (sum((c.amount for c in breakdown), ZERO) == total_variance
                 and sum((c.amount for c in cutoff_breakdown), ZERO) == variance_at_cutoff)

    # Assemble discrepancies
    discrepancies: list[Discrepancy] = (
        _duplicate_findings(p_groups + b_groups + sid_groups, p, b)
        + missing + unmatched_bank + late
        + amounts.mismatches + amounts.type_mismatches
        + ([amounts.aggregate_finding] if amounts.aggregate_finding else [])
        + amounts.sub_paise + refund_findings
        + timing.out_of_period_findings(period, cutoff)
    )
    discrepancies.sort(key=lambda d: (ISSUE_ORDER[d.issue_type], d.transaction_id or "", d.settlement_id or ""))
    for i, d in enumerate(discrepancies, start=1):
        d.discrepancy_id = f"D{i:04d}"

    def count(issue: IssueType) -> int:
        return sum(1 for d in discrepancies if d.issue_type == issue)

    issue_counts = {t.value: count(t) for t in IssueType if count(t)}

    summary = ReconciliationSummary(
        total_platform_records=len(p),
        unique_platform_transactions=p["transaction_id"].nunique(),
        total_bank_settlements=len(b),
        unique_bank_transactions=b["transaction_id"].nunique(),
        matched_transactions=len(match.matched),
        unmatched_transactions=len(match.platform_only) + len(match.bank_only),
        unmatched_platform_transactions=len(match.platform_only),
        unmatched_bank_settlements=len(match.bank_only),
        duplicate_records=sum(len(g.rows) - 1 for g in p_groups + b_groups),
        duplicate_groups=len(p_groups) + len(b_groups) + len(sid_groups),
        unresolved_duplicate_ids=len(unresolved_ids),
        late_settlements=len(late),
        unmatched_refunds=count(IssueType.UNMATCHED_REFUND),
        invalid_refunds=count(IssueType.INVALID_REFUND),
        amount_mismatches=len(amounts.mismatches),
        sub_paise_variances=len(amounts.sub_paise),
        out_of_period_records=len(period.platform_out),
        aggregate_platform_amount=platform_total,
        aggregate_bank_amount=bank_total,
        aggregate_bank_amount_at_cutoff=bank_total_at_cutoff,
        total_variance=total_variance,
        variance_at_cutoff=variance_at_cutoff,
        aggregate_rounding_difference=amounts.aggregate_difference,
        individually_rounded_difference=amounts.individually_rounded_difference,
        rounding_threshold_breached=amounts.threshold_breached,
        variance_fully_explained=explained,
        late_settlement_amount=late_amount,
    )

    return ReconciliationReport(
        generated_at=datetime.now(timezone.utc),
        parameters=ReconciliationParameters(
            cutoff_date=cutoff, cutoff_source=cutoff_source,
            materiality_threshold=materiality_threshold, bank_rounding_mode="ROUND_HALF_EVEN",
        ),
        summary=summary,
        variance_breakdown=breakdown,
        cutoff_variance_breakdown=cutoff_breakdown,
        issue_counts=issue_counts,
        discrepancies=discrepancies,
    )
