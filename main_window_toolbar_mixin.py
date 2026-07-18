from __future__ import annotations

import logging
import os
from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QStyle, QToolBar


class MainWindowToolbarMixin:
    """Origin-style two-row function toolbar.

    The toolbar is intentionally icon-only: labels live in tooltips and every
    action carries a unique ``toolbarIconKey`` so tests can catch duplicated or
    unclear symbols.
    """

    TOOLBAR_ICON_SIZE = 16

    # --- Origin-style action enablement -----------------------------------
    # Commands that only make sense once the active Book holds data are dimmed
    # (disabled) until data is present; graph-only tools are dimmed until a
    # Graph window exists. Everything else stays always-on (Open, New Graph,
    # workflow history, settings, ...). Keyed by ``toolbar_actions`` key so the
    # single QAction object is dimmed on every surface that hosts it.
    _ACTIONS_NEED_DATA = frozenset({
        "use_active_book", "reload_columns", "derived_column", "column_types",
        "units_calibration",
        "plot", "spectrogram",
        "plot_line", "plot_scatter", "plot_linesymbol", "plot_bar",
        "plot_histogram", "plot_gallery",
        "error_bars", "fill_band", "secondary_y", "broken_axis",
        "processors", "moving_average", "magnitude", "bangkok_time", "aggregate",
        "fill_missing", "interpolate_missing", "remove_missing_rows",
        "remove_duplicates", "remove_outliers", "crop_range", "normalize",
        "detrend", "sort", "resample", "time_merge",
        "butterworth", "smooth", "window_func", "fft", "psd", "hilbert",
        "envelope", "instant_freq", "autocorr", "convolution", "deconvolution",
        "decimation", "harmonic", "ifft", "stft", "zero_pad",
        "stats", "covariance", "peak_metrics", "signal_quality", "nonlinear_fit",
        "cc_window", "cc_compute", "cc_clear", "peak_settings", "peak_detect",
        "peak_export", "peak_clear",
        "dataset_duplicate", "dataset_rename", "dataset_group", "dataset_merge",
        "dataset_split", "dataset_filter", "dataset_search",
        "sci_statistics", "sci_global_fit", "sci_peak_analyzer",
        "matrix_gridding", "matrix_heatmap", "matrix_surface",
    })
    _ACTIONS_NEED_GRAPH = frozenset({
        "format_graph", "crosshair", "boxzoom", "reset_view",
        "left_zoom_in", "left_zoom_out",
        "export_figure", "export_data", "batch_export", "copy_graph",
        "ann_enable", "ann_text", "ann_arrow", "ann_line", "ann_rect",
        "ann_ellipse", "ann_callout", "ann_manage",
    })

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
            try:
                method = getattr(self, method_name, None)
                if callable(method):
                    return method()
            except Exception as exc:
                reporter = getattr(self, "report_ui_exception", None)
                if callable(reporter):
                    reporter(method_name.replace("_", " ").title(), exc)
                else:
                    logging.getLogger(__name__).exception("Toolbar action failed: %s", method_name)
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
            try:
                workbook = getattr(self, "workbook", None)
                method = getattr(workbook, method_name, None)
                if callable(method):
                    return method()
            except Exception as exc:
                reporter = getattr(self, "report_ui_exception", None)
                if callable(reporter):
                    reporter(method_name.replace("_", " ").title(), exc)
                else:
                    logging.getLogger(__name__).exception("Worksheet action failed: %s", method_name)
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

    def _add_group_label(self, toolbar: QToolBar, text: str, key: str) -> QAction:
        """Add a small visible section label without changing icon-only tools."""
        label = QLabel(text)
        label.setObjectName("ToolbarGroupLabel")
        label.setAlignment(Qt.AlignCenter)
        label.setContentsMargins(6, 2, 6, 2)
        label.setStyleSheet(
            "QLabel#ToolbarGroupLabel { color: palette(mid); font-family: 'Segoe UI'; "
            "font-size: 8pt; font-weight: 600; }"
        )
        action = toolbar.addWidget(label)
        action.setProperty("toolbarIconKey", f"group_{key}")
        action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        return action

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
        """Populate the top two rows with only the everyday essentials.

        Row 1 = File / Data / View, Row 2 = Plot. The specialized processing,
        cleaning, signal, analysis, dataset, annotation and workflow tools are
        moved out to the categorized left/right/bottom docks (see
        :meth:`build_side_toolbars`) so the top bar stays uncluttered — but every
        action still registers under the same ``toolbar_actions`` key so callers
        and tests keep working regardless of which surface hosts it.
        """
        self._ensure_core_actions()
        top = self.tb
        plot_row = self.function_toolbar

        # --- Row 1: File ---
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
        # --- Row 1: Data / worksheet ---
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
        # --- Row 1: View / graph inspection ---
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
        self._add_toolbar_action(
            top, "settings", "Settings", None, "settings",
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
            existing_action=self.actSettings,
        )

        # --- Row 2: Plot ---
        self._add_group_label(plot_row, "Plot", "plot")
        act_plot = self._add_toolbar_action(
            plot_row, "plot", "Plot", self.on_action_plot, "plot",
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            tooltip="Plot selected worksheet columns on the active/last graph",
        )
        act_spec = self._add_toolbar_action(
            plot_row, "spectrogram", "Spectrogram", self.on_action_spectrogram,
            "spectrogram", QStyle.StandardPixmap.SP_MediaPlay,
        )
        self._add_separator(plot_row)
        for name, icons, tip, style in self._PLOT_BAR_SPECS:
            action = QAction(self._plot_bar_icon(icons), name, self)
            action.setProperty("toolbarIconKey", f"plot_{style}")
            action.setToolTip(tip)
            action.setStatusTip(tip)
            action.triggered.connect(
                lambda _=False, s=style: self.plot_from_workbook(s, new_graph=True)
            )
            plot_row.addAction(action)
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
        plot_row.addAction(gallery)
        self.plot_bar_actions["gallery"] = gallery
        self.toolbar_actions["plot_gallery"] = gallery
        self._add_separator(plot_row)
        self._add_toolbar_action(
            plot_row, "error_bars", "Error Bars", self._toolbar_slot("plot_error_bars"),
            "error_bars", QStyle.StandardPixmap.SP_FileDialogDetailedView,
        )
        self._add_toolbar_action(
            plot_row, "fill_band", "Fill Band", self._toolbar_slot("plot_fill_between"),
            "fill_band", QStyle.StandardPixmap.SP_FileDialogContentsView,
        )
        self._add_toolbar_action(
            plot_row, "secondary_y", "Secondary Y", self._toolbar_slot("plot_secondary_axis"),
            "secondary_y", QStyle.StandardPixmap.SP_ArrowRight,
        )
        self._add_toolbar_action(
            plot_row, "broken_axis", "Broken Axis", self._toolbar_slot("plot_broken_axis"),
            "broken_axis", QStyle.StandardPixmap.SP_TitleBarShadeButton,
        )
        self._add_toolbar_action(
            plot_row, "plot_equation", "Plot Equation", None, "Plot_from_Equation",
            QStyle.StandardPixmap.SP_DialogApplyButton,
            existing_action=self.actPlotEquation,
        )

        # Compatibility alias (tests/callers expect plot_toolbar == the top bar).
        self.plot_toolbar = self.tb
        # The specialized tool groups are registered into the docks so the
        # top stays lean. Keep local variables referenced.
        _ = (act_plot, act_spec)
        return

    def _create_dock_tool_groups(self, left, right, bottom):
        """Register the relocated tool groups onto the categorized docks, keeping
        the original ``toolbar_actions`` keys. Left = annotation, Right = dataset
        ops, Bottom = process / clean / signal / analysis / peak / workflow.
        Called by :meth:`build_side_toolbars`.
        """
        # ---- BOTTOM: quick transforms ----
        for key, text, method, icon, fallback in (
            ("processors", "Processors", "on_action_open_processors", "processors", QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ("moving_average", "Moving Average", "feature_add_moving_average", "moving_average", QStyle.StandardPixmap.SP_MediaSeekForward),
            ("magnitude", "Add |B|", "feature_add_magnitude", "magnitude", QStyle.StandardPixmap.SP_DialogApplyButton),
            ("bangkok_time", "Bangkok Time", "feature_add_bkk_time", "bangkok_time", QStyle.StandardPixmap.SP_ComputerIcon),
            ("aggregate", "Aggregate", "run_aggregate_dialog", "aggregate", QStyle.StandardPixmap.SP_FileDialogListView),
        ):
            self._add_toolbar_action(bottom, key, text, self._toolbar_slot(method), icon, fallback)
        self._add_separator(bottom)

        # ---- RIGHT: dataset / Book operations ----
        self._add_separator(right)
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
                right, key, text, self._toolbar_slot(method), icon,
                QStyle.StandardPixmap.SP_FileDialogDetailedView,
            )

        # ---- BOTTOM: clean & prepare ----
        self._add_group_label(bottom, "Clean", "clean")
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

        self._add_group_label(bottom, "Analyze", "analyze")
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
        # ---- BOTTOM: scientific suite (statistics / fits / recipes / batch) ----
        self._add_separator(bottom)
        self._add_group_label(bottom, "Scientific", "scientific")
        for key, text, method, icon in (
            ("sci_statistics", "Statistics", "scientific_open_statistics", "sci_statistics"),
            ("sci_global_fit", "Global Fit", "scientific_open_global_fit", "sci_global_fit"),
            ("sci_peak_analyzer", "Peak Analyzer", "scientific_open_peak_analyzer", "sci_peak_analyzer"),
            ("sci_recipes", "Recipes", "scientific_manage_recipes", "sci_recipes"),
            ("sci_recalculate", "Recalculate", "scientific_recalculate_all", "sci_recalculate"),
            ("sci_batch", "Batch Analysis", "scientific_batch_analysis", "sci_batch"),
        ):
            self._add_toolbar_action(
                bottom, key, text, self._toolbar_slot(method), icon,
                QStyle.StandardPixmap.SP_FileDialogDetailedView,
            )
        # ---- BOTTOM: matrix workflow ----
        self._add_separator(bottom)
        self._add_group_label(bottom, "Matrix", "matrix")
        for key, text, method, icon in (
            ("matrix_gridding", "XYZ → Matrix", "matrix_grid_dialog", "matrix_gridding"),
            ("matrix_heatmap", "Matrix Heatmap", "matrix_plot_heatmap", "matrix_heatmap"),
            ("matrix_surface", "Matrix Surface", "matrix_plot_surface", "matrix_surface"),
        ):
            self._add_toolbar_action(
                bottom, key, text, self._toolbar_slot(method), icon,
                QStyle.StandardPixmap.SP_FileDialogDetailedView,
            )
        self._add_separator(bottom)
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
        # ---- LEFT: annotation & history ----
        self._add_separator(left)
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
                left, key, text, self._trigger_action_attr(attr), icon,
                QStyle.StandardPixmap.SP_FileDialogContentsView,
            )

        # ---- BOTTOM: reproducibility / workflow ----
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
            self._toolbar_qss_text = qss  # reused by the side/bottom docks
            for toolbar in self._function_toolbars():
                toolbar.setStyleSheet(qss)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Failed to apply toolbar styling: %s", exc
            )

    # ================= Origin-style side & bottom tool docks =================
    # Left = graph interaction + annotation; Right = window/layout + export;
    # Bottom = plot types + analysis shortcuts. Every action is wired to a real
    # handler (no dead icons), reusing the existing checkable actions (crosshair,
    # inspector) so their state stays in sync with the top function bar.

    def _make_dock_toolbar(self, title: str, object_name: str, area) -> QToolBar:
        toolbar = QToolBar(title, self)
        toolbar.setObjectName(object_name)
        toolbar.setIconSize(QSize(self.TOOLBAR_ICON_SIZE, self.TOOLBAR_ICON_SIZE))
        toolbar.setMovable(True)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.addToolBar(area, toolbar)
        try:
            qss = getattr(self, "_toolbar_qss_text", None)
            if qss:
                toolbar.setStyleSheet(qss)
        except Exception:
            logging.getLogger(__name__).debug("dock toolbar styling skipped", exc_info=True)
        return toolbar

    def _reuse_action(self, toolbar: QToolBar, key: str) -> QAction | None:
        """Add the already-built top-bar action *key* to *toolbar* too, so both
        surfaces drive (and reflect) the exact same command/checked state."""
        action = self.toolbar_actions.get(key) if hasattr(self, "toolbar_actions") else None
        if action is not None:
            toolbar.addAction(action)
        return action

    def _zoom_active_axes(self, scale: float) -> None:
        """Zoom the active graph's axes about its center (scale<1 = zoom in)."""
        ax = None
        try:
            ax = self.active_axes()
        except Exception:
            ax = None
        if ax is None:
            return
        try:
            for get_lim, set_lim in ((ax.get_xlim, ax.set_xlim), (ax.get_ylim, ax.set_ylim)):
                lo, hi = get_lim()
                center = (lo + hi) / 2.0
                half = (hi - lo) * float(scale) / 2.0
                set_lim(center - half, center + half)
            ax.figure.canvas.draw_idle()
        except Exception:
            logging.getLogger(__name__).debug("zoom active axes failed", exc_info=True)

    def build_side_toolbars(self):
        """Create the categorized left / right / bottom Origin-style tool docks.

        Called after the menu is built so the annotation/window actions the docks
        surface already exist. Layout:
          Left   — Graph Tools: crosshair, box zoom, zoom in/out, reset, format
                   + annotation tools + undo/redo
          Right  — Windows & Export: new graph, tile, cascade, inspector, export
                   figure/data, batch export, copy + Book operations
          Bottom — Process · Clean · Signal · Analyze · Peak · Workflow
        Checkable tools that also live on the top bar (crosshair/box zoom/reset/
        format/inspector) are the *same* action objects (state stays in sync).
        """
        SP = QStyle.StandardPixmap
        self.side_toolbars = {}

        # ---------------- LEFT: graph interaction ----------------
        left = self._make_dock_toolbar("Graph Tools", "GraphToolsToolbar", Qt.LeftToolBarArea)
        self.left_toolbar = left
        self.side_toolbars["left"] = left
        self._reuse_action(left, "crosshair")
        self._reuse_action(left, "boxzoom")
        self._add_toolbar_action(
            left, "left_zoom_in", "Zoom In", lambda: self._zoom_active_axes(0.8),
            "zoom_in", SP.SP_FileDialogContentsView, tooltip="Zoom in (center)")
        self._add_toolbar_action(
            left, "left_zoom_out", "Zoom Out", lambda: self._zoom_active_axes(1.25),
            "zoom_out", SP.SP_FileDialogContentsView, tooltip="Zoom out (center)")
        self._reuse_action(left, "reset_view")
        self._reuse_action(left, "format_graph")
        # annotation + undo/redo appended by _create_dock_tool_groups

        # ---------------- RIGHT: windows & export ----------------
        right = self._make_dock_toolbar("Windows", "WindowsToolbar", Qt.RightToolBarArea)
        self.right_toolbar = right
        self.side_toolbars["right"] = right
        self._add_toolbar_action(
            right, "addtab", "New Graph", self._toolbar_slot("on_action_add_tab"),
            "addtab", SP.SP_FileDialogNewFolder, tooltip="New Graph window")
        self._add_toolbar_action(
            right, "window_tile", "Tile Windows", self._mdi_slot("tile"),
            "window_tile", SP.SP_FileDialogListView, tooltip="Tile Book/Graph windows")
        self._add_toolbar_action(
            right, "window_cascade", "Cascade Windows", self._mdi_slot("cascade"),
            "window_cascade", SP.SP_TitleBarNormalButton, tooltip="Cascade windows")
        self._reuse_action(right, "inspector")
        self._add_separator(right)
        self._add_group_label(right, "Export", "export")
        self._add_toolbar_action(
            right, "export_figure", "Export Figure",
            self._toolbar_slot("on_action_export_figure"), "export_figure",
            SP.SP_DialogSaveButton, tooltip="Export the active graph")
        self._add_toolbar_action(
            right, "export_data", "Export Data",
            self._toolbar_slot("on_action_export_data"), "export_data",
            SP.SP_DialogSaveButton, tooltip="Export the active graph's data")
        self._add_toolbar_action(
            right, "batch_export", "Batch Export",
            self._toolbar_slot("export_figures_batch"), "batch_export",
            SP.SP_DriveFDIcon, tooltip="Export every graph to a folder")
        self._add_toolbar_action(
            right, "copy_graph", "Copy Graph",
            self._toolbar_slot("copy_figure_to_clipboard"), "copy_graph",
            SP.SP_FileDialogContentsView, tooltip="Copy the active graph to the clipboard")
        # Book operations appended by _create_dock_tool_groups

        # ---------------- BOTTOM: process · analyze ----------------
        bottom = self._make_dock_toolbar("Process & Analyze", "PlotAnalyzeToolbar",
                                         Qt.BottomToolBarArea)
        self.bottom_toolbar = bottom
        self.side_toolbars["bottom"] = bottom

        # relocate the specialized groups onto the categorized docks
        self._create_dock_tool_groups(left, right, bottom)

        self._update_compact_ui()
        # Now that every action exists on some surface, dim the ones that can't
        # run yet and keep them in sync with Book/Graph state.
        self._wire_action_state_updates()
        return self.side_toolbars

    def _mdi_slot(self, method_name: str) -> Callable:
        def _run(*_args):
            tabs = getattr(self, "tabs", None)
            method = getattr(tabs, method_name, None)
            if callable(method):
                return method()
            return None
        return _run

    def _update_compact_ui(self):
        """Keep both toolbar rows icon-only at every window width."""
        try:
            for toolbar in self._function_toolbars():
                toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        except Exception:
            pass

    # ================= Origin-style action enablement (dim when unusable) ===
    def _has_plot_data(self) -> bool:
        """True when there is data to work on — either an adopted DataFrame or
        values already typed into the active worksheet (the Origin loop lets you
        plot straight from the sheet before clicking 'Use Active Data')."""
        resolver = getattr(self, "_resolve_active_dataframe", None)
        try:
            df = resolver() if callable(resolver) else getattr(self, "_df", None)
        except Exception:
            df = getattr(self, "_df", None)
        try:
            if df is not None and not df.empty:
                return True
        except Exception:
            if df is not None:
                return True
        wb = getattr(self, "workbook", None)
        checker = getattr(wb, "has_data_cells", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        return False

    def _has_graph_window(self) -> bool:
        """True when at least one Graph window exists."""
        tabs = getattr(self, "tabs", None)
        if tabs is None:
            return False
        try:
            return len(getattr(tabs, "tabs", {}) or {}) > 0
        except Exception:
            return False

    def _set_action_enabled(self, action, enabled: bool, reason: str) -> None:
        """Enable/disable an action, keeping a helpful tooltip when dimmed."""
        if action is None:
            return
        enabled = bool(enabled)
        try:
            base = action.property("_baseToolTip")
            if base is None:
                base = action.toolTip() or action.text() or ""
                action.setProperty("_baseToolTip", base)
            action.setEnabled(enabled)
            action.setToolTip(base if enabled else f"{base}  —  {reason}".strip(" —"))
        except Exception:
            logging.getLogger(__name__).debug(
                "action enablement failed", exc_info=True
            )

    def update_action_states(self) -> None:
        """Dim toolbar commands that cannot run yet (Origin behaviour).

        Data commands need an active Book with rows; graph tools need a Graph
        window. The single QAction object is shared across the top bar and the
        left/right/bottom docks, so dimming here dims every surface at once.
        """
        actions = getattr(self, "toolbar_actions", None)
        if not actions:
            return
        has_data = self._has_plot_data()
        has_graph = self._has_graph_window()
        for key, action in actions.items():
            if key in self._ACTIONS_NEED_DATA:
                self._set_action_enabled(
                    action, has_data, "Open or type data into a Book first"
                )
            elif key in self._ACTIONS_NEED_GRAPH:
                self._set_action_enabled(
                    action, has_graph, "Plot a graph first"
                )

    def _refresh_action_states(self) -> None:
        """Guarded convenience hook callers use after state changes."""
        fn = getattr(self, "update_action_states", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                logging.getLogger(__name__).debug(
                    "action state refresh failed", exc_info=True
                )

    def _wire_action_state_updates(self) -> None:
        """Connect Graph/Book signals so dimming tracks state live."""
        self._refresh_action_states()
        tabs = getattr(self, "tabs", None)
        for sig_name in ("tabCreated", "tabRemoved", "currentChanged"):
            sig = getattr(tabs, sig_name, None)
            if sig is not None:
                try:
                    sig.connect(lambda *_: self._refresh_action_states())
                except Exception:
                    logging.getLogger(__name__).debug(
                        "tab signal wiring for action states failed", exc_info=True
                    )
        mdi = getattr(self, "mdi", None)
        book_activated = getattr(mdi, "bookActivated", None)
        if book_activated is not None:
            try:
                book_activated.connect(lambda *_: self._refresh_action_states())
            except Exception:
                logging.getLogger(__name__).debug(
                    "book signal wiring for action states failed", exc_info=True
                )
        # Typing into the active worksheet should light up the plot bar even
        # before 'Use Active Data' is clicked (Origin loop).
        self._connect_workbook_state_signal(getattr(self, "workbook", None))

    def _connect_workbook_state_signal(self, workbook) -> None:
        """Re-evaluate action state whenever the worksheet's cells change."""
        table = getattr(workbook, "table", None)
        signal = getattr(table, "itemChanged", None)
        if signal is not None:
            try:
                signal.connect(lambda *_: self._refresh_action_states())
            except Exception:
                logging.getLogger(__name__).debug(
                    "workbook itemChanged wiring for action states failed",
                    exc_info=True,
                )
