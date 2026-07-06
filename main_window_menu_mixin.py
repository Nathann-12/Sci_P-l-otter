from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMessageBox, QStyle

from core.plot_data import clamp_date_limits as _clamp_date_limits
from core.plot_mode import PlotMode
from charts_gallery import ChartGalleryMenu
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

    def _init_menu(self):
        m = self.menuBar()
        fileMenu = m.addMenu("&File")  # UI-REFINE: File
        self.actOpen = fileMenu.addAction("Open Data (CSV/Excel/JSON/HDF5/MAT/XML/NC/CDF)...")
        self.actOpen.triggered.connect(lambda: getattr(self, 'open_file', lambda: None)())
        actBatch = fileMenu.addAction("Open Multiple Files (Batch Import)…")
        actBatch.triggered.connect(lambda: getattr(self, 'stage_add_files', lambda: None)())
        fileMenu.addSeparator()
        # Export PNG lives in the Export menu (not duplicated here — on_action_export_figure calls the same export_png)
        actExit = fileMenu.addAction("Exit"); actExit.triggered.connect(self.close)

        viewMenu = m.addMenu("&View")
        actReset = viewMenu.addAction("Reset View")
        actReset.triggered.connect(lambda: [self.canvas.ax.set_xlim(auto=True), self.canvas.ax.set_ylim(auto=True), self.canvas.draw()])
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

        self.dataMenu = m.addMenu("&Data")  # units, calibration, derived column

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
        actAddLine = plotMenu.addAction("Add Line (overlay)")
        actAddScatter = plotMenu.addAction("Add Scatter (overlay)")
        try:
            actAddLine.setShortcut("Ctrl+Shift+L")
            actAddScatter.setShortcut("Ctrl+Shift+S")
        except Exception:
            pass
        actAddLine.triggered.connect(self.add_line_overlay)
        actAddScatter.triggered.connect(self.add_scatter_overlay)
        if hasattr(self, 'actPlotEquation'):
            plotMenu.addAction(self.actPlotEquation)
        else:
            self.actPlotEquation = plotMenu.addAction('Plot from Equation...')
            self.actPlotEquation.triggered.connect(self.on_plot_from_equation)
            try:
                self.actPlotEquation.setIcon(self._icon('Plot_from_Equation', QStyle.StandardPixmap.SP_DialogApplyButton))
            except Exception:
                pass
        self.dataMenu.addAction("Units & Calibration…").triggered.connect(self.open_units_dialog)
        # Derived column (moved here from plotcore); Ctrl+Shift+D so it does not
        # clash with Ctrl+D of Peak "Detect in Range"
        if not hasattr(self, "_actDataDerived"):
            self._actDataDerived = self.dataMenu.addAction("Create Column (Derived)…")
            self._actDataDerived.setShortcut("Ctrl+Shift+D")
            self._actDataDerived.triggered.connect(self.open_derived_column_dialog)

        procMenu = m.addMenu("&Process")  # UI-REFINE: Process
        procMenu.addAction("FFT").triggered.connect(self.run_fft_dialog)
        procMenu.addAction("PSD (Welch)…").triggered.connect(self.run_psd_dialog)
        procMenu.addAction("Moving Average").triggered.connect(self.feature_add_moving_average)
        procMenu.addAction("Add |B|").triggered.connect(self.feature_add_magnitude)
        procMenu.addAction("Add Bangkok Time").triggered.connect(self.feature_add_bkk_time)
        procMenu.addAction("Aggregate…").triggered.connect(self.run_aggregate_dialog)  # UI-REFINE

        # Data cleaning (ROADMAP B) — column ops add a new column; row ops swap the df
        procMenu.addSeparator()
        cleanMenu = procMenu.addMenu("Data Cleaning")
        cleanMenu.addAction("Fill Missing…").triggered.connect(self.feature_clean_fill_missing)
        cleanMenu.addAction("Interpolate Missing").triggered.connect(self.feature_clean_interpolate)
        cleanMenu.addAction("Remove Duplicates").triggered.connect(self.feature_clean_remove_duplicates)
        cleanMenu.addAction("Remove Outliers…").triggered.connect(self.feature_clean_remove_outliers)
        cleanMenu.addAction("Normalize / Standardize…").triggered.connect(self.feature_clean_normalize)
        cleanMenu.addAction("Detrend / Baseline…").triggered.connect(self.feature_clean_detrend)
        cleanMenu.addAction("Sort…").triggered.connect(self.feature_clean_sort)
        cleanMenu.addAction("Resample (uniform grid)…").triggered.connect(self.feature_clean_resample)

        # Signal filters (ROADMAP E)
        filterMenu = procMenu.addMenu("Filters")
        filterMenu.addAction("Butterworth (Low/High/Band)…").triggered.connect(self.feature_filter_butterworth)
        filterMenu.addAction("Smooth (Savitzky-Golay/Median/Gaussian)…").triggered.connect(self.feature_filter_smooth)
        filterMenu.addAction("Apply Window (Hann/Hamming/Blackman/Kaiser)…").triggered.connect(self.feature_apply_window)

        exportMenu = m.addMenu("&Export")  # UI-REFINE: Export
        exportMenu.addAction("Export Visible CSV").triggered.connect(self.export_visible_range_csv)
        exportMenu.addAction("Export PNG").triggered.connect(self.export_png)
        exportMenu.addSeparator()
        exportMenu.addAction("Export Report (PDF)...").triggered.connect(self.on_export_report)

        toolsMenu = m.addMenu("&Tools")  # UI-REFINE: Tools
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
        # อัปเดตช็อตคัตให้ครอบคลุมฟีเจอร์ใหม่ (Annotation/Analysis)
        # คีย์ลัดจริงที่ลงทะเบียนในแอป (ตรวจให้ตรงกับ setShortcut จริง)
        help_shortcuts = (
            "[ทั่วไป]\n"
            "Ctrl+O: เปิดไฟล์\n"
            "Ctrl+K: Command Palette (ค้นหาคำสั่ง)\n"
            "Ctrl+, : ตั้งค่า (Settings)\n"
            "Ctrl+Shift+D: สร้างคอลัมน์ใหม่ (Derived Column)\n"
            "\n[Plot]\n"
            "Ctrl+Shift+L: เพิ่มเส้นลงกราฟปัจจุบัน (overlay)\n"
            "Ctrl+Shift+S: เพิ่มจุดลงกราฟปัจจุบัน (overlay)\n"
            "\n[Annotation]\n"
            "T/W/L/R/E/C: Text/Arrow/Line/Rect/Ellipse/Callout\n"
            "Ctrl+Z / Ctrl+Y: Undo / Redo\n"
            "\n[Analysis]\n"
            "Ctrl+Shift+X: สลับโหมด Multi-Cursor\n"
            "Ctrl+Shift+P: สลับ Peak Detection\n"
            "Ctrl+D: ตรวจจับพีคในช่วง\n"
            "Ctrl+E: ส่งออกตารางพีค (CSV/Excel)"
        )

        # Charts gallery menu (Excel-like)
        try:
            import pandas as _pd
            def _cg_get_df():
                df = getattr(self, "_df", None)
                return df if df is not None else _pd.DataFrame()
            def _cg_get_fig():
                try:
                    if getattr(self, "canvas", None) and hasattr(self.canvas, "fig"):
                        return self.canvas.fig
                except Exception:
                    pass
                try:
                    tab = self.tabs.currentWidget()
                    return tab.get_figure()
                except Exception:
                    # Last resort: create a temporary Figure (won't show on canvas)
                    from matplotlib.figure import Figure as _Figure
                    return _Figure()
            charts_menu = ChartGalleryMenu(get_dataframe=_cg_get_df, get_main_figure=_cg_get_fig, apply_plot=self.apply_plot, parent=self)
            m.addMenu(charts_menu)
        except Exception:
            pass

        helpMenu.addAction("Shortcuts").triggered.connect(lambda: QMessageBox.information(self, "Shortcuts", help_shortcuts))

        # === Analysis Menu ===
        analysisMenu = m.addMenu("&Analysis")

        # Cross-Correlation submenu
        ccMenu = analysisMenu.addMenu("Cross-Correlation")
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
        pkMenu = analysisMenu.addMenu("Peak Detection")
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
                self.annMenu = m.addMenu("&Annotation")
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
