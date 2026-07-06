"""Wire + behavior tests for the Gas Sensor module inside the real MainWindow
(headless). The math itself is covered in test_gas_sensor.py."""
from __future__ import annotations

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


def _stub_prompts(win, forms=()):
    """Feed scripted form results (one dict per ask_form call) and capture
    inform() calls."""
    reports = []
    form_iter = iter(forms)
    win.ask_form = lambda *a, **k: next(form_iter)
    win.inform = lambda title, text: reports.append((title, text))
    return reports


def test_module_registered_in_rail_and_menu(win):
    assert win.shell.context_widget("gas_sensor") is win.gas_sensor_panel
    assert not win.shell.rail.isHidden()
    menu_titles = [a.text().replace("&", "") for a in win.menuBar().actions()]
    assert "Gas Sensor" in menu_titles
    for name in ("gs_analyze_response", "gs_detect_cycles",
                 "gs_calibration", "gs_dilution"):
        assert callable(getattr(win, name))


def test_gs_analyze_response_end_to_end(win):
    # synthetic exposure: Ra=100 → Rg=20 (exponential, tau=5)
    t = np.linspace(0, 300, 3001)
    y = np.full_like(t, 100.0)
    on = (t >= 50) & (t < 150)
    y[on] = 20 + 80 * np.exp(-(t[on] - 50) / 5.0)
    rec = t >= 150
    y[rec] = 100 - 80 * np.exp(-(t[rec] - 150) / 5.0)
    df = pd.DataFrame({"time": t, "resistance": y})
    win._stage_insert("gas.csv [ตาราง]", df, None)

    reports = _stub_prompts(
        win, forms=[{"y_col": "resistance", "t_on": 50.0, "t_off": 150.0}])
    win.gs_analyze_response()

    assert reports, "analysis must report via inform()"
    title, text = reports[-1]
    assert "resistance" in title
    assert "Response: 80" in text            # 80 %
    assert "Sensitivity" in text and "5" in text  # Ra/Rg = 5


def test_gs_detect_cycles_reports_three_pulses(win):
    t = np.linspace(0, 600, 6001)
    y = np.full_like(t, 100.0)
    for on, off in ((100, 150), (300, 350), (500, 550)):
        y[(t >= on) & (t <= off)] = 30.0
    df = pd.DataFrame({"time": t, "r": y})
    win._stage_insert("cycles.csv [ตาราง]", df, None)

    reports = _stub_prompts(
        win, forms=[{"y_col": "r", "threshold_pct": 5.0}])
    win.gs_detect_cycles()

    assert reports
    _title, text = reports[-1]
    assert "พบ 3 รอบ" in text


def test_gs_calibration_plots_new_graph_and_reports_lod(win):
    conc = [10.0, 20.0, 50.0, 100.0]
    resp = [0.4 * c + 2.0 for c in conc]
    df = pd.DataFrame({"conc": conc, "resp": resp})
    win._stage_insert("calib.csv [ตาราง]", df, None)

    graphs_before = win.tabs.count()
    reports = _stub_prompts(win, forms=[{
        "conc_col": "conc", "resp_col": "resp", "model": "linear", "noise_std": 0.2}])
    win.gs_calibration()

    assert win.tabs.count() == graphs_before + 1  # new calibration Graph
    _title, text = reports[-1]
    assert "slope: 0.4" in text
    assert "R²: 1" in text
    assert "LOD" in text and "1.5" in text  # 3*0.2/0.4 = 1.5


def test_gs_dilution_computes_ppm(win):
    reports = _stub_prompts(win, forms=[{
        "source_ppm": 1000.0, "flow_gas": 2.0, "flow_total": 100.0}])
    win.gs_dilution()

    _title, text = reports[-1]
    assert "20 ppm" in text
