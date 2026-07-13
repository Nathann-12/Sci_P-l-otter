from __future__ import annotations

import logging
from typing import Sequence

from PySide6.QtWidgets import QMessageBox, QInputDialog, QFileDialog

from core.english_ui import sanitize_form_fields, to_english
from core.plot_request import PlotOptions

logger = logging.getLogger(__name__)


class MainWindowViewAccessMixin:
    """A thin 'view seam' between business logic and the concrete Qt widgets.

    Logic mixins should call these accessors instead of reaching into
    ``self.cbX`` / ``QInputDialog`` / ``self.statusBar()`` directly. That keeps
    the UI swappable (the upcoming Research OS shell re-implements this seam)
    and makes logic testable headless by stubbing these methods.

    The default implementations are backed by the current widgets.
    """

    # --- notifications -------------------------------------------------------
    def notify(
        self,
        msg: str,
        error: bool = False,
        *,
        level: str | None = None,
    ) -> None:
        """Show a transient status message."""
        error = error or level == "error"
        msg = to_english(msg, fallback="Operation completed.")
        try:
            self.statusBar().showMessage(msg)
        except Exception:
            if error:
                print(f"Error: {msg}")

    def warn(self, title: str, text: str) -> None:
        title = to_english(title, fallback="Warning")
        text = to_english(text, fallback="Check the current data and try again.")
        QMessageBox.warning(self, title, text)

    def inform(self, title: str, text: str) -> None:
        title = to_english(title, fallback="Information")
        text = to_english(text, fallback="Open a data file or select a Book first.")
        QMessageBox.information(self, title, text)

    def error_box(self, title: str, text: str) -> None:
        title = to_english(title, fallback="Error")
        text = to_english(text, fallback="The operation failed.")
        QMessageBox.critical(self, title, text)

    # --- column selection ----------------------------------------------------
    def selected_x_column(self) -> str:
        try:
            return self.cbX.currentText()
        except Exception:
            return ""

    def selected_y_column(self) -> str:
        try:
            return self.cbY.currentText()
        except Exception:
            return ""

    def selected_y_index(self) -> int:
        try:
            return self.cbY.currentIndex()
        except Exception:
            return -1

    def x_column_count(self) -> int:
        try:
            return self.cbX.count()
        except Exception:
            return 0

    def y_column_count(self) -> int:
        try:
            return self.cbY.count()
        except Exception:
            return 0

    def add_x_column_option(self, name: str) -> None:
        try:
            self.cbX.addItem(name)
        except Exception:
            pass

    def add_y_column_option(self, name: str) -> None:
        try:
            self.cbY.addItem(name)
        except Exception:
            pass
        # Every caller invokes this right after committing a new column to the
        # active DataFrame. The visible worksheet must follow (signal-transforms
        # contract) — Smooth/Filter/Normalize/... used to update only this
        # hidden combo, so on screen nothing appeared to happen at all.
        sync = getattr(self, "_sync_dataframe_after_column_edit", None)
        if callable(sync):
            try:
                sync()
            except Exception:
                logger.debug("worksheet sync after new column failed", exc_info=True)

    def current_plot_options(self) -> PlotOptions:
        """Return application plot defaults without exposing their storage."""
        options = getattr(self, "_plot_options", None)
        return options if isinstance(options, PlotOptions) else PlotOptions()

    # --- prompts -------------------------------------------------------------
    def ask_choice(self, title: str, label: str, options: Sequence[str], current: int = 0):
        """Modal single-choice picker. Returns (value, ok)."""
        title = to_english(title, fallback="Select")
        label = to_english(label, fallback="Choose an option:")
        return QInputDialog.getItem(self, title, label, list(options), current, False)

    def ask_number(self, title: str, label: str, value: float = 0.0,
                   minimum: float = -1e12, maximum: float = 1e12, decimals: int = 4):
        """Modal float input. Returns (value, ok)."""
        title = to_english(title, fallback="Value")
        label = to_english(label, fallback="Value:")
        return QInputDialog.getDouble(self, title, label, value, minimum, maximum, decimals)

    def ask_int(self, title: str, label: str, value: int = 0,
                minimum: int = -1_000_000_000, maximum: int = 1_000_000_000, step: int = 1):
        """Modal integer input. Returns (value, ok)."""
        title = to_english(title, fallback="Value")
        label = to_english(label, fallback="Value:")
        return QInputDialog.getInt(self, title, label, value, minimum, maximum, step)

    def ask_form(self, title, fields, description: str = None):
        """One consolidated dialog for multi-field input (replaces chained
        QInputDialog popups). Returns a dict of {name: value}, or None if
        cancelled. See dialogs.form_dialog for the field spec."""
        from dialogs.form_dialog import run_form
        return run_form(
            self,
            to_english(title, fallback="Options"),
            sanitize_form_fields(fields),
            description=to_english(description, fallback="") if description else description,
        )

    def ask_save_path(self, title: str, default_name: str, file_filter: str) -> str:
        title = to_english(title, fallback="Save As")
        path, _ = QFileDialog.getSaveFileName(self, title, default_name, file_filter)
        return path

    def ask_open_path(self, title: str, file_filter: str) -> str:
        title = to_english(title, fallback="Open")
        path, _ = QFileDialog.getOpenFileName(self, title, "", file_filter)
        return path

    def _apply_english_ui_texts(self, root=None) -> None:
        """Normalize existing static Qt chrome without touching worksheet data."""
        try:
            from PySide6.QtGui import QAction
            from PySide6.QtWidgets import (
                QDockWidget,
                QGroupBox,
                QLabel,
                QLineEdit,
                QMenu,
                QPushButton,
                QToolButton,
            )
        except Exception:
            return
        root = root or self

        try:
            for menu in root.findChildren(QMenu):
                menu.setTitle(to_english(menu.title(), fallback=menu.title() or "Menu"))
        except Exception:
            pass
        try:
            for action in root.findChildren(QAction):
                if action.text():
                    action.setText(to_english(action.text(), fallback=action.text()))
                if action.toolTip():
                    action.setToolTip(to_english(action.toolTip(), fallback=action.toolTip()))
                if action.statusTip():
                    action.setStatusTip(to_english(action.statusTip(), fallback=action.statusTip()))
        except Exception:
            pass
        widget_specs = (
            (QLabel, "text", "setText", "Label"),
            (QPushButton, "text", "setText", "Action"),
            (QToolButton, "text", "setText", "Action"),
            (QGroupBox, "title", "setTitle", "Group"),
            (QDockWidget, "windowTitle", "setWindowTitle", "Panel"),
        )
        for cls, getter, setter, fallback in widget_specs:
            try:
                widgets = []
                if isinstance(root, cls):
                    widgets.append(root)
                widgets.extend(root.findChildren(cls))
                for widget in widgets:
                    value = getattr(widget, getter)()
                    if value:
                        getattr(widget, setter)(to_english(value, fallback=fallback))
            except Exception:
                pass
        try:
            widgets = []
            if isinstance(root, QLineEdit):
                widgets.append(root)
            widgets.extend(root.findChildren(QLineEdit))
            for widget in widgets:
                value = widget.placeholderText()
                if value:
                    widget.setPlaceholderText(to_english(value, fallback=""))
        except Exception:
            pass

    def _install_english_ui_filter(self) -> None:
        """Sanitize dialogs/widgets created after startup when they are shown."""
        try:
            from PySide6.QtCore import QEvent, QObject
            from PySide6.QtWidgets import QApplication, QDialog, QMenu
            import weakref
        except Exception:
            return

        class _EnglishUiFilter(QObject):
            def __init__(self, owner, parent=None):
                super().__init__(parent)
                self.set_owner(owner)

            def set_owner(self, owner) -> None:
                self._owner_ref = weakref.ref(owner)

            def eventFilter(self, obj, event):  # noqa: N802 - Qt API
                try:
                    if event.type() == QEvent.Show and isinstance(obj, (QDialog, QMenu)):
                        if obj.property("_sciplotterEnglishUiDone"):
                            return False
                        obj.setProperty("_sciplotterEnglishUiDone", True)
                        owner = self._owner_ref()
                        if owner is None:
                            return False
                        owner._apply_english_ui_texts(obj)
                except Exception:
                    pass
                return False

        app = QApplication.instance()
        if app is None:
            return
        existing = getattr(app, "_sciplotter_english_ui_filter", None)
        if existing is not None:
            try:
                existing.set_owner(self)
                self._english_ui_filter = existing
            except Exception:
                pass
            return
        if getattr(self, "_english_ui_filter", None) is None:
            self._english_ui_filter = _EnglishUiFilter(self, app)
            app._sciplotter_english_ui_filter = self._english_ui_filter
            app.installEventFilter(self._english_ui_filter)

    # --- plotting surface ----------------------------------------------------
    def active_axes(self):
        """Return the matplotlib Axes of the active tab/canvas, or None."""
        try:
            tab = self.tabs.currentWidget()
            if tab is not None and hasattr(tab, "get_axes"):
                canvas = getattr(tab, "canvas", None)
                if canvas is not None:
                    self.canvas = canvas
                return tab.get_axes()
        except Exception:
            pass
        try:
            return self.canvas.ax
        except Exception:
            try:
                return self.tabs.currentWidget().get_axes()
            except Exception:
                return None
