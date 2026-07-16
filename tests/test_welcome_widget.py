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

from UI.welcome import WelcomeWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_open_button_emits_open_requested(qapp):
    widget = WelcomeWidget()
    fired = []
    widget.open_requested.connect(lambda: fired.append(True))

    widget.open_button.click()

    assert fired == [True]


def test_sample_and_blank_buttons_emit_their_actions(qapp):
    widget = WelcomeWidget()
    fired = []
    widget.sample_requested.connect(lambda: fired.append("sample"))
    widget.blank_requested.connect(lambda: fired.append("blank"))

    widget.sample_button.click()
    widget.blank_button.click()

    assert fired == ["sample", "blank"]


def test_set_recent_files_populates_list(qapp):
    widget = WelcomeWidget()
    paths = ["C:/data/a.csv", "C:/data/b.xlsx"]
    widget.set_recent_files(paths)

    assert widget.recent_files() == paths
    assert widget.recent_list.count() == 2

    # setting again replaces the contents
    widget.set_recent_files(["C:/data/c.txt"])
    assert widget.recent_files() == ["C:/data/c.txt"]


def test_recent_double_click_emits_path(qapp):
    widget = WelcomeWidget()
    widget.set_recent_files(["C:/data/a.csv"])
    received = []
    widget.recent_file_activated.connect(received.append)

    item = widget.recent_list.item(0)
    widget.recent_list.itemDoubleClicked.emit(item)

    assert received == ["C:/data/a.csv"]
