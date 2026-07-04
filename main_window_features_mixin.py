from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog

from dialogs import AggregateDialog, ColumnTypeDialog, DerivedColumnDialog
from dialogs_units import UnitsDialog
from dialogs_report import ExportReportDialog
from report_generator import export_report
from processors import (
    add_time_bangkok, add_magnitude, add_moving_average, apply_column_types,
    compute_fft, beautify_axes, _infer_sampling_rate,
)
from analysis.cleaning import (
    FILL_METHODS, NORMALIZE_METHODS, OUTLIER_METHODS,
    detrend_polynomial, fill_missing, interpolate_missing, normalize_column,
    remove_duplicates, remove_outliers, resample_uniform, sort_dataframe,
)
from analysis.signal_filters import (
    BUTTER_KINDS, butterworth_filter, gaussian_smooth, median_filter,
    savitzky_golay, welch_psd,
)
from analysis.descriptive import covariance_matrix, describe_series, format_describe
from core.units import UNIT_REGISTRY
from core.plot_mode import PlotMode

if TYPE_CHECKING:  # shared MainWindow state this mixin relies on (set in MainWindow.__init__)
    _df: object
    _current_path: object
    _datasets: dict
    _fft_df: object
    _fft_meta: dict
    canvas: object
    plot_mode: object


class MainWindowFeaturesMixin:
    """Data feature/processor actions and report/units/derived dialogs extracted from MainWindow.

    Talks to the UI through the view-accessor seam (notify / inform / ask_choice /
    selected_*_column / add_*_column_option) rather than touching widgets directly.
    """

    def run_aggregate_dialog(self):
        if self._df is None or self._df.empty:
            self.inform("ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน"); return
        cols = [str(c) for c in self._df.columns]
        dlg = AggregateDialog(self, self._df, cols)
        if dlg.exec() != QDialog.Accepted:
            return
        params = dlg.get_params()
        id_col = params.get("id_col"); value_cols = params.get("value_cols", []); agg = params.get("agg", "sum"); stacked = bool(params.get("stacked", False))
        try:
            self._aggregate_and_plot(self._df, id_col=id_col, value_cols=value_cols, agg=agg, stacked=stacked)
        except Exception as e:
            self.error_box("Aggregate failed", f"Reason: {e}")

    # ---------- Features ----------
    def feature_add_bkk_time(self):
        if self._df is None or self.x_column_count() == 0:
            self.inform("ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน"); return
        x_col = self.selected_x_column()
        try:
            new_col = add_time_bangkok(self._df, x_col)
            self.add_x_column_option(new_col)
            self.notify(f"เพิ่มคอลัมน์เวลา (Bangkok) แล้ว: {new_col}")
        except Exception as e:
            self.error_box("ทำไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_add_magnitude(self):
        if self._df is None or self.y_column_count() == 0:
            self.inform("ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน"); return
        cols = [str(c) for c in self._df.columns]
        bx, ok = self.ask_choice("เลือกคอลัมน์ Bx", "Bx:", cols, 0)
        if not ok: return
        by, ok = self.ask_choice("เลือกคอลัมน์ By", "By:", cols, 0)
        if not ok: return
        bz, ok = self.ask_choice("เลือกคอลัมน์ Bz", "Bz:", cols, 0)
        if not ok: return
        try:
            new_col = add_magnitude(self._df, bx, by, bz, new_col="B_mag")
            self.add_y_column_option(new_col)
            self.notify(f"เพิ่มคอลัมน์ |B| แล้ว: {new_col}")
        except Exception as e:
            self.error_box("ทำไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_add_moving_average(self):
        if self._df is None or self.y_column_count() == 0:
            self.inform("ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน"); return
        y_col = self.selected_y_column()
        try:
            new_col = add_moving_average(self._df, y_col, window=25)
            self.add_y_column_option(new_col)
            self.notify(f"เพิ่มคอลัมน์ Moving Average แล้ว: {new_col}")
        except Exception as e:
            self.error_box("ทำไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_set_column_types(self):
        if self._df is None or len(self._df.columns) == 0:
            self.inform("ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน"); return
        dlg = ColumnTypeDialog(self, self._df.columns)
        if dlg.exec() != QDialog.Accepted:
            return
        mapping = dlg.get_mapping()
        try:
            apply_column_types(self._df, mapping)
            self.load_columns_from_df()
            # รีเฟรชกราฟหลังจากแปลงชนิดข้อมูล
            self.refresh_plot()
            self.notify("แปลงชนิดข้อมูลคอลัมน์เรียบร้อย")
        except Exception as e:
            self.error_box("แปลงไม่สำเร็จ", f"สาเหตุ: {e}")

    # ---------- Data cleaning (ROADMAP B) ----------
    def _has_y_data(self) -> bool:
        if self._df is None or getattr(self._df, "empty", True) or self.y_column_count() == 0:
            self.inform("ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน")
            return False
        return True

    def _swap_dataframe(self, new_df) -> None:
        """Replace the active DataFrame and refresh columns/worksheet views."""
        self._df = new_df
        for refresh in ("load_columns_from_df", "_refresh_workbook"):
            try:
                fn = getattr(self, refresh, None)
                if callable(fn):
                    fn()
            except Exception:
                import logging
                logging.getLogger(__name__).debug("%s failed after swap", refresh, exc_info=True)

    def feature_clean_fill_missing(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        method, ok = self.ask_choice("เติมค่าที่หาย (Fill Missing)", "วิธี:", list(FILL_METHODS), 1)
        if not ok:
            return
        value = None
        if method == "value":
            value, ok = self.ask_number("เติมค่าที่หาย", "ค่าที่ใช้เติม:", 0.0)
            if not ok:
                return
        try:
            new_col = fill_missing(self._df, y_col, method=method, value=value)
            self.add_y_column_option(new_col)
            self.notify(f"เติมค่าที่หายแล้ว: {new_col} (วิธี {method})")
        except Exception as e:
            self.error_box("เติมค่าไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_interpolate(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        try:
            new_col = interpolate_missing(self._df, y_col)
            self.add_y_column_option(new_col)
            self.notify(f"เติมค่าด้วย interpolation แล้ว: {new_col}")
        except Exception as e:
            self.error_box("Interpolate ไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_remove_duplicates(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน")
            return
        try:
            new_df, removed = remove_duplicates(self._df)
            self._swap_dataframe(new_df)
            self.notify(f"ลบแถวซ้ำแล้ว {removed} แถว (เหลือ {len(new_df)})")
        except Exception as e:
            self.error_box("ลบแถวซ้ำไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_remove_outliers(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        method, ok = self.ask_choice("ตัด Outliers", "วิธีตรวจ:", list(OUTLIER_METHODS), 0)
        if not ok:
            return
        default_thr = 3.0 if method == "zscore" else 1.5
        threshold, ok = self.ask_number("ตัด Outliers", "threshold:", default_thr, 0.1, 100.0, 2)
        if not ok:
            return
        try:
            new_df, removed = remove_outliers(self._df, y_col, method=method, threshold=threshold)
            self._swap_dataframe(new_df)
            self.notify(f"ตัด outliers ของ {y_col} แล้ว {removed} แถว (วิธี {method})")
        except Exception as e:
            self.error_box("ตัด outliers ไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_normalize(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        method, ok = self.ask_choice("Normalize / Standardize", "วิธี:", list(NORMALIZE_METHODS), 0)
        if not ok:
            return
        try:
            new_col = normalize_column(self._df, y_col, method=method)
            self.add_y_column_option(new_col)
            self.notify(f"สร้างคอลัมน์ normalize แล้ว: {new_col}")
        except Exception as e:
            self.error_box("Normalize ไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_detrend(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        order, ok = self.ask_int("Detrend / Baseline", "อันดับพหุนาม (1 = เชิงเส้น):", 1, 0, 10)
        if not ok:
            return
        x_col = self.selected_x_column()
        if x_col not in getattr(self._df, "columns", []):
            x_col = None
        try:
            new_col = detrend_polynomial(self._df, y_col, order=int(order), x_col=x_col)
            self.add_y_column_option(new_col)
            self.notify(f"ลบ baseline/trend อันดับ {order} แล้ว: {new_col}")
        except Exception as e:
            self.error_box("Detrend ไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_sort(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน")
            return
        cols = [str(c) for c in self._df.columns]
        col, ok = self.ask_choice("เรียงข้อมูล (Sort)", "ตามคอลัมน์:", cols, 0)
        if not ok:
            return
        direction, ok = self.ask_choice("เรียงข้อมูล", "ทิศทาง:", ["น้อย→มาก", "มาก→น้อย"], 0)
        if not ok:
            return
        try:
            new_df = sort_dataframe(self._df, col, ascending=(direction == "น้อย→มาก"))
            self._swap_dataframe(new_df)
            self.notify(f"เรียงข้อมูลตาม {col} แล้ว")
        except Exception as e:
            self.error_box("เรียงไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_resample(self):
        if not self._has_y_data():
            return
        x_col = self.selected_x_column()
        if x_col not in getattr(self._df, "columns", []):
            self.inform("เลือกแกน X ก่อน", "resample ต้องมีคอลัมน์ X ที่เป็นตัวเลข")
            return
        n_default = len(self._df)
        n_points, ok = self.ask_int("Resample", "จำนวนจุดบนกริดใหม่:", n_default, 2, 10_000_000)
        if not ok:
            return
        try:
            new_df = resample_uniform(self._df, x_col, n_points=int(n_points))
            self._swap_dataframe(new_df)
            self.notify(f"resample เป็นกริดสม่ำเสมอ {n_points} จุดแล้ว (คงเฉพาะคอลัมน์ตัวเลข)")
        except Exception as e:
            self.error_box("Resample ไม่สำเร็จ", f"สาเหตุ: {e}")

    # ---------- Signal filters (ROADMAP E) ----------
    def _sampling_rate_or_ask(self):
        """Infer fs from the selected X column, else prompt. None = cancelled."""
        try:
            x_col = self.selected_x_column()
            if x_col and x_col in getattr(self._df, "columns", []):
                fs = _infer_sampling_rate(self._df[x_col])
                if fs and fs > 0:
                    return float(fs)
        except Exception:
            import logging
            logging.getLogger(__name__).debug("fs inference failed", exc_info=True)
        fs, ok = self.ask_number("Sampling rate", "fs (Hz):", 100.0, 1e-9, 1e12, 6)
        return float(fs) if ok else None

    def feature_filter_butterworth(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        kind, ok = self.ask_choice("Butterworth Filter", "ชนิด:", list(BUTTER_KINDS), 0)
        if not ok:
            return
        fs = self._sampling_rate_or_ask()
        if fs is None:
            return
        if kind in ("bandpass", "bandstop"):
            lo, ok = self.ask_number("Butterworth Filter", "cutoff ต่ำ (Hz):", fs / 20, 1e-12, fs / 2, 6)
            if not ok:
                return
            hi, ok = self.ask_number("Butterworth Filter", "cutoff สูง (Hz):", fs / 5, 1e-12, fs / 2, 6)
            if not ok:
                return
            cutoff = (lo, hi)
        else:
            c, ok = self.ask_number("Butterworth Filter", "cutoff (Hz):", fs / 10, 1e-12, fs / 2, 6)
            if not ok:
                return
            cutoff = c
        try:
            filtered = butterworth_filter(self._df[y_col], fs, kind=kind, cutoff=cutoff)
            new_col = f"{y_col}_{kind}"
            self._df[new_col] = filtered
            self.add_y_column_option(new_col)
            self.notify(f"กรองสัญญาณ ({kind}) แล้ว: {new_col} (fs≈{fs:.4g} Hz)")
        except Exception as e:
            self.error_box("กรองไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_filter_smooth(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        method, ok = self.ask_choice(
            "Smooth", "วิธี:", ["savitzky-golay", "median", "gaussian"], 0
        )
        if not ok:
            return
        try:
            if method == "savitzky-golay":
                window, ok = self.ask_int("Savitzky-Golay", "ความยาวหน้าต่าง (คี่):", 11, 3, 9999)
                if not ok:
                    return
                smoothed = savitzky_golay(self._df[y_col], window_length=int(window))
                new_col = f"{y_col}_savgol"
            elif method == "median":
                kernel, ok = self.ask_int("Median Filter", "ขนาด kernel (คี่):", 5, 1, 9999)
                if not ok:
                    return
                smoothed = median_filter(self._df[y_col], kernel_size=int(kernel))
                new_col = f"{y_col}_median"
            else:
                sigma, ok = self.ask_number("Gaussian Filter", "sigma (จุด):", 2.0, 0.01, 1e6, 2)
                if not ok:
                    return
                smoothed = gaussian_smooth(self._df[y_col], sigma=float(sigma))
                new_col = f"{y_col}_gauss"
            self._df[new_col] = smoothed
            self.add_y_column_option(new_col)
            self.notify(f"smooth ({method}) แล้ว: {new_col}")
        except Exception as e:
            self.error_box("Smooth ไม่สำเร็จ", f"สาเหตุ: {e}")

    # ---------- Statistics & spectra (ROADMAP D/E) ----------
    def feature_show_statistics(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        try:
            stats = describe_series(self._df[y_col])
            self.inform(f"สถิติของ {y_col}", format_describe(stats, title=f"คอลัมน์: {y_col}"))
        except Exception as e:
            self.error_box("คำนวณสถิติไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_show_covariance(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน")
            return
        try:
            cov = covariance_matrix(self._df)
            self.inform("Covariance Matrix", cov.to_string(float_format=lambda v: f"{v:.6g}"))
        except Exception as e:
            self.error_box("คำนวณ covariance ไม่สำเร็จ", f"สาเหตุ: {e}")

    def run_psd_dialog(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_default = max(0, self.selected_y_index())
        y_col, ok = self.ask_choice("เลือกคอลัมน์ Y สำหรับ PSD", "Y:", cols, y_default)
        if not ok:
            return
        fs = self._sampling_rate_or_ask()
        if fs is None:
            return
        try:
            freqs, pxx = welch_psd(self._df[y_col], fs=fs)
            try:
                if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE:
                    self.canvas.clear()
            except Exception:
                pass
            self.canvas.ax.semilogy(freqs, pxx, linewidth=2)
            self.canvas.ax.set_xlabel("Frequency (Hz)")
            self.canvas.ax.set_ylabel("PSD")
            beautify_axes(self.canvas.ax, title=f"Welch PSD of {y_col} (fs≈{fs:.4g} Hz)")
            self.notify("คำนวณ PSD (Welch) เสร็จแล้ว")
        except Exception as e:
            self.error_box("PSD ไม่สำเร็จ", f"สาเหตุ: {e}")

    def run_fft_dialog(self):
        if self._df is None or self.x_column_count() == 0 or self.y_column_count() == 0:
            self.inform("ยังไม่มีข้อมูล", "โปรดเปิดไฟล์และกด 'โหลดคอลัมน์จากข้อมูล' ก่อน")
            return

        cols = [str(c) for c in self._df.columns]
        y_default = max(0, self.selected_y_index())
        y_col, ok = self.ask_choice("เลือกคอลัมน์ Y สำหรับ FFT", "Y:", cols, y_default)
        if not ok: return

        window, ok = self.ask_choice("หน้าต่าง (window)", "ชนิด:", ["hanning", "hamming", "none"], 0)
        if not ok: return
        detrend_choice, ok = self.ask_choice("ลบค่าเฉลี่ยก่อนคำนวณ?", "detrend:", ["True", "False"], 0)
        if not ok: return
        detrend = (detrend_choice == "True")

        x_col = self.selected_x_column()

        try:
            df_fft, fs = compute_fft(self._df, x_col=x_col, y_col=y_col, detrend=detrend, window=window)
            self._fft_df = df_fft
            self._fft_meta = {"fs": fs, "x_col": x_col, "y_col": y_col, "window": window, "detrend": detrend}

            try:
                if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE:
                    self.canvas.clear()
            except Exception:
                pass
            self.canvas.ax.plot(df_fft["freq_Hz"].values, df_fft["amplitude"].values, linewidth=2)
            self.canvas.ax.set_xlabel("Frequency (Hz)")
            self.canvas.ax.set_ylabel("Amplitude")
            beautify_axes(self.canvas.ax, title=f"FFT of {y_col} (fs≈{fs:.3f} Hz, window={window}, detrend={detrend})")
            self.notify("คำนวณ FFT เสร็จแล้ว • ใช้ Export FFT เพื่อบันทึกผลได้")

        except Exception as e:
            self.error_box("FFT ไม่สำเร็จ", f"สาเหตุ: {e}")

    def on_export_report(self):
        """Export a comprehensive report to PDF containing data analysis and plots"""
        if self._df is None:
            self.warn("ไม่มีข้อมูล", "โปรดเปิดไฟล์ข้อมูลก่อน")
            return

        if not hasattr(self.canvas, 'fig') or not self.canvas.fig:
            self.warn("ไม่มีกราฟ", "โปรดสร้างกราฟก่อน")
            return

        # Show Export Report Dialog
        dialog = ExportReportDialog(self._df, self)
        if dialog.exec() != QDialog.Accepted:
            return

        # Get options from dialog
        options = dialog.get_options()

        # Validate options
        if not options["include_meta"] and not options["include_stats"] and not options["include_fig"]:
            self.warn("ไม่มีการเลือกเนื้อหา", "โปรดเลือกเนื้อหาอย่างน้อยหนึ่งอย่าง")
            return

        # Get save path from user
        path = self.ask_save_path("บันทึกรายงานเป็น PDF", "sciplotter_report.pdf", "PDF Document (*.pdf)")

        if not path:
            return

        try:
            # Prepare metadata with more information
            meta = {
                'filename': os.path.basename(self._current_path) if self._current_path else 'Unknown',
                'columns_used': []
            }

            # Get columns used for plotting if available
            if self.selected_x_column():
                meta['columns_used'].append(self.selected_x_column())
            if self.selected_y_column():
                meta['columns_used'].append(self.selected_y_column())

            # Add more metadata if available
            if hasattr(self, '_datasets') and self._current_path:
                for name, data in self._datasets.items():
                    if data.get('path') == self._current_path:
                        meta['dataset_name'] = name
                        break

            # Generate report with options
            success = export_report(
                fig=self.canvas.fig,
                df=self._df,
                meta=meta,
                save_path=path,
                options=options
            )

            if success:
                self.notify(f"บันทึกรายงานแล้ว: {path}")
                self.inform("สำเร็จ", f"บันทึกรายงานแล้ว:\n{path}")
            else:
                self.error_box("บันทึกไม่สำเร็จ", "เกิดข้อผิดพลาดในการสร้างรายงาน")

        except Exception as e:
            self.error_box("บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

    def open_units_dialog(self):
        """Open units and calibration dialog"""
        if self._df is None or self._df.empty:
            self.warn("No Data", "ยังไม่มีข้อมูล")
            return

        try:
            dlg = UnitsDialog(self._df, self)
            if dlg.exec():
                mapping = dlg.result  # {col: {dim, from_unit, to_unit, a, b}}

                # Apply transformations
                df_new = self._df.copy()
                from core.units import apply_to_dataframe

                for col, cfg in mapping.items():
                    if col in df_new.columns:
                        # Get the units
                        from_unit = UNIT_REGISTRY.find_unit(cfg['from_unit'])
                        to_unit = UNIT_REGISTRY.find_unit(cfg['to_unit'])

                        if from_unit and to_unit:
                            # Generate new column name
                            new_col = f"{col} ({cfg['to_unit']})"

                            # Apply transformation
                            df_new = apply_to_dataframe(
                                df_new, column=col,
                                a=cfg["a"], b=cfg["b"],
                                unit_from=from_unit, unit_to=to_unit,
                                new_col=new_col
                            )

                # Update dataframe
                self._df = df_new

                # Store units mapping in metadata
                if not hasattr(self, 'meta'):
                    self.meta = {}
                self.meta.setdefault("units", {})
                self.meta["units"].update(mapping)

                # Refresh display
                self.refresh_plot()
                if hasattr(self, "refresh_stats"):
                    self.refresh_stats()

                self.inform("Done", "แปลงหน่วยและสอบเทียบเรียบร้อย (สร้างคอลัมน์ใหม่)")

        except Exception as e:
            self.error_box("Error", f"เกิดข้อผิดพลาด: {str(e)}")

    def open_derived_column_dialog(self):
        """เปิด dialog สำหรับสร้างคอลัมน์ใหม่จากนิพจน์ทางคณิตศาสตร์"""
        # ตรวจสอบว่ามีข้อมูลหรือไม่
        if self._df is None or self._df.empty:
            self.warn("ไม่มีข้อมูล", "กรุณาโหลดข้อมูลก่อนสร้างคอลัมน์ใหม่")
            return

        try:
            # เปิด DerivedColumnDialog
            dlg = DerivedColumnDialog(self, self._df)

            # รอให้ผู้ใช้ป้อนข้อมูลและกด Apply
            if dlg.exec() == QDialog.Accepted:
                # Dialog จะสร้างคอลัมน์ใหม่ใน self._df โดยตรง
                # ดังนั้นเราต้องรีเฟรชการแสดงผลเท่านั้น

                # รีเฟรชกราฟ
                self.refresh_plot()

                # รีเฟรชสถิติถ้ามี
                if hasattr(self, "refresh_stats"):
                    self.refresh_stats()

                # แสดงข้อความสำเร็จ
                self.inform(
                    "สำเร็จ",
                    "สร้างคอลัมน์ใหม่เรียบร้อยแล้ว\nกราฟจะอัปเดตอัตโนมัติ"
                )

        except Exception as e:
            # แสดงข้อผิดพลาดถ้าเกิดปัญหา
            self.error_box(
                "ข้อผิดพลาด",
                f"ไม่สามารถเปิด dialog สร้างคอลัมน์ใหม่ได้:\n{str(e)}"
            )
