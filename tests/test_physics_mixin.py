"""Physics / General Lab integration tests through the real MainWindow."""
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


def test_physics_module_registered_in_modules_gallery_and_search(win):
    assert win.shell.context_widget("modules") is win.modules_panel
    assert win.modules_panel.module_widget("physics_lab") is win.physics_panel
    assert win.shell.context_widget("physics_lab") is None

    win.show_module_gallery("physics_lab")

    assert win.modules_panel.current_module_id() == "physics_lab"
    win.modules_panel.set_search_text("pendulum")
    assert win.modules_panel.visible_module_ids() == ["physics_lab"]
    assert "Physics / General Lab" not in [_clean_text(a.text()) for a in win.menuBar().actions()]


def test_physics_menu_actions_execute_user_flows(win):
    current = np.linspace(-0.002, 0.002, 40)
    voltage = 150.0 * current
    time = np.linspace(0, 5, 40)
    rc = 5.0 * (1.0 - np.exp(-time / 1.2))
    length = np.linspace(0.25, 1.1, 40)
    period = 2 * np.pi * np.sqrt(length / 9.81)
    df = pd.DataFrame({
        "current": current,
        "voltage": voltage,
        "time": time,
        "rc_voltage": rc,
        "length": length,
        "period": period,
    })
    win._stage_insert("physics.csv [table]", df, None)
    source_df = df.copy()
    forms = [
        {"current_col": "current", "voltage_col": "voltage"},
        {"time_col": "time", "value_col": "rc_voltage", "mode": "charge"},
        {"length_col": "length", "period_col": "period"},
        {
            "coefficient": 1.0,
            "a_value": 2.0,
            "a_unc": 0.1,
            "a_power": 1.0,
            "b_value": 3.0,
            "b_unc": 0.2,
            "b_power": 2.0,
            "c_value": 1.0,
            "c_unc": 0.0,
            "c_power": 0.0,
        },
    ]
    reports, errors = _stub_forms(win, forms)
    menu = _submenu(_top_menu(win, "Modules"), "Physics / General Lab")
    graphs_before = win.tabs.count()

    for text in (
        "Ohm's Law Fit...",
        "RC Time Constant...",
        "Pendulum g Fit...",
        "Uncertainty Propagation...",
    ):
        win._df = source_df
        win.workbook.set_dataframe(source_df)
        win.workbook.source_df = source_df
        win.load_columns_from_df()
        _menu_action(menu, text).trigger()

    assert errors == []
    assert len(reports) == 4
    assert any("Ohm" in title for title, _text in reports)
    assert any("RC" in title for title, _text in reports)
    assert any("Pendulum" in title for title, _text in reports)
    assert any("Uncertainty" in title for title, _text in reports)
    assert win.tabs.count() >= graphs_before + 3
    assert any(name.startswith("Ohm Law Fit") for name in win._datasets)
    assert any(name.startswith("RC Time Constant") for name in win._datasets)
    assert any(name.startswith("Uncertainty Propagation") for name in win._datasets)
