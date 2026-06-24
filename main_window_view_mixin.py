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
        self.statusBar().showMessage("ล้างกราฟแล้ว")

    def _reset_view(self):
        """Reset view for current tab."""
        tab = self._get_current_tab()
        if tab is None:
            return

        ax = tab.get_axes()
        ax.set_xlim(auto=True)
        ax.set_ylim(auto=True)
        tab.draw()

    def _update_canvas_reference(self):
        """Update canvas reference to point to the current tab's canvas."""
        tab = self._get_current_tab()
        if tab is not None:
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
        self.statusBar().showMessage("เพิ่มแท็บใหม่แล้ว")

    def toggle_crosshair(self, checked: bool):
        if self._cursor is not None:
            self._cursor = None
        if self._cid_motion is not None:
            try:
                self.canvas.mpl_disconnect(self._cid_motion)
            except Exception:
                pass
            self._cid_motion = None

        if not checked:
            self.statusBar().showMessage("ปิด Crosshair แล้ว")
            self.canvas.draw()
            return

        self._cursor = Cursor(self.canvas.ax, useblit=True, horizOn=True, vertOn=True)

        def _on_move(event):
            if event.inaxes != self.canvas.ax:
                return
            x, y = event.xdata, event.ydata
            try:
                if x is None or y is None:
                    return
                self._sb_cursor.setText(f"x={x:.3g}, y={y:.3g}")
            except Exception:
                pass

        self._cid_motion = self.canvas.mpl_connect("motion_notify_event", _on_move)
        self.statusBar().showMessage("เปิด Crosshair แล้ว")
        self.canvas.draw()

    def toggle_inspector(self, checked: bool):
        try:
            self._panel_right.setVisible(bool(checked))
        except Exception:
            pass

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
        if self._rs is not None:
            try:
                self._rs.set_active(False)
            except Exception:
                pass
            self._rs = None

        ax = self.canvas.ax
        self.statusBar().showMessage("โหมดเลือกช่วง: ลากเมาส์คลุมพื้นที่ที่ต้องการซูม (คลิกซ้ายค้างแล้วลาก)")

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
                self.canvas.draw()
                self.statusBar().showMessage(f"ซูมช่วง X=({xmin}, {xmax})  Y=({ymin}, {ymax})")
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
