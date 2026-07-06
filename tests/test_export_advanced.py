"""Tests for advanced figure export (formats / DPI / transparent / clipboard)
through the real MainWindow."""
from __future__ import annotations

import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    yield w
    w.close()


def _plot(win):
    df = pd.DataFrame({"t": [0.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]})
    win._stage_insert("x.csv [ตาราง]", df, None)
    win.plot_from_workbook("line")


@pytest.mark.parametrize("fmt,ext", [
    ("PNG", "png"), ("PDF", "pdf"), ("SVG", "svg"), ("EPS", "eps"),
])
def test_export_each_format(win, tmp_path, fmt, ext):
    _plot(win)
    out = tmp_path / f"fig.{ext}"
    win.ask_form = lambda *a, **k: {"fmt": fmt, "dpi": 120,
                                    "transparent": False, "tight": True}
    win.ask_save_path = lambda *a, **k: str(out)
    win.export_figure_advanced()
    assert out.exists() and out.stat().st_size > 0


def test_export_tiff_if_pillow(win, tmp_path):
    pytest.importorskip("PIL")
    _plot(win)
    out = tmp_path / "fig.tiff"
    win.ask_form = lambda *a, **k: {"fmt": "TIFF", "dpi": 100,
                                    "transparent": False, "tight": True}
    win.ask_save_path = lambda *a, **k: str(out)
    win.export_figure_advanced()
    assert out.exists() and out.stat().st_size > 0


def test_export_transparent_png(win, tmp_path):
    _plot(win)
    out = tmp_path / "clear.png"
    win.ask_form = lambda *a, **k: {"fmt": "PNG", "dpi": 100,
                                    "transparent": True, "tight": True}
    win.ask_save_path = lambda *a, **k: str(out)
    win.export_figure_advanced()
    assert out.exists()
    # top-left pixel should be fully transparent
    from PIL import Image
    px = Image.open(out).convert("RGBA").getpixel((0, 0))
    assert px[3] == 0


def test_export_cancelled_does_nothing(win, tmp_path):
    _plot(win)
    win.ask_form = lambda *a, **k: None  # user cancels the form
    called = {"save": False}
    win.ask_save_path = lambda *a, **k: called.__setitem__("save", True) or ""
    win.export_figure_advanced()
    assert called["save"] is False  # never reached the save dialog


def test_copy_figure_to_clipboard(win):
    _plot(win)
    win.copy_figure_to_clipboard()
    img = QApplication.clipboard().image()
    assert not img.isNull()
    assert img.width() > 0 and img.height() > 0
