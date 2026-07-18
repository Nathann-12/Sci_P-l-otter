from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from ai.model_manager import ModelInstallError
from ai.runtime_manager import RuntimeManager, RuntimePackage


def _runtime_fixture(tmp_path):
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("llama-server.exe", b"server")
        bundle.writestr("llama.dll", b"dll")
    payload = archive.read_bytes()
    package = RuntimePackage(
        runtime_id="test-runtime",
        version="test",
        platform="windows",
        architecture="x86_64",
        filename="runtime.zip",
        server_filename="llama-server.exe",
        download_url="https://example.invalid/runtime.zip",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        license_name="MIT",
        license_url="https://example.invalid/license",
        source_url="https://example.invalid/source",
    )
    return archive, package


def test_runtime_archive_installs_server_dependencies_license_and_manifest(tmp_path):
    archive, package = _runtime_fixture(tmp_path)
    manager = RuntimeManager(tmp_path / "installed", package)

    runtime = manager._install_archive(archive)

    assert runtime.read_bytes() == b"server"
    assert (runtime.parent / "llama.dll").is_file()
    assert (runtime.parent / "LICENSE-llama.cpp.txt").is_file()
    assert manager.is_installed()


def test_full_installer_read_only_runtime_root_is_recognised(tmp_path):
    archive, package = _runtime_fixture(tmp_path)
    bundled_root = tmp_path / "application" / "runtime" / "llama"
    RuntimeManager(bundled_root, package)._install_archive(archive)

    manager = RuntimeManager(
        tmp_path / "user-runtime",
        package,
        read_roots=[bundled_root],
    )

    assert manager.is_installed()
    assert manager.runtime_path.parent == bundled_root / package.runtime_id


def test_runtime_archive_rejects_path_traversal(tmp_path):
    archive, package = _runtime_fixture(tmp_path)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../llama-server.exe", b"bad")
    manager = RuntimeManager(tmp_path / "installed", package)

    with pytest.raises(ModelInstallError, match="Unsafe path"):
        manager._install_archive(archive)


def test_cancel_interrupts_runtime_extraction_and_removes_staging(tmp_path):
    archive, package = _runtime_fixture(tmp_path)
    manager = RuntimeManager(tmp_path / "installed", package)

    with pytest.raises(ModelInstallError, match="cancelled"):
        manager._install_archive(archive, cancelled=lambda: True)

    assert not manager.install_dir.exists()
    assert not (manager.root / f".{package.runtime_id}.installing").exists()


@pytest.mark.parametrize(
    "member_name",
    (
        r"..\escape.exe",
        r"nested\..\..\escape.exe",
        r"C:\escape.exe",
        r"\\server\share\escape.exe",
    ),
)
def test_runtime_archive_rejects_windows_path_escape(tmp_path, member_name):
    archive, package = _runtime_fixture(tmp_path)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(member_name, b"bad")
    manager = RuntimeManager(tmp_path / "installed", package)

    with pytest.raises(ModelInstallError, match="Unsafe path"):
        manager._install_archive(archive)

    assert not (manager.root / "escape.exe").exists()


def test_runtime_archive_rejects_casefolded_destination_collision(tmp_path):
    archive, package = _runtime_fixture(tmp_path)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("llama-server.exe", b"server")
        bundle.writestr("LLAMA-SERVER.EXE", b"other")
    manager = RuntimeManager(tmp_path / "installed", package)

    with pytest.raises(ModelInstallError, match="Duplicate path"):
        manager._install_archive(archive)


@pytest.mark.parametrize("tamper", ("catalog", "package"))
def test_runtime_install_rejects_stale_or_tampered_manifest(tmp_path, tamper):
    archive, package = _runtime_fixture(tmp_path)
    manager = RuntimeManager(tmp_path / "installed", package)
    manager._install_archive(archive)
    manifest = manager.install_dir / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if tamper == "catalog":
        data["catalog_version"] = "stale"
    else:
        data["package"]["version"] = "tampered"
    manifest.write_text(json.dumps(data), encoding="utf-8")

    assert manager.is_installed() is False


def test_runtime_catalog_entry_has_pinned_hash_and_loopback_server_binary():
    manager = RuntimeManager()
    package = manager.package
    assert package.download_url.startswith("https://github.com/ggml-org/llama.cpp/")
    assert len(package.sha256) == 64
    int(package.sha256, 16)
    assert package.server_filename == "llama-server.exe"
