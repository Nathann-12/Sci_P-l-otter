from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from core.plot_extras import add_secondary_y, draw_error_bars, draw_fill_between
from processors import beautify_axes

logger = logging.getLogger(__name__)


class MainWindowPlotExtraMixin:
    """Extra plot types (ROADMAP C): error bars, fill-between, secondary axis.

    Column pickers use the ask_form seam; error-bar/fill plots open a NEW graph
    (Origin loop), while the secondary axis is added to the CURRENT graph.
    Drawing math lives in core/plot_extras.py.
    """

    def _px_cols(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("No data", "Open or select a Book with data first")
            return None
        return [str(c) for c in self._df.columns]

    def _px_series(self, name):
        return pd.to_numeric(self._df[name], errors="coerce").to_numpy(dtype=float)

    # ------------------------------------------------------------- error bars
    def plot_error_bars(self):
        cols = self._px_cols()
        if not cols or len(cols) < 3:
            if cols is not None:
                self.inform("Need 3 columns", "Error-bar plot needs X, Y and an error column")
            return
        x_sel = self.selected_x_column()
        y_sel = self.selected_y_column()
        res = self.ask_form("Error Bar Plot", [
            {"name": "x", "label": "X column", "kind": "choice", "options": cols,
             "default": x_sel if x_sel in cols else cols[0]},
            {"name": "y", "label": "Y column", "kind": "choice", "options": cols,
             "default": y_sel if y_sel in cols else cols[1]},
            {"name": "yerr", "label": "Y error column", "kind": "choice", "options": cols,
             "default": cols[2] if len(cols) > 2 else cols[-1]},
            {"name": "xerr", "label": "X error column", "kind": "choice",
             "options": ["(none)"] + cols, "default": "(none)"},
        ], description="Plot Y vs X with error bars → new graph")
        if res is None:
            return
        try:
            self.tabs.add_tab()
            ax = self.tabs.currentWidget().get_axes()
            xerr = None if res["xerr"] == "(none)" else self._px_series(res["xerr"])
            draw_error_bars(ax, self._px_series(res["x"]), self._px_series(res["y"]),
                            self._px_series(res["yerr"]), xerr=xerr, label=res["y"])
            ax.set_xlabel(res["x"]); ax.set_ylabel(res["y"])
            beautify_axes(ax, title=f"{res['y']} vs {res['x']} (± {res['yerr']})")
            self.tabs.currentWidget().draw()
            self._show_plot_view()
            self.notify("Error-bar plot created")
        except Exception as e:
            self.error_box("Error-bar plot failed", f"Reason: {e}")

    # ---------------------------------------------------------- fill between
    def plot_fill_between(self):
        cols = self._px_cols()
        if not cols or len(cols) < 3:
            if cols is not None:
                self.inform("Need 3 columns", "Fill-between needs X and two Y columns")
            return
        x_sel = self.selected_x_column()
        res = self.ask_form("Fill Between (band)", [
            {"name": "x", "label": "X column", "kind": "choice", "options": cols,
             "default": x_sel if x_sel in cols else cols[0]},
            {"name": "y1", "label": "Lower Y column", "kind": "choice", "options": cols,
             "default": cols[1]},
            {"name": "y2", "label": "Upper Y column", "kind": "choice", "options": cols,
             "default": cols[2] if len(cols) > 2 else cols[-1]},
            {"name": "alpha", "label": "Opacity", "kind": "float", "default": 0.3,
             "min": 0.0, "max": 1.0, "decimals": 2, "step": 0.05},
        ], description="Shade the band between two Y curves → new graph")
        if res is None:
            return
        try:
            self.tabs.add_tab()
            ax = self.tabs.currentWidget().get_axes()
            draw_fill_between(ax, self._px_series(res["x"]),
                              self._px_series(res["y1"]), self._px_series(res["y2"]),
                              label=f"{res['y1']}–{res['y2']}", alpha=float(res["alpha"]))
            ax.set_xlabel(res["x"])
            beautify_axes(ax, title=f"Band {res['y1']}–{res['y2']} vs {res['x']}")
            self.tabs.currentWidget().draw()
            self._show_plot_view()
            self.notify("Fill-between band created")
        except Exception as e:
            self.error_box("Fill-between failed", f"Reason: {e}")

    # -------------------------------------------------------- secondary axis
    def plot_secondary_axis(self):
        cols = self._px_cols()
        if not cols or len(cols) < 2:
            if cols is not None:
                self.inform("Need 2 columns", "A secondary axis needs an X and a second Y column")
            return
        ax, fig, lines = self._active_graph_axes() if hasattr(self, "_active_graph_axes") \
            else (self.tabs.currentWidget().get_axes(), None, [])
        if ax is None or not lines:
            self.inform("No graph", "Plot a primary curve first, then add a secondary axis")
            return
        x_sel = self.selected_x_column()
        res = self.ask_form("Add Secondary Y Axis", [
            {"name": "x", "label": "X column", "kind": "choice", "options": cols,
             "default": x_sel if x_sel in cols else cols[0]},
            {"name": "y2", "label": "Right-axis Y column", "kind": "choice", "options": cols,
             "default": cols[-1]},
        ], description="Overlay a second Y column on a right-hand axis (current graph)")
        if res is None:
            return
        try:
            add_secondary_y(ax, self._px_series(res["x"]), self._px_series(res["y2"]),
                            label=res["y2"], ylabel=res["y2"])
            self.tabs.currentWidget().draw()
            self.notify(f"Added right-axis: {res['y2']}")
        except Exception as e:
            self.error_box("Secondary axis failed", f"Reason: {e}")
