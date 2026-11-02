"""Audit trail events: step order, evidence, and the rule that raw output stays out."""

from __future__ import annotations

import json
from pathlib import Path

from recon.llm.verifier import VERDICT_REJECTED
from recon.matching.engine import RunResult
from recon.report.audit import (
    AUDIT_TRAIL_NAME,
    STEP_INGEST,
    STEP_LLM_ATTEMPT,
    STEP_NORMALIZE,
    STEP_RULE,
    audit_events,
    audit_trail_lines,
    write_audit_trail,
)


def _by_step(events: list[dict[str, object]], step: str) -> list[dict[str, object]]:
    """Select the events belonging to one pipeline step."""
    return [event for event in events if event["step"] == step]


def test_the_documented_step_order_is_preserved(mini_run: RunResult) -> None:
    """Ingest and normalize come first, then one rule event per finding, then LLM work."""
    events = audit_events(mini_run)
    steps = [event["step"] for event in events]

    assert _by_step(events, STEP_INGEST)
    assert steps[:2] == [STEP_INGEST, STEP_INGEST]
    assert steps[2:4] == [STEP_NORMALIZE, STEP_NORMALIZE]
    assert steps[4 : 4 + len(mini_run.findings)] == [STEP_RULE] * len(mini_run.findings)
    assert steps[4 + len(mini_run.findings) :] == []


def test_ingest_events_carry_the_file_hash_and_row_total(mini_run: RunResult) -> None:
    """Each input file is identified by its SHA-256 and its full row count."""
    events = _by_step(audit_events(mini_run), STEP_INGEST)

    assert [event["source"] for event in events] == ["bank", "ledger"]
    for event in events:
        meta = mini_run.meta["inputs"][str(event["source"])]
        assert event["sha256"] == meta["sha256"]
        assert event["file"] == meta["file"]
        assert event["rows_total"] == meta["valid_rows"] + meta["invalid_rows"]
        assert event["column_map"]


def test_normalize_events_name_every_excluded_row(mini_run: RunResult) -> None:
    """Invalid rows are visible in the trail with their code and row number."""
    events = _by_step(audit_events(mini_run), STEP_NORMALIZE)
    ledger = next(event for event in events if event["source"] == "ledger")
    issues = [issue for issue in mini_run.issues if str(issue.source) == "ledger"]

    assert ledger["invalid_rows"] == len(issues)
    assert ledger["valid_rows"] == len(mini_run.ledger)
    assert [(row["row_number"], row["code"]) for row in ledger["excluded_rows"]] == [
        (issue.row_number, issue.code) for issue in sorted(issues, key=lambda i: i.row_number)
    ]


def test_rule_events_follow_the_stable_finding_order(mini_run: RunResult) -> None:
    """The trail reports exactly the findings the run produced, in report order."""
    events = _by_step(audit_events(mini_run), STEP_RULE)

    assert [event["finding_id"] for event in events] == [
        finding.id for finding in mini_run.findings
    ]
    for event, finding in zip(events, mini_run.findings, strict=True):
        assert event["rule_id"] == finding.rule_id
        assert event["finding_type"] == str(finding.type)
        assert event["ledger_ids"] == finding.ledger_ids
        assert event["bank_ids"] == finding.bank_ids


def test_llm_attempts_are_recorded_without_the_raw_answer(explained_run: RunResult) -> None:
    """Every attempt and verdict is auditable; the unverified text is not."""
    events = _by_step(audit_events(explained_run), STEP_LLM_ATTEMPT)
    trail = audit_trail_lines(audit_events(explained_run))

    assert events
    assert len(events) == len(explained_run.verifier_records)
    assert all("raw" not in event for event in events)
    assert all(event["run_id"] == explained_run.run_id for event in events)
    for record in explained_run.verifier_records:
        assert str(record["raw"]) not in trail


def test_a_rejected_attempt_feeds_the_retry_with_its_codes(fallback_run: RunResult) -> None:
    """The trail shows both attempts, and the second carries the first failure codes."""
    events = _by_step(audit_events(fallback_run), STEP_LLM_ATTEMPT)
    first = [event for event in events if event["attempt"] == 0]
    second = [event for event in events if event["attempt"] == 1]
    codes_by_packet = {event["packet_hash"]: event["failure_codes"] for event in first}

    assert first and second
    assert all(event["verdict"] == VERDICT_REJECTED for event in events)
    assert all(not event["request_codes"] for event in first)
    assert all(event["request_codes"] == codes_by_packet[event["packet_hash"]] for event in second)
    assert all(event["failure_codes"] for event in second)


def test_the_trail_is_identical_when_rebuilt(mini_run: RunResult) -> None:
    """Deriving the audit trail twice from one run writes the same bytes."""
    first = audit_trail_lines(audit_events(mini_run))

    assert first == audit_trail_lines(audit_events(mini_run))


def test_each_line_is_one_json_object(mini_run: RunResult, tmp_path: Path) -> None:
    """The artifact is valid JSONL with one event per line."""
    events = audit_events(mini_run)
    path = write_audit_trail(tmp_path / AUDIT_TRAIL_NAME, events)
    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == len(events)
    assert all(json.loads(line) for line in lines)
