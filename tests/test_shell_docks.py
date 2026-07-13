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


def test_ai_dock_context_enables_quick_plot_actions(qapp):
    dock = AiAssistantDock()
    received = []
    dock.message_submitted.connect(received.append)

    assert all(not button.isEnabled() for button in dock.quick_buttons)
    dock.set_context("Book1", 120, 3, ["time", "voltage", "current"])
    dock.quick_buttons[1].click()

    assert "Book1" in dock.context_label.text()
    assert "120 rows" in dock.context_meta.text()
    assert "voltage" in dock.context_columns.text()
    assert "plot voltage vs time as scatter" in dock.input_edit.placeholderText()
    assert received == ["Plot the active data as a scatter graph."]
    assert dock.quick_buttons[2].text() == "Analyze"
    assert dock.quick_buttons[3].text() == "Find peaks"


def test_ai_dock_busy_completion_and_error_states(qapp):
    from ai.agent import AssistantResult

    dock = AiAssistantDock()
    dock.set_context("Book1", 3, 2)
    dock.input_edit.setText("plot signal vs time")
    dock._submit()
    dock.set_busy(True, "Understanding request")

    assert not dock.input_edit.isEnabled()
    assert dock.send_button.text() == "Working"

    dock.complete_request(
        AssistantResult(
            answer="Created a line graph.",
            trace=[("plot_columns", {"style": "line"}, "Created a line graph.")],
        )
    )
    assert dock.input_edit.isEnabled()
    assert dock.status_label.text() == "Completed"
    assert "plot_columns" in dock.action_label.text()
    assert "AI: Created a line graph." in dock.transcript_text()

    dock.complete_request(
        AssistantResult(
            answer="Could not create the plot.",
            trace=[("plot_columns", {}, "Could not create the plot.")],
            error="Could not create the plot.",
        )
    )
    assert dock.status_label.text() == "Needs attention"
    assert not dock.retry_button.isHidden()


def test_ai_dock_clear_restores_empty_state(qapp):
    dock = AiAssistantDock()
    dock.append_message("AI", "hello")
    assert dock.content_stack.currentIndex() == 1

    dock.clear()

    assert dock.transcript_text() == ""
    assert dock.content_stack.currentIndex() == 0


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
