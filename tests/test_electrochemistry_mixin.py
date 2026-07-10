"""Electrochemistry module integration tests through the real MainWindow."""
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


def _clean_text(text: str) -> str:
    return (text or "").replace("&", "").replace("â€¦", "...").strip()


def _top_menu(win, title: str):
    for action in win.menuBar().actions():
        menu = action.menu()
        if menu is not None and _clean_text(menu.title()) == title:
            return menu
    raise AssertionError(f"top menu not found: {title}")


def _menu_action(menu, text: str):
    target = _clean_text(text)
    for action in menu.actions():
        if action.isSeparator():
            continue
        if _clean_text(action.text()) == target:
            return action
    raise AssertionError(f"action not found: {text}")


def _submenu(menu, title: str):
    target = _clean_text(title)
    for action in menu.actions():
        child = action.menu()
        if child is not None and _clean_text(child.title()) == target:
            return child
    raise AssertionError(f"submenu not found: {title}")


def _stub_forms(win, forms):
    reports = []
    errors = []
    form_iter = iter(forms)
    win.ask_form = lambda *a, **k: next(form_iter)
    win.inform = lambda title, text: reports.append((title, text))
    win.error_box = lambda title, text: errors.append((title, text))
    win.notify = lambda *a, **k: None
    return reports, errors


def test_electrochemistry_module_registered_in_modules_gallery_and_menu(win):
    assert win.shell.context_widget("modules") is win.modules_panel
    assert win.modules_panel.module_widget("electrochemistry") is win.electrochemistry_panel
    assert win.shell.context_widget("electrochemistry") is None
    assert win.shell.rail.isHidden()
    assert win.shell.context_stack.isHidden()

    win.show_module_gallery("electrochemistry")

    assert not win.shell.rail.isHidden()
    assert not win.shell.context_stack.isHidden()
    assert win.shell.current_context_id() == "modules"
    assert win.modules_panel.current_module_id() == "electrochemistry"
    menu_titles = [_clean_text(a.text()) for a in win.menuBar().actions()]
    assert "Modules" in menu_titles
    assert "Electrochemistry" not in menu_titles
    for name in (
        "ec_cv_peak_metrics",
        "ec_randles_ecsa",
        "ec_tafel_analysis",
        "ec_gcd_metrics",
        "ec_eis_analysis",
    ):
        assert callable(getattr(win, name))


def test_electrochemistry_menu_actions_execute_user_flows(win):
    df = pd.DataFrame({
        "potential": [-0.2, 0.0, 0.25, 0.5, 0.2, -0.1],
        "current": [0.0, 0.2, 1.8, 0.4, -0.3, -1.2],
        "scan_rate": [0.01, 0.04, 0.09, 0.16, 0.25, 0.36],
        "peak_current": 2.0 * np.sqrt([0.01, 0.04, 0.09, 0.16, 0.25, 0.36]) + 0.1,
        "eta": 0.12 * np.log10([1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1]) + 0.7,
        "tafel_current": [1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1],
        "time": [0, 1, 2, 4, 8, 12],
        "voltage": [0.0, 1.0, 0.9, 0.6, 0.25, 0.0],
        "freq": [10000, 1000, 100, 10, 1, 0.1],
        "zreal": [5, 7, 12, 18, 25, 30],
        "zimag": [-0.5, -3, -6, -8, -4, -2],
    })
    win._stage_insert("ec.csv [table]", df, None)
    source_df = df.copy()

    forms = [
        {"potential_col": "potential", "current_col": "current"},
        {
            "scan_rate_col": "scan_rate",
            "peak_current_col": "peak_current",
            "n": 1.0,
            "diffusion": 1e-5,
            "concentration": 1e-6,
        },
        {"eta_col": "eta", "current_col": "tafel_current"},
        {"time_col": "time", "voltage_col": "voltage", "current_a": 0.002, "mass_g": 0.01},
        {"freq_col": "freq", "zreal_col": "zreal", "zimag_col": "zimag"},
    ]
    reports, errors = _stub_forms(win, forms)
    menu = _submenu(_top_menu(win, "Modules"), "Electrochemistry")
    graphs_before = win.tabs.count()

    for text in (
        "CV Peak Metrics...",
        "Randles-Sevcik + ECSA...",
        "Tafel Analysis...",
        "GCD / Supercapacitor Metrics...",
        "EIS Nyquist / Bode...",
    ):
        win._df = source_df
        win.workbook.set_dataframe(source_df)
        win.workbook.source_df = source_df
        win.load_columns_from_df()
        _menu_action(menu, text).trigger()

    assert errors == []
    assert len(reports) == 5
    assert any("CV Peak" in title for title, _text in reports)
    assert any("Randles" in title for title, _text in reports)
    assert any("Tafel" in title for title, _text in reports)
    assert any("GCD" in title for title, _text in reports)
    assert any("EIS" in title for title, _text in reports)
    assert win.tabs.count() >= graphs_before + 5
    assert any(name.startswith("CV Peak Metrics") for name in win._datasets)
    assert any(name.startswith("EIS Bode Data") for name in win._datasets)
