"""Tiny Ollama chat client over the standard library (no extra dependency).

Ollama exposes a local HTTP API on 127.0.0.1:11434. We use ``/api/chat`` in
non-streaming mode and, crucially, ``format: "json"`` which forces *any* model
(even a 2B one) to emit a single valid JSON object — that is what makes the
prompt-based tool protocol in :mod:`ai.agent` reliable on tiny local models.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ai.local_endpoint import (
    DEFAULT_LOCAL_AI_BASE_URL,
    local_http_urlopen,
    normalize_local_http_base_url,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = DEFAULT_LOCAL_AI_BASE_URL
# Lightest broadly-available tool-router. Configurable per install.
DEFAULT_MODEL = "gemma2:2b"


class OllamaClient:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = normalize_local_http_base_url(base_url)
        self.timeout = float(timeout)

    # ----------------------------------------------------------------- probing
    def available(self) -> bool:
        """True if an Ollama server answers locally (never raises)."""
        try:
            self._get("/api/tags", timeout=3.0)
            return True
        except Exception:
            logger.debug("Ollama not reachable at %s", self.base_url, exc_info=True)
            return False

    def list_models(self, timeout: float = 5.0) -> List[str]:
        """Return locally installed models, using a caller-bounded probe timeout."""
        try:
            data = self._get("/api/tags", timeout=max(0.05, float(timeout)))
            return [str(m.get("name", "")) for m in data.get("models", []) if m.get("name")]
        except Exception:
            logger.debug("Ollama list_models failed", exc_info=True)
            return []

    # -------------------------------------------------------------------- chat
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        format_json: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Return the assistant message content for a non-streaming chat turn."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if format_json:
            payload["format"] = "json"
        if options:
            payload["options"] = options
        data = self._post("/api/chat", payload)
        return str((data.get("message") or {}).get("content", "")).strip()

    # ----------------------------------------------------------------- private
    def _get(self, path: str, timeout: float) -> Dict[str, Any]:
        request = urllib.request.Request(self.base_url + path, method="GET")
        with local_http_urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with local_http_urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
