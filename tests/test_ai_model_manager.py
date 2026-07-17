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


def test_install_rejects_wrong_hash_without_leaving_model(tmp_path, tiny_pack):
    pack, payload = tiny_pack
    bad = tmp_path / "bad.gguf"
    bad.write_bytes(b"x" * len(payload))
    manager = ModelManager(tmp_path / "models")

    with pytest.raises(ModelInstallError, match="SHA-256"):
        manager.install_model_file(pack.pack_id, bad)

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
