"""Cutoff handling: reporting period, late settlements, missing settlements.

  * LATE_SETTLEMENT     - recorded on/before the cutoff, settled *after* it. A timing
                          difference (cash in transit), not a loss.
  * MISSING_SETTLEMENT  - recorded on/before the cutoff with no settlement anywhere in
                          the uploaded bank file (which should include the post-cutoff
                          lookahead window, assumptions §2.1).
  * UNMATCHED_SETTLEMENT- bank settlement with no platform transaction.
  * OUT_OF_PERIOD       - platform transaction dated after the cutoff. Excluded from the
                          period population together with its settlement (if any).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.models import Discrepancy, IssueType, SourceDataset


@dataclass
class PeriodSplit:
    platform: pd.DataFrame
    bank: pd.DataFrame
    platform_out: pd.DataFrame
    bank_out: pd.DataFrame


def derive_cutoff(platform: pd.DataFrame) -> date:
    """Month-end of the latest platform transaction date."""
    latest: date = max(platform["date"])
    return date(latest.year, latest.month, calendar.monthrange(latest.year, latest.month)[1])


def split_period(platform: pd.DataFrame, bank: pd.DataFrame, cutoff: date) -> PeriodSplit:
    is_out = platform["date"].map(lambda d: d > cutoff).astype(bool)
    platform_in, platform_out = platform[~is_out], platform[is_out]
    # A settlement belongs out of period only if its transaction exists solely after the cutoff.
    out_only_ids = set(platform_out["transaction_id"]) - set(platform_in["transaction_id"])
    bank_is_out = bank["transaction_id"].isin(out_only_ids)
    return PeriodSplit(platform_in, bank[~bank_is_out], platform_out, bank[bank_is_out])


def late_settlement_mask(matched: pd.DataFrame, cutoff: date) -> pd.Series:
    if matched.empty:
        return pd.Series(dtype=bool)
    return matched.apply(
        lambda r: r["date_platform"] <= cutoff < r["date_bank"], axis=1
    ).astype(bool)


def late_settlement_findings(matched: pd.DataFrame, cutoff: date) -> list[Discrepancy]:
    findings = []
    for _, r in matched[late_settlement_mask(matched, cutoff)].iterrows():
        lag = (r["date_bank"] - r["date_platform"]).days
        findings.append(Discrepancy(
            issue_type=IssueType.LATE_SETTLEMENT,
            classification="TIMING_DIFFERENCE",
            source_dataset=SourceDataset.BOTH,
            transaction_id=r["transaction_id"],
            settlement_id=r["settlement_id"],
            transaction_date=r["date_platform"],
            settlement_date=r["date_bank"],
            platform_amount=r["amount_platform"],
            bank_amount=r["amount_bank"],
            amount_difference=r["amount_platform"] - r["amount_bank"],
            explanation=(
                f"Recorded {r['date_platform']} (on/before cutoff {cutoff}) but settled "
                f"{r['date_bank']}, {lag} day(s) later and after the cutoff. Timing difference: "
                f"INR {r['amount_bank']} is in transit at the cutoff, not a missing settlement."
            ),
            platform_rows=[int(r["row_number_platform"])],
            bank_rows=[int(r["row_number_bank"])],
        ))
    return findings


def missing_settlement_findings(platform_only: pd.DataFrame, cutoff: date) -> list[Discrepancy]:
    return [
        Discrepancy(
            issue_type=IssueType.MISSING_SETTLEMENT,
            classification="NO_BANK_RECORD",
            source_dataset=SourceDataset.PLATFORM,
            transaction_id=r["transaction_id"],
            transaction_date=r["date"],
            platform_amount=r["amount"],
            amount_difference=r["amount"],
            explanation=(
                f"Platform {r['transaction_type']} recorded {r['date']} has no settlement in the "
                f"uploaded bank file, including any records after the {cutoff} cutoff. "
                f"Not a timing difference within the supplied data."
            ),
            platform_rows=[int(r["row_number"])],
        )
        for _, r in platform_only.iterrows()
    ]


def unmatched_settlement_findings(bank_only: pd.DataFrame) -> list[Discrepancy]:
    return [
        Discrepancy(
            issue_type=IssueType.UNMATCHED_SETTLEMENT,
            classification="NO_PLATFORM_RECORD",
            source_dataset=SourceDataset.BANK,
            transaction_id=r["transaction_id"],
            settlement_id=r["settlement_id"],
            settlement_date=r["date"],
            bank_amount=r["amount"],
            amount_difference=-r["amount"],
            explanation=(
                f"Bank settlement {r['settlement_id']} on {r['date']} references "
                f"{r['transaction_id']}, which is not in the platform file's reporting period."
            ),
            bank_rows=[int(r["row_number"])],
        )
        for _, r in bank_only.iterrows()
    ]


def out_of_period_findings(split: PeriodSplit, cutoff: date) -> list[Discrepancy]:
    settlements = {r["transaction_id"]: r for _, r in split.bank_out.iterrows()}
    findings = []
    for _, r in split.platform_out.sort_values(["transaction_id", "row_number"]).iterrows():
        s = settlements.get(r["transaction_id"])
        findings.append(Discrepancy(
            issue_type=IssueType.OUT_OF_PERIOD,
            classification="AFTER_CUTOFF",
            source_dataset=SourceDataset.PLATFORM,
            transaction_id=r["transaction_id"],
            settlement_id=None if s is None else s["settlement_id"],
            transaction_date=r["date"],
            settlement_date=None if s is None else s["date"],
            platform_amount=r["amount"],
            bank_amount=None if s is None else s["amount"],
            explanation=(
                f"Transaction dated {r['date']} is after the {cutoff} cutoff and is excluded "
                f"from this period's totals"
                + ("" if s is None else f", together with its settlement {s['settlement_id']}")
                + ". Informational."
            ),
            platform_rows=[int(r["row_number"])],
            bank_rows=[] if s is None else [int(s["row_number"])],
        ))
    return findings
