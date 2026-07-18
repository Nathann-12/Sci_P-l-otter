from __future__ import annotations

import json
import urllib.error

import ai.llama_cpp_client as client_module
from ai.llama_cpp_client import LlamaCppClient, resolve_llama_server


class _Process:
    def __init__(self):
        self.terminated = False

    def poll(self):
        return None if not self.terminated else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


class _Response:
    def __init__(self, payload=None):
        self.status = 200
        self.payload = payload or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_resolve_llama_server_accepts_configured_runtime(tmp_path):
    runtime = tmp_path / "llama-server.exe"
    runtime.write_bytes(b"binary")
    assert resolve_llama_server(runtime) == runtime.resolve()


def test_client_binds_loopback_and_requests_json(monkeypatch, tmp_path):
    runtime = tmp_path / "llama-server.exe"
    model = tmp_path / "model.gguf"
    runtime.write_bytes(b"runtime")
    model.write_bytes(b"model")
    commands = []
    requests = []
    process = _Process()
    monkeypatch.setattr(client_module, "_free_loopback_port", lambda: 23456)
    monkeypatch.setattr(
        client_module.subprocess,
        "Popen",
        lambda command, **kwargs: commands.append((command, kwargs)) or process,
    )

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        if isinstance(request, str):
            return _Response()
        return _Response({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})

    monkeypatch.setattr(client_module, "local_http_urlopen", fake_urlopen)
    client = LlamaCppClient(model, runtime_path=runtime)

    reply = client.chat([{"role": "user", "content": "hi"}], format_json=True)

    assert reply == '{"answer":"ok"}'
    command = commands[0][0]
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert "--no-webui" in command
    request_payload = json.loads(requests[-1].data)
    assert request_payload["response_format"] == {"type": "json_object"}
    client.close()
    assert process.terminated


def test_client_requests_strict_schema_and_falls_back_for_old_runtime(
    monkeypatch, tmp_path
):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"model")
    requests = []

    def fake_urlopen(request, timeout=None):
        requests.append(json.loads(request.data))
        if len(requests) == 1:
            raise urllib.error.HTTPError(request.full_url, 400, "unsupported", None, None)
        return _Response({"choices": [{"message": {"content": '{"answer":"ok"}'}}]})

    monkeypatch.setattr(client_module, "local_http_urlopen", fake_urlopen)
    client = LlamaCppClient(model)
    monkeypatch.setattr(client, "start", lambda: None)
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    assert client.chat([], format_json=True, json_schema=schema) == '{"answer":"ok"}'
    strict = requests[0]["response_format"]
    assert strict["type"] == "json_schema"
    assert strict["json_schema"]["strict"] is True
    assert strict["json_schema"]["schema"] == schema
    assert requests[1]["response_format"] == {"type": "json_object"}
