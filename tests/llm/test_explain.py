"""Tests for the explanation pipeline: rationales, retries, fallbacks and the run wiring."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from recon.config import get_settings
from recon.errors import LLMError
from recon.evidence.packet import ALLOWED_CAUSES, EvidencePacket
from recon.llm.explain import explain_findings, is_explainable, rationale
from recon.llm.mock import FaultyMockProvider, MockProvider
from recon.llm.verifier import VERDICT_ERROR
from recon.matching.engine import RunResult, run_pipeline
from recon.models import ExplanationSource, Finding
from recon.report.builder import findings_payload, write_run_artifacts
from recon.synth.generator import generate_dataset

HEADER = "Date,Amount,Reference,Description,Currency\n"
LEDGER_ROWS = [
    "2026-01-05,100.00,EXACT1,Acme Supplies,USD",
    "2026-01-06,250.00,ONLYLED,Acme Supplies,USD",
    "2026-01-07,300.00,DUP1,AZ Distributors,USD",
    "2026-01-07,300.00,DUP1,AZ Distributors,USD",
    "not-a-date,50.00,BADROW,Acme Supplies,USD",
]
BANK_ROWS = [
    "2026-01-05,100.00,EXACT1,Acme Supplies,USD",
    "2026-01-09,180.00,BANKONLY,Coffee Roasters,USD",
    "2026-01-07,300.00,DUP1,AZ Distributors,USD",
]
DISCREPANCY_TYPES = {"missing_in_bank", "missing_in_ledger", "duplicate_in_ledger"}


class _StickyFaultyProvider:
    """A provider that ignores the retry feedback and repeats its fault."""

    name = "sticky_mock"
    model_name = "sticky"

    def __init__(self, fault: str = "invented_amount") -> None:
        """Wrap one forced `faulty_mock` fault."""
        self.inner = FaultyMockProvider(fault=fault)

    def complete(self, packet: EvidencePacket, error_codes: tuple[str, ...] = ()) -> str:
        """Always answer as if this were the first attempt."""
        return self.inner.complete(packet, ())


class _FailingProvider:
    """A provider whose transport never succeeds."""

    name = "failing"
    model_name = "failing-model"

    def complete(self, packet: EvidencePacket, error_codes: tuple[str, ...] = ()) -> str:
        """Raise the documented provider error."""
        raise LLMError("provider request failed: ConnectTimeout")


class _CountingProvider:
    """A provider that records how many answers are in flight at once."""

    name = "counting"
    model_name = "counting"

    def __init__(self) -> None:
        """Start with no calls in flight."""
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def complete(self, packet: EvidencePacket, error_codes: tuple[str, ...] = ()) -> str:
        """Hold the thread briefly so a wider pool would be visible."""
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(0.02)
            return MockProvider().complete(packet, error_codes)
        finally:
            with self.lock:
                self.active -= 1


def _write(tmp_path: Path, name: str, rows: list[str]) -> Path:
    """Write one mini CSV file, creating its folder if needed."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text(f"{HEADER}{chr(10).join(rows)}{chr(10)}", encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def mini(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """One tiny run holding a match, a duplicate, both missing types and an invalid row."""
    folder = tmp_path_factory.mktemp("explain-mini")
    ledger = _write(folder, "ledger.csv", LEDGER_ROWS)
    bank = _write(folder, "bank.csv", BANK_ROWS)
    return run_pipeline(bank, ledger, get_settings())


@pytest.fixture(scope="module")
def full(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """An `easy` dataset run so every discrepancy type is present."""
    folder = generate_dataset("easy", 5, tmp_path_factory.mktemp("explain-full"))
    return run_pipeline(folder / "bank.csv", folder / "ledger.csv", get_settings())


def _decision_fields(finding: Finding) -> tuple:
    """Project everything about a finding except its explanation."""
    return (
        finding.id,
        str(finding.type),
        str(finding.status),
        str(finding.severity),
        tuple(finding.ledger_ids),
        tuple(finding.bank_ids),
        finding.rule_id,
        json.dumps(finding.facts, sort_keys=True),
    )


def test_mini_run_covers_the_shapes_the_pipeline_must_handle(mini: RunResult) -> None:
    """The fixture really holds matches, discrepancies and an invalid record."""
    types = {str(finding.type) for finding in mini.findings}

    assert DISCREPANCY_TYPES <= types
    assert "match_exact" in types
    assert "invalid_record" in types


def test_every_finding_is_explained_with_the_mock(mini: RunResult) -> None:
    """No finding is left blank: discrepancies are verified, the rest are rationales."""
    outcome = explain_findings(mini.findings, mini.records_by_id, MockProvider(), get_settings())
    discrepancies = [finding for finding in mini.findings if is_explainable(finding)]

    assert all(finding.explanation is not None for finding in outcome.findings)
    for finding in outcome.findings:
        source = str(finding.explanation.explanation_source)
        expected = "ai_verified" if is_explainable(finding) else "deterministic_fallback"
        assert source == expected
    assert outcome.stats["explained"] == len(discrepancies)


def test_all_eight_discrepancy_types_are_verified_on_a_real_dataset(full: RunResult) -> None:
    """Every documented LLM type gets an AI explanation on generated data."""
    outcome = explain_findings(full.findings, full.records_by_id, MockProvider(), get_settings())

    assert {str(f.type) for f in full.findings if is_explainable(f)} == set(ALLOWED_CAUSES)
    explained = [f for f in outcome.findings if is_explainable(f)]
    assert all(str(f.explanation.explanation_source) == "ai_verified" for f in explained)
    assert all(f.explanation.cited_facts for f in explained)


@pytest.mark.parametrize("provider_name", ["mock", "faulty"])
def test_the_llm_never_changes_a_finding(mini: RunResult, provider_name: str) -> None:
    """Property: types, statuses and record IDs are identical with and without the LLM."""
    provider = MockProvider() if provider_name == "mock" else FaultyMockProvider(rate=1.0)
    outcome = explain_findings(mini.findings, mini.records_by_id, provider, get_settings())

    before = [_decision_fields(finding) for finding in mini.findings]
    after = [_decision_fields(finding) for finding in outcome.findings]
    assert before == after
    assert [f.explanation for f in outcome.findings].count(None) == 0


def test_a_faulty_run_completes_with_every_rejection_logged(mini: RunResult) -> None:
    """All injected faults are caught, every packet is retried, and none reach a fallback."""
    outcome = explain_findings(
        mini.findings, mini.records_by_id, FaultyMockProvider(rate=1.0), get_settings()
    )

    assert outcome.stats["rejected_answers"] == outcome.stats["explained"]
    assert outcome.stats["retried"] == outcome.stats["explained"]
    assert outcome.stats["deterministic_fallback"] == 0
    assert len(outcome.verifier_records) == 2 * outcome.stats["explained"]
    assert [record["verdict"] for record in outcome.verifier_records[:2]] == [
        "rejected",
        "accepted",
    ]


def test_a_provider_that_repeats_its_fault_falls_back_flagged(mini: RunResult) -> None:
    """A second rejection yields the marked deterministic explanation, never a gap."""
    outcome = explain_findings(
        mini.findings, mini.records_by_id, _StickyFaultyProvider(), get_settings()
    )
    discrepancies = [finding for finding in outcome.findings if is_explainable(finding)]

    assert outcome.stats["deterministic_fallback"] == len(discrepancies)
    assert outcome.stats["ai_verified"] == 0
    for finding in discrepancies:
        assert finding.explanation is not None
        assert finding.explanation.explanation_source is ExplanationSource.DETERMINISTIC_FALLBACK
        assert finding.explanation.likely_cause == "unknown"


def test_a_provider_error_does_not_fail_the_run(mini: RunResult) -> None:
    """Transport failure becomes a flagged fallback and one `provider_error` record."""
    outcome = explain_findings(
        mini.findings, mini.records_by_id, _FailingProvider(), get_settings()
    )
    discrepancies = [finding for finding in outcome.findings if is_explainable(finding)]

    assert outcome.stats["provider_errors"] == len(discrepancies)
    assert all(finding.explanation is not None for finding in discrepancies)
    assert all(
        str(finding.explanation.explanation_source) == "deterministic_fallback"
        for finding in discrepancies
    )
    assert [record["verdict"] for record in outcome.verifier_records] == [VERDICT_ERROR] * len(
        discrepancies
    )


def test_the_pool_respects_the_configured_concurrency_limit(mini: RunResult) -> None:
    """With the limit at one, no two provider calls overlap."""
    settings = replace(get_settings(), llm_max_concurrency=1)
    provider = _CountingProvider()

    explain_findings(mini.findings, mini.records_by_id, provider, settings)

    assert provider.peak == 1
    assert provider.peak <= settings.llm_max_concurrency


def test_rationales_are_one_line_deterministic_and_cite_the_records(mini: RunResult) -> None:
    """Matches and invalid rows get the documented single-line deterministic rationale."""
    outcome = explain_findings(mini.findings, mini.records_by_id, MockProvider(), get_settings())
    rationales = [finding for finding in outcome.findings if not is_explainable(finding)]
    again = explain_findings(mini.findings, mini.records_by_id, MockProvider(), get_settings())

    assert rationales
    for finding in rationales:
        explanation = finding.explanation
        assert explanation is not None
        assert "\n" not in explanation.explanation
        assert finding.rule_id in explanation.explanation
        assert str(explanation.confidence) == "high"
        assert explanation.likely_cause in {"matched_by_rule", "invalid_row"}
    assert [f.explanation for f in rationales] == [
        f.explanation for f in again.findings if not is_explainable(f)
    ]


def test_a_rationale_built_directly_names_the_claimed_records(mini: RunResult) -> None:
    """The rationale helper is usable standalone and cites the finding's own IDs."""
    invalid = next(finding for finding in mini.findings if str(finding.type) == "invalid_record")
    explanation = rationale(invalid)

    assert explanation.recommended_action == "investigate"
    assert str(invalid.facts["row_number"]) in explanation.explanation
    assert {fact.value for fact in explanation.cited_facts} >= {invalid.id}


def test_run_pipeline_with_a_provider_keeps_findings_and_adds_meta(tmp_path: Path) -> None:
    """A provider run writes the same findings plus explanations and a filled meta section."""
    folder = tmp_path / "explain-run"
    ledger = _write(folder, "ledger.csv", LEDGER_ROWS)
    bank = _write(folder, "bank.csv", BANK_ROWS)
    plain = run_pipeline(bank, ledger, get_settings())
    explained = run_pipeline(bank, ledger, get_settings(), provider=MockProvider())

    assert [_decision_fields(f) for f in plain.findings] == [
        _decision_fields(f) for f in explained.findings
    ]
    assert plain.meta["llm"] == {"provider": "none"}
    assert explained.meta["llm"]["provider"] == "mock"
    assert explained.meta["llm"]["ai_verified"] == explained.meta["llm"]["explained"]
    assert "api_key" not in json.dumps(explained.meta)


def test_artifacts_include_the_verifier_log_only_for_llm_runs(
    tmp_path: Path, mini: RunResult
) -> None:
    """`verifier_log.jsonl` appears when the LLM ran and is rewritten, not appended."""
    folder = tmp_path / "src"
    ledger = _write(folder, "ledger.csv", LEDGER_ROWS)
    bank = _write(folder, "bank.csv", BANK_ROWS)
    provider_run = run_pipeline(bank, ledger, get_settings(), provider=MockProvider())

    plain = write_run_artifacts(tmp_path / "plain", mini)
    written = write_run_artifacts(tmp_path / "llm", provider_run)
    write_run_artifacts(tmp_path / "llm", provider_run)

    assert [path.name for path in plain] == [
        "findings.json",
        "run_meta.json",
        "audit_trail.jsonl",
        "report.html",
    ]
    assert [path.name for path in written] == [
        "findings.json",
        "run_meta.json",
        "audit_trail.jsonl",
        "verifier_log.jsonl",
        "report.html",
    ]
    log = next(path for path in written if path.name == "verifier_log.jsonl")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(provider_run.verifier_records)
    assert json.loads(lines[0])["raw"]
    assert findings_payload(provider_run)[0]["explanation"] is not None
