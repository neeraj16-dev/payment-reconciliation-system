"""One-to-one transaction matching on ``transaction_id``.

Inputs must already be de-duplicated (see ``duplicates.split_for_matching``), so each
ID appears at most once per side. pandas' ``validate="one_to_one"`` enforces this:
a duplicate slipping through raises instead of silently producing extra matches.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PLATFORM_COLUMNS = ["transaction_id", "row_number", "date", "transaction_type", "amount", "original_transaction_id"]
BANK_COLUMNS = ["transaction_id", "settlement_id", "row_number", "date", "transaction_type", "amount"]


@dataclass
class MatchResult:
    matched: pd.DataFrame        # columns suffixed _platform / _bank (settlement_id unsuffixed)
    platform_only: pd.DataFrame  # platform rows with no bank settlement
    bank_only: pd.DataFrame      # bank rows with no platform transaction


def match_transactions(platform: pd.DataFrame, bank: pd.DataFrame) -> MatchResult:
    matched = platform[PLATFORM_COLUMNS].merge(
        bank[BANK_COLUMNS],
        on="transaction_id",
        how="inner",
        suffixes=("_platform", "_bank"),
        validate="one_to_one",
    ).sort_values("transaction_id", kind="stable").reset_index(drop=True)

    platform_only = platform[~platform["transaction_id"].isin(bank["transaction_id"])]
    bank_only = bank[~bank["transaction_id"].isin(platform["transaction_id"])]
    return MatchResult(
        matched=matched,
        platform_only=platform_only.sort_values("transaction_id", kind="stable"),
        bank_only=bank_only.sort_values("transaction_id", kind="stable"),
    )
