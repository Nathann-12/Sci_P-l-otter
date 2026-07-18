"""Local-only llama.cpp server lifecycle and OpenAI-compatible chat client."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.local_endpoint import local_http_urlopen


def resolve_llama_server(configured: str | Path | None = None) -> Path | None:
    """Find the release-bundled runtime or an explicitly installed one."""
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    if os.environ.get("SCIPLOTTER_LLAMA_SERVER"):
        candidates.append(Path(os.environ["SCIPLOTTER_LLAMA_SERVER"]))
    try:
        from ai.runtime_manager import RuntimeManager

        managed_runtime = RuntimeManager()
        if managed_runtime.is_installed():
            candidates.append(managed_runtime.runtime_path)
    except Exception:
        pass
    names = ("llama-server.exe", "llama-server")
    bases = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        bases.append(Path(frozen_root))
    bases.extend((Path(sys.executable).resolve().parent, Path(__file__).resolve().parents[1]))
    for base in bases:
        for name in names:
            candidates.extend((base / "runtime" / "llama" / name, base / name))
    for name in names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LlamaCppClient:
    """Starts a bundled ``llama-server`` lazily and never exposes it remotely."""

    supports_json_schema = True

    def __init__(
        self,
        model_path: str | Path,
        *,
        runtime_path: str | Path | None = None,
        model: str = "SciPlotter local model",
        context_size: int = 4096,
        timeout: float = 120.0,
        startup_timeout: float = 90.0,
    ) -> None:
        self.model_path = Path(model_path)
        self.runtime_path = resolve_llama_server(runtime_path)
        self.model = model
        self.context_size = max(2048, int(context_size))
        self.timeout = float(timeout)
        self.startup_timeout = float(startup_timeout)
        self._process: subprocess.Popen | None = None
        self._port = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def available(self) -> bool:
        return bool(self.model_path.is_file() and self.runtime_path is not None)

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        if not self.model_path.is_file():
            raise RuntimeError("The selected local model is not installed.")
        if self.runtime_path is None:
            raise RuntimeError("llama.cpp runtime is missing from this installation.")
        self._port = _free_loopback_port()
        cpu_count = os.cpu_count() or 2
        command = [
            str(self.runtime_path),
            "--model", str(self.model_path),
            "--host", "127.0.0.1",
            "--port", str(self._port),
            "--ctx-size", str(self.context_size),
            "--threads", str(max(1, min(cpu_count - 1, 8))),
            "--parallel", "1",
            "--jinja",
            "--no-webui",
        ]
        kwargs: Dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = subprocess.Popen(command, **kwargs)
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError("The local AI runtime stopped during startup.")
            try:
                with local_http_urlopen(
                    self.base_url + "/health", timeout=1.0
                ) as response:
                    if response.status == 200:
                        return
            except Exception:
                time.sleep(0.2)
        self.stop()
        raise RuntimeError("Timed out while loading the local AI model.")

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    close = stop
    cancel = stop

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        format_json: bool = False,
        json_schema: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.start()
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.1,
            "max_tokens": 500,
            "cache_prompt": True,
        }
        if format_json and json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "sciplotter_reply",
                    "strict": True,
                    "schema": json_schema,
                },
            }
        elif format_json:
            payload["response_format"] = {"type": "json_object"}
        if options:
            payload.update(options)

        def send() -> Dict[str, Any]:
            request = urllib.request.Request(
                self.base_url + "/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with local_http_urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        try:
            data = send()
        except urllib.error.HTTPError as exc:
            # Older pinned llama.cpp builds understand json_object but not the
            # newer OpenAI-compatible json_schema wrapper. Keep those releases
            # usable while current runtimes receive strict per-tool grammar.
            if not json_schema or exc.code not in {400, 404, 415, 422}:
                raise
            payload["response_format"] = {"type": "json_object"}
            data = send()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("The local AI runtime returned no response.")
        return str((choices[0].get("message") or {}).get("content", "")).strip()

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass
