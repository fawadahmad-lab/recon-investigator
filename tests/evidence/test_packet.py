"""Tests for the evidence packet contract in Architecture section 9."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from recon.config import get_settings
from recon.evidence.packet import (
    ALLOWED_CAUSES,
    LLM_FINDING_TYPES,
    MAX_CANDIDATES,
    RULE_DESCRIPTIONS,
    build_packet,
    packet_hash,
    packet_json,
)
from recon.matching.engine import RULES, build_findings, run_pipeline
from recon.models import EvidencePacket, Finding, Transaction, from_minor
from recon.normalize.pipeline import NormalizationResult
from recon.synth.generator import generate_dataset

DAY = date(2026, 1, 5)
ID_TOKEN = re.compile(r'"((?:[LB]-\d{6}|F-\d{4}))"')
DATE_TOKEN = re.compile(r'"(\d{4}-\d{2}-\d{2})"')
PREFIX = {"ledger": "L", "bank": "B"}


def _transaction(
    source: str,
    number: int,
    reference: str,
    amount_minor: int,
    transaction_date: date = DAY,
    description: str = "acme supplies",
) -> Transaction:
    """Build one canonical record for packet fixtures."""
    return Transaction(
        id=f"{PREFIX[source]}-{number:06d}",
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


def _outcome(ledger: list[Transaction], bank: list[Transaction]):
    """Run the rule chain over fixture records."""
    return build_findings(
        NormalizationResult(transactions=ledger, issues=[]),
        NormalizationResult(transactions=bank, issues=[]),
        get_settings(),
    )


def _fixture_rows():
    """Match a record set that produces every LLM-explained finding type once."""
    ledger = [
        _transaction("ledger", 1, "DUPPRIM", 5000),
        _transaction("ledger", 2, "DUPPRIM", 5000),
        _transaction("ledger", 3, "ONLYL1", 30000),
        _transaction("ledger", 4, "AMTMS1", 200000),
        _transaction("ledger", 5, "FEE001", 10000),
        _transaction("ledger", 6, "DATEM1", 40000, DAY + timedelta(days=20)),
        _transaction("ledger", 7, "SPLITMB", 20000),
        _transaction("ledger", 8, "DBNK001", 7000),
    ]
    bank = [
        _transaction("bank", 1, "DUPPRIM", 5000),
        _transaction("bank", 2, "DBNK001", 7000),
        _transaction("bank", 3, "DBNK001", 7000),
        _transaction("bank", 4, "ONLYB1", 60000),
        _transaction("bank", 5, "AMTMS1", 150000),
        _transaction("bank", 6, "FEE001", 9800),
        _transaction("bank", 7, "DATEM1", 40000),
        _transaction("bank", 8, "SPLITMB", 12000),
        _transaction("bank", 9, "SPLITMB", 8000),
        _transaction("bank", 10, "SPLITMB", 11000),
        _transaction("bank", 11, "SPLITMB", 9000),
    ]
    return ledger, bank


def _first_of_type(findings: list[Finding]) -> dict[str, Finding]:
    """Return the first finding of each type in stable order."""
    first: dict[str, Finding] = {}
    for finding in findings:
        first.setdefault(str(finding.type), finding)
    return first


def _walk(value: Any) -> Any:
    """Yield every scalar value inside a JSON-like structure."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def test_allowed_cause_table_matches_the_architecture() -> None:
    """Every explained type has its documented causes and every rule is described."""
    assert LLM_FINDING_TYPES == (
        "missing_in_bank",
        "missing_in_ledger",
        "duplicate_in_ledger",
        "duplicate_in_bank",
        "amount_mismatch",
        "fee_difference",
        "date_mismatch",
        "ambiguous_split",
    )
    for causes in ALLOWED_CAUSES.values():
        assert causes[-1] == "unknown"
        assert len(set(causes)) == len(causes)
    assert set(RULE_DESCRIPTIONS) == {rule_id for rule_id, _ in RULES.values()}


@pytest.mark.parametrize("finding_type", LLM_FINDING_TYPES)
def test_a_packet_exists_for_every_type_that_uses_the_llm(finding_type: str) -> None:
    """Each explained type yields a packet with its rule, records and allowed causes."""
    ledger, bank = _fixture_rows()
    outcome = _outcome(ledger, bank)
    finding = _first_of_type(outcome.findings)[finding_type]
    records = {row.id: row for row in [*outcome.ledger, *outcome.bank]}

    packet = build_packet(finding, records, get_settings())

    assert packet.packet_version == "1"
    assert packet.finding_id == finding.id
    assert str(packet.finding_type) == finding_type
    assert packet.rule.id == finding.rule_id
    assert packet.rule.version == finding.rule_version
    assert packet.rule.description == RULE_DESCRIPTIONS[finding.rule_id]
    assert packet.allowed_causes == list(ALLOWED_CAUSES[finding_type])
    assert {record["id"] for record in packet.records} >= {
        *finding.ledger_ids,
        *finding.bank_ids,
    }
    assert {record["role"] for record in packet.records} <= {"ledger", "bank"}


def test_allowed_values_cover_every_amount_date_and_id_in_the_packet() -> None:
    """Amounts come from the records, and every ID and date in the text is whitelisted."""
    ledger, bank = _fixture_rows()
    outcome = _outcome(ledger, bank)
    records = {row.id: row for row in [*outcome.ledger, *outcome.bank]}
    settings = get_settings()

    for finding in outcome.findings:
        if str(finding.type) not in ALLOWED_CAUSES:
            continue
        packet = build_packet(finding, records, settings)
        text = packet_json(packet)
        allowed = packet.allowed_values
        assert set(ID_TOKEN.findall(text)) <= set(allowed["ids"])
        assert set(DATE_TOKEN.findall(text)) <= set(allowed["dates"])
        for value in _walk(packet.model_dump(mode="json")):
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                assert str(value) in allowed["numbers"]
        for row_id in (*finding.ledger_ids, *finding.bank_ids):
            row = records[row_id]
            assert row_id in allowed["ids"]
            assert row.date.isoformat() in allowed["dates"]
            assert f"{from_minor(row.amount_minor):.2f}" in allowed["amounts"]
            assert str(row.row_number) in allowed["numbers"]
        for key, value in finding.facts.items():
            if key.endswith("_minor"):
                unitless = key[: -len("_minor")]
                assert f"{Decimal(value) / 100:.2f}" in allowed["amounts"]
                assert unitless in packet.facts
        assert finding.id in allowed["ids"]


def test_duplicate_packet_includes_the_matched_primary_record() -> None:
    """A duplicate's primary is evidence in its own right, not only an ID in the facts."""
    ledger, bank = _fixture_rows()
    outcome = _outcome(ledger, bank)
    finding = _first_of_type(outcome.findings)["duplicate_in_ledger"]
    records = {row.id: row for row in [*outcome.ledger, *outcome.bank]}

    packet = build_packet(finding, records, get_settings())

    primary = str(finding.facts["primary_id"])
    assert {primary, finding.ledger_ids[0]} == {record["id"] for record in packet.records}
    assert primary in packet.allowed_values["ids"]


def test_ambiguous_split_lists_at_most_three_scored_candidates() -> None:
    """Ambiguity evidence names candidates with transparent scores and one reason."""
    ledger, bank = _fixture_rows()
    outcome = _outcome(ledger, bank)
    finding = _first_of_type(outcome.findings)["ambiguous_split"]
    records = {row.id: row for row in [*outcome.ledger, *outcome.bank]}

    packet = build_packet(finding, records, get_settings())

    assert 0 < len(packet.candidates_considered) <= MAX_CANDIDATES
    assert [item["score"] for item in packet.candidates_considered] == sorted(
        (item["score"] for item in packet.candidates_considered), reverse=True
    )
    anchor_side = str(records[str(finding.facts["anchor_id"])].source)
    for item in packet.candidates_considered:
        assert set(item) == {"id", "score", "components", "rejected_reason"}
        assert set(item["components"]) == {"ref_sim", "desc_sim", "date_sim"}
        assert item["rejected_reason"]
        roles = {record["id"]: record["role"] for record in packet.records}
        assert roles[item["id"]] != anchor_side


def test_amount_facts_use_two_decimal_strings_and_leave_the_finding_untouched() -> None:
    """Minor units never reach the model and the deterministic finding is not mutated."""
    ledger, bank = _fixture_rows()
    outcome = _outcome(ledger, bank)
    finding = _first_of_type(outcome.findings)["amount_mismatch"]
    records = {row.id: row for row in [*outcome.ledger, *outcome.bank]}

    packet = build_packet(finding, records, get_settings())

    assert packet.facts["ledger_amount"] == "2000.00"
    assert packet.facts["bank_amount"] == "1500.00"
    assert packet.facts["amount_difference"] == "500.00"
    assert not any(key.endswith("_minor") for key in packet.facts)
    assert finding.facts["ledger_amount_minor"] == 200000
    assert "500.00" in packet.allowed_values["amounts"]


def _standalone_finding(finding_type: str, **facts: Any) -> Finding:
    """Build one finding of a type the fixture run cannot produce."""
    rule_id, rule_version = RULES[finding_type]
    return Finding(
        id="F-0001",
        type=finding_type,
        status="discrepancy",
        bank_ids=["B-000001"],
        rule_id=rule_id,
        rule_version=rule_version,
        facts=dict(facts),
        severity="low",
    )


@pytest.mark.parametrize("finding_type", ["match_exact", "match_fuzzy", "invalid_record"])
def test_findings_the_llm_must_not_explain_have_no_packet(finding_type: str) -> None:
    """Match and invalid-record findings cannot enter the LLM path at all."""
    ledger = [
        _transaction("ledger", 1, "EXACTX", 1234),
        _transaction("ledger", 2, "FUZZYX", 2200, DAY + timedelta(days=2)),
    ]
    bank = [
        _transaction("bank", 1, "EXACTX", 1234),
        _transaction("bank", 2, "FUZZYXX", 2200),
    ]
    outcome = _outcome(ledger, bank)
    records = {row.id: row for row in [*outcome.ledger, *outcome.bank]}
    finding = _first_of_type(outcome.findings).get(finding_type)
    finding = finding or _standalone_finding(finding_type, code="unparsable_amount")

    with pytest.raises(ValueError, match="not explained by the LLM"):
        build_packet(finding, records, get_settings())


def test_unknown_record_reference_is_reported_instead_of_dropping_evidence() -> None:
    """A packet cannot be built from evidence the run does not hold."""
    ledger, bank = _fixture_rows()
    outcome = _outcome(ledger, bank)
    finding = _first_of_type(outcome.findings)["missing_in_bank"]
    records = {row.id: row for row in [*outcome.ledger, *outcome.bank]}
    altered = finding.model_copy(update={"bank_ids": ["B-000099"]})

    with pytest.raises(ValueError, match="unknown records"):
        build_packet(altered, records, get_settings())


def test_packets_serialize_deterministically_and_hash_their_content() -> None:
    """Identical packets are byte-identical and different content moves the hash."""
    ledger, bank = _fixture_rows()
    outcome = _outcome(ledger, bank)
    records = {row.id: row for row in [*outcome.ledger, *outcome.bank]}
    settings = get_settings()
    findings = _first_of_type(outcome.findings)

    first = build_packet(findings["fee_difference"], records, settings)
    second = build_packet(findings["fee_difference"], records, settings)
    other = build_packet(findings["missing_in_ledger"], records, settings)

    assert packet_json(first) == packet_json(second)
    assert packet_hash(first) == packet_hash(second)
    assert packet_hash(other) != packet_hash(first)
    assert json.loads(packet_json(first))["finding_id"] == first.finding_id


def test_real_run_yields_a_stable_packet_for_every_explained_finding(tmp_path: Path) -> None:
    """A full synthetic run covers all explained types with unique, reproducible packets."""
    dataset = generate_dataset("realistic", 42, tmp_path)
    result = run_pipeline(dataset / "bank.csv", dataset / "ledger.csv", get_settings())
    settings = get_settings()
    explained = [item for item in result.findings if str(item.type) in ALLOWED_CAUSES]

    packets = [build_packet(item, result.records_by_id, settings) for item in explained]

    assert {str(packet.finding_type) for packet in packets} == set(ALLOWED_CAUSES)
    assert len({packet_hash(packet) for packet in packets}) == len(packets)
    for packet, finding in zip(packets, explained, strict=True):
        assert isinstance(packet, EvidencePacket)
        assert packet.finding_id == finding.id
        assert {record["id"] for record in packet.records} >= {
            *finding.ledger_ids,
            *finding.bank_ids,
        }
        assert packet_json(build_packet(finding, result.records_by_id, settings)) == packet_json(
            packet
        )
