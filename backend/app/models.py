"""Pydantic models for the reconciliation API.

Monetary values are ``Decimal`` and serialise to JSON strings, so source precision
(e.g. ``100.105``) survives the round trip to the client unchanged.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class IssueType(str, Enum):
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    MISSING_SETTLEMENT = "MISSING_SETTLEMENT"
    UNMATCHED_SETTLEMENT = "UNMATCHED_SETTLEMENT"
    LATE_SETTLEMENT = "LATE_SETTLEMENT"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    AGGREGATE_ROUNDING_DIFFERENCE = "AGGREGATE_ROUNDING_DIFFERENCE"
    SUB_PAISE_VARIANCE = "SUB_PAISE_VARIANCE"
    UNMATCHED_REFUND = "UNMATCHED_REFUND"
    INVALID_REFUND = "INVALID_REFUND"
    OUT_OF_PERIOD = "OUT_OF_PERIOD"


# Display / sort order for the detailed report.
ISSUE_ORDER: dict[IssueType, int] = {t: i for i, t in enumerate(IssueType)}


class SourceDataset(str, Enum):
    PLATFORM = "PLATFORM"
    BANK = "BANK"
    BOTH = "BOTH"


class Discrepancy(BaseModel):
    discrepancy_id: str = Field(default="", description="Assigned by the orchestrator after sorting.")
    issue_type: IssueType
    classification: str
    source_dataset: SourceDataset
    transaction_id: str | None = None
    settlement_id: str | None = None
    transaction_date: date | None = None
    settlement_date: date | None = None
    platform_amount: Decimal | None = None
    bank_amount: Decimal | None = None
    amount_difference: Decimal | None = Field(
        default=None, description="Platform minus bank (effect on total variance)."
    )
    explanation: str
    platform_rows: list[int] = Field(
        default_factory=list, description="1-based CSV line numbers (header = line 1)."
    )
    bank_rows: list[int] = Field(default_factory=list)
    related_transaction_ids: list[str] = Field(default_factory=list)


class VarianceComponent(BaseModel):
    key: str
    label: str
    amount: Decimal
    record_count: int


class ReconciliationParameters(BaseModel):
    cutoff_date: date
    cutoff_source: str = Field(description="'provided' or 'derived' (month-end of latest transaction).")
    materiality_threshold: Decimal
    bank_rounding_mode: str


class ReconciliationSummary(BaseModel):
    total_platform_records: int
    unique_platform_transactions: int
    total_bank_settlements: int
    unique_bank_transactions: int
    matched_transactions: int
    unmatched_transactions: int
    unmatched_platform_transactions: int
    unmatched_bank_settlements: int
    duplicate_records: int = Field(description="Extra rows beyond the first, across both datasets.")
    duplicate_groups: int
    unresolved_duplicate_ids: int
    late_settlements: int
    unmatched_refunds: int
    invalid_refunds: int
    amount_mismatches: int
    sub_paise_variances: int
    out_of_period_records: int
    aggregate_platform_amount: Decimal
    aggregate_bank_amount: Decimal
    aggregate_bank_amount_at_cutoff: Decimal
    total_variance: Decimal = Field(description="Platform total minus all bank settlements.")
    variance_at_cutoff: Decimal = Field(description="Platform total minus bank settled on/before cutoff.")
    aggregate_rounding_difference: Decimal
    individually_rounded_difference: Decimal = Field(
        description="Same rounding cohort compared after rounding each platform amount to 2dp."
    )
    rounding_threshold_breached: bool
    variance_fully_explained: bool
    late_settlement_amount: Decimal


class ReconciliationReport(BaseModel):
    generated_at: datetime
    parameters: ReconciliationParameters
    summary: ReconciliationSummary
    variance_breakdown: list[VarianceComponent]
    cutoff_variance_breakdown: list[VarianceComponent]
    issue_counts: dict[str, int]
    discrepancies: list[Discrepancy]


class ValidationIssue(BaseModel):
    dataset: str
    row: int | None = None
    column: str | None = None
    value: str | None = None
    message: str


class ValidationErrorResponse(BaseModel):
    message: str
    total_errors: int
    errors: list[ValidationIssue]
