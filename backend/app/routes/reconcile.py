"""HTTP routes. Thin layer: read uploads, parse parameters, delegate to the reconciler."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.config import DEFAULT_MATERIALITY_THRESHOLD, MAX_REPORTED_VALIDATION_ERRORS, MAX_UPLOAD_BYTES
from app.models import ReconciliationReport, ValidationErrorResponse, ValidationIssue
from app.services.csv_loader import CSVValidationError, load_bank, load_platform
from app.services.reconciler import reconcile

router = APIRouter(prefix="/api")


def _error_response(message: str, issues: list[ValidationIssue], status: int = 422) -> JSONResponse:
    body = ValidationErrorResponse(
        message=message,
        total_errors=len(issues),
        errors=issues[:MAX_REPORTED_VALIDATION_ERRORS],
    )
    return JSONResponse(status_code=status, content={"detail": body.model_dump(mode="json")})


async def _read_upload(upload: UploadFile, dataset: str, issues: list[ValidationIssue]) -> bytes | None:
    if upload.filename and not upload.filename.lower().endswith(".csv"):
        issues.append(ValidationIssue(dataset=dataset, message=f"'{upload.filename}' is not a .csv file."))
        return None
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        issues.append(ValidationIssue(dataset=dataset,
                                      message=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."))
        return None
    return content


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post(
    "/reconcile",
    response_model=ReconciliationReport,
    responses={422: {"model": ValidationErrorResponse}},
)
async def run_reconciliation(
    platform_file: UploadFile = File(..., description="platform_transactions CSV"),
    bank_file: UploadFile = File(..., description="bank_settlements CSV"),
    cutoff_date: str | None = Form(None, description="YYYY-MM-DD; defaults to month-end of latest transaction"),
    materiality_threshold: str | None = Form(None, description="Aggregate rounding threshold in INR"),
):
    issues: list[ValidationIssue] = []

    cutoff: date | None = None
    if cutoff_date:
        try:
            cutoff = date.fromisoformat(cutoff_date.strip())
        except ValueError:
            issues.append(ValidationIssue(dataset="parameters", column="cutoff_date", value=cutoff_date,
                                          message="Invalid cutoff date; expected YYYY-MM-DD."))

    threshold = DEFAULT_MATERIALITY_THRESHOLD
    if materiality_threshold:
        try:
            threshold = Decimal(materiality_threshold.strip())
            if not threshold.is_finite() or threshold < 0:
                raise InvalidOperation
        except InvalidOperation:
            issues.append(ValidationIssue(dataset="parameters", column="materiality_threshold",
                                          value=materiality_threshold,
                                          message="Materiality threshold must be a non-negative number."))

    # Validate both files before failing so the user sees every problem at once.
    platform = bank = None
    platform_bytes = await _read_upload(platform_file, "platform", issues)
    bank_bytes = await _read_upload(bank_file, "bank", issues)
    if platform_bytes is not None:
        try:
            platform = load_platform(platform_bytes)
        except CSVValidationError as exc:
            issues.extend(exc.issues)
    if bank_bytes is not None:
        try:
            bank = load_bank(bank_bytes)
        except CSVValidationError as exc:
            issues.extend(exc.issues)

    if issues:
        return _error_response("Upload validation failed. No reconciliation was performed.", issues)

    return reconcile(platform, bank, cutoff, threshold)
