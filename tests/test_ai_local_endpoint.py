from __future__ import annotations

import json
import urllib.request

import pytest

from ai.local_endpoint import (
    DEFAULT_LOCAL_AI_BASE_URL,
    LocalEndpointError,
    local_http_urlopen,
    normalize_local_http_base_url,
    parse_local_http_base_url,
)
from ai.ollama_client import OllamaClient
from settings import AIConfig, SettingsManager


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("HTTP://LOCALHOST:11434/", "http://localhost:11434"),
        ("https://127.12.34.56:443/ollama/", "https://127.12.34.56:443/ollama"),
        ("http://[::1]:11434", "http://[::1]:11434"),
    ),
)
def test_local_endpoint_accepts_and_canonicalizes_loopback_urls(value, expected):
    endpoint = parse_local_http_base_url(value)

    assert endpoint.url == expected
    assert normalize_local_http_base_url(value) == expected


@pytest.mark.parametrize(
    "value",
    (
        "",
        "localhost:11434",
        "ftp://127.0.0.1:11434",
        "http://example.com:11434",
        "http://192.168.1.10:11434",
        "http://0.0.0.0:11434",
        "http://localhost.evil:11434",
        "http://user:secret@localhost:11434",
        "http://localhost:99999",
        "http://localhost:11434?remote=true",
        "http://localhost:11434/#fragment",
        "http://localhost:11434/a path",
        "http://[::ffff:127.0.0.1]:11434",
        "http://[::1%25ethernet]:11434",
    ),
)
def test_local_endpoint_rejects_nonlocal_or_ambiguous_urls(value):
    with pytest.raises(LocalEndpointError):
        parse_local_http_base_url(value)


def test_ai_config_fails_closed_for_invalid_endpoint():
    config = AIConfig(base_url="https://models.example.org/api")

    assert config.base_url == DEFAULT_LOCAL_AI_BASE_URL


def test_settings_load_and_update_normalize_ai_endpoint(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"ai": {"backend": "ollama", "base_url": "http://10.0.0.8:11434"}}),
        encoding="utf-8",
    )
    manager = SettingsManager(str(config_path))
    assert manager.get_ai().base_url == DEFAULT_LOCAL_AI_BASE_URL

    manager.update_ai(base_url="HTTPS://[::1]:8443/ollama/")
    assert manager.get_ai().base_url == "https://[::1]:8443/ollama"

    manager.update_ai(base_url="http://research-server:11434")
    assert manager.get_ai().base_url == DEFAULT_LOCAL_AI_BASE_URL


def test_ollama_client_rejects_remote_endpoint_at_network_boundary():
    with pytest.raises(LocalEndpointError):
        OllamaClient(base_url="http://api.example.org:11434")

    assert OllamaClient(base_url="http://127.255.1.2:11434/").base_url == (
        "http://127.255.1.2:11434"
    )


def test_ollama_model_probe_honors_caller_timeout(monkeypatch):
    client = OllamaClient()
    calls = []
    monkeypatch.setattr(
        client,
        "_get",
        lambda path, timeout: calls.append((path, timeout))
        or {"models": [{"name": "local-router"}]},
    )

    assert client.list_models(timeout=1.0) == ["local-router"]
    assert calls == [("/api/tags", 1.0)]


def test_local_inference_opener_disables_proxies_and_redirects(monkeypatch):
    captured = {}
    sentinel = object()

    class _Opener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return sentinel

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return _Opener()

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat")

    assert local_http_urlopen(request, timeout=0.2) is sentinel
    proxy = next(
        handler
        for handler in captured["handlers"]
        if isinstance(handler, urllib.request.ProxyHandler)
    )
    redirect = next(
        handler
        for handler in captured["handlers"]
        if isinstance(handler, urllib.request.HTTPRedirectHandler)
    )
    assert proxy.proxies == {}
    assert captured["timeout"] == 0.2
    with pytest.raises(LocalEndpointError, match="redirect"):
        redirect.redirect_request(
            request,
            None,
            307,
            "Temporary Redirect",
            {},
            "https://example.org/leak",
        )
