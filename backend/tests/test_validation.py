"""CSV validation: invalid formats, missing columns, missing values (scenarios 7 & 8)."""

from decimal import Decimal

import pytest

from app.services.csv_loader import CSVValidationError, load_bank, load_platform
from tests.conftest import BANK_HEADER, PLATFORM_HEADER, bset, ptxn, to_csv


def platform_errors(content: bytes):
    with pytest.raises(CSVValidationError) as exc:
        load_platform(content)
    return exc.value.issues


def bank_errors(content: bytes):
    with pytest.raises(CSVValidationError) as exc:
        load_bank(content)
    return exc.value.issues


def test_valid_file_preserves_source_precision():
    frame = load_platform(to_csv(PLATFORM_HEADER, [ptxn("TXN0001", "100.105"), ptxn("TXN0002", "1250.00")]))
    assert frame.loc[0, "amount"] == Decimal("100.105")
    assert str(frame.loc[0, "amount"]) == "100.105"
    assert str(frame.loc[1, "amount"]) == "1250.00"
    assert isinstance(frame.loc[0, "amount"], Decimal)
    assert list(frame["row_number"]) == [2, 3]


def test_ids_are_not_coerced_to_numbers():
    frame = load_platform(to_csv(PLATFORM_HEADER, [ptxn("000123", "10.00")]))
    assert frame.loc[0, "transaction_id"] == "000123"


# --- Scenario 8: missing required columns -----------------------------------

def test_missing_required_columns_lists_them():
    header = [c for c in PLATFORM_HEADER if c not in ("gross_amount", "transaction_date")]
    rows = [{k: v for k, v in ptxn("TXN0001", "10.00").items() if k in header}]
    issues = platform_errors(to_csv(header, rows))
    assert len(issues) == 1
    assert "gross_amount" in issues[0].message and "transaction_date" in issues[0].message
    assert issues[0].dataset == "platform"


def test_bank_file_uploaded_as_platform_is_rejected(bank_bytes):
    issues = platform_errors(bank_bytes)
    assert "Missing required column" in issues[0].message


def test_bank_missing_settlement_amount_column():
    header = [c for c in BANK_HEADER if c != "settlement_amount"]
    rows = [{k: v for k, v in bset("TXN0001", "10.00").items() if k in header}]
    issues = bank_errors(to_csv(header, rows))
    assert "settlement_amount" in issues[0].message


# --- Scenario 7: invalid CSV ------------------------------------------------

@pytest.mark.parametrize("content, fragment", [
    (b"", "empty"),
    (b"   \n\n", "empty"),
    (b"\xff\xfe\x00\x00garbage\x81", "UTF-8"),
    (",".join(PLATFORM_HEADER).encode() + b"\n", "no data rows"),
])
def test_unreadable_or_empty_files(content, fragment):
    issues = platform_errors(content)
    assert fragment in issues[0].message


def test_malformed_row_with_extra_fields():
    content = to_csv(PLATFORM_HEADER, [ptxn("TXN0001", "10.00")]) + b"TXN0002,2026-10-01,PAYMENT,SUCCESS,INR,5.00,UPI,M,C,,EXTRA,MORE\n"
    issues = platform_errors(content)
    assert "Malformed CSV" in issues[0].message


def test_missing_values_are_reported_with_row_and_column():
    row = ptxn("TXN0001", "10.00")
    row["gross_amount"] = ""
    row["transaction_date"] = ""
    issues = platform_errors(to_csv(PLATFORM_HEADER, [ptxn("TXN0000", "1.00"), row]))
    located = {(i.row, i.column) for i in issues}
    assert (3, "gross_amount") in located and (3, "transaction_date") in located


def test_empty_original_transaction_id_is_allowed_for_payments():
    load_platform(to_csv(PLATFORM_HEADER, [ptxn("TXN0001", "10.00", original="")]))


def test_short_row_treated_as_missing_values():
    content = ",".join(PLATFORM_HEADER).encode() + b"\nTXN0001,2026-10-01,PAYMENT\n"
    issues = platform_errors(content)
    assert {"status", "currency", "gross_amount"} <= {i.column for i in issues}


@pytest.mark.parametrize("amount", ["abc", "1,250.00", "1e3", "NaN", "Infinity", "12.5.0", "₹100"])
def test_invalid_amount_formats(amount):
    issues = platform_errors(to_csv(PLATFORM_HEADER, [ptxn("TXN0001", amount)]))
    assert any(i.column == "gross_amount" and "Invalid amount" in i.message for i in issues)


@pytest.mark.parametrize("day", ["2026/10/01", "01-10-2026", "2026-13-01", "2026-02-30", "yesterday"])
def test_invalid_dates(day):
    issues = platform_errors(to_csv(PLATFORM_HEADER, [ptxn("TXN0001", "10.00", day=day)]))
    assert any(i.column == "transaction_date" for i in issues)


def test_sign_convention_enforced():
    rows = [ptxn("TXN0001", "-10.00"), ptxn("TXN0002", "10.00", txn_type="REFUND", original="TXN0001"),
            ptxn("TXN0003", "0.00")]
    messages = {i.row: i.message for i in platform_errors(to_csv(PLATFORM_HEADER, rows))}
    assert "positive" in messages[2] and "negative" in messages[3] and "non-zero" in messages[4]


def test_unknown_enum_values_and_currency():
    row = ptxn("TXN0001", "10.00")
    row.update(transaction_type="CHARGEBACK", status="PENDING", currency="USD")
    columns = {i.column for i in platform_errors(to_csv(PLATFORM_HEADER, [row]))}
    assert {"transaction_type", "status", "currency"} <= columns


def test_bank_amount_with_sub_paise_precision_rejected():
    issues = bank_errors(to_csv(BANK_HEADER, [bset("TXN0001", "100.105")]))
    assert "decimal places" in issues[0].message


def test_all_errors_are_collected_not_just_the_first():
    rows = [ptxn(f"TXN{i:04d}", "bad") for i in range(5)]
    assert len(platform_errors(to_csv(PLATFORM_HEADER, rows))) == 5


def test_whitespace_around_values_is_trimmed():
    row = ptxn("TXN0001", " 10.50 ")
    row["transaction_id"] = " TXN0001 "
    frame = load_platform(to_csv(PLATFORM_HEADER, [row]))
    assert frame.loc[0, "transaction_id"] == "TXN0001"
    assert frame.loc[0, "amount"] == Decimal("10.50")
