from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import pytest

from app.services.csv_loader import load_bank, load_platform
from app.services.reconciler import reconcile

DATASETS_DIR = Path(__file__).resolve().parents[2] / "datasets"
CUTOFF = date(2026, 10, 31)

PLATFORM_HEADER = ["transaction_id", "transaction_date", "transaction_type", "status", "currency",
                   "gross_amount", "payment_method", "merchant_id", "customer_id", "original_transaction_id"]
BANK_HEADER = ["settlement_id", "transaction_id", "settlement_date", "transaction_type", "status",
               "currency", "settlement_amount", "bank_reference"]


def to_csv(header: list[str], rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def ptxn(txn_id: str, amount: str, day: str = "2026-10-10", txn_type: str = "PAYMENT",
         original: str = "") -> dict:
    return {
        "transaction_id": txn_id, "transaction_date": day, "transaction_type": txn_type,
        "status": "SUCCESS", "currency": "INR", "gross_amount": amount, "payment_method": "UPI",
        "merchant_id": "MCH001", "customer_id": "CUST1001", "original_transaction_id": original,
    }


def bset(txn_id: str, amount: str, day: str = "2026-10-11", txn_type: str = "PAYMENT",
         settlement_id: str | None = None) -> dict:
    sid = settlement_id or txn_id.replace("TXN", "SET")
    return {
        "settlement_id": sid, "transaction_id": txn_id, "settlement_date": day,
        "transaction_type": txn_type, "status": "SETTLED", "currency": "INR",
        "settlement_amount": amount, "bank_reference": f"UTR{sid}",
    }


def run(platform_rows: list[dict], bank_rows: list[dict], cutoff: date = CUTOFF, **kwargs):
    platform = load_platform(to_csv(PLATFORM_HEADER, platform_rows))
    bank = load_bank(to_csv(BANK_HEADER, bank_rows))
    return reconcile(platform, bank, cutoff, **kwargs)


def of_type(report, issue_type: str) -> list:
    return [d for d in report.discrepancies if d.issue_type.value == issue_type]


@pytest.fixture(scope="session")
def platform_bytes() -> bytes:
    return (DATASETS_DIR / "platform_transactions.csv").read_bytes()


@pytest.fixture(scope="session")
def bank_bytes() -> bytes:
    return (DATASETS_DIR / "bank_settlements.csv").read_bytes()


@pytest.fixture(scope="session")
def dataset_report(platform_bytes, bank_bytes):
    return reconcile(load_platform(platform_bytes), load_bank(bank_bytes), CUTOFF)
