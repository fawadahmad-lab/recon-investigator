"""Shared fixtures for the report tests: small runs plus a run per explanation source."""

from __future__ import annotations

from pathlib import Path

import pytest

from recon.config import Settings, get_settings
from recon.evidence.packet import EvidencePacket
from recon.llm.mock import MockProvider
from recon.matching.engine import RunResult, run_pipeline
from recon.synth.generator import generate_dataset

HEADER = "Date,Amount,Reference,Description,Currency\n"
MARKER = "RAWONLYMARKER"
BAD_ANSWER = '{"summary": "%s", "unexpected_field": 1}' % MARKER
LEDGER_ROWS = [
    "2026-01-05,1234.56,EXACT1,Acme Supplies,USD",
    "2026-01-06,98765.43,ONLYLED,Big Payment invoice,USD",
    '2026-01-07,300.00,DUP1,"Evil <script>alert(1)</script> & ""quotes""",USD',
    "not-a-date,50.00,BADROW,Acme Supplies,USD",
]
BANK_ROWS = [
    "2026-01-05,1234.56,EXACT1,Acme Supplies,USD",
    "2026-01-09,180.00,BANKONLY,Coffee Roasters,USD",
]


class _FallbackProvider:
    """A provider whose answer is always rejected, so the verifier must fall back."""

    name = "always_bad"
    model_name = "always-bad-model"

    def __init__(self) -> None:
        """Count calls so the retry path is observable."""
        self.calls = 0

    def complete(self, packet: EvidencePacket, error_codes: tuple[str, ...] = ()) -> str:
        """Return the same malformed answer regardless of the verifier feedback."""
        self.calls += 1
        return BAD_ANSWER


def _write(folder: Path, name: str, rows: list[str]) -> Path:
    """Write one mini CSV file, creating its folder if needed."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(f"{HEADER}{chr(10).join(rows)}{chr(10)}", encoding="utf-8")
    return path


def _mini_files(folder: Path) -> tuple[Path, Path]:
    """Write the mini ledger and bank CSVs for one run."""
    return _write(folder, "ledger.csv", LEDGER_ROWS), _write(folder, "bank.csv", BANK_ROWS)


@pytest.fixture(scope="session")
def settings() -> Settings:
    """The default configuration so reported thresholds match `run_meta.json`."""
    return get_settings()


@pytest.fixture(scope="session")
def mini_run(tmp_path_factory: pytest.TempPathFactory, settings: Settings) -> RunResult:
    """A deterministic run holding a match, both missing types, a description with markup."""
    folder = tmp_path_factory.mktemp("report-mini")
    ledger, bank = _mini_files(folder)
    return run_pipeline(bank, ledger, settings)


@pytest.fixture(scope="session")
def explained_run(tmp_path_factory: pytest.TempPathFactory, settings: Settings) -> RunResult:
    """The same mini run with `mock` explanations, so verified AI boxes exist."""
    folder = tmp_path_factory.mktemp("report-explained")
    ledger, bank = _mini_files(folder)
    return run_pipeline(bank, ledger, settings, provider=MockProvider())


@pytest.fixture(scope="session")
def fallback_run(tmp_path_factory: pytest.TempPathFactory, settings: Settings) -> RunResult:
    """A run where every answer is rejected, so every box is a marked fallback."""
    folder = tmp_path_factory.mktemp("report-fallback")
    ledger, bank = _mini_files(folder)
    return run_pipeline(bank, ledger, settings, provider=_FallbackProvider())


@pytest.fixture(scope="session")
def full_run(tmp_path_factory: pytest.TempPathFactory, settings: Settings) -> RunResult:
    """An `easy` dataset explained by `mock` so all eight discrepancy types are present."""
    folder = generate_dataset("easy", 5, tmp_path_factory.mktemp("report-full"))
    return run_pipeline(
        folder / "bank.csv", folder / "ledger.csv", settings, provider=MockProvider()
    )
