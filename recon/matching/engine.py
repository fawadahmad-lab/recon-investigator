"""Deterministic matching engine: rule steps 1 to 8 and stable finding output."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from recon import __version__
from recon.config import Settings, get_settings
from recon.ingest.column_map import ColumnMap
from recon.ingest.loaders import load_file
from recon.llm.base import LLMProvider
from recon.llm.explain import explain_findings
from recon.matching.classify import (
    ClassifiedPair,
    classify_amount_differences,
    classify_date_mismatches,
)
from recon.matching.duplicates import DuplicateFinding, detect_duplicates
from recon.matching.exact import ExactMatch, match_exact
from recon.matching.fuzzy import FuzzyMatch, fuzzy_components, match_fuzzy
from recon.matching.keys import date_difference_days
from recon.matching.split import AmbiguousSplit, SplitMatch, match_splits
from recon.models import (
    Finding,
    FindingStatus,
    FindingType,
    Severity,
    Source,
    Transaction,
    ValidationIssue,
)
from recon.normalize.pipeline import NormalizationResult, normalize_frame

LOGGER = logging.getLogger(__name__)

RULES: dict[str, tuple[str, str]] = {
    "match_exact": ("R1-EXACT", "1"),
    "match_fuzzy": ("R2-FUZZY", "1"),
    "duplicate_in_ledger": ("R3-DUP", "1"),
    "duplicate_in_bank": ("R3-DUP", "1"),
    "amount_mismatch": ("R4-AMT", "1"),
    "fee_difference": ("R4-AMT", "1"),
    "date_mismatch": ("R5-DATE", "1"),
    "match_split": ("R6-SPLIT", "1"),
    "ambiguous_split": ("R6-SPLIT", "1"),
    "missing_in_bank": ("R7-MISSING", "1"),
    "missing_in_ledger": ("R7-MISSING", "1"),
    "invalid_record": ("R0-INVALID", "1"),
}
SEVERITY_RANK = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
STATUS_BY_TYPE: dict[str, FindingStatus] = {
    "match_exact": FindingStatus.MATCHED,
    "match_fuzzy": FindingStatus.MATCHED,
    "match_split": FindingStatus.MATCHED,
    "ambiguous_split": FindingStatus.NEEDS_REVIEW,
}


@dataclass(frozen=True)
class MatchingOutcome:
    """Findings in stable order plus the records that produced them."""

    findings: list[Finding]
    ledger: list[Transaction]
    bank: list[Transaction]
    issues: list[ValidationIssue]


def _severity(amounts: list[int], settings: Settings) -> Severity:
    """Rank severity from the largest absolute amount in a finding."""
    peak = max((abs(value) for value in amounts), default=0)
    if peak >= settings.severity_high_minor:
        return Severity.HIGH
    if peak >= settings.severity_medium_minor:
        return Severity.MEDIUM
    return Severity.LOW


def _status(finding_type: str) -> FindingStatus:
    """Map a deterministic finding type onto its report status."""
    return STATUS_BY_TYPE.get(finding_type, FindingStatus.DISCREPANCY)


def _finding(
    finding_type: str,
    ledger_ids: list[str],
    bank_ids: list[str],
    facts: dict[str, Any],
    amounts: list[int],
    settings: Settings,
    score: float | None = None,
) -> Finding:
    """Build one finding with its configured rule identity and severity."""
    rule_id, rule_version = RULES[finding_type]
    return Finding(
        id="pending",
        type=FindingType(finding_type),
        status=_status(finding_type),
        ledger_ids=ledger_ids,
        bank_ids=bank_ids,
        rule_id=rule_id,
        rule_version=rule_version,
        score=score,
        facts=facts,
        severity=_severity(amounts, settings),
    )


def _exact_findings(matches: list[ExactMatch], settings: Settings) -> list[Finding]:
    """Report Tier 1 matches with their date-distance evidence."""
    return [
        _finding(
            "match_exact",
            [item.ledger.id],
            [item.bank.id],
            {
                "date_difference_days": item.date_difference_days,
                "amount_minor": item.bank.amount_minor,
                "currency": item.bank.currency,
                "reference_norm": item.bank.reference_norm,
            },
            [item.ledger.amount_minor, item.bank.amount_minor],
            settings,
        )
        for item in matches
    ]


def _fuzzy_findings(matches: list[FuzzyMatch], settings: Settings) -> list[Finding]:
    """Report Tier 2 matches with their transparent score components."""
    findings: list[Finding] = []
    for item in matches:
        reference, description, date = fuzzy_components(
            item.ledger, item.bank, settings.date_window_fuzzy_days
        )
        findings.append(
            _finding(
                "match_fuzzy",
                [item.ledger.id],
                [item.bank.id],
                {
                    "date_difference_days": date_difference_days(item.ledger.date, item.bank.date),
                    "score_components": {
                        "reference": round(reference, 4),
                        "description": round(description, 4),
                        "date": round(date, 4),
                    },
                },
                [item.ledger.amount_minor, item.bank.amount_minor],
                settings,
                score=round(item.score, 4),
            )
        )
    return findings


def _duplicate_findings(items: list[DuplicateFinding], settings: Settings) -> list[Finding]:
    """Report duplicates linked to their same-source matched primary."""
    return [
        _finding(
            item.type,
            [item.duplicate.id] if item.duplicate.source is Source.LEDGER else [],
            [item.duplicate.id] if item.duplicate.source is Source.BANK else [],
            {
                "primary_id": item.primary.id,
                "source": str(item.duplicate.source),
                "date_difference_days": date_difference_days(
                    item.duplicate.date, item.primary.date
                ),
            },
            [item.duplicate.amount_minor, item.primary.amount_minor],
            settings,
        )
        for item in items
    ]


def _pair_findings(pairs: list[ClassifiedPair], settings: Settings) -> list[Finding]:
    """Report amount, fee, and date classifications with their measured difference."""
    findings: list[Finding] = []
    for pair in pairs:
        facts: dict[str, Any] = {
            "ledger_amount_minor": pair.ledger.amount_minor,
            "bank_amount_minor": pair.bank.amount_minor,
        }
        if pair.amount_difference_minor is not None:
            facts["amount_difference_minor"] = pair.amount_difference_minor
        if pair.date_difference_days is not None:
            facts["date_difference_days"] = pair.date_difference_days
        findings.append(
            _finding(
                pair.type,
                [pair.ledger.id],
                [pair.bank.id],
                facts,
                [pair.ledger.amount_minor, pair.bank.amount_minor],
                settings,
                score=None if pair.score is None else round(pair.score, 4),
            )
        )
    return findings


def _side_ids(anchor: Transaction, records: list[Transaction]) -> tuple[list[str], list[str]]:
    """Split record IDs into ledger and bank sides with the anchor included."""
    ledger_ids = [row.id for row in records if row.source is Source.LEDGER]
    bank_ids = [row.id for row in records if row.source is Source.BANK]
    if anchor.source is Source.LEDGER:
        return [anchor.id, *ledger_ids], bank_ids
    return ledger_ids, [anchor.id, *bank_ids]


def _split_findings(
    matches: list[SplitMatch],
    ambiguous: list[AmbiguousSplit],
    records_by_id: dict[str, Transaction],
    settings: Settings,
) -> list[Finding]:
    """Report unique split matches and every ambiguity with its listed candidate sets."""
    findings: list[Finding] = []
    for item in matches:
        part_ids = [part.id for part in item.parts]
        ledger_ids, bank_ids = _side_ids(item.anchor, list(item.parts))
        amounts = [item.anchor.amount_minor, *(part.amount_minor for part in item.parts)]
        findings.append(
            _finding(
                "match_split",
                ledger_ids,
                bank_ids,
                {
                    "anchor_id": item.anchor.id,
                    "part_ids": part_ids,
                    "part_count": len(item.parts),
                    "difference_minor": item.difference_minor,
                },
                amounts,
                settings,
                score=item.average_similarity,
            )
        )
    for item in ambiguous:
        candidates = [
            records_by_id[identifier]
            for identifier in sorted(
                {id_ for candidate in item.candidate_sets for id_ in candidate}
            )
        ]
        ledger_ids, bank_ids = _side_ids(item.anchor, candidates)
        amounts = [item.anchor.amount_minor, *(row.amount_minor for row in candidates)]
        findings.append(
            _finding(
                "ambiguous_split",
                ledger_ids,
                bank_ids,
                {
                    "anchor_id": item.anchor.id,
                    "candidate_sets": [list(candidate) for candidate in item.candidate_sets],
                    "solution_count_listed": len(item.candidate_sets),
                },
                amounts,
                settings,
            )
        )
    return findings


def _missing_findings(
    ledger: list[Transaction],
    bank: list[Transaction],
    truncated: list[Transaction],
    reported_ids: set[str],
    settings: Settings,
) -> list[Finding]:
    """Report each remaining unreported record, flagging truncated split searches."""
    truncated_ids = {row.id for row in truncated}
    findings: list[Finding] = []
    for finding_type, rows in (
        ("missing_in_bank", ledger),
        ("missing_in_ledger", bank),
    ):
        source = Source.LEDGER if finding_type == "missing_in_bank" else Source.BANK
        for row in rows:
            if row.id in reported_ids:
                continue
            facts: dict[str, Any] = {"unmatched_source": str(source)}
            if row.id in truncated_ids:
                facts["split_search_truncated"] = True
            findings.append(
                _finding(
                    finding_type,
                    [row.id] if source is Source.LEDGER else [],
                    [] if source is Source.LEDGER else [row.id],
                    facts,
                    [row.amount_minor],
                    settings,
                )
            )
    return findings


def _invalid_findings(issues: list[ValidationIssue], settings: Settings) -> list[Finding]:
    """Report each excluded row as an invalid record under its file-derived ID."""
    findings: list[Finding] = []
    for issue in issues:
        record_id = f"{'B' if issue.source is Source.BANK else 'L'}-{issue.row_number:06d}"
        ledger_ids = [record_id] if issue.source is Source.LEDGER else []
        bank_ids = [record_id] if issue.source is Source.BANK else []
        findings.append(
            _finding(
                "invalid_record",
                ledger_ids,
                bank_ids,
                {
                    "code": issue.code,
                    "message": issue.message,
                    "source": str(issue.source),
                    "row_number": issue.row_number,
                },
                [],
                settings,
            )
        )
    return findings


def _order_key(finding: Finding) -> tuple[int, str, str, str]:
    """Return the stable ordering key: severity, type, then lowest record IDs."""
    return (
        SEVERITY_RANK[finding.severity],
        str(finding.type),
        min(finding.ledger_ids, default=""),
        min(finding.bank_ids, default=""),
    )


def assign_finding_ids(findings: list[Finding]) -> list[Finding]:
    """Sort findings deterministically and number them from F-0001."""
    ordered = sorted(findings, key=_order_key)
    return [
        finding.model_copy(update={"id": f"F-{number:04d}"})
        for number, finding in enumerate(ordered, start=1)
    ]


def build_findings(
    ledger_result: NormalizationResult,
    bank_result: NormalizationResult,
    settings: Settings,
) -> MatchingOutcome:
    """Apply rules R1 to R7 in the fixed order and add R0 invalid-record findings."""
    ledger = ledger_result.transactions
    bank = bank_result.transactions
    exact = match_exact(ledger, bank, settings.date_window_exact_days)
    fuzzy = match_fuzzy(
        exact.unmatched_ledger,
        exact.unmatched_bank,
        settings.date_window_fuzzy_days,
        settings.fuzzy_accept,
    )
    matched_ledger = {
        *(item.ledger.id for item in exact.matches),
        *(item.ledger.id for item in fuzzy.matches),
    }
    matched_bank = {
        *(item.bank.id for item in exact.matches),
        *(item.bank.id for item in fuzzy.matches),
    }
    duplicates = detect_duplicates(
        fuzzy.unmatched_ledger,
        fuzzy.unmatched_bank,
        [row for row in ledger if row.id in matched_ledger],
        [row for row in bank if row.id in matched_bank],
        settings.dup_date_window_days,
    )
    amounts = classify_amount_differences(
        duplicates.unmatched_ledger, duplicates.unmatched_bank, settings
    )
    dates = classify_date_mismatches(amounts.unmatched_ledger, amounts.unmatched_bank, settings)
    splits = match_splits(dates.unmatched_ledger, dates.unmatched_bank, settings)
    records_by_id = {row.id: row for row in [*ledger, *bank]}
    issues = [*ledger_result.issues, *bank_result.issues]
    findings = [
        *_exact_findings(exact.matches, settings),
        *_fuzzy_findings(fuzzy.matches, settings),
        *_duplicate_findings(duplicates.findings, settings),
        *_pair_findings(amounts.pairs, settings),
        *_pair_findings(dates.pairs, settings),
        *_split_findings(splits.matches, splits.ambiguous, records_by_id, settings),
    ]
    reported_ids = {
        row_id for finding in findings for row_id in (*finding.ledger_ids, *finding.bank_ids)
    }
    findings.extend(
        _missing_findings(
            splits.unmatched_ledger, splits.unmatched_bank, splits.truncated, reported_ids, settings
        )
    )
    findings.extend(_invalid_findings(issues, settings))
    return MatchingOutcome(
        findings=assign_finding_ids(findings),
        ledger=ledger,
        bank=bank,
        issues=issues,
    )


@dataclass(frozen=True)
class RunResult:
    """One complete deterministic reconciliation run and its audit metadata."""

    run_id: str
    findings: list[Finding]
    ledger: list[Transaction]
    bank: list[Transaction]
    issues: list[ValidationIssue]
    meta: dict[str, Any]
    verifier_records: list[dict[str, Any]] = field(default_factory=list)

    @property
    def records_by_id(self) -> dict[str, Transaction]:
        """Index every valid transaction by ID for evidence and reporting."""
        return {row.id: row for row in [*self.ledger, *self.bank]}


def serializable_config(settings: Settings) -> dict[str, Any]:
    """Return every setting except credentials for the config hash and appendix."""
    values = settings.__dict__
    return {name: value for name, value in sorted(values.items()) if not name.endswith("api_key")}


def config_hash(settings: Settings) -> str:
    """Hash the credential-free configuration so a run can be reproduced."""
    payload = json.dumps(serializable_config(settings), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one input file for the run's audit metadata."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_id(created_at: datetime, settings: Settings) -> str:
    """Build the documented run identifier from the UTC start time and config."""
    return f"{created_at:%Y%m%d-%H%M%S}-{config_hash(settings)[:8]}"


def _input_meta(path: Path, result: NormalizationResult, column_map: ColumnMap) -> dict[str, Any]:
    """Describe one ingested input file for `run_meta.json`."""
    return {
        "file": path.name,
        "sha256": sha256_file(path),
        "valid_rows": len(result.transactions),
        "invalid_rows": len(result.issues),
        "column_map": column_map.as_dict(),
    }


def run_pipeline(
    bank_path: Path,
    ledger_path: Path,
    settings: Settings | None = None,
    column_map: Mapping[str, str] | None = None,
    provider: LLMProvider | None = None,
) -> RunResult:
    """Ingest, normalize and match one pair of files, then explain if asked to.

    With a provider every discrepancy gains a verified explanation and every other
    finding a deterministic rationale; types, statuses and record IDs are identical
    either way because the LLM only fills the `explanation` field.
    """
    config = settings or get_settings()
    started = datetime.now(timezone.utc)
    bank_file = load_file(bank_path, column_map)
    ledger_file = load_file(ledger_path, column_map)
    bank = normalize_frame(bank_file.frame, Source.BANK, bank_file.column_map, config)
    ledger = normalize_frame(ledger_file.frame, Source.LEDGER, ledger_file.column_map, config)
    outcome = build_findings(ledger, bank, config)
    findings = outcome.findings
    llm_meta: dict[str, Any] = {"provider": "none"}
    verifier_records: list[dict[str, Any]] = []
    if provider is not None:
        records = {row.id: row for row in [*outcome.ledger, *outcome.bank]}
        explained = explain_findings(findings, records, provider, config)
        findings = explained.findings
        verifier_records = explained.verifier_records
        llm_meta = explained.stats
    meta = {
        "run_id": _run_id(started, config),
        "created_at": started.isoformat(),
        "tool_version": __version__,
        "inputs": {
            "bank": _input_meta(bank_file.path, bank, bank_file.column_map),
            "ledger": _input_meta(ledger_file.path, ledger, ledger_file.column_map),
        },
        "validation_issues": len(outcome.issues),
        "finding_count": len(findings),
        "config": serializable_config(config),
        "config_hash": config_hash(config),
        "llm": llm_meta,
    }
    LOGGER.info(
        "run_complete run_id=%s findings=%d issues=%d llm=%s",
        meta["run_id"],
        len(findings),
        len(outcome.issues),
        meta["llm"]["provider"],
    )
    return RunResult(
        run_id=meta["run_id"],
        findings=findings,
        ledger=outcome.ledger,
        bank=outcome.bank,
        issues=outcome.issues,
        meta=meta,
        verifier_records=verifier_records,
    )
