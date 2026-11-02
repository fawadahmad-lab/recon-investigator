"""Tests for the deterministic matching engine and the run pipeline."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from recon.config import get_settings
from recon.matching.engine import build_findings, config_hash, run_pipeline, serializable_config
from recon.models import Finding, FindingStatus, Source, Transaction
from recon.normalize.pipeline import NormalizationResult
from recon.report.builder import findings_payload, write_run_artifacts

DAY = date(2026, 1, 5)


def _transaction(
    source: Source,
    number: int,
    reference: str,
    amount_minor: int,
    transaction_date: date = DAY,
    description: str = "acme supplies",
) -> Transaction:
    """Build one canonical record for engine fixtures."""
    prefix = "L" if source is Source.LEDGER else "B"
    return Transaction(
        id=f"{prefix}-{number:06d}",
        source=source,
        row_number=number,
        date=transaction_date,
        amount_minor=amount_minor,
        currency="USD",
        reference_norm=reference,
        reference_raw=reference,
        description_norm=description,
        description_raw=description,
    )


def _result(rows: list[Transaction]) -> NormalizationResult:
    """Wrap fixture records as a normalization result without issues."""
    return NormalizationResult(transactions=rows, issues=[])


def _ids(finding_type: str, findings: list[Finding]) -> list[list[str]]:
    """Collect the record IDs carried by every finding of one type."""
    return [
        sorted([*item.ledger_ids, *item.bank_ids])
        for item in findings
        if str(item.type) == finding_type
    ]


def test_every_valid_record_appears_in_exactly_one_finding() -> None:
    """The rule chain claims each ledger and bank record once and only once."""
    ledger = [
        _transaction(Source.LEDGER, 1, "EXACT1", 10000),
        _transaction(Source.LEDGER, 2, "FUZZY1", 20000, DAY + timedelta(days=2)),
        _transaction(Source.LEDGER, 3, "ONLYLED", 30000),
        _transaction(Source.LEDGER, 4, "ANCHORA", 40000),
        _transaction(Source.LEDGER, 5, "DUPPRIM", 50000),
        _transaction(Source.LEDGER, 6, "DUPPRIM", 50000),
    ]
    bank = [
        _transaction(Source.BANK, 1, "EXACT1", 10000),
        _transaction(Source.BANK, 2, "FUZZY1X", 20000),
        _transaction(Source.BANK, 3, "ONLYBANK", 60000),
        _transaction(Source.BANK, 4, "PARTA1", 25000),
        _transaction(Source.BANK, 5, "PARTA1", 15000),
        _transaction(Source.BANK, 6, "DUPPRIM", 50000),
    ]
    outcome = build_findings(_result(ledger), _result(bank), get_settings())
    claims = [identifier for finding in outcome.findings for identifier in finding.ledger_ids]
    claims += [identifier for finding in outcome.findings for identifier in finding.bank_ids]

    assert len(claims) == len(set(claims))
    assert len(claims) == len(ledger) + len(bank)


def test_split_parts_and_ambiguous_candidates_are_claimed_once() -> None:
    """A split match claims its parts and an ambiguity claims its listed candidates."""
    ledger = [
        _transaction(Source.LEDGER, 1, "SPLITOK", 10000),
        _transaction(Source.LEDGER, 2, "SPLITAMB", 20000),
    ]
    bank = [
        _transaction(Source.BANK, 1, "SPLITOK", 6000),
        _transaction(Source.BANK, 2, "SPLITOK", 4000),
        _transaction(Source.BANK, 3, "SPLITAMB", 12000),
        _transaction(Source.BANK, 4, "SPLITAMB", 8000),
        _transaction(Source.BANK, 5, "SPLITAMB", 11000),
        _transaction(Source.BANK, 6, "SPLITAMB", 9000),
    ]
    outcome = build_findings(_result(ledger), _result(bank), get_settings())

    assert _ids("match_split", outcome.findings) == [["B-000001", "B-000002", "L-000001"]]
    assert _ids("ambiguous_split", outcome.findings) == [
        ["B-000003", "B-000004", "B-000005", "B-000006", "L-000002"]
    ]
    assert _ids("missing_in_bank", outcome.findings) == []


def test_findings_are_ordered_by_severity_and_type_with_stable_ids() -> None:
    """Stable ordering assigns F-0001 to the highest-severity, alphabetically first type."""
    ledger = [
        _transaction(Source.LEDGER, 1, "SMALL1", 1000),
        _transaction(Source.LEDGER, 2, "LARGE1", 2000000),
        _transaction(Source.LEDGER, 3, "MEDIUM", 200000),
    ]
    bank = [
        _transaction(Source.BANK, 1, "SMALL1", 1000),
        _transaction(Source.BANK, 2, "LARGEONLY", 2000000),
        _transaction(Source.BANK, 3, "MEDIUM", 200000),
    ]
    outcome = build_findings(_result(ledger), _result(bank), get_settings())

    assert [(item.id, str(item.type), str(item.severity)) for item in outcome.findings] == [
        ("F-0001", "match_fuzzy", "high"),
        ("F-0002", "match_exact", "medium"),
        ("F-0003", "match_exact", "low"),
    ]
    assert {item.status for item in outcome.findings} == {FindingStatus.MATCHED}
    assert [item.rule_id for item in outcome.findings] == ["R2-FUZZY", "R1-EXACT", "R1-EXACT"]


def test_truncated_split_anchor_is_reported_missing_with_the_evidence_flag() -> None:
    """A split search stopped by the node budget leaves a flagged missing record."""
    ledger = [_transaction(Source.LEDGER, 1, "TRUNC1", 9000)]
    bank = [_transaction(Source.BANK, number, "TRUNC1", 2500) for number in range(1, 11)]
    settings = replace(get_settings(), split_max_nodes=20)

    outcome = build_findings(_result(ledger), _result(bank), settings)
    missing = [item for item in outcome.findings if str(item.type) == "missing_in_bank"]

    assert [item.facts.get("split_search_truncated") for item in missing] == [True]
    assert missing[0].rule_id == "R7-MISSING"


def test_invalid_rows_become_invalid_record_findings(tmp_path: Path) -> None:
    """Rows excluded by validation are reported under their file-derived record ID."""
    ledger = tmp_path / "ledger.csv"
    bank = tmp_path / "bank.csv"
    header = "Date,Amount,Reference,Description,Currency\n"
    ledger.write_text(f"{header}2026-01-05,100.00,OK1,Acme Supplies,USD\n", encoding="utf-8")
    bank.write_text(
        f"{header}2026-01-05,not-a-number,OK1,Acme Supplies,USD\n",
        encoding="utf-8",
    )

    result = run_pipeline(bank, ledger, get_settings())
    invalid = [item for item in result.findings if str(item.type) == "invalid_record"]

    assert [(item.rule_id, item.bank_ids, item.facts["code"]) for item in invalid] == [
        ("R0-INVALID", ["B-000001"], "unparsable_amount")
    ]
    assert str(invalid[0].status) == "discrepancy"


def test_run_pipeline_writes_reproducible_artifacts(tmp_path: Path) -> None:
    """Two runs of the same inputs write byte-identical findings and hashed metadata."""
    ledger = tmp_path / "ledger.csv"
    bank = tmp_path / "bank.csv"
    header = "Date,Amount,Reference,Description,Currency\n"
    ledger.write_text(
        f"{header}2026-01-05,100.00,OK1,Acme Supplies,USD\n2026-01-06,70.00,ONLY,Acme,USD\n",
        encoding="utf-8",
    )
    bank.write_text(
        f"{header}2026-01-05,100.00,OK1X,Acme Supplies,USD\n2026-01-07,55.00,BANKONLY,Coffee,USD\n",
        encoding="utf-8",
    )

    first = run_pipeline(bank, ledger, get_settings())
    second = run_pipeline(bank, ledger, get_settings())
    written = write_run_artifacts(tmp_path / "run", first)
    write_run_artifacts(tmp_path / "run2", second)
    findings_text = (tmp_path / "run" / "findings.json").read_text(encoding="utf-8")
    meta = json.loads((tmp_path / "run" / "run_meta.json").read_text(encoding="utf-8"))

    assert findings_text == (tmp_path / "run2" / "findings.json").read_text(encoding="utf-8")
    assert [path.name for path in written] == [
        "findings.json",
        "run_meta.json",
        "audit_trail.jsonl",
        "report.html",
    ]
    trail = (tmp_path / "run" / "audit_trail.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(trail) == len(first.findings) + 4
    assert meta["config_hash"] == config_hash(get_settings())
    assert meta["config"] == serializable_config(get_settings())
    assert "llm_api_key" not in json.dumps(meta)
    assert meta["inputs"]["bank"]["sha256"]
    assert meta["run_id"].endswith(meta["config_hash"][:8])
    assert findings_payload(first)[0]["id"] == "F-0001"


def test_engine_handles_large_inputs_within_the_time_budget() -> None:
    """A 2,000-row pair completes the full rule chain well inside the run budget."""
    settings = get_settings()
    ledger_rows = [
        _transaction(Source.LEDGER, number, f"REF{number}", 1000 + number)
        for number in range(1, 2001)
    ]
    bank_rows = [
        _transaction(
            Source.BANK,
            number,
            f"REF{number}",
            1000 + number,
            DAY + timedelta(days=number % 4),
        )
        for number in range(1, 2001)
    ]

    started = time.perf_counter()
    outcome = build_findings(_result(ledger_rows), _result(bank_rows), settings)
    elapsed = time.perf_counter() - started

    assert len(outcome.findings) == 2000
    assert elapsed < 10.0
