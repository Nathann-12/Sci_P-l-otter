"""Verified download and offline installation of optional local AI packs."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from ai.model_catalog import MODEL_CATALOG_VERSION, ModelPack, get_model_pack, model_packs
from ai.license_texts import APACHE_2_LICENSE

ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]
_CHUNK = 1024 * 1024
_MAX_OFFLINE_PACK_BYTES = 8 * 1024**3


class ModelInstallError(RuntimeError):
    pass


def default_model_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "SciPlotter" / "models"
    return Path.home() / ".sciplotter" / "models"


def bundled_model_roots() -> tuple[Path, ...]:
    """Read-only roots used by an AI Starter/Plus full installer."""
    bases: list[Path] = [Path(sys.executable).resolve().parent]
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        bases.append(Path(frozen_root))
    roots: list[Path] = []
    for base in bases:
        candidate = base / "models"
        if candidate not in roots:
            roots.append(candidate)
    return tuple(roots)


def system_ram_gb() -> float:
    """Best-effort physical RAM detection without adding a dependency."""
    try:
        if os.name == "nt":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.ullTotalPhys / 1024**3
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        return float(page_size * pages) / 1024**3
    except Exception:
        return 0.0


class ModelManager:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        read_roots: Iterable[str | Path] | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else default_model_root()
        if read_roots is not None:
            extras = tuple(Path(path) for path in read_roots)
        elif root is None:
            extras = bundled_model_roots()
        else:
            extras = ()
        roots: list[Path] = []
        for path in (self.root, *extras):
            if path not in roots:
                roots.append(path)
        self.read_roots = tuple(roots)

    def packs(self) -> tuple[ModelPack, ...]:
        return tuple(model_packs())

    def pack_dir(self, pack_id: str) -> Path:
        get_model_pack(pack_id)  # reject paths/non-catalogue identifiers
        return self.root / pack_id

    def model_path(self, pack_id: str) -> Path:
        pack = get_model_pack(pack_id)
        for root in self.read_roots:
            directory = root / pack_id
            if self._valid_install_dir(pack, directory):
                return directory / pack.filename
        return self.pack_dir(pack_id) / pack.filename

    def is_installed(self, pack_id: str) -> bool:
        try:
            pack = get_model_pack(pack_id)
        except KeyError:
            return False
        return any(
            self._valid_install_dir(pack, root / pack_id) for root in self.read_roots
        )

    def _valid_install_dir(self, pack: ModelPack, directory: Path) -> bool:
        manifest = directory / "manifest.json"
        model = directory / pack.filename
        if not manifest.is_file() or not model.is_file():
            return False
        try:
            saved = json.loads(manifest.read_text(encoding="utf-8"))
            return (
                saved.get("pack", {}).get("sha256") == pack.sha256
                and model.stat().st_size == pack.size_bytes
            )
        except Exception:
            return False

    def installed_pack_ids(self) -> list[str]:
        return [pack.pack_id for pack in self.packs() if self.is_installed(pack.pack_id)]

    def recommended_pack(self, ram_gb: float | None = None) -> ModelPack:
        ram = system_ram_gb() if ram_gb is None else max(0.0, float(ram_gb))
        eligible = [pack for pack in self.packs() if ram >= pack.recommended_ram_gb]
        return eligible[-1] if eligible else self.packs()[0]

    def download(
        self,
        pack_id: str,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
        opener=None,
    ) -> Path:
        """Download, hash-check, and atomically install one catalogue model."""
        pack = get_model_pack(pack_id)
        self.root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(self.root).free
        if free < pack.size_bytes + 256 * 1024**2:
            raise ModelInstallError("Not enough disk space for this model pack.")

        downloads = self.root / ".downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        part = downloads / f"{pack.pack_id}.part"
        request = urllib.request.Request(
            pack.download_url,
            headers={"User-Agent": "SciPlotter/AI-Model-Manager"},
        )
        open_url = opener or urllib.request.urlopen
        try:
            with open_url(request, timeout=60) as response, open(part, "wb") as target:
                total = int(response.headers.get("Content-Length") or pack.size_bytes)
                received = 0
                while True:
                    if cancelled is not None and cancelled():
                        raise ModelInstallError("Download cancelled.")
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    target.write(chunk)
                    received += len(chunk)
                    if received > pack.size_bytes + _CHUNK:
                        raise ModelInstallError("Download is larger than the signed catalogue entry.")
                    if progress is not None:
                        progress(received, total)
            return self.install_model_file(pack.pack_id, part, move=True)
        finally:
            part.unlink(missing_ok=True)

    def install_model_file(
        self, pack_id: str, source: str | Path, *, move: bool = False
    ) -> Path:
        pack = get_model_pack(pack_id)
        source_path = Path(source)
        self._verify_model_file(pack, source_path)
        destination_dir = self.pack_dir(pack_id)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / pack.filename
        temporary = destination.with_suffix(destination.suffix + ".installing")
        temporary.unlink(missing_ok=True)
        if move:
            os.replace(source_path, temporary)
        else:
            shutil.copyfile(source_path, temporary)
        os.replace(temporary, destination)
        self._write_manifest(pack)
        return destination

    def install_offline_bundle(
        self,
        bundle: str | Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> Path:
        """Install a ``.scimodel`` ZIP without trusting paths inside it."""
        bundle_path = Path(bundle)
        try:
            archive = zipfile.ZipFile(bundle_path, "r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise ModelInstallError(f"Invalid offline model pack: {exc}") from exc
        with archive:
            infos = archive.infolist()
            if sum(info.file_size for info in infos) > _MAX_OFFLINE_PACK_BYTES:
                raise ModelInstallError("Offline model pack is too large.")
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ModelInstallError("Unsafe path in offline model pack.")
                if info.compress_size and info.file_size / info.compress_size > 250:
                    raise ModelInstallError("Unsafe compression ratio in offline model pack.")
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                pack = get_model_pack(str(manifest["pack"]["pack_id"]))
            except Exception as exc:
                raise ModelInstallError("Offline pack manifest is missing or unknown.") from exc
            signed = manifest.get("pack") or {}
            if signed.get("sha256") != pack.sha256 or signed.get("filename") != pack.filename:
                raise ModelInstallError("Offline pack does not match the signed catalogue.")
            try:
                info = archive.getinfo(pack.filename)
            except KeyError as exc:
                raise ModelInstallError("Offline pack does not contain its model file.") from exc

            self.root.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix="sciplotter-model-", suffix=".part", dir=self.root)
            os.close(fd)
            temporary = Path(temp_name)
            try:
                received = 0
                with archive.open(info, "r") as source, open(temporary, "wb") as target:
                    while True:
                        if cancelled is not None and cancelled():
                            raise ModelInstallError("Installation cancelled.")
                        chunk = source.read(_CHUNK)
                        if not chunk:
                            break
                        target.write(chunk)
                        received += len(chunk)
                        if progress is not None:
                            progress(received, info.file_size)
                return self.install_model_file(pack.pack_id, temporary, move=True)
            finally:
                temporary.unlink(missing_ok=True)

    def create_offline_bundle(
        self,
        pack_id: str,
        destination: str | Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> Path:
        """Export an installed model for an air-gapped research computer."""
        pack = get_model_pack(pack_id)
        model = self.model_path(pack_id)
        if not self.is_installed(pack_id):
            raise ModelInstallError("Install and verify the model before exporting it.")
        destination_path = Path(destination)
        if destination_path.suffix.casefold() != ".scimodel":
            destination_path = destination_path.with_suffix(".scimodel")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination_path.with_suffix(destination_path.suffix + ".part")
        temporary.unlink(missing_ok=True)
        manifest = self._manifest_data(pack)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                archive.writestr("LICENSE-model.txt", APACHE_2_LICENSE)
                archive.writestr(
                    "MODEL-NOTICE.txt",
                    f"{pack.display_name}\nSource: {pack.source_url}\nLicense: {pack.license_url}\n",
                )
                with model.open("rb") as source, archive.open(
                    pack.filename, "w", force_zip64=True
                ) as target:
                    written = 0
                    while True:
                        if cancelled is not None and cancelled():
                            raise ModelInstallError("Offline export cancelled.")
                        chunk = source.read(_CHUNK)
                        if not chunk:
                            break
                        target.write(chunk)
                        written += len(chunk)
                        if progress is not None:
                            progress(written, pack.size_bytes)
            os.replace(temporary, destination_path)
        finally:
            temporary.unlink(missing_ok=True)
        return destination_path

    def remove(self, pack_id: str) -> None:
        get_model_pack(pack_id)
        directory = self.pack_dir(pack_id)
        if directory.exists():
            root = self.root.resolve()
            resolved = directory.resolve()
            if resolved == root or root not in resolved.parents:
                raise ModelInstallError("Refusing to remove a path outside the model directory.")
            shutil.rmtree(resolved)

    def _verify_model_file(self, pack: ModelPack, path: Path) -> None:
        if not path.is_file():
            raise ModelInstallError("Model file was not found.")
        if path.stat().st_size != pack.size_bytes:
            raise ModelInstallError("Model size does not match the signed catalogue.")
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(_CHUNK), b""):
                digest.update(chunk)
        if digest.hexdigest().casefold() != pack.sha256.casefold():
            raise ModelInstallError("SHA-256 verification failed; the file was not installed.")

    def _manifest_data(self, pack: ModelPack) -> dict:
        return {
            "catalog_version": MODEL_CATALOG_VERSION,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "pack": asdict(pack),
        }

    def _write_manifest(self, pack: ModelPack) -> None:
        manifest = self.pack_dir(pack.pack_id) / "manifest.json"
        temporary = manifest.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._manifest_data(pack), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, manifest)
