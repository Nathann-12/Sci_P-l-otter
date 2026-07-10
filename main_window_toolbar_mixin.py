from __future__ import annotations

import logging
import os
from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QStyle, QToolBar


class MainWindowToolbarMixin:
    """Origin-style two-row function toolbar.

    The toolbar is intentionally icon-only: labels live in tooltips and every
    action carries a unique ``toolbarIconKey`` so tests can catch duplicated or
    unclear symbols.
    """

    TOOLBAR_ICON_SIZE = 16

    _PLOT_BAR_SPECS = (
        ("Line", ("mdi.chart-line",), "Line plot -> new graph", "line"),
        ("Scatter", ("mdi.scatter-plot-outline", "mdi.chart-scatter-plot"),
         "Scatter plot -> new graph", "scatter"),
        ("Line+Symbol", ("mdi.chart-line-variant", "mdi.chart-timeline-variant"),
         "Line + symbol -> new graph", "linesymbol"),
        ("Column", ("mdi.chart-bar",), "Column / bar chart -> new graph", "bar"),
        ("Histogram", ("mdi.chart-histogram", "mdi.chart-bell-curve"),
         "Histogram -> new graph", "histogram"),
    )

    def build_toolbar(self):
        """Build a compact two-row function bar like desktop science tools."""
        self.tb = self._make_toolbar("Function Bar 1", "FunctionToolbarPrimary")
        self.addToolBar(Qt.TopToolBarArea, self.tb)
        self.addToolBarBreak(Qt.TopToolBarArea)
        self.function_toolbar = self._make_toolbar(
            "Function Bar 2", "FunctionToolbarSecondary"
        )
        self.addToolBar(Qt.TopToolBarArea, self.function_toolbar)

        self.toolbar_actions = {}
        self.plot_bar_actions = {}
        self._create_toolbar_actions()
        self._sync_toolbar_tooltips()
        self._apply_toolbar_styling()

    def _make_toolbar(self, title: str, object_name: str) -> QToolBar:
        toolbar = QToolBar(title, self)
        toolbar.setObjectName(object_name)
        toolbar.setIconSize(QSize(self.TOOLBAR_ICON_SIZE, self.TOOLBAR_ICON_SIZE))
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setAllowedAreas(Qt.TopToolBarArea)
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        return toolbar

    def _function_toolbars(self) -> tuple[QToolBar, ...]:
        bars = []
        for name in ("tb", "function_toolbar"):
            toolbar = getattr(self, name, None)
            if toolbar is not None:
                bars.append(toolbar)
        return tuple(bars)

    def _plot_bar_icon(
        self,
        candidates,
        fallback_sp=QStyle.StandardPixmap.SP_FileDialogContentsView,
    ):
        """Return a qtawesome icon from the first available candidate."""
        try:
            from main import _qtawesome_icon

            for name in candidates:
                icon = _qtawesome_icon(name)
                if icon is not None:
                    return icon
        except Exception:
            pass
        try:
            return self.style().standardIcon(fallback_sp)
        except Exception:
            from PySide6.QtGui import QIcon

            return QIcon()

    def _set_toolbar_icon(self, action: QAction, icon_key: str, fallback_sp) -> None:
        """Set a unique semantic icon key and icon for a toolbar action."""
        try:
            action.setProperty("toolbarIconKey", icon_key)
            action.setIcon(self._icon(icon_key, fallback_sp))
        except Exception:
            logging.getLogger(__name__).debug(
                "Failed to set toolbar icon %s", icon_key, exc_info=True
            )

    def _toolbar_slot(self, method_name: str) -> Callable:
        def _run(*_args):
            method = getattr(self, method_name, None)
            if callable(method):
                return method()
            return None

        return _run

    def _trigger_action_attr(self, attr: str) -> Callable:
        def _run(*_args):
            action = getattr(self, attr, None)
            if action is not None:
                action.trigger()

        return _run

    def _workbook_slot(self, method_name: str) -> Callable:
        def _run(*_args):
            workbook = getattr(self, "workbook", None)
            method = getattr(workbook, method_name, None)
            if callable(method):
                return method()
            return None

        return _run

    def _add_toolbar_action(
        self,
        toolbar: QToolBar,
        key: str,
        text: str,
        slot: Callable | None,
        icon_key: str,
        fallback_sp=QStyle.StandardPixmap.SP_FileIcon,
        *,
        tooltip: str | None = None,
        checkable: bool = False,
        existing_action: QAction | None = None,
    ) -> QAction:
        action = existing_action or QAction(text, self)
        if existing_action is None and slot is not None:
            action.triggered.connect(slot)
        action.setText(text)
        action.setToolTip(tooltip or text)
        action.setStatusTip(tooltip or text)
        action.setCheckable(checkable)
        self._set_toolbar_icon(action, icon_key, fallback_sp)
        toolbar.addAction(action)
        self.toolbar_actions[key] = action
        return action

    def _add_separator(self, toolbar: QToolBar) -> None:
        toolbar.addSeparator()

    def _ensure_core_actions(self) -> None:
        if not hasattr(self, "actToggleInspector"):
            self.actToggleInspector = QAction("Inspector", self)
            self.actToggleInspector.setCheckable(True)
            self.actToggleInspector.triggered.connect(self.toggle_inspector)
        self._set_toolbar_icon(
            self.actToggleInspector,
            "inspector",
            QStyle.StandardPixmap.SP_FileDialogInfoView,
        )

        if not hasattr(self, "actOpen"):
            self.actOpen = QAction("Open", self)
            try:
                self.actOpen.triggered.connect(self.open_file)
            except Exception:
                self.actOpen.triggered.connect(
                    lambda: getattr(self, "open_file", lambda: None)()
                )
        self._set_toolbar_icon(
            self.actOpen, "open", QStyle.StandardPixmap.SP_DialogOpenButton
        )

        if not hasattr(self, "actSettings"):
            self.actSettings = QAction("Settings", self)
            self.actSettings.triggered.connect(self.show_settings)
        self._set_toolbar_icon(
            self.actSettings,
            "settings",
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
        )

        if not hasattr(self, "actPlotEquation"):
            self.actPlotEquation = QAction("Plot from Equation", self)
            self.actPlotEquation.triggered.connect(self.on_plot_from_equation)
        self._set_toolbar_icon(
            self.actPlotEquation,
            "Plot_from_Equation",
            QStyle.StandardPixmap.SP_DialogApplyButton,
        )

        if not hasattr(self, "actCrosshair"):
            self.actCrosshair = QAction("Crosshair", self)
            self.actCrosshair.setCheckable(True)
            self.actCrosshair.toggled.connect(
                lambda checked: getattr(self, "chkCross", None) is not None
                and self.chkCross.setChecked(checked)
            )
        self.actCrosshair.setToolTip("Show crosshair on the active graph")
        self._set_toolbar_icon(
            self.actCrosshair, "crosshair", QStyle.StandardPixmap.SP_DialogYesButton
        )

        if not hasattr(self, "actBoxZoom"):
            self.actBoxZoom = QAction("Box Zoom", self)
            self.actBoxZoom.triggered.connect(
                lambda: getattr(self, "start_box_zoom", lambda: None)()
            )
        self.actBoxZoom.setToolTip("Box zoom on the active graph")
        self._set_toolbar_icon(
            self.actBoxZoom,
            "boxzoom",
            QStyle.StandardPixmap.SP_FileDialogContentsView,
        )

        if not hasattr(self, "actFormatGraph"):
            self.actFormatGraph = QAction("Format Graph", self)
            self.actFormatGraph.triggered.connect(
                lambda: getattr(self, "open_plot_details_dialog", lambda: None)()
            )
        self.actFormatGraph.setToolTip(
            "Format Graph - Plot Details (title, axes, grid, legend, lines)"
        )
        self._set_toolbar_icon(
            self.actFormatGraph, "format", QStyle.StandardPixmap.SP_DesktopIcon
        )

        if not hasattr(self, "actErrorPanel"):
            self.actErrorPanel = QAction("Error Panel", self)
            self.actErrorPanel.setCheckable(True)
            self.actErrorPanel.triggered.connect(self.toggle_error_panel)
        self._set_toolbar_icon(
            self.actErrorPanel,
            "error_panel",
            QStyle.StandardPixmap.SP_MessageBoxWarning,
        )

    def _create_toolbar_actions(self):
        """Populate both rows with direct, testable app actions."""
        self._ensure_core_actions()
        top = self.tb
        bottom = self.function_toolbar

        # Row 1: file/data/plot/view/export shell controls.
        self._add_toolbar_action(
            top, "open", "Open", None, "open",
            QStyle.StandardPixmap.SP_DialogOpenButton,
            tooltip="Open a data file into a new Book",
            existing_action=self.actOpen,
        )
        self._add_toolbar_action(
            top, "batch_import", "Batch Import", self._toolbar_slot("stage_add_files"),
            "batch_import", QStyle.StandardPixmap.SP_DirOpenIcon,
            tooltip="Open multiple data files as separate Books",
        )
        self._add_toolbar_action(
            top, "open_project", "Open Project", self._toolbar_slot("open_project"),
            "open_project", QStyle.StandardPixmap.SP_DialogOpenButton,
        )
        self._add_toolbar_action(
            top, "save_project", "Save Project", self._toolbar_slot("save_project_as"),
            "save_project", QStyle.StandardPixmap.SP_DialogSaveButton,
        )
        self._add_separator(top)
        self._add_toolbar_action(
            top, "use_active_book", "Use Active Data", self.adopt_workbook_data,
            "use_active_book", QStyle.StandardPixmap.SP_DialogApplyButton,
            tooltip="Read the active worksheet into the working DataFrame",
        )
        self._add_toolbar_action(
            top, "reload_columns", "Reload Columns", self.load_columns_from_df,
            "reload_columns", QStyle.StandardPixmap.SP_BrowserReload,
        )
        self._add_toolbar_action(
            top, "add_row", "Add Row", self._workbook_slot("add_data_row"),
            "add_row", QStyle.StandardPixmap.SP_ArrowDown,
        )
        self._add_toolbar_action(
            top, "add_column", "Add Column", self._workbook_slot("add_data_column"),
            "add_column", QStyle.StandardPixmap.SP_ArrowRight,
        )
        self._add_toolbar_action(
            top, "derived_column", "Derived Column",
            self._toolbar_slot("open_derived_column_dialog"),
            "derived_column", QStyle.StandardPixmap.SP_FileDialogNewFolder,
        )
        self._add_toolbar_action(
            top, "column_types", "Column Types",
            self._toolbar_slot("feature_set_column_types"),
            "column_types", QStyle.StandardPixmap.SP_FileDialogDetailedView,
        )
        self._add_toolbar_action(
            top, "units_calibration", "Units", self._toolbar_slot("open_units_dialog"),
            "units_calibration", QStyle.StandardPixmap.SP_FileDialogInfoView,
        )
        self._add_separator(top)

        act_plot = self._add_toolbar_action(
            top, "plot", "Plot", self.on_action_plot, "plot",
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            tooltip="Plot selected worksheet columns on the active/last graph",
        )
        act_spec = self._add_toolbar_action(
            top, "spectrogram", "Spectrogram", self.on_action_spectrogram,
            "spectrogram", QStyle.StandardPixmap.SP_MediaPlay,
        )
        self._add_separator(top)
        for name, icons, tip, style in self._PLOT_BAR_SPECS:
            action = QAction(self._plot_bar_icon(icons), name, self)
            action.setProperty("toolbarIconKey", f"plot_{style}")
            action.setToolTip(tip)
            action.setStatusTip(tip)
            action.triggered.connect(
                lambda _=False, s=style: self.plot_from_workbook(s, new_graph=True)
            )
            top.addAction(action)
            self.plot_bar_actions[style] = action
            self.toolbar_actions[f"plot_{style}"] = action
        gallery = QAction(
            self._plot_bar_icon(
                ("mdi.view-gallery-outline", "mdi.grid-large", "mdi.chart-box-outline")
            ),
            "Gallery",
            self,
        )
        gallery.setProperty("toolbarIconKey", "plot_gallery")
        gallery.setToolTip("Open the Origin-style chart gallery")
        gallery.triggered.connect(self.open_plot_gallery)
        top.addAction(gallery)
        self.plot_bar_actions["gallery"] = gallery
        self.toolbar_actions["plot_gallery"] = gallery
        self._add_separator(top)
        self._add_toolbar_action(
            top, "error_bars", "Error Bars", self._toolbar_slot("plot_error_bars"),
            "error_bars", QStyle.StandardPixmap.SP_FileDialogDetailedView,
        )
        self._add_toolbar_action(
            top, "fill_band", "Fill Band", self._toolbar_slot("plot_fill_between"),
            "fill_band", QStyle.StandardPixmap.SP_FileDialogContentsView,
        )
        self._add_toolbar_action(
            top, "secondary_y", "Secondary Y", self._toolbar_slot("plot_secondary_axis"),
            "secondary_y", QStyle.StandardPixmap.SP_ArrowRight,
        )
        self._add_toolbar_action(
            top, "broken_axis", "Broken Axis", self._toolbar_slot("plot_broken_axis"),
            "broken_axis", QStyle.StandardPixmap.SP_TitleBarShadeButton,
        )
        self._add_toolbar_action(
            top, "plot_equation", "Plot Equation", None, "Plot_from_Equation",
            QStyle.StandardPixmap.SP_DialogApplyButton,
            existing_action=self.actPlotEquation,
        )
        self._add_separator(top)
        self._add_toolbar_action(
            top, "addtab", "Add Tab", self.on_action_add_tab, "addtab",
            QStyle.StandardPixmap.SP_FileDialogNewFolder,
        )
        self._add_toolbar_action(
            top, "window_cascade", "Cascade",
            lambda *_: getattr(getattr(self, "mdi", None), "mdi", None).cascadeSubWindows(),
            "window_cascade", QStyle.StandardPixmap.SP_TitleBarNormalButton,
        )
        self._add_toolbar_action(
            top, "window_tile", "Tile",
            lambda *_: getattr(getattr(self, "mdi", None), "mdi", None).tileSubWindows(),
            "window_tile", QStyle.StandardPixmap.SP_TitleBarMaxButton,
        )
        self._add_toolbar_action(
            top, "format_graph", "Format Graph", None, "format",
            QStyle.StandardPixmap.SP_DesktopIcon,
            existing_action=self.actFormatGraph,
        )
        self._add_toolbar_action(
            top, "crosshair", "Crosshair", None, "crosshair",
            QStyle.StandardPixmap.SP_DialogYesButton,
            checkable=True,
            existing_action=self.actCrosshair,
        )
        self._add_toolbar_action(
            top, "boxzoom", "Box Zoom", None, "boxzoom",
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            existing_action=self.actBoxZoom,
        )
        self._add_toolbar_action(
            top, "reset_view", "Reset View", self._toolbar_slot("_reset_view"),
            "reset_view", QStyle.StandardPixmap.SP_BrowserReload,
        )
        self._add_toolbar_action(
            top, "inspector", "Inspector", None, "inspector",
            QStyle.StandardPixmap.SP_FileDialogInfoView,
            checkable=True,
            existing_action=self.actToggleInspector,
        )
        self._add_toolbar_action(
            top, "error_panel", "Error Panel", None, "error_panel",
            QStyle.StandardPixmap.SP_MessageBoxWarning,
            checkable=True,
            existing_action=self.actErrorPanel,
        )
        self._add_separator(top)
        self._add_toolbar_action(
            top, "export_figure", "Export Figure", self.on_action_export_figure,
            "export_figure", QStyle.StandardPixmap.SP_DialogSaveButton,
        )
        self._add_toolbar_action(
            top, "export_data", "Export Data", self.on_action_export_data,
            "export_data", QStyle.StandardPixmap.SP_DialogSaveButton,
        )
        self._add_toolbar_action(
            top, "batch_export", "Batch Export", self._toolbar_slot("export_figures_batch"),
            "batch_export", QStyle.StandardPixmap.SP_DriveFDIcon,
        )
        self._add_toolbar_action(
            top, "copy_graph", "Copy Graph",
            self._toolbar_slot("copy_figure_to_clipboard"),
            "copy_graph", QStyle.StandardPixmap.SP_FileDialogContentsView,
        )
        self._add_toolbar_action(
            top, "settings", "Settings", None, "settings",
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
            existing_action=self.actSettings,
        )

        # Row 2: processing, analysis, annotation, gas, reproducibility.
        for key, text, method, icon, fallback in (
            ("processors", "Processors", "on_action_open_processors", "processors", QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ("moving_average", "Moving Average", "feature_add_moving_average", "moving_average", QStyle.StandardPixmap.SP_MediaSeekForward),
            ("magnitude", "Add |B|", "feature_add_magnitude", "magnitude", QStyle.StandardPixmap.SP_DialogApplyButton),
            ("bangkok_time", "Bangkok Time", "feature_add_bkk_time", "bangkok_time", QStyle.StandardPixmap.SP_ComputerIcon),
            ("aggregate", "Aggregate", "run_aggregate_dialog", "aggregate", QStyle.StandardPixmap.SP_FileDialogListView),
        ):
            self._add_toolbar_action(bottom, key, text, self._toolbar_slot(method), icon, fallback)
        self._add_separator(bottom)

        for key, text, method, icon in (
            ("dataset_duplicate", "Duplicate Book", "feature_dataset_duplicate", "dataset_duplicate"),
            ("dataset_rename", "Rename Book", "feature_dataset_rename", "dataset_rename"),
            ("dataset_group", "Group", "feature_dataset_group", "dataset_group"),
            ("dataset_merge", "Merge Books", "feature_dataset_merge", "dataset_merge"),
            ("dataset_split", "Split Book", "feature_dataset_split", "dataset_split"),
            ("dataset_filter", "Filter Rows", "feature_dataset_filter", "dataset_filter"),
            ("dataset_search", "Search Book", "feature_dataset_search", "dataset_search"),
        ):
            self._add_toolbar_action(
                bottom, key, text, self._toolbar_slot(method), icon,
                QStyle.StandardPixmap.SP_FileDialogDetailedView,
            )
        self._add_separator(bottom)

        for key, text, method, icon in (
            ("fill_missing", "Fill Missing", "feature_clean_fill_missing", "fill_missing"),
            ("interpolate_missing", "Interpolate", "feature_clean_interpolate", "interpolate_missing"),
            ("remove_missing_rows", "Remove Missing", "feature_clean_remove_nan", "remove_missing_rows"),
            ("remove_duplicates", "Duplicates", "feature_clean_remove_duplicates", "remove_duplicates"),
            ("remove_outliers", "Outliers", "feature_clean_remove_outliers", "remove_outliers"),
            ("crop_range", "Crop Range", "feature_clean_crop_range", "crop_range"),
            ("normalize", "Normalize", "feature_clean_normalize", "normalize"),
            ("detrend", "Detrend", "feature_clean_detrend", "detrend"),
            ("sort", "Sort", "feature_clean_sort", "sort"),
            ("resample", "Resample", "feature_clean_resample", "resample"),
            ("time_merge", "Time Merge", "feature_clean_merge_by_timestamp", "time_merge"),
        ):
            self._add_toolbar_action(
                bottom, key, text, self._toolbar_slot(method), icon,
                QStyle.StandardPixmap.SP_FileDialogDetailedView,
            )
        self._add_separator(bottom)

        for key, text, method, icon in (
            ("butterworth", "Butterworth", "feature_filter_butterworth", "butterworth"),
            ("smooth", "Smooth", "feature_filter_smooth", "smooth"),
            ("window_func", "Window", "feature_apply_window", "window_func"),
            ("fft", "FFT", "run_fft_dialog", "fft"),
            ("psd", "PSD", "run_psd_dialog", "psd"),
            ("hilbert", "Hilbert", "feature_signal_hilbert", "hilbert"),
            ("envelope", "Envelope", "feature_signal_envelope", "envelope"),
            ("instant_freq", "Instant Freq", "feature_signal_instantaneous_frequency", "instant_freq"),
            ("autocorr", "Auto-corr", "feature_signal_autocorrelation", "autocorr"),
            ("convolution", "Convolution", "feature_signal_convolution", "convolution"),
            ("deconvolution", "Deconvolution", "feature_signal_deconvolution", "deconvolution"),
            ("decimation", "Decimation", "feature_signal_decimation", "decimation"),
            ("harmonic", "Harmonic", "feature_signal_harmonic_analysis", "harmonic"),
            ("ifft", "IFFT", "feature_signal_ifft", "ifft"),
            ("stft", "STFT", "feature_signal_stft", "stft"),
            ("zero_pad", "Zero Pad", "feature_signal_zero_pad", "zero_pad"),
        ):
            self._add_toolbar_action(
                bottom, key, text, self._toolbar_slot(method), icon,
                QStyle.StandardPixmap.SP_MediaPlay,
            )
        self._add_separator(bottom)

        for key, text, method, icon in (
            ("stats", "Stats", "feature_show_statistics", "stats"),
            ("covariance", "Covariance", "feature_show_covariance", "covariance"),
            ("peak_metrics", "Peak Metrics", "feature_peak_metrics", "peak_metrics"),
            ("signal_quality", "Signal Quality", "feature_signal_quality", "signal_quality"),
            ("nonlinear_fit", "Nonlinear Fit", "open_nonlinear_fit_dialog", "fit"),
        ):
            self._add_toolbar_action(
                bottom, key, text, self._toolbar_slot(method), icon,
                QStyle.StandardPixmap.SP_DialogApplyButton,
            )
        self._add_toolbar_action(
            bottom, "cc_window", "CC Window", self._trigger_action_attr("actCCWindow"),
            "cc_window", QStyle.StandardPixmap.SP_FileDialogInfoView,
        )
        self._add_toolbar_action(
            bottom, "cc_compute", "CC Compute", self._trigger_action_attr("actCCCompute"),
            "cc_compute", QStyle.StandardPixmap.SP_DialogApplyButton,
        )
        self._add_toolbar_action(
            bottom, "cc_clear", "CC Clear", self._trigger_action_attr("actCCClear"),
            "cc_clear", QStyle.StandardPixmap.SP_DialogResetButton,
        )
        self._add_toolbar_action(
            bottom, "peak_settings", "Peak Settings", self._trigger_action_attr("actPkSettings"),
            "peak_settings", QStyle.StandardPixmap.SP_FileDialogDetailedView,
        )
        self._add_toolbar_action(
            bottom, "peak_detect", "Peak Detect", self._trigger_action_attr("actPkDetect"),
            "peak_detect", QStyle.StandardPixmap.SP_DialogApplyButton,
        )
        self._add_toolbar_action(
            bottom, "peak_export", "Peak Export", self._trigger_action_attr("actPkExport"),
            "peak_export", QStyle.StandardPixmap.SP_DialogSaveButton,
        )
        self._add_toolbar_action(
            bottom, "peak_clear", "Peak Clear", self._trigger_action_attr("actPkClear"),
            "peak_clear", QStyle.StandardPixmap.SP_DialogResetButton,
        )
        self._add_separator(bottom)

        for key, text, attr, icon in (
            ("ann_enable", "Annotate", "actAnnEnable", "ann_enable"),
            ("ann_text", "Text", "actAnnText", "ann_text"),
            ("ann_arrow", "Arrow", "actAnnArrow", "ann_arrow"),
            ("ann_line", "Ann Line", "actAnnLine", "ann_line"),
            ("ann_rect", "Rect", "actAnnRect", "ann_rect"),
            ("ann_ellipse", "Ellipse", "actAnnEllipse", "ann_ellipse"),
            ("ann_callout", "Callout", "actAnnCallout", "ann_callout"),
            ("ann_manage", "Manage Ann", "actAnnManage", "ann_manage"),
            ("undo", "Undo", "actUndo", "undo"),
            ("redo", "Redo", "actRedo", "redo"),
        ):
            self._add_toolbar_action(
                bottom, key, text, self._trigger_action_attr(attr), icon,
                QStyle.StandardPixmap.SP_FileDialogContentsView,
            )
        self._add_separator(bottom)

        for key, text, method, icon in (
            ("workflow_history", "Workflow History", "wf_show_history", "workflow_history"),
            ("workflow_export", "Workflow Export", "wf_export", "workflow_export"),
            ("workflow_import", "Workflow Re-run", "wf_import_and_run", "workflow_import"),
            ("workflow_script", "Workflow Script", "wf_generate_script", "workflow_script"),
            ("workflow_report", "Auto Report", "wf_auto_report", "workflow_report"),
            ("workflow_snapshot", "Snapshot", "wf_project_snapshot", "workflow_snapshot"),
            ("workflow_compare", "Compare", "wf_compare_versions", "workflow_compare"),
            ("workflow_audit", "Audit Trail", "wf_audit_trail", "workflow_audit"),
            ("workflow_clear", "Workflow Clear", "wf_clear", "workflow_clear"),
        ):
            self._add_toolbar_action(
                bottom, key, text, self._toolbar_slot(method), icon,
                QStyle.StandardPixmap.SP_FileDialogDetailedView,
            )

        # Compatibility alias used by existing tests and callers. Plot shortcuts
        # now live in the top two-row bar rather than a bottom-only toolbar.
        self.plot_toolbar = self.tb
        # Keep local variables referenced so linters do not collapse these key
        # compatibility actions during future refactors.
        _ = (act_plot, act_spec)

    def build_plot_toolbar(self):
        """Compatibility no-op; plot buttons are part of the two-row top bar."""
        return getattr(self, "plot_toolbar", None)

    def _sync_toolbar_tooltips(self):
        """Make every icon-only action discoverable."""
        try:
            for toolbar in self._function_toolbars():
                for action in toolbar.actions():
                    if action.isSeparator():
                        continue
                    text = (action.text() or "").replace("&", "").strip()
                    if not text:
                        continue
                    clean = text.rstrip(".").rstrip("...").strip() or text
                    if not action.toolTip() or action.toolTip() == action.text():
                        action.setToolTip(clean)
                    if not action.statusTip():
                        action.setStatusTip(action.toolTip())
        except Exception:
            logging.getLogger(__name__).debug(
                "Failed to sync toolbar tooltips", exc_info=True
            )

    def _apply_toolbar_styling(self):
        """Apply dense Origin-like styling to both toolbar rows."""
        try:
            qss_path = os.path.join("styles", "toolbar.qss")
            qss = None
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    qss = f.read()
            if not qss:
                qss = """
                QToolBar {
                    background: #1b1e23;
                    border: none;
                    border-bottom: 1px solid #2a2f36;
                    spacing: 1px;
                    padding: 2px 4px;
                }
                QToolBar::separator {
                    background-color: #343941;
                    width: 1px;
                    margin: 3px 3px;
                }
                QToolBar QToolButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 2px;
                    margin: 0px;
                    color: #cfd3d6;
                }
                QToolBar QToolButton:hover {
                    background: rgba(79, 156, 249, 0.14);
                    border: 1px solid rgba(79, 156, 249, 0.35);
                    color: #ffffff;
                }
                QToolBar QToolButton:checked {
                    background: rgba(79, 156, 249, 0.22);
                    border: 1px solid rgba(79, 156, 249, 0.55);
                    color: #4F9CF9;
                }
                """
            for toolbar in self._function_toolbars():
                toolbar.setStyleSheet(qss)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Failed to apply toolbar styling: %s", exc
            )

    def _update_compact_ui(self):
        """Keep both toolbar rows icon-only at every window width."""
        try:
            for toolbar in self._function_toolbars():
                toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        except Exception:
            pass
