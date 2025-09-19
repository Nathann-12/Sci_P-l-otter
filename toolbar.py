"""Custom toolbar helpers for SciPlotter."""
from __future__ import annotations

import logging

from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.backends.qt_compat import QtCore, QtWidgets


logger = logging.getLogger(__name__)


class PlotNavigationToolbar(NavigationToolbar2QT):
    """Navigation toolbar with a compact, scrollable Figure Options dialog."""

    _HEIGHT_RATIO = 0.5
    _WIDTH_RATIO = 0.8

    def edit_parameters(self) -> None:  # pragma: no cover - UI interaction
        super().edit_parameters()
        self._schedule_dialog_resize()

    # Internal helpers -------------------------------------------------
    def _schedule_dialog_resize(self) -> None:
        dialog = getattr(self, "_fedit_dialog", None)
        if dialog is None:
            return
        QtCore.QTimer.singleShot(0, self._shrink_fig_options_dialog)
        QtCore.QTimer.singleShot(150, self._shrink_fig_options_dialog)

    def _ensure_scroll_area(self, dialog: QtWidgets.QDialog) -> None:
        if getattr(dialog, "_sciplotter_scroll_wrapped", False):
            return
        formwidget = getattr(dialog, "formwidget", None)
        layout = dialog.layout()
        if formwidget is None or layout is None:
            return
        try:
            layout.removeWidget(formwidget)
        except Exception:
            logger.debug("Failed to detach form widget from figure options dialog", exc_info=True)
            return
        scroll = QtWidgets.QScrollArea(dialog)
        scroll.setObjectName("SciPlotterFigureOptionsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(formwidget)
        layout.insertWidget(0, scroll)
        dialog._sciplotter_scroll_wrapped = True

    def _shrink_fig_options_dialog(self) -> None:
        dialog = getattr(self, "_fedit_dialog", None)
        if dialog is None or not isinstance(dialog, QtWidgets.QDialog):
            return
        try:
            self._ensure_scroll_area(dialog)

            dialog.setMinimumSize(460, 300)
            dialog.adjustSize()

            screen = dialog.screen() or QtWidgets.QApplication.primaryScreen()
            if screen is None:
                max_width = 680
                max_height = 420
                center = None
            else:
                available = screen.availableGeometry()
                max_width = max(620, int(available.width() * self._WIDTH_RATIO))
                max_height = max(360, int(available.height() * self._HEIGHT_RATIO))
                center = available.center()

            width = min(dialog.width(), max_width)
            height = min(dialog.height(), max_height)

            dialog.setMaximumSize(max_width, max_height)
            dialog.resize(width, height)
            dialog.setSizeGripEnabled(True)

            if center is not None:
                geo = dialog.frameGeometry()
                geo.moveCenter(center)
                dialog.move(geo.topLeft())
        except Exception:  # pragma: no cover - defensive guard
            logger.debug("Could not resize Figure Options dialog", exc_info=True)
