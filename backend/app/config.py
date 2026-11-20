"""Reconciliation-wide constants.

Every value here comes from ``datasets/dataset_assumptions.md``; nothing is tuned
to make a particular dataset pass.
"""

from decimal import ROUND_HALF_EVEN, Decimal

# Bank settles in 2-decimal INR (paise) using banker's rounding (assumptions §2.3).
BANK_PRECISION = Decimal("0.01")
BANK_ROUNDING = ROUND_HALF_EVEN

# Aggregate rounding materiality threshold (assumptions §2.3). Overridable per request.
DEFAULT_MATERIALITY_THRESHOLD = Decimal("0.10")

# No FX handling is defined, so any other currency is rejected at validation time.
SUPPORTED_CURRENCIES = frozenset({"INR"})

TRANSACTION_TYPES = frozenset({"PAYMENT", "REFUND"})
PLATFORM_STATUSES = frozenset({"SUCCESS"})
BANK_STATUSES = frozenset({"SETTLED"})

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REPORTED_VALIDATION_ERRORS = 200
