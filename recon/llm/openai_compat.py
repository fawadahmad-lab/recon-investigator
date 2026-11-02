"""OpenAI-compatible chat provider with JSON mode, timeout, backoff and caching."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx

from recon.config import Settings
from recon.errors import LLMError
from recon.evidence.packet import EvidencePacket, packet_hash
from recon.llm.cache import ResponseCache
from recon.llm.prompts import SYSTEM_PROMPT, user_prompt

MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 0.5
RETRY_STATUS_CODES = (429, 500, 502, 503)


class OpenAICompatProvider:
    """Calls one configured chat endpoint; every answer is cached by packet hash."""

    def __init__(
        self,
        settings: Settings,
        name: str = "openai_compat",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Build the provider from settings only: no key, model or URL is hard-coded."""
        self.settings = settings
        self.name = name
        self.model_name = settings.llm_model
        self._sleep = sleep
        self._limit = threading.BoundedSemaphore(max(1, settings.llm_max_concurrency))
        self._client = httpx.Client(
            base_url=settings.llm_base_url.rstrip("/"),
            timeout=settings.llm_timeout_s,
            transport=transport,
        )
        self.cache = (
            ResponseCache(Path(settings.llm_cache_dir), self.model_name, name)
            if settings.llm_cache_dir
            else None
        )

    def close(self) -> None:
        """Release the HTTP client."""
        self._client.close()

    def complete(self, packet: EvidencePacket, error_codes: Sequence[str] = ()) -> str:
        """Return the answer for one packet, from cache when this packet was asked before."""
        codes = tuple(error_codes)
        key = packet_hash(packet)
        if self.cache is not None and not codes:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        raw = self._request(packet, codes)
        if self.cache is not None and not codes:
            self.cache.put(key, raw)
        return raw

    def _request(self, packet: EvidencePacket, codes: tuple[str, ...]) -> str:
        """POST the prompt with bounded concurrency and retry on rate limits."""
        if not self.settings.llm_api_key:
            raise LLMError("LLM_API_KEY is not set; use the mock provider or configure .env")
        body = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(packet, codes)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        with self._limit:
            response = self._post(body, headers)
            for attempt in range(1, MAX_ATTEMPTS):
                if response.status_code not in RETRY_STATUS_CODES:
                    break
                self._sleep(_delay(response, attempt))
                response = self._post(body, headers)
        return _content(response)

    def _post(self, body: dict[str, object], headers: dict[str, str]) -> httpx.Response:
        """Send one request, converting transport failures into provider errors."""
        try:
            return self._client.post("/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as error:
            raise LLMError(f"provider request failed: {type(error).__name__}") from error


def _delay(response: httpx.Response, attempt: int) -> float:
    """Honor a server retry hint, otherwise back off exponentially."""
    hint = response.headers.get("retry-after", "").strip()
    if hint.isdigit():
        return float(hint)
    return BACKOFF_BASE_S * (2 ** (attempt - 1))


def _content(response: httpx.Response) -> str:
    """Extract the assistant message text without echoing credentials."""
    if response.status_code != 200:
        raise LLMError(f"provider returned HTTP {response.status_code}")
    try:
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise LLMError("provider response carries no message content") from error
    if not isinstance(content, str):
        raise LLMError("provider message content is not text")
    return content
