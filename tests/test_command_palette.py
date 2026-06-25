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

from widgets.command_palette import CommandPalette


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _commands(calls):
    return [
        ("Open File", lambda: calls.append("open")),
        ("Save Session", lambda: calls.append("save")),
        ("Export PNG", lambda: calls.append("export")),
    ]


def test_set_commands_lists_all(qapp):
    palette = CommandPalette()
    calls = []
    palette.set_commands(_commands(calls))

    assert palette.visible_labels() == ["Open File", "Save Session", "Export PNG"]


def test_filter_is_case_insensitive_substring(qapp):
    palette = CommandPalette()
    calls = []
    palette.set_commands(_commands(calls))

    palette.search_edit.setText("save")
    assert palette.visible_labels() == ["Save Session"]

    palette.search_edit.setText("PNG")
    assert palette.visible_labels() == ["Export PNG"]

    palette.search_edit.setText("e")  # matches all three (Open, Save, Export)
    assert set(palette.visible_labels()) == {"Open File", "Save Session", "Export PNG"}


def test_enter_runs_selected_and_closes(qapp):
    palette = CommandPalette()
    calls = []
    palette.set_commands(_commands(calls))

    palette.search_edit.setText("export")
    # simulate pressing Enter in the search field
    palette.search_edit.returnPressed.emit()

    assert calls == ["export"]
    assert not palette.isVisible()


def test_double_click_runs_callable(qapp):
    palette = CommandPalette()
    calls = []
    palette.set_commands(_commands(calls))

    item = palette.list_widget.item(0)  # "Open File"
    palette.list_widget.itemDoubleClicked.emit(item)

    assert calls == ["open"]
