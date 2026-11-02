"""Tests for the prompt contract and the provider registry."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from recon.config import get_settings
from recon.errors import ValidationError
from recon.evidence.packet import EvidencePacket, packet_json
from recon.llm.base import PROVIDER_NAMES, LLMProvider, build_provider
from recon.llm.mock import FaultyMockProvider, MockProvider
from recon.llm.openai_compat import OpenAICompatProvider
from recon.llm.prompts import SYSTEM_PROMPT, user_prompt
from recon.llm.schema import output_schema

SCHEMA_FIELDS = {
    "summary",
    "likely_cause",
    "explanation",
    "cited_facts",
    "recommended_action",
    "action_detail",
    "confidence",
    "uncertainties",
}


def test_system_prompt_states_the_trust_boundary() -> None:
    """The prompt forbids deciding matches, requires packet-only values and unknown-low."""
    lowered = SYSTEM_PROMPT.lower()
    for phrase in (
        "never decide",
        "allowed_values",
        '"unknown"',
        'confidence "low"',
        "single json object",
    ):
        assert phrase in lowered
    assert "reconciliation is already decided" in lowered


def test_system_prompt_carries_the_parser_schema_and_no_secrets() -> None:
    """The schema in the prompt is the schema the parser enforces, verbatim."""
    assert json.dumps(output_schema(), sort_keys=True) in SYSTEM_PROMPT
    assert "http" not in SYSTEM_PROMPT
    assert "bearer" not in SYSTEM_PROMPT.lower()
    assert "sk-" not in SYSTEM_PROMPT


def test_user_prompt_embeds_the_packet_verbatim(packets: dict[str, EvidencePacket]) -> None:
    """The model sees exactly the packet the verifier will check it against."""
    packet = packets["amount_mismatch"]
    prompt = user_prompt(packet)

    assert packet_json(packet) in prompt
    assert prompt.startswith("Evidence packet (JSON):")
    assert "Failure codes" not in prompt


def test_retry_prompt_reports_only_the_verifier_codes(packets: dict[str, EvidencePacket]) -> None:
    """A retry names the failure codes and repeats the packet unchanged."""
    packet = packets["missing_in_bank"]
    prompt = user_prompt(packet, ("unsupported_figure", "bad_enum", "bad_enum"))

    assert "bad_enum, unsupported_figure" in prompt
    assert packet_json(packet) in prompt


def test_output_schema_matches_the_documented_answer_shape() -> None:
    """The wire schema has the eight fields of Architecture section 10 and no more."""
    schema = output_schema()

    assert set(schema["properties"]) == SCHEMA_FIELDS
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == SCHEMA_FIELDS - {"cited_facts", "uncertainties"}
    assert schema["properties"]["summary"]["maxLength"] == 200
    assert schema["properties"]["explanation"]["maxLength"] == 800
    assert schema["properties"]["action_detail"]["maxLength"] == 300


@pytest.mark.parametrize(
    ("name", "expected"),
    [("mock", MockProvider), ("faulty_mock", FaultyMockProvider)],
)
def test_registry_builds_the_configured_offline_provider(name: str, expected: type) -> None:
    """Provider selection is by name only and never touches the network."""
    provider = build_provider(replace(get_settings(), llm_provider=name))

    assert isinstance(provider, expected)
    assert isinstance(provider, LLMProvider)
    assert provider.name == name


def test_groq_and_openai_compat_share_one_endpoint_implementation() -> None:
    """Both documented real-provider names use the OpenAI-compatible client."""
    settings = replace(
        get_settings(),
        llm_base_url="http://127.0.0.1:9/v1",
        llm_api_key="test-key",
        llm_cache_dir="",
    )

    for name in ("groq", "openai_compat"):
        provider = build_provider(settings, name)
        assert isinstance(provider, OpenAICompatProvider)
        assert provider.name == name
        assert provider.model_name == settings.llm_model
        provider.close()


def test_an_unknown_provider_name_is_a_configuration_error() -> None:
    """A typo in `LLM_PROVIDER` fails fast instead of silently calling a mock."""
    with pytest.raises(ValidationError, match="unknown LLM provider"):
        build_provider(replace(get_settings(), llm_provider="openai"), "gpt-proxy")
    with pytest.raises(ValidationError, match="unknown LLM provider"):
        build_provider(replace(get_settings(), llm_provider="gpt-proxy"))


def test_registry_lists_every_documented_provider() -> None:
    """The provider names in Architecture section 10 are all selectable."""
    assert PROVIDER_NAMES == ("mock", "faulty_mock", "openai_compat", "groq")
