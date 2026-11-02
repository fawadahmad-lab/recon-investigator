"""Tests for the packet-keyed response cache."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recon.errors import LLMError
from recon.evidence.packet import packet_hash
from recon.llm.cache import ResponseCache
from recon.models import EvidencePacket

KEY = "a" * 64
OTHER = "b" * 64


def test_a_cached_answer_is_returned_only_for_its_own_packet_and_model(
    tmp_path: Path,
) -> None:
    """Model and provider are part of the key so two endpoints never share an answer."""
    cache = ResponseCache(tmp_path / "llm", "model-one", "openai_compat")

    assert cache.get(KEY) is None
    path = cache.put(KEY, '{"summary": "one"}')
    assert cache.get(KEY) == '{"summary": "one"}'
    assert path.parent == tmp_path / "llm"
    assert ResponseCache(tmp_path / "llm", "model-two", "openai_compat").get(KEY) is None
    assert ResponseCache(tmp_path / "llm", "model-one", "groq").get(KEY) is None


def test_the_record_names_the_packet_provider_and_model(tmp_path: Path) -> None:
    """A cache file is self-describing for the audit trail."""
    cache = ResponseCache(tmp_path, "llama-test", "groq")
    path = cache.put(KEY, "raw text")

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record == {
        "packet_hash": KEY,
        "provider": "groq",
        "model": "llama-test",
        "raw": "raw text",
    }


def test_a_rewritten_answer_leaves_no_temporary_file(tmp_path: Path) -> None:
    """Atomic replacement keeps the cache directory free of partial writes."""
    cache = ResponseCache(tmp_path, "m", "groq")
    cache.put(KEY, "first")
    cache.put(KEY, "second")

    assert cache.get(KEY) == "second"
    assert [item.name for item in tmp_path.iterdir()] == [
        cache.path(KEY).name,
    ]


@pytest.mark.parametrize("key", ["", "../escape", "short", "A" * 64, "z" * 64])
def test_a_key_that_is_not_a_lowercase_sha256_is_refused(tmp_path: Path, key: str) -> None:
    """Cache keys come from packet hashes, and anything else cannot name a file."""
    cache = ResponseCache(tmp_path, "m", "groq")

    with pytest.raises(LLMError, match="SHA-256 packet hash"):
        cache.get(key)
    with pytest.raises(LLMError, match="SHA-256 packet hash"):
        cache.put(key, "raw")


def test_a_corrupt_cache_file_is_reported_not_ignored(tmp_path: Path) -> None:
    """A damaged answer must not look like a cache miss and silently re-request."""
    cache = ResponseCache(tmp_path, "m", "groq")
    cache.put(KEY, "raw")
    cache.path(KEY).write_text("{nope", encoding="utf-8")

    with pytest.raises(LLMError, match="not valid JSON"):
        cache.get(KEY)


def test_real_packets_get_their_own_cache_file(
    tmp_path: Path, packets: dict[str, EvidencePacket]
) -> None:
    """One run cannot reuse another finding's answer: the key is the packet itself."""
    cache = ResponseCache(tmp_path, "m", "groq")

    for packet in packets.values():
        cache.put(packet_hash(packet), packet.finding_id)

    assert len(list(tmp_path.iterdir())) == len(packets)
    first = next(iter(packets.values()))
    assert cache.get(packet_hash(first)) == first.finding_id
