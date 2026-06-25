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

from UI.docks.ai_dock import AiAssistantDock
from UI.docks.log_dock import OperationLogDock


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_ai_dock_emits_and_echoes(qapp):
    dock = AiAssistantDock()
    received = []
    dock.message_submitted.connect(received.append)

    dock.input_edit.setText("ทำกราฟให้หน่อย")
    dock.send_button.click()

    assert received == ["ทำกราฟให้หน่อย"]
    assert "ทำกราฟให้หน่อย" in dock.transcript_text()
    assert dock.input_edit.text() == ""  # cleared after send


def test_ai_dock_ignores_empty_and_whitespace(qapp):
    dock = AiAssistantDock()
    received = []
    dock.message_submitted.connect(received.append)

    dock.input_edit.setText("   ")
    dock.send_button.click()

    assert received == []
    assert dock.transcript_text() == ""


def test_ai_dock_return_key_submits(qapp):
    dock = AiAssistantDock()
    received = []
    dock.message_submitted.connect(received.append)

    dock.input_edit.setText("hello")
    dock.input_edit.returnPressed.emit()

    assert received == ["hello"]


def test_log_dock_add_entry(qapp):
    dock = OperationLogDock()
    dock.add_entry("Loaded sample.csv")
    dock.add_entry("Plotted line")

    assert dock.log_list.count() == 2
    assert dock.entries() == ["Loaded sample.csv", "Plotted line"]


def test_log_dock_rerun_signal(qapp):
    dock = OperationLogDock()
    fired = []
    dock.rerun_requested.connect(lambda: fired.append(True))

    dock.rerun_button.click()

    assert fired == [True]
