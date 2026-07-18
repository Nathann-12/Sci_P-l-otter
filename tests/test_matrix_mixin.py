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


def test_matrix_analysis_cores_statistics_profile_arithmetic(window):
    frame = _xyz_frame()
    window._stage_insert("XYZ Analyze", frame, None)
    book, _ = window.matrix_grid_core("xpos", "ypos", "height")
    window._df = window._datasets[book]["df"]

    stats_book, stats = window.matrix_statistics_core()
    assert stats_book in window._datasets
    assert {"min", "max", "mean", "max_x", "max_y"} <= set(stats)

    window._df = window._datasets[book]["df"]
    graphs_before = len(window.tabs.tabs)
    profile_book, n = window.matrix_line_profile_core((0.0, 1.0), (4.0, 1.0), samples=30)
    assert profile_book in window._datasets and n > 0
    assert set(window._datasets[profile_book]["df"].columns) >= {"distance", "value"}
    assert len(window.tabs.tabs) == graphs_before + 1  # profile is plotted

    # arithmetic needs a second matrix Book; duplicate the first
    window._datasets["Matrix Copy"] = {
        "df": window._datasets[book]["df"].copy(), "path": None}
    window._df = window._datasets[book]["df"]
    diff_book, shape = window.matrix_arithmetic_core("Matrix Copy", "subtract")
    assert diff_book in window._datasets
    z, _x, _y = _matrix_of(window, diff_book)
    assert np.allclose(np.nan_to_num(z), 0.0)  # A - A == 0


def test_matrix_fft2_and_resize_via_transform(window):
    frame = _xyz_frame()
    window._stage_insert("XYZ FFT", frame, None)
    book, _ = window.matrix_grid_core("xpos", "ypos", "height")
    window._df = window._datasets[book]["df"]
    fbook, shape = window.matrix_transform_core("fft2")
    assert fbook in window._datasets and shape == (5, 9)
    window._df = window._datasets[book]["df"]
    rbook, rshape = window.matrix_transform_core("resize", ny=8, nx=12)
    assert rshape == (8, 12)


def test_ai_matrix_analysis_tools(window):
    from ai.app_tools import build_app_registry

    frame = _xyz_frame()
    window._stage_insert("XYZ AI2", frame, None)
    registry = build_app_registry(window)
    registry.execute("grid_xyz", {
        "x_column": "xpos", "y_column": "ypos", "z_column": "height"})
    book = [n for n in window._datasets if n.startswith("Matrix height")][-1]

    window._df = window._datasets[book]["df"]
    assert "statistics" in registry.execute("matrix_statistics", {}).lower()
    window._df = window._datasets[book]["df"]
    assert "profile" in registry.execute(
        "line_profile", {"x0": 0, "y0": 1, "x1": 4, "y1": 1, "samples": 25}).lower()
    window._df = window._datasets[book]["df"]
    assert "fft2" in registry.execute("matrix_transform", {"op": "fft2"}).lower() \
        or "matrix" in registry.execute("matrix_transform", {"op": "fft2"}).lower()

    out = registry.execute("matrix_arithmetic", {"other_book": "nope"})
    assert "not available" in out or "Could not" in out


def test_matrix_image_ops_and_surface_and_stack(window):
    frame = _xyz_frame()
    window._stage_insert("XYZ Img", frame, None)
    book, _ = window.matrix_grid_core("xpos", "ypos", "height")

    def use_matrix():
        window._df = window._datasets[book]["df"]

    for op, params in (
        ("threshold", {"level": 0.0, "mode": "binary"}),
        ("edge_detect", {"method": "sobel"}),
        ("contrast", {"brightness": 0.1, "contrast": 2.0}),
        ("morphology", {"mode": "dilate", "size": 3}),
        ("gradient", {}),
    ):
        use_matrix()
        out_book, shape = window.matrix_transform_core(op, **params)
        assert out_book in window._datasets and shape == (5, 9)

    use_matrix()
    roi_book, roi_shape = window.matrix_transform_core(
        "roi", x0=1.0, x1=3.0, y0=0.5, y1=2.5)
    assert roi_shape[0] < 5 and roi_shape[1] < 9

    use_matrix()
    sbook, metrics = window.matrix_surface_metrics_core()
    assert sbook in window._datasets
    assert {"Ra", "Rq", "peak_to_valley", "volume_above_min"} <= set(metrics)

    # a stack from two duplicated matrix Books
    window._datasets["Frame A"] = {"df": window._datasets[book]["df"].copy(), "path": None}
    window._datasets["Frame B"] = {"df": window._datasets[book]["df"].copy(), "path": None}
    pbook, pshape = window.matrix_stack_core(["Frame A", "Frame B"], "max")
    assert pbook in window._datasets and pshape == (5, 9)


def test_ai_matrix_image_surface_stack_tools(window):
    from ai.app_tools import build_app_registry

    frame = _xyz_frame()
    window._stage_insert("XYZ AI3", frame, None)
    registry = build_app_registry(window)
    registry.execute("grid_xyz", {
        "x_column": "xpos", "y_column": "ypos", "z_column": "height"})
    book = [n for n in window._datasets if n.startswith("Matrix height")][-1]

    window._df = window._datasets[book]["df"]
    assert "surface metrics" in registry.execute("surface_metrics", {}).lower()
    window._df = window._datasets[book]["df"]
    assert "threshold" in registry.execute(
        "matrix_transform", {"op": "threshold", "level": 0.0}).lower()

    window._datasets["FA"] = {"df": window._datasets[book]["df"].copy(), "path": None}
    window._datasets["FB"] = {"df": window._datasets[book]["df"].copy(), "path": None}
    window._df = window._datasets[book]["df"]
    assert "projection" in registry.execute(
        "matrix_stack", {"books": ["FA", "FB"], "mode": "mean"}).lower()
    assert "at least two" in registry.execute(
        "matrix_stack", {"books": ["FA"]}).lower()


def _matrix_of(window, book):
    from analysis.gridding import dataframe_to_matrix

    return dataframe_to_matrix(window._datasets[book]["df"])


def test_ai_grid_xyz_defensive_without_data(window):
    from ai.app_tools import build_app_registry

    # force truly-empty state regardless of earlier tests
    window._df = pd.DataFrame()
    window._datasets = {}
    workbook = getattr(window, "workbook", None)
    out = build_app_registry(window).execute("grid_xyz", {})
    assert "No active data" in out or "three numeric columns" in out
