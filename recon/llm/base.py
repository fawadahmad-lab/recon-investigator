"""Provider interface and the registry the run pipeline selects from."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from recon.config import Settings
from recon.errors import ValidationError
from recon.evidence.packet import EvidencePacket
from recon.llm.mock import FaultyMockProvider, MockProvider
from recon.llm.openai_compat import OpenAICompatProvider

PROVIDER_NAMES = ("mock", "faulty_mock", "openai_compat", "groq")


@runtime_checkable
class LLMProvider(Protocol):
    """One packet in, one raw investigator answer out."""

    @property
    def name(self) -> str:
        """Provider name written into `run_meta.json`."""

    @property
    def model_name(self) -> str:
        """Model identifier used in the cache key and request payload."""

    def complete(self, packet: EvidencePacket, error_codes: tuple[str, ...] = ()) -> str:
        """Return the raw JSON answer for one evidence packet."""


def build_provider(settings: Settings, name: str | None = None) -> LLMProvider:
    """Build the configured provider; `groq` is an OpenAI-compatible endpoint."""
    provider_name = (name if name is not None else settings.llm_provider).strip().lower()
    if provider_name not in PROVIDER_NAMES:
        raise ValidationError(f"unknown LLM provider: {provider_name}")
    if provider_name == "mock":
        return MockProvider()
    if provider_name == "faulty_mock":
        return FaultyMockProvider()
    return OpenAICompatProvider(settings, provider_name)
