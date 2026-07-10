"""Spectroscopy module integration tests through the real MainWindow."""
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
    return (text or "").replace("&", "").replace("Ã¢â‚¬Â¦", "...").strip()


def _top_menu(win, title: str):
    for action in win.menuBar().actions():
        menu = action.menu()
        if menu is not None and _clean_text(menu.title()) == title:
            return menu
    raise AssertionError(f"top menu not found: {title}")


def _submenu(menu, title: str):
    target = _clean_text(title)
    for action in menu.actions():
        child = action.menu()
        if child is not None and _clean_text(child.title()) == target:
            return child
    raise AssertionError(f"submenu not found: {title}")


def _menu_action(menu, text: str):
    target = _clean_text(text)
    for action in menu.actions():
        if not action.isSeparator() and _clean_text(action.text()) == target:
            return action
    raise AssertionError(f"action not found: {text}")


def _stub_forms(win, forms):
    reports = []
    errors = []
    form_iter = iter(forms)
    win.ask_form = lambda *a, **k: next(form_iter)
    win.inform = lambda title, text: reports.append((title, text))
    win.error_box = lambda title, text: errors.append((title, text))
    win.notify = lambda *a, **k: None
    return reports, errors


def test_spectroscopy_module_registered_in_modules_gallery_and_search(win):
    assert win.shell.context_widget("modules") is win.modules_panel
    assert win.modules_panel.module_widget("spectroscopy") is win.spectroscopy_panel
    assert win.shell.context_widget("spectroscopy") is None

    win.show_module_gallery("spectroscopy")

    assert not win.shell.rail.isHidden()
    assert win.modules_panel.current_module_id() == "spectroscopy"
    win.modules_panel.set_search_text("scherrer")
    assert win.modules_panel.visible_module_ids() == ["spectroscopy"]
    assert "Spectroscopy" not in [_clean_text(a.text()) for a in win.menuBar().actions()]


def test_spectroscopy_menu_actions_execute_user_flows(win):
    x = np.linspace(1000, 1800, 401)
    raman = 0.001 * (x - 1000) + 2.0
    raman += 2.0 * np.exp(-0.5 * ((x - 1350) / 20) ** 2)
    raman += 4.0 * np.exp(-0.5 * ((x - 1580) / 25) ** 2)
    energy = np.linspace(1.5, 3.2, x.size)
    absorbance = np.clip(energy - 2.05, 0, None) / energy
    df = pd.DataFrame({
        "shift": x,
        "intensity": raman,
        "energy": energy,
        "absorbance": absorbance,
    })
    win._stage_insert("spectra.csv [table]", df, None)
    source_df = df.copy()
    forms = [
        {"x_col": "shift", "y_col": "intensity", "degree": 1, "quantile": 0.25, "normalize": "max"},
        {"x_col": "shift", "y_col": "intensity", "threshold_rel": 0.35, "min_distance": 25},
        {"x_col": "shift", "y_col": "intensity", "d_min": 1250.0, "d_max": 1450.0, "g_min": 1500.0, "g_max": 1650.0},
        {"energy_col": "energy", "abs_col": "absorbance", "exponent": "1.0", "fit_fraction": 0.45},
        {"two_theta": 26.5, "fwhm": 0.2, "wavelength": 1.5406, "shape_factor": 0.9},
    ]
    reports, errors = _stub_forms(win, forms)
    menu = _submenu(_top_menu(win, "Modules"), "Spectroscopy")
    graphs_before = win.tabs.count()

    for text in (
        "Baseline + Normalize...",
        "Peak Table...",
        "Raman D/G Ratio...",
        "Tauc Band Gap...",
        "XRD Scherrer Size...",
    ):
        win._df = source_df
        win.workbook.set_dataframe(source_df)
        win.workbook.source_df = source_df
        win.load_columns_from_df()
        _menu_action(menu, text).trigger()

    assert errors == []
    assert len(reports) == 5
    assert any("Spectrum Preprocess" in title for title, _text in reports)
    assert any("Peak" in title for title, _text in reports)
    assert any("Raman" in title for title, _text in reports)
    assert any("Tauc" in title for title, _text in reports)
    assert any("Scherrer" in title for title, _text in reports)
    assert win.tabs.count() >= graphs_before + 4
    assert any(name.startswith("Spectrum Preprocess") for name in win._datasets)
    assert any(name.startswith("Raman DG Ratio") for name in win._datasets)
    assert any(name.startswith("XRD Scherrer Size") for name in win._datasets)
