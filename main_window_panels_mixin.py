from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
    QSizePolicy, QGraphicsDropShadowEffect, QMessageBox, QWidget,
)

from widgets.plot_tabs import CompactPlotPanel

if TYPE_CHECKING:  # shared MainWindow state this mixin relies on (set in MainWindow.__init__)
    import pandas as _pd

    _df: "_pd.DataFrame | None"
    _datasets: dict


class MainWindowPanelsMixin:
    """Left panel, right Inspector tabs, layer manager and sidepanel styling extracted from MainWindow."""

    def _build_left_panel(self):
        """Workflow spine — 3 numbered steps so the app explains itself:
        ① เปิด/พิมพ์ข้อมูล → ② เลือกคอลัมน์แล้วพล็อต → ③ เครื่องมือกราฟ"""
        l = self._left_layout

        # ── Data ─────────────────────────────────────────────────────
        # Origin model: opening a file = a new Book; the dataset list lives in
        # the Project Explorer (no staging list anymore)
        gb_data = QGroupBox("Data")
        gbd = QVBoxLayout(gb_data); gbd.setContentsMargins(8, 8, 8, 8); gbd.setSpacing(8)
        self.btnOpenData = QPushButton("Open Data File…")
        self.btnOpenData.setToolTip("CSV / TSV / TXT / Excel / JSON / HDF5 / MAT / XML / NetCDF / CDF — opens a new Book")
        gbd.addWidget(self.btnOpenData)
        self.btnUseSheet = QPushButton("Use Sheet Data (Book)")
        self.btnUseSheet.setToolTip("Type data into a Book, then click to use it for plotting / analysis")
        gbd.addWidget(self.btnUseSheet)
        self.lblFile = QLabel("No file opened"); self.lblFile.setWordWrap(True)
        gbd.addWidget(self.lblFile)
        l.addWidget(gb_data)

        # ── Origin loop: การพล็อตทำผ่าน worksheet + แถบไอคอนพล็อตล่างแล้ว ──
        # CompactPlotPanel is retained only for the column-selection and legacy
        # button seams. Plot styling now lives in immutable PlotOptions.
        panel = CompactPlotPanel(self)
        panel.hide()

        # aliases เดิม — โค้ด mixin อื่นเรียกผ่านชื่อพวกนี้ทั้งหมด
        self.panel_plot = panel
        self.btnLoadCols = getattr(panel, "btnLoadCols", getattr(panel, "btn_load_cols", None))
        self.cbX         = panel.cbo_x
        self.cbY         = panel.cbo_y
        self.btnLine     = panel.btn_line
        self.btnScatter  = panel.btn_scatter
        self.btnClear    = panel.btn_clear
        self.btnCurveFit = panel.btn_fit

        # ── Graph Tools ──────────────────────────────────────────────
        gb_tools = QGroupBox("Graph Tools")
        gbt = QVBoxLayout(gb_tools); gbt.setContentsMargins(8, 8, 8, 8); gbt.setSpacing(8)
        self.chkCross = QCheckBox("Show Crosshair")
        gbt.addWidget(self.chkCross)
        self.btnBoxZoom = QPushButton("Box Zoom (drag to zoom)")
        gbt.addWidget(self.btnBoxZoom)
        l.addWidget(gb_tools)

        l.addStretch(1)

        # ปุ่มขั้น ① ต่อเข้าเส้นทางเดิม (open_file / adopt_workbook_data มาจาก data mixin)
        try:
            self.btnOpenData.clicked.connect(lambda _=False: getattr(self, "open_file", lambda: None)())
            self.btnUseSheet.clicked.connect(lambda _=False: getattr(self, "adopt_workbook_data", lambda: None)())
        except Exception:
            pass
        # UI-REFINE: การเชื่อมสัญญาณอื่นอยู่ที่ _connect_signals()

    def _build_inspector_tabs(self):
        """
        Inspector ด้านขวา: Plot / Processing / Export
        - Plot ใช้ CompactPlotPanel เพียงชุดเดียว (ไม่มีวิดเจ็ตเก่าซ้ำซ้อน)
        - ทำ alias ตัวแปรเดิมให้โค้ดส่วนอื่นเรียกต่อได้
        """
        from PySide6.QtWidgets import (
            QTabWidget, QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QPushButton, QFrame
        )
        from PySide6.QtCore import Qt

        r = self._right_layout

        # ---------- Tabs ----------
        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)
        try:
            tabs.setMaximumWidth(420)
        except Exception:
            pass
        # ================== TAB: PLOT (Layers) ==================
        # ชุดเลือกคอลัมน์/ปุ่มพล็อต (CompactPlotPanel) อยู่ที่ panel ซ้ายขั้น ②
        # แล้ว — Inspector เหลือหน้าที่เสริม: จัดการ Layers ของกราฟ
        tab_plot = QWidget()
        tp = QVBoxLayout(tab_plot)
        tp.setContentsMargins(8,8,8,8)
        tp.setSpacing(8)

        if not hasattr(self, "panel_plot"):
            # เผื่อกรณีสร้าง Inspector โดยไม่ได้สร้าง left panel (เช่นในเทสต์เก่า)
            panel = CompactPlotPanel(self)
            tp.addWidget(panel)
            self.panel_plot = panel
            self.btnLoadCols = getattr(panel, "btnLoadCols", getattr(panel, "btn_load_cols", None))
            self.cbX         = panel.cbo_x
            self.cbY         = panel.cbo_y
            self.btnLine     = panel.btn_line
            self.btnScatter  = panel.btn_scatter
            self.btnClear    = panel.btn_clear
            self.btnCurveFit = panel.btn_fit
        self.layerGroup = QGroupBox("Layers", self)
        self.layerGroupLayout = QVBoxLayout(self.layerGroup)
        self.layerGroupLayout.setContentsMargins(6, 6, 6, 6)
        self.layerGroupLayout.setSpacing(6)
        self._layer_manager_empty = QLabel("No layers yet", self.layerGroup)
        self._layer_manager_empty.setAlignment(Qt.AlignCenter)
        self.layerGroupLayout.addWidget(self._layer_manager_empty)
        tp.addWidget(self.layerGroup)

        tabs.addTab(tab_plot, "Plot")

        # ================== TAB: PROCESSING ==================
        tab_proc = QWidget()
        pr = QVBoxLayout(tab_proc); pr.setContentsMargins(8,8,8,8); pr.setSpacing(8)

        gb_feat = QGroupBox("Extra Features"); pr.addWidget(gb_feat)
        gbl = QVBoxLayout(gb_feat); gbl.setContentsMargins(8,8,8,8); gbl.setSpacing(8)
        row1 = QHBoxLayout();
        self.btnTZ  = QPushButton("Add Bangkok Time (+7h)");
        self.btnMag = QPushButton("Add |B| from 3 Axes");
        row1.addWidget(self.btnTZ); row1.addWidget(self.btnMag); gbl.addLayout(row1)
        row2 = QHBoxLayout();
        self.btnMA  = QPushButton("Add Moving Average (Y)");
        row2.addWidget(self.btnMA); gbl.addLayout(row2)
        rowAgg = QHBoxLayout();
        self.btnAgg = QPushButton("Aggregate…");
        rowAgg.addWidget(self.btnAgg); gbl.addLayout(rowAgg)

        gb_fmt = QGroupBox("Data Formatting"); pr.addWidget(gb_fmt)
        gbf = QVBoxLayout(gb_fmt); gbf.setContentsMargins(8,8,8,8); gbf.setSpacing(8)
        row3 = QHBoxLayout();
        self.btnTypes = QPushButton("Set Column Types");
        row3.addWidget(self.btnTypes); gbf.addLayout(row3)

        tabs.addTab(tab_proc, "Processing")

        # ================== TAB: EXPORT ==================
        tab_exp = QWidget()
        ex = QVBoxLayout(tab_exp); ex.setContentsMargins(8,8,8,8); ex.setSpacing(8)
        self.btnExport      = QPushButton("Save Image (PNG)"); ex.addWidget(self.btnExport)
        self.btnExportRange = QPushButton("Export Visible Range (CSV)"); ex.addWidget(self.btnExportRange)
        self.btnExportAgg   = QPushButton("Export Aggregated CSV"); ex.addWidget(self.btnExportAgg)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        ex.addWidget(sep)

        self.btnExportReport = QPushButton("Export Report (PDF)"); ex.addWidget(self.btnExportReport)

        tabs.addTab(tab_exp, "Export")

        # ---------- mount ----------
        r.addWidget(tabs)
        self._mount_layer_manager()
        return

    def _mount_layer_manager(self):
        layout = getattr(self, 'layerGroupLayout', None)
        if layout is None:
            return
        # Clear current widget(s) inside container
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                try:
                    widget.hide()
                except Exception:
                    pass
                widget.setParent(None)
        tab_widget = None
        try:
            tab_widget = self.tabs.currentWidget()
        except Exception:
            tab_widget = None
        if tab_widget and hasattr(tab_widget, 'layer_manager'):
            layer_widget = tab_widget.layer_manager
            try:
                layer_widget.setParent(self.layerGroup)
            except Exception:
                pass
            layout.addWidget(layer_widget)
            layer_widget.show()
        else:
            placeholder = getattr(self, '_layer_manager_empty', None)
            if placeholder is None:
                placeholder = QLabel('No layers yet', self.layerGroup if hasattr(self, 'layerGroup') else None)
                placeholder.setAlignment(Qt.AlignCenter)
                self._layer_manager_empty = placeholder
            try:
                placeholder.setParent(self.layerGroup)
            except Exception:
                pass
            layout.addWidget(placeholder)
            placeholder.show()

    def refresh_xy_columns(self):
        """
        โหลดคอลัมน์จาก DataFrame ปัจจุบัน → เติมลง cbo_x/cbo_y
        - คงค่าที่ผู้ใช้เลือกไว้ถ้ายังมีคอลัมน์นั้นอยู่
        - กรองเฉพาะคอลัมน์ตัวเลขสำหรับ Y
        - เดา X จากชื่อ time/t/timestamp/datetime ถ้ามี
        """
        try:
            from PySide6.QtCore import QSignalBlocker as _QSignalBlocker
        except Exception:
            _QSignalBlocker = None
        df = self._resolve_active_dataframe()
        if df is None or (hasattr(df, 'empty') and df.empty):
            QMessageBox.information(self, "No data", "No active data is available.")
            return

        cols = [str(c) for c in df.columns]
        try:
            num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
        except Exception:
            num_cols = cols[:]

        # Preserve old selection
        try:
            old_x = self.cbX.currentText().strip()
        except Exception:
            old_x = ""
        try:
            old_y = self.cbY.currentText().strip()
        except Exception:
            old_y = ""

        # Fill combos with signal blocking
        if _QSignalBlocker is not None:
            try:
                with _QSignalBlocker(self.cbX), _QSignalBlocker(self.cbY):
                    self.cbX.clear(); self.cbY.clear()
                    self.cbX.addItems(cols)
                    self.cbY.addItems(num_cols if num_cols else cols)
            except Exception:
                self.cbX.clear(); self.cbY.clear()
                self.cbX.addItems(cols)
                self.cbY.addItems(num_cols if num_cols else cols)
        else:
            self.cbX.clear(); self.cbY.clear()
            self.cbX.addItems(cols)
            self.cbY.addItems(num_cols if num_cols else cols)
        # Restore X if possible; else guess by time-like names
        idx = self.cbX.findText(old_x) if old_x else -1
        if idx >= 0:
            self.cbX.setCurrentIndex(idx)
        else:
            t_candidates = [c for c in cols if any(k in str(c).lower() for k in ("time","t","timestamp","datetime"))]
            self.cbX.setCurrentText(t_candidates[0] if t_candidates else (num_cols[0] if num_cols else cols[0]))

        # Restore Y if possible; else first numeric not equal to X
        idy = self.cbY.findText(old_y) if old_y else -1
        if idy >= 0:
            self.cbY.setCurrentIndex(idy)
        else:
            try:
                pref = [c for c in num_cols if c != self.cbX.currentText()]
                self.cbY.setCurrentText(pref[0] if pref else (num_cols[0] if num_cols else cols[0]))
            except Exception:
                if cols:
                    self.cbY.setCurrentText(cols[0])

        # Status/labels
        try:
            rows_count = len(df)
            cols_count = len(df.columns)
            try:
                self._sb_rows.setText(f"rows: {rows_count:,}")
            except Exception:
                pass
            self.statusBar().showMessage(f"Loaded columns: rows={rows_count:,}, cols={cols_count}")
        except Exception:
            pass

    def apply_sidepanel_style(self):
        """Assign object names, classes, sizes, and shadows to the left side panel."""
        try:
            # Container name for QSS scoping
            self._panel_left.setObjectName("SidePanel")

            # Buttons sizing + class names
            for btn, cls in (
                (self.btnOpenData, "btn-primary"),
                (self.btnUseSheet, "btn-secondary"),
                (self.btnBoxZoom, "btn-secondary"),
            ):
                try:
                    btn.setProperty("class", cls)
                    btn.setMinimumHeight(34)
                    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    # Allow shrink so three can fit on narrow sidebars
                    try:
                        btn.setMinimumWidth(0)
                    except Exception:
                        pass
                except Exception:
                    pass
            # Button/checkbox readable Thai/English labels
            try:
                self.btnBoxZoom.setText("Box Zoom (drag to zoom)")
                self.chkCross.setText("Show Crosshair")
            except Exception:
                pass

            # Card-like frames: add class and shadow, adjust padding
            try:
                cards = self._panel_left.findChildren(QGroupBox)
                for card in cards:
                    try:
                        card.setProperty("class", "card")
                        lay = card.layout()
                        if lay:
                            lay.setContentsMargins(12, 12, 12, 12)
                            lay.setSpacing(10)
                        # Subtle drop shadow
                        eff = QGraphicsDropShadowEffect(card)
                        eff.setColor(Qt.black)
                        eff.setBlurRadius(18)
                        eff.setOffset(0, 2)
                        card.setGraphicsEffect(eff)
                    except Exception:
                        pass
                # Titles are set at construction (numbered workflow steps) —
                # do not overwrite them here.
            except Exception:
                pass
        except Exception:
            pass
