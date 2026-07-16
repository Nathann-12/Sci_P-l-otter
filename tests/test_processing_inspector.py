from __future__ import annotations

import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QGroupBox


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main

    window = app_main.MainWindow()
    yield window
    window.close()


def test_processing_inspector_starts_contextual_and_disabled(win):
    assert win.procBookLabel.text() == "No active data"
    assert not win.procColumnCombo.isEnabled()
    assert not win.btnMA.isEnabled()
    assert not win.btnProcUndo.isEnabled()

    titles = {
        group.title()
        for group in win.processingScroll.findChildren(QGroupBox)
    }
    assert {"Clean rows", "Transform column", "Time & vector", "Summarize"}.issubset(titles)
    assert "Extra Features" not in titles
    assert "Data Formatting" not in titles


def test_processing_context_uses_real_data_and_syncs_target_y(win, qapp):
    frame = pd.DataFrame({
        "time_s": [0, 1, 1, 2],
        "signal": [1.0, np.nan, np.nan, 4.0],
        "label": ["a", "b", "b", "c"],
    })
    win._stage_insert("sensor.csv [table]", frame, None)
    qapp.processEvents()

    assert win.procBookLabel.text() == "sensor.csv [table]"
    assert win.procDataSummary.text() == "4 rows x 3 columns   |   2 numeric"
    assert win.procQualityLabel.text() == "Missing: 2   Duplicates: 1"
    assert win.procXLabel.text() == "X / time: time_s"
    assert [
        win.procColumnCombo.itemText(index)
        for index in range(win.procColumnCombo.count())
    ] == ["time_s", "signal"]
    assert all(button.isEnabled() for button in win._processing_data_buttons)

    win.procColumnCombo.setCurrentText("signal")

    assert win.cbY.currentText() == "signal"
    assert "signal" in win.procStatusLabel.text()


def test_processing_undo_button_tracks_dataframe_history(win, qapp):
    win._stage_insert(
        "history.csv [table]",
        pd.DataFrame({"x": [0, 0], "y": [2.0, 2.0]}),
        None,
    )
    qapp.processEvents()
    assert not win.btnProcUndo.isEnabled()

    win.btnRemoveDuplicates.click()
    qapp.processEvents()

    assert win.btnProcUndo.isEnabled()
    assert len(win._df) == 1
    assert win.procQualityLabel.text() == "Missing: 0   Duplicates: 0"

    win.btnProcUndo.click()
    qapp.processEvents()

    assert len(win._df) == 2
    assert win.procQualityLabel.text() == "Missing: 0   Duplicates: 1"


def test_large_data_rendering_controls_are_explicit_and_update_options(win):
    assert win.cboBarReducer.currentData() == "sum"
    assert win.cboScatterRender.currentData() == "auto"

    win.cboBarReducer.setCurrentIndex(win.cboBarReducer.findData("mean"))
    win.cboScatterRender.setCurrentIndex(win.cboScatterRender.findData("density"))

    assert win.current_plot_options().bar_reducer == "mean"
    assert win.current_plot_options().scatter_mode == "density"
