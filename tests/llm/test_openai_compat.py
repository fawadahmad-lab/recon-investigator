"""Tests for the OpenAI-compatible provider using a stubbed HTTP layer."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from recon.config import Settings, get_settings
from recon.errors import LLMError
from recon.evidence.packet import packet_hash
from recon.llm.openai_compat import BACKOFF_BASE_S, MAX_ATTEMPTS, OpenAICompatProvider
from recon.llm.prompts import SYSTEM_PROMPT, user_prompt
from recon.llm.schema import parse_investigation
from recon.models import EvidencePacket

CONTENT = json.dumps(
    {
        "summary": "L-000042: typo or transposition",
        "likely_cause": "unknown",
        "explanation": "The packet does not separate the causes.",
        "cited_facts": [],
        "recommended_action": "investigate",
        "action_detail": "Ask the preparer for the source document.",
        "confidence": "low",
        "uncertainties": ["No further evidence in the packet."],
    },
    sort_keys=True,
)
API_KEY = "test-key"


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    """Build isolated settings so ambient `.env` values cannot leak into a test."""
    base: dict[str, object] = {
        "llm_api_key": API_KEY,
        "llm_base_url": "http://stub/v1",
        "llm_model": "stub-model",
        "llm_cache_dir": "",
        "llm_max_concurrency": 2,
        "llm_timeout_s": 5,
    }
    base.update(overrides)
    return replace(get_settings(), **base)


class Stub:
    """A scripted HTTP layer plus the requests it recorded."""

    def __init__(self, script: list[httpx.Response]) -> None:
        self.script = script
        self.requests: list[httpx.Request] = []
        self._in_flight = 0
        self._peak = 0
        self._lock = threading.Lock()

    @property
    def peak_concurrency(self) -> int:
        """Highest number of requests the provider held open at once."""
        return self._peak

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Serve the next scripted response, repeating the last one once spent."""
        with self._lock:
            self.requests.append(request)
            self._in_flight += 1
            self._peak = max(self._peak, self._in_flight)
        try:
            if len(self.requests) > 1:
                threading.Event().wait(0.01)
            return self.script[min(len(self.requests), len(self.script)) - 1]
        finally:
            with self._lock:
                self._in_flight -= 1

    def body(self, index: int = 0) -> dict:
        """Decode one recorded request body."""
        return json.loads(self.requests[index].content.decode("utf-8"))


def _provider(
    tmp_path: Path, script: list[httpx.Response], sleeps: list[float], **overrides: object
) -> tuple[OpenAICompatProvider, Stub]:
    """Wire a provider onto a stub transport and a recorded sleep function."""
    stub = Stub(script)
    provider = OpenAICompatProvider(
        _settings(tmp_path, **overrides),
        transport=httpx.MockTransport(stub.handler),
        sleep=sleeps.append,
    )
    return provider, stub


def _ok(content: str = CONTENT) -> httpx.Response:
    """Build a chat completion response carrying one assistant message."""
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture(name="packet")
def _packet(packets: dict[str, EvidencePacket]) -> EvidencePacket:
    """The amount-mismatch packet every provider test asks about."""
    return packets["amount_mismatch"]


def test_the_request_posts_the_packet_in_json_mode(tmp_path: Path, packet: EvidencePacket) -> None:
    """One call sends the system prompt, the packet, JSON mode and the temperature."""
    provider, stub = _provider(tmp_path, [_ok()], [])

    content = provider.complete(packet)

    assert content == CONTENT
    assert stub.requests[0].url.path == "/v1/chat/completions"
    assert stub.requests[0].headers["authorization"] == f"Bearer {API_KEY}"
    body = stub.body()
    assert body["model"] == "stub-model"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert body["messages"][1]["role"] == "user"
    assert parse_investigation(content).confidence is not None


def test_the_prompt_never_carries_the_api_key(tmp_path: Path, packet: EvidencePacket) -> None:
    """Credentials stay in the header, so no prompt text can leak them."""
    provider, stub = _provider(tmp_path, [_ok()], [])
    provider.complete(packet)

    assert API_KEY not in json.dumps(stub.body())
    assert API_KEY not in user_prompt(packet)
    assert API_KEY not in SYSTEM_PROMPT


def test_a_rate_limit_is_retried_after_backoff(tmp_path: Path, packet: EvidencePacket) -> None:
    """A single 429 costs one recorded sleep and one extra request."""
    sleeps: list[float] = []
    provider, stub = _provider(tmp_path, [httpx.Response(429), _ok()], sleeps)

    assert provider.complete(packet) == CONTENT
    assert len(stub.requests) == 2
    assert sleeps == [BACKOFF_BASE_S]


def test_a_retry_after_hint_is_honoured(tmp_path: Path, packet: EvidencePacket) -> None:
    """The server's own wait time wins over the exponential schedule."""
    sleeps: list[float] = []
    responses = [httpx.Response(429, headers={"Retry-After": "3"}), _ok()]
    provider, stub = _provider(tmp_path, responses, sleeps)

    provider.complete(packet)

    assert sleeps == [3.0]


def test_a_persistent_rate_limit_raises_after_the_attempt_budget(
    tmp_path: Path, packet: EvidencePacket
) -> None:
    """The provider stops after its budget instead of looping on a rate limit."""
    sleeps: list[float] = []
    provider, stub = _provider(tmp_path, [httpx.Response(429)], sleeps)

    with pytest.raises(LLMError, match="HTTP 429"):
        provider.complete(packet)

    assert len(stub.requests) == MAX_ATTEMPTS
    assert sleeps == [BACKOFF_BASE_S, BACKOFF_BASE_S * 2]


def test_a_server_error_is_retried_then_reported(tmp_path: Path, packet: EvidencePacket) -> None:
    """5xx responses share the retry policy with rate limits."""
    provider, stub = _provider(tmp_path, [httpx.Response(503)], [])

    with pytest.raises(LLMError, match="HTTP 503"):
        provider.complete(packet)

    assert len(stub.requests) == MAX_ATTEMPTS


def test_a_client_error_is_reported_once(tmp_path: Path, packet: EvidencePacket) -> None:
    """A 400 is not retried and its message carries no credential."""
    body = httpx.Response(400, json={"error": f"bad key {API_KEY}"})
    provider, stub = _provider(tmp_path, [body], [])

    with pytest.raises(LLMError, match="HTTP 400") as caught:
        provider.complete(packet)

    assert API_KEY not in str(caught.value)
    assert len(stub.requests) == 1


def test_a_missing_api_key_stops_before_the_transport(
    tmp_path: Path, packet: EvidencePacket
) -> None:
    """A configuration error never reaches the transport."""
    provider, stub = _provider(tmp_path, [_ok()], [], llm_api_key=None)

    with pytest.raises(LLMError, match="LLM_API_KEY is not set"):
        provider.complete(packet)

    assert stub.requests == []


def test_a_response_without_message_content_is_a_provider_error(
    tmp_path: Path, packet: EvidencePacket
) -> None:
    """An unexpected payload shape is reported instead of parsed as text."""
    empty = _provider(tmp_path, [httpx.Response(200, json={"choices": []})], [])
    with pytest.raises(LLMError, match="no message content"):
        empty[0].complete(packet)

    nomessage = _provider(tmp_path, [httpx.Response(200, json={"choices": [{"message": {}}]})], [])
    with pytest.raises(LLMError, match="no message content"):
        nomessage[0].complete(packet)

    notext = _provider(
        tmp_path, [httpx.Response(200, json={"choices": [{"message": {"content": 12}}]})], []
    )
    with pytest.raises(LLMError, match="not text"):
        notext[0].complete(packet)


def test_a_transport_failure_becomes_a_provider_error(
    tmp_path: Path, packet: EvidencePacket
) -> None:
    """Connection problems surface as `LLMError`, never as a bare httpx exception."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = OpenAICompatProvider(_settings(tmp_path), transport=httpx.MockTransport(refuse))

    with pytest.raises(LLMError, match="provider request failed"):
        provider.complete(packet)


def test_the_second_answer_for_a_packet_comes_from_disk(
    tmp_path: Path, packet: EvidencePacket
) -> None:
    """The cache is keyed by packet hash and model, so a repeat run costs nothing."""
    cache = tmp_path / "cache"
    provider, stub = _provider(tmp_path, [_ok()], [], llm_cache_dir=str(cache))

    first = provider.complete(packet)
    second = provider.complete(packet)

    assert first == second == CONTENT
    assert len(stub.requests) == 1
    assert provider.cache is not None
    assert list(cache.iterdir()) == [provider.cache.path(packet_hash(packet))]


def test_another_model_never_reads_a_cached_answer(tmp_path: Path, packet: EvidencePacket) -> None:
    """A model switch invalidates the cache instead of serving the old model's text."""
    cache = tmp_path / "cache"
    provider, stub = _provider(tmp_path, [_ok(), _ok("second")], [], llm_cache_dir=str(cache))
    provider.complete(packet)

    other = OpenAICompatProvider(
        _settings(tmp_path, llm_model="other-model", llm_cache_dir=str(cache)),
        transport=httpx.MockTransport(stub.handler),
    )

    assert other.complete(packet) == "second"
    assert len(stub.requests) == 2


def test_a_retry_answer_is_never_served_from_or_written_to_the_cache(
    tmp_path: Path, packet: EvidencePacket
) -> None:
    """A corrected retry must not be masked by, or overwrite, the cached first answer."""
    provider, stub = _provider(
        tmp_path, [_ok(), _ok("retry text")], [], llm_cache_dir=str(tmp_path / "cache")
    )

    assert provider.complete(packet) == CONTENT
    assert provider.complete(packet, ("bad_enum",)) == "retry text"
    assert provider.complete(packet) == CONTENT
    assert len(stub.requests) == 2


def test_the_concurrency_limit_is_enforced(
    tmp_path: Path, packets: dict[str, EvidencePacket]
) -> None:
    """Five findings never mean more than `LLM_MAX_CONCURRENCY` open requests."""
    provider, stub = _provider(tmp_path, [_ok()], [], llm_max_concurrency=2)
    asked = list(packets.values())[:5]

    with ThreadPoolExecutor(max_workers=5) as pool:
        answers = list(pool.map(lambda item: provider.complete(item, ("bad_enum",)), asked))

    assert answers == [CONTENT] * 5
    assert stub.peak_concurrency <= 2
    assert len(stub.requests) == 5
