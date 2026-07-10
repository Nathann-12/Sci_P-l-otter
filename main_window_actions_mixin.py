from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pandas as pd
from PySide6 import QtGui

from dialogs_histogram import HistogramDialog

if TYPE_CHECKING:  # shared MainWindow state this mixin relies on (set in MainWindow.__init__)
    _df: object
    _datasets: dict
    tabs: object


class MainWindowActionsMixin:
    """Thin toolbar/menu dispatchers, dataframe accessors and drag-and-drop extracted from MainWindow."""

    def _activate_dataframe_candidate(self, df: pd.DataFrame, path=None) -> pd.DataFrame:
        """Cache a fallback candidate as the active dataset."""
        self._df = df.copy()
        self._current_path = path
        return self._df

    def _resolve_active_dataframe(self) -> pd.DataFrame | None:
        """Resolve active data using one compatibility-aware precedence policy."""
        for candidate in (
            getattr(self, "_df", None),
            getattr(self, "current_df", None),
        ):
            if isinstance(candidate, pd.DataFrame):
                return candidate

        workbook = getattr(self, "workbook", None)
        source_df = getattr(workbook, "source_df", None)
        if isinstance(source_df, pd.DataFrame):
            return self._activate_dataframe_candidate(source_df)

        datasets = getattr(self, "_datasets", {})
        if not isinstance(datasets, dict):
            return None

        selected_name = None
        list_widget = getattr(self, "lstFiles", None)
        if list_widget is not None:
            try:
                current_item = list_widget.currentItem()
                selected_name = current_item.text() if current_item is not None else None
            except (AttributeError, RuntimeError):
                selected_name = None

        entries = []
        if selected_name in datasets:
            entries.append(datasets[selected_name])
        entries.extend(data for name, data in datasets.items() if name != selected_name)

        for data in entries:
            if not isinstance(data, dict):
                continue
            candidate = data.get("df")
            if isinstance(candidate, pd.DataFrame):
                return self._activate_dataframe_candidate(candidate, data.get("path"))
        return None

    def get_current_dataframe(self) -> pd.DataFrame:
        """Return the active DataFrame, or an empty frame when no data is active."""
        df = self._resolve_active_dataframe()
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    # Action handlers
    def on_action_reload(self):
        """Reload current file"""
        if hasattr(self, 'current_file_path') and self.current_file_path:
            self.open_file(self.current_file_path)
        else:
            self.inform("Reload", "No file loaded to reload.")

    def on_action_plot(self):
        """Plot action handler - opens plot dialog"""
        self.plot_line()

    def on_action_spectrogram(self):
        """Spectrogram action handler"""
        self.open_spectrogram_dialog()

    def on_action_add_tab(self):
        """Add new tab action handler"""
        self.tabs.add_tab()

    def on_action_open_processors(self):
        """Open processors action handler"""
        # Simple FFT dialog for now
        self.run_fft_dialog()

    def on_action_export_figure(self):
        """Export figure action handler"""
        self.export_png()

    def on_action_export_data(self):
        """Export data action handler"""
        self.export_visible_range_csv()

    # Menu: Plot Histogram (uses toolbar or panel controls)
    def on_histogram_menu(self):
        # Open new non-modal Histogram dialog
        try:
            self.show_histogram_dialog()
        except Exception as e:
            print(f"Debug: open histogram dialog failed: {e}")

    # === Analysis overlay dialogs ===
    def get_current_xy(self):
        """Return (x,y) currently selected in Plot tab, using existing _get_xy logic."""
        try:
            x, y = self._get_xy()
            return x, y
        except Exception:
            return None, None

    def show_histogram_dialog(self):
        dlg = HistogramDialog(parent=self, get_current_data=self.get_current_xy)
        try:
            from PySide6.QtCore import Qt
            dlg.setWindowModality(Qt.NonModal)
        except Exception:
            pass
        dlg.resize(720, 480)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.show()

    def show_spectrogram_dialog(self):
        # Reuse existing spectrogram dialog path
        self.open_spectrogram_dialog()

    # DnD
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path): self.load_data(path); break
