"""CSV loading and validation.

Every cell is read as a string so pandas never coerces amounts to floats or IDs to
numbers. Amounts are then parsed into ``Decimal`` exactly as written in the source
file (``"100.105"`` stays ``Decimal("100.105")``).

Validation is all-or-nothing: if any row is invalid the whole file is rejected with
a list of every problem found. Silently skipping rows would hide money.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd

from app.config import (
    BANK_STATUSES,
    PLATFORM_STATUSES,
    SUPPORTED_CURRENCIES,
    TRANSACTION_TYPES,
)
from app.models import ValidationIssue

AMOUNT_PATTERN = re.compile(r"^-?\d+(\.\d+)?$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class DatasetSchema:
    name: str
    required_columns: tuple[str, ...]
    optional_value_columns: frozenset[str]
    date_column: str
    amount_column: str
    allowed_statuses: frozenset[str]
    max_decimal_places: int | None


PLATFORM_SCHEMA = DatasetSchema(
    name="platform",
    required_columns=(
        "transaction_id",
        "transaction_date",
        "transaction_type",
        "status",
        "currency",
        "gross_amount",
        "original_transaction_id",
    ),
    # Empty for PAYMENT rows by design; refund linkage is checked by refunds.py.
    optional_value_columns=frozenset({"original_transaction_id"}),
    date_column="transaction_date",
    amount_column="gross_amount",
    allowed_statuses=PLATFORM_STATUSES,
    max_decimal_places=None,  # platform may carry sub-paise precision (assumptions §2.3)
)

BANK_SCHEMA = DatasetSchema(
    name="bank",
    required_columns=(
        "settlement_id",
        "transaction_id",
        "settlement_date",
        "transaction_type",
        "status",
        "currency",
        "settlement_amount",
    ),
    optional_value_columns=frozenset(),
    date_column="settlement_date",
    amount_column="settlement_amount",
    allowed_statuses=BANK_STATUSES,
    max_decimal_places=2,  # bank settles in paise (assumptions §2.3)
)


class CSVValidationError(Exception):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__(f"{len(issues)} validation error(s)")


def _issue(schema: DatasetSchema, message: str, row: int | None = None,
           column: str | None = None, value: str | None = None) -> ValidationIssue:
    return ValidationIssue(dataset=schema.name, row=row, column=column, value=value, message=message)


def _read_frame(content: bytes, schema: DatasetSchema) -> pd.DataFrame:
    if not content or not content.strip():
        raise CSVValidationError([_issue(schema, "File is empty.")])
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CSVValidationError([_issue(schema, "File is not valid UTF-8 text; expected a CSV file.")])
    try:
        frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, skip_blank_lines=True)
    except pd.errors.EmptyDataError:
        raise CSVValidationError([_issue(schema, "File has no header row.")])
    except pd.errors.ParserError as exc:
        raise CSVValidationError([_issue(schema, f"Malformed CSV: {exc}".strip())])

    frame.columns = [str(c).strip() for c in frame.columns]
    missing = [c for c in schema.required_columns if c not in frame.columns]
    if missing:
        raise CSVValidationError([
            _issue(
                schema,
                f"Missing required column(s): {', '.join(missing)}. "
                f"Found: {', '.join(frame.columns) or '(none)'}.",
            )
        ])
    if frame.empty:
        raise CSVValidationError([_issue(schema, "File has a header but no data rows.")])

    # Short rows are padded with NaN by pandas; treat them as empty cells.
    frame = frame.fillna("")
    for column in frame.columns:
        frame[column] = frame[column].astype(str).str.strip()
    return frame


def _parse_amount(raw: str) -> Decimal | None:
    if not AMOUNT_PATTERN.match(raw):
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:  # pragma: no cover - regex already guards this
        return None


def _parse_date(raw: str) -> date | None:
    if not DATE_PATTERN.match(raw):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def load_dataset(content: bytes, schema: DatasetSchema) -> pd.DataFrame:
    """Parse and validate a CSV upload.

    Returns the original columns plus:
      ``row_number`` (CSV line number, header = 1), ``amount`` (Decimal), ``date`` (date).
    Raises ``CSVValidationError`` listing every problem if anything is invalid.
    """
    frame = _read_frame(content, schema)
    issues: list[ValidationIssue] = []
    amounts: list[Decimal | None] = []
    dates: list[date | None] = []

    for position, record in enumerate(frame.to_dict("records")):
        row = position + 2  # +1 for header, +1 for 1-based line numbers

        for column in schema.required_columns:
            if column not in schema.optional_value_columns and record[column] == "":
                issues.append(_issue(schema, "Required value is missing.", row, column, ""))

        txn_type = record["transaction_type"]
        if txn_type and txn_type not in TRANSACTION_TYPES:
            issues.append(_issue(schema, f"Unknown transaction_type; expected one of "
                                 f"{sorted(TRANSACTION_TYPES)}.", row, "transaction_type", txn_type))

        status = record["status"]
        if status and status not in schema.allowed_statuses:
            issues.append(_issue(schema, f"Unsupported status; expected one of "
                                 f"{sorted(schema.allowed_statuses)}.", row, "status", status))

        currency = record["currency"]
        if currency and currency not in SUPPORTED_CURRENCIES:
            issues.append(_issue(schema, f"Unsupported currency; expected one of "
                                 f"{sorted(SUPPORTED_CURRENCIES)} (no FX conversion is defined).",
                                 row, "currency", currency))

        raw_date = record[schema.date_column]
        parsed_date = _parse_date(raw_date) if raw_date else None
        if raw_date and parsed_date is None:
            issues.append(_issue(schema, "Invalid date; expected ISO format YYYY-MM-DD.",
                                 row, schema.date_column, raw_date))
        dates.append(parsed_date)

        raw_amount = record[schema.amount_column]
        amount = _parse_amount(raw_amount) if raw_amount else None
        if raw_amount and amount is None:
            issues.append(_issue(schema, "Invalid amount; expected a plain decimal number such as "
                                 "1250.00 (no thousands separators or exponents).",
                                 row, schema.amount_column, raw_amount))
        if amount is not None:
            places = max(0, -amount.as_tuple().exponent)
            if schema.max_decimal_places is not None and places > schema.max_decimal_places:
                issues.append(_issue(schema, f"Amount has {places} decimal places; bank settlements "
                                     f"must have at most {schema.max_decimal_places}.",
                                     row, schema.amount_column, raw_amount))
            if amount == 0:
                issues.append(_issue(schema, "Amount must be non-zero.", row, schema.amount_column, raw_amount))
            elif txn_type == "PAYMENT" and amount < 0:
                issues.append(_issue(schema, "PAYMENT amounts must be positive.",
                                     row, schema.amount_column, raw_amount))
            elif txn_type == "REFUND" and amount > 0:
                issues.append(_issue(schema, "REFUND amounts must be negative (signed ledger convention).",
                                     row, schema.amount_column, raw_amount))
        amounts.append(amount)

    if issues:
        raise CSVValidationError(issues)

    frame["row_number"] = range(2, len(frame) + 2)
    frame["amount"] = pd.Series(amounts, index=frame.index, dtype=object)
    frame["date"] = pd.Series(dates, index=frame.index, dtype=object)
    return frame


def load_platform(content: bytes) -> pd.DataFrame:
    return load_dataset(content, PLATFORM_SCHEMA)


def load_bank(content: bytes) -> pd.DataFrame:
    return load_dataset(content, BANK_SCHEMA)
