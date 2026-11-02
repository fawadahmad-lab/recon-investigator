"""Audit trail: one JSONL event per pipeline step, derived from a finished run."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from recon.errors import ReportError
from recon.matching.engine import RunResult
from recon.models import Source

LOGGER = logging.getLogger(__name__)

STEP_INGEST = "ingest"
STEP_NORMALIZE = "normalize"
STEP_RULE = "rule"
STEP_LLM_ATTEMPT = "llm_attempt"
SOURCE_ORDER: tuple[str, str] = (str(Source.BANK), str(Source.LEDGER))
AUDIT_TRAIL_NAME = "audit_trail.jsonl"
RAW_FIELD = "raw"


def _ingest_events(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Record one ingest event per input file with its SHA-256 and row totals."""
    events: list[dict[str, Any]] = []
    for name in SOURCE_ORDER:
        inputs: dict[str, Any] = meta["inputs"][name]
        valid = int(inputs["valid_rows"])
        invalid = int(inputs["invalid_rows"])
        events.append(
            {
                "step": STEP_INGEST,
                "run_id": meta["run_id"],
                "source": name,
                "file": inputs["file"],
                "sha256": inputs["sha256"],
                "rows_total": valid + invalid,
                "column_map": dict(sorted(inputs["column_map"].items())),
            }
        )
    return events


def _normalize_events(result: RunResult) -> list[dict[str, Any]]:
    """Record one normalize event per source, naming every excluded row."""
    events: list[dict[str, Any]] = []
    for name in SOURCE_ORDER:
        issues = sorted(
            (issue for issue in result.issues if str(issue.source) == name),
            key=lambda issue: issue.row_number,
        )
        events.append(
            {
                "step": STEP_NORMALIZE,
                "run_id": result.run_id,
                "source": name,
                "valid_rows": len(result.bank if name == str(Source.BANK) else result.ledger),
                "invalid_rows": len(issues),
                "excluded_rows": [
                    {"row_number": issue.row_number, "code": issue.code, "message": issue.message}
                    for issue in issues
                ],
            }
        )
    return events


def _rule_events(result: RunResult) -> list[dict[str, Any]]:
    """Record one event per rule application, in the run's stable finding order."""
    return [
        {
            "step": STEP_RULE,
            "run_id": result.run_id,
            "rule_id": finding.rule_id,
            "rule_version": finding.rule_version,
            "finding_id": finding.id,
            "finding_type": str(finding.type),
            "status": str(finding.status),
            "severity": str(finding.severity),
            "ledger_ids": list(finding.ledger_ids),
            "bank_ids": list(finding.bank_ids),
            "score": finding.score,
            "explanation_source": (
                None if finding.explanation is None else str(finding.explanation.explanation_source)
            ),
        }
        for finding in result.findings
    ]


def _llm_events(result: RunResult) -> list[dict[str, Any]]:
    """Record each provider attempt and verifier verdict, without the raw answer."""
    events: list[dict[str, Any]] = []
    for record in result.verifier_records:
        events.append(
            {
                "step": STEP_LLM_ATTEMPT,
                "run_id": result.run_id,
                **{key: value for key, value in record.items() if key != RAW_FIELD},
            }
        )
    return events


def audit_events(result: RunResult) -> list[dict[str, Any]]:
    """Build the documented audit sequence: ingest, normalize, rules, LLM attempts."""
    events = [*_ingest_events(result.meta), *_normalize_events(result)]
    events.extend(_rule_events(result))
    events.extend(_llm_events(result))
    LOGGER.info("audit_events_built run_id=%s events=%d", result.run_id, len(events))
    return events


def audit_trail_lines(events: list[dict[str, Any]]) -> str:
    """Render audit events as canonical JSONL text."""
    return "".join(f"{json.dumps(event, sort_keys=True, default=str)}\n" for event in events)


def write_audit_trail(path: Path, events: list[dict[str, Any]]) -> Path:
    """Write the audit trail for one run as one JSON object per line."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(audit_trail_lines(events), encoding="utf-8")
    except OSError as error:
        raise ReportError(f"could not write artifact: {path.name}") from error
    return path
