"""HTTP layer: uploads, parameters, error format, JSON precision."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PLATFORM_HEADER, ptxn, to_csv


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def post(client, platform: bytes, bank: bytes, platform_name="platform.csv", bank_name="bank.csv", **form):
    return client.post(
        "/api/reconcile",
        files={"platform_file": (platform_name, platform, "text/csv"),
               "bank_file": (bank_name, bank, "text/csv")},
        data=form,
    )


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_reconcile_dataset_end_to_end(client, platform_bytes, bank_bytes):
    response = post(client, platform_bytes, bank_bytes, cutoff_date="2026-10-31")
    assert response.status_code == 200
    body = response.json()
    # Decimals are serialised as strings with source precision intact.
    assert body["summary"]["aggregate_platform_amount"] == "213946.540"
    assert body["summary"]["total_variance"] == "1250.120"
    assert body["summary"]["variance_at_cutoff"] == "6000.120"
    assert body["parameters"]["cutoff_date"] == "2026-10-31"
    assert body["parameters"]["materiality_threshold"] == "0.10"
    sub_paise = [d for d in body["discrepancies"] if d["issue_type"] == "SUB_PAISE_VARIANCE"]
    assert sub_paise[0]["platform_amount"] == "100.105"


def test_invalid_csv_returns_422_with_details(client, bank_bytes):
    response = post(client, b"\x00\x81not,a\ncsv", bank_bytes)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["total_errors"] >= 1
    assert detail["errors"][0]["dataset"] == "platform"


def test_missing_columns_returns_422(client, bank_bytes):
    content = to_csv(PLATFORM_HEADER[:3], [{k: v for k, v in ptxn("TXN1", "1.00").items() if k in PLATFORM_HEADER[:3]}])
    response = post(client, content, bank_bytes)
    assert response.status_code == 422
    assert "Missing required column" in response.json()["detail"]["errors"][0]["message"]


def test_errors_from_both_files_reported_together(client):
    response = post(client, b"", b"")
    datasets = {e["dataset"] for e in response.json()["detail"]["errors"]}
    assert datasets == {"platform", "bank"}


def test_files_swapped_are_rejected(client, platform_bytes, bank_bytes):
    response = post(client, bank_bytes, platform_bytes)
    assert response.status_code == 422
    assert {e["dataset"] for e in response.json()["detail"]["errors"]} == {"platform", "bank"}


def test_non_csv_extension_rejected(client, platform_bytes, bank_bytes):
    response = post(client, platform_bytes, bank_bytes, platform_name="platform.xlsx")
    assert response.status_code == 422
    assert ".csv" in response.json()["detail"]["errors"][0]["message"]


@pytest.mark.parametrize("form, column", [
    ({"cutoff_date": "31/10/2026"}, "cutoff_date"),
    ({"materiality_threshold": "-1"}, "materiality_threshold"),
    ({"materiality_threshold": "abc"}, "materiality_threshold"),
])
def test_invalid_parameters(client, platform_bytes, bank_bytes, form, column):
    response = post(client, platform_bytes, bank_bytes, **form)
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["column"] == column


def test_missing_file_field(client, platform_bytes):
    response = client.post("/api/reconcile", files={"platform_file": ("p.csv", platform_bytes, "text/csv")})
    assert response.status_code == 422
