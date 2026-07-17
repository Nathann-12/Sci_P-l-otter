from __future__ import annotations

from dataclasses import replace
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
            QTabWidget, QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QPushButton,
            QFrame, QGridLayout, QComboBox, QScrollArea, QListWidget,
            QAbstractItemView,
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

        data_group = QGroupBox("Graph Data", self)
        data_layout = QGridLayout(data_group)
        data_layout.setContentsMargins(8, 14, 8, 8)
        data_layout.setHorizontalSpacing(6)
        data_layout.setVerticalSpacing(6)
        self.cboGraphDataX = QComboBox(data_group)
        self.cboGraphDataX.setToolTip(
            "Choose a real X column, or Row (1…N) for one-column data."
        )
        self.lstGraphDataY = QListWidget(data_group)
        self.lstGraphDataY.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lstGraphDataY.setMinimumHeight(72)
        self.lstGraphDataY.setMaximumHeight(130)
        self.lstGraphDataY.setToolTip(
            "Select one or many numeric Y columns (Ctrl/Shift-click for multiple)."
        )
        self.cboGraphDataStyle = QComboBox(data_group)
        for label, value in (
            ("Line", "line"),
            ("Line + Symbol", "linesymbol"),
            ("Scatter", "scatter"),
            ("Bar", "bar"),
        ):
            self.cboGraphDataStyle.addItem(label, value)
        self.btnGraphDataReplace = QPushButton("Replace Plot", data_group)
        self.btnGraphDataAdd = QPushButton("Add Series", data_group)
        self.btnGraphDataReplace.setToolTip(
            "Replace all layers in this Graph with the selected X/Y mapping."
        )
        self.btnGraphDataAdd.setToolTip(
            "Add all selected Y columns to this Graph in one render batch."
        )
        data_layout.addWidget(QLabel("X axis", data_group), 0, 0)
        data_layout.addWidget(self.cboGraphDataX, 0, 1)
        data_layout.addWidget(QLabel("Y data", data_group), 1, 0, Qt.AlignTop)
        data_layout.addWidget(self.lstGraphDataY, 1, 1)
        data_layout.addWidget(QLabel("Style", data_group), 2, 0)
        data_layout.addWidget(self.cboGraphDataStyle, 2, 1)
        button_row = QHBoxLayout()
        button_row.addWidget(self.btnGraphDataReplace)
        button_row.addWidget(self.btnGraphDataAdd)
        data_layout.addLayout(button_row, 3, 0, 1, 2)
        tp.addWidget(data_group)
        self.graphDataGroup = data_group
        self.btnGraphDataReplace.clicked.connect(
            lambda _=False: self._plot_graph_data_panel(add=False)
        )
        self.btnGraphDataAdd.clicked.connect(
            lambda _=False: self._plot_graph_data_panel(add=True)
        )

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

        render_group = QGroupBox("Large Data Rendering", self)
        render_layout = QGridLayout(render_group)
        render_layout.setContentsMargins(8, 14, 8, 8)
        render_layout.setHorizontalSpacing(6)
        render_layout.setVerticalSpacing(6)
        line_lod = QLabel("Line", render_group)
        line_policy = QLabel("Auto min-max LOD", render_group)
        line_policy.setToolTip(
            "Keeps peaks and spikes using about two samples per screen pixel; statistics use full data."
        )
        self.cboBarReducer = QComboBox(render_group)
        self.cboBarReducer.addItem("Sum per pixel", "sum")
        self.cboBarReducer.addItem("Mean per pixel", "mean")
        self.cboBarReducer.addItem("Off (all bars)", "none")
        self.cboBarReducer.setToolTip(
            "Explicit reducer used only when several bars occupy one screen pixel."
        )
        self.cboScatterRender = QComboBox(render_group)
        self.cboScatterRender.addItem("Auto", "auto")
        self.cboScatterRender.addItem("Points", "points")
        self.cboScatterRender.addItem("Density", "density")
        self.cboScatterRender.setToolTip(
            "Auto rasterizes large point clouds and switches very large clouds to hex density."
        )
        render_layout.addWidget(line_lod, 0, 0)
        render_layout.addWidget(line_policy, 0, 1)
        render_layout.addWidget(QLabel("Bars", render_group), 1, 0)
        render_layout.addWidget(self.cboBarReducer, 1, 1)
        render_layout.addWidget(QLabel("Scatter", render_group), 2, 0)
        render_layout.addWidget(self.cboScatterRender, 2, 1)
        current_options = getattr(self, "_plot_options", None)
        for combo, value in (
            (self.cboBarReducer, getattr(current_options, "bar_reducer", "sum")),
            (self.cboScatterRender, getattr(current_options, "scatter_mode", "auto")),
        ):
            index = combo.findData(value)
            combo.setCurrentIndex(max(0, index))
        self.cboBarReducer.currentIndexChanged.connect(self._update_render_options)
        self.cboScatterRender.currentIndexChanged.connect(self._update_render_options)
        tp.addWidget(render_group)

        tabs.addTab(tab_plot, "Plot")

        # ================== TAB: PROCESSING ==================
        tab_proc = QWidget()
        tab_proc.setObjectName("ProcessingInspector")
        tab_proc_layout = QVBoxLayout(tab_proc)
        tab_proc_layout.setContentsMargins(0, 0, 0, 0)

        proc_scroll = QScrollArea(tab_proc)
        proc_scroll.setObjectName("ProcessingScroll")
        proc_scroll.setWidgetResizable(True)
        proc_scroll.setFrameShape(QFrame.NoFrame)
        proc_content = QWidget(proc_scroll)
        proc_content.setObjectName("ProcessingContent")
        pr = QVBoxLayout(proc_content)
        pr.setContentsMargins(10, 10, 10, 12)
        pr.setSpacing(10)

        def _compact_group(title: str) -> tuple[QGroupBox, QGridLayout]:
            group = QGroupBox(title, proc_content)
            group.setObjectName("ProcessingGroup")
            group.setProperty("class", "card")
            group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            grid = QGridLayout(group)
            grid.setContentsMargins(8, 14, 8, 8)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            return group, grid

        def _proc_button(text: str, tooltip: str, *, primary: bool = False) -> QPushButton:
            button = QPushButton(text, proc_content)
            button.setProperty("class", "btn-primary" if primary else "btn-secondary")
            button.setToolTip(tooltip)
            button.setMinimumHeight(32)
            return button

        # Context first: every processing command has an explicit Book/target.
        context_card = QFrame(proc_content)
        context_card.setObjectName("ProcessingContextCard")
        context_card.setProperty("class", "card")
        context_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        context_layout = QVBoxLayout(context_card)
        context_layout.setContentsMargins(10, 9, 10, 10)
        context_layout.setSpacing(5)
        context_eyebrow = QLabel("ACTIVE DATA", context_card)
        context_eyebrow.setObjectName("ProcessingEyebrow")
        self.procBookLabel = QLabel("No active data", context_card)
        self.procBookLabel.setObjectName("ProcessingBookLabel")
        self.procBookLabel.setWordWrap(True)
        self.procDataSummary = QLabel("Open a file or use worksheet data to begin.", context_card)
        self.procDataSummary.setObjectName("ProcessingDataSummary")
        self.procDataSummary.setWordWrap(True)
        target_row = QHBoxLayout()
        self.procXLabel = QLabel("X / time: -", context_card)
        self.procXLabel.setObjectName("ProcessingXLabel")
        target_label = QLabel("Target Y", context_card)
        target_label.setObjectName("ProcessingTargetLabel")
        self.procColumnCombo = QComboBox(context_card)
        self.procColumnCombo.setObjectName("ProcessingColumnCombo")
        self.procColumnCombo.setToolTip(
            "The numeric column used by moving average, normalize, detrend, and outlier tools."
        )
        target_row.addWidget(target_label)
        target_row.addWidget(self.procColumnCombo, 1)
        self.procQualityLabel = QLabel("Missing: -   Duplicates: -", context_card)
        self.procQualityLabel.setObjectName("ProcessingQualityLabel")
        context_layout.addWidget(context_eyebrow)
        context_layout.addWidget(self.procBookLabel)
        context_layout.addWidget(self.procDataSummary)
        context_layout.addWidget(self.procXLabel)
        context_layout.addLayout(target_row)
        context_layout.addWidget(self.procQualityLabel)
        pr.addWidget(context_card)

        clean_group, clean_grid = _compact_group("Clean rows")
        self.btnRemoveMissing = _proc_button(
            "Missing rows...", "Remove rows containing missing values. This operation can be undone."
        )
        self.btnRemoveDuplicates = _proc_button(
            "Duplicates", "Remove duplicate rows. This operation can be undone."
        )
        self.btnOutliers = _proc_button(
            "Outliers...", "Remove target-column outliers. This operation can be undone."
        )
        self.btnCrop = _proc_button(
            "Crop range...", "Keep rows inside a numeric range. This operation can be undone."
        )
        clean_grid.addWidget(self.btnRemoveMissing, 0, 0)
        clean_grid.addWidget(self.btnRemoveDuplicates, 0, 1)
        clean_grid.addWidget(self.btnOutliers, 1, 0)
        clean_grid.addWidget(self.btnCrop, 1, 1)
        pr.addWidget(clean_group)

        transform_group, transform_grid = _compact_group("Transform column")
        self.btnMA = _proc_button(
            "Moving average...", "Create a moving-average column from the selected target.", primary=True
        )
        self.btnNormalize = _proc_button(
            "Normalize...", "Create a normalized or standardized target column."
        )
        self.btnDetrend = _proc_button(
            "Detrend...", "Remove a fitted baseline from the selected target column."
        )
        self.btnDerived = _proc_button(
            "Derived column...", "Create a new column from a mathematical expression."
        )
        self.btnTypes = _proc_button(
            "Column types...", "Convert columns to numeric, datetime, string, or automatic types."
        )
        transform_grid.addWidget(self.btnMA, 0, 0, 1, 2)
        transform_grid.addWidget(self.btnNormalize, 1, 0)
        transform_grid.addWidget(self.btnDetrend, 1, 1)
        transform_grid.addWidget(self.btnDerived, 2, 0)
        transform_grid.addWidget(self.btnTypes, 2, 1)
        pr.addWidget(transform_group)

        domain_group, domain_grid = _compact_group("Time & vector")
        self.btnTZ = _proc_button(
            "Bangkok time", "Create a UTC+7 datetime column from the selected time column."
        )
        self.btnMag = _proc_button(
            "Vector |B|...", "Create vector magnitude from three selected axis columns."
        )
        domain_grid.addWidget(self.btnTZ, 0, 0)
        domain_grid.addWidget(self.btnMag, 0, 1)
        pr.addWidget(domain_group)

        summary_group, summary_grid = _compact_group("Summarize")
        self.btnAgg = _proc_button("Aggregate...", "Group rows and calculate summary values.")
        self.btnProcStats = _proc_button("Statistics", "Show statistics for the active Book.")
        summary_grid.addWidget(self.btnAgg, 0, 0)
        summary_grid.addWidget(self.btnProcStats, 0, 1)
        pr.addWidget(summary_group)

        self.btnProcUndo = _proc_button(
            "Undo last data change", "Restore the last destructive clean operation."
        )
        self.btnProcUndo.setObjectName("ProcessingUndoButton")
        pr.addWidget(self.btnProcUndo)
        self.procStatusLabel = QLabel("Open data to enable processing tools.", proc_content)
        self.procStatusLabel.setObjectName("ProcessingStatusLabel")
        self.procStatusLabel.setWordWrap(True)
        pr.addWidget(self.procStatusLabel)
        pr.addStretch(1)

        self._processing_data_buttons = [
            self.btnRemoveMissing, self.btnRemoveDuplicates, self.btnOutliers,
            self.btnCrop, self.btnMA, self.btnNormalize, self.btnDetrend,
            self.btnDerived, self.btnTypes, self.btnTZ, self.btnMag, self.btnAgg,
            self.btnProcStats,
        ]
        self.procColumnCombo.currentTextChanged.connect(self._on_processing_target_changed)
        x_combo = getattr(self, "cbX", None)
        if x_combo is not None:
            x_combo.currentTextChanged.connect(
                lambda value: self.procXLabel.setText(f"X / time: {value or '-'}")
            )
        self.btnRemoveMissing.clicked.connect(self.feature_clean_remove_nan)
        self.btnRemoveDuplicates.clicked.connect(self.feature_clean_remove_duplicates)
        self.btnOutliers.clicked.connect(self.feature_clean_remove_outliers)
        self.btnCrop.clicked.connect(self.feature_clean_crop_range)
        self.btnNormalize.clicked.connect(self.feature_clean_normalize)
        self.btnDetrend.clicked.connect(self.feature_clean_detrend)
        self.btnDerived.clicked.connect(self.open_derived_column_dialog)
        self.btnProcStats.clicked.connect(self.feature_show_statistics)
        self.btnProcUndo.clicked.connect(self.undo_last_dataframe_change)

        proc_scroll.setWidget(proc_content)
        tab_proc_layout.addWidget(proc_scroll)
        self.processingScroll = proc_scroll
        self._refresh_processing_context()

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
        self.inspectorTabs = tabs
        self._mount_layer_manager()
        return

    def _refresh_graph_data_panel(self) -> None:
        """Populate the graph mapping controls from the active Book."""
        x_combo = getattr(self, "cboGraphDataX", None)
        y_list = getattr(self, "lstGraphDataY", None)
        if x_combo is None or y_list is None:
            return
        resolver = getattr(self, "_resolve_active_dataframe", None)
        df = resolver() if callable(resolver) else getattr(self, "_df", None)
        previous_x = x_combo.currentData()
        previous_y = {item.text() for item in y_list.selectedItems()}
        x_combo.clear()
        y_list.clear()
        x_combo.addItem("Row (1…N)", None)

        has_data = isinstance(df, pd.DataFrame) and not df.empty
        if not has_data:
            x_combo.setEnabled(False)
            y_list.setEnabled(False)
            self.btnGraphDataReplace.setEnabled(False)
            self.btnGraphDataAdd.setEnabled(False)
            return

        x_columns = [
            str(column)
            for column in df.columns
            if pd.api.types.is_numeric_dtype(df[column])
            or pd.api.types.is_datetime64_any_dtype(df[column])
        ]
        y_columns = [
            str(column)
            for column in df.columns
            if pd.api.types.is_numeric_dtype(df[column])
        ]
        for column in x_columns:
            x_combo.addItem(column, column)
        for column in y_columns:
            y_list.addItem(column)

        if previous_x in x_columns:
            x_combo.setCurrentIndex(x_combo.findData(previous_x))
        else:
            # Row is intentionally the safe default: selecting one Y always
            # produces that column against 1…N without silently stealing X.
            x_combo.setCurrentIndex(0)

        preferred_y = set(previous_y)
        tab = getattr(getattr(self, "tabs", None), "currentWidget", lambda: None)()
        if not preferred_y and tab is not None:
            preferred_y = {
                str(info.get("meta", {}).get("y_column", ""))
                for info in getattr(tab, "layers", {}).values()
            }
        if not preferred_y:
            selected_y = getattr(self, "selected_y_column", lambda: "")()
            if selected_y:
                preferred_y = {str(selected_y)}
        selected_any = False
        for index in range(y_list.count()):
            item = y_list.item(index)
            selected = item.text() in preferred_y
            item.setSelected(selected)
            selected_any = selected_any or selected
        if not selected_any and y_list.count():
            y_list.item(0).setSelected(True)

        enabled = bool(y_columns)
        x_combo.setEnabled(True)
        y_list.setEnabled(enabled)
        self.btnGraphDataReplace.setEnabled(enabled)
        self.btnGraphDataAdd.setEnabled(enabled)

    def _plot_graph_data_panel(self, *, add: bool) -> dict | None:
        """Apply the visible X/multi-Y mapping to the current Graph."""
        tab = getattr(getattr(self, "tabs", None), "currentWidget", lambda: None)()
        if tab is None or not hasattr(tab, "get_axes"):
            self.inform("No graph", "Open or select a Graph first.")
            return None
        y_columns = [item.text() for item in self.lstGraphDataY.selectedItems()]
        if not y_columns:
            self.inform("Choose Y data", "Select at least one Y column.")
            return None
        x_column = self.cboGraphDataX.currentData()
        style = str(self.cboGraphDataStyle.currentData() or "line")
        try:
            result = self.plot_explicit_columns(
                style,
                str(x_column) if x_column is not None else None,
                y_columns,
                new_graph=False,
                replace_existing=not add,
            )
        except Exception as exc:
            self.inform("Could not update graph", str(exc))
            return None
        self._mount_layer_manager()
        return result

    def open_graph_data_panel(self) -> bool:
        """Reveal and focus Graph Data; used by canvas double-click."""
        tab = getattr(getattr(self, "tabs", None), "currentWidget", lambda: None)()
        if tab is None or not hasattr(tab, "get_axes"):
            self.inform("No graph", "Open or select a Graph first.")
            return False
        self.toggle_inspector(True)
        action = getattr(self, "actToggleInspector", None)
        if action is not None:
            action.setChecked(True)
        inspector_tabs = getattr(self, "inspectorTabs", None)
        if inspector_tabs is not None:
            inspector_tabs.setCurrentIndex(0)
        self._refresh_graph_data_panel()
        self.lstGraphDataY.setFocus()
        self.statusBar().showMessage(
            "Graph Data opened — choose Row or an X column, select one or more Y columns, then Add or Replace."
        )
        return True

    def _update_render_options(self, *_args) -> None:
        """Commit explicit large-data render policies to immutable options."""
        options = getattr(self, "_plot_options", None)
        if options is None:
            return
        try:
            self._plot_options = replace(
                options,
                bar_reducer=str(self.cboBarReducer.currentData() or "sum"),
                scatter_mode=str(self.cboScatterRender.currentData() or "auto"),
            )
        except Exception:
            pass

    def _on_processing_target_changed(self, column: str) -> None:
        """Keep the visible processing target and the app's active Y in sync."""
        column = str(column or "").strip()
        if not column:
            return
        combo = getattr(self, "cbY", None)
        if combo is not None:
            index = combo.findText(column)
            if index >= 0 and combo.currentIndex() != index:
                combo.setCurrentIndex(index)
        status = getattr(self, "procStatusLabel", None)
        if status is not None:
            status.setText(
                f"Ready to process '{column}'. Destructive clean actions can be undone."
            )

    def _refresh_processing_context(self) -> None:
        """Refresh Book context, quality summary, target columns, and enablement."""
        combo = getattr(self, "procColumnCombo", None)
        if combo is None:
            return
        df = getattr(self, "_df", None)
        if not isinstance(df, pd.DataFrame) or df.empty:
            source = getattr(getattr(self, "workbook", None), "source_df", None)
            df = source if isinstance(source, pd.DataFrame) and not source.empty else None

        has_data = isinstance(df, pd.DataFrame) and not df.empty
        for button in getattr(self, "_processing_data_buttons", []):
            button.setEnabled(has_data)
        undo_available = bool(getattr(self, "_dataframe_undo_stack", []))
        undo_button = getattr(self, "btnProcUndo", None)
        if undo_button is not None:
            undo_button.setEnabled(undo_available)

        from PySide6.QtCore import QSignalBlocker
        blocker = QSignalBlocker(combo)
        previous = combo.currentText().strip()
        combo.clear()
        if not has_data:
            combo.setEnabled(False)
            self.procBookLabel.setText("No active data")
            self.procDataSummary.setText(
                "Open a file or click Use Active Worksheet Data to begin."
            )
            self.procXLabel.setText("X / time: -")
            self.procQualityLabel.setText("Missing: -   Duplicates: -")
            self.procStatusLabel.setText(
                "Processing tools will enable when an active Book contains data."
            )
            del blocker
            return

        numeric = [
            str(column) for column in df.columns
            if pd.api.types.is_numeric_dtype(df[column])
        ]
        targets = numeric or [str(column) for column in df.columns]
        combo.addItems(targets)
        preferred = previous
        y_combo = getattr(self, "cbY", None)
        if not preferred and y_combo is not None:
            preferred = y_combo.currentText().strip()
        if preferred in targets:
            combo.setCurrentText(preferred)
        combo.setEnabled(bool(targets))

        workbook = getattr(self, "workbook", None)
        book_name = str(getattr(workbook, "dataset_name", "") or "Active Book")
        missing = int(df.isna().sum().sum())
        duplicates = int(df.duplicated().sum())
        self.procBookLabel.setText(book_name)
        self.procDataSummary.setText(
            f"{len(df):,} rows x {len(df.columns)} columns   |   {len(numeric)} numeric"
        )
        x_combo = getattr(self, "cbX", None)
        x_column = x_combo.currentText().strip() if x_combo is not None else ""
        self.procXLabel.setText(f"X / time: {x_column or '-'}")
        self.procQualityLabel.setText(
            f"Missing: {missing:,}   Duplicates: {duplicates:,}"
        )
        target = combo.currentText().strip()
        self.procStatusLabel.setText(
            f"Ready to process '{target}'. Destructive clean actions can be undone."
            if target else "Choose a target column to continue."
        )
        del blocker

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
        refresh_data = getattr(self, "_refresh_graph_data_panel", None)
        if callable(refresh_data):
            refresh_data()

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
