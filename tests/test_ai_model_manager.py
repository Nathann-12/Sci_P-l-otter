from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest
from PySide6.QtWidgets import QApplication

import ai.model_manager as manager_module
from ai.model_catalog import BUILTIN_MODEL_PACKS, ModelPack
from ai.model_manager import ModelInstallError, ModelManager
from ai.readiness import AIReadiness
from ai.runtime_manager import RuntimeManager, RuntimePackage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tiny_pack(monkeypatch):
    payload = b"tiny verified gguf fixture"
    pack = ModelPack(
        pack_id="tiny-test",
        display_name="Tiny test pack",
        model_id="test/tiny",
        filename="tiny.gguf",
        download_url="https://example.invalid/tiny.gguf",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        min_ram_gb=1,
        recommended_ram_gb=2,
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
    monkeypatch.setattr(manager_module, "get_model_pack", lambda pack_id: pack)
    monkeypatch.setattr(manager_module, "model_packs", lambda: (pack,))
    return pack, payload


def test_builtin_catalog_pins_https_size_hash_and_commercial_license():
    assert len(BUILTIN_MODEL_PACKS) >= 2
    for pack in BUILTIN_MODEL_PACKS:
        assert pack.download_url.startswith("https://")
        assert len(pack.sha256) == 64
        int(pack.sha256, 16)
        assert pack.size_bytes > 100_000_000
        assert pack.commercial_use is True
        assert pack.license_name == "Apache-2.0"
        assert pack.release_status in {"preview", "release"}
        assert pack.router_protocol == "2.0"
        assert pack.tool_schema_version == "1.4"


def test_install_rejects_wrong_hash_without_leaving_model(tmp_path, tiny_pack):
    pack, payload = tiny_pack
    bad = tmp_path / "bad.gguf"
    bad.write_bytes(b"x" * len(payload))
    manager = ModelManager(tmp_path / "models")

    with pytest.raises(ModelInstallError, match="SHA-256"):
        manager.install_model_file(pack.pack_id, bad)

    assert not manager.model_path(pack.pack_id).exists()


def test_cancel_interrupts_model_verification_without_partial_install(tmp_path, tiny_pack):
    pack, payload = tiny_pack
    source = tmp_path / pack.filename
    source.write_bytes(payload)
    manager = ModelManager(tmp_path / "models")

    with pytest.raises(ModelInstallError, match="cancelled"):
        manager.install_model_file(
            pack.pack_id,
            source,
            cancelled=lambda: True,
        )

    assert not manager.model_path(pack.pack_id).exists()


def test_offline_export_and_import_round_trip(tmp_path, tiny_pack):
    pack, payload = tiny_pack
    source = tmp_path / pack.filename
    source.write_bytes(payload)
    first = ModelManager(tmp_path / "first")
    first.install_model_file(pack.pack_id, source)

    bundle = first.create_offline_bundle(pack.pack_id, tmp_path / "portable.scimodel")
    second = ModelManager(tmp_path / "second")
    installed = second.install_offline_bundle(bundle)

    assert installed.read_bytes() == payload
    assert second.is_installed(pack.pack_id)
    with zipfile.ZipFile(bundle) as archive:
        assert {
            "manifest.json", "LICENSE-model.txt", "MODEL-NOTICE.txt", pack.filename
        } <= set(archive.namelist())


def test_offline_import_rejects_traversal_path(tmp_path, tiny_pack):
    pack, _payload = tiny_pack
    bundle = tmp_path / "unsafe.scimodel"
    manifest = {"pack": pack.to_dict()}
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("../escape.gguf", b"bad")

    with pytest.raises(ModelInstallError, match="Unsafe path"):
        ModelManager(tmp_path / "models").install_offline_bundle(bundle)


@pytest.mark.parametrize(
    "member_name",
    (
        r"..\escape.gguf",
        r"nested\..\..\escape.gguf",
        r"C:\escape.gguf",
        r"\\server\share\escape.gguf",
    ),
)
def test_offline_import_rejects_windows_path_escape(
    tmp_path, tiny_pack, member_name
):
    pack, _payload = tiny_pack
    bundle = tmp_path / "unsafe-windows.scimodel"
    manifest = {"pack": pack.to_dict()}
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr(member_name, b"bad")

    with pytest.raises(ModelInstallError, match="Unsafe path"):
        ModelManager(tmp_path / "models").install_offline_bundle(bundle)


def test_offline_import_rejects_casefolded_destination_collision(
    tmp_path, tiny_pack
):
    pack, _payload = tiny_pack
    bundle = tmp_path / "duplicate.scimodel"
    manifest = {"pack": pack.to_dict()}
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("MANIFEST.JSON", json.dumps(manifest))

    with pytest.raises(ModelInstallError, match="Duplicate path"):
        ModelManager(tmp_path / "models").install_offline_bundle(bundle)


@pytest.mark.parametrize("tamper", ("catalog", "pack"))
def test_installed_model_rejects_stale_or_tampered_manifest(
    tmp_path, tiny_pack, tamper
):
    pack, payload = tiny_pack
    source = tmp_path / pack.filename
    source.write_bytes(payload)
    manager = ModelManager(tmp_path / "models")
    manager.install_model_file(pack.pack_id, source)
    manifest = manager.pack_dir(pack.pack_id) / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if tamper == "catalog":
        data["catalog_version"] = "stale"
    else:
        data["pack"]["display_name"] = "tampered"
    manifest.write_text(json.dumps(data), encoding="utf-8")

    assert manager.is_installed(pack.pack_id) is False


def test_installed_model_accepts_legacy_preview_contract_defaults(tmp_path, tiny_pack):
    pack, payload = tiny_pack
    source = tmp_path / pack.filename
    source.write_bytes(payload)
    manager = ModelManager(tmp_path / "models")
    manager.install_model_file(pack.pack_id, source)
    manifest = manager.pack_dir(pack.pack_id) / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for key in ("release_status", "router_protocol", "tool_schema_version"):
        data["pack"].pop(key)
    manifest.write_text(json.dumps(data), encoding="utf-8")

    assert manager.is_installed(pack.pack_id) is True


def test_recommendation_uses_small_pack_on_low_memory_and_larger_on_high():
    manager = ModelManager("unused")
    assert manager.recommended_pack(4).pack_id == "qwen3-0.6b-q8"
    assert manager.recommended_pack(8).pack_id == "qwen3-1.7b-q4"


def test_full_installer_read_only_model_root_is_recognised(tmp_path, tiny_pack):
    pack, payload = tiny_pack
    source = tmp_path / pack.filename
    source.write_bytes(payload)
    bundled_root = tmp_path / "application" / "models"
    ModelManager(bundled_root).install_model_file(pack.pack_id, source)

    manager = ModelManager(tmp_path / "user-models", read_roots=[bundled_root])

    assert manager.is_installed(pack.pack_id)
    assert manager.model_path(pack.pack_id).parent == bundled_root / pack.pack_id


def test_cancelled_offline_export_removes_partial_file(tmp_path, tiny_pack):
    pack, payload = tiny_pack
    source = tmp_path / pack.filename
    source.write_bytes(payload)
    manager = ModelManager(tmp_path / "models")
    manager.install_model_file(pack.pack_id, source)
    destination = tmp_path / "cancelled.scimodel"

    with pytest.raises(ModelInstallError, match="cancelled"):
        manager.create_offline_bundle(
            pack.pack_id, destination, cancelled=lambda: True
        )

    assert not destination.exists()
    assert not destination.with_suffix(".scimodel.part").exists()


def test_model_manager_dialog_exposes_download_runtime_and_offline_paths(qapp, tmp_path):
    from dialogs.ai_model_manager_dialog import AiModelManagerDialog

    dialog = AiModelManagerDialog(manager=ModelManager(tmp_path / "models"))

    assert dialog.table.rowCount() == len(BUILTIN_MODEL_PACKS)
    assert dialog.download_button.text() == "Download & verify"
    assert "runtime" in dialog.runtime_button.text().casefold()
    assert "offline" in dialog.import_button.text().casefold()
    dialog.close()


def _empty_runtime_manager(tmp_path):
    package = RuntimePackage(
        runtime_id="dialog-runtime",
        version="test",
        platform="windows",
        architecture="x86_64",
        filename="runtime.zip",
        server_filename="llama-server.exe",
        download_url="https://example.invalid/runtime.zip",
        sha256="1" * 64,
        size_bytes=20,
        license_name="MIT",
        license_url="https://example.invalid/license",
        source_url="https://example.invalid/runtime",
    )
    return RuntimeManager(tmp_path / "runtime", package)


def _installed_runtime_manager(tmp_path):
    manager = _empty_runtime_manager(tmp_path)
    archive = tmp_path / "dialog-runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("llama-server.exe", b"runtime")
        bundle.writestr("llama.dll", b"dependency")
    manager._install_archive(archive)
    return manager


def test_dialog_does_not_activate_model_without_runtime(qapp, tmp_path, tiny_pack):
    pack, payload = tiny_pack
    source = tmp_path / pack.filename
    source.write_bytes(payload)
    manager = ModelManager(tmp_path / "models")
    manager.install_model_file(pack.pack_id, source)
    dialog = __import__(
        "dialogs.ai_model_manager_dialog", fromlist=["AiModelManagerDialog"]
    ).AiModelManagerDialog(
        manager=manager,
        runtime_manager=_empty_runtime_manager(tmp_path),
        runtime_resolver=lambda _configured: None,
        ram_gb=2,
    )

    assert dialog.active_pack_id == ""
    assert not dialog.use_button.isEnabled()
    assert "runtime" in dialog.setup_button.text().casefold()
    assert "runtime needed" in dialog.table.item(0, 3).text().casefold()

    dialog._on_installed(pack.pack_id)
    assert dialog.active_pack_id == ""
    dialog.close()


def test_dialog_use_requires_complete_ready_stack(qapp, tmp_path, tiny_pack):
    from dialogs.ai_model_manager_dialog import AiModelManagerDialog
    from PySide6.QtWidgets import QDialog

    pack, payload = tiny_pack
    source = tmp_path / pack.filename
    source.write_bytes(payload)
    manager = ModelManager(tmp_path / "models")
    manager.install_model_file(pack.pack_id, source)
    runtime_manager = _installed_runtime_manager(tmp_path)
    dialog = AiModelManagerDialog(
        manager=manager,
        runtime_manager=runtime_manager,
        runtime_path=str(runtime_manager.runtime_path),
        runtime_resolver=lambda _configured: None,
        ram_gb=2,
    )

    assert dialog.use_button.isEnabled()
    dialog._use_selected()
    assert dialog.active_pack_id == pack.pack_id
    assert dialog.result() == QDialog.Accepted


def test_dialog_preselects_hardware_recommendation(qapp, tmp_path):
    from dialogs.ai_model_manager_dialog import AiModelManagerDialog

    dialog = AiModelManagerDialog(
        manager=ModelManager(tmp_path / "models"),
        runtime_manager=_empty_runtime_manager(tmp_path),
        runtime_resolver=lambda _configured: None,
        ram_gb=8,
    )

    assert dialog.selected_pack_id() == "qwen3-1.7b-q4"
    dialog.close()


def test_one_click_setup_sequences_runtime_then_model_then_activation(
    qapp, tmp_path, tiny_pack, monkeypatch
):
    from dialogs.ai_model_manager_dialog import AiModelManagerDialog

    pack, _payload = tiny_pack
    dialog = AiModelManagerDialog(
        manager=ModelManager(tmp_path / "models"),
        runtime_manager=_empty_runtime_manager(tmp_path),
        runtime_resolver=lambda _configured: None,
        ram_gb=2,
    )
    calls = []
    accepted = []
    monkeypatch.setattr(dialog, "_start_runtime_download", lambda: calls.append("runtime"))
    monkeypatch.setattr(
        dialog, "_start_model_download", lambda pack_id: calls.append(("model", pack_id))
    )
    monkeypatch.setattr(dialog, "accept", lambda: accepted.append(True))
    dialog._setup_target_pack_id = pack.pack_id

    monkeypatch.setattr(
        dialog,
        "_readiness",
        lambda _pack_id: AIReadiness(
            "model_and_runtime_missing", False, "missing", pack.pack_id
        ),
    )
    dialog._continue_setup()
    monkeypatch.setattr(
        dialog,
        "_readiness",
        lambda _pack_id: AIReadiness("model_missing", False, "missing", pack.pack_id),
    )
    dialog._continue_setup()
    monkeypatch.setattr(
        dialog,
        "_readiness",
        lambda _pack_id: AIReadiness("ready", True, "ready", pack.pack_id),
    )
    dialog._continue_setup()

    assert calls == ["runtime", ("model", pack.pack_id)]
    assert dialog.active_pack_id == pack.pack_id
    assert accepted == [True]
    dialog.close()


def test_cancelling_one_click_setup_clears_follow_on_stage(qapp, tmp_path):
    from dialogs.ai_model_manager_dialog import AiModelManagerDialog

    dialog = AiModelManagerDialog(
        manager=ModelManager(tmp_path / "models"),
        runtime_manager=_empty_runtime_manager(tmp_path),
        runtime_resolver=lambda _configured: None,
        ram_gb=8,
    )

    class _Worker:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    worker = _Worker()
    dialog._worker = worker
    dialog._setup_target_pack_id = "qwen3-1.7b-q4"

    dialog._cancel_download()

    assert dialog._setup_target_pack_id == ""
    assert worker.cancelled is True
    dialog._worker = None
    dialog.close()
