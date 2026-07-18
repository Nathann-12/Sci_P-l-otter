from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ai.model_catalog import ModelPack
from ai.readiness import AIReadiness, inspect_bundled_ai


def _pack(*, minimum=2.0, recommended=4.0) -> ModelPack:
    return ModelPack(
        pack_id="test-pack",
        display_name="Test local model",
        model_id="test/model",
        filename="test.gguf",
        download_url="https://example.invalid/test.gguf",
        sha256="0" * 64,
        size_bytes=10,
        min_ram_gb=minimum,
        recommended_ram_gb=recommended,
        context_size=2048,
        quantization="test",
        license_name="Apache-2.0",
        license_url="https://example.invalid/license",
        source_url="https://example.invalid/model",
        description="fixture",
        release_status="preview",
        router_protocol="2.0",
        tool_schema_version="1.4",
    )


class _Models:
    def __init__(self, pack: ModelPack, root: Path, installed: bool) -> None:
        self.pack = pack
        self.root = root
        self.installed = installed

    def packs(self):
        return (self.pack,)

    def recommended_pack(self, _ram):
        return self.pack

    def is_installed(self, pack_id):
        return pack_id == self.pack.pack_id and self.installed

    def model_path(self, _pack_id):
        return self.root / self.pack.filename


class _Runtime:
    def __init__(self, path: Path, installed: bool) -> None:
        self.runtime_path = path
        self.installed = installed

    def is_installed(self):
        return self.installed


def _inspect(tmp_path, *, model=False, runtime=False, ram=8.0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    pack = _pack()
    model_path = tmp_path / pack.filename
    runtime_path = tmp_path / "llama-server.exe"
    if model:
        model_path.write_bytes(b"model")
    if runtime:
        runtime_path.write_bytes(b"runtime")
    return inspect_bundled_ai(
        pack.pack_id,
        manager=_Models(pack, tmp_path, model),
        runtime_manager=_Runtime(runtime_path, runtime),
        ram_gb=ram,
        runtime_resolver=lambda _configured: None,
    )


def test_readiness_reports_both_missing_components(tmp_path):
    report = _inspect(tmp_path)

    assert report.state == "model_and_runtime_missing"
    assert report.missing == ("model", "runtime")
    assert report.ready is False


def test_readiness_distinguishes_model_and_runtime_gaps(tmp_path):
    assert _inspect(tmp_path / "model-only", model=True).state == "runtime_missing"
    assert _inspect(tmp_path / "runtime-only", runtime=True).state == "model_missing"


def test_readiness_is_ready_only_when_stack_and_memory_are_usable(tmp_path):
    report = _inspect(tmp_path, model=True, runtime=True, ram=8)

    assert report.ready is True
    assert report.state == "ready"
    assert report.model_path is not None
    assert report.runtime_path is not None
    assert "on-device" in report.detail


def test_readiness_blocks_below_minimum_ram_and_warns_below_recommended(tmp_path):
    blocked = _inspect(tmp_path / "blocked", model=True, runtime=True, ram=1)
    limited = _inspect(tmp_path / "limited", model=True, runtime=True, ram=3)

    assert blocked.state == "insufficient_memory"
    assert blocked.ready is False
    assert limited.ready is True
    assert "recommended" in limited.warning.casefold()


def test_low_ram_blocks_setup_before_components_are_downloaded(tmp_path):
    report = _inspect(tmp_path, model=False, runtime=False, ram=1)

    assert report.state == "insufficient_memory"
    assert report.missing == ()


def test_unverified_custom_runtime_never_counts_as_ready(tmp_path):
    pack = _pack()
    runtime = tmp_path / "custom-llama.exe"
    runtime.write_bytes(b"not really llama.cpp")
    report = inspect_bundled_ai(
        pack.pack_id,
        runtime_path=runtime,
        manager=_Models(pack, tmp_path, True),
        runtime_manager=_Runtime(tmp_path / "managed.exe", False),
        ram_gb=8,
        runtime_resolver=lambda _configured: runtime,
    )

    assert report.ready is False
    assert report.state == "unverified_runtime"
    assert report.runtime_path is None
    assert report.missing == ("runtime",)


def test_incompatible_router_contract_is_blocked(tmp_path):
    pack = replace(_pack(), tool_schema_version="stale")
    report = inspect_bundled_ai(
        pack.pack_id,
        manager=_Models(pack, tmp_path, False),
        runtime_manager=_Runtime(tmp_path / "runtime.exe", False),
        ram_gb=8,
        runtime_resolver=lambda _configured: None,
    )

    assert report.state == "incompatible_model"
    assert report.ready is False


def test_readiness_rejects_unknown_pack(tmp_path):
    pack = _pack()
    report = inspect_bundled_ai(
        "removed-pack",
        manager=_Models(pack, tmp_path, False),
        runtime_manager=_Runtime(tmp_path / "runtime.exe", False),
        ram_gb=8,
        runtime_resolver=lambda _configured: None,
    )

    assert report.state == "unknown_model"
    assert report.ready is False


def test_setup_button_is_shown_when_dock_is_unavailable():
    from UI.docks.ai_dock import AiAssistantDock

    dock = AiAssistantDock()
    requested = []
    dock.manage_models_requested.connect(lambda: requested.append(True))

    dock.set_available(False, "Install the local model")

    assert not dock.input_edit.isEnabled()
    assert not dock.setup_button.isHidden()
    assert "Install" in dock.status_label.text()
    dock.setup_button.click()
    assert requested == [True]


def test_setup_error_never_marks_the_dock_ready(monkeypatch):
    from PySide6.QtCore import QObject
    from UI.docks.ai_dock import AiAssistantDock
    from ai.readiness import AISetupRequired
    from main_window_ai_mixin import MainWindowAIMixin

    class _Host(QObject, MainWindowAIMixin):
        def __init__(self, dock):
            super().__init__()
            self.ai_dock = dock

    dock = AiAssistantDock()
    host = _Host(dock)
    report = AIReadiness(
        state="model_missing",
        ready=False,
        detail="Install the private model",
        pack_id="test-pack",
    )
    monkeypatch.setattr(host, "_build_ai_client", lambda _cfg: (_ for _ in ()).throw(AISetupRequired(report)))

    assert host.init_ai_assistant() is False
    assert dock.status_label.text() == "Install the private model"
    assert not dock.setup_button.isHidden()


def test_explicit_ollama_backend_requires_configured_model(monkeypatch):
    from ai.ollama_client import OllamaClient
    from main_window_ai_mixin import MainWindowAIMixin
    from settings import AIConfig

    host = MainWindowAIMixin()
    monkeypatch.setattr(OllamaClient, "list_models", lambda self, timeout=5.0: [])

    try:
        host._build_ai_client(AIConfig(backend="ollama", model="missing:latest"))
    except Exception as exc:
        assert getattr(exc, "readiness").state == "ollama_unavailable"
    else:
        raise AssertionError("an unavailable Ollama model must not produce a ready client")

    monkeypatch.setattr(
        OllamaClient,
        "list_models",
        lambda self, timeout=5.0: ["available:latest"],
    )
    client = host._build_ai_client(AIConfig(backend="ollama", model="available"))
    assert client.model == "available"
