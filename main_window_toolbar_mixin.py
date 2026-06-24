from __future__ import annotations

import os
import logging

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar, QWidget, QSizePolicy, QStyle


class MainWindowToolbarMixin:
    """Main toolbar construction, styling and responsive density extracted from MainWindow."""

    def build_toolbar(self):
        """Build the main toolbar with organized groups"""
        self.tb = QToolBar("Main Toolbar", self)
        self.tb.setIconSize(QSize(24, 24))
        # Show icon + text on toolbar buttons for clarity
        try:
            from PySide6.QtCore import Qt
            self.tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        except Exception:
            pass
        self.addToolBar(self.tb)

        # Create toolbar actions
        self._create_toolbar_actions()

        # Apply styling
        self._apply_toolbar_styling()

    def _create_toolbar_actions(self):
        """Create all toolbar actions with proper grouping"""
        # สร้าง actions ที่จำเป็นถ้ายังไม่มี
        if not hasattr(self, 'actToggleInspector'):
            self.actToggleInspector = QAction("Inspector", self)
            self.actToggleInspector.setCheckable(True)
            self.actToggleInspector.triggered.connect(self.toggle_inspector)
            try:
                self.actToggleInspector.setIcon(self._icon("inspector", QStyle.StandardPixmap.SP_FileDialogInfoView))
            except Exception:
                pass

        if not hasattr(self, 'actOpen'):
            self.actOpen = QAction("Open", self)
            # Connect lazily to avoid init-order issues
            try:
                self.actOpen.triggered.connect(self.open_file)
            except Exception:
                self.actOpen.triggered.connect(lambda: getattr(self, 'open_file', lambda: None)())
            try:
                self.actOpen.setIcon(self._icon("open", QStyle.StandardPixmap.SP_DialogOpenButton))
            except Exception:
                pass

        if not hasattr(self, 'actSettings'):
            self.actSettings = QAction("Settings", self)
            self.actSettings.triggered.connect(self.show_settings)
        if not hasattr(self, 'actPlotEquation'):
            self.actPlotEquation = QAction('Plot from Equation...', self)
            self.actPlotEquation.triggered.connect(self.on_plot_from_equation)
            try:
                self.actPlotEquation.setIcon(self._icon('Plot_from_Equation', QStyle.StandardPixmap.SP_DialogApplyButton))
            except Exception:
                pass

        # === กลุ่มที่ 1: ไฟล์และข้อมูล ===
        self.tb.addAction(self.actOpen)
        # Place Inspector as the second button after Open
        self.tb.addAction(self.actToggleInspector)
        self.tb.addAction(self.actPlotEquation)
        self.tb.addSeparator()

        # === กลุ่มที่ 2: การสร้างกราฟ ===
        act_plot = self.tb.addAction("Plot", self.on_action_plot)
        act_spec = self.tb.addAction("Spectrogram", self.on_action_spectrogram)
        try:
            act_plot.setIcon(self._icon("plot", QStyle.StandardPixmap.SP_FileDialogContentsView))
            act_spec.setIcon(self._icon("fft", QStyle.StandardPixmap.SP_MediaPlay))
        except Exception:
            pass
        self.tb.addSeparator()

        # === กลุ่มที่ 3: การจัดการแท็บ ===
        act_add_tab = self.tb.addAction("Add Tab", self.on_action_add_tab)
        try:
            act_add_tab.setIcon(self._icon("addtab", QStyle.StandardPixmap.SP_FileDialogNewFolder))
        except Exception:
            pass
        self.tb.addSeparator()

        # === กลุ่มที่ 4: การประมวลผลข้อมูล ===
        act_processors = self.tb.addAction("Processors", self.on_action_open_processors)
        try:
            act_processors.setIcon(self._icon("settings", QStyle.StandardPixmap.SP_FileDialogDetailedView))
        except Exception:
            pass
        self.tb.addSeparator()

        # === กลุ่มที่ 5: การส่งออกข้อมูล ===
        act_export_fig = self.tb.addAction("Export Figure", self.on_action_export_figure)
        act_export_data = self.tb.addAction("Export Data", self.on_action_export_data)
        try:
            act_export_fig.setIcon(self._icon("export", QStyle.StandardPixmap.SP_DialogSaveButton))
            act_export_data.setIcon(self._icon("export", QStyle.StandardPixmap.SP_DialogSaveButton))
        except Exception:
            pass
        self.tb.addSeparator()

        # === กลุ่มที่ 6: การแสดงผลและเครื่องมือ ===
        # Inspector already added near the Open button for better access

        # Error Panel toggle
        self.actErrorPanel = self.tb.addAction("Error Panel")
        self.actErrorPanel.setCheckable(True)
        self.actErrorPanel.triggered.connect(self.toggle_error_panel)
        try:
            self.actErrorPanel.setIcon(self._icon("clear", QStyle.StandardPixmap.SP_MessageBoxWarning))
        except Exception:
            pass
        self.tb.addSeparator()

        # === กลุ่มที่ 7: การตั้งค่า (ขวาสุด) ===
        # Spacer เพื่อผลักปุ่ม Settings ไปขวาสุด
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.tb.addWidget(spacer)

        self.tb.addAction(self.actSettings)

    def _apply_toolbar_styling(self):
        """Apply QSS styling to toolbar"""
        try:
            # Try to load from styles/toolbar.qss
            qss_path = os.path.join("styles", "toolbar.qss")
            if os.path.exists(qss_path):
                with open(qss_path, 'r', encoding='utf-8') as f:
                    self.tb.setStyleSheet(f.read())
            else:
                # Enhanced toolbar styling
                self.tb.setStyleSheet("""
                    QToolBar {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #3a3a3a, stop:1 #2b2b2b);
                        border: none;
                        border-bottom: 1px solid #404040;
                        spacing: 6px;
                        padding: 4px 8px;
                        font-size: 11px;
                        font-weight: 500;
                    }

                    QToolBar::separator {
                        background-color: #555555;
                        width: 1px;
                        margin: 6px 4px;
                        border-radius: 1px;
                    }

                    QToolButton {
                        background-color: transparent;
                        border: 1px solid transparent;
                        border-radius: 6px;
                        padding: 6px 10px;
                        margin: 1px;
                        color: #e0e0e0;
                        font-size: 11px;
                        font-weight: 500;
                        min-width: 60px;
                        text-align: center;
                    }

                    QToolButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #4a4a4a, stop:1 #3a3a3a);
                        border: 1px solid #666666;
                        color: #ffffff;
                    }

                    QToolButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #0078d4, stop:1 #106ebe);
                        border: 1px solid #106ebe;
                        color: #ffffff;
                    }

                    QToolButton:checked {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #0078d4, stop:1 #106ebe);
                        border: 1px solid #106ebe;
                        color: #ffffff;
                    }

                    /* Special styling for different groups */
                    QToolButton[text="Open"] {
                        background-color: #28a745;
                        color: #ffffff;
                        font-weight: bold;
                    }
                    QToolButton[text="Open"]:hover {
                        background-color: #218838;
                    }

                    QToolButton[text="Plot"] {
                        background-color: #007bff;
                        color: #ffffff;
                        font-weight: bold;
                    }
                    QToolButton[text="Plot"]:hover {
                        background-color: #0056b3;
                    }

                    QToolButton[text="Export Figure"],
                    QToolButton[text="Export Data"] {
                        background-color: #17a2b8;
                        color: #ffffff;
                        font-weight: bold;
                    }
                    QToolButton[text="Export Figure"]:hover,
                    QToolButton[text="Export Data"]:hover {
                        background-color: #138496;
                    }

                    QToolButton[text="Settings"] {
                        background-color: #6c757d;
                        color: #ffffff;
                        font-weight: bold;
                    }
                    QToolButton[text="Settings"]:hover {
                        background-color: #545b62;
                    }
                """)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to apply toolbar styling: {e}")

    # --- Responsive UI helpers ---
    def _update_compact_ui(self):
        """Switch toolbar density/icon mode based on window width.
        Keep icons-only when narrow to avoid ugly elided labels."""
        try:
            from PySide6.QtCore import Qt
            w = self.width()
            # Wide: text beside icon; Medium: text under icon; Narrow: icon only
            if w < 900:
                self.tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
            elif w < 1200:
                self.tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            else:
                self.tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        except Exception:
            pass
