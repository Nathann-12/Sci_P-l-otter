from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QGroupBox, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QCheckBox, QComboBox, QSpinBox, QFrame, QStyle, QSizePolicy,
    QGraphicsDropShadowEffect, QMessageBox, QTabWidget, QWidget,
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

        # ── ① ข้อมูล ────────────────────────────────────────────────
        # Origin model: เปิดไฟล์ = Book ใหม่; รายชื่อชุดข้อมูลดูที่ Project
        # Explorer (ไม่มี staging list อีกแล้ว)
        gb_data = QGroupBox("① ข้อมูล")
        gbd = QVBoxLayout(gb_data); gbd.setContentsMargins(8, 8, 8, 8); gbd.setSpacing(8)
        self.btnOpenData = QPushButton("เปิดไฟล์ข้อมูล…")
        self.btnOpenData.setToolTip("CSV / TSV / TXT / Excel / NetCDF / CDF — เปิดเป็น Book ใหม่")
        gbd.addWidget(self.btnOpenData)
        self.btnUseSheet = QPushButton("ใช้ข้อมูลจากตาราง (Book)")
        self.btnUseSheet.setToolTip("พิมพ์ข้อมูลลง Book แล้วกดปุ่มนี้เพื่อนำมาพล็อต/วิเคราะห์")
        gbd.addWidget(self.btnUseSheet)
        self.lblFile = QLabel("ยังไม่ได้เปิดไฟล์"); self.lblFile.setWordWrap(True)
        gbd.addWidget(self.lblFile)
        l.addWidget(gb_data)

        # ── Origin loop: การพล็อตทำผ่าน worksheet + แถบไอคอนพล็อตล่างแล้ว ──
        # CompactPlotPanel เหลือหน้าที่เป็น hidden state-holder เท่านั้น เพื่อรักษา
        # aliases (cbX/cbY/spLineWidth/...) ที่ mixin อื่นอ่าน/เขียนทั้งหมด
        # (หนี้เทคนิค: ถอด cbX ออกจาก logic จริงเป็นงานรีแฟคเตอร์รอบหน้า)
        panel = CompactPlotPanel(self)
        panel.hide()

        # aliases เดิม — โค้ด mixin อื่นเรียกผ่านชื่อพวกนี้ทั้งหมด
        self.panel_plot = panel
        self.btnLoadCols = getattr(panel, "btnLoadCols", getattr(panel, "btn_load_cols", None))
        self.cbX         = panel.cbo_x
        self.cbY         = panel.cbo_y
        self.spLineWidth = panel.spin_width
        self.chkMarker   = panel.chk_points
        self.btnLine     = panel.btn_line
        self.btnScatter  = panel.btn_scatter
        self.btnClear    = panel.btn_clear
        self.btnCurveFit = panel.btn_fit

        # ── ③ เครื่องมือกราฟ ───────────────────────────────────────
        gb_tools = QGroupBox("③ เครื่องมือกราฟ")
        gbt = QVBoxLayout(gb_tools); gbt.setContentsMargins(8, 8, 8, 8); gbt.setSpacing(8)
        self.chkCross = QCheckBox("แสดง Crosshair")
        gbt.addWidget(self.chkCross)
        self.btnBoxZoom = QPushButton("เลือกช่วง (ลากเพื่อซูม)")
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
            self.spLineWidth = panel.spin_width
            self.chkMarker   = panel.chk_points
            self.btnLine     = panel.btn_line
            self.btnScatter  = panel.btn_scatter
            self.btnClear    = panel.btn_clear
            self.btnCurveFit = panel.btn_fit
        self.layerGroup = QGroupBox("Layers", self)
        self.layerGroupLayout = QVBoxLayout(self.layerGroup)
        self.layerGroupLayout.setContentsMargins(6, 6, 6, 6)
        self.layerGroupLayout.setSpacing(6)
        self._layer_manager_empty = QLabel("ยังไม่มีเลเยอร์", self.layerGroup)
        self._layer_manager_empty.setAlignment(Qt.AlignCenter)
        self.layerGroupLayout.addWidget(self._layer_manager_empty)
        tp.addWidget(self.layerGroup)

        tabs.addTab(tab_plot, "Plot")

        # ================== TAB: PROCESSING ==================
        tab_proc = QWidget()
        pr = QVBoxLayout(tab_proc); pr.setContentsMargins(8,8,8,8); pr.setSpacing(8)

        gb_feat = QGroupBox("ฟีเจอร์เสริม"); pr.addWidget(gb_feat)
        gbl = QVBoxLayout(gb_feat); gbl.setContentsMargins(8,8,8,8); gbl.setSpacing(8)
        row1 = QHBoxLayout();
        self.btnTZ  = QPushButton("เพิ่มคอลัมน์เวลา +7h (Bangkok)");
        self.btnMag = QPushButton("เพิ่มคอลัมน์ |B| จาก 3 แกน");
        row1.addWidget(self.btnTZ); row1.addWidget(self.btnMag); gbl.addLayout(row1)
        row2 = QHBoxLayout();
        self.btnMA  = QPushButton("เพิ่มคอลัมน์ Moving Average (จาก Y)");
        row2.addWidget(self.btnMA); gbl.addLayout(row2)
        rowAgg = QHBoxLayout();
        self.btnAgg = QPushButton("Aggregate…");
        rowAgg.addWidget(self.btnAgg); gbl.addLayout(rowAgg)

        gb_fmt = QGroupBox("การจัดรูปแบบข้อมูล"); pr.addWidget(gb_fmt)
        gbf = QVBoxLayout(gb_fmt); gbf.setContentsMargins(8,8,8,8); gbf.setSpacing(8)
        row3 = QHBoxLayout();
        self.btnTypes = QPushButton("กำหนดชนิดคอลัมน์");
        row3.addWidget(self.btnTypes); gbf.addLayout(row3)

        tabs.addTab(tab_proc, "Processing")

        # ================== TAB: EXPORT ==================
        tab_exp = QWidget()
        ex = QVBoxLayout(tab_exp); ex.setContentsMargins(8,8,8,8); ex.setSpacing(8)
        self.btnExport      = QPushButton("บันทึกรูปภาพ (PNG)"); ex.addWidget(self.btnExport)
        self.btnExportRange = QPushButton("ส่งออกช่วงที่เห็น (CSV)"); ex.addWidget(self.btnExportRange)
        self.btnExportAgg   = QPushButton("Export Aggregated CSV"); ex.addWidget(self.btnExportAgg)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        ex.addWidget(sep)

        self.btnExportReport = QPushButton("Export Report (PDF)"); ex.addWidget(self.btnExportReport)

        tabs.addTab(tab_exp, "Export")

        # ---------- mount ----------
        r.addWidget(tabs)
        self._mount_layer_manager()
        return
        # Legacy load-cols and X/Y controls are replaced by CompactPlotPanel; do not add duplicates
        # self.btnLoadCols = QPushButton("โหลดคอลัมน์จากข้อมูล")
        # tp.addWidget(self.btnLoadCols)
        # tp.addWidget(QLabel("เลือกคอลัมน์แกน X")); self.cbX = QComboBox(); tp.addWidget(self.cbX)
        # tp.addWidget(QLabel("เลือกคอลัมน์แกน Y")); self.cbY = QComboBox(); tp.addWidget(self.cbY)
        styleRow = QHBoxLayout(); styleRow.addWidget(QLabel("ความหนาเส้น")); self.spLineWidth = QSpinBox(); self.spLineWidth.setRange(1,10); self.spLineWidth.setValue(2); styleRow.addWidget(self.spLineWidth); tp.addLayout(styleRow)
        markerRow = QHBoxLayout(); self.chkMarker = QCheckBox("แสดงจุดข้อมูล"); self.chkMarker.setChecked(False); markerRow.addWidget(self.chkMarker); markerRow.addStretch(1); tp.addLayout(markerRow)
        btnRow = QHBoxLayout(); self.btnLine = QPushButton("แสดงกราฟเส้น"); self.btnScatter = QPushButton("แสดงกราฟจุด (Scatter)"); btnRow.addWidget(self.btnLine); btnRow.addWidget(self.btnScatter); tp.addLayout(btnRow)
        # UI-REFINE: ปุ่มล้างกราฟ (Clear Plot)
        # UI-FIT: ปุ่ม Curve Fit
        self.btnCurveFit = QPushButton("Curve Fit…"); tp.addWidget(self.btnCurveFit)
        # UI-SPECTROGRAM: ปุ่ม Spectrogram
        self.btnSpectrogram = QPushButton("Spectrogram…"); tp.addWidget(self.btnSpectrogram)
        # UI-REFINE: Histogram controls
        tp.addWidget(QLabel("Histogram"))
        rowH1 = QHBoxLayout(); tp.addLayout(rowH1)
        rowH1.addWidget(QLabel("คอลัมน์")); self.cbHist = QComboBox(); rowH1.addWidget(self.cbHist)
        rowH1.addWidget(QLabel("bins")); self.spHistBins = QSpinBox(); self.spHistBins.setRange(5, 200); self.spHistBins.setValue(20); rowH1.addWidget(self.spHistBins)
        rowH2 = QHBoxLayout(); self.chkHistFit = QCheckBox("Fit Normal curve"); self.btnHist = QPushButton("Plot Histogram"); rowH2.addWidget(self.chkHistFit); rowH2.addStretch(1); rowH2.addWidget(self.btnHist); tp.addLayout(rowH2)
        tabs.addTab(tab_plot, "Plot")
        # Inject compact plot panel and remap references before signals are connected
        try:
            _panel = CompactPlotPanel(self)
            # Replace legacy widget refs with compact ones for downstream logic
            self.btnLoadCols = _panel.btnLoadCols
            self.cbX = _panel.cbo_x
            self.cbY = _panel.cbo_y
            self.spLineWidth = _panel.spin_width
            self.chkMarker = _panel.chk_points
            self.btnLine = _panel.btn_line
            self.btnScatter = _panel.btn_scatter
            self.btnClear = _panel.btn_clear
            self.btnCurveFit = _panel.btn_fit
            # Place compact panel at top
            try:
                tp.insertWidget(0, _panel)
            except Exception:
                tp.addWidget(_panel)
            try:
                self.btnLoadCols.raise_()
            except Exception:
                pass
            # Remove legacy controls in Plot tab that are not inside CompactPlotPanel
            try:
                from PySide6.QtWidgets import QPushButton as _QB, QComboBox as _QCB, QSpinBox as _QSB, QCheckBox as _QCK, QLabel as _QL
                def _remove_if_not_in_panel(widget):
                    try:
                        if _panel.isAncestorOf(widget):
                            return
                    except Exception:
                        return
                    try:
                        parent = widget.parent()
                        widget.setParent(None)
                        widget.deleteLater()
                        if parent and hasattr(parent, 'update'):
                            parent.update()
                    except Exception:
                        pass
                for cls in (_QB, _QCB, _QSB, _QCK, _QL):
                    for w in tab_plot.findChildren(cls):
                        _remove_if_not_in_panel(w)
            except Exception:
                pass
        except Exception:
            pass
        # Hide Spectrogram/Histogram controls in Plot tab (moved to Analysis dialogs)
        try:
            if hasattr(self, 'btnSpectrogram'): self.btnSpectrogram.setVisible(False)
            if hasattr(self, 'cbHist'): self.cbHist.setVisible(False)
            if hasattr(self, 'spHistBins'): self.spHistBins.setVisible(False)
            if hasattr(self, 'chkHistFit'): self.chkHistFit.setVisible(False)
            if hasattr(self, 'btnHist'): self.btnHist.setVisible(False)
            # Hide the 'Histogram' title label if present
            for _lbl in tab_plot.findChildren(QLabel):
                try:
                    if str(_lbl.text()).strip().lower() == "histogram":
                        _lbl.setVisible(False)
                except Exception:
                    pass
        except Exception:
            pass
        # Tab: Processing
        tab_proc = QWidget(); pr = QVBoxLayout(tab_proc)
        # CHANGE: กล่อง "ฟีเจอร์เสริม"
        gb_feat = QGroupBox("ฟีเจอร์เสริม"); gbl = QVBoxLayout(gb_feat); gbl.setContentsMargins(8,8,8,8); gbl.setSpacing(8)
        row1 = QHBoxLayout(); self.btnTZ = QPushButton("เพิ่มคอลัมน์เวลา +7h (Bangkok)"); self.btnMag = QPushButton("เพิ่มคอลัมน์ |B| จาก 3 แกน"); row1.addWidget(self.btnTZ); row1.addWidget(self.btnMag); gbl.addLayout(row1)
        row2 = QHBoxLayout(); self.btnMA = QPushButton("เพิ่มคอลัมน์ Moving Average (จาก Y)"); row2.addWidget(self.btnMA); gbl.addLayout(row2)
        rowAgg = QHBoxLayout(); self.btnAgg = QPushButton("Aggregate…"); rowAgg.addWidget(self.btnAgg); gbl.addLayout(rowAgg)
        pr.addWidget(gb_feat)
        # CHANGE: กล่อง "การจัดรูปแบบข้อมูล"
        gb_fmt = QGroupBox("การจัดรูปแบบข้อมูล"); gbf = QVBoxLayout(gb_fmt); gbf.setContentsMargins(8,8,8,8); gbf.setSpacing(8)
        row3 = QHBoxLayout(); self.btnTypes = QPushButton("กำหนดชนิดคอลัมน์"); row3.addWidget(self.btnTypes); gbf.addLayout(row3)
        pr.addWidget(gb_fmt)
        tabs.addTab(tab_proc, "Processing")
        # Tab: Export
        tab_exp = QWidget(); ex = QVBoxLayout(tab_exp)
        self.btnExport = QPushButton("บันทึกรูปภาพ (PNG)"); ex.addWidget(self.btnExport)
        self.btnExportRange = QPushButton("ส่งออกช่วงที่เห็น (CSV)"); ex.addWidget(self.btnExportRange)
        # UI-REFINE: ปุ่ม Export ผล Aggregate เป็น CSV
        self.btnExportAgg = QPushButton("Export Aggregated CSV")
        ex.addWidget(self.btnExportAgg)

        # เพิ่มเส้นแบ่ง
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        ex.addWidget(separator)

        # ปุ่ม Export Report เป็น PDF
        self.btnExportReport = QPushButton("Export Report (PDF)")
        ex.addWidget(self.btnExportReport)
        tabs.addTab(tab_exp, "Export")
        # CHANGE: ตั้งไอคอนแท็บ
        try:
            tabs.setTabIcon(0, self._icon("plot", QStyle.StandardPixmap.SP_FileDialogContentsView))
            tabs.setTabIcon(1, self._icon("settings", QStyle.StandardPixmap.SP_FileDialogDetailedView))
            tabs.setTabIcon(2, self._icon("export", QStyle.StandardPixmap.SP_DialogSaveButton))
        except Exception:
            pass
        r.addWidget(tabs)
        # Remove legacy Spectrogram/Histogram controls from Plot tab and tighten layout
        try:
            self._post_build_cleanup_plot_panel(tab_plot)
        except Exception:
            pass

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
                placeholder = QLabel('ยังไม่มีเลเยอร์', self.layerGroup if hasattr(self, 'layerGroup') else None)
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
        # Resolve current DataFrame
        df = getattr(self, 'current_df', None)
        if df is None or (hasattr(df, 'empty') and df.empty):
            df = getattr(self, '_df', None)
        if (df is None) or (hasattr(df, 'empty') and df.empty):
            # Try staging selection
            try:
                if hasattr(self, 'lstFiles') and hasattr(self, '_datasets'):
                    item = self.lstFiles.currentItem()
                    if item is not None:
                        data = self._datasets.get(item.text())
                        if data and isinstance(data.get('df'), pd.DataFrame):
                            df = data['df']
                            self._df = df.copy()
                            self._current_path = data.get('path')
            except Exception:
                pass
        if df is None or (hasattr(df, 'empty') and df.empty):
            QMessageBox.information(self, "No data", "ยังไม่มีข้อมูลที่ใช้งานอยู่")
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
        # Sync histogram column combo if present
        try:
            if hasattr(self, 'cbHist') and isinstance(self.cbHist, QComboBox):
                if _QSignalBlocker is not None:
                    with _QSignalBlocker(self.cbHist):
                        self.cbHist.clear(); self.cbHist.addItems(cols)
                else:
                    self.cbHist.clear(); self.cbHist.addItems(cols)
        except Exception:
            pass

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
                self.btnBoxZoom.setText("เลือกช่วง (ลากเพื่อซูม)")
                self.chkCross.setText("แสดง Crosshair")
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

    def _safe_remove_widget(self, w):
        try:
            if w is None:
                return
            w.hide()
            w.setParent(None)
            w.deleteLater()
        except Exception:
            pass

    def _post_build_cleanup_plot_panel(self, plot_widget):
        """Remove legacy Spectrogram/Histogram widgets from Plot tab and compact layout."""
        try:
            for name in ("btnSpectrogram", "cbHist", "spHistBins", "chkHistFit", "btnHist"):
                self._safe_remove_widget(getattr(self, name, None))
        except Exception:
            pass
        # Remove 'Histogram' label if present
        try:
            from PySide6.QtWidgets import QLabel
            for lbl in plot_widget.findChildren(QLabel):
                try:
                    t = str(lbl.text()).strip().lower()
                    if t.startswith("histogram") or t == "bins" or t == "คอลัมน์" or t == "คอลัมน์:" or t == "columns":
                        self._safe_remove_widget(lbl)
                except Exception:
                    pass
        except Exception:
            pass
        # Compact layout by removing invisible items and empty layouts
        try:
            lay = plot_widget.layout()
            def _prune(l):
                if l is None: return
                for i in reversed(range(l.count())):
                    it = l.itemAt(i)
                    # Remove nested layouts first
                    try:
                        child_lay = it.layout() if hasattr(it, 'layout') else None
                    except Exception:
                        child_lay = None
                    if child_lay is not None:
                        _prune(child_lay)
                        # if child layout empty (no visible widgets)
                        empty = True
                        for j in range(child_lay.count()):
                            it2 = child_lay.itemAt(j)
                            w2 = it2.widget() if hasattr(it2, 'widget') else None
                            if w2 is not None and w2.isVisible():
                                empty = False; break
                        if empty:
                            l.takeAt(i)
                            try:
                                child_lay.deleteLater()
                            except Exception:
                                pass
                        continue
                    # Remove hidden widgets
                    w = it.widget() if hasattr(it, 'widget') else None
                    if w is not None and not w.isVisible():
                        l.takeAt(i)
                return
            if lay is not None:
                _prune(lay)
        except Exception:
            pass

        # Make all buttons in Plot tab compact (avoid full-width expansion)
        try:
            from PySide6.QtWidgets import QPushButton
            btns = plot_widget.findChildren(QPushButton)
            for b in btns:
                try:
                    b.setMaximumWidth(220)
                    from PySide6.QtWidgets import QSizePolicy
                    b.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                except Exception:
                    pass
        except Exception:
            pass

        # Make input widgets (combos/spins/edits/labels) compact and left-aligned
        try:
            from PySide6.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QLabel
            from PySide6.QtCore import Qt
            MAX_W = 260
            # Direct children alignment to left
            def _align_left(w):
                try:
                    plot_widget.layout().setAlignment(w, Qt.AlignLeft)
                except Exception:
                    pass
            for w in plot_widget.findChildren(QComboBox):
                try:
                    w.setMaximumWidth(MAX_W); _align_left(w)
                except Exception:
                    pass
            for w in plot_widget.findChildren((QSpinBox, QDoubleSpinBox)):
                try:
                    w.setMaximumWidth(100); _align_left(w)
                except Exception:
                    pass
            for w in plot_widget.findChildren(QLineEdit):
                try:
                    w.setMaximumWidth(MAX_W); _align_left(w)
                except Exception:
                    pass
            # Keep labels from stretching across the panel
            for w in plot_widget.findChildren(QLabel):
                try:
                    if w.text().strip():
                        w.setMaximumWidth(MAX_W)
                except Exception:
                    pass
        except Exception:
            pass
