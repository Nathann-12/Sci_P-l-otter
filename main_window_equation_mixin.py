from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QMessageBox

from core.plot_data import clamp_date_limits as _clamp_date_limits
from dialogs_equation import EquationPlotDialog
from eqplot import plot_equations_on_axes
from eqplot3d import plot_surfaces_on_axes

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # shared MainWindow state this mixin relies on (set in MainWindow.__init__)
    canvas: object
    tabs: object


class MainWindowEquationMixin:
    """Plot-from-equation handler extracted from MainWindow."""

    def on_plot_from_equation(self):
        dlg = EquationPlotDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        expressions = vals["expressions"]
        if not expressions:
            self._show_status("กรุณาพิมพ์สมการอย่างน้อย 1 บรรทัด", error=True)
            return
        mode = vals.get("mode", "2d")
        try:
            tab = None
            current_tab_id = None
            try:
                if hasattr(self, "tabs") and hasattr(self.tabs, "get_current_tab_id"):
                    current_tab_id = self.tabs.get_current_tab_id()
            except Exception:
                current_tab_id = None
            if current_tab_id and hasattr(self.tabs, "tabs"):
                tab = self.tabs.tabs.get(current_tab_id)
            overlay_flag = bool(vals.get("overlay", True))
            tab_cleared = False
            ax = None
            if tab is not None:
                try:
                    if hasattr(tab, "canvas"):
                        self.canvas = tab.canvas
                    if not overlay_flag:
                        tab.clear()
                        tab_cleared = True
                    ax = tab.get_axes()
                except Exception:
                    ax = None
            if ax is None:
                ax = getattr(self, "axes", None)
            if ax is None:
                ax = getattr(self, "ax", None)
            if ax is None:
                canvas = getattr(self, "canvas", None)
                if canvas is not None:
                    ax = getattr(canvas, "axes", None)
                    if ax is None:
                        ax = getattr(canvas, "ax", None)
                    if ax is None and hasattr(canvas, "fig"):
                        fig_axes = getattr(canvas.fig, "axes", []) or []
                        if fig_axes:
                            ax = fig_axes[0]
            if ax is None:
                self._show_status("ไม่พบแกน Matplotlib", error=True)
                return
            ax = self._ensure_plot_axes_dimension(ax, mode)
            if ax is None:
                self._show_status("ไม่พบแกน Matplotlib", error=True)
                return

            eq_overlay = overlay_flag
            if tab_cleared:
                eq_overlay = True

            layer_infos = []
            if mode == "3d_surface":
                layer_infos = plot_surfaces_on_axes(
                    ax=ax,
                    expressions=expressions,
                    x_min=vals["x_min"],
                    x_max=vals["x_max"],
                    n_points=vals["n_points"],
                    y_min=vals.get("y_min", -10.0),
                    y_max=vals.get("y_max", 10.0),
                    n_y_points=vals.get("n_y_points", 200),
                    params_str=vals["params"],
                    wireframe=vals["wireframe"],
                    overlay=eq_overlay,
                )
                self._show_status("วาดพื้นผิว 3D จากสมการเรียบร้อย")
            else:
                layer_infos = plot_equations_on_axes(
                    ax=ax,
                    expressions=expressions,
                    x_min=vals["x_min"],
                    x_max=vals["x_max"],
                    n_points=vals["n_points"],
                    params_str=vals["params"],
                    y_scale=vals["y_scale"],
                    overlay=eq_overlay,
                )
                self._show_status("วาดกราฟจากสมการเรียบร้อย")

            if tab is not None:
                for info in layer_infos:
                    artists = info.get('artists') or []
                    if not artists:
                        continue
                    label = info.get('label') or 'Equation'
                    style = info.get('style', 'line')
                    style_kwargs = info.get('style_kwargs', {})
                    meta = self._build_layer_meta(style, label, style_kwargs, source='plot_equation')
                    tab.register_layer(artists, label, style, meta=meta, kwargs=style_kwargs)
                try:
                    tab._refresh_legend()
                except Exception:
                    pass
                _clamp_date_limits(ax)
                try:
                    tab.draw()
                except Exception:
                    pass
                _clamp_date_limits(ax)
                try:
                    self._mount_layer_manager()
                except Exception:
                    pass

            self._update_3d_controls_state(ax, tab)
        except ValueError as exc:
            self._warn_equation_failure(str(exc))
        except Exception as exc:
            self._show_status("เกิดข้อผิดพลาด: {}".format(exc), error=True)

    # [Equation Plotter]
    def _warn_equation_failure(self, details: str) -> None:
        clean = (details or "").strip()
        if not clean:
            clean = "unknown error"
        message = "ไม่สามารถพล็อตสมการได้:\n{}".format(clean)
        self._show_status(message, error=True)
        try:
            QMessageBox.warning(self, "Plot from Equation", message)
        except Exception:
            logger.warning("Failed to show equation warning dialog: %s", message, exc_info=True)
            print(message)
