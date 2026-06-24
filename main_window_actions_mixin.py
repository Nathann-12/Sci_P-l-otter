from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pandas as pd
from PySide6 import QtGui
from PySide6.QtWidgets import QMessageBox

from dialogs_histogram import HistogramDialog

if TYPE_CHECKING:  # shared MainWindow state this mixin relies on (set in MainWindow.__init__)
    _df: object
    _datasets: dict
    tabs: object


class MainWindowActionsMixin:
    """Thin toolbar/menu dispatchers, dataframe accessors and drag-and-drop extracted from MainWindow."""

    def _resolve_active_dataframe(self) -> pd.DataFrame:
        """Return the current DataFrame, falling back to staged datasets."""
        df = getattr(self, '_df', None)
        if isinstance(df, pd.DataFrame):
            return df
        df = getattr(self, 'current_df', None)
        if isinstance(df, pd.DataFrame):
            return df
    def get_current_dataframe(self) -> pd.DataFrame:
        """คืน DataFrame ปัจจุบัน (ถ้าไม่มีให้ผลลัพธ์ว่าง)."""
        df = self._resolve_active_dataframe()
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

        datasets = getattr(self, '_datasets', {}) if hasattr(self, '_datasets') else {}
        lst_widget = getattr(self, 'lstFiles', None)
        current_item = None
        if lst_widget is not None:
            try:
                current_item = lst_widget.currentItem()
            except Exception:
                current_item = None
        if current_item is not None and isinstance(datasets, dict):
            data = datasets.get(current_item.text())
            df_candidate = data.get('df') if isinstance(data, dict) else None
            if isinstance(df_candidate, pd.DataFrame):
                if getattr(self, '_df', None) is None:
                    try:
                        self._df = df_candidate.copy()
                    except Exception:
                        self._df = df_candidate
                try:
                    if isinstance(data, dict) and data.get('path'):
                        self._current_path = data.get('path')
                except Exception:
                    pass
                return df_candidate
        if isinstance(datasets, dict):
            for data in datasets.values():
                if not isinstance(data, dict):
                    continue
                df_candidate = data.get('df')
                if isinstance(df_candidate, pd.DataFrame):
                    if getattr(self, '_df', None) is None:
                        try:
                            self._df = df_candidate.copy()
                        except Exception:
                            self._df = df_candidate
                    try:
                        if data.get('path'):
                            self._current_path = data.get('path')
                    except Exception:
                        pass
                    return df_candidate
        return pd.DataFrame()

    # Action handlers
    def on_action_reload(self):
        """Reload current file"""
        if hasattr(self, 'current_file_path') and self.current_file_path:
            self.open_file(self.current_file_path)
        else:
            QMessageBox.information(self, "Reload", "No file loaded to reload.")

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

    # Toolbar: histogram plot using compact controls
    def _on_toolbar_plot_histogram(self):
        try:
            # Sync hidden panel controls then reuse existing logic
            if hasattr(self, 'tbCbHist'):
                col = self.tbCbHist.currentText()
                if hasattr(self, 'cbHist'):
                    try: self.cbHist.setCurrentText(col)
                    except Exception: pass
            if hasattr(self, 'tbHistBins') and hasattr(self, 'spHistBins'):
                try: self.spHistBins.setValue(int(self.tbHistBins.value()))
                except Exception: pass
            if hasattr(self, 'tbHistFit') and hasattr(self, 'chkHistFit'):
                try: self.chkHistFit.setChecked(bool(self.tbHistFit.isChecked()))
                except Exception: pass
            # Call existing workflow
            self.plot_histogram()
        except Exception as e:
            print(f"Debug: toolbar histogram failed: {e}")

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
