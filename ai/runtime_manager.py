"""Verified installer for the small llama.cpp runtime shipped with SciPlotter."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from ai.archive_safety import (
    UnsafeArchiveMemberError,
    safe_zip_destination,
    zip_destination_key,
)
from ai.model_manager import ModelInstallError

RUNTIME_CATALOG_VERSION = "1.0"
LLAMA_CPP_LICENSE = """MIT License

Copyright (c) 2023-2026 The ggml authors

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


@dataclass(frozen=True)
class RuntimePackage:
    runtime_id: str
    version: str
    platform: str
    architecture: str
    filename: str
    server_filename: str
    download_url: str
    sha256: str
    size_bytes: int
    license_name: str
    license_url: str
    source_url: str


WINDOWS_X64_RUNTIME = RuntimePackage(
    runtime_id="llama-cpp-b10042-win-cpu-x64",
    version="b10042",
    platform="windows",
    architecture="x86_64",
    filename="llama-b10042-bin-win-cpu-x64.zip",
    server_filename="llama-server.exe",
    download_url=(
        "https://github.com/ggml-org/llama.cpp/releases/download/b10042/"
        "llama-b10042-bin-win-cpu-x64.zip"
    ),
    sha256="860f034f0a9a591cf3976bbf8fb2ed52677bb3ec7eca05146fa260cb7823ca73",
    size_bytes=18_418_846,
    license_name="MIT",
    license_url="https://github.com/ggml-org/llama.cpp/blob/b10042/LICENSE",
    source_url="https://github.com/ggml-org/llama.cpp/releases/tag/b10042",
)


def default_runtime_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "SciPlotter" / "runtime" / "llama"
    return Path.home() / ".sciplotter" / "runtime" / "llama"


def bundled_runtime_roots() -> tuple[Path, ...]:
    """Read-only roots used by an AI Starter/Plus full installer."""

    bases: list[Path] = [Path(sys.executable).resolve().parent]
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        bases.append(Path(frozen_root))
    roots: list[Path] = []
    for base in bases:
        candidate = base / "runtime" / "llama"
        if candidate not in roots:
            roots.append(candidate)
    return tuple(roots)


class RuntimeManager:
    def __init__(
        self,
        root: str | Path | None = None,
        package: RuntimePackage | None = None,
        *,
        read_roots: Iterable[str | Path] | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else default_runtime_root()
        self.package = package or WINDOWS_X64_RUNTIME
        if read_roots is not None:
            extras = tuple(Path(path) for path in read_roots)
        elif root is None:
            extras = bundled_runtime_roots()
        else:
            extras = ()
        roots: list[Path] = []
        for path in (self.root, *extras):
            if path not in roots:
                roots.append(path)
        self.read_roots = tuple(roots)

    @property
    def install_dir(self) -> Path:
        return self.root / self.package.runtime_id

    @property
    def runtime_path(self) -> Path:
        for root in self.read_roots:
            directory = root / self.package.runtime_id
            if self._valid_install_dir(directory):
                return directory / self.package.server_filename
        return self.install_dir / self.package.server_filename

    def supported(self) -> bool:
        machine = platform.machine().casefold()
        return os.name == "nt" and machine in {"amd64", "x86_64"}

    def is_installed(self) -> bool:
        return any(
            self._valid_install_dir(root / self.package.runtime_id)
            for root in self.read_roots
        )

    def _valid_install_dir(self, directory: Path) -> bool:
        runtime = directory / self.package.server_filename
        manifest = directory / "manifest.json"
        if not runtime.is_file() or not manifest.is_file():
            return False
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return (
                data.get("catalog_version") == RUNTIME_CATALOG_VERSION
                and data.get("package") == asdict(self.package)
                and runtime.stat().st_size > 0
            )
        except Exception:
            return False

    def download_and_install(
        self,
        *,
        progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        opener=None,
    ) -> Path:
        if not self.supported():
            raise ModelInstallError("This bundled runtime currently supports Windows x64 only.")
        self.root.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.root).free < self.package.size_bytes + 256 * 1024**2:
            raise ModelInstallError("Not enough disk space for the local AI runtime.")
        fd, temp_name = tempfile.mkstemp(prefix="sciplotter-runtime-", suffix=".zip", dir=self.root)
        os.close(fd)
        archive_path = Path(temp_name)
        request = urllib.request.Request(
            self.package.download_url,
            headers={"User-Agent": "SciPlotter/AI-Runtime-Manager"},
        )
        open_url = opener or urllib.request.urlopen
        try:
            digest = hashlib.sha256()
            received = 0
            with open_url(request, timeout=60) as response, open(archive_path, "wb") as target:
                total = int(response.headers.get("Content-Length") or self.package.size_bytes)
                while True:
                    if cancelled is not None and cancelled():
                        raise ModelInstallError("Runtime download cancelled.")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if received > self.package.size_bytes + 1024 * 1024:
                        raise ModelInstallError("Runtime download is larger than its signed entry.")
                    if progress is not None:
                        progress(received, total)
            if received != self.package.size_bytes or digest.hexdigest() != self.package.sha256:
                raise ModelInstallError("Runtime SHA-256 verification failed.")
            return self._install_archive(archive_path, cancelled=cancelled)
        finally:
            archive_path.unlink(missing_ok=True)

    def _install_archive(
        self,
        archive_path: Path,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        staging = self.root / f".{self.package.runtime_id}.installing"
        self._remove_inside_root(staging)
        staging.mkdir(parents=True)
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                infos = archive.infolist()
                if sum(info.file_size for info in infos) > 1024**3:
                    raise ModelInstallError("Runtime archive is unexpectedly large.")
                destinations: set[str] = set()
                for info in infos:
                    if cancelled is not None and cancelled():
                        raise ModelInstallError("Runtime installation cancelled.")
                    try:
                        destination = safe_zip_destination(staging, info.filename)
                    except UnsafeArchiveMemberError as exc:
                        raise ModelInstallError("Unsafe path in runtime archive.") from exc
                    key = zip_destination_key(destination)
                    if key in destinations:
                        raise ModelInstallError("Duplicate path in runtime archive.")
                    destinations.add(key)
                    if info.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, open(destination, "wb") as target:
                        while True:
                            if cancelled is not None and cancelled():
                                raise ModelInstallError("Runtime installation cancelled.")
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            target.write(chunk)
            if cancelled is not None and cancelled():
                raise ModelInstallError("Runtime installation cancelled.")
            server_matches = list(staging.rglob(self.package.server_filename))
            if len(server_matches) != 1:
                raise ModelInstallError("Runtime archive does not contain llama-server.")
            server = server_matches[0]
            if server.parent != staging:
                for child in server.parent.iterdir():
                    shutil.move(str(child), staging / child.name)
            (staging / "LICENSE-llama.cpp.txt").write_text(LLAMA_CPP_LICENSE, encoding="utf-8")
            (staging / "manifest.json").write_text(
                json.dumps(
                    {
                        "catalog_version": RUNTIME_CATALOG_VERSION,
                        "package": asdict(self.package),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            self._remove_inside_root(self.install_dir)
            os.replace(staging, self.install_dir)
            return self.runtime_path
        except Exception:
            self._remove_inside_root(staging)
            raise

    def _remove_inside_root(self, path: Path) -> None:
        if not path.exists():
            return
        root = self.root.resolve()
        resolved = path.resolve()
        if resolved == root or root not in resolved.parents:
            raise ModelInstallError("Refusing to remove a path outside the runtime directory.")
        shutil.rmtree(resolved)
