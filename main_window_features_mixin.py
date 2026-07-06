from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pandas as pd
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
    BUTTER_KINDS, WINDOW_KINDS, apply_window, butterworth_filter, estimate_snr,
    fwhm, gaussian_smooth, median_filter, noise_floor, peak_area,
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
        res = self.ask_form("เพิ่มคอลัมน์ |B| จาก 3 แกน", [
            {"name": "bx", "label": "แกน X (Bx)", "kind": "choice", "options": cols,
             "default": cols[0]},
            {"name": "by", "label": "แกน Y (By)", "kind": "choice", "options": cols,
             "default": cols[1] if len(cols) > 1 else cols[0]},
            {"name": "bz", "label": "แกน Z (Bz)", "kind": "choice", "options": cols,
             "default": cols[2] if len(cols) > 2 else cols[0]},
        ], description="สร้างคอลัมน์ขนาดเวกเตอร์ |B| = √(Bx²+By²+Bz²)")
        if res is None:
            return
        bx, by, bz = res["bx"], res["by"], res["bz"]
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
            self._log_workflow("add_moving_average", col=y_col, window=25)
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

    # ---------- Reproducibility hook (ROADMAP F) ----------
    def _log_workflow(self, op: str, **params):
        """ส่งต่อไปยัง workflow recorder ถ้ามี (stub ในเทสต์ไม่มี → เงียบ)"""
        recorder = getattr(self, "_record_op", None)
        if callable(recorder):
            try:
                recorder(op, **params)
            except Exception:
                import logging
                logging.getLogger(__name__).debug("workflow record failed", exc_info=True)

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
        res = self.ask_form("เติมค่าที่หาย (Fill Missing)", [
            {"name": "method", "label": "วิธี", "kind": "choice",
             "options": list(FILL_METHODS), "default": "mean"},
            {"name": "value", "label": "ค่าที่ใช้เติม", "kind": "float",
             "default": 0.0, "show_if": ("method", "value")},
        ], description=f"เติมค่าที่หายในคอลัมน์ '{y_col}' → สร้างคอลัมน์ใหม่")
        if res is None:
            return
        method = res["method"]
        value = res["value"] if method == "value" else None
        try:
            new_col = fill_missing(self._df, y_col, method=method, value=value)
            self.add_y_column_option(new_col)
            self._log_workflow("fill_missing", col=y_col, method=method, value=value)
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
            self._log_workflow("interpolate_missing", col=y_col)
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
            self._log_workflow("remove_duplicates")
            self.notify(f"ลบแถวซ้ำแล้ว {removed} แถว (เหลือ {len(new_df)})")
        except Exception as e:
            self.error_box("ลบแถวซ้ำไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_remove_outliers(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("ตัด Outliers", [
            {"name": "method", "label": "วิธีตรวจ", "kind": "choice",
             "options": list(OUTLIER_METHODS), "default": "zscore"},
            {"name": "threshold", "label": "threshold", "kind": "float",
             "default": 3.0, "min": 0.1, "max": 100.0, "decimals": 2},
        ], description=f"ตัดแถวที่ '{y_col}' เป็น outlier (zscore≈3, iqr≈1.5)")
        if res is None:
            return
        method, threshold = res["method"], res["threshold"]
        try:
            new_df, removed = remove_outliers(self._df, y_col, method=method, threshold=threshold)
            self._swap_dataframe(new_df)
            self._log_workflow("remove_outliers", col=y_col, method=method, threshold=threshold)
            self.notify(f"ตัด outliers ของ {y_col} แล้ว {removed} แถว (วิธี {method})")
        except Exception as e:
            self.error_box("ตัด outliers ไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_normalize(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Normalize / Standardize", [
            {"name": "method", "label": "วิธี", "kind": "choice",
             "options": list(NORMALIZE_METHODS), "default": "zscore"},
        ], description=f"ปรับสเกลคอลัมน์ '{y_col}' (zscore = ค่าเฉลี่ย 0 / minmax = 0–1)")
        if res is None:
            return
        method = res["method"]
        try:
            new_col = normalize_column(self._df, y_col, method=method)
            self.add_y_column_option(new_col)
            self._log_workflow("normalize_column", col=y_col, method=method)
            self.notify(f"สร้างคอลัมน์ normalize แล้ว: {new_col}")
        except Exception as e:
            self.error_box("Normalize ไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_detrend(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Detrend / Baseline", [
            {"name": "order", "label": "อันดับพหุนาม", "kind": "int",
             "default": 1, "min": 0, "max": 10},
        ], description=f"ลบแนวโน้ม/เส้นฐานจาก '{y_col}' (1 = เชิงเส้น, สูงขึ้น = baseline โค้ง)")
        if res is None:
            return
        order = res["order"]
        x_col = self.selected_x_column()
        if x_col not in getattr(self._df, "columns", []):
            x_col = None
        try:
            new_col = detrend_polynomial(self._df, y_col, order=int(order), x_col=x_col)
            self.add_y_column_option(new_col)
            self._log_workflow("detrend_polynomial", col=y_col, order=int(order), x_col=x_col)
            self.notify(f"ลบ baseline/trend อันดับ {order} แล้ว: {new_col}")
        except Exception as e:
            self.error_box("Detrend ไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_clean_sort(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน")
            return
        cols = [str(c) for c in self._df.columns]
        res = self.ask_form("เรียงข้อมูล (Sort)", [
            {"name": "col", "label": "ตามคอลัมน์", "kind": "choice",
             "options": cols, "default": cols[0]},
            {"name": "direction", "label": "ทิศทาง", "kind": "choice",
             "options": ["น้อย→มาก", "มาก→น้อย"], "default": "น้อย→มาก"},
        ])
        if res is None:
            return
        col = res["col"]
        try:
            ascending = (res["direction"] == "น้อย→มาก")
            new_df = sort_dataframe(self._df, col, ascending=ascending)
            self._swap_dataframe(new_df)
            self._log_workflow("sort_dataframe", col=col, ascending=ascending)
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
        res = self.ask_form("Resample เป็นกริดสม่ำเสมอ", [
            {"name": "n_points", "label": "จำนวนจุด", "kind": "int",
             "default": n_default, "min": 2, "max": 10_000_000},
        ], description=f"สุ่มใหม่บนแกน '{x_col}' ให้ระยะห่างเท่ากัน (interpolate เชิงเส้น)")
        if res is None:
            return
        n_points = res["n_points"]
        try:
            new_df = resample_uniform(self._df, x_col, n_points=int(n_points))
            self._swap_dataframe(new_df)
            self._log_workflow("resample_uniform", x_col=x_col, n_points=int(n_points))
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

    def _infer_fs_default(self, fallback: float = 100.0) -> float:
        """Inferred sampling rate for pre-filling a form (never prompts)."""
        try:
            x_col = self.selected_x_column()
            if x_col and x_col in getattr(self._df, "columns", []):
                fs = _infer_sampling_rate(self._df[x_col])
                if fs and fs > 0:
                    return float(fs)
        except Exception:
            import logging
            logging.getLogger(__name__).debug("fs inference failed", exc_info=True)
        return float(fallback)

    def feature_filter_butterworth(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        fs_guess = self._infer_fs_default()
        res = self.ask_form("Butterworth Filter", [
            {"name": "kind", "label": "ชนิด", "kind": "choice",
             "options": list(BUTTER_KINDS), "default": "lowpass"},
            {"name": "fs", "label": "fs (Hz)", "kind": "float",
             "default": round(fs_guess, 6), "min": 1e-9, "max": 1e12, "decimals": 6},
            {"name": "cutoff_lo", "label": "cutoff ต่ำ (Hz)", "kind": "float",
             "default": round(fs_guess / 10, 6), "min": 1e-12, "max": 1e12, "decimals": 6,
             "show_if": ("kind", ("bandpass", "bandstop"))},
            {"name": "cutoff_hi", "label": "cutoff สูง (Hz)", "kind": "float",
             "default": round(fs_guess / 5, 6), "min": 1e-12, "max": 1e12, "decimals": 6,
             "show_if": ("kind", ("bandpass", "bandstop"))},
            {"name": "cutoff", "label": "cutoff (Hz)", "kind": "float",
             "default": round(fs_guess / 10, 6), "min": 1e-12, "max": 1e12, "decimals": 6,
             "show_if": ("kind", ("lowpass", "highpass"))},
        ], description=f"กรองสัญญาณ '{y_col}' แบบ zero-phase (fs เดาจากแกน X ให้แล้ว)")
        if res is None:
            return
        kind, fs = res["kind"], float(res["fs"])
        if kind in ("bandpass", "bandstop"):
            cutoff = (float(res["cutoff_lo"]), float(res["cutoff_hi"]))
        else:
            cutoff = float(res["cutoff"])
        try:
            filtered = butterworth_filter(self._df[y_col], fs, kind=kind, cutoff=cutoff)
            new_col = f"{y_col}_{kind}"
            self._df[new_col] = filtered
            self.add_y_column_option(new_col)
            self._log_workflow(
                "butterworth_filter", col=y_col, fs=float(fs), kind=kind,
                cutoff=list(cutoff) if isinstance(cutoff, tuple) else float(cutoff),
                order=4, new_col=new_col)
            self.notify(f"กรองสัญญาณ ({kind}) แล้ว: {new_col} (fs≈{fs:.4g} Hz)")
        except Exception as e:
            self.error_box("กรองไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_filter_smooth(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Smooth (ลดสัญญาณรบกวน)", [
            {"name": "method", "label": "วิธี", "kind": "choice",
             "options": ["savitzky-golay", "median", "gaussian"], "default": "savitzky-golay"},
            {"name": "window", "label": "ความยาวหน้าต่าง (คี่)", "kind": "int",
             "default": 11, "min": 3, "max": 9999, "show_if": ("method", "savitzky-golay")},
            {"name": "kernel", "label": "ขนาด kernel (คี่)", "kind": "int",
             "default": 5, "min": 1, "max": 9999, "show_if": ("method", "median")},
            {"name": "sigma", "label": "sigma (จุด)", "kind": "float",
             "default": 2.0, "min": 0.01, "max": 1e6, "decimals": 2, "show_if": ("method", "gaussian")},
        ], description=f"ปรับเรียบสัญญาณ '{y_col}' → สร้างคอลัมน์ใหม่")
        if res is None:
            return
        method = res["method"]
        try:
            if method == "savitzky-golay":
                smoothed = savitzky_golay(self._df[y_col], window_length=int(res["window"]))
                new_col = f"{y_col}_savgol"
                op, params = "savitzky_golay", {"col": y_col, "window": int(res["window"])}
            elif method == "median":
                smoothed = median_filter(self._df[y_col], kernel_size=int(res["kernel"]))
                new_col = f"{y_col}_median"
                op, params = "median_filter", {"col": y_col, "kernel": int(res["kernel"])}
            else:
                smoothed = gaussian_smooth(self._df[y_col], sigma=float(res["sigma"]))
                new_col = f"{y_col}_gauss"
                op, params = "gaussian_smooth", {"col": y_col, "sigma": float(res["sigma"])}
            self._df[new_col] = smoothed
            self.add_y_column_option(new_col)
            self._log_workflow(op, new_col=new_col, **params)
            self.notify(f"smooth ({method}) แล้ว: {new_col}")
        except Exception as e:
            self.error_box("Smooth ไม่สำเร็จ", f"สาเหตุ: {e}")

    # ---------- Peak & signal-quality metrics (ROADMAP E) ----------
    def _finite_xy_for_metrics(self):
        """(x, y, x_name, y_name) เป็น float ที่ finite ทั้งคู่ — สำหรับ FWHM/พื้นที่พีค"""
        import numpy as np

        y_name = self.selected_y_column()
        y = pd.to_numeric(self._df[y_name], errors="coerce").to_numpy(dtype=float)
        x_name = self.selected_x_column()
        if x_name in [str(c) for c in self._df.columns]:
            ser = self._df[x_name]
            if pd.api.types.is_datetime64_any_dtype(ser):
                x = (ser - ser.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
            else:
                x = pd.to_numeric(ser, errors="coerce").to_numpy(dtype=float)
        else:
            x_name = "index"
            x = np.arange(y.size, dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        return x[mask], y[mask], x_name, y_name

    def feature_peak_metrics(self):
        """FWHM + พื้นที่ใต้พีคของคอลัมน์ Y ที่เลือก (เทียบแกน X)"""
        if not self._has_y_data():
            return
        try:
            x, y, x_name, y_name = self._finite_xy_for_metrics()
            area = peak_area(x, y)
            lines = [f"คอลัมน์: {y_name} (X = {x_name})",
                     f"พื้นที่ใต้กราฟ (trapezoid): {area:.6g}"]
            try:
                width = fwhm(x, y)
                lines.append(f"FWHM ของพีคหลัก: {width:.6g}")
            except ValueError as e:
                lines.append(f"FWHM: คำนวณไม่ได้ ({e})")
            self.inform("Peak Metrics", "\n".join(lines))
            self.notify(f"Peak metrics ของ {y_name} คำนวณแล้ว")
        except Exception as e:
            self.error_box("คำนวณไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_signal_quality(self):
        """SNR + noise floor (จาก Welch PSD) ของคอลัมน์ Y ที่เลือก"""
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        fs = self._sampling_rate_or_ask()
        if fs is None:
            return
        try:
            snr_db = estimate_snr(self._df[y_col], fs=fs)
            floor = noise_floor(self._df[y_col], fs=fs)
            self.inform(
                f"Signal Quality — {y_col}",
                f"fs ≈ {fs:.6g} Hz\nSNR (พีคเทียบ median PSD): {snr_db:.4g} dB\n"
                f"Noise floor (median Welch PSD): {floor:.6g}")
            self.notify(f"SNR ของ {y_col}: {snr_db:.4g} dB")
        except Exception as e:
            self.error_box("คำนวณไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_apply_window(self):
        """คูณสัญญาณด้วย window (hann/hamming/blackman/kaiser) → คอลัมน์ใหม่"""
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Apply Window", [
            {"name": "window", "label": "ชนิด window", "kind": "choice",
             "options": list(WINDOW_KINDS), "default": "hann"},
            {"name": "beta", "label": "beta (Kaiser)", "kind": "float",
             "default": 14.0, "min": 0.0, "max": 100.0, "decimals": 2,
             "show_if": ("window", "kaiser")},
        ], description=f"คูณสัญญาณ '{y_col}' ด้วย taper window → คอลัมน์ใหม่")
        if res is None:
            return
        window = res["window"]
        beta = res["beta"] if window == "kaiser" else 14.0
        try:
            tapered = apply_window(self._df[y_col], window=window, beta=float(beta))
            new_col = f"{y_col}_{window}"
            self._df[new_col] = tapered
            self.add_y_column_option(new_col)
            self._log_workflow("apply_window", col=y_col, window=window,
                               beta=float(beta), new_col=new_col)
            self.notify(f"ใส่ window ({window}) แล้ว: {new_col}")
        except Exception as e:
            self.error_box("ใส่ window ไม่สำเร็จ", f"สาเหตุ: {e}")

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
        y_sel = self.selected_y_column()
        res = self.ask_form("PSD (Welch)", [
            {"name": "y_col", "label": "คอลัมน์ Y", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "fs", "label": "fs (Hz)", "kind": "float",
             "default": round(self._infer_fs_default(), 6), "min": 1e-9, "max": 1e12, "decimals": 6},
        ], description="ความหนาแน่นสเปกตรัมกำลัง (fs เดาจากแกน X ให้แล้ว) → พล็อตกราฟใหม่")
        if res is None:
            return
        y_col, fs = res["y_col"], float(res["fs"])
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
        y_sel = self.selected_y_column()
        res = self.ask_form("FFT", [
            {"name": "y_col", "label": "คอลัมน์ Y", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "window", "label": "หน้าต่าง (window)", "kind": "choice",
             "options": ["hanning", "hamming", "none"], "default": "hanning"},
            {"name": "detrend", "label": "ลบค่าเฉลี่ยก่อนคำนวณ", "kind": "bool", "default": True},
        ], description="แปลงฟูริเยร์ (fs เดาจากแกน X) → พล็อตสเปกตรัมกราฟใหม่")
        if res is None:
            return
        y_col, window, detrend = res["y_col"], res["window"], bool(res["detrend"])

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
