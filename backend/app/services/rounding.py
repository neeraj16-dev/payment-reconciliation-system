"""Amount comparison and aggregate rounding analysis.

For each matched pair, ``delta = platform - bank`` is computed exactly in Decimal:

  * delta == 0                                         -> clean
  * delta != 0 and round_2dp(platform) == bank         -> SUB_PAISE_VARIANCE
        (invisible if you only compare individually rounded amounts)
  * otherwise                                          -> AMOUNT_MISMATCH

The sub-paise deltas are then summed *without* intermediate rounding. If the
absolute sum reaches the materiality threshold, an AGGREGATE_ROUNDING_DIFFERENCE is
raised listing every contributing transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd

from app.config import BANK_PRECISION, BANK_ROUNDING
from app.models import Discrepancy, IssueType, SourceDataset

ZERO = Decimal("0.00")  # empty sums display as 0.00 (bank precision)


def round_to_bank_precision(amount: Decimal) -> Decimal:
    return amount.quantize(BANK_PRECISION, rounding=BANK_ROUNDING)


@dataclass
class RoundingAnalysis:
    threshold: Decimal
    sub_paise: list[Discrepancy] = field(default_factory=list)
    mismatches: list[Discrepancy] = field(default_factory=list)
    type_mismatches: list[Discrepancy] = field(default_factory=list)
    aggregate_difference: Decimal = ZERO
    individually_rounded_difference: Decimal = ZERO
    mismatch_difference: Decimal = ZERO
    aggregate_finding: Discrepancy | None = None

    @property
    def threshold_breached(self) -> bool:
        return self.aggregate_finding is not None


def _base(r: pd.Series) -> dict:
    return dict(
        source_dataset=SourceDataset.BOTH,
        transaction_id=r["transaction_id"],
        settlement_id=r["settlement_id"],
        transaction_date=r["date_platform"],
        settlement_date=r["date_bank"],
        platform_amount=r["amount_platform"],
        bank_amount=r["amount_bank"],
        platform_rows=[int(r["row_number_platform"])],
        bank_rows=[int(r["row_number_bank"])],
    )


def analyse_amounts(matched: pd.DataFrame, threshold: Decimal) -> RoundingAnalysis:
    result = RoundingAnalysis(threshold=threshold)
    sub_paise_platform = sub_paise_bank = ZERO

    for _, r in matched.iterrows():
        platform_amt: Decimal = r["amount_platform"]
        bank_amt: Decimal = r["amount_bank"]
        delta = platform_amt - bank_amt

        if r["transaction_type_platform"] != r["transaction_type_bank"]:
            result.type_mismatches.append(Discrepancy(
                issue_type=IssueType.TYPE_MISMATCH, classification="TRANSACTION_TYPE_CONFLICT",
                amount_difference=delta,
                explanation=(f"Platform records {r['transaction_type_platform']} but the bank records "
                             f"{r['transaction_type_bank']} for the same transaction_id."),
                **_base(r),
            ))

        if delta == 0:
            continue
        rounded = round_to_bank_precision(platform_amt)
        if rounded == bank_amt:
            result.aggregate_difference += delta
            result.individually_rounded_difference += rounded - bank_amt  # always 0 by definition
            sub_paise_platform += platform_amt
            sub_paise_bank += bank_amt
            result.sub_paise.append(Discrepancy(
                issue_type=IssueType.SUB_PAISE_VARIANCE, classification="ROUNDING_VARIANCE",
                amount_difference=delta,
                explanation=(f"Platform carries sub-paise precision ({platform_amt}); bank settled "
                             f"{bank_amt}. Difference {delta} disappears when the platform amount is "
                             f"rounded to 2dp ({rounded}), but still counts toward the aggregate."),
                **_base(r),
            ))
        else:
            result.mismatch_difference += delta
            result.mismatches.append(Discrepancy(
                issue_type=IssueType.AMOUNT_MISMATCH, classification="AMOUNT_DIFFERENCE",
                amount_difference=delta,
                explanation=(f"Platform amount {platform_amt} differs from bank settlement {bank_amt} "
                             f"by {delta}; not explained by rounding to 2dp (rounded platform "
                             f"amount is {rounded})."),
                **_base(r),
            ))

    if result.sub_paise and abs(result.aggregate_difference) >= threshold:
        count = len(result.sub_paise)
        result.aggregate_finding = Discrepancy(
            issue_type=IssueType.AGGREGATE_ROUNDING_DIFFERENCE,
            classification="ROUNDING_VARIANCE",
            source_dataset=SourceDataset.BOTH,
            platform_amount=sub_paise_platform,
            bank_amount=sub_paise_bank,
            amount_difference=result.aggregate_difference,
            explanation=(
                f"{count} matched transactions each differ by less than one paisa. Compared one by "
                f"one after rounding to 2dp they total {result.individually_rounded_difference}, but "
                f"the exact differences sum to {result.aggregate_difference}, which meets the "
                f"INR {threshold} materiality threshold."
            ),
            related_transaction_ids=[d.transaction_id for d in result.sub_paise],
        )
    return result
