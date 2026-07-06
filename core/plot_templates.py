"""Reusable graph-style templates (save a Plot Details style, reuse anywhere).

A template is just a style dict (see core.plot_style) persisted as JSON. The
store is a plain directory of ``<name>.json`` files, so templates are easy to
share, back up, or ship with the app. The directory is configurable so tests
run hermetically.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DIR: Optional[Path] = None


def default_dir() -> Path:
    """User templates directory (``~/.sciplotter/plot_templates``), created."""
    global _DEFAULT_DIR
    if _DEFAULT_DIR is None:
        _DEFAULT_DIR = Path.home() / ".sciplotter" / "plot_templates"
    _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_DIR


def _safe_name(name: str) -> str:
    slug = re.sub(r"[^\w\-. ]+", "_", str(name).strip())
    slug = slug.strip(" .") or "template"
    return slug


def _dir(directory: Optional[os.PathLike]) -> Path:
    d = Path(directory) if directory is not None else default_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_template(name: str, style: Dict[str, Any],
                  directory: Optional[os.PathLike] = None) -> Path:
    """Persist ``style`` under ``name``; returns the file path."""
    if not str(name).strip():
        raise ValueError("template name is empty")
    path = _dir(directory) / f"{_safe_name(name)}.json"
    payload = {"name": name, "kind": "sciplotter_plot_template", "style": style}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_template(name: str, directory: Optional[os.PathLike] = None) -> Dict[str, Any]:
    """Load the style dict stored under ``name``."""
    path = _dir(directory) / f"{_safe_name(name)}.json"
    if not path.exists():
        raise FileNotFoundError(f"template not found: {name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    style = data.get("style")
    if not isinstance(style, dict):
        raise ValueError(f"template {name!r} has no style block")
    return style


def list_templates(directory: Optional[os.PathLike] = None) -> List[str]:
    """Names of the saved templates (sorted, case-insensitive)."""
    d = _dir(directory)
    names = []
    for p in d.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            names.append(str(data.get("name") or p.stem))
        except Exception:
            names.append(p.stem)
    return sorted(names, key=str.lower)


def delete_template(name: str, directory: Optional[os.PathLike] = None) -> bool:
    """Delete a template; returns True if a file was removed."""
    path = _dir(directory) / f"{_safe_name(name)}.json"
    if path.exists():
        path.unlink()
        return True
    return False
