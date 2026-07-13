from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from core.plot_data import clamp_date_limits as _clamp_date_limits
from core.plot_mode import PlotMode
from processors import beautify_axes

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # shared MainWindow state this mixin relies on (set in MainWindow.__init__)
    plot_mode: object
    canvas: object
    tabs: object
    current_aggregated_df: object


class MainWindowPlotCoreMixin:
    """Core plotting engine: axes/canvas management, drawing, theme and style.

    Distinct from MainWindowPlotMixin (user-facing plot commands); this holds the
    primitives those commands build on.
    """

    @staticmethod
    def _axes_projection(ax) -> str:
        if hasattr(ax, "zaxis"):
            return "3d"
        return getattr(ax, "name", "rectilinear") or "rectilinear"

    @staticmethod
    def _add_projected_axes(fig, projection: str):
        return fig.add_subplot(
            111,
            projection=None if projection == "rectilinear" else projection,
        )

    def get_main_axes(
        self,
        prefer_3d: bool = False,
        projection: str | None = None,
    ):
        """Return a matplotlib Axes for plotting based on current PlotMode.
        - OVERLAY: reuse last axes when possible; create new if 2D/3D differs
        - REPLACE: clear figure and create fresh axes
        """
        try:
            fig = self.canvas.fig
        except Exception:
            try:
                tab = self.tabs.currentWidget()
                fig = tab.get_figure()
            except Exception:
                from matplotlib.figure import Figure as _Figure
                fig = _Figure()

        desired_projection = projection or ("3d" if prefer_3d else "rectilinear")
        mode = getattr(self, 'plot_mode', PlotMode.OVERLAY)
        if mode == PlotMode.REPLACE or not fig.axes:
            fig.clear()
            return self._add_projected_axes(fig, desired_projection)

        ax = fig.axes[-1]
        if self._axes_projection(ax) != desired_projection:
            return self._add_projected_axes(fig, desired_projection)
        return ax

    def apply_plot(
        self,
        drawer,
        prefer_3d: bool = False,
        projection: str | None = None,
    ):
        tab = None
        canvas = None
        initial_layer_ids = set()
        pre_artist_ids = set()
        try:
            if hasattr(self, '_update_canvas_reference') and hasattr(self, 'tabs'):
                self._update_canvas_reference()
            tab = self.tabs.currentWidget() if hasattr(self, 'tabs') else None
        except Exception:
            tab = None

        desired_projection = projection or ("3d" if prefer_3d else "rectilinear")
        mode = getattr(self, 'plot_mode', PlotMode.OVERLAY)

        if tab is not None and hasattr(tab, 'canvas'):
            canvas = tab.canvas
            self.canvas = canvas
            ax = canvas.ax
            if self._axes_projection(ax) != desired_projection:
                canvas.fig.clf()
                ax = self._add_projected_axes(canvas.fig, desired_projection)
                canvas.ax = ax
            try:
                import matplotlib as _mpl
                fig_fc = _mpl.rcParams.get('figure.facecolor', '#1e2126') or '#1e2126'
                ax_fc = _mpl.rcParams.get('axes.facecolor', '#1e2126') or '#1e2126'
                canvas.fig.patch.set_facecolor(fig_fc)
                ax.set_facecolor(ax_fc)
            except Exception:
                pass

            if mode == PlotMode.REPLACE:
                try:
                    ax.clear()
                except Exception:
                    pass
                _clamp_date_limits(ax)
                try:
                    tab.clear_layers()
                except Exception:
                    pass

            initial_layer_ids = set(getattr(tab, 'layers', {}).keys())
            pre_artist_ids = {id(artist) for artist in self._collect_plot_artists(ax)}
        else:
            ax = self.get_main_axes(
                prefer_3d=prefer_3d,
                projection=projection,
            )
            tab = None
            pre_artist_ids = {id(artist) for artist in self._collect_plot_artists(ax)}

        drawer(ax)

        try:
            if hasattr(ax, 'relim'):
                ax.relim()
            if hasattr(ax, 'autoscale_view'):
                ax.autoscale_view(True, True, True)
        except Exception:
            pass

        post_layer_ids = set(getattr(tab, 'layers', {}).keys()) if tab is not None else set()
        if tab is not None and post_layer_ids == initial_layer_ids:
            new_artists = [artist for artist in self._collect_plot_artists(ax) if id(artist) not in pre_artist_ids]
            if new_artists:
                used_labels = {info.get('label', '') for info in tab.layers.values() if info.get('label')}
                registered = False
                for artist in new_artists:
                    style = self._infer_artist_style(artist)
                    if style == 'layer':
                        continue
                    try:
                        label = artist.get_label()
                    except Exception:
                        label = ''
                    if not label or str(label).startswith('_'):
                        label = self._generate_auto_layer_label(tab, style, used_labels)
                    else:
                        used_labels.add(label)
                    layer_meta = {'source': 'analysis.apply_plot', 'style': style}
                    layer_id = tab.register_layer([artist], label, style, meta=layer_meta, kwargs={})
                    if layer_id:
                        registered = True
                if registered:
                    try:
                        tab._refresh_legend()
                    except Exception:
                        pass

        try:
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(loc='best')
        except Exception:
            pass
        try:
            ax.figure.canvas.draw_idle()
        except Exception:
            pass
        if tab is not None:
            try:
                tab.draw()
            except Exception:
                try:
                    tab.canvas.draw()
                except Exception:
                    pass

    def _collect_plot_artists(self, ax):
        """Return new plot artists (lines/collections) for layer registration."""
        artists = []
        try:
            artists.extend(getattr(ax, 'lines', []))
        except Exception:
            pass
        try:
            artists.extend(getattr(ax, 'collections', []))
        except Exception:
            pass
        unique = []
        seen = set()
        for artist in artists:
            if artist is None:
                continue
            art_id = id(artist)
            if art_id in seen:
                continue
            seen.add(art_id)
            unique.append(artist)
        return unique

    @staticmethod
    def _infer_artist_style(artist: object) -> str:
        if isinstance(artist, Line2D):
            return 'line'
        if isinstance(artist, PathCollection):
            return 'scatter'
        return 'layer'

    def _generate_auto_layer_label(self, tab, style: str, used_labels: set) -> str:
        base = 'Series' if style == 'line' else (style.capitalize() if style else 'Series')
        idx = 1
        candidate = f"{base} {idx}"
        while candidate in used_labels:
            idx += 1
            candidate = f"{base} {idx}"
        used_labels.add(candidate)
        return candidate

    def apply_current_mpl_theme_to_canvas(self):
        try:
            tab = self.tabs.currentWidget()
            if not tab:
                return
            from styles.theme import apply_matplotlib_to_figure

            apply_matplotlib_to_figure(tab.get_figure())
        except Exception:
            logger.debug("Could not apply Matplotlib defaults to current canvas", exc_info=True)

        # Add keyboard shortcuts
        self.actOpen.setShortcut("Ctrl+O")
        self.actSettings.setShortcut("Ctrl+,")
        # (Derived Column action + คีย์ลัด ย้ายไปอยู่ใน _init_menu แล้ว — เมนู Data)

        # Load saved plot style preference
        self._load_plot_style_config()

        # Load and apply settings from config
        self._load_and_apply_settings()
        QTimer.singleShot(300, self._prompt_restore_session)

    def refresh_all_canvases(self):
        """Refresh all matplotlib canvases to apply new settings"""
        try:
            # Refresh main canvas
            if hasattr(self, 'canvas') and self.canvas:
                self.canvas.draw()

            # Refresh any other canvases that might exist
            from styles.theme import refresh_matplotlib_canvases
            refresh_matplotlib_canvases()

            logger.info("All canvases refreshed")
        except Exception as e:
            logger.error(f"Error refreshing canvases: {e}")

    def change_plot_style(self, style, save_config=True):
        """Change plot style and optionally save preference"""
        try:
            import matplotlib

            if style == "dark":
                # Try to load dark style file first
                style_path = os.path.join(os.path.dirname(__file__), "styles", "mpl_style_dark_pro.mplstyle")
                if os.path.exists(style_path):
                    plt.style.use(style_path)
                    logger.info("Dark style file loaded successfully")
                else:
                    # Apply fallback dark theme using rcParams
                    matplotlib.rcParams["figure.facecolor"] = "#1e2126"
                    matplotlib.rcParams["axes.facecolor"] = "#1e2126"
                    matplotlib.rcParams["axes.edgecolor"] = "#3a3f44"
                    matplotlib.rcParams["axes.labelcolor"] = "#e6e6e6"
                    matplotlib.rcParams["xtick.color"] = "#cfd3d6"
                    matplotlib.rcParams["ytick.color"] = "#cfd3d6"
                    matplotlib.rcParams["text.color"] = "#e6e6e6"
                    matplotlib.rcParams["grid.color"] = "#3a3f44"
                    matplotlib.rcParams["grid.alpha"] = 0.3
                    logger.info("Fallback dark theme applied")

                # Update menu check state
                if hasattr(self, 'actDarkStyle'):
                    self.actDarkStyle.setChecked(True)
                    self.actDefaultStyle.setChecked(False)

            elif style == "default":
                plt.style.use('default')
                # Reset to default colors
                matplotlib.rcParams["figure.facecolor"] = "white"
                matplotlib.rcParams["axes.facecolor"] = "white"
                matplotlib.rcParams["axes.edgecolor"] = "black"
                matplotlib.rcParams["axes.labelcolor"] = "black"
                matplotlib.rcParams["xtick.color"] = "black"
                matplotlib.rcParams["ytick.color"] = "black"
                matplotlib.rcParams["text.color"] = "black"
                matplotlib.rcParams["grid.color"] = "black"
                matplotlib.rcParams["grid.alpha"] = 0.3
                logger.info("Default theme applied")

                # Update menu check state
                if hasattr(self, 'actDarkStyle'):
                    self.actDarkStyle.setChecked(False)
                    self.actDefaultStyle.setChecked(True)

            # Force canvas redraw to apply new style
            if hasattr(self, 'canvas') and self.canvas:
                try:
                    # Clear and redraw canvas to apply new style
                    self.canvas.clear()
                    self.canvas.draw()
                    logger.info("Canvas redrawn with new style")
                except Exception as e:
                    logger.error(f"Canvas redraw error: {e}")

            # Save preference + status message only for user-initiated changes
            # (startup restore passes save_config=False and must stay silent,
            # or it stomps the "ready" message in the status bar)
            if save_config:
                self._save_plot_style_config(style)
                self.statusBar().showMessage(f"Plot style changed to: {style.title()}")

        except Exception as e:
            QMessageBox.critical(self, "Style Change Failed", f"Failed to change plot style: {str(e)}")
            logger.error(f"Style change error: {e}")

    # [Equation Plotter]
    def _ensure_plot_axes_dimension(self, ax, mode: str):
        """Ensure the active axes match the requested dimensionality."""
        if ax is None:
            return None
        canvas = getattr(self, "canvas", None)
        fig = ax.figure
        facecolor = fig.get_facecolor()
        try:
            axes_facecolor = ax.get_facecolor()
        except Exception:
            axes_facecolor = None

        target = "3d_surface" if mode == "3d_surface" else "2d"

        if target == "3d_surface" and not hasattr(ax, "zaxis"):
            fig.clf()
            new_ax = fig.add_subplot(111, projection="3d")
            fig.patch.set_facecolor(facecolor)
            if axes_facecolor is not None:
                try:
                    new_ax.set_facecolor(axes_facecolor)
                except Exception:
                    pass
            if canvas is not None:
                canvas.ax = new_ax
            for attr in ("axes", "ax"):
                if hasattr(self, attr):
                    setattr(self, attr, new_ax)
            return new_ax

        if target == "2d" and hasattr(ax, "zaxis"):
            fig.clf()
            new_ax = fig.add_subplot(111)
            fig.patch.set_facecolor(facecolor)
            if axes_facecolor is not None:
                try:
                    new_ax.set_facecolor(axes_facecolor)
                except Exception:
                    pass
            if canvas is not None:
                canvas.ax = new_ax
            for attr in ("axes", "ax"):
                if hasattr(self, attr):
                    setattr(self, attr, new_ax)
            return new_ax

        return ax

    def _update_3d_controls_state(self, ax=None, tab=None) -> None:
        if not hasattr(self, "view3DDock"):
            return
        try:
            current_ax = ax
            current_tab = tab
            if current_ax is None:
                tab_id = None
                try:
                    tab_id = self.tabs.get_current_tab_id() if hasattr(self.tabs, "get_current_tab_id") else None
                except Exception:
                    tab_id = None
                if tab_id and hasattr(self.tabs, "tabs"):
                    current_tab = self.tabs.tabs.get(tab_id)
                if current_tab is not None and hasattr(current_tab, "get_axes"):
                    try:
                        current_ax = current_tab.get_axes()
                    except Exception:
                        current_ax = None
            if current_ax is not None and hasattr(current_ax, "zaxis"):
                canvas = getattr(current_tab, "canvas", None) if current_tab is not None else getattr(self, "canvas", None)
                toolbar = getattr(current_tab, "toolbar", None) if current_tab is not None else None
                self.view3DDock.attach_axes(current_ax, canvas=canvas, toolbar=toolbar)
                try:
                    should_show = self.view3DDock.toggleViewAction().isChecked()
                except Exception:
                    should_show = self.view3DDock.isVisible()
                if not getattr(self, "_3d_dock_has_shown", False) or should_show:
                    self.view3DDock.show()
                    self._3d_dock_has_shown = True
            else:
                self.view3DDock.detach_axes()
                self.view3DDock.hide()
        except Exception:
            logger.debug("Failed to update 3D dock state", exc_info=True)

    def refresh_plot(self, keep_limits: bool = True) -> None:
        """
        อะแดปเตอร์เรียกวาดกราฟใหม่
        - keep_limits: ถ้า True พยายามรักษา xlim/ylim เดิมไว้
        """
        # เดาว่าคุณมีฟังก์ชันวาดอยู่แล้ว เช่น update_plot()/redraw_plot()
        # ปรับชื่อให้ตรงกับของคุณ
        target = None
        for name in ("update_plot", "redraw_plot", "plot_current", "plot_data"):
            if hasattr(self, name):
                target = getattr(self, name)
                break

        if target is None:
            # fallback แบบเบา ๆ: เคลียร์แกนแล้ววาดใหม่จากข้อมูลล่าสุดถ้ามี
            fig = self.canvas.figure
            ax = fig.axes[0] if fig.axes else fig.add_subplot(111)
            xlim = ax.get_xlim() if keep_limits else None
            ylim = ax.get_ylim() if keep_limits else None
            try:
                mode = getattr(self, 'plot_mode', PlotMode.OVERLAY)
            except Exception:
                mode = PlotMode.OVERLAY
            if mode == PlotMode.REPLACE:
                ax.clear()
            # ถ้ามีเมธอดช่วยดึงข้อมูลปัจจุบัน ให้เรียกที่นี่แทน
            if hasattr(self, "_plot_current"):
                self._plot_current(ax)  # ปรับชื่อให้ตรงโปรเจกต์คุณ
            fig.canvas.draw_idle()
            if keep_limits and xlim and ylim:
                ax.set_xlim(*xlim); ax.set_ylim(*ylim)
            return

        # ถ้ามีเมธอดหลักอยู่แล้วก็เรียกเลย
        target()

    # UI-REFINE: wrapper สำหรับ Aggregate ไม่แตะ logic core
    def _aggregate_and_plot(self, df: pd.DataFrame, id_col: str, value_cols: list[str], agg: str, stacked: bool = False):
        import pandas as pd
        if not id_col or not value_cols:
            return
        if agg == "sum":
            out = df.groupby(id_col)[value_cols].sum().reset_index()
        elif agg == "mean":
            out = df.groupby(id_col)[value_cols].mean().reset_index()
        elif agg == "count":
            out = df.groupby(id_col)[value_cols].count().reset_index()
        elif agg == "max":
            out = df.groupby(id_col)[value_cols].max().reset_index()
        else:
            out = df.groupby(id_col)[value_cols].min().reset_index()

        # Plot: if multiple columns selected
        try:
            if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE:
                self.canvas.clear()
        except Exception:
            pass
        x = out[id_col]
        if len(value_cols) == 1 or not stacked:
            # Use first column for bar chart
            y = out[value_cols[0]]
            self.plot_bar(x=x, y=y, xlabel=id_col, ylabel=f"{agg}({value_cols[0]})", title=f"{agg} by {id_col}")
        else:
            import numpy as _np
            ind = _np.arange(len(x))
            bottom = _np.zeros(len(x))
            for col in value_cols:
                vals = out[col].values
                self.canvas.ax.bar(ind, vals, bottom=bottom, label=col)
                bottom = bottom + vals
            self.canvas.ax.set_xticks(ind)
            self.canvas.ax.set_xticklabels(list(map(str, x)), rotation=45, ha="right")
            self.canvas.ax.set_xlabel(id_col)
            self.canvas.ax.set_ylabel(f"{agg}(values)")
            # Use English title to avoid font issues
            self.canvas.ax.set_title(f"{agg} by {id_col} (stacked)")
            beautify_axes(self.canvas.ax, title=f"{agg} by {id_col} (stacked)")

        # Store result for Export
        self.current_aggregated_df = out
        self.statusBar().showMessage("Aggregate successful • Use Export tab to save results")
