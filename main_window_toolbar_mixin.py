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
        self.tb.setIconSize(QSize(22, 22))
        self.tb.setMovable(False)
        # Icon-only toolbar: full labels live in tooltips so nothing gets
        # elided into unreadable garbage when the window is narrow.
        try:
            from PySide6.QtCore import Qt
            self.tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        except Exception:
            pass
        self.addToolBar(self.tb)

        # Create toolbar actions
        self._create_toolbar_actions()

        # Every action's text becomes its tooltip so icon-only stays discoverable
        self._sync_toolbar_tooltips()

        # Apply styling
        self._apply_toolbar_styling()

        # Origin-style 2D plot bar (bottom): select columns on the sheet ->
        # click an icon -> a NEW graph window appears.
        try:
            self.build_plot_toolbar()
        except Exception:
            logging.getLogger(__name__).debug("plot toolbar skipped", exc_info=True)

    # Origin's 2D graph toolbar. (kind, icon candidates, thai tooltip, style key)
    _PLOT_BAR_SPECS = (
        ("Line", ("mdi.chart-line", "fa5s.chart-line"),
         "พล็อตเส้น → Graph ใหม่", "line"),
        ("Scatter", ("mdi.chart-scatter-plot", "fa5s.braille"),
         "พล็อตจุด (Scatter) → Graph ใหม่", "scatter"),
        ("Line+Symbol", ("mdi.chart-timeline-variant", "fa5s.chart-line"),
         "เส้น+จุด → Graph ใหม่", "linesymbol"),
        ("Column", ("mdi.chart-bar", "fa5s.chart-bar"),
         "กราฟแท่ง → Graph ใหม่", "bar"),
        ("Histogram", ("mdi.chart-histogram", "fa5s.chart-area"),
         "Histogram → Graph ใหม่", "histogram"),
    )

    def _plot_bar_icon(self, candidates, fallback_sp=QStyle.StandardPixmap.SP_FileDialogContentsView):
        """qtawesome icon from the first available candidate name, else a
        standard-pixmap fallback (never raises)."""
        try:
            import qtawesome as qta
            for name in candidates:
                try:
                    return qta.icon(name, color="#cfd3d6")
                except Exception:
                    continue
        except Exception:
            pass
        try:
            return self.style().standardIcon(fallback_sp)
        except Exception:
            from PySide6.QtGui import QIcon
            return QIcon()

    def build_plot_toolbar(self):
        """Origin-style plot bar: one icon per graph type, always visible at
        the bottom. Every action funnels into plot_from_workbook(new_graph=True)."""
        from PySide6.QtCore import Qt

        tb = QToolBar("Plot Toolbar", self)
        tb.setObjectName("PlotToolbar")
        tb.setIconSize(QSize(20, 20))
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)

        self.plot_bar_actions = {}
        for name, icons, tip, style in self._PLOT_BAR_SPECS:
            act = QAction(self._plot_bar_icon(icons), name, self)
            act.setToolTip(tip)
            act.triggered.connect(
                lambda _=False, s=style: self.plot_from_workbook(s, new_graph=True))
            tb.addAction(act)
            self.plot_bar_actions[style] = act

        self.addToolBar(Qt.BottomToolBarArea, tb)
        self.plot_toolbar = tb

    def _sync_toolbar_tooltips(self):
        """Make each toolbar action's tooltip = its label (icon-only mode).

        Strips trailing ellipsis from labels for cleaner tooltips and leaves
        any action that already has a richer tooltip untouched.
        """
        try:
            for action in self.tb.actions():
                if action.isSeparator():
                    continue
                text = (action.text() or "").replace("&", "").strip()
                if not text:
                    continue
                clean = text.rstrip(".").rstrip("…").strip() or text
                if not action.toolTip() or action.toolTip() == action.text():
                    action.setToolTip(clean)
        except Exception:
            logging.getLogger(__name__).debug(
                "Failed to sync toolbar tooltips", exc_info=True
            )

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
            try:
                self.actSettings.setIcon(self._icon("settings", QStyle.StandardPixmap.SP_FileDialogDetailedView))
            except Exception:
                pass
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

        # === กลุ่มที่ 7: การตั้งค่า ===
        self.tb.addAction(self.actSettings)

    def _apply_toolbar_styling(self):
        """Apply calm, flat icon-button styling to the toolbar.

        Icon-only buttons with a subtle hover, hairline separators and the
        blue accent reserved for the active (checked) state only.
        """
        try:
            # Allow an external override file to win if present
            qss_path = os.path.join("styles", "toolbar.qss")
            if os.path.exists(qss_path):
                with open(qss_path, 'r', encoding='utf-8') as f:
                    self.tb.setStyleSheet(f.read())
                return

            self.tb.setStyleSheet("""
                QToolBar {
                    background: #1b1e23;
                    border: none;
                    border-bottom: 1px solid #2a2f36;
                    spacing: 2px;
                    padding: 5px 8px;
                }

                QToolBar::separator {
                    background-color: #2f343b;
                    width: 1px;
                    margin: 6px 6px;
                }

                QToolBar QToolButton {
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: 8px;
                    padding: 6px;
                    margin: 0px;
                    color: #cfd3d6;
                }

                QToolBar QToolButton:hover {
                    background-color: rgba(255, 255, 255, 0.06);
                    border: 1px solid transparent;
                    color: #ffffff;
                }

                QToolBar QToolButton:pressed {
                    background-color: rgba(255, 255, 255, 0.10);
                }

                QToolBar QToolButton:checked {
                    background-color: rgba(79, 156, 249, 0.16);
                    border: 1px solid rgba(79, 156, 249, 0.45);
                    color: #4F9CF9;
                }

                QToolBar QToolButton:checked:hover {
                    background-color: rgba(79, 156, 249, 0.24);
                }
            """)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to apply toolbar styling: {e}")

    # --- Responsive UI helpers ---
    def _update_compact_ui(self):
        """Keep the main toolbar icon-only at every width.

        Labels are surfaced through tooltips, so we never elide text into
        unreadable fragments. This intentionally no longer switches button
        styles by width.
        """
        try:
            from PySide6.QtCore import Qt
            self.tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        except Exception:
            pass
