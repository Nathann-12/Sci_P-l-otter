"""Tests for the consolidated form dialog (dialogs/form_dialog.py) that
replaced chains of QInputDialog popups."""
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

from PySide6.QtWidgets import QApplication

from dialogs.form_dialog import FormDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _fields():
    return [
        {"name": "kind", "label": "ชนิด", "kind": "choice",
         "options": ["lowpass", "bandpass"], "default": "lowpass"},
        {"name": "fs", "label": "fs", "kind": "float", "default": 100.0},
        {"name": "n", "label": "จำนวน", "kind": "int", "default": 4, "min": 1, "max": 10},
        {"name": "flag", "label": "detrend", "kind": "bool", "default": True},
        {"name": "hi", "label": "cutoff สูง", "kind": "float", "default": 5.0,
         "show_if": ("kind", "bandpass")},
    ]


def test_values_reflect_defaults_and_types(qapp):
    d = FormDialog("t", _fields())
    v = d.values()
    assert v["kind"] == "lowpass"
    assert isinstance(v["fs"], float) and v["fs"] == 100.0
    assert isinstance(v["n"], int) and v["n"] == 4
    assert v["flag"] is True
    assert v["hi"] == 5.0  # hidden fields still return a value


def test_editing_widgets_changes_values(qapp):
    d = FormDialog("t", _fields())
    d._widgets["kind"].setCurrentText("bandpass")
    d._widgets["fs"].setValue(250.0)
    d._widgets["n"].setValue(6)
    d._widgets["flag"].setChecked(False)
    v = d.values()
    assert v == {"kind": "bandpass", "fs": 250.0, "n": 6, "flag": False, "hi": 5.0}


def test_conditional_visibility_tracks_controller(qapp):
    d = FormDialog("t", _fields())
    # lowpass → hi hidden
    assert not d._rows["hi"][1].isVisibleTo(d)
    d._widgets["kind"].setCurrentText("bandpass")
    assert d._rows["hi"][1].isVisibleTo(d)
    d._widgets["kind"].setCurrentText("lowpass")
    assert not d._rows["hi"][1].isVisibleTo(d)


def test_show_if_accepts_multiple_values(qapp):
    fields = [
        {"name": "kind", "label": "k", "kind": "choice",
         "options": ["a", "b", "c"], "default": "a"},
        {"name": "x", "label": "x", "kind": "float", "default": 1.0,
         "show_if": ("kind", ("b", "c"))},
    ]
    d = FormDialog("t", fields)
    assert not d._rows["x"][1].isVisibleTo(d)
    d._widgets["kind"].setCurrentText("c")
    assert d._rows["x"][1].isVisibleTo(d)
