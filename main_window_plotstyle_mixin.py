from __future__ import annotations

import logging

from core.plot_style import (
    apply_line_style,
    apply_style,
    read_line_style,
    read_style,
)

logger = logging.getLogger(__name__)


class MainWindowPlotStyleMixin:
    """OriginPro-style graph customization ("Plot Details").

    Reads the active graph's axes/figure/curves into a style dict, hands it to
    the tabbed dialog, and applies the edited result back. Live "Apply" redraws
    without closing. The style math lives in core/plot_style.py.
    """

    def bind_graph_dblclick(self, *_):
        """Bind double-click on the current graph canvas → Plot Details (Origin).

        Safe to call repeatedly (guards against re-binding the same canvas).
        """
        try:
            tab = self.tabs.currentWidget()
            canvas = getattr(tab, "canvas", None)
            if canvas is None or getattr(canvas, "_plotdetails_bound", False):
                return
            canvas.mpl_connect("button_press_event", self._on_canvas_click)
            canvas._plotdetails_bound = True
        except Exception:
            logger.debug("graph dblclick bind skipped", exc_info=True)

    def _on_canvas_click(self, event):
        if getattr(event, "dblclick", False):
            self.open_plot_details_dialog()

    def _active_graph_axes(self):
        """(ax, fig, lines) of the current graph tab, or (None, None, [])."""
        try:
            tab = self.tabs.currentWidget()
            if tab is None or not hasattr(tab, "get_axes"):
                return None, None, []
            ax = tab.get_axes()
            fig = tab.get_figure() if hasattr(tab, "get_figure") else ax.figure
            return ax, fig, list(ax.get_lines())
        except Exception:
            logger.debug("active graph axes lookup failed", exc_info=True)
            return None, None, []

    def open_plot_details_dialog(self):
        """Open the Plot Details dialog for the active graph."""
        from dialogs.plot_details_dialog import PlotDetailsDialog

        ax, fig, lines = self._active_graph_axes()
        if ax is None:
            self.inform("No graph", "Open or select a graph window first")
            return
        if not lines:
            self.inform("Empty graph", "Plot something first, then customize it")
            return

        style = read_style(ax, fig)
        line_styles = [read_line_style(ln) for ln in lines]
        dlg = PlotDetailsDialog(style, line_styles, parent=self)

        def _apply():
            self._apply_plot_details(ax, fig, lines, dlg)

        dlg.applied.connect(_apply)
        from PySide6.QtWidgets import QDialog
        if dlg.exec() == QDialog.Accepted:
            _apply()

    def _apply_plot_details(self, ax, fig, lines, dlg) -> None:
        try:
            apply_style(ax, dlg.get_style(), fig)
            for ln, d in zip(lines, dlg.get_line_styles()):
                apply_line_style(ln, d)
            # a legend may need rebuilding after labels/colors change
            style = dlg.get_style()
            if style.get("legend", {}).get("visible"):
                apply_style(ax, {"legend": style["legend"]})
            tab = self.tabs.currentWidget()
            if hasattr(tab, "draw"):
                tab.draw()
            else:
                fig.canvas.draw_idle()
            self.notify("Applied graph formatting")
        except Exception as e:
            self.error_box("Formatting failed", f"Reason: {e}")
