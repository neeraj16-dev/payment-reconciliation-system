"""Duplicate detection.

Duplicates are found strictly by key (``transaction_id``; also ``settlement_id`` in
the bank file). Rows that merely share a date and amount are never compared.

Within a group of rows sharing a ``transaction_id``:
  * EXACT_DUPLICATE        - every financial attribute is identical. The first row
                             is kept for matching; the others are "excess" and their
                             amount is an overstatement of that ledger.
  * CONFLICTING_DUPLICATE  - same ID but financial attributes differ. Choosing one
                             row would be a guess, so the ID is excluded from
                             matching and reported as unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd

from app.models import SourceDataset

# Attributes that must agree for two rows to be "the same entry recorded twice".
# Bank settlement_date is deliberately excluded: the same settlement paid twice on
# different days is still a double settlement of identical value.
PLATFORM_FINANCIAL_ATTRIBUTES = ("date", "transaction_type", "amount", "currency", "original_transaction_id")
BANK_FINANCIAL_ATTRIBUTES = ("transaction_type", "amount", "currency")

EXACT = "EXACT_DUPLICATE"
CONFLICTING = "CONFLICTING_DUPLICATE"
SETTLEMENT_ID_REUSE = "DUPLICATE_SETTLEMENT_ID"


@dataclass
class DuplicateGroup:
    dataset: SourceDataset
    key_column: str
    key: str
    classification: str
    rows: pd.DataFrame
    kept_row_number: int | None = None
    excess_row_numbers: list[int] = field(default_factory=list)
    excess_amount: Decimal = Decimal("0.00")

    @property
    def row_numbers(self) -> list[int]:
        return [int(r) for r in self.rows["row_number"]]

    @property
    def total_amount(self) -> Decimal:
        return sum(self.rows["amount"], Decimal("0.00"))

    @property
    def is_conflicting(self) -> bool:
        return self.classification == CONFLICTING


def _signature(row: pd.Series, attributes: tuple[str, ...]) -> tuple:
    return tuple(row[a] for a in attributes)


def find_transaction_duplicates(frame: pd.DataFrame, dataset: SourceDataset) -> list[DuplicateGroup]:
    """Group rows by transaction_id and classify every group with more than one row."""
    attributes = PLATFORM_FINANCIAL_ATTRIBUTES if dataset == SourceDataset.PLATFORM else BANK_FINANCIAL_ATTRIBUTES
    # Deterministic choice of the kept row: earliest date, then earliest line in file.
    ordered = frame.sort_values(["date", "row_number"], kind="stable")
    counts = ordered["transaction_id"].value_counts()
    groups: list[DuplicateGroup] = []
    for txn_id in sorted(counts[counts > 1].index):
        rows = ordered[ordered["transaction_id"] == txn_id]
        signatures = {_signature(r, attributes) for _, r in rows.iterrows()}
        if len(signatures) == 1:
            excess = rows.iloc[1:]
            groups.append(DuplicateGroup(
                dataset=dataset,
                key_column="transaction_id",
                key=txn_id,
                classification=EXACT,
                rows=rows,
                kept_row_number=int(rows.iloc[0]["row_number"]),
                excess_row_numbers=[int(r) for r in excess["row_number"]],
                excess_amount=sum(excess["amount"], Decimal("0.00")),
            ))
        else:
            groups.append(DuplicateGroup(
                dataset=dataset, key_column="transaction_id", key=txn_id,
                classification=CONFLICTING, rows=rows,
            ))
    return groups


def find_settlement_id_reuse(bank: pd.DataFrame) -> list[DuplicateGroup]:
    """Bank settlement_id must be unique. Reuse across *different* transaction_ids is
    reported here; reuse within one transaction_id is already covered by
    ``find_transaction_duplicates``. Informational only: matching is by transaction_id.
    """
    counts = bank["settlement_id"].value_counts()
    groups: list[DuplicateGroup] = []
    for settlement_id in sorted(counts[counts > 1].index):
        rows = bank[bank["settlement_id"] == settlement_id].sort_values("row_number")
        if rows["transaction_id"].nunique() > 1:
            groups.append(DuplicateGroup(
                dataset=SourceDataset.BANK, key_column="settlement_id", key=settlement_id,
                classification=SETTLEMENT_ID_REUSE, rows=rows,
            ))
    return groups


def split_for_matching(frame: pd.DataFrame, groups: list[DuplicateGroup],
                       unresolved_ids: set[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Partition rows into (canonical, excess, unresolved).

    canonical  - at most one row per transaction_id, eligible for matching
    excess     - extra copies of exact duplicates (never matched)
    unresolved - all rows whose transaction_id is in ``unresolved_ids``
    """
    excess_rows = {n for g in groups if not g.is_conflicting for n in g.excess_row_numbers}
    is_unresolved = frame["transaction_id"].isin(unresolved_ids)
    is_excess = frame["row_number"].isin(excess_rows) & ~is_unresolved
    canonical = frame[~is_unresolved & ~is_excess]
    return canonical, frame[is_excess], frame[is_unresolved]
