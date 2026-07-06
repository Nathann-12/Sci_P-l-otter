from __future__ import annotations

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox


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
                self.statusBar().showMessage(f"บันทึก CSV แล้ว: {path}")
            except Exception as e:
                QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

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
                self.statusBar().showMessage(f"บันทึก Excel แล้ว: {path}")
            except Exception as e:
                QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

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
                self.statusBar().showMessage(f"บันทึก NetCDF แล้ว: {path}")
            except Exception as e:
                QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

    def _line_to_numeric_for_export(self, values):
        import matplotlib.dates as mdates

        arr = np.asarray(values)
        if arr.size == 0:
            return arr.astype(float), False
        if np.issubdtype(arr.dtype, np.number):
            return arr.astype(float), False
        numeric = pd.to_numeric(arr, errors="coerce")
        if hasattr(numeric, "to_numpy"):
            numeric_arr = numeric.to_numpy()
        else:
            numeric_arr = np.asarray(numeric, dtype=float)
        if numeric_arr.size and np.isfinite(numeric_arr).any():
            return numeric_arr, False
        dt_series = pd.Series(pd.to_datetime(arr, errors="coerce"))
        valid = dt_series.notna()
        if not valid.any():
            return numeric_arr, False
        numeric_arr = np.full(len(dt_series), np.nan, dtype=float)
        numeric_arr[valid.to_numpy()] = mdates.date2num(dt_series[valid].to_numpy(dtype="datetime64[ns]"))
        return numeric_arr, True

    def export_visible_range_csv(self):
        if self._df is None or self.cbX.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน")
            return

        ax = self.canvas.ax
        xmin, xmax = ax.get_xlim()

        xcol = self.cbX.currentText()
        xser = self._df[xcol]

        df_view = None
        lower = min(xmin, xmax)
        upper = max(xmin, xmax)
        use_datetime = False
        x_dt = None
        try:
            if pd.api.types.is_datetime64_any_dtype(xser):
                use_datetime = True
                x_dt = pd.to_datetime(xser, errors="coerce")
            else:
                if pd.api.types.is_object_dtype(xser) or pd.api.types.is_string_dtype(xser):
                    candidate = pd.to_datetime(xser, errors="coerce")
                    if candidate.notna().any():
                        x_dt = candidate
                        use_datetime = True
            if use_datetime and x_dt is not None:
                import matplotlib.dates as mdates

                valid = x_dt.notna() if hasattr(x_dt, "notna") else ~pd.isna(x_dt)
                if np.any(valid):
                    valid_mask = valid.to_numpy() if hasattr(valid, "to_numpy") else np.asarray(valid)
                    xnum = np.full(len(xser), np.nan, dtype=float)
                    dt_values = x_dt[valid] if hasattr(x_dt, "__getitem__") else np.asarray(x_dt)[valid_mask]
                    dt_series = pd.Series(dt_values)
                    dt_series = pd.to_datetime(dt_series, errors="coerce")
                    xnum[valid_mask] = mdates.date2num(dt_series.to_numpy(dtype="datetime64[ns]"))
                    mask = np.isfinite(xnum) & (xnum >= lower) & (xnum <= upper)
                    if mask.any():
                        df_view = self._df.loc[mask].copy()
                else:
                    use_datetime = False
            if df_view is None:
                xnum = pd.to_numeric(xser, errors="coerce")
                xarr = xnum.to_numpy() if hasattr(xnum, "to_numpy") else np.asarray(xnum)
                mask = np.isfinite(xarr) & (xarr >= lower) & (xarr <= upper)
                if mask.any():
                    df_view = self._df.loc[mask].copy()
        except Exception:
            xnum = pd.to_numeric(xser, errors="coerce")
            xarr = xnum.to_numpy() if hasattr(xnum, "to_numpy") else np.asarray(xnum)
            mask = np.isfinite(xarr) & (xarr >= lower) & (xarr <= upper)
            df_view = self._df.loc[mask].copy()

        if df_view is None or df_view.empty:
            fallback_df = None
            fallback_use_datetime = use_datetime
            try:
                import matplotlib.dates as mdates

                for i, ln in enumerate(ax.get_lines()):
                    x_raw = ln.get_xdata(orig=False)
                    y_raw = ln.get_ydata(orig=False)
                    x_numeric, line_is_datetime = self._line_to_numeric_for_export(x_raw)
                    if x_numeric.size == 0:
                        continue
                    y_arr = np.asarray(y_raw)
                    if y_arr.size == 0:
                        continue
                    mask_line = np.isfinite(x_numeric) & (x_numeric >= lower) & (x_numeric <= upper)
                    if not mask_line.any():
                        continue
                    x_filtered = x_numeric[mask_line]
                    y_filtered = y_arr[mask_line]
                    label = (
                        ln.get_label()
                        if ln.get_label() and not ln.get_label().startswith("_")
                        else f"y{i + 1}"
                    )
                    line_df = pd.DataFrame({"__x__": x_filtered, label: y_filtered})
                    if fallback_df is None:
                        fallback_df = line_df
                    else:
                        fallback_df = pd.merge(fallback_df, line_df, on="__x__", how="outer")

                    fallback_use_datetime = fallback_use_datetime or line_is_datetime

                if fallback_df is not None and not fallback_df.empty:
                    fallback_df.sort_values("__x__", inplace=True)
                    fallback_df.reset_index(drop=True, inplace=True)
                    if fallback_use_datetime:
                        dt_series = pd.Series(
                            pd.to_datetime(mdates.num2date(fallback_df["__x__"].to_numpy()))
                        )
                        try:
                            dt_series = dt_series.dt.tz_localize(None)
                        except (TypeError, AttributeError, ValueError):
                            pass
                        fallback_df[xcol] = dt_series.to_numpy()
                    else:
                        fallback_df[xcol] = fallback_df["__x__"]
                    ordered_cols = [xcol] + [c for c in fallback_df.columns if c not in {"__x__", xcol}]
                    df_view = fallback_df[ordered_cols]
            except Exception:
                pass

        if df_view is None or df_view.empty:
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
            self.statusBar().showMessage(f"บันทึก CSV ช่วงที่เห็นแล้ว: {path}")
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
                return tab.get_figure()
        except Exception:
            pass
        return self.canvas.fig

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
        ext, filt = self._EXPORT_FORMATS[res["fmt"]]
        path = self.ask_save_path(f"Export as {res['fmt']}", f"figure.{ext}", filt)
        if not path:
            return
        # honor a print size chosen in Plot Details (Figure tab) — applied only
        # around savefig so the on-screen graph is never disturbed
        saved_size = fig.get_size_inches().copy()
        print_spec = getattr(self.tabs.currentWidget(), "_print_figure", None) \
            if hasattr(self, "tabs") else None
        try:
            if print_spec and print_spec.get("width_in"):
                fig.set_size_inches(float(print_spec["width_in"]),
                                    float(print_spec.get("height_in") or saved_size[1]))
            fig.savefig(
                path, format=ext, dpi=int(res["dpi"]),
                transparent=bool(res["transparent"]),
                bbox_inches="tight" if res["tight"] else None)
            self.notify(f"Exported {res['fmt']}: {path}")
        except Exception as e:
            self.error_box("Export failed", f"Reason: {e}")
        finally:
            try:
                fig.set_size_inches(*saved_size)
                fig.canvas.draw_idle()
            except Exception:
                pass

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
