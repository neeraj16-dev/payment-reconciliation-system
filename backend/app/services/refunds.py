"""Refund validation (assumptions §2.5).

Each REFUND must reference, via ``original_transaction_id``, a PAYMENT in the
platform file such that:
  1. the original exists and is a PAYMENT          -> else UNMATCHED_REFUND
  2. refund date >= original payment date          -> else INVALID_REFUND
  3. |refund| <= original amount                   -> else INVALID_REFUND
  4. the running total of refunds against one payment (in date order) does not
     exceed the original amount                    -> else INVALID_REFUND

Only the uploaded platform file is searched. A refund of a payment from an earlier
period will be reported as "not found in the uploaded file", not as fraud.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pandas as pd

from app.models import Discrepancy, IssueType, SourceDataset


def _first_per_id(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values("row_number").drop_duplicates("transaction_id", keep="first")


def validate_refunds(
    period_platform: pd.DataFrame,
    all_platform: pd.DataFrame,
    bank: pd.DataFrame,
) -> list[Discrepancy]:
    """``period_platform``: rows whose refunds are checked (in-period).
    ``all_platform``: full upload used to look up originals.
    ``bank``: used only to show the refund's settlement alongside the finding.
    """
    originals = {r["transaction_id"]: r for _, r in _first_per_id(all_platform).iterrows()}
    settlements = {r["transaction_id"]: r for _, r in _first_per_id(bank).iterrows()}
    refunds = _first_per_id(period_platform[period_platform["transaction_type"] == "REFUND"])
    refunds = refunds.sort_values(["date", "row_number"], kind="stable")

    findings: list[Discrepancy] = []
    refunded_so_far: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))

    def finding(r: pd.Series, issue: IssueType, classification: str, explanation: str) -> Discrepancy:
        s = settlements.get(r["transaction_id"])
        return Discrepancy(
            issue_type=issue,
            classification=classification,
            source_dataset=SourceDataset.PLATFORM,
            transaction_id=r["transaction_id"],
            settlement_id=None if s is None else s["settlement_id"],
            transaction_date=r["date"],
            settlement_date=None if s is None else s["date"],
            platform_amount=r["amount"],
            bank_amount=None if s is None else s["amount"],
            amount_difference=None if s is None else r["amount"] - s["amount"],
            explanation=explanation,
            platform_rows=[int(r["row_number"])],
            bank_rows=[] if s is None else [int(s["row_number"])],
            related_transaction_ids=[r["original_transaction_id"]] if r["original_transaction_id"] else [],
        )

    for _, r in refunds.iterrows():
        original_id = r["original_transaction_id"]
        if not original_id:
            findings.append(finding(r, IssueType.UNMATCHED_REFUND, "MISSING_REFERENCE",
                                    "Refund has no original_transaction_id, so it cannot be linked "
                                    "to the payment it reverses."))
            continue
        original = originals.get(original_id)
        if original is None:
            findings.append(finding(r, IssueType.UNMATCHED_REFUND, "ORPHAN_REFUND",
                                    f"Refund references original_transaction_id {original_id}, which "
                                    f"does not exist in the uploaded platform file. Escalate for "
                                    f"manual refund audit."))
            continue
        if original["transaction_type"] != "PAYMENT":
            findings.append(finding(r, IssueType.UNMATCHED_REFUND, "INVALID_REFERENCE",
                                    f"Refund references {original_id}, which is a "
                                    f"{original['transaction_type']}, not a PAYMENT."))
            continue

        refund_abs = -r["amount"]
        original_amount: Decimal = original["amount"]
        reasons = []
        if r["date"] < original["date"]:
            reasons.append(f"refund date {r['date']} is before the original payment date {original['date']}")
        if refund_abs > original_amount:
            reasons.append(f"refund of {refund_abs} exceeds the original payment of {original_amount}")
        else:
            refunded_so_far[original_id] += refund_abs
            if refunded_so_far[original_id] > original_amount:
                reasons.append(f"cumulative refunds against {original_id} reach "
                               f"{refunded_so_far[original_id]}, exceeding the original payment "
                               f"of {original_amount}")
        if reasons:
            findings.append(finding(r, IssueType.INVALID_REFUND, "REFUND_RULE_VIOLATION",
                                    f"Refund of {original_id} is invalid: " + "; ".join(reasons) + "."))
    return findings
