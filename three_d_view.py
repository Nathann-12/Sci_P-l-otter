"""Dock widget providing manual controls for Matplotlib 3D views."""
from __future__ import annotations

import logging
from typing import List, Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from matplotlib.axes import Axes
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from PySide6.QtWidgets import QToolBar


logger = logging.getLogger(__name__)


class ThreeDViewDock(QDockWidget):
    """Expose rotation and zoom controls for a 3D Matplotlib axes."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("3D View Controls", parent)
        self.setObjectName("ThreeDViewDock")

        self._ax: Optional["Axes"] = None
        self._canvas: Optional["FigureCanvasQTAgg"] = None
        self._toolbar: Optional["QToolBar"] = None
        self._canvas_cids: List[int] = []
        self._updating: bool = False
        self._defaults = {"elev": 30.0, "azim": -60.0, "dist": 10.0}

        container = QWidget(self)
        layout = QFormLayout(container)
        layout.setLabelAlignment(Qt.AlignRight)

        self.spin_elev = QDoubleSpinBox(container)
        self.spin_elev.setRange(-180.0, 180.0)
        self.spin_elev.setDecimals(1)
        self.spin_elev.setSingleStep(1.0)
        self.spin_elev.valueChanged.connect(self._update_axes_view)
        layout.addRow("Elevation (deg)", self.spin_elev)

        self.spin_azim = QDoubleSpinBox(container)
        self.spin_azim.setRange(-360.0, 360.0)
        self.spin_azim.setDecimals(1)
        self.spin_azim.setSingleStep(1.0)
        self.spin_azim.valueChanged.connect(self._update_axes_view)
        layout.addRow("Azimuth (deg)", self.spin_azim)

        self.spin_dist = QDoubleSpinBox(container)
        self.spin_dist.setRange(2.0, 100.0)
        self.spin_dist.setDecimals(1)
        self.spin_dist.setSingleStep(0.5)
        self.spin_dist.valueChanged.connect(self._update_axes_view)
        layout.addRow("Distance", self.spin_dist)

        buttons_layout = QHBoxLayout()
        self.btn_reset = QPushButton("Reset View", container)
        self.btn_sync = QPushButton("Sync From Plot", container)
        buttons_layout.addWidget(self.btn_reset)
        buttons_layout.addWidget(self.btn_sync)
        buttons_row = QWidget(container)
        buttons_row.setLayout(buttons_layout)
        layout.addRow("", buttons_row)

        self.chk_toolbar = QCheckBox("Show Matplotlib toolbar", container)
        self.chk_toolbar.toggled.connect(self._toggle_toolbar)
        layout.addRow("", self.chk_toolbar)

        tips = QLabel("Tip: drag with the mouse to rotate; use the wheel to zoom.", container)
        tips.setWordWrap(True)
        tips.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addRow(tips)

        self.setWidget(container)
        self.setEnabled(False)

        self.btn_reset.clicked.connect(self._reset_view)
        self.btn_sync.clicked.connect(self._sync_from_axes)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def attach_axes(
        self,
        ax: Optional["Axes"],
        canvas: Optional["FigureCanvasQTAgg"] = None,
        toolbar: Optional["QToolBar"] = None,
    ) -> None:
        """Bind the dock to a 3D axes and optional canvas/toolbar."""
        if ax is None or not hasattr(ax, "view_init"):
            self.detach_axes()
            return

        logger.debug("Attaching 3D view dock to axes %s", ax)

        self._disconnect_canvas_events()
        self._ax = ax
        self._canvas = canvas
        self._toolbar = toolbar

        try:
            self._defaults = {
                "elev": float(getattr(ax, "elev", self._defaults["elev"])),
                "azim": float(getattr(ax, "azim", self._defaults["azim"])),
                "dist": float(getattr(ax, "dist", self._defaults["dist"])),
            }
        except Exception:  # pragma: no cover - defensive
            logger.debug("Failed to read 3D defaults", exc_info=True)

        self.setEnabled(True)
        self._sync_from_axes()
        self._connect_canvas_events()
        self._ensure_toolbar_checkbox_state()

    def detach_axes(self) -> None:
        """Clear references and disable the dock."""
        self._disconnect_canvas_events()
        self._ax = None
        self._canvas = None
        self._toolbar = None
        self.setEnabled(False)

        blocker = QSignalBlocker(self.chk_toolbar)
        self.chk_toolbar.setChecked(False)
        del blocker
        self.chk_toolbar.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots / helpers
    # ------------------------------------------------------------------
    def _sync_from_axes(self) -> None:
        if self._ax is None:
            return

        self._updating = True
        blockers = [
            QSignalBlocker(self.spin_elev),
            QSignalBlocker(self.spin_azim),
            QSignalBlocker(self.spin_dist),
        ]
        try:
            elev = float(getattr(self._ax, "elev", self._defaults["elev"]))
            azim = float(getattr(self._ax, "azim", self._defaults["azim"]))
            dist = float(getattr(self._ax, "dist", self._defaults["dist"]))
            self.spin_elev.setValue(elev)
            self.spin_azim.setValue(azim)
            self.spin_dist.setValue(dist)
        except Exception:  # pragma: no cover - defensive
            logger.debug("Failed to sync 3D view controls", exc_info=True)
        finally:
            del blockers
            self._updating = False

    def _update_axes_view(self) -> None:
        if self._ax is None or self._updating:
            return

        elev = float(self.spin_elev.value())
        azim = float(self.spin_azim.value())
        dist = float(self.spin_dist.value())

        logger.debug("Updating 3D view: elev=%s azim=%s dist=%s", elev, azim, dist)

        try:
            self._ax.view_init(elev=elev, azim=azim)
            if hasattr(self._ax, "dist"):
                self._ax.dist = dist
            self._ax.figure.canvas.draw_idle()
        except Exception:  # pragma: no cover - defensive
            logger.debug("Failed to update 3D axes", exc_info=True)

    def _reset_view(self) -> None:
        if self._ax is None:
            return

        blockers = [
            QSignalBlocker(self.spin_elev),
            QSignalBlocker(self.spin_azim),
            QSignalBlocker(self.spin_dist),
        ]
        try:
            self.spin_elev.setValue(self._defaults.get("elev", 30.0))
            self.spin_azim.setValue(self._defaults.get("azim", -60.0))
            self.spin_dist.setValue(self._defaults.get("dist", 10.0))
        finally:
            del blockers

        self._update_axes_view()

    def _toggle_toolbar(self, checked: bool) -> None:
        if self._toolbar is None:
            return
        try:
            self._toolbar.setVisible(bool(checked))
        except Exception:  # pragma: no cover - defensive
            logger.debug("Failed to toggle toolbar visibility", exc_info=True)

    def _ensure_toolbar_checkbox_state(self) -> None:
        has_toolbar = self._toolbar is not None
        blocker = QSignalBlocker(self.chk_toolbar)
        try:
            self.chk_toolbar.setEnabled(has_toolbar)
            if has_toolbar:
                self.chk_toolbar.setChecked(self._toolbar.isVisible())
            else:
                self.chk_toolbar.setChecked(False)
        finally:
            del blocker

    def _connect_canvas_events(self) -> None:
        if self._canvas is None:
            return
        try:
            self._canvas_cids.append(self._canvas.mpl_connect("button_release_event", self._on_canvas_event))
            self._canvas_cids.append(self._canvas.mpl_connect("scroll_event", self._on_canvas_event))
        except Exception:  # pragma: no cover - defensive
            logger.debug("Failed to connect canvas events", exc_info=True)

    def _disconnect_canvas_events(self) -> None:
        if self._canvas is None:
            self._canvas_cids.clear()
            return
        for cid in self._canvas_cids:
            try:
                self._canvas.mpl_disconnect(cid)
            except Exception:  # pragma: no cover - defensive
                logger.debug("Failed to disconnect canvas event", exc_info=True)
        self._canvas_cids.clear()

    # Matplotlib event handler -------------------------------------------------
    def _on_canvas_event(self, event) -> None:  # type: ignore[override]
        if self._ax is None:
            return
        in_axes = getattr(event, "inaxes", None) is self._ax
        if not in_axes:
            return

        if getattr(event, "name", "") == "scroll_event":
            step = getattr(event, "step", 0)
            if step == 0:
                return
            dist = float(getattr(self._ax, "dist", self.spin_dist.value()))
            factor = 0.9 if step > 0 else 1.1
            new_dist = max(self.spin_dist.minimum(), min(self.spin_dist.maximum(), dist * factor))
            logger.debug("Scroll zoom: step=%s dist=%s -> %s", step, dist, new_dist)
            try:
                self._ax.dist = new_dist
                self.spin_dist.setValue(new_dist)
                self._ax.figure.canvas.draw_idle()
            except Exception:  # pragma: no cover
                logger.debug("Failed during scroll zoom", exc_info=True)
            return

        # For rotation/pan updates, refresh controls after the interaction.
        self._sync_from_axes()
