from __future__ import annotations

from typing import Sequence

from PySide6.QtWidgets import QMessageBox, QInputDialog, QFileDialog


class MainWindowViewAccessMixin:
    """A thin 'view seam' between business logic and the concrete Qt widgets.

    Logic mixins should call these accessors instead of reaching into
    ``self.cbX`` / ``QInputDialog`` / ``self.statusBar()`` directly. That keeps
    the UI swappable (the upcoming Research OS shell re-implements this seam)
    and makes logic testable headless by stubbing these methods.

    The default implementations are backed by the current widgets.
    """

    # --- notifications -------------------------------------------------------
    def notify(self, msg: str, error: bool = False) -> None:
        """Show a transient status message."""
        try:
            self.statusBar().showMessage(msg)
        except Exception:
            pass

    def warn(self, title: str, text: str) -> None:
        QMessageBox.warning(self, title, text)

    def inform(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)

    def error_box(self, title: str, text: str) -> None:
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

    # --- prompts -------------------------------------------------------------
    def ask_choice(self, title: str, label: str, options: Sequence[str], current: int = 0):
        """Modal single-choice picker. Returns (value, ok)."""
        return QInputDialog.getItem(self, title, label, list(options), current, False)

    def ask_number(self, title: str, label: str, value: float = 0.0,
                   minimum: float = -1e12, maximum: float = 1e12, decimals: int = 4):
        """Modal float input. Returns (value, ok)."""
        return QInputDialog.getDouble(self, title, label, value, minimum, maximum, decimals)

    def ask_int(self, title: str, label: str, value: int = 0,
                minimum: int = -1_000_000_000, maximum: int = 1_000_000_000, step: int = 1):
        """Modal integer input. Returns (value, ok)."""
        return QInputDialog.getInt(self, title, label, value, minimum, maximum, step)

    def ask_save_path(self, title: str, default_name: str, file_filter: str) -> str:
        path, _ = QFileDialog.getSaveFileName(self, title, default_name, file_filter)
        return path

    # --- plotting surface ----------------------------------------------------
    def active_axes(self):
        """Return the matplotlib Axes of the active tab/canvas, or None."""
        try:
            return self.canvas.ax
        except Exception:
            try:
                return self.tabs.currentWidget().get_axes()
            except Exception:
                return None
