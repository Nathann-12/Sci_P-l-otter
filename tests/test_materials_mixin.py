"""Materials Science module integration tests through the real MainWindow."""
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


def test_materials_module_registered_in_modules_gallery_and_search(win):
    assert win.shell.context_widget("modules") is win.modules_panel
    assert win.modules_panel.module_widget("materials") is win.materials_panel
    assert win.shell.context_widget("materials") is None

    win.show_module_gallery("materials")

    assert win.modules_panel.current_module_id() == "materials"
    win.modules_panel.set_search_text("arrhenius")
    assert win.modules_panel.visible_module_ids() == ["materials"]
    assert "Materials Science" not in [_clean_text(a.text()) for a in win.menuBar().actions()]


def test_materials_menu_actions_execute_user_flows(win):
    temp = np.linspace(280.0, 420.0, 32)
    sigma = 2.0e4 * np.exp(-0.28 / (8.617333262145e-5 * temp))
    voltage = np.linspace(-0.2, 0.2, temp.size)
    current = voltage / 100.0
    tga_temp = np.linspace(30, 800, temp.size)
    mass = 100.0 - 30.0 / (1.0 + np.exp(-(tga_temp - 430.0) / 18.0))
    df = pd.DataFrame({
        "sample": ["A", "B", "C", "D"] * 8,
        "composition": ["x", "x", "y", "y"] * 8,
        "temperature_K": temp,
        "conductivity": sigma,
        "voltage": voltage,
        "current": current,
        "tga_temp": tga_temp,
        "mass": mass,
        "score": np.linspace(1, 32, temp.size),
    })
    win._stage_insert("materials.csv [table]", df, None)
    source_df = df.copy()
    forms = [
        {"voltage_col": "voltage", "current_col": "current", "length_m": 0.01, "area_m2": 1e-6, "thickness_m": 1e-6},
        {"temperature_col": "temperature_K", "conductivity_col": "conductivity"},
        {"temperature_col": "tga_temp", "value_col": "mass", "mode": "tga_loss", "onset_fraction": 0.05},
        {"sample_col": "sample", "metric_col": "score", "group_col": "composition", "direction": "higher is better"},
    ]
    reports, errors = _stub_forms(win, forms)
    menu = _submenu(_top_menu(win, "Modules"), "Materials Science")
    graphs_before = win.tabs.count()

    for text in (
        "Conductivity / Resistivity...",
        "Arrhenius Activation Energy...",
        "TGA / DSC Thermal Metrics...",
        "Rank Samples...",
    ):
        win._df = source_df
        win.workbook.set_dataframe(source_df)
        win.workbook.source_df = source_df
        win.load_columns_from_df()
        _menu_action(menu, text).trigger()

    assert errors == []
    assert len(reports) == 4
    assert any("Conductivity" in title for title, _text in reports)
    assert any("Arrhenius" in title for title, _text in reports)
    assert any("Thermal" in title or "TGA" in title for title, _text in reports)
    assert any("Rank" in title for title, _text in reports)
    assert win.tabs.count() >= graphs_before + 3
    assert any(name.startswith("Materials Conductivity") for name in win._datasets)
    assert any(name.startswith("Arrhenius Activation") for name in win._datasets)
    assert any(name.startswith("Materials Ranking") for name in win._datasets)
