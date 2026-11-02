"""Run artifacts: findings JSON, run metadata, audit trail, verifier log and the report."""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from recon.errors import ReportError
from recon.evidence.packet import RULE_DESCRIPTIONS
from recon.llm.explain import is_explainable
from recon.llm.verifier import write_verifier_log
from recon.matching.engine import RULES, RunResult
from recon.models import (
    ExplanationSource,
    Finding,
    FindingStatus,
    Severity,
    Transaction,
    format_amount,
)
from recon.report.audit import AUDIT_TRAIL_NAME, audit_events, write_audit_trail

LOGGER = logging.getLogger(__name__)
JSON_SUFFIX = ".json"
VERIFIER_LOG_NAME = "verifier_log.jsonl"
REPORT_NAME = "report.html"
MINOR_SUFFIX = "_minor"
PRODUCT_NAME = "Recon Investigator"
METHOD_STATEMENT = (
    "Matches and discrepancies in this report were decided by deterministic rules. "
    "AI-generated explanations were checked by an automated verifier; any explanation "
    "that failed verification was replaced by a deterministic fallback."
)
SEVERITY_ORDER: tuple[Severity, ...] = (Severity.HIGH, Severity.MEDIUM, Severity.LOW)
TOKENS_PATH = Path(__file__).resolve().parent.parent / "assets" / "tokens.css"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def write_json(path: Path, payload: Any) -> Path:
    """Write one deterministic, pretty-printed JSON artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    try:
        path.write_text(f"{text}\n", encoding="utf-8")
    except OSError as error:
        raise ReportError(f"could not write artifact: {path.name}") from error
    return path


def findings_payload(result: RunResult) -> list[dict[str, Any]]:
    """Serialize findings in their stable order for `findings.json`."""
    return [finding.model_dump(mode="json") for finding in result.findings]


def _label(text: str) -> str:
    """Turn a snake_case code value into report prose casing."""
    return text.replace("_", " ").capitalize()


def _record_cell(identifier: str, records: Mapping[str, Transaction]) -> dict[str, Any]:
    """Project one record ID onto the finding card's evidence row."""
    record = records.get(identifier)
    if record is None:
        return {"id": identifier, "unavailable": True}
    return {
        "id": record.id,
        "unavailable": False,
        "row_number": record.row_number,
        "date": record.date.isoformat(),
        "amount": format_amount(record.amount_minor),
        "currency": record.currency,
        "reference": record.reference_norm or record.reference_raw,
        "description": record.description_raw,
    }


def _side_rows(
    identifiers: Sequence[str], records: Mapping[str, Transaction]
) -> list[dict[str, Any]]:
    """Build the evidence rows for one side of a finding."""
    return [_record_cell(identifier, records) for identifier in identifiers]


def _side_total(identifiers: Sequence[str], records: Mapping[str, Transaction]) -> str:
    """Sum one side's minor units and format the total as money."""
    amounts = [
        records[identifier].amount_minor for identifier in identifiers if identifier in records
    ]
    return format_amount(sum(amounts)) if amounts else ""


def _fact_value(value: Any) -> str:
    """Render one fact or setting value as report text without touching money."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, Mapping):
        return ", ".join(f"{key}={_fact_value(item)}" for key, item in sorted(value.items()))
    if isinstance(value, (list, tuple)):
        if all(isinstance(item, (list, tuple)) for item in value):
            return " or ".join(" + ".join(_fact_value(item) for item in group) for group in value)
        return ", ".join(_fact_value(item) for item in value)
    return str(value)


def _fact_rows(facts: Mapping[str, Any], prefix: str = "") -> list[dict[str, str]]:
    """Flatten a finding's facts into sorted label and value pairs."""
    rows: list[dict[str, str]] = []
    for name in sorted(facts):
        value = facts[name]
        key = f"{prefix}{name}"
        if name.endswith(MINOR_SUFFIX):
            label = key[: -len(MINOR_SUFFIX)].replace("_", " ")
            rows.append({"label": label, "value": format_amount(int(value))})
        elif isinstance(value, Mapping):
            rows.extend(_fact_rows(value, prefix=f"{key}."))
        else:
            rows.append({"label": key.replace("_", " "), "value": _fact_value(value)})
    return rows


def _explanation_box(finding: Finding) -> dict[str, Any] | None:
    """Describe the verified explanation or deterministic rationale attached to a finding."""
    explanation = finding.explanation
    if explanation is None:
        return None
    fallback = explanation.explanation_source is ExplanationSource.DETERMINISTIC_FALLBACK
    return {
        "kind": "deterministic" if fallback else "ai",
        "badge": "Deterministic fallback" if fallback else "Verified",
        "label": "Deterministic rationale" if fallback else "AI explanation",
        "summary": explanation.summary,
        "cause": _label(explanation.likely_cause),
        "text": explanation.explanation,
        "cited": [{"field": fact.field, "value": fact.value} for fact in explanation.cited_facts],
        "action": _label(str(explanation.recommended_action)),
        "action_detail": explanation.action_detail,
        "confidence": _label(str(explanation.confidence)),
        "uncertainties": list(explanation.uncertainties),
    }


def _card(finding: Finding, records: Mapping[str, Transaction]) -> dict[str, Any]:
    """Build one finding card: evidence, rule line, facts, then the explanation box."""
    return {
        "id": finding.id,
        "type": str(finding.type),
        "type_label": _label(str(finding.type)),
        "status": str(finding.status),
        "status_label": _label(str(finding.status)),
        "severity": str(finding.severity),
        "severity_label": _label(str(finding.severity)),
        "severity_class": _severity_class(finding),
        "rule": {
            "id": finding.rule_id,
            "version": finding.rule_version,
            "description": RULE_DESCRIPTIONS[finding.rule_id],
        },
        "score": None if finding.score is None else f"{finding.score:.4f}",
        "ledger": _side_rows(finding.ledger_ids, records),
        "bank": _side_rows(finding.bank_ids, records),
        "facts": _fact_rows(finding.facts),
        "explanation": _explanation_box(finding),
    }


def _severity_class(finding: Finding) -> str:
    """Map a finding onto the Design section 2 status colour pair."""
    if str(finding.status) == str(FindingStatus.MATCHED):
        return "matched"
    if finding.severity is Severity.HIGH:
        return "danger"
    if finding.severity is Severity.MEDIUM:
        return "warning"
    return "info"


def _match_row(finding: Finding, records: Mapping[str, Transaction]) -> dict[str, Any]:
    """Build one compact row of the matched items table."""
    return {
        "id": finding.id,
        "type": str(finding.type),
        "rule": finding.rule_id,
        "ledger_ids": finding.ledger_ids,
        "bank_ids": finding.bank_ids,
        "ledger_total": _side_total(finding.ledger_ids, records),
        "bank_total": _side_total(finding.bank_ids, records),
        "score": None if finding.score is None else f"{finding.score:.4f}",
    }


def _finding_groups(
    findings: Sequence[Finding], records: Mapping[str, Transaction]
) -> list[dict[str, Any]]:
    """Group every non-matched finding by severity, then by type."""
    unmatched = [finding for finding in findings if finding.status is not FindingStatus.MATCHED]
    groups: list[dict[str, Any]] = []
    for severity in SEVERITY_ORDER:
        by_severity = sorted(
            (finding for finding in unmatched if finding.severity is severity),
            key=lambda finding: (str(finding.type), finding.id),
        )
        sections = [
            {
                "type": name,
                "type_label": _label(name),
                "cards": [
                    _card(finding, records) for finding in by_severity if str(finding.type) == name
                ],
            }
            for name in sorted({str(finding.type) for finding in by_severity})
        ]
        if sections:
            groups.append(
                {
                    "severity": str(severity),
                    "severity_label": _label(str(severity)),
                    "sections": sections,
                }
            )
    return groups


def _type_counts(findings: Sequence[Finding]) -> list[dict[str, Any]]:
    """Count findings per type and status for the summary table."""
    counts = Counter((str(finding.status), str(finding.type)) for finding in findings)
    return [
        {
            "status": _label(status),
            "type": name,
            "type_label": _label(name),
            "count": counts[(status, name)],
        }
        for status, name in sorted(counts)
    ]


def _source_count(items: Sequence[Finding], source: ExplanationSource) -> int:
    """Count findings explained by one explanation source."""
    return sum(
        1
        for finding in items
        if finding.explanation is not None and finding.explanation.explanation_source is source
    )


def _kpis(findings: Sequence[Finding]) -> list[dict[str, Any]]:
    """Build the five summary counts named in Design section 5."""
    explained = [finding for finding in findings if is_explainable(finding)]
    matched = sum(1 for finding in findings if finding.status is FindingStatus.MATCHED)
    return [
        {"label": "Matched", "value": matched},
        {"label": "Discrepancies", "value": len(findings) - matched},
        {
            "label": "High severity",
            "value": sum(1 for finding in findings if finding.severity is Severity.HIGH),
        },
        {"label": "AI verified", "value": _source_count(explained, ExplanationSource.AI_VERIFIED)},
        {
            "label": "Verifier fallback",
            "value": _source_count(explained, ExplanationSource.DETERMINISTIC_FALLBACK),
        },
    ]


def _timestamp(text: str) -> str:
    """Render the run's UTC instant as a readable stamp for the title block."""
    return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M:%S UTC")


def _mapping_rows(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    """Render a flat mapping as sorted label and value rows."""
    return [
        {"label": str(key), "value": _fact_value(value)} for key, value in sorted(payload.items())
    ]


def _input_rows(meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Describe both input files with their hashes and row counts."""
    return [
        {
            "source": _label(name),
            "file": data["file"],
            "sha256": data["sha256"],
            "valid_rows": data["valid_rows"],
            "invalid_rows": data["invalid_rows"],
            "column_map": _mapping_rows(data["column_map"]),
        }
        for name, data in sorted(meta["inputs"].items())
    ]


def _rule_rows() -> list[dict[str, str]]:
    """List every rule identity used by the engine with its description."""
    identities = sorted({(rule_id, version) for rule_id, version in RULES.values()})
    return [
        {
            "id": rule_id,
            "version": version,
            "description": RULE_DESCRIPTIONS.get(rule_id, ""),
        }
        for rule_id, version in identities
    ]


def report_context(result: RunResult) -> dict[str, Any]:
    """Assemble every value the report template renders from a finished run."""
    meta = result.meta
    records = result.records_by_id
    matched = [finding for finding in result.findings if finding.status is FindingStatus.MATCHED]
    findings = result.findings
    return {
        "product_name": PRODUCT_NAME,
        "run_id": meta["run_id"],
        "created_at": _timestamp(meta["created_at"]),
        "tool_version": meta["tool_version"],
        "method_statement": METHOD_STATEMENT,
        "inputs": _input_rows(meta),
        "kpis": _kpis(findings),
        "type_counts": _type_counts(findings),
        "validation_issues": meta["validation_issues"],
        "finding_count": len(findings),
        "groups": _finding_groups(findings, records),
        "matches": [_match_row(finding, records) for finding in matched],
        "llm": _mapping_rows(meta["llm"]),
        "config": _mapping_rows(meta["config"]),
        "config_hash": meta["config_hash"],
        "rules": _rule_rows(),
        "tokens": TOKENS_PATH.read_text(encoding="utf-8"),
    }


def render_report(result: RunResult) -> str:
    """Render the self-contained, printable HTML report for one run."""
    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    try:
        return environment.get_template("report.html.j2").render(report_context(result))
    except OSError as error:
        raise ReportError("could not read the report template or design tokens") from error


def write_report(out_dir: Path, result: RunResult) -> Path:
    """Write `report.html` as one self-contained file."""
    path = out_dir / REPORT_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_report(result), encoding="utf-8")
    except OSError as error:
        raise ReportError(f"could not write artifact: {path.name}") from error
    LOGGER.info("report_written run_id=%s file=%s", result.run_id, path.name)
    return path


def write_run_artifacts(out_dir: Path, result: RunResult) -> list[Path]:
    """Write every documented artifact for one completed run."""
    written = [
        write_json(out_dir / f"findings{JSON_SUFFIX}", findings_payload(result)),
        write_json(out_dir / f"run_meta{JSON_SUFFIX}", result.meta),
        write_audit_trail(out_dir / AUDIT_TRAIL_NAME, audit_events(result)),
    ]
    if result.verifier_records:
        path = out_dir / VERIFIER_LOG_NAME
        write_verifier_log(path, result.verifier_records, truncate=True)
        written.append(path)
    written.append(write_report(out_dir, result))
    LOGGER.info("artifacts_written run_id=%s files=%d", result.run_id, len(written))
    return written
