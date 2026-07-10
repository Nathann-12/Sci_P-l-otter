from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from core.export_request import (
    BatchFigureExportOptions,
    ExportSeries,
    FigureExportOptions,
    VisibleRangeExportRequest,
    batch_export_filename,
    dataframe_for_visible_range,
    line_to_numeric,
)


class MainWindowExportMixin:
    """Reusable export actions extracted from MainWindow."""

    def export_aggregated_csv(self):
        if getattr(self, "current_aggregated_df", None) is None:
            QMessageBox.information(self, "No Aggregate result", "Please run Aggregate first")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Aggregate result as CSV",
            "aggregate.csv",
            "CSV (*.csv)",
        )
        if not path:
            return
        try:
            self.current_aggregated_df.to_csv(path, index=False)
            self.statusBar().showMessage(f"Aggregate CSV saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"Reason: {e}")

    def export_fft_dialog(self):
        if self._fft_df is None or self._fft_df.empty:
            QMessageBox.information(self, "ยังไม่มีผล FFT", "โปรดคำนวณ FFT ก่อน (ปุ่ม FFT)")
            return

        kind, ok = QInputDialog.getItem(
            self,
            "เลือกชนิดไฟล์",
            "บันทึกเป็น:",
            ["CSV (.csv)", "Excel (.xlsx)", "NetCDF (.nc)"],
            0,
            False,
        )
        if not ok:
            return

        if kind.startswith("CSV"):
            path, _ = QFileDialog.getSaveFileName(
                self,
                "บันทึกผล FFT เป็น CSV",
                "fft_result.csv",
                "CSV (*.csv)",
            )
            if not path:
                return
            try:
                self._fft_df.to_csv(path, index=False)
                self.statusBar().showMessage(f"CSV saved: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Reason: {e}")

        elif kind.startswith("Excel"):
            path, _ = QFileDialog.getSaveFileName(
                self,
                "บันทึกผล FFT เป็น Excel",
                "fft_result.xlsx",
                "Excel (*.xlsx)",
            )
            if not path:
                return
            try:
                with pd.ExcelWriter(path) as w:
                    self._fft_df.to_excel(w, sheet_name="FFT", index=False)
                    meta = pd.DataFrame([self._fft_meta])
                    meta.to_excel(w, sheet_name="meta", index=False)
                self.statusBar().showMessage(f"Excel saved: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Reason: {e}")

        else:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "บันทึกผล FFT เป็น NetCDF",
                "fft_result.nc",
                "NetCDF (*.nc)",
            )
            if not path:
                return
            try:
                import xarray as xr

                ds = xr.Dataset(
                    data_vars=dict(
                        amplitude=("freq_Hz", self._fft_df["amplitude"].values),
                        power=("freq_Hz", self._fft_df["power"].values),
                    ),
                    coords=dict(
                        freq_Hz=("freq_Hz", self._fft_df["freq_Hz"].values),
                    ),
                    attrs=dict(**self._fft_meta),
                )
                ds.to_netcdf(path)
                self.statusBar().showMessage(f"NetCDF saved: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Reason: {e}")

    def _line_to_numeric_for_export(self, values):
        return line_to_numeric(values)

    def build_visible_range_export_request(self) -> VisibleRangeExportRequest | None:
        dataframe = self.get_current_dataframe()
        x_column = self.selected_x_column()
        axes = self.active_axes()
        if dataframe.empty or not x_column or x_column not in dataframe.columns or axes is None:
            return None
        lower, upper = axes.get_xlim()
        series = tuple(
            ExportSeries(
                x=line.get_xdata(orig=False),
                y=line.get_ydata(orig=False),
                label=line.get_label() or "",
            )
            for line in axes.get_lines()
        )
        return VisibleRangeExportRequest(
            dataframe=dataframe,
            x_column=x_column,
            lower=lower,
            upper=upper,
            series=series,
        )

    def export_visible_range_csv(
        self,
        request: VisibleRangeExportRequest | None = None,
    ):
        request = request or self.build_visible_range_export_request()
        if request is None:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน")
            return
        df_view = dataframe_for_visible_range(request)
        if df_view.empty:
            QMessageBox.information(self, "ไม่มีข้อมูลในช่วงนี้", "ช่วงที่แสดงอยู่ไม่มีข้อมูลให้ส่งออก")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "บันทึกช่วงที่เห็นเป็น CSV",
            "view_range.csv",
            "CSV (*.csv)",
        )
        if not path:
            return
        try:
            df_view.to_csv(path, index=False)
            self.statusBar().showMessage(f"Visible range CSV saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"Reason: {e}")

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save image as",
            "plot.png",
            "PNG Image (*.png)",
        )
        if not path:
            return
        try:
            self._export_target_figure().savefig(path, dpi=300, bbox_inches="tight")
            self.statusBar().showMessage(f"Image saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"Reason: {e}")

    # ---------------- advanced export (ROADMAP C) ----------------
    _EXPORT_FORMATS = {
        "PNG": ("png", "PNG Image (*.png)"),
        "PDF": ("pdf", "PDF Document (*.pdf)"),
        "SVG": ("svg", "SVG Vector (*.svg)"),
        "TIFF": ("tiff", "TIFF Image (*.tiff)"),
        "EPS": ("eps", "EPS Vector (*.eps)"),
    }

    def _export_target_figure(self):
        """The active graph's figure (Origin multi-graph), else the legacy canvas."""
        try:
            tab = self.tabs.currentWidget()
            if tab is not None and hasattr(tab, "get_figure"):
                canvas = getattr(tab, "canvas", None)
                if canvas is not None:
                    self.canvas = canvas
                return tab.get_figure()
        except Exception:
            pass
        return self.canvas.fig

    @staticmethod
    def _figure_has_exportable_content(fig) -> bool:
        try:
            for ax in fig.axes:
                if (
                    getattr(ax, "lines", None)
                    or getattr(ax, "collections", None)
                    or getattr(ax, "patches", None)
                    or getattr(ax, "images", None)
                    or getattr(ax, "containers", None)
                    or getattr(ax, "texts", None)
                ):
                    return True
        except Exception:
            return False
        return False

    def _save_figure_with_options(
        self,
        fig,
        path: str,
        ext: str,
        options: FigureExportOptions | BatchFigureExportOptions,
        print_spec: dict | None = None,
    ) -> None:
        saved_size = fig.get_size_inches().copy()
        try:
            if print_spec and print_spec.get("width_in"):
                fig.set_size_inches(
                    float(print_spec["width_in"]),
                    float(print_spec.get("height_in") or saved_size[1]),
                )
            fig.savefig(
                path,
                format=ext,
                dpi=options.dpi,
                transparent=options.transparent,
                bbox_inches="tight" if options.tight else None,
            )
        finally:
            try:
                fig.set_size_inches(*saved_size)
                fig.canvas.draw_idle()
            except Exception:
                pass

    def export_figure_advanced(self):
        """Export the active graph with a chosen format / DPI / transparency."""
        fig = self._export_target_figure()
        if fig is None:
            self.inform("No graph", "Open or select a graph window first")
            return
        res = self.ask_form("Export Figure", [
            {"name": "fmt", "label": "Format", "kind": "choice",
             "options": list(self._EXPORT_FORMATS.keys()), "default": "PNG"},
            {"name": "dpi", "label": "DPI (raster)", "kind": "int",
             "default": 300, "min": 30, "max": 2400},
            {"name": "transparent", "label": "Transparent background",
             "kind": "bool", "default": False},
            {"name": "tight", "label": "Tight bounding box", "kind": "bool", "default": True},
        ], description="Save the active graph (vector formats ignore DPI)")
        if res is None:
            return
        options = FigureExportOptions(
            format_name=res["fmt"],
            dpi=int(res["dpi"]),
            transparent=bool(res["transparent"]),
            tight=bool(res["tight"]),
        )
        ext, filt = self._EXPORT_FORMATS[options.format_name]
        path = self.ask_save_path(
            f"Export as {options.format_name}", f"figure.{ext}", filt
        )
        if not path:
            return
        # honor a print size chosen in Plot Details (Figure tab) — applied only
        # around savefig so the on-screen graph is never disturbed
        print_spec = getattr(self.tabs.currentWidget(), "_print_figure", None) \
            if hasattr(self, "tabs") else None
        try:
            self._save_figure_with_options(fig, path, ext, options, print_spec)
            self.notify(f"Exported {options.format_name}: {path}")
        except Exception as e:
            self.error_box("Export failed", f"Reason: {e}")

    def _iter_export_graph_targets(self, include_empty: bool = False):
        """Yield (title, tab, figure) for open Graph windows in workspace order."""
        try:
            open_tabs = list(self.tabs.get_open_tabs())
            tab_map = getattr(self.tabs, "tabs", {})
        except Exception:
            open_tabs = []
            tab_map = {}

        if not open_tabs and hasattr(self, "tabs"):
            try:
                tab_map = getattr(self.tabs, "tabs", {})
                open_tabs = [
                    (getattr(tab, "tab_id", f"tab_{index + 1}"), self.tabs.tabText(index))
                    for index, tab in enumerate(tab_map.values())
                ]
            except Exception:
                open_tabs = []

        for tab_id, title in open_tabs:
            tab = tab_map.get(tab_id)
            if tab is None:
                continue
            try:
                fig = tab.get_figure()
            except Exception:
                fig = getattr(getattr(tab, "canvas", None), "fig", None)
            if fig is None:
                continue
            if include_empty or self._figure_has_exportable_content(fig):
                yield title or tab_id, tab, fig

    def export_figures_batch(self):
        """Export every open Graph window to one directory."""
        res = self.ask_form("Batch Export Graphs", [
            {"name": "fmt", "label": "Format", "kind": "choice",
             "options": list(self._EXPORT_FORMATS.keys()), "default": "PNG"},
            {"name": "dpi", "label": "DPI (raster)", "kind": "int",
             "default": 300, "min": 30, "max": 2400},
            {"name": "transparent", "label": "Transparent background",
             "kind": "bool", "default": False},
            {"name": "tight", "label": "Tight bounding box", "kind": "bool", "default": True},
            {"name": "include_empty", "label": "Include empty graphs",
             "kind": "bool", "default": False},
        ], description="Save all open Graph windows to a folder")
        if res is None:
            return

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select batch export folder",
            "",
        )
        if not directory:
            return

        options = BatchFigureExportOptions(
            format_name=res["fmt"],
            directory=directory,
            dpi=int(res["dpi"]),
            transparent=bool(res["transparent"]),
            tight=bool(res["tight"]),
            include_empty=bool(res.get("include_empty", False)),
        )
        ext, _filt = self._EXPORT_FORMATS[options.format_name]
        targets = list(self._iter_export_graph_targets(include_empty=options.include_empty))
        if not targets:
            self.inform("No graphs", "No graph windows with plot content were found.")
            return

        saved = []
        failed = []
        for index, (title, tab, fig) in enumerate(targets, start=1):
            path = batch_export_filename(options.directory, title, index, ext)
            try:
                self._save_figure_with_options(
                    fig,
                    str(path),
                    ext,
                    options,
                    getattr(tab, "_print_figure", None),
                )
                saved.append(path)
            except Exception as exc:
                failed.append((title, exc))

        if failed:
            details = "\n".join(f"{title}: {exc}" for title, exc in failed[:5])
            self.error_box(
                "Batch export failed",
                f"Saved {len(saved)} graph(s), failed {len(failed)}.\n{details}",
            )
            return
        self.notify(f"Exported {len(saved)} graph(s) to {options.directory}")

    def copy_figure_to_clipboard(self):
        """Copy the active graph to the clipboard as an image."""
        import io
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication

        fig = self._export_target_figure()
        if fig is None:
            self.inform("No graph", "Open or select a graph window first")
            return
        try:
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
            image = QImage.fromData(buf.getvalue(), "PNG")
            QApplication.clipboard().setImage(image)
            self.notify("Graph copied to clipboard")
        except Exception as e:
            self.error_box("Copy failed", f"Reason: {e}")
