from __future__ import annotations

import logging

from matplotlib.widgets import Cursor, RectangleSelector


class MainWindowViewMixin:
    """Reusable view and canvas interactions extracted from MainWindow."""

    def _get_current_tab(self):
        current_tab_id = self.tabs.get_current_tab_id()
        if current_tab_id and current_tab_id in self.tabs.tabs:
            return self.tabs.tabs[current_tab_id]
        return None

    def _active_canvas(self):
        """Return the selected/last-selected graph canvas and sync self.canvas."""
        tab = self._get_current_tab()
        if tab is not None and getattr(tab, "canvas", None) is not None:
            self.canvas = tab.canvas
            return tab.canvas
        return getattr(self, "canvas", None)

    def clear_plot(self):
        tab = self._get_current_tab()
        if tab is None:
            return

        tab.clear()
        try:
            ax = tab.get_axes()
            ax.cla()
            tab.draw()
        except Exception:
            pass
        try:
            self._mount_layer_manager()
        except Exception:
            pass
        self.statusBar().showMessage("Graph cleared.")

    def _reset_view(self):
        """Reset the current graph to show all data (Rescale to Show All).

        Must actively autoscale: ``set_xlim(auto=True)`` only flips the
        autoscale flag, and a plain ``draw()`` does not recompute the view, so
        the graph stayed stuck at the zoomed limits (or off-screen). Autoscaling
        from the axes' dataLim always brings every artist back into view.
        """
        tab = self._get_current_tab()
        if tab is None:
            return

        ax = tab.get_axes()
        try:
            ax.autoscale(enable=True, axis="both", tight=False)
            ax.autoscale_view()
        except Exception:
            ax.set_xlim(auto=True)
            ax.set_ylim(auto=True)
        tab.draw()

    def _update_canvas_reference(self, *_):
        """Update canvas reference to point to the current tab's canvas."""
        tab = self._get_current_tab()
        if tab is not None and getattr(tab, "canvas", None) is not None:
            self.canvas = tab.canvas
        elif self.tabs.count() > 0:
            first_tab_widget = self.tabs.widget(0)
            for candidate in self.tabs.tabs.values():
                if candidate == first_tab_widget:
                    self.canvas = candidate.canvas
                    break

        self._update_3d_controls_state()

    def _add_new_tab(self):
        """Add a new graph tab."""
        self.tabs.add_tab()
        self.statusBar().showMessage("New graph tab added.")

    def toggle_crosshair(self, checked: bool):
        canvas = self._active_canvas()
        if canvas is None:
            return
        if self._cursor is not None:
            self._cursor = None
        if self._cid_motion is not None:
            try:
                old_canvas = getattr(self, "_cid_motion_canvas", None) or canvas
                old_canvas.mpl_disconnect(self._cid_motion)
            except Exception:
                pass
            self._cid_motion = None
            self._cid_motion_canvas = None

        if not checked:
            self.statusBar().showMessage("Crosshair disabled.")
            canvas.draw()
            return

        self._cursor = Cursor(canvas.ax, useblit=True, horizOn=True, vertOn=True)

        def _on_move(event):
            if event.inaxes != canvas.ax:
                return
            x, y = event.xdata, event.ydata
            try:
                if x is None or y is None:
                    return
                self._sb_cursor.setText(f"x={x:.3g}, y={y:.3g}")
            except Exception:
                pass

        self._cid_motion = canvas.mpl_connect("motion_notify_event", _on_move)
        self._cid_motion_canvas = canvas
        self.statusBar().showMessage("Crosshair enabled.")
        canvas.draw()

    def toggle_inspector(self, checked: bool):
        try:
            self._panel_right.setVisible(bool(checked))
        except Exception:
            pass
        # Collapse the whole inspector column in the shell splitter too —
        # hiding only the inner panel leaves a dead strip on the right.
        try:
            shell = getattr(self, "shell", None)
            if shell is not None and hasattr(shell, "set_inspector_visible"):
                shell.set_inspector_visible(bool(checked))
        except Exception:
            logging.getLogger(__name__).debug("shell inspector toggle skipped", exc_info=True)

    def toggle_error_panel(self, checked: bool):
        """Open or close the error panel."""
        try:
            if checked:
                self.error_panel.setFloating(True)
                self.error_panel.show()
                self.error_panel.raise_()
                self.error_panel.activateWindow()
            else:
                self.error_panel.hide()
        except Exception as exc:
            logging.getLogger(__name__).error(f"Error toggling error panel: {exc}")

    def start_box_zoom(self):
        canvas = self._active_canvas()
        if canvas is None:
            return
        if self._rs is not None:
            try:
                self._rs.set_active(False)
            except Exception:
                pass
            self._rs = None

        ax = canvas.ax
        self.statusBar().showMessage("Box zoom: drag over the area to zoom.")

        def _on_select(eclick, erelease):
            try:
                x1, y1 = eclick.xdata, eclick.ydata
                x2, y2 = erelease.xdata, erelease.ydata
                if None in (x1, y1, x2, y2):
                    return
                xmin, xmax = sorted([x1, x2])
                ymin, ymax = sorted([y1, y2])
                ax.set_xlim(xmin, xmax)
                ax.set_ylim(ymin, ymax)
                canvas.draw()
                self.statusBar().showMessage(f"Zoomed to X=({xmin}, {xmax})  Y=({ymin}, {ymax})")
            finally:
                if self._rs is not None:
                    try:
                        self._rs.set_active(False)
                    except Exception:
                        pass
                    self._rs = None

        self._rs = RectangleSelector(
            ax,
            _on_select,
            useblit=True,
            button=[1],
            interactive=False,
            minspanx=0,
            minspany=0,
            spancoords="data",
        )
