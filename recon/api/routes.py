"""API endpoints: the run contract, the run index and the response shapes."""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from starlette.responses import FileResponse

from recon import __version__
from recon.config import Settings
from recon.errors import (
    IngestError,
    LLMError,
    MappingError,
    MatchingError,
    ReconError,
    ReportError,
    ValidationError,
    VerificationError,
)
from recon.ingest.validate import MAX_FILE_SIZE_BYTES, SUPPORTED_SUFFIXES
from recon.llm.base import LLMProvider, build_provider
from recon.llm.explain import is_explainable
from recon.matching.engine import RunResult, run_pipeline
from recon.models import (
    ExplanationSource,
    Finding,
    FindingStatus,
    Severity,
    Transaction,
    format_amount,
)
from recon.report.builder import REPORT_NAME, write_run_artifacts
from recon.synth.generator import generate_dataset

LOGGER = logging.getLogger(__name__)

WEB_RUNS_FOLDER = "web"
DEMO_PROFILE = "easy"
DEMO_SEED = 42
DEMO_BANK = "bank.csv"
DEMO_LEDGER = "ledger.csv"
PROVIDER_NONE = "none"
SEVERITY_ORDER = (Severity.HIGH, Severity.MEDIUM, Severity.LOW)
STEPS = ("parse", "normalize", "match", "investigate", "report")

STATUS_BY_ERROR: dict[type[ReconError], int] = {
    IngestError: 400,
    MappingError: 400,
    MatchingError: 400,
    ValidationError: 422,
    LLMError: 500,
    VerificationError: 500,
    ReportError: 500,
}
STAGE_BY_ERROR: dict[type[ReconError], str] = {
    IngestError: "parse",
    MappingError: "parse",
    ValidationError: "parse",
    MatchingError: "match",
    LLMError: "investigate",
    VerificationError: "investigate",
    ReportError: "report",
}


class ApiProblem(Exception):
    """An endpoint-level failure carried into the documented JSON error shape."""

    def __init__(self, status: int, code: str, message: str, stage: str, **details: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.stage = stage
        self.details = details


@dataclass(frozen=True)
class Upload:
    """One validated upload held in memory before it is staged on disk."""

    label: str
    name: str
    payload: bytes


@dataclass
class StoredRun:
    """A finished web run: its JSON summary and the report written on disk."""

    summary: dict[str, Any]
    report_path: Path


class RunStore:
    """Runs created through the API, keyed by their documented run id."""

    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = Path(reports_dir)
        self._runs: dict[str, StoredRun] = {}

    def put(self, run_id: str, summary: dict[str, Any], report_path: Path) -> None:
        """Remember one run so its summary and report stay addressable."""
        self._runs[run_id] = StoredRun(summary=summary, report_path=report_path)

    def get(self, run_id: str) -> StoredRun | None:
        """Return the stored run for an id, or None when it is unknown."""
        return self._runs.get(run_id)


def lookup_by_class(table: Mapping[type, Any], error: BaseException, default: Any) -> Any:
    """Find a mapping entry for an exception class, honouring its bases."""
    for klass in type(error).__mro__:
        if klass in table:
            return table[klass]
    return default


def error_code(error: ReconError) -> str:
    """Derive a stable snake_case error code from the exception class name."""
    name = type(error).__name__
    return "".join("_" + char.lower() if char.isupper() else char for char in name).lstrip("_")


def parse_column_map(text: str | None) -> dict[str, str] | None:
    """Parse the optional `column_map` form field into a header override."""
    if text is None or not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as cause:
        raise ValidationError(f"column_map is not valid JSON: {cause.msg}") from cause
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
    ):
        raise ValidationError("column_map must be a JSON object of column names to file headers")
    return dict(payload)


def read_upload(upload: UploadFile, label: str) -> Upload:
    """Read one uploaded file and enforce the documented size limit."""
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ApiProblem(
            400, "unsupported_file_type", f"{label} upload must be a CSV or XLSX file", "parse"
        )
    payload = upload.file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(payload) > MAX_FILE_SIZE_BYTES:
        raise ApiProblem(
            422,
            "file_too_large",
            f"{label} file exceeds the {MAX_FILE_SIZE_BYTES} byte limit",
            "parse",
            limit_bytes=MAX_FILE_SIZE_BYTES,
        )
    return Upload(label=label, name=f"{label}{suffix}", payload=payload)


def build_llm_provider(settings: Settings) -> LLMProvider | None:
    """Return the configured explanation provider, or None when the LLM is off."""
    if settings.llm_provider.strip().lower() == PROVIDER_NONE:
        return None
    return build_provider(settings)


def _label(text: str) -> str:
    """Turn a snake_case code value into UI prose casing."""
    return text.replace("_", " ").capitalize()


def _side_total(ids: Iterable[str], records: Mapping[str, Transaction]) -> str | None:
    """Sum one side in minor units and format the total for display.

    An `invalid_record` finding names a rejected row that has no transaction, so a
    side with no resolvable records has no total.
    """
    amounts = [records[identifier].amount_minor for identifier in ids if identifier in records]
    if not amounts:
        return None
    return format_amount(sum(amounts))


def _explanation_cell(finding: Finding) -> dict[str, Any] | None:
    """Project a verified explanation or rationale onto the findings-table cell."""
    explanation = finding.explanation
    if explanation is None:
        return None
    verified = explanation.explanation_source is ExplanationSource.AI_VERIFIED
    return {
        "summary": explanation.summary,
        "likely_cause": explanation.likely_cause,
        "confidence": str(explanation.confidence),
        "recommended_action": str(explanation.recommended_action),
        "source": str(explanation.explanation_source),
        "badge": "Verified" if verified else "Deterministic fallback",
    }


def _finding_row(finding: Finding, records: Mapping[str, Transaction]) -> dict[str, Any]:
    """Serialize one finding for the UI table without raw record contents."""
    return {
        "id": finding.id,
        "type": str(finding.type),
        "type_label": _label(str(finding.type)),
        "status": str(finding.status),
        "severity": str(finding.severity),
        "severity_label": _label(str(finding.severity)),
        "rule": f"{finding.rule_id} v{finding.rule_version}",
        "ledger_ids": list(finding.ledger_ids),
        "bank_ids": list(finding.bank_ids),
        "ledger_total": _side_total(finding.ledger_ids, records),
        "bank_total": _side_total(finding.bank_ids, records),
        "score": finding.score,
        "explanation": _explanation_cell(finding),
    }


def _totals(findings: Sequence[Finding]) -> dict[str, int]:
    """Count the five KPI values named in Design section 5."""
    explained = [finding for finding in findings if is_explainable(finding)]
    matched = sum(1 for finding in findings if finding.status is FindingStatus.MATCHED)

    def _count(source: ExplanationSource) -> int:
        return sum(
            1
            for finding in explained
            if finding.explanation is not None and finding.explanation.explanation_source is source
        )

    return {
        "matched": matched,
        "discrepancies": len(findings) - matched,
        "high_severity": sum(1 for finding in findings if finding.severity is Severity.HIGH),
        "ai_verified": _count(ExplanationSource.AI_VERIFIED),
        "fallback": _count(ExplanationSource.DETERMINISTIC_FALLBACK),
    }


def _filters(findings: Sequence[Finding]) -> dict[str, list[str]]:
    """List the filter values present in this run in a fixed order."""
    types = sorted({str(finding.type) for finding in findings})
    present = {str(finding.severity) for finding in findings}
    severities = [str(severity) for severity in SEVERITY_ORDER if str(severity) in present]
    return {"types": types, "severities": severities}


def run_summary(result: RunResult, report_url: str) -> dict[str, Any]:
    """Build the JSON body both run endpoints return for one finished run."""
    records = result.records_by_id
    meta = result.meta
    return {
        "run_id": result.run_id,
        "report_url": report_url,
        "created_at": meta["created_at"],
        "tool_version": meta["tool_version"],
        "config_hash": meta["config_hash"],
        "inputs": meta["inputs"],
        "llm": meta["llm"],
        "validation_issues": meta["validation_issues"],
        "totals": _totals(result.findings),
        "filters": _filters(result.findings),
        "findings": [_finding_row(finding, records) for finding in result.findings],
    }


def stage_uploads(uploads: Iterable[Upload], staging: Path) -> list[Path]:
    """Write each upload into the staging folder and return the paths in order."""
    paths: list[Path] = []
    for upload in uploads:
        path = staging / upload.name
        path.write_bytes(upload.payload)
        paths.append(path)
    return paths


def execute_run(
    store: RunStore,
    settings: Settings,
    uploads: Sequence[Upload],
    column_map: Mapping[str, str] | None,
) -> dict[str, Any]:
    """Stage one file pair, run the pipeline once and write its run artifacts."""
    provider = build_llm_provider(settings)
    with tempfile.TemporaryDirectory(prefix="recon-web-") as staging:
        paths = stage_uploads(uploads, Path(staging))
        result = run_pipeline(
            paths[0], paths[1], settings, column_map=column_map, provider=provider
        )
        out_dir = store.reports_dir / WEB_RUNS_FOLDER / result.run_id
        write_run_artifacts(out_dir, result)
    report_path = out_dir / REPORT_NAME
    summary = run_summary(result, f"/api/runs/{result.run_id}/report")
    store.put(result.run_id, summary, report_path)
    LOGGER.info(
        "web_run run_id=%s findings=%d llm=%s",
        result.run_id,
        len(result.findings),
        summary["llm"]["provider"],
    )
    return summary


def demo_uploads() -> list[Upload]:
    """Generate the seeded demo pair in a scratch folder and read it back."""
    with tempfile.TemporaryDirectory(prefix="recon-demo-") as scratch:
        dataset = generate_dataset(DEMO_PROFILE, DEMO_SEED, Path(scratch) / "demo")
        return [
            Upload(label, name, (dataset / name).read_bytes())
            for label, name in (("bank", DEMO_BANK), ("ledger", DEMO_LEDGER))
        ]


def build_router(store: RunStore, settings: Settings) -> APIRouter:
    """Build the `/api` router bound to one run index and settings snapshot."""
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, Any]:
        """Report that the service is up and which explanation provider runs use."""
        return {
            "status": "ok",
            "tool_version": __version__,
            "llm_provider": settings.llm_provider,
        }

    @router.post("/run")
    def run(
        bank: UploadFile = File(...),
        ledger: UploadFile = File(...),
        column_map: str | None = Form(None),
    ) -> JSONResponse:
        """Reconcile one uploaded bank and ledger file pair."""
        summary = execute_run(
            store,
            settings,
            [read_upload(bank, "bank"), read_upload(ledger, "ledger")],
            parse_column_map(column_map),
        )
        return JSONResponse(summary)

    @router.post("/demo")
    def demo() -> JSONResponse:
        """Reconcile the seeded synthetic demo pair."""
        return JSONResponse(execute_run(store, settings, demo_uploads(), None))

    @router.get("/runs/{run_id}")
    def run_detail(run_id: str) -> JSONResponse:
        """Return the stored summary for one finished run."""
        stored = store.get(run_id)
        if stored is None:
            raise ApiProblem(
                404, "run_not_found", f"unknown run id: {run_id}", "report", run_id=run_id
            )
        return JSONResponse(stored.summary)

    @router.get("/runs/{run_id}/report")
    def run_report(run_id: str) -> FileResponse:
        """Serve the self-contained audit report of one finished run."""
        stored = store.get(run_id)
        if stored is None:
            raise ApiProblem(
                404, "run_not_found", f"unknown run id: {run_id}", "report", run_id=run_id
            )
        if not stored.report_path.exists():
            raise ApiProblem(
                404,
                "report_not_found",
                f"report missing for run id: {run_id}",
                "report",
                run_id=run_id,
            )
        return FileResponse(stored.report_path, media_type="text/html")

    return router
