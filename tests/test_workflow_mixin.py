"""End-to-end reproducibility tests through the real MainWindow (headless):
do an operation → it lands in history → export workflow → re-run on fresh
data → generate a Python script."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
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


def _load_book(win, name, df):
    win._stage_insert(name, df, None)


def test_operations_are_recorded_into_history(win):
    _load_book(win, "wf.csv [ตาราง]", pd.DataFrame({"t": [0, 1, 2], "y": [1.0, 2.0, 3.0]}))
    win.ask_form = lambda *a, **k: {"method": "minmax"}
    assert len(win.analysis_history) == 0

    win.feature_clean_normalize()

    assert len(win.analysis_history) == 1
    entry = win.analysis_history.entries[0]
    assert entry["op"] == "normalize_column"
    assert entry["params"] == {"col": "y", "method": "minmax"}
    # operation log dock got a readable line too
    assert any("normalize_column" in line for line in win.op_log_dock.entries())


def test_export_import_rerun_roundtrip(win, tmp_path):
    df = pd.DataFrame({"t": np.arange(6, dtype=float),
                       "y": [1.0, np.nan, 3.0, 4.0, np.nan, 6.0]})
    _load_book(win, "src.csv [ตาราง]", df)
    win.ask_form = lambda *a, **k: {"method": "mean", "value": 0.0}
    win.feature_clean_fill_missing()

    out = tmp_path / "workflow.json"
    win.ask_save_path = lambda *a, **k: str(out)
    win.wf_export()
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["stamp"]["app"] == "SciPlotter"
    assert payload["source_checksum"]  # checksum of the current df recorded
    assert payload["operations"][0]["op"] == "fill_missing"

    # fresh Book with different values → re-run the same workflow on it
    df2 = pd.DataFrame({"t": np.arange(4, dtype=float),
                        "y": [10.0, np.nan, 30.0, np.nan]})
    _load_book(win, "other.csv [ตาราง]", df2)
    win.ask_open_path = lambda *a, **k: str(out)
    win.wf_import_and_run()

    assert "y_filled" in win._df.columns
    assert win._df["y_filled"].tolist() == [10.0, 20.0, 30.0, 20.0]


def test_generate_script_writes_runnable_python(win, tmp_path):
    _load_book(win, "scr.csv [ตาราง]",
               pd.DataFrame({"t": [0.0, 1.0, 2.0], "y": [5.0, 6.0, 7.0]}))
    win.ask_form = lambda *a, **k: {"method": "zscore"}
    win.feature_clean_normalize()

    out = tmp_path / "wf_script.py"
    win.ask_save_path = lambda *a, **k: str(out)
    win.wf_generate_script()

    assert out.exists()
    script = out.read_text(encoding="utf-8")
    assert "def apply_workflow(df):" in script
    assert "cleaning.normalize_column" in script

    namespace: dict = {"__name__": "wf_test"}
    exec(compile(script, str(out), "exec"), namespace)
    result = namespace["apply_workflow"](pd.DataFrame({"y": [1.0, 2.0, 3.0]}))
    assert "y_zscore" in result.columns
    assert result["y_zscore"].mean() == pytest.approx(0.0, abs=1e-12)


def test_history_view_and_clear(win):
    _load_book(win, "hv.csv [ตาราง]", pd.DataFrame({"t": [0, 1], "y": [1.0, 2.0]}))
    win.ask_form = lambda *a, **k: {"method": "minmax"}
    win.feature_clean_normalize()

    reports = []
    win.inform = lambda title, text: reports.append((title, text))
    win.wf_show_history()
    assert "normalize_column" in reports[-1][1]

    win.wf_clear()
    assert len(win.analysis_history) == 0
    win.wf_show_history()
    assert "ยังไม่มี" in reports[-1][1]
