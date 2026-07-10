from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_plot_data_mapping_reorders_and_inserts_row(qapp):
    from dialogs.plot_data_mapping_dialog import PlotDataMappingDialog, ROW_INDEX

    df = pd.DataFrame({
        "time": [10.0, 20.0, 30.0],
        "signal": [1.0, 4.0, 9.0],
        "fit": [1.1, 3.9, 9.2],
        "group": ["A", "A", "B"],
    })
    dlg = PlotDataMappingDialog(df, "Line")
    dlg.set_mapping(
        primary=ROW_INDEX,
        y_columns=["fit", "signal"],
        group_column="group",
        keep_unused=False,
    )

    mapped = dlg.mapped_dataframe()

    assert list(mapped.columns) == ["Row", "fit", "signal", "group"]
    assert mapped["Row"].to_list() == [1.0, 2.0, 3.0]
    assert mapped["fit"].to_list() == [1.1, 3.9, 9.2]


def test_plot_data_mapping_can_append_unused_columns(qapp):
    from dialogs.plot_data_mapping_dialog import PlotDataMappingDialog

    df = pd.DataFrame({
        "x": np.arange(3.0),
        "y": [2.0, 3.0, 4.0],
        "z": [5.0, 6.0, 7.0],
    })
    dlg = PlotDataMappingDialog(df, "Contour")
    dlg.set_mapping(primary="x", y_columns=["z"], keep_unused=True)

    mapped = dlg.mapped_dataframe()

    assert list(mapped.columns) == ["x", "z", "y"]
