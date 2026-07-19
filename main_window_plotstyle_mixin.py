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
        """Bind graph double-click → Graph Data (Ctrl+double-click → Plot Details).

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
            # Origin behaviour: double-click ANYWHERE on the graph opens Plot
            # Details — no need to aim at a thin line. Landing near a curve
            # (generous 12px radius) preselects it in the Lines tab.
            # Ctrl/Shift+double-click opens the Graph Data inspector instead.
            key = str(getattr(event, "key", "") or "").casefold()
            if "control" in key or "shift" in key:
                opener = getattr(self, "open_graph_data_panel", None)
                if callable(opener):
                    opener()
                    return
            self.open_plot_details_dialog(
                preselect_line=self._line_index_at_event(event)
            )

    _PICK_RADIUS_PX = 12.0  # generous hit area — thin lines are hard targets

    def _line_index_at_event(self, event):
        """Index (among the user's curves) of the line under the cursor, or None."""
        try:
            from core.plot_style import list_line_artists

            ax, _fig, _lines = self._active_graph_axes()
            if ax is None:
                return None
            for index, line in enumerate(list_line_artists(ax)):
                old_radius = line.get_pickradius()
                try:
                    line.set_pickradius(self._PICK_RADIUS_PX)
                    hit, _detail = line.contains(event)
                finally:
                    line.set_pickradius(old_radius)
                if hit:
                    return index
        except Exception:
            logger.debug("pick-to-edit hit test failed", exc_info=True)
        return None

    def _active_graph_axes(self):
        """(ax, fig, lines) of the current graph tab, or (None, None, [])."""
        try:
            from core.plot_style import list_line_artists

            tab = self.tabs.currentWidget()
            if tab is None or not hasattr(tab, "get_axes"):
                return None, None, []
            ax = tab.get_axes()
            fig = tab.get_figure() if hasattr(tab, "get_figure") else ax.figure
            # only the user's curves — never our decoration artists
            # (reference lines, error-bar caps) as editable "Lines"
            return ax, fig, list_line_artists(ax)
        except Exception:
            logger.debug("active graph axes lookup failed", exc_info=True)
            return None, None, []

    def open_plot_details_dialog(self, preselect_line=None):
        """Open the Plot Details dialog for the active graph."""
        from dialogs.plot_details_dialog import PlotDetailsDialog
        from core import plot_templates

        target_tab = self.tabs.currentWidget()
        ax, fig, lines = self._active_graph_axes()
        if ax is None:
            self.inform("No graph", "Open or select a graph window first")
            return
        if not lines:
            self.inform("Empty graph", "Plot something first, then customize it")
            return

        style = read_style(ax, fig)
        line_styles = [read_line_style(ln) for ln in lines]
        dlg = PlotDetailsDialog(
            style, line_styles, parent=self,
            template_names=plot_templates.list_templates())

        def _apply():
            self._apply_plot_details(ax, fig, lines, dlg, target_tab=target_tab)

        def _save_template(name):
            self._save_plot_template_from_dialog(dlg, name)

        def _load_template(name):
            self._load_plot_template_into_dialog(
                dlg, name, ax=ax, fig=fig, lines=lines, target_tab=target_tab
            )

        def _delete_template(name):
            self._delete_plot_template_from_dialog(dlg, name)

        dlg.applied.connect(_apply)
        dlg.save_template_requested.connect(_save_template)
        dlg.load_template_requested.connect(_load_template)
        dlg.delete_template_requested.connect(_delete_template)
        if preselect_line is not None:
            dlg.focus_line(int(preselect_line))

        # Non-modal + placed beside the graph so the live preview stays visible.
        # A modal window centred over the graph hid the very thing being
        # formatted, so the user could not see their changes take effect.
        from PySide6.QtWidgets import QDialog

        prev = getattr(self, "_plot_details_dlg", None)
        if prev is not None:
            try:
                prev.close()
            except Exception:
                logger.debug("closing previous plot details failed", exc_info=True)
        self._plot_details_dlg = dlg

        def _on_finished(result):
            try:
                if result == QDialog.Accepted:
                    _apply()
                else:
                    # Live preview committed edits as the user typed; Cancel must
                    # put the graph back exactly as it was when the dialog opened.
                    self._restore_plot_details(
                        ax, fig, lines, style, line_styles, target_tab=target_tab
                    )
            finally:
                if getattr(self, "_plot_details_dlg", None) is dlg:
                    self._plot_details_dlg = None

        dlg.finished.connect(_on_finished)
        dlg.setModal(False)
        self._position_plot_details_dialog(dlg, target_tab)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def _plot_details_target_rect(self, target_tab):
        """Global-screen rectangle of the graph being formatted, if resolvable."""
        from PySide6.QtCore import QRect
        try:
            canvas = getattr(target_tab, "canvas", None)
            if canvas is not None and canvas.isVisible():
                tl = canvas.mapToGlobal(canvas.rect().topLeft())
                br = canvas.mapToGlobal(canvas.rect().bottomRight())
                return QRect(tl, br)
        except Exception:
            logger.debug("plot details target rect failed", exc_info=True)
        return None

    def _position_plot_details_dialog(self, dlg, target_tab) -> None:
        """Place Plot Details next to the graph, never on top of it."""
        from PySide6.QtWidgets import QApplication
        try:
            dlg.adjustSize()
            dw, dh = dlg.width(), dlg.height()
            screen = self.screen() if hasattr(self, "screen") else None
            screen = screen or QApplication.primaryScreen()
            avail = screen.availableGeometry()
            graph = self._plot_details_target_rect(target_tab)
            margin = 8
            x = y = None
            if graph is not None:
                if graph.right() + margin + dw <= avail.right():          # right of graph
                    x = graph.right() + margin
                elif avail.left() + dw + margin <= graph.left():          # left of graph
                    x = graph.left() - margin - dw
                if x is not None:
                    y = min(max(graph.top(), avail.top()), avail.bottom() - dh)
            if x is None:
                # No clear side — dock to the right screen edge (over the tool
                # docks, which matter far less than the graph itself).
                x = avail.right() - dw - margin
                y = avail.top() + margin
            x = max(avail.left(), min(int(x), avail.right() - dw))
            y = max(avail.top(), min(int(y), avail.bottom() - dh))
            dlg.move(x, y)
        except Exception:
            logger.debug("plot details positioning failed", exc_info=True)

    def _restore_plot_details(self, ax, fig, lines, style, line_styles, *,
                              target_tab=None) -> None:
        """Reapply the pre-edit snapshot to undo any live-preview changes."""
        try:
            apply_style(ax, style, fig, live=True)
            for ln, d in zip(lines, line_styles):
                apply_line_style(ln, d)
            self._relayout_live_figure(fig)
            tab = target_tab or self._graph_tab_for_figure(fig)
            if hasattr(tab, "draw"):
                tab.draw()
            elif getattr(fig, "canvas", None) is not None:
                fig.canvas.draw_idle()
        except Exception:
            logger.debug("plot details revert failed", exc_info=True)

    def _refresh_plot_template_names(self, dlg) -> None:
        from core import plot_templates

        try:
            dlg.set_template_names(plot_templates.list_templates())
        except Exception:
            logger.debug("template list refresh skipped", exc_info=True)

    def _save_plot_template_from_dialog(self, dlg, name: str) -> None:
        from core import plot_templates

        try:
            plot_templates.save_template(name, dlg.get_style())
            self._refresh_plot_template_names(dlg)
            try:
                dlg.cb_template.setCurrentText(name)
            except Exception:
                logger.debug("template combobox sync skipped", exc_info=True)
            self.notify(f"Saved template: {name}")
        except Exception as e:
            self.error_box("Save template failed", f"Reason: {e}")

    def _load_plot_template_into_dialog(self, dlg, name: str, *, ax, fig, lines, target_tab=None) -> None:
        from core import plot_templates

        try:
            tpl = plot_templates.load_template(name)
            dlg._loading = True
            try:
                dlg.load_style_into_controls(tpl)
            finally:
                dlg._loading = False
            self._apply_plot_details(ax, fig, lines, dlg, target_tab=target_tab)
            self.notify(f"Applied template: {name}")
        except Exception as e:
            self.error_box("Load template failed", f"Reason: {e}")

    def _delete_plot_template_from_dialog(self, dlg, name: str) -> None:
        from core import plot_templates

        try:
            removed = plot_templates.delete_template(name)
            if not removed:
                self.inform("Template not found", f"Template '{name}' no longer exists.")
                self._refresh_plot_template_names(dlg)
                return
            self._refresh_plot_template_names(dlg)
            self.notify(f"Deleted template: {name}")
        except Exception as e:
            self.error_box("Delete template failed", f"Reason: {e}")

    def _draw_active_graph(self, fig=None, tab=None) -> None:
        if tab is None:
            tab = self._graph_tab_for_figure(fig)
        if hasattr(tab, "draw"):
            tab.draw()
        elif fig is not None:
            fig.canvas.draw_idle()

    def _graph_tab_for_figure(self, fig):
        try:
            for tab in getattr(self.tabs, "tabs", {}).values():
                try:
                    if tab.get_figure() is fig:
                        return tab
                except Exception:
                    continue
        except Exception:
            pass
        try:
            return self.tabs.currentWidget()
        except Exception:
            return None

    def _apply_plot_details(self, ax, fig, lines, dlg, *, target_tab=None) -> None:
        from core.plot_style import diff_style

        try:
            style = dlg.get_style()
            line_styles = dlg.get_line_styles()
            # Apply ONLY what changed since the dialog opened / last Apply —
            # untouched controls must never restyle the graph (identity Apply
            # is a visual no-op; a stray seed can't blank the plot).
            baseline = getattr(dlg, "_seed_style", None)
            effective = diff_style(baseline, style) if baseline else style
            apply_style(ax, effective, fig, live=True)   # on-screen: no size/dpi
            base_lines = getattr(dlg, "_seed_line_styles", None)
            lines_changed = False
            for i, (ln, d) in enumerate(zip(lines, line_styles)):
                if (base_lines is not None and i < len(base_lines)
                        and d == base_lines[i]):
                    continue
                apply_line_style(ln, d)
                lines_changed = True
            # Scientific palette recolour: a one-shot action, applied only when
            # the user actually changed it since the last Apply (so identity
            # Apply stays a no-op and respects the diff-apply contract).
            palette = style.get("palette") or {}
            base_palette = (baseline or {}).get("palette") or {}
            pal_name = palette.get("name")
            keep = getattr(dlg, "_palette_keep", "— keep colors —")
            if pal_name and pal_name != keep and palette != base_palette:
                from core.plot_style import apply_palette
                apply_palette(ax, pal_name, line_width=palette.get("line_width"))
                lines_changed = True
            # a legend may need rebuilding after labels/colors change
            if ((("legend" in effective) or lines_changed)
                    and style.get("legend", {}).get("visible")):
                apply_style(ax, {"legend": style["legend"]})
            # next Apply diffs against what is now on screen
            try:
                dlg._seed_style = style
                dlg._seed_line_styles = line_styles
            except Exception:
                logger.debug("re-baselining style failed", exc_info=True)
            # remember the chosen print size/dpi for export (not applied live)
            tab = target_tab or self._graph_tab_for_figure(fig)
            fig_style = style.get("figure", {})
            if tab is not None and (fig_style.get("width_in") or fig_style.get("dpi")):
                tab._print_figure = {
                    "width_in": fig_style.get("width_in"),
                    "height_in": fig_style.get("height_in"),
                    "dpi": fig_style.get("dpi"),
                }
            self._relayout_live_figure(fig)  # re-expand plot area; never resize canvas
            if hasattr(tab, "draw"):
                tab.draw()
            else:
                fig.canvas.draw_idle()
            self.notify("Applied graph formatting")
        except Exception as e:
            self.error_box("Formatting failed", f"Reason: {e}")

    def _relayout_live_figure(self, fig) -> None:
        """Re-expand the plot area to fill the canvas after a style change.

        Deliberately never sets the figure size or DPI. The embedded Qt canvas
        owns those, and forcing them from Qt *logical* pixels renders the figure
        smaller than the widget on any HiDPI display (device pixel ratio > 1,
        i.e. Windows at 125%/150%): that is the "graph shrinks whenever I
        decorate it" bug. ``tight_layout`` maximizes the axes within whatever
        size the canvas currently is, so the plot area stays full every apply.
        """
        if fig is None:
            return
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fig.tight_layout()
            return
        except Exception:
            logger.debug("tight_layout relayout skipped", exc_info=True)
        # fallback: sane fixed margins for a simple single-axes figure
        try:
            axes = [ax for ax in getattr(fig, "axes", []) if ax.get_visible()]
            if len(axes) == 1:
                fig.subplots_adjust(left=0.12, right=0.96, bottom=0.14, top=0.92)
        except Exception:
            logger.debug("axes layout restore skipped", exc_info=True)
