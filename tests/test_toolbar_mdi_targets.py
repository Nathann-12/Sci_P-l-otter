from __future__ import annotations

import os
from pathlib import Path
import sys

import pandas as pd
import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("PySide6")
pytest.importorskip("numexpr")

from PySide6.QtWidgets import QApplication, QDialog

from widgets.workbook import META_ROW_COUNT


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main

    w = app_main.MainWindow()
    yield w
    w.close()


def _seed_book(win, rows=None):
    rows = rows or [(0, 1.0), (1, 4.0), (2, 9.0), (3, 16.0)]
    wb = win.workbook
    wb.set_meta(0, long_name="t")
    wb.set_meta(1, long_name="signal")
    for r, (xv, yv) in enumerate(rows):
        wb.table.item(META_ROW_COUNT + r, 0).setText(str(xv))
        wb.table.item(META_ROW_COUNT + r, 1).setText(str(yv))
    assert win.adopt_workbook_data() is True


def _toolbar_action(win, text):
    # search the top two rows AND the categorized left/right/bottom docks — a
    # tool may live on any surface after the toolbar reorganization
    toolbars = [getattr(win, "tb", None), getattr(win, "function_toolbar", None)]
    toolbars.extend((getattr(win, "side_toolbars", {}) or {}).values())
    for toolbar in toolbars:
        if toolbar is None:
            continue
        for action in toolbar.actions():
            if action.text().replace("&", "") == text:
                return action
    raise AssertionError(f"toolbar action not found: {text}")


def _focus_book(win, qapp):
    win.mdi.mdi.setActiveSubWindow(win._book_sub)
    qapp.processEvents()


def _focus_graph(win, qapp, tab_id):
    win.mdi.mdi.setActiveSubWindow(win.mdi._graph_subs[tab_id])
    qapp.processEvents()


def _new_selected_graph(win, qapp, name="Graph 2"):
    tab_id = win.tabs.add_tab(name)
    _focus_graph(win, qapp, tab_id)
    return tab_id


def _artist_count(ax):
    return (
        len(ax.get_lines())
        + len(getattr(ax, "collections", []))
        + len(getattr(ax, "containers", []))
        + len(getattr(ax, "patches", []))
        + len(getattr(ax, "images", []))
    )


def test_plot_command_with_no_graph_open_creates_one(win, qapp):
    # Origin loop: the app starts sheet-first with no Graph window; the first
    # plot command must create the Graph, not die with a "no tab" warning.
    _seed_book(win)
    assert win.tabs.count() == 0

    win.plot_line()

    assert win.tabs.count() == 1
    assert len(win.tabs.currentWidget().get_axes().get_lines()) == 1


def test_main_plot_action_draws_on_last_selected_graph_after_book_focus(win, qapp):
    _seed_book(win)
    first_id = _new_selected_graph(win, qapp, "Graph 1")
    second_id = _new_selected_graph(win, qapp)

    _focus_book(win, qapp)
    _toolbar_action(win, "Plot").trigger()

    assert len(win.tabs.tabs[second_id].get_axes().get_lines()) == 1
    assert len(win.tabs.tabs[first_id].get_axes().get_lines()) == 0


@pytest.mark.parametrize("style", ["line", "scatter", "linesymbol", "bar", "histogram"])
def test_bottom_plot_toolbar_styles_create_new_graph_after_book_focus(win, qapp, style):
    _seed_book(win)
    second_id = _new_selected_graph(win, qapp)
    before_count = win.tabs.count()
    before_artists = _artist_count(win.tabs.tabs[second_id].get_axes())

    _focus_book(win, qapp)
    win.plot_bar_actions[style].trigger()

    assert win.tabs.count() == before_count + 1
    assert _artist_count(win.tabs.tabs[second_id].get_axes()) == before_artists
    assert _artist_count(win.tabs.currentWidget().get_axes()) > 0


def test_book_overlay_targets_last_selected_graph_after_book_focus(win, qapp):
    from core.plot_mode import PlotMode

    win.plot_mode = PlotMode.OVERLAY
    _seed_book(win)
    first_id = _new_selected_graph(win, qapp, "Graph 1")
    second_id = _new_selected_graph(win, qapp)
    win.plot_from_workbook("line", new_graph=False)
    before_count = win.tabs.count()
    before_lines = len(win.tabs.tabs[second_id].get_axes().get_lines())

    _focus_book(win, qapp)
    win.plot_from_workbook("line", new_graph=False)

    assert win.tabs.count() == before_count
    assert len(win.tabs.tabs[second_id].get_axes().get_lines()) == before_lines + 1
    assert len(win.tabs.tabs[first_id].get_axes().get_lines()) == 0


def test_crosshair_and_boxzoom_toolbar_use_last_graph_canvas_after_book_focus(win, qapp, monkeypatch):
    second_id = _new_selected_graph(win, qapp)
    target_ax = win.tabs.tabs[second_id].get_axes()
    captured = {}

    class _Cursor:
        def __init__(self, ax, **_kwargs):
            captured["cursor_ax"] = ax

    class _RectangleSelector:
        def __init__(self, ax, callback, **kwargs):
            captured["zoom_ax"] = ax
            captured["zoom_callback"] = callback
            captured["zoom_kwargs"] = kwargs

        def set_active(self, _value):
            pass

    monkeypatch.setattr("main_window_view_mixin.Cursor", _Cursor)
    monkeypatch.setattr("main_window_view_mixin.RectangleSelector", _RectangleSelector)

    _focus_book(win, qapp)
    win.actCrosshair.setChecked(True)
    win.actBoxZoom.trigger()

    assert captured["cursor_ax"] is target_ax
    assert captured["zoom_ax"] is target_ax
    assert win.canvas is win.tabs.tabs[second_id].canvas


def test_export_figure_toolbar_saves_last_selected_graph_after_book_focus(win, qapp, monkeypatch, tmp_path):
    first_id = _new_selected_graph(win, qapp, "Graph 1")
    second_id = _new_selected_graph(win, qapp)
    out_path = tmp_path / "active.png"
    saved = []

    monkeypatch.setattr(
        "main_window_export_mixin.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(out_path), "PNG Image (*.png)"),
    )
    monkeypatch.setattr(
        win.tabs.tabs[first_id].get_figure(),
        "savefig",
        lambda *args, **kwargs: saved.append(("first", args, kwargs)),
    )
    monkeypatch.setattr(
        win.tabs.tabs[second_id].get_figure(),
        "savefig",
        lambda *args, **kwargs: saved.append(("second", args, kwargs)),
    )

    _focus_book(win, qapp)
    _toolbar_action(win, "Export Figure").trigger()

    assert [entry[0] for entry in saved] == ["second"]
    assert saved[0][1][0] == str(out_path)


def test_export_data_toolbar_uses_last_selected_graph_xlim_after_book_focus(win, qapp, monkeypatch, tmp_path):
    _seed_book(win, rows=[(0, 10), (1, 20), (2, 30), (3, 40)])
    first_id = _new_selected_graph(win, qapp, "Graph 1")
    second_id = _new_selected_graph(win, qapp)
    win.plot_line()
    win.tabs.tabs[first_id].get_axes().set_xlim(0.0, 0.5)
    win.tabs.tabs[second_id].get_axes().set_xlim(1.5, 2.5)
    out_path = tmp_path / "visible.csv"

    monkeypatch.setattr(
        "main_window_export_mixin.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(out_path), "CSV (*.csv)"),
    )

    _focus_book(win, qapp)
    _toolbar_action(win, "Export Data").trigger()

    saved = pd.read_csv(out_path)
    assert saved.to_dict(orient="list") == {"t": [2], "signal": [30]}


def test_format_graph_toolbar_reads_last_selected_graph_after_book_focus(win, qapp, monkeypatch):
    import dialogs.plot_details_dialog as plot_details_dialog

    first_id = _new_selected_graph(win, qapp, "Graph 1")
    second_id = _new_selected_graph(win, qapp)
    win.tabs.tabs[first_id].get_axes().plot([0, 1], [1, 1], label="graph-one")
    win.tabs.tabs[second_id].get_axes().plot([0, 1], [2, 2], label="graph-two")
    captured = {}

    class _Signal:
        def connect(self, _callback):
            pass

    class _Dialog:
        def __init__(self, _style, line_styles, **_kwargs):
            captured["labels"] = [line["label"] for line in line_styles]
            self.applied = _Signal()
            self.save_template_requested = _Signal()
            self.load_template_requested = _Signal()

        def exec(self):
            return QDialog.Rejected

    monkeypatch.setattr(plot_details_dialog, "PlotDetailsDialog", _Dialog)

    _focus_book(win, qapp)
    win.actFormatGraph.trigger()

    assert captured["labels"] == ["graph-two"]


def test_curve_fit_reads_last_selected_graph_after_book_focus(win, qapp, monkeypatch):
    import dialogs

    _seed_book(win)
    first_id = _new_selected_graph(win, qapp, "Graph 1")
    second_id = _new_selected_graph(win, qapp)
    win.tabs.tabs[first_id].get_axes().plot([0, 1], [1, 1], label="graph-one")
    win.tabs.tabs[second_id].get_axes().plot([0, 1], [2, 3], label="graph-two")
    captured = {}

    class _FitDialog:
        def __init__(self, _parent, labels, _series_data):
            captured["labels"] = list(labels)

        def exec(self):
            return QDialog.Rejected

    monkeypatch.setattr(dialogs, "FitDialog", _FitDialog)

    _focus_book(win, qapp)
    win._open_fit_dialog()

    # Origin-style: the fit reads the series from the last-selected graph.
    assert captured["labels"] == ["graph-two"]


def test_curve_fit_overlay_draws_on_last_selected_graph_after_book_focus(win, qapp, monkeypatch):
    import dialogs

    _seed_book(win)
    first_id = _new_selected_graph(win, qapp, "Graph 1")
    second_id = _new_selected_graph(win, qapp)
    win.tabs.tabs[first_id].get_axes().plot([0, 1, 2, 3], [0, 1, 2, 3], label="graph-one")
    win.tabs.tabs[second_id].get_axes().plot([0, 1, 2, 3], [0, 2, 4, 6], label="graph-two")
    first_before = len(win.tabs.tabs[first_id].get_axes().get_lines())
    second_before = len(win.tabs.tabs[second_id].get_axes().get_lines())

    class _FitDialog:
        def __init__(self, _parent, _labels, _series_data):
            pass

        def exec(self):
            return QDialog.Accepted

        def get_params(self):
            return {
                "series_label": "graph-two",
                "model": "linear",
                "degree": None,
                "show_eq": False,
                "show_resid": False,
            }

    monkeypatch.setattr(dialogs, "FitDialog", _FitDialog)
    # A modal error box would hang the offscreen suite; capture instead of block.
    errors = []
    monkeypatch.setattr(
        "main_window_fit_mixin.QMessageBox.critical",
        lambda *args, **kwargs: errors.append(args[2] if len(args) > 2 else args),
    )

    _focus_book(win, qapp)
    win._open_fit_dialog()

    assert not errors, f"fit raised: {errors}"

    # The fitted curve is drawn on the last-selected graph, not the stale one.
    assert len(win.tabs.tabs[second_id].get_axes().get_lines()) == second_before + 1
    assert len(win.tabs.tabs[first_id].get_axes().get_lines()) == first_before


def test_curve_fit_metrics_do_not_broadcast_mismatch(win):
    # Regression: _do_curve_fit evaluated the fit at 400 linspace points for the
    # R^2/RMSE metrics but compared them against the original (shorter) samples,
    # raising "operands could not be broadcast" for every model and popping a
    # modal "Fit failed" box — the fit never drew. Metrics must use the samples.
    import numpy as np

    x = np.linspace(1.0, 5.0, 9)
    cases = {
        "linear": 2.0 * x + 1.0,
        "polynomial": x ** 2 - x,
        "exponential": 2.0 * np.exp(0.3 * x) + 1.0,
        "power": 2.0 * x ** 1.5,
        "gaussian": 3.0 * np.exp(-0.5 * ((x - 3.0) / 0.8) ** 2) + 0.5,
        "sine": np.sin(2.0 * x) + 0.05 * x,
    }
    for model, y in cases.items():
        xfit, yfit, _params, metrics = win._do_curve_fit(x, y, model=model, degree=2)
        assert len(xfit) == len(yfit), model
        assert {"r2", "rmse"} <= set(metrics), model
        assert np.isfinite(metrics["r2"]), model


def test_plot_equation_toolbar_targets_last_selected_graph_after_book_focus(win, qapp, monkeypatch):
    import main_window_equation_mixin as equation_mixin

    first_id = _new_selected_graph(win, qapp, "Graph 1")
    second_id = _new_selected_graph(win, qapp)

    class _EquationDialog:
        def __init__(self, _parent):
            pass

        def exec(self):
            return QDialog.Accepted

        def get_values(self):
            return {
                "expressions": ["sin(x)"],
                "mode": "2d",
                "x_min": 0.0,
                "x_max": 1.0,
                "n_points": 50,
                "params": "",
                "y_scale": "linear",
                "overlay": True,
                "wireframe": False,
            }

    monkeypatch.setattr(equation_mixin, "EquationPlotDialog", _EquationDialog)

    _focus_book(win, qapp)
    win.actPlotEquation.trigger()

    assert len(win.tabs.tabs[second_id].get_axes().get_lines()) == 1
    assert len(win.tabs.tabs[first_id].get_axes().get_lines()) == 0


def test_processors_fft_toolbar_targets_last_selected_graph_after_book_focus(win, qapp, monkeypatch):
    _seed_book(win, rows=[(i, float(i * i)) for i in range(12)])
    first_id = _new_selected_graph(win, qapp, "Graph 1")
    second_id = _new_selected_graph(win, qapp)

    monkeypatch.setattr(
        type(win),
        "ask_form",
        lambda self, *_args, **_kwargs: {
            "y_col": "signal",
            "window": "none",
            "detrend": False,
        },
        raising=False,
    )

    _focus_book(win, qapp)
    _toolbar_action(win, "Processors").trigger()

    target_ax = win.tabs.tabs[second_id].get_axes()
    assert len(target_ax.get_lines()) == 1
    assert "FFT of signal" in (
        target_ax.get_title()
        or target_ax.get_title(loc="left")
        or target_ax.get_title(loc="right")
    )
    assert len(win.tabs.tabs[first_id].get_axes().get_lines()) == 0


def test_add_tab_toolbar_creates_and_selects_graph_after_book_focus(win, qapp):
    before_count = win.tabs.count()

    _focus_book(win, qapp)
    _toolbar_action(win, "New Graph").trigger()

    assert win.tabs.count() == before_count + 1
    assert win.tabs.currentWidget() is next(reversed(win.tabs.tabs.values()))
