"""Shared path validation for ZIP members installed by SciPlotter.

ZIP member names normally use POSIX separators, but a crafted archive can put
Windows separators, drive letters, UNC paths, or NTFS alternate-data-stream
syntax in the central directory.  Validate both path dialects and perform a
final resolved-path containment check before a caller writes any member.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


class UnsafeArchiveMemberError(ValueError):
    """Raised when a ZIP member cannot be written safely below its root."""


def safe_zip_destination(root: str | Path, member_name: str) -> Path:
    """Return a resolved destination strictly below *root*.

    The check is intentionally platform-independent: Windows paths must be
    rejected even when release tooling or tests inspect an archive elsewhere.
    """

    raw = str(member_name or "")
    if not raw or "\x00" in raw:
        raise UnsafeArchiveMemberError("empty or NUL-containing member name")

    # ZIP specifies '/', but treating '\\' as data is unsafe on Windows where
    # Path/open will interpret it as a separator.
    normalized = raw.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(raw)
    parts = posix_path.parts
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
        # Colons include drive-relative paths (C:foo) and NTFS ADS names.
        or any(":" in part for part in parts)
    ):
        raise UnsafeArchiveMemberError(f"unsafe ZIP member path: {raw!r}")

    resolved_root = Path(root).resolve()
    destination = resolved_root.joinpath(*parts).resolve()
    if destination == resolved_root or resolved_root not in destination.parents:
        raise UnsafeArchiveMemberError(f"ZIP member escapes destination: {raw!r}")
    return destination


def zip_destination_key(destination: str | Path) -> str:
    """Return a Windows-safe key for duplicate/collision detection."""

    return str(Path(destination)).casefold()
