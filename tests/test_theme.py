from __future__ import annotations

import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

pytest.importorskip("PySide6")

from styles.theme import DARK_CUSTOM_COLORS


def test_dark_custom_colors_drive_qdarktheme_stylesheet():
    """qdarktheme must accept our palette dict and bake the SciPlotter accent
    into the generated stylesheet, replacing its default light blue."""
    qdarktheme = pytest.importorskip("qdarktheme")

    qss = qdarktheme.load_stylesheet("dark", custom_colors=DARK_CUSTOM_COLORS).lower()
    assert "4f9cf9" in qss  # SciPlotter accent is in
    assert "8ab4f7" not in qss  # qdarktheme's default primary is gone


def test_dark_custom_colors_stay_in_family():
    """Guard the palette contract: accent + core surfaces must match the
    values the hand-written QSS files are built around."""
    assert DARK_CUSTOM_COLORS["primary"] == "#4F9CF9"
    assert DARK_CUSTOM_COLORS["background"] == "#1e2126"
    assert DARK_CUSTOM_COLORS["border"] == "#3a3f44"
    assert DARK_CUSTOM_COLORS["foreground"] == "#e6e6e6"
