"""On-disk provider response cache keyed by packet hash plus model name."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from recon.errors import LLMError

_HASH_RE = re.compile(r"[0-9a-f]{64}")


class ResponseCache:
    """Store one raw provider answer per packet and model."""

    def __init__(self, directory: str | Path, model: str, provider: str) -> None:
        """Point the cache at a directory and the model whose answers it holds."""
        self.directory = Path(directory)
        self.model = model
        self.provider = provider

    def path(self, key: str) -> Path:
        """Return the cache file for one packet hash without trusting the caller's path."""
        if not _HASH_RE.fullmatch(key):
            raise LLMError("cache key must be a SHA-256 packet hash")
        model_key = hashlib.sha256(f"{self.provider}|{self.model}".encode("utf-8")).hexdigest()[:16]
        return self.directory / f"{key}-{model_key}.json"

    def get(self, key: str) -> str | None:
        """Return the cached answer, or None when this packet was never requested."""
        path = self.path(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as error:
            raise LLMError(f"cache file {path.name} is not valid JSON: {error.msg}") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("raw"), str):
            raise LLMError(f"cache file {path.name} is not a provider record")
        return str(payload["raw"])

    def put(self, key: str, raw: str) -> Path:
        """Write the answer atomically so concurrent runs never read a partial file."""
        path = self.path(key)
        self.directory.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "packet_hash": key,
            "provider": self.provider,
            "model": self.model,
            "raw": raw,
        }
        temp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        temp.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        temp.replace(path)
        return path
