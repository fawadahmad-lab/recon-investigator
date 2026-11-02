"""Shared fixtures for the LLM provider tests."""

from __future__ import annotations

import pytest

from recon.config import get_settings
from recon.evidence.packet import ALLOWED_CAUSES, build_packet
from recon.matching.engine import run_pipeline
from recon.models import EvidencePacket
from recon.synth.generator import generate_dataset


@pytest.fixture(scope="session")
def packets(tmp_path_factory: pytest.TempPathFactory) -> dict[str, EvidencePacket]:
    """Return one evidence packet per LLM-explained finding type."""
    dataset = generate_dataset("realistic", 7, tmp_path_factory.mktemp("llm-data"))
    result = run_pipeline(dataset / "bank.csv", dataset / "ledger.csv", get_settings())
    found: dict[str, EvidencePacket] = {}
    for finding in result.findings:
        finding_type = str(finding.type)
        if finding_type in ALLOWED_CAUSES and finding_type not in found:
            found[finding_type] = build_packet(finding, result.records_by_id, get_settings())
    assert set(found) == set(ALLOWED_CAUSES)
    return found


@pytest.fixture(scope="session")
def all_packets(packets: dict[str, EvidencePacket]) -> list[EvidencePacket]:
    """List the packets in a stable order."""
    return [packets[finding_type] for finding_type in ALLOWED_CAUSES]
