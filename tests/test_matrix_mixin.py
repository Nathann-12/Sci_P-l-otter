"""Matrix menu workflow on a real MainWindow (headless) + AI matrix tools."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture()
def window(qapp):
    import main

    win = main.MainWindow()
    win.show()
    yield win
    try:
        win.close()
    except RuntimeError:
        pass


def _xyz_frame():
    gx = np.linspace(0.0, 4.0, 9)
    gy = np.linspace(0.0, 2.0, 5)
    mesh_x, mesh_y = np.meshgrid(gx, gy)
    z = np.sin(mesh_x) + mesh_y
    return pd.DataFrame({
        "xpos": mesh_x.ravel(), "ypos": mesh_y.ravel(), "height": z.ravel(),
    })


def _menu(window, title):
    wanted = title.replace("&", "")
    stack = [a.menu() for a in window.menuBar().actions() if a.menu()]
    while stack:
        menu = stack.pop()
        if menu.title().replace("&", "") == wanted:
            return menu
        stack.extend(a.menu() for a in menu.actions() if a.menu())
    return None


def _action(menu, text):
    for action in menu.actions():
        if action.text().replace("&", "") == text:
            return action
    raise AssertionError(f"action {text!r} not in menu {menu.title()!r}")


def test_matrix_menu_exists_with_workflow_sections(window):
    menu = _menu(window, "Matrix")
    assert menu is not None
    titles = {a.menu().title().replace("&", "") for a in menu.actions() if a.menu()}
    assert {"Convert", "Transform", "Filter && Background".replace("&&", "&"),
            "Visualize"} <= titles or {"Convert", "Transform", "Visualize"} <= titles


def test_grid_core_creates_matrix_book_and_transform_chain(window):
    frame = _xyz_frame()
    window._stage_insert("XYZ Source", frame, None)
    book, result = window.matrix_grid_core("xpos", "ypos", "height")
    assert result.method == "regular"          # complete grid pivots exactly
    assert result.shape == (5, 9)
    assert book in window._datasets

    # activate the matrix Book and run a transform through the same core the AI uses
    window._df = window._datasets[book]["df"]
    tbook, shape = window.matrix_transform_core("transpose")
    assert shape == (9, 5)
    assert tbook in window._datasets

    # round-trip back to XYZ
    window._df = window._datasets[book]["df"]
    window.matrix_to_xyz_book()
    xyz_books = [n for n in window._datasets if n.startswith("Matrix XYZ")]
    assert xyz_books
    xyz = window._datasets[xyz_books[0]]["df"]
    assert set(xyz.columns) == {"x", "y", "z"} and len(xyz) == 45


def test_matrix_plot_core_creates_graphs_for_all_kinds(window):
    frame = _xyz_frame()
    window._stage_insert("XYZ Plot", frame, None)
    book, _ = window.matrix_grid_core("xpos", "ypos", "height")
    window._df = window._datasets[book]["df"]
    before = len(window.tabs.tabs)
    for kind in ("heatmap", "contour", "surface"):
        note = window.matrix_plot_core(kind)
        assert "matrix" in note
    assert len(window.tabs.tabs) == before + 3


def test_matrix_menu_transform_actions_trigger_via_qaction(window):
    frame = _xyz_frame()
    window._stage_insert("XYZ Menu", frame, None)
    book, _ = window.matrix_grid_core("xpos", "ypos", "height")
    window._df = window._datasets[book]["df"]
    menu = _menu(window, "Matrix")
    transform = next(a.menu() for a in menu.actions()
                     if a.menu() and a.menu().title().replace("&", "") == "Transform")
    n_books = len(window._datasets)
    _action(transform, "Flip Horizontal").trigger()
    assert len(window._datasets) == n_books + 1


def test_ai_matrix_tools_end_to_end(window):
    from ai.app_tools import build_app_registry

    frame = _xyz_frame()
    window._stage_insert("XYZ AI", frame, None)
    registry = build_app_registry(window)
    out = registry.execute("grid_xyz", {
        "x_column": "xpos", "y_column": "ypos", "z_column": "height",
    })
    assert "matrix" in out and "Book" in out

    matrix_books = [n for n in window._datasets if n.startswith("Matrix height")]
    assert matrix_books
    window._df = window._datasets[matrix_books[-1]]["df"]

    out = registry.execute("matrix_transform", {"op": "smooth_gaussian", "sigma": 1.0})
    assert "smooth_gaussian" in out
    out = registry.execute("matrix_transform", {"op": "not_an_op"})
    assert "Could not apply" in out or "Unknown" in out
    out = registry.execute("plot_matrix", {"kind": "heatmap"})
    assert "heatmap" in out


def test_ai_grid_xyz_defensive_without_data(window):
    from ai.app_tools import build_app_registry

    # force truly-empty state regardless of earlier tests
    window._df = pd.DataFrame()
    window._datasets = {}
    workbook = getattr(window, "workbook", None)
    out = build_app_registry(window).execute("grid_xyz", {})
    assert "No active data" in out or "three numeric columns" in out
