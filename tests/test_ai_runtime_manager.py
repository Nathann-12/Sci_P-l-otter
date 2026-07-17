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


def test_runtime_archive_rejects_path_traversal(tmp_path):
    archive, package = _runtime_fixture(tmp_path)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../llama-server.exe", b"bad")
    manager = RuntimeManager(tmp_path / "installed", package)

    with pytest.raises(ModelInstallError, match="Unsafe path"):
        manager._install_archive(archive)


def test_runtime_catalog_entry_has_pinned_hash_and_loopback_server_binary():
    manager = RuntimeManager()
    package = manager.package
    assert package.download_url.startswith("https://github.com/ggml-org/llama.cpp/")
    assert len(package.sha256) == 64
    int(package.sha256, 16)
    assert package.server_filename == "llama-server.exe"
