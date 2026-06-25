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

from widgets.activity_rail import ActivityRail


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_first_activity_becomes_active_and_emits(qapp):
    rail = ActivityRail()
    received = []
    rail.activity_changed.connect(received.append)

    rail.add_activity("data", "ข้อมูล")

    assert rail.current_activity() == "data"
    assert received == ["data"]
    assert rail.button_for("data").isChecked()


def test_set_active_switches_and_emits_once(qapp):
    rail = ActivityRail()
    received = []
    rail.activity_changed.connect(received.append)

    rail.add_activity("data", "ข้อมูล")
    rail.add_activity("plot", "กราฟ")
    received.clear()

    rail.set_active("plot")

    assert rail.current_activity() == "plot"
    assert received == ["plot"]
    assert rail.button_for("plot").isChecked()
    assert not rail.button_for("data").isChecked()

    # set_active to the same id must NOT re-emit
    rail.set_active("plot")
    assert received == ["plot"]


def test_clicking_button_changes_activity(qapp):
    rail = ActivityRail()
    received = []
    rail.activity_changed.connect(received.append)

    rail.add_activity("data", "ข้อมูล")
    rail.add_activity("plot", "กราฟ")
    received.clear()

    rail.button_for("plot").click()

    assert rail.current_activity() == "plot"
    assert received == ["plot"]


def test_unknown_id_and_duplicate_add(qapp):
    rail = ActivityRail()
    first = rail.add_activity("data", "ข้อมูล")
    # adding the same id returns the same button, no duplicate
    again = rail.add_activity("data", "ข้อมูล (อีกครั้ง)")
    assert first is again
    assert rail.activity_ids() == ["data"]

    # set_active with unknown id is a no-op
    rail.set_active("does-not-exist")
    assert rail.current_activity() == "data"
