from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from core.render_optimization import apply_line_lod, canvas_pixel_width
from core.plot_extras import (
    add_secondary_y,
    draw_broken_axis,
    draw_error_bars,
    draw_fill_between,
)
from processors import beautify_axes

logger = logging.getLogger(__name__)


class MainWindowPlotExtraMixin:
    """Extra plot types (ROADMAP C): error bars, fill-between, extra axes.

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
            x_values = self._px_series(res["x"])
            y_values = self._px_series(res["y2"])
            ax2, line = add_secondary_y(
                ax, x_values, y_values, label=res["y2"], ylabel=res["y2"]
            )
            line._sciplotter_x_values = x_values.tolist()
            line._sciplotter_y_values = y_values.tolist()
            render_info = apply_line_lod(
                ax2, line, pixel_width=canvas_pixel_width(ax2)
            )
            try:
                tab = self.tabs.currentWidget()
                tab.register_layer(
                    [line],
                    str(res["y2"]),
                    "line",
                    meta={
                        "source": "secondary_y",
                        "style": "line",
                        "render": render_info,
                    },
                    kwargs={},
                )
            except Exception:
                logger.debug("secondary-axis layer registration skipped", exc_info=True)
            self.tabs.currentWidget().draw()
            self.notify(f"Added right-axis: {res['y2']}")
        except Exception as e:
            self.error_box("Secondary axis failed", f"Reason: {e}")

    # ------------------------------------------------------------- broken axis
    def plot_broken_axis(self):
        try:
            tab = self.tabs.currentWidget()
            ax = tab.get_axes()
        except Exception:
            self.inform("No graph", "Plot a line graph first, then add a broken axis")
            return
        if ax is None or not getattr(ax, "lines", None):
            self.inform("No line plot", "Broken axis currently supports line plots on the active graph")
            return
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        default_lower = float(ylim[0] + (ylim[1] - ylim[0]) * 0.35)
        default_upper = float(ylim[0] + (ylim[1] - ylim[0]) * 0.65)
        res = self.ask_form("Broken Axis", [
            {"name": "axis", "label": "Axis", "kind": "choice",
             "options": ["Y", "X"], "default": "Y"},
            {"name": "lower", "label": "Break lower bound", "kind": "float",
             "default": default_lower,
             "decimals": 6},
            {"name": "upper", "label": "Break upper bound", "kind": "float",
             "default": default_upper,
             "decimals": 6},
        ], description="Split the active line graph and hide the selected range")
        if res is None:
            return
        try:
            axis = str(res["axis"]).lower()[0]
            lower = float(res["lower"])
            upper = float(res["upper"])
            if axis == "x" and lower == default_lower and upper == default_upper:
                lower = float(xlim[0] + (xlim[1] - xlim[0]) * 0.35)
                upper = float(xlim[0] + (xlim[1] - xlim[0]) * 0.65)
            axes = draw_broken_axis(ax, axis, lower, upper)
            if axes:
                tab.canvas.ax = axes[0]
            try:
                tab.clear_layers()
            except Exception:
                logger.debug("broken-axis layer clear skipped", exc_info=True)
            new_lines = [
                line
                for target in axes
                for line in target.get_lines()
                if hasattr(line, "_sciplotter_x_values")
            ]
            render_infos = []
            for line in new_lines:
                try:
                    render_infos.append(
                        apply_line_lod(
                            line.axes,
                            line,
                            pixel_width=canvas_pixel_width(line.axes),
                        )
                    )
                except Exception:
                    logger.debug("broken-axis LOD skipped", exc_info=True)
            if new_lines:
                tab.register_layer(
                    new_lines,
                    "Broken axis lines",
                    "line",
                    meta={
                        "source": "broken_axis",
                        "style": "line",
                        "render": render_infos[0] if render_infos else {},
                    },
                    kwargs={},
                )
            tab.draw()
            self.notify(f"Broken {axis.upper()} axis applied")
        except Exception as e:
            self.error_box("Broken axis failed", f"Reason: {e}")
