from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMessageBox, QMenu, QStyle

from core.plot_data import clamp_date_limits as _clamp_date_limits
from core.plot_mode import PlotMode
from widgets.chart_mega_menu import OriginChartMenu
from crosscorr import CrossCorrManager, CrossCorrDock
from peaks import PeakDetectorManager, PeakDetectionDock
from three_d_view import ThreeDViewDock
from annotations import AnnotationStyleDock, AnnotationListDialog

if TYPE_CHECKING:  # shared MainWindow state this mixin relies on (set in MainWindow.__init__)
    import pandas as _pd

    _df: "_pd.DataFrame | None"
    plot_mode: object
    settings: object


class MainWindowMenuMixin:
    """Menu-bar construction and wiring extracted from MainWindow."""

    def _add_data_action(
        self,
        menu,
        text: str,
        slot,
        *,
        shortcut: str | None = None,
        status_tip: str = "",
        icon_key: str | None = None,
        fallback_icon=QStyle.StandardPixmap.SP_FileIcon,
    ) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        if status_tip:
            action.setStatusTip(status_tip)
            action.setToolTip(status_tip)
        if icon_key:
            try:
                action.setIcon(self._icon(icon_key, fallback_icon))
            except Exception:
                logging.getLogger(__name__).debug(
                    "Data menu icon failed for %s", icon_key, exc_info=True
                )
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_data_menu(self) -> None:
        """Build the Data menu around worksheet tasks, not legacy leftovers."""
        data_menu = self.dataMenu
        data_menu.setObjectName("DataWorkflowMenu")
        try:
            data_menu.setToolTipsVisible(True)
        except Exception:
            pass

        active_menu = data_menu.addMenu("Active Book")
        self._add_data_action(
            active_menu,
            "Open Data File...",
            lambda: getattr(self, "open_file", lambda: None)(),
            shortcut="Ctrl+O",
            status_tip="Open a data file into a new Book window.",
            icon_key="open",
            fallback_icon=QStyle.StandardPixmap.SP_DialogOpenButton,
        )
        self._add_data_action(
            active_menu,
            "Batch Import Files...",
            lambda: getattr(self, "stage_add_files", lambda: None)(),
            status_tip="Open multiple files as separate Book windows.",
            icon_key="batch_import",
            fallback_icon=QStyle.StandardPixmap.SP_DirOpenIcon,
        )
        active_menu.addSeparator()
        self._add_data_action(
            active_menu,
            "Use Active Worksheet Data",
            self.adopt_workbook_data,
            shortcut="Ctrl+Shift+U",
            status_tip="Read the active Book into the working DataFrame.",
            icon_key="use_active_book",
            fallback_icon=QStyle.StandardPixmap.SP_DialogApplyButton,
        )
        self._add_data_action(
            active_menu,
            "Reload Column List",
            self.load_columns_from_df,
            status_tip="Refresh X/Y selectors and worksheet-derived column state.",
            icon_key="reload_columns",
            fallback_icon=QStyle.StandardPixmap.SP_BrowserReload,
        )
        active_menu.addSeparator()
        self._add_data_action(
            active_menu,
            "Duplicate Active Book...",
            self.feature_dataset_duplicate,
            status_tip="Create a separate copy of the active Book.",
            icon_key="dataset_duplicate",
            fallback_icon=QStyle.StandardPixmap.SP_FileDialogNewFolder,
        )
        self._add_data_action(
            active_menu,
            "Rename Active Book...",
            self.feature_dataset_rename,
            status_tip="Rename the active Book and project registry entry.",
            icon_key="dataset_rename",
            fallback_icon=QStyle.StandardPixmap.SP_FileDialogDetailedView,
        )

        columns_menu = data_menu.addMenu("Columns")
        if not hasattr(self, "_actDataDerived"):
            self._actDataDerived = QAction("Create Derived Column...", self)
            self._actDataDerived.setShortcut("Ctrl+Shift+D")
            self._actDataDerived.setStatusTip("Create a calculated column from an expression.")
            self._actDataDerived.setToolTip("Create a calculated column from an expression.")
            try:
                self._actDataDerived.setIcon(
                    self._icon("derived_column", QStyle.StandardPixmap.SP_FileDialogNewFolder)
                )
            except Exception:
                pass
            self._actDataDerived.triggered.connect(self.open_derived_column_dialog)
        columns_menu.addAction(self._actDataDerived)
        self._add_data_action(
            columns_menu,
            "Set Column Types...",
            self.feature_set_column_types,
            status_tip="Convert worksheet columns to numeric, datetime, string, or auto.",
            icon_key="column_types",
            fallback_icon=QStyle.StandardPixmap.SP_FileDialogDetailedView,
        )
        columns_menu.addSeparator()
        self._add_data_action(
            columns_menu,
            "Add Row to Active Book",
            lambda: getattr(getattr(self, "workbook", None), "add_data_row", lambda: None)(),
            status_tip="Append an empty row to the active worksheet.",
            icon_key="add_row",
            fallback_icon=QStyle.StandardPixmap.SP_ArrowDown,
        )
        self._add_data_action(
            columns_menu,
            "Add Column to Active Book",
            lambda: getattr(getattr(self, "workbook", None), "add_data_column", lambda: None)(),
            status_tip="Append an empty column to the active worksheet.",
            icon_key="add_column",
            fallback_icon=QStyle.StandardPixmap.SP_ArrowRight,
        )

        units_menu = data_menu.addMenu("Units + Metadata")
        self._add_data_action(
            units_menu,
            "Units + Calibration...",
            self.open_units_dialog,
            status_tip="Convert units and apply calibration into new worksheet columns.",
            icon_key="units_calibration",
            fallback_icon=QStyle.StandardPixmap.SP_FileDialogInfoView,
        )

        quick_menu = data_menu.addMenu("Quick Transforms")
        self._add_data_action(
            quick_menu,
            "Moving Average",
            self.feature_add_moving_average,
            status_tip="Create a rolling-average column from the active Y column.",
            icon_key="moving_average",
            fallback_icon=QStyle.StandardPixmap.SP_MediaSeekForward,
        )
        self._add_data_action(
            quick_menu,
            "Add |B|",
            self.feature_add_magnitude,
            status_tip="Create vector magnitude |B| from three selected components.",
            icon_key="magnitude",
            fallback_icon=QStyle.StandardPixmap.SP_DialogApplyButton,
        )
        self._add_data_action(
            quick_menu,
            "Add Bangkok Time",
            self.feature_add_bkk_time,
            status_tip="Create a Bangkok-time column from the active X/time column.",
            icon_key="bangkok_time",
            fallback_icon=QStyle.StandardPixmap.SP_ComputerIcon,
        )
        self._add_data_action(
            quick_menu,
            "Aggregate...",
            self.run_aggregate_dialog,
            status_tip="Aggregate worksheet rows by group/value columns.",
            icon_key="aggregate",
            fallback_icon=QStyle.StandardPixmap.SP_FileDialogListView,
        )

        books_menu = data_menu.addMenu("Books + Query")
        self._add_data_action(books_menu, "Group and Summarize...", self.feature_dataset_group)
        self._add_data_action(books_menu, "Merge Books...", self.feature_dataset_merge)
        self._add_data_action(books_menu, "Split Book...", self.feature_dataset_split)
        self._add_data_action(books_menu, "Filter Rows...", self.feature_dataset_filter)
        self._add_data_action(books_menu, "Search Book...", self.feature_dataset_search)

        clean_menu = data_menu.addMenu("Clean Data")
        self._add_data_action(clean_menu, "Fill Missing...", self.feature_clean_fill_missing)
        self._add_data_action(clean_menu, "Interpolate Missing", self.feature_clean_interpolate)
        self._add_data_action(clean_menu, "Remove Missing Rows...", self.feature_clean_remove_nan)
        self._add_data_action(clean_menu, "Remove Duplicates", self.feature_clean_remove_duplicates)
        self._add_data_action(clean_menu, "Remove Outliers...", self.feature_clean_remove_outliers)
        self._add_data_action(clean_menu, "Crop Range...", self.feature_clean_crop_range)
        self._add_data_action(clean_menu, "Normalize / Standardize...", self.feature_clean_normalize)
        self._add_data_action(clean_menu, "Detrend / Baseline...", self.feature_clean_detrend)
        self._add_data_action(clean_menu, "Sort...", self.feature_clean_sort)
        self._add_data_action(clean_menu, "Resample (uniform grid)...", self.feature_clean_resample)
        self._add_data_action(clean_menu, "Merge by Timestamp...", self.feature_clean_merge_by_timestamp)

    def _add_process_submenu(
        self,
        menu,
        title: str,
        *,
        icon_key: str | None = None,
        fallback_icon=QStyle.StandardPixmap.SP_DirIcon,
    ):
        submenu = menu.addMenu(title)
        if icon_key:
            try:
                submenu.menuAction().setIcon(self._icon(icon_key, fallback_icon))
            except Exception:
                logging.getLogger(__name__).debug(
                    "Process submenu icon failed for %s", icon_key, exc_info=True
                )
        return submenu

    def _add_process_action(
        self,
        menu,
        text: str,
        slot,
        *,
        icon_key: str | None = None,
        status_tip: str = "",
        fallback_icon=QStyle.StandardPixmap.SP_FileIcon,
    ) -> QAction:
        action = QAction(text, self)
        if icon_key:
            try:
                action.setIcon(self._icon(icon_key, fallback_icon))
            except Exception:
                logging.getLogger(__name__).debug(
                    "Process action icon failed for %s", icon_key, exc_info=True
                )
        if status_tip:
            action.setStatusTip(status_tip)
            action.setToolTip(status_tip)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_process_menu(self) -> None:
        """Build Process as task groups instead of a flat legacy command list."""
        proc_menu = self.processMenu
        proc_menu.setObjectName("ProcessWorkflowMenu")
        try:
            proc_menu.setToolTipsVisible(True)
        except Exception:
            pass

        quick_menu = self._add_process_submenu(proc_menu, "Quick Actions", icon_key="processors")
        self._add_process_action(
            quick_menu,
            "Moving Average",
            self.feature_add_moving_average,
            icon_key="moving_average",
            status_tip="Create a moving-average column from the active signal.",
        )
        self._add_process_action(
            quick_menu,
            "Add |B|",
            self.feature_add_magnitude,
            icon_key="magnitude",
            status_tip="Create vector magnitude |B| from selected components.",
        )
        self._add_process_action(
            quick_menu,
            "Add Bangkok Time",
            self.feature_add_bkk_time,
            icon_key="bangkok_time",
            status_tip="Create a UTC+7/Bangkok-time column from the active time column.",
        )
        self._add_process_action(
            quick_menu,
            "Aggregate...",
            self.run_aggregate_dialog,
            icon_key="aggregate",
            status_tip="Group worksheet rows and compute summary values.",
        )

        spectrum_menu = self._add_process_submenu(proc_menu, "Frequency & Spectrum", icon_key="fft")
        self._add_process_action(spectrum_menu, "FFT", self.run_fft_dialog, icon_key="fft")
        self._add_process_action(spectrum_menu, "PSD (Welch)...", self.run_psd_dialog, icon_key="psd")
        self._add_process_action(spectrum_menu, "STFT...", self.feature_signal_stft, icon_key="stft")
        self._add_process_action(spectrum_menu, "IFFT...", self.feature_signal_ifft, icon_key="ifft")
        self._add_process_action(
            spectrum_menu,
            "Harmonic Analysis...",
            self.feature_signal_harmonic_analysis,
            icon_key="harmonic",
        )

        filters_menu = self._add_process_submenu(proc_menu, "Smoothing & Filters", icon_key="smooth")
        self._add_process_action(filters_menu, "Moving Average", self.feature_add_moving_average, icon_key="moving_average")
        self._add_process_action(
            filters_menu,
            "Butterworth (Low/High/Band)...",
            self.feature_filter_butterworth,
            icon_key="butterworth",
        )
        self._add_process_action(
            filters_menu,
            "Smooth (Savitzky-Golay/Median/Gaussian)...",
            self.feature_filter_smooth,
            icon_key="smooth",
        )
        self._add_process_action(
            filters_menu,
            "Apply Window (Hann/Hamming/Blackman/Kaiser)...",
            self.feature_apply_window,
            icon_key="window_func",
        )
        self._add_process_action(filters_menu, "Decimation...", self.feature_signal_decimation, icon_key="decimation")

        transforms_menu = self._add_process_submenu(proc_menu, "Signal Transforms", icon_key="hilbert")
        self._add_process_action(transforms_menu, "Hilbert Transform...", self.feature_signal_hilbert, icon_key="hilbert")
        self._add_process_action(transforms_menu, "Envelope Detection...", self.feature_signal_envelope, icon_key="envelope")
        self._add_process_action(
            transforms_menu,
            "Instantaneous Frequency...",
            self.feature_signal_instantaneous_frequency,
            icon_key="instant_freq",
        )
        self._add_process_action(transforms_menu, "Zero Padding...", self.feature_signal_zero_pad, icon_key="zero_pad")

        corr_menu = self._add_process_submenu(proc_menu, "Correlation & Convolution", icon_key="autocorr")
        self._add_process_action(corr_menu, "Auto-correlation...", self.feature_signal_autocorrelation, icon_key="autocorr")
        self._add_process_action(corr_menu, "Convolution...", self.feature_signal_convolution, icon_key="convolution")
        self._add_process_action(corr_menu, "Deconvolution...", self.feature_signal_deconvolution, icon_key="deconvolution")

        clean_menu = self._add_process_submenu(proc_menu, "Clean & Prepare Data", icon_key="fill_missing")
        self._add_process_action(clean_menu, "Fill Missing...", self.feature_clean_fill_missing, icon_key="fill_missing")
        self._add_process_action(clean_menu, "Interpolate Missing", self.feature_clean_interpolate, icon_key="interpolate_missing")
        self._add_process_action(clean_menu, "Remove Missing Rows...", self.feature_clean_remove_nan, icon_key="remove_missing_rows")
        self._add_process_action(clean_menu, "Remove Duplicates", self.feature_clean_remove_duplicates, icon_key="remove_duplicates")
        self._add_process_action(clean_menu, "Remove Outliers...", self.feature_clean_remove_outliers, icon_key="remove_outliers")
        self._add_process_action(clean_menu, "Crop Range...", self.feature_clean_crop_range, icon_key="crop_range")
        self._add_process_action(clean_menu, "Normalize / Standardize...", self.feature_clean_normalize, icon_key="normalize")
        self._add_process_action(clean_menu, "Detrend / Baseline...", self.feature_clean_detrend, icon_key="detrend")
        self._add_process_action(clean_menu, "Sort...", self.feature_clean_sort, icon_key="sort")
        self._add_process_action(clean_menu, "Resample (uniform grid)...", self.feature_clean_resample, icon_key="resample")
        self._add_process_action(clean_menu, "Merge by Timestamp...", self.feature_clean_merge_by_timestamp, icon_key="time_merge")

        summary_menu = self._add_process_submenu(proc_menu, "Summarize & Aggregate", icon_key="aggregate")
        self._add_process_action(summary_menu, "Aggregate...", self.run_aggregate_dialog, icon_key="aggregate")
        self._add_process_action(summary_menu, "Descriptive Statistics...", self.feature_show_statistics, icon_key="stats")
        self._add_process_action(
            summary_menu,
            "Signal Quality (SNR / Noise floor)...",
            self.feature_signal_quality,
            icon_key="signal_quality",
        )

    def _init_menu(self):
        m = self.menuBar()
        fileMenu = m.addMenu("&File")  # UI-REFINE: File
        self.actOpen = fileMenu.addAction("Open Data (CSV/Excel/JSON/HDF5/MAT/XML/NC/CDF)...")
        self.actOpen.triggered.connect(lambda: getattr(self, 'open_file', lambda: None)())
        actBatch = fileMenu.addAction("Open Multiple Files (Batch Import)…")
        actBatch.triggered.connect(lambda: getattr(self, 'stage_add_files', lambda: None)())
        fileMenu.addSeparator()
        # Project files (*.sciproj) — self-contained: data + graphs + styles
        actOpenProj = fileMenu.addAction("Open Project… (*.sciproj)")
        actOpenProj.setShortcut("Ctrl+Shift+O")
        actOpenProj.triggered.connect(self.open_project)
        actSaveProj = fileMenu.addAction("Save Project… (*.sciproj)")
        actSaveProj.setShortcut("Ctrl+S")
        actSaveProj.triggered.connect(self.save_project_as)
        fileMenu.addSeparator()
        # Export PNG lives in the Export menu (not duplicated here — on_action_export_figure calls the same export_png)
        actExit = fileMenu.addAction("Exit"); actExit.triggered.connect(self.close)

        viewMenu = m.addMenu("&View")
        actReset = viewMenu.addAction("Reset View")
        actReset.triggered.connect(self._reset_view)
        try:
            viewMenu.addAction(self.actToggleInspector)
            try:
                viewMenu.addAction(self.view3DDock.toggleViewAction())
            except Exception:
                pass
        except Exception:
            try:
                self.actToggleInspector = QAction("Inspector", self)
                self.actToggleInspector.setCheckable(True)
                self.actToggleInspector.triggered.connect(self.toggle_inspector)
                viewMenu.addAction(self.actToggleInspector)
            except Exception:
                pass

        # Origin-style deep graph customization — reuse the toolbar action if built
        if hasattr(self, "actFormatGraph"):
            self.actFormatGraph.setText("Format Graph… (Plot Details)")
            self.actFormatGraph.setShortcut("Ctrl+Shift+F")
            viewMenu.addAction(self.actFormatGraph)
        else:
            self.actFormatGraph = viewMenu.addAction("Format Graph… (Plot Details)")
            self.actFormatGraph.setShortcut("Ctrl+Shift+F")
            self.actFormatGraph.triggered.connect(self.open_plot_details_dialog)

        # Plot Style submenu
        plotStyleMenu = viewMenu.addMenu("Plot Style")
        self.actDarkStyle = plotStyleMenu.addAction("Dark")
        self.actDefaultStyle = plotStyleMenu.addAction("Default")
        self.actDarkStyle.setCheckable(True)
        self.actDefaultStyle.setCheckable(True)
        self.actDarkStyle.triggered.connect(lambda: self.change_plot_style("dark"))
        self.actDefaultStyle.triggered.connect(lambda: self.change_plot_style("default"))

        self.dataMenu = m.addMenu("&Data")
        self._build_data_menu()

        # Plot menu (top menubar) — Origin model: each entry = a NEW graph
        plotMenu = m.addMenu("&Plot")
        for _title, _style in (
            ("Line", "line"),
            ("Scatter", "scatter"),
            ("Line + Symbol", "linesymbol"),
            ("Column / Bar", "bar"),
            ("Histogram", "histogram"),
        ):
            _act = plotMenu.addAction(f"{_title} → new graph")
            _act.triggered.connect(
                lambda _=False, s=_style: self.plot_from_workbook(s, new_graph=True))
        plotMenu.addSeparator()
        actGallery = plotMenu.addAction("Plot Gallery…  (Statistical / QC / Relational)")
        try:
            actGallery.setShortcut("Ctrl+Shift+G")
        except Exception:
            pass
        actGallery.triggered.connect(self.open_plot_gallery)
        plotMenu.addSeparator()
        actAddLine = plotMenu.addAction("Add Line (overlay)")
        actAddScatter = plotMenu.addAction("Add Scatter (overlay)")
        try:
            actAddLine.setShortcut("Ctrl+Shift+L")
            actAddScatter.setShortcut("Ctrl+Shift+S")
        except Exception:
            pass
        actAddLine.triggered.connect(self.add_line_overlay)
        actAddScatter.triggered.connect(self.add_scatter_overlay)
        plotMenu.addSeparator()
        plotMenu.addAction("Error Bar Plot…").triggered.connect(self.plot_error_bars)
        plotMenu.addAction("Fill Between (band)…").triggered.connect(self.plot_fill_between)
        plotMenu.addAction("Add Secondary Y Axis…").triggered.connect(self.plot_secondary_axis)
        plotMenu.addAction("Broken Axis...").triggered.connect(self.plot_broken_axis)
        plotMenu.addSeparator()
        if hasattr(self, 'actPlotEquation'):
            plotMenu.addAction(self.actPlotEquation)
        else:
            self.actPlotEquation = plotMenu.addAction('Plot from Equation...')
            self.actPlotEquation.triggered.connect(self.on_plot_from_equation)
            try:
                self.actPlotEquation.setIcon(self._icon('Plot_from_Equation', QStyle.StandardPixmap.SP_DialogApplyButton))
            except Exception:
                pass
        procMenu = m.addMenu("&Process")  # UI-REFINE: Process
        self.processMenu = procMenu
        self._build_process_menu()

        exportMenu = m.addMenu("&Export")  # UI-REFINE: Export
        exportMenu.addAction("Export Visible CSV").triggered.connect(self.export_visible_range_csv)
        exportMenu.addAction("Export PNG").triggered.connect(self.export_png)
        exportMenu.addAction("Export Figure… (PNG/PDF/SVG/TIFF/EPS)").triggered.connect(
            self.export_figure_advanced)
        exportMenu.addAction("Batch Export Graphs...").triggered.connect(
            self.export_figures_batch)
        actCopyFig = exportMenu.addAction("Copy Graph to Clipboard")
        actCopyFig.setShortcut("Ctrl+Shift+C")
        actCopyFig.triggered.connect(self.copy_figure_to_clipboard)
        exportMenu.addSeparator()
        exportMenu.addAction("Export Report (PDF)...").triggered.connect(self.on_export_report)

        toolsMenu = QMenu("&Tools", self)  # UI-REFINE: Tools
        m.addMenu(toolsMenu)
        toolsMenu.addAction(self.actSettings)
        self.toolsMenu = toolsMenu  # โมดูลอื่น (เช่น workflow) เติมรายการต่อได้

        # Window menu (Origin-style): arrange MDI sub-windows
        try:
            windowMenu = m.addMenu("&Window")
            windowMenu.addAction("Cascade").triggered.connect(
                lambda: getattr(self, "mdi", None) and self.mdi.cascade())
            windowMenu.addAction("Tile").triggered.connect(
                lambda: getattr(self, "mdi", None) and self.mdi.tile())
            windowMenu.addSeparator()
            windowMenu.addAction("New Graph").triggered.connect(
                lambda: getattr(self, "mdi", None) and self.mdi.add_tab())
        except Exception:
            logging.getLogger(__name__).debug("Window menu setup skipped", exc_info=True)

        # Plotting Mode → อยู่ใน Tools (เดิมเป็น top-menu "Settings" แยกซ้ำซ้อน
        # กับ Tools ที่มี Settings dialog อยู่แล้ว)
        try:
            from PySide6.QtGui import QActionGroup
            plot_mode_menu = toolsMenu.addMenu("Plotting Mode")
            grp = QActionGroup(self); grp.setExclusive(True)
            act_overlay = QAction("Overlay (default)", self, checkable=True)
            act_replace = QAction("Replace", self, checkable=True)
            grp.addAction(act_overlay); grp.addAction(act_replace)
            plot_mode_menu.addAction(act_overlay); plot_mode_menu.addAction(act_replace)
            act_overlay.setChecked(getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.OVERLAY)
            act_replace.setChecked(getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE)
            def _set_mode(mode):
                try:
                    self.plot_mode = mode
                    if hasattr(self, 'settings'):
                        self.settings.setValue("plot/mode", mode.value)
                except Exception:
                    self.plot_mode = mode
            act_overlay.triggered.connect(lambda: _set_mode(PlotMode.OVERLAY))
            act_replace.triggered.connect(lambda: _set_mode(PlotMode.REPLACE))
        except Exception:
            pass

        helpMenu = m.addMenu("&Help")
        actAbout = helpMenu.addAction("About"); actAbout.triggered.connect(self.show_about)
        helpMenu.addAction("Associate .sciproj files with this app").triggered.connect(
            self.register_file_association)
        help_shortcuts = (
            "[General]\n"
            "Ctrl+O: Open data file\n"
            "Ctrl+K: Command Palette\n"
            "Ctrl+, : Settings\n"
            "Ctrl+Shift+D: Create Derived Column\n"
            "\n[Plot]\n"
            "Ctrl+Shift+L: Add line overlay to the current graph\n"
            "Ctrl+Shift+S: Add scatter overlay to the current graph\n"
            "\n[Annotation]\n"
            "T/W/L/R/E/C: Text/Arrow/Line/Rect/Ellipse/Callout\n"
            "Ctrl+Z / Ctrl+Y: Undo / Redo\n"
            "\n[Analysis]\n"
            "Ctrl+Shift+X: Toggle Multi-Cursor mode\n"
            "Ctrl+Shift+P: Toggle Peak Detection\n"
            "Ctrl+D: Detect peaks in range\n"
            "Ctrl+E: Export peak table (CSV/Excel)"
        )

        # Origin-style chart mega menu on the top menubar.
        try:
            self.chartsMenu = OriginChartMenu(
                on_basic=self.plot_basic_gallery_chart,
                on_registry=self.plot_from_gallery,
                parent=self,
            )
            m.insertMenu(procMenu.menuAction(), self.chartsMenu)
        except Exception:
            logging.getLogger(__name__).debug("chart mega menu setup failed", exc_info=True)

        helpMenu.addAction("Shortcuts").triggered.connect(lambda: QMessageBox.information(self, "Shortcuts", help_shortcuts))

        # === Analysis Menu ===
        analysisMenu = QMenu("&Analysis", self)
        m.addMenu(analysisMenu)
        self.analysisMenu = analysisMenu

        def _analysis_action(menu, text: str, slot):
            action = QAction(text, self)
            action.triggered.connect(slot)
            menu.addAction(action)
            return action

        def _trigger_late(attr: str):
            def _run(*_args):
                action = getattr(self, attr, None)
                if action is not None:
                    action.trigger()
            return _run

        # Origin-like Analysis menu map. These mirror existing working
        # features so users can approach analysis from one place without
        # losing the Process/Data menu paths.
        statistics_menu = analysisMenu.addMenu("Statistics")
        _analysis_action(statistics_menu, "Descriptive Statistics...", self.feature_show_statistics)
        _analysis_action(statistics_menu, "Covariance Matrix...", self.feature_show_covariance)
        _analysis_action(statistics_menu, "Correlation Matrix...", self.feature_show_covariance)
        _analysis_action(statistics_menu, "Signal Quality (SNR / Noise floor)...", self.feature_signal_quality)

        mathematics_menu = analysisMenu.addMenu("Mathematics")
        _analysis_action(mathematics_menu, "Create Column (Derived)...", self.open_derived_column_dialog)
        _analysis_action(mathematics_menu, "Add |B|...", self.feature_add_magnitude)
        _analysis_action(mathematics_menu, "Normalize / Standardize...", self.feature_clean_normalize)
        _analysis_action(mathematics_menu, "Detrend / Baseline...", self.feature_clean_detrend)

        manipulation_menu = analysisMenu.addMenu("Data Manipulation")
        _analysis_action(manipulation_menu, "Set Column Types...", self.feature_set_column_types)
        _analysis_action(manipulation_menu, "Aggregate...", self.run_aggregate_dialog)
        _analysis_action(manipulation_menu, "Group and Summarize...", self.feature_dataset_group)
        _analysis_action(manipulation_menu, "Merge Books...", self.feature_dataset_merge)
        _analysis_action(manipulation_menu, "Split Book...", self.feature_dataset_split)
        _analysis_action(manipulation_menu, "Filter Rows...", self.feature_dataset_filter)
        _analysis_action(manipulation_menu, "Search Book...", self.feature_dataset_search)
        _analysis_action(manipulation_menu, "Fill Missing...", self.feature_clean_fill_missing)
        _analysis_action(manipulation_menu, "Interpolate Missing", self.feature_clean_interpolate)
        _analysis_action(manipulation_menu, "Remove Missing Rows...", self.feature_clean_remove_nan)
        _analysis_action(manipulation_menu, "Remove Duplicates", self.feature_clean_remove_duplicates)
        _analysis_action(manipulation_menu, "Remove Outliers...", self.feature_clean_remove_outliers)
        _analysis_action(manipulation_menu, "Crop Range...", self.feature_clean_crop_range)
        _analysis_action(manipulation_menu, "Sort...", self.feature_clean_sort)
        _analysis_action(manipulation_menu, "Resample (uniform grid)...", self.feature_clean_resample)
        _analysis_action(manipulation_menu, "Merge by Timestamp...", self.feature_clean_merge_by_timestamp)

        fitting_menu = analysisMenu.addMenu("Fitting")
        _analysis_action(fitting_menu, "Linear Fit...", self._open_fit_dialog)
        _analysis_action(fitting_menu, "Polynomial Fit...", self._open_fit_dialog)
        _analysis_action(fitting_menu, "Nonlinear Curve Fit...", self.open_nonlinear_fit_dialog)

        signal_processing_menu = analysisMenu.addMenu("Signal Processing")
        smooth_menu = signal_processing_menu.addMenu("Smooth")
        _analysis_action(smooth_menu, "Moving Average", self.feature_add_moving_average)
        _analysis_action(smooth_menu, "Smooth (Savitzky-Golay/Median/Gaussian)...", self.feature_filter_smooth)
        _analysis_action(smooth_menu, "Apply Window (Hann/Hamming/Blackman/Kaiser)...", self.feature_apply_window)
        _analysis_action(signal_processing_menu, "FFT Filters...", self.feature_filter_butterworth)
        _analysis_action(signal_processing_menu, "IIR Filter...", self.feature_filter_butterworth)
        _analysis_action(signal_processing_menu, "STFT...", self.feature_signal_stft)
        fft_menu = signal_processing_menu.addMenu("FFT")
        _analysis_action(fft_menu, "FFT", self.run_fft_dialog)
        _analysis_action(fft_menu, "PSD (Welch)...", self.run_psd_dialog)
        _analysis_action(fft_menu, "IFFT...", self.feature_signal_ifft)
        wavelet_menu = signal_processing_menu.addMenu("Wavelet")
        _analysis_action(wavelet_menu, "CWT / Wavelet Spectrogram...", self.open_spectrogram_dialog)
        _analysis_action(signal_processing_menu, "Convolution...", self.feature_signal_convolution)
        _analysis_action(signal_processing_menu, "Deconvolution...", self.feature_signal_deconvolution)
        corr_menu = signal_processing_menu.addMenu("Correlation")
        _analysis_action(corr_menu, "Auto-correlation...", self.feature_signal_autocorrelation)
        _analysis_action(corr_menu, "Cross-Correlation Window...", _trigger_late("actCCWindow"))
        _analysis_action(signal_processing_menu, "Hilbert Transform...", self.feature_signal_hilbert)
        _analysis_action(signal_processing_menu, "Envelope...", self.feature_signal_envelope)
        _analysis_action(signal_processing_menu, "Instantaneous Frequency...", self.feature_signal_instantaneous_frequency)
        _analysis_action(signal_processing_menu, "Decimation...", self.feature_signal_decimation)
        _analysis_action(signal_processing_menu, "Harmonic Analysis...", self.feature_signal_harmonic_analysis)

        peaks_baseline_menu = analysisMenu.addMenu("Peaks and Baseline")
        _analysis_action(peaks_baseline_menu, "Peak Metrics (FWHM / Area)...", self.feature_peak_metrics)
        _analysis_action(peaks_baseline_menu, "Signal Quality (SNR / Noise floor)...", self.feature_signal_quality)
        _analysis_action(peaks_baseline_menu, "Peak Settings...", _trigger_late("actPkSettings"))
        _analysis_action(peaks_baseline_menu, "Detect in Range", _trigger_late("actPkDetect"))
        _analysis_action(peaks_baseline_menu, "Annotate Peaks", _trigger_late("actPkAnnotate"))
        _analysis_action(peaks_baseline_menu, "Export Peak Table (CSV/Excel)", _trigger_late("actPkExport"))
        _analysis_action(peaks_baseline_menu, "Clear Peaks", _trigger_late("actPkClear"))
        analysisMenu.addSeparator()
        _analysis_action(analysisMenu, "1 Linear Fit: <default>...", self._open_fit_dialog)
        _analysis_action(analysisMenu, "2 Smooth: <default>...", self.feature_filter_smooth)
        _analysis_action(analysisMenu, "3 Descriptive Statistics: <default>...", self.feature_show_statistics)
        analysisMenu.addSeparator()

        # Cross-Correlation submenu
        ccMenu = QMenu("Cross-Correlation", self)
        analysisMenu.addMenu(ccMenu)
        self.ccMenu = ccMenu
        self.actCCEnable = ccMenu.addAction("Enable Multi-Cursor Mode"); self.actCCEnable.setCheckable(True); self.actCCEnable.setShortcut("Ctrl+Shift+X")
        self.actCCWindow = ccMenu.addAction("Window…")
        self.actCCLink = ccMenu.addAction("Link Axes by X-Time"); self.actCCLink.setCheckable(True)
        self.actCCCompute = ccMenu.addAction("Compute in Range")
        self.actCCClear = ccMenu.addAction("Clear Results")

        # --- MENU-BAR ONLY: Analysis --- (No toolbar entries for Analysis)
        # Lazy-import overlay dialog and wire actions directly under Analysis
        from PySide6.QtWidgets import QMessageBox as _QMessageBox
        from pathlib import Path as _Path
        import sys as _sys, traceback as _traceback

        # Ensure project folder is on sys.path (for dialogs_charts_adv import)
        try:
            _sys.path.insert(0, str(_Path(__file__).resolve().parent))
        except Exception:
            pass

        def _get_df():
            try:
                df = self._resolve_active_dataframe()
                return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
            except Exception:
                return pd.DataFrame()

        def _apply_to_main(draw_fn, prefer_3d: bool=False):
            try:
                self.apply_plot(draw_fn, prefer_3d=prefer_3d)
            except Exception:
                # fallback: try best effort without clearing
                try:
                    fig = self.canvas.fig
                    ax = fig.axes[-1] if fig.axes else fig.add_subplot(111)
                    draw_fn(ax)
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        def open_overlay(kind: str):
            try:
                from dialogs_charts_adv import ChartOptionsDialogPro as _ChartOptionsDialogPro
            except ModuleNotFoundError as e:
                _QMessageBox.critical(
                    self,
                    "Module not found",
                    (
                        "Unable to import 'dialogs_charts_adv.py'.\n"
                        "Make sure the file lives next to main.py or add its folder to PYTHONPATH."
                    ),
                )
                print("Import error:", e)
                print(_traceback.format_exc())
                return
            dlg = _ChartOptionsDialogPro(kind=kind, get_df=_get_df, apply_to_main=_apply_to_main, parent=self)
            dlg.exec()

        # ชนิดกราฟที่ Plot menu (พล็อตจากชีต) ไม่มี — เปิดกล่องเลือกคอลัมน์ให้
        # (Line/Scatter/Bar/Histogram ตัดออกเพราะซ้ำกับ Plot menu โดยตรงแล้ว)
        # NOTE: เติมเป็น submenu ของ "Plot" ไม่ใช่ Analysis — การทำกราฟรวมอยู่ที่ Plot
        advChartsMenu = plotMenu.addMenu("More chart types (Area/Box/Pie/3D)…")
        for title, kind in [
            ("Area…", "area"),
            ("Box…", "box"),
            ("Pie…", "pie"),
            ("3D Scatter…", "3d_scatter"),
        ]:
            act = QAction(title, self)
            advChartsMenu.addAction(act)
            act.triggered.connect(lambda _, k=kind: open_overlay(k))

        analysisMenu.addAction("Descriptive Statistics…").triggered.connect(
            self.feature_show_statistics)
        analysisMenu.addAction("Covariance Matrix…").triggered.connect(
            self.feature_show_covariance)
        analysisMenu.addAction("Peak Metrics (FWHM / Area)…").triggered.connect(
            self.feature_peak_metrics)
        analysisMenu.addAction("Signal Quality (SNR / Noise floor)…").triggered.connect(
            self.feature_signal_quality)
        analysisMenu.addSeparator()
        fit_icon = self._icon("fit", QStyle.SP_DialogApplyButton)
        self.actNonlinearFit = analysisMenu.addAction(fit_icon, "Nonlinear Curve Fit…")
        self.actNonlinearFit.triggered.connect(self.open_nonlinear_fit_dialog)
        analysisMenu.addSeparator()

# Peak Detection submenu
        pkMenu = QMenu("Peak Detection", self)
        analysisMenu.addMenu(pkMenu)
        self.pkMenu = pkMenu
        self.actPkEnable = pkMenu.addAction("Enable Peak Detection"); self.actPkEnable.setCheckable(True); self.actPkEnable.setShortcut("Ctrl+Shift+P")
        self.actPkSettings = pkMenu.addAction("Peak Settings…")
        self.actPkDetect = pkMenu.addAction("Detect in Range"); self.actPkDetect.setShortcut("Ctrl+D")
        self.actPkAnnotate = pkMenu.addAction("Annotate Peaks"); self.actPkAnnotate.setCheckable(True)
        self.actPkExport = pkMenu.addAction("Export Peak Table (CSV/Excel)"); self.actPkExport.setShortcut("Ctrl+E")
        self.actPkClear = pkMenu.addAction("Clear Peaks")

        # Docks + managers
        self.ccDock = CrossCorrDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.ccDock); self.ccDock.hide()
        self.crosscorr = CrossCorrManager(self)
        self.pkDock = PeakDetectionDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.pkDock); self.pkDock.hide()
        self.peaks = PeakDetectorManager(self)
        self.view3DDock = ThreeDViewDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.view3DDock)
        self.view3DDock.hide()
        self._3d_dock_has_shown = False

        def populate_cols_into_docks():
            try:
                import pandas as pd
                df = getattr(self, '_df', None)
                cols = list(df.columns) if df is not None else []
            except Exception:
                cols = []
            self.ccDock.populate_columns(cols)
            self.pkDock.populate_columns(cols)

        populate_cols_into_docks()

        # Wire actions
        self.actCCEnable.toggled.connect(lambda on: self.crosscorr.set_enabled(on))
        self.actCCLink.toggled.connect(lambda on: self.crosscorr.set_link_axes(on))
        self.actCCWindow.triggered.connect(lambda: (populate_cols_into_docks(), self.ccDock.show()))
        self.ccDock.request_compute.connect(self._on_cc_compute)
        self.actCCCompute.triggered.connect(lambda: self.ccDock._emit_compute())
        self.actCCClear.triggered.connect(lambda: self.crosscorr._clear_vlines())

        self.actPkEnable.toggled.connect(lambda on: self.peaks.set_enabled(on))
        self.actPkSettings.triggered.connect(lambda: (populate_cols_into_docks(), self.pkDock.show()))
        self.pkDock.request_detect.connect(self._on_pk_detect)
        self.pkDock.request_annotate.connect(lambda _: self._on_pk_annotate(True))
        self.pkDock.request_clear.connect(lambda: (self.peaks.clear(), self.pkDock.table.setRowCount(0)))
        self.pkDock.request_export.connect(self._on_pk_export)
        self.actPkDetect.triggered.connect(lambda: self._on_pk_detect(self._collect_pk_params_from_menu()))
        self.actPkAnnotate.toggled.connect(lambda on: self._on_pk_annotate(on))
        self.actPkExport.triggered.connect(self._on_pk_export)
        self.actPkClear.triggered.connect(lambda: (self.peaks.clear(), self.pkDock.table.setRowCount(0)))

        # --- Annotation menu (recreate safely) ---
        def _mgr():
            tab = self.tabs.currentWidget()
            return getattr(tab, 'annotation_manager', None)

        try:
            self.annMenu
        except Exception:
            self.annMenu = None
        if self.annMenu is None:
            try:
                self.annMenu = QMenu("&Annotation", self)
                m.addMenu(self.annMenu)
                self.actAnnEnable = self.annMenu.addAction("Enable Annotation Mode"); self.actAnnEnable.setCheckable(True)
                self.actAnnText = self.annMenu.addAction("Add Text (T)")
                self.actAnnArrow = self.annMenu.addAction("Add Arrow (W)")
                self.actAnnLine = self.annMenu.addAction("Add Line (L)")
                self.actAnnRect = self.annMenu.addAction("Add Rectangle (R)")
                self.actAnnEllipse = self.annMenu.addAction("Add Ellipse (E)")
                self.actAnnCallout = self.annMenu.addAction("Add Callout (C)")
                self.annMenu.addSeparator()
                self.actAnnStyleDock = self.annMenu.addAction("Style Dock...")
                self.actAnnManage = self.annMenu.addAction("Manage Annotations")
                self.annMenu.addSeparator()
                self.actUndo = self.annMenu.addAction("Undo"); self.actRedo = self.annMenu.addAction("Redo")
                # Shortcuts
                self.actAnnText.setShortcut("T"); self.actAnnArrow.setShortcut("W"); self.actAnnLine.setShortcut("L")
                self.actAnnRect.setShortcut("R"); self.actAnnEllipse.setShortcut("E"); self.actAnnCallout.setShortcut("C")
                self.actUndo.setShortcut("Ctrl+Z"); self.actRedo.setShortcut("Ctrl+Y")
                # Dock
                self.annStyleDock = AnnotationStyleDock(self); self.addDockWidget(Qt.RightDockWidgetArea, self.annStyleDock); self.annStyleDock.hide()
            except Exception:
                pass

        # Wire actions (guarded)
        try:
            self.actAnnEnable.toggled.connect(lambda on: (_mgr() and _mgr().set_enabled(on)))
            self.actAnnText.triggered.connect(lambda: (_mgr() and _mgr().set_mode('text')))
            self.actAnnArrow.triggered.connect(lambda: (_mgr() and _mgr().set_mode('arrow')))
            self.actAnnLine.triggered.connect(lambda: (_mgr() and _mgr().set_mode('line')))
            self.actAnnRect.triggered.connect(lambda: (_mgr() and _mgr().set_mode('rect')))
            self.actAnnEllipse.triggered.connect(lambda: (_mgr() and _mgr().set_mode('ellipse')))
            self.actAnnCallout.triggered.connect(lambda: (_mgr() and _mgr().set_mode('callout')))
            self.actAnnStyleDock.triggered.connect(lambda: self.annStyleDock.show())
            self.actAnnManage.triggered.connect(lambda: (_mgr() and AnnotationListDialog(_mgr(), self).exec()))
            self.actUndo.triggered.connect(lambda: (_mgr() and _mgr().undo()))
            self.actRedo.triggered.connect(lambda: (_mgr() and _mgr().redo()))
            self.annStyleDock.style_applied.connect(lambda st: (_mgr() and _mgr().set_style(st)))
        except Exception:
            pass
