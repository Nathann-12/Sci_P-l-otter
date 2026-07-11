from __future__ import annotations

import os
from typing import TYPE_CHECKING

import numpy as np
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
    BUTTER_KINDS, CONVOLUTION_MODES, WINDOW_KINDS, apply_window,
    autocorrelation, butterworth_filter, compute_ifft, compute_stft,
    convolve_signals, deconvolve_signals, gaussian_smooth,
    harmonic_analysis, hilbert_transform, instantaneous_frequency, median_filter,
    peak_metrics_summary, savitzky_golay, signal_envelope,
    signal_quality_summary, welch_psd, zero_pad,
)
from analysis.descriptive import covariance_table, descriptive_table
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
            self.inform("No data", "Open a data file first."); return
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
            self.inform("No data", "Open a data file and reload columns first."); return
        x_col = self.selected_x_column()
        try:
            new_col = add_time_bangkok(self._df, x_col)
            self.add_x_column_option(new_col)
            self.notify(f"Bangkok time column added: {new_col}")
        except Exception as e:
            self.error_box("Operation failed", f"Reason: {e}")

    def feature_add_magnitude(self):
        if self._df is None or self.y_column_count() == 0:
            self.inform("No data", "Open a data file and reload columns first."); return
        cols = [str(c) for c in self._df.columns]
        res = self.ask_form("Add |B| from 3 axes", [
            {"name": "bx", "label": "X axis (Bx)", "kind": "choice", "options": cols,
             "default": cols[0]},
            {"name": "by", "label": "Y axis (By)", "kind": "choice", "options": cols,
             "default": cols[1] if len(cols) > 1 else cols[0]},
            {"name": "bz", "label": "Z axis (Bz)", "kind": "choice", "options": cols,
             "default": cols[2] if len(cols) > 2 else cols[0]},
        ], description="Vector magnitude |B| = √(Bx²+By²+Bz²)")
        if res is None:
            return
        bx, by, bz = res["bx"], res["by"], res["bz"]
        try:
            new_col = add_magnitude(self._df, bx, by, bz, new_col="B_mag")
            self.add_y_column_option(new_col)
            self.notify(f"|B| column added: {new_col}")
        except Exception as e:
            self.error_box("Operation failed", f"Reason: {e}")

    def feature_add_moving_average(self):
        if self._df is None or self.y_column_count() == 0:
            self.inform("No data", "Open a data file and reload columns first."); return
        y_col = self.selected_y_column()
        try:
            new_col = add_moving_average(self._df, y_col, window=25)
            self.add_y_column_option(new_col)
            self._log_workflow("add_moving_average", col=y_col, window=25)
            self.notify(f"Moving average column added: {new_col}")
        except Exception as e:
            self.error_box("Operation failed", f"Reason: {e}")

    def feature_set_column_types(self):
        if self._df is None or len(self._df.columns) == 0:
            self.inform("No data", "Open a data file first."); return
        dlg = ColumnTypeDialog(self, self._df.columns)
        if dlg.exec() != QDialog.Accepted:
            return
        mapping = dlg.get_mapping()
        try:
            apply_column_types(self._df, mapping)
            self.load_columns_from_df()
            # รีเฟรชกราฟหลังจากแปลงชนิดข้อมูล
            self.refresh_plot()
            self.notify("Column types converted.")
        except Exception as e:
            self.error_box("Conversion failed", f"Reason: {e}")

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
            self.inform(
                "No data",
                "Open a file or type data into a Book, then click Use This Data first.",
            )
            return False
        return True

    _ALL_NUMERIC_LABEL = "All numeric columns"

    def _numeric_column_names(self) -> list:
        """Numeric columns of the active DataFrame (worksheet order)."""
        if self._df is None:
            return []
        return [str(c) for c in self._df.columns
                if pd.api.types.is_numeric_dtype(self._df[c])]

    def _active_book_label(self) -> str:
        """Name of the Book being analyzed, shown in analysis forms.

        Result Books become the active Book when they open (multi-book
        contract), so without this label a second analysis silently runs on
        the previous result table — the name makes the source obvious.
        """
        wb = getattr(self, "workbook", None)
        name = str(getattr(wb, "dataset_name", "") or "").strip()
        if name:
            return name
        path = getattr(self, "_current_path", None)
        if path:
            return os.path.basename(str(path))
        return "Book1"

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

    def _sync_dataframe_after_column_edit(self) -> None:
        """Keep the active Origin-style Book and dataset registry in sync."""
        try:
            wb = getattr(self, "workbook", None)
            if wb is not None and self._df is not None:
                old_designations = list(getattr(wb, "_designations", []))
                wb.source_df = self._df
                if hasattr(wb, "set_dataframe"):
                    wb.set_dataframe(self._df)
                    if old_designations:
                        restored = old_designations[: len(self._df.columns)]
                        while len(restored) < len(self._df.columns):
                            restored.append("Y")
                        if "X" not in restored and restored:
                            restored[0] = "X"
                        wb._designations = restored
                        if hasattr(wb, "_apply_column_headers"):
                            wb._apply_column_headers(len(self._df.columns))
                if hasattr(wb, "mark_clean"):
                    wb.mark_clean()
                key = getattr(wb, "dataset_name", "") or getattr(self, "_book_title_for", lambda _wb: "")(wb)
                if key and hasattr(self, "_datasets"):
                    existing = self._datasets.get(key) or {}
                    self._datasets[key] = {"df": self._df, "path": existing.get("path")}
                show_data = getattr(self, "_show_data_view", None)
                if callable(show_data):
                    show_data()
        except Exception:
            import logging
            logging.getLogger(__name__).debug("active book sync failed", exc_info=True)
        try:
            fn = getattr(self, "load_columns_from_df", None)
            if callable(fn):
                fn()
        except Exception:
            import logging
            logging.getLogger(__name__).debug("load_columns_from_df failed after column edit", exc_info=True)

    def _numeric_column_values(self, col: str, *, drop_blank: bool = False) -> np.ndarray:
        values = pd.to_numeric(self._df[col], errors="coerce")
        if drop_blank:
            values = values[np.isfinite(values.to_numpy(dtype=float))]
        return values.to_numpy(dtype=float)

    def _series_for_active_index(self, values) -> pd.Series:
        out = pd.Series(np.nan, index=self._df.index, dtype=float)
        arr = np.asarray(values, dtype=float).ravel()
        out.iloc[: min(arr.size, out.size)] = arr[: out.size]
        return out

    def _open_signal_result_book(self, name: str, df: pd.DataFrame) -> str:
        datasets = getattr(self, "_datasets", None)
        final_name = name
        if isinstance(datasets, dict):
            base = name
            i = 2
            while final_name in datasets:
                final_name = f"{base} {i}"
                i += 1
            datasets[final_name] = {"df": df, "path": None}
        opener = getattr(self, "_open_book_for_dataset", None)
        if callable(opener):
            opener(final_name, df, None)
        else:
            self._swap_dataframe(df)
        return final_name

    def _active_dataframe_or_none(self):
        if isinstance(getattr(self, "_df", None), pd.DataFrame) and not self._df.empty:
            return self._df
        self.inform("No data", "Open a data file or select a Book first.")
        return None

    def _dataset_names(self, *, include_active: bool = True) -> list[str]:
        names: list[str] = []
        active = self._active_book_label()
        datasets = getattr(self, "_datasets", None)
        if isinstance(datasets, dict):
            for name, payload in datasets.items():
                if isinstance(payload, dict) and isinstance(payload.get("df"), pd.DataFrame):
                    names.append(str(name))
        if include_active and isinstance(getattr(self, "_df", None), pd.DataFrame):
            if active and active not in names:
                names.insert(0, active)
        return names

    def _dataset_frame(self, name: str):
        active = self._active_book_label()
        if name == active and isinstance(getattr(self, "_df", None), pd.DataFrame):
            return self._df
        payload = getattr(self, "_datasets", {}).get(name)
        if isinstance(payload, dict) and isinstance(payload.get("df"), pd.DataFrame):
            return payload["df"]
        return None

    def _rename_active_dataset(self, new_name: str) -> str:
        old_name = self._active_book_label()
        new_name = str(new_name or "").strip()
        if not new_name:
            raise ValueError("new name is empty")
        if new_name == old_name:
            return new_name
        datasets = getattr(self, "_datasets", None)
        if isinstance(datasets, dict):
            if new_name in datasets:
                raise ValueError(f"a Book named {new_name!r} already exists")
            payload = datasets.pop(old_name, None)
            if payload is None and isinstance(getattr(self, "_df", None), pd.DataFrame):
                payload = {"df": self._df, "path": getattr(self, "_current_path", None)}
            if payload is not None:
                datasets[new_name] = payload
        wb = getattr(self, "workbook", None)
        if wb is not None:
            wb.dataset_name = new_name
        mdi = getattr(self, "mdi", None)
        try:
            books = getattr(mdi, "_books", None)
            if isinstance(books, dict):
                for key, (widget, sub) in list(books.items()):
                    if widget is wb or key == old_name or sub.windowTitle() == old_name:
                        sub.setWindowTitle(new_name)
                        books.pop(key, None)
                        books[new_name] = (widget, sub)
                        break
        except Exception:
            import logging
            logging.getLogger(__name__).debug("book window rename failed", exc_info=True)
        return new_name

    def feature_dataset_duplicate(self):
        df = self._active_dataframe_or_none()
        if df is None:
            return
        default_name = f"{self._active_book_label()} Copy"
        res = self.ask_form("Duplicate Book", [
            {"name": "name", "label": "New Book name", "kind": "text", "default": default_name},
        ], description="Create a separate copy of the active Book.")
        if res is None:
            return
        try:
            name = str(res.get("name") or default_name).strip() or default_name
            target = self._open_signal_result_book(name, df.copy(deep=True))
            self._log_workflow("dataset_duplicate", source=self._active_book_label(), output=target)
            self.notify(f"Duplicated Book -> {target}")
        except Exception as e:
            self.error_box("Duplicate Book failed", f"Reason: {e}")

    def feature_dataset_rename(self):
        df = self._active_dataframe_or_none()
        if df is None:
            return
        old_name = self._active_book_label()
        res = self.ask_form("Rename Book", [
            {"name": "name", "label": "Book name", "kind": "text", "default": old_name},
        ], description="Rename the active Book and update the project registry.")
        if res is None:
            return
        try:
            new_name = self._rename_active_dataset(res.get("name"))
            self._log_workflow("dataset_rename", old_name=old_name, new_name=new_name)
            self.notify(f"Renamed Book: {old_name} -> {new_name}")
        except Exception as e:
            self.error_box("Rename Book failed", f"Reason: {e}")

    def feature_dataset_group(self):
        df = self._active_dataframe_or_none()
        if df is None:
            return
        cols = [str(c) for c in df.columns]
        numeric = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
        if not cols or not numeric:
            self.inform("Not enough data", "Grouping needs at least one numeric column.")
            return
        default_group = cols[0]
        default_value = next((c for c in numeric if c != default_group), numeric[0])
        res = self.ask_form("Group and Summarize", [
            {"name": "group_col", "label": "Group column", "kind": "choice", "options": cols, "default": default_group},
            {"name": "value_col", "label": "Value column", "kind": "choice", "options": numeric, "default": default_value},
            {"name": "agg", "label": "Aggregation", "kind": "choice",
             "options": ["mean", "sum", "median", "min", "max", "count"], "default": "mean"},
        ], description="Create an Origin-style result Book grouped by a column.")
        if res is None:
            return
        try:
            group_col, value_col, agg = res["group_col"], res["value_col"], res["agg"]
            grouped = (
                df.groupby(group_col, dropna=False)[value_col]
                .agg([agg, "count"])
                .reset_index()
                .rename(columns={agg: f"{value_col}_{agg}", "count": "row_count"})
            )
            target = self._open_signal_result_book(f"Group_{group_col}", grouped)
            self._log_workflow("dataset_group", group_col=group_col, value_col=value_col, agg=agg, output=target)
            self.notify(f"Grouped summary -> {target}")
        except Exception as e:
            self.error_box("Group summary failed", f"Reason: {e}")

    def feature_dataset_merge(self):
        left = self._active_dataframe_or_none()
        if left is None:
            return
        names = [n for n in self._dataset_names() if n != self._active_book_label()]
        if not names:
            self.inform("No second Book", "Open or create another Book before merging.")
            return
        left_cols = [str(c) for c in left.columns]
        right_default_name = names[0]
        right = self._dataset_frame(right_default_name)
        right_cols = [str(c) for c in right.columns] if isinstance(right, pd.DataFrame) else left_cols
        key_guess = next((c for c in left_cols if c in right_cols), left_cols[0])
        res = self.ask_form("Merge Books", [
            {"name": "right_book", "label": "Right Book", "kind": "choice", "options": names, "default": right_default_name},
            {"name": "left_key", "label": "Left key column", "kind": "choice", "options": left_cols, "default": key_guess},
            {"name": "right_key", "label": "Right key column", "kind": "choice", "options": right_cols, "default": key_guess if key_guess in right_cols else right_cols[0]},
            {"name": "how", "label": "Join type", "kind": "choice", "options": ["inner", "left", "outer"], "default": "inner"},
        ], description="Merge the active Book with another Book and open the result.")
        if res is None:
            return
        try:
            right = self._dataset_frame(res["right_book"])
            if not isinstance(right, pd.DataFrame):
                raise ValueError("right Book is not available")
            out = pd.merge(
                left,
                right,
                left_on=res["left_key"],
                right_on=res["right_key"],
                how=res["how"],
                suffixes=("_left", "_right"),
            )
            target = self._open_signal_result_book(f"Merge_{self._active_book_label()}_{res['right_book']}", out)
            self._log_workflow("dataset_merge", right_book=res["right_book"], how=res["how"], output=target)
            self.notify(f"Merged Books -> {target} ({len(out)} rows)")
        except Exception as e:
            self.error_box("Merge Books failed", f"Reason: {e}")

    def feature_dataset_split(self):
        df = self._active_dataframe_or_none()
        if df is None:
            return
        cols = [str(c) for c in df.columns]
        default_chunk = max(1, min(len(df), max(1, len(df) // 2)))
        res = self.ask_form("Split Book", [
            {"name": "mode", "label": "Split mode", "kind": "choice",
             "options": ["Every N rows", "By category values"], "default": "Every N rows"},
            {"name": "chunk_size", "label": "Rows per Book", "kind": "int",
             "default": default_chunk, "min": 1, "max": max(1, len(df))},
            {"name": "group_col", "label": "Category column", "kind": "choice",
             "options": cols, "default": cols[0]},
        ], description="Split the active Book into multiple result Books.")
        if res is None:
            return
        try:
            outputs = []
            if res["mode"] == "By category values":
                group_col = res["group_col"]
                for value, part in df.groupby(group_col, dropna=False):
                    safe_value = str(value).replace("/", "_").replace("\\", "_")[:40]
                    outputs.append(self._open_signal_result_book(f"Split_{group_col}_{safe_value}", part.reset_index(drop=True)))
            else:
                chunk = int(res["chunk_size"])
                for start in range(0, len(df), chunk):
                    part = df.iloc[start:start + chunk].reset_index(drop=True)
                    outputs.append(self._open_signal_result_book(f"Split_rows_{start + 1}_{start + len(part)}", part))
            self._log_workflow("dataset_split", mode=res["mode"], outputs=outputs)
            self.notify(f"Split complete: {len(outputs)} Books")
        except Exception as e:
            self.error_box("Split Book failed", f"Reason: {e}")

    def feature_dataset_filter(self):
        df = self._active_dataframe_or_none()
        if df is None:
            return
        cols = [str(c) for c in df.columns]
        default_col = self.selected_y_column() if self.selected_y_column() in cols else cols[0]
        res = self.ask_form("Filter Rows", [
            {"name": "col", "label": "Column", "kind": "choice", "options": cols, "default": default_col},
            {"name": "operator", "label": "Condition", "kind": "choice",
             "options": ["is finite", "equals", "contains", ">=", "<=", ">", "<"], "default": "is finite"},
            {"name": "value", "label": "Value", "kind": "text", "default": ""},
        ], description="Create a filtered result Book without changing the source Book.")
        if res is None:
            return
        try:
            col, op, value = res["col"], res["operator"], res.get("value", "")
            series = df[col]
            if op == "is finite":
                mask = np.isfinite(pd.to_numeric(series, errors="coerce"))
            elif op == "contains":
                mask = series.astype(str).str.contains(str(value), case=False, na=False, regex=False)
            elif op == "equals":
                mask = series.astype(str) == str(value)
            else:
                nums = pd.to_numeric(series, errors="coerce")
                target_value = float(value)
                if op == ">=":
                    mask = nums >= target_value
                elif op == "<=":
                    mask = nums <= target_value
                elif op == ">":
                    mask = nums > target_value
                else:
                    mask = nums < target_value
            out = df.loc[mask].reset_index(drop=True)
            target = self._open_signal_result_book(f"Filter_{col}", out)
            self._log_workflow("dataset_filter", col=col, operator=op, output=target)
            self.notify(f"Filtered rows -> {target} ({len(out)} rows)")
        except Exception as e:
            self.error_box("Filter Rows failed", f"Reason: {e}")

    def feature_dataset_search(self):
        df = self._active_dataframe_or_none()
        if df is None:
            return
        cols = [str(c) for c in df.columns]
        res = self.ask_form("Search Book", [
            {"name": "query", "label": "Search text", "kind": "text", "default": "0"},
            {"name": "column", "label": "Column", "kind": "choice",
             "options": ["All columns"] + cols, "default": "All columns"},
        ], description="Find matching rows and open them in a result Book.")
        if res is None:
            return
        query = str(res.get("query", "")).strip()
        if not query:
            self.inform("Empty search", "Enter text to search for.")
            return
        try:
            if res["column"] == "All columns":
                mask = pd.Series(False, index=df.index)
                for col in cols:
                    mask |= df[col].astype(str).str.contains(query, case=False, na=False, regex=False)
            else:
                mask = df[res["column"]].astype(str).str.contains(query, case=False, na=False, regex=False)
            out = df.loc[mask].reset_index(drop=True)
            target = self._open_signal_result_book("Search Results", out)
            self._log_workflow("dataset_search", query=query, column=res["column"], output=target)
            self.notify(f"Search complete -> {target} ({len(out)} rows)")
        except Exception as e:
            self.error_box("Search Book failed", f"Reason: {e}")

    def feature_clean_remove_nan(self):
        df = self._active_dataframe_or_none()
        if df is None:
            return
        cols = [str(c) for c in df.columns]
        default_col = self.selected_y_column() if self.selected_y_column() in cols else cols[0]
        res = self.ask_form("Remove Missing Rows", [
            {"name": "scope", "label": "Scope", "kind": "choice",
             "options": ["Selected column", "Any column", "All selected numeric columns"], "default": "Selected column"},
            {"name": "col", "label": "Column", "kind": "choice", "options": cols, "default": default_col},
        ], description="Drop rows with missing values and update the active Book.")
        if res is None:
            return
        try:
            if res["scope"] == "Any column":
                subset = None
            elif res["scope"] == "All selected numeric columns":
                subset = self._numeric_column_names() or None
            else:
                subset = [res["col"]]
            out = df.dropna(subset=subset).reset_index(drop=True)
            removed = len(df) - len(out)
            self._swap_dataframe(out)
            self._log_workflow("remove_missing_rows", scope=res["scope"], col=res["col"])
            self.notify(f"Removed {removed} rows with missing values.")
        except Exception as e:
            self.error_box("Remove Missing Rows failed", f"Reason: {e}")

    def feature_clean_crop_range(self):
        df = self._active_dataframe_or_none()
        if df is None:
            return
        numeric = self._numeric_column_names()
        if not numeric:
            self.inform("No numeric columns", "Crop range needs at least one numeric column.")
            return
        default_col = self.selected_x_column() if self.selected_x_column() in numeric else numeric[0]
        values = pd.to_numeric(df[default_col], errors="coerce")
        lo_default = float(values.min()) if values.notna().any() else 0.0
        hi_default = float(values.max()) if values.notna().any() else 1.0
        res = self.ask_form("Crop Range", [
            {"name": "col", "label": "Range column", "kind": "choice", "options": numeric, "default": default_col},
            {"name": "min_value", "label": "Minimum", "kind": "float", "default": lo_default, "decimals": 6},
            {"name": "max_value", "label": "Maximum", "kind": "float", "default": hi_default, "decimals": 6},
        ], description="Keep rows whose selected column is inside the range.")
        if res is None:
            return
        try:
            col = res["col"]
            lo, hi = sorted((float(res["min_value"]), float(res["max_value"])))
            nums = pd.to_numeric(df[col], errors="coerce")
            out = df.loc[(nums >= lo) & (nums <= hi)].reset_index(drop=True)
            removed = len(df) - len(out)
            self._swap_dataframe(out)
            self._log_workflow("crop_range", col=col, min_value=lo, max_value=hi)
            self.notify(f"Cropped range on {col}: removed {removed} rows.")
        except Exception as e:
            self.error_box("Crop Range failed", f"Reason: {e}")

    def feature_clean_merge_by_timestamp(self):
        left = self._active_dataframe_or_none()
        if left is None:
            return
        names = [n for n in self._dataset_names() if n != self._active_book_label()]
        if not names:
            self.inform("No second Book", "Open or create another Book before merging by time.")
            return
        time_like = lambda cols: next((c for c in cols if any(k in str(c).lower() for k in ("time", "timestamp", "datetime", "date", "t"))), cols[0])
        left_cols = [str(c) for c in left.columns]
        right_default = names[0]
        right = self._dataset_frame(right_default)
        right_cols = [str(c) for c in right.columns] if isinstance(right, pd.DataFrame) else left_cols
        res = self.ask_form("Merge by Timestamp", [
            {"name": "right_book", "label": "Right Book", "kind": "choice", "options": names, "default": right_default},
            {"name": "left_time", "label": "Left time column", "kind": "choice", "options": left_cols, "default": time_like(left_cols)},
            {"name": "right_time", "label": "Right time column", "kind": "choice", "options": right_cols, "default": time_like(right_cols)},
            {"name": "mode", "label": "Match mode", "kind": "choice", "options": ["exact", "nearest"], "default": "nearest"},
        ], description="Align two Books by timestamp or numeric time and open the result.")
        if res is None:
            return
        try:
            right = self._dataset_frame(res["right_book"])
            if not isinstance(right, pd.DataFrame):
                raise ValueError("right Book is not available")
            left_time, right_time = res["left_time"], res["right_time"]
            if res["mode"] == "exact":
                out = pd.merge(left, right, left_on=left_time, right_on=right_time, how="left", suffixes=("_left", "_right"))
            else:
                l2 = left.copy()
                r2 = right.copy()
                l2["_merge_time"] = pd.to_numeric(l2[left_time], errors="coerce")
                r2["_merge_time"] = pd.to_numeric(r2[right_time], errors="coerce")
                if l2["_merge_time"].isna().all() or r2["_merge_time"].isna().all():
                    l2["_merge_time"] = pd.to_datetime(l2[left_time], errors="coerce")
                    r2["_merge_time"] = pd.to_datetime(r2[right_time], errors="coerce")
                l2 = l2.dropna(subset=["_merge_time"]).sort_values("_merge_time")
                r2 = r2.dropna(subset=["_merge_time"]).sort_values("_merge_time")
                out = pd.merge_asof(l2, r2, on="_merge_time", direction="nearest", suffixes=("_left", "_right"))
                out = out.drop(columns=["_merge_time"])
            target = self._open_signal_result_book(f"TimeMerge_{self._active_book_label()}_{res['right_book']}", out.reset_index(drop=True))
            self._log_workflow("merge_by_timestamp", right_book=res["right_book"], mode=res["mode"], output=target)
            self.notify(f"Time merge complete -> {target} ({len(out)} rows)")
        except Exception as e:
            self.error_box("Merge by Timestamp failed", f"Reason: {e}")

    def feature_clean_fill_missing(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Fill Missing", [
            {"name": "method", "label": "Method", "kind": "choice",
             "options": list(FILL_METHODS), "default": "mean"},
            {"name": "value", "label": "Fill value", "kind": "float",
             "default": 0.0, "show_if": ("method", "value")},
        ], description=f"Fill missing values in column '{y_col}' → new column")
        if res is None:
            return
        method = res["method"]
        value = res["value"] if method == "value" else None
        try:
            new_col = fill_missing(self._df, y_col, method=method, value=value)
            self.add_y_column_option(new_col)
            self._log_workflow("fill_missing", col=y_col, method=method, value=value)
            self.notify(f"Missing values filled: {new_col} (method: {method})")
        except Exception as e:
            self.error_box("Fill missing values failed", f"Reason: {e}")

    def feature_clean_interpolate(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        try:
            new_col = interpolate_missing(self._df, y_col)
            self.add_y_column_option(new_col)
            self._log_workflow("interpolate_missing", col=y_col)
            self.notify(f"Interpolation completed: {new_col}")
        except Exception as e:
            self.error_box("Interpolation failed", f"Reason: {e}")

    def feature_clean_remove_duplicates(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("No data", "Open a data file first.")
            return
        try:
            new_df, removed = remove_duplicates(self._df)
            self._swap_dataframe(new_df)
            self._log_workflow("remove_duplicates")
            self.notify(f"Removed {removed} duplicate rows ({len(new_df)} rows remain).")
        except Exception as e:
            self.error_box("Remove duplicates failed", f"Reason: {e}")

    def feature_clean_remove_outliers(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Remove Outliers", [
            {"name": "method", "label": "Method", "kind": "choice",
             "options": list(OUTLIER_METHODS), "default": "zscore"},
            {"name": "threshold", "label": "Threshold", "kind": "float",
             "default": 3.0, "min": 0.1, "max": 100.0, "decimals": 2},
        ], description=f"Drop rows where '{y_col}' is an outlier (zscore≈3, iqr≈1.5)")
        if res is None:
            return
        method, threshold = res["method"], res["threshold"]
        try:
            new_df, removed = remove_outliers(self._df, y_col, method=method, threshold=threshold)
            self._swap_dataframe(new_df)
            self._log_workflow("remove_outliers", col=y_col, method=method, threshold=threshold)
            self.notify(f"Removed {removed} outlier rows from {y_col} (method: {method}).")
        except Exception as e:
            self.error_box("Remove outliers failed", f"Reason: {e}")

    def feature_clean_normalize(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Normalize / Standardize", [
            {"name": "method", "label": "Method", "kind": "choice",
             "options": list(NORMALIZE_METHODS), "default": "zscore"},
        ], description=f"Rescale column '{y_col}' (zscore = mean 0 / minmax = 0–1)")
        if res is None:
            return
        method = res["method"]
        try:
            new_col = normalize_column(self._df, y_col, method=method)
            self.add_y_column_option(new_col)
            self._log_workflow("normalize_column", col=y_col, method=method)
            self.notify(f"Normalized column created: {new_col}")
        except Exception as e:
            self.error_box("Normalize failed", f"Reason: {e}")

    def feature_clean_detrend(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Detrend / Baseline", [
            {"name": "order", "label": "Polynomial order", "kind": "int",
             "default": 1, "min": 0, "max": 10},
        ], description=f"Remove trend/baseline from '{y_col}' (1 = linear, higher = curved baseline)")
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
            self.notify(f"Baseline/trend removed (order {order}): {new_col}")
        except Exception as e:
            self.error_box("Detrend failed", f"Reason: {e}")

    def feature_clean_sort(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("No data", "Open a data file first.")
            return
        cols = [str(c) for c in self._df.columns]
        res = self.ask_form("Sort", [
            {"name": "col", "label": "By column", "kind": "choice",
             "options": cols, "default": cols[0]},
            {"name": "direction", "label": "Direction", "kind": "choice",
             "options": ["Ascending", "Descending"], "default": "Ascending"},
        ])
        if res is None:
            return
        col = res["col"]
        try:
            ascending = (res["direction"] == "Ascending")
            new_df = sort_dataframe(self._df, col, ascending=ascending)
            self._swap_dataframe(new_df)
            self._log_workflow("sort_dataframe", col=col, ascending=ascending)
            self.notify(f"Data sorted by {col}.")
        except Exception as e:
            self.error_box("Sort failed", f"Reason: {e}")

    def feature_clean_resample(self):
        if not self._has_y_data():
            return
        x_col = self.selected_x_column()
        if x_col not in getattr(self._df, "columns", []):
            self.inform("Select X first", "Resample requires a numeric X column.")
            return
        n_default = len(self._df)
        res = self.ask_form("Resample (uniform grid)", [
            {"name": "n_points", "label": "Number of points", "kind": "int",
             "default": n_default, "min": 2, "max": 10_000_000},
        ], description=f"Resample onto an evenly-spaced '{x_col}' grid (linear interpolation)")
        if res is None:
            return
        n_points = res["n_points"]
        try:
            new_df = resample_uniform(self._df, x_col, n_points=int(n_points))
            self._swap_dataframe(new_df)
            self._log_workflow("resample_uniform", x_col=x_col, n_points=int(n_points))
            self.notify(f"Resampled to a uniform grid with {n_points} points (numeric columns only).")
        except Exception as e:
            self.error_box("Resample failed", f"Reason: {e}")

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

    def filter_column_butterworth(self, col, fs, kind="lowpass", cutoff=None):
        """Add a zero-phase Butterworth-filtered copy of *col* to the active data.

        Param-taking core shared by the dialog and the AI tool (no UI here).
        ``cutoff`` is a float for lowpass/highpass or a (lo, hi) pair for
        bandpass/bandstop. Returns the new column name; raises on bad input.
        """
        if self._df is None or col not in getattr(self._df, "columns", []):
            raise ValueError(f"column '{col}' not found in the active data")
        fs = float(fs)
        if fs <= 0:
            raise ValueError("fs must be positive")
        if kind in ("bandpass", "bandstop"):
            if not isinstance(cutoff, (tuple, list)) or len(cutoff) != 2:
                raise ValueError(f"{kind} needs a (low, high) cutoff pair")
            cutoff = (float(cutoff[0]), float(cutoff[1]))
        else:
            cutoff = float(cutoff)
        filtered = butterworth_filter(self._df[col], fs, kind=kind, cutoff=cutoff)
        new_col = f"{col}_{kind}"
        self._df[new_col] = filtered
        self.add_y_column_option(new_col)
        self._log_workflow(
            "butterworth_filter", col=col, fs=float(fs), kind=kind,
            cutoff=list(cutoff) if isinstance(cutoff, tuple) else float(cutoff),
            order=4, new_col=new_col)
        return new_col

    def feature_filter_butterworth(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        fs_guess = self._infer_fs_default()
        res = self.ask_form("Butterworth Filter", [
            {"name": "kind", "label": "Kind", "kind": "choice",
             "options": list(BUTTER_KINDS), "default": "lowpass"},
            {"name": "fs", "label": "fs (Hz)", "kind": "float",
             "default": round(fs_guess, 6), "min": 1e-9, "max": 1e12, "decimals": 6},
            {"name": "cutoff_lo", "label": "Low cutoff (Hz)", "kind": "float",
             "default": round(fs_guess / 10, 6), "min": 1e-12, "max": 1e12, "decimals": 6,
             "show_if": ("kind", ("bandpass", "bandstop"))},
            {"name": "cutoff_hi", "label": "High cutoff (Hz)", "kind": "float",
             "default": round(fs_guess / 5, 6), "min": 1e-12, "max": 1e12, "decimals": 6,
             "show_if": ("kind", ("bandpass", "bandstop"))},
            {"name": "cutoff", "label": "Cutoff (Hz)", "kind": "float",
             "default": round(fs_guess / 10, 6), "min": 1e-12, "max": 1e12, "decimals": 6,
             "show_if": ("kind", ("lowpass", "highpass"))},
        ], description=f"Zero-phase filter of '{y_col}' (fs inferred from the X axis)")
        if res is None:
            return
        kind, fs = res["kind"], float(res["fs"])
        if kind in ("bandpass", "bandstop"):
            cutoff = (float(res["cutoff_lo"]), float(res["cutoff_hi"]))
        else:
            cutoff = float(res["cutoff"])
        try:
            new_col = self.filter_column_butterworth(y_col, fs, kind=kind, cutoff=cutoff)
            self.notify(f"Signal filtered ({kind}): {new_col} (fs~{fs:.4g} Hz)")
        except Exception as e:
            self.error_box("Filter failed", f"Reason: {e}")

    def smooth_column(self, col, method="savitzky-golay", *, window=11, kernel=5, sigma=2.0):
        """Add a smoothed copy of *col* to the active data (param-taking core).

        method: savitzky-golay | median | gaussian. Returns new column name.
        Shared by the Smooth dialog and the AI tool; contains no UI.
        """
        if self._df is None or col not in getattr(self._df, "columns", []):
            raise ValueError(f"column '{col}' not found in the active data")
        if method == "savitzky-golay":
            smoothed = savitzky_golay(self._df[col], window_length=int(window))
            new_col, op, params = f"{col}_savgol", "savitzky_golay", {"col": col, "window": int(window)}
        elif method == "median":
            smoothed = median_filter(self._df[col], kernel_size=int(kernel))
            new_col, op, params = f"{col}_median", "median_filter", {"col": col, "kernel": int(kernel)}
        elif method == "gaussian":
            smoothed = gaussian_smooth(self._df[col], sigma=float(sigma))
            new_col, op, params = f"{col}_gauss", "gaussian_smooth", {"col": col, "sigma": float(sigma)}
        else:
            raise ValueError(f"unknown smooth method '{method}'")
        self._df[new_col] = smoothed
        self.add_y_column_option(new_col)
        self._log_workflow(op, new_col=new_col, **params)
        return new_col

    def feature_filter_smooth(self):
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Smooth (reduce noise)", [
            {"name": "method", "label": "Method", "kind": "choice",
             "options": ["savitzky-golay", "median", "gaussian"], "default": "savitzky-golay"},
            {"name": "window", "label": "Window length (odd)", "kind": "int",
             "default": 11, "min": 3, "max": 9999, "show_if": ("method", "savitzky-golay")},
            {"name": "kernel", "label": "Kernel size (odd)", "kind": "int",
             "default": 5, "min": 1, "max": 9999, "show_if": ("method", "median")},
            {"name": "sigma", "label": "Sigma (samples)", "kind": "float",
             "default": 2.0, "min": 0.01, "max": 1e6, "decimals": 2, "show_if": ("method", "gaussian")},
        ], description=f"Smooth signal '{y_col}' → new column")
        if res is None:
            return
        method = res["method"]
        try:
            new_col = self.smooth_column(
                y_col, method,
                window=int(res.get("window", 11)),
                kernel=int(res.get("kernel", 5)),
                sigma=float(res.get("sigma", 2.0)),
            )
            self.notify(f"Smooth completed ({method}): {new_col}")
        except Exception as e:
            self.error_box("Smooth failed", f"Reason: {e}")

    def feature_signal_hilbert(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        res = self.ask_form("Hilbert Transform", [
            {"name": "y_col", "label": "Signal column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
        ], description="Create analytic-signal real/imaginary columns from the selected signal.")
        if res is None:
            return
        y_col = res["y_col"]
        try:
            analytic = hilbert_transform(self._df[y_col])
            real_col = f"{y_col}_hilbert_real"
            imag_col = f"{y_col}_hilbert_imag"
            self._df[real_col] = np.real(analytic)
            self._df[imag_col] = np.imag(analytic)
            self.add_y_column_option(real_col)
            self.add_y_column_option(imag_col)
            self._sync_dataframe_after_column_edit()
            self._log_workflow("hilbert_transform", col=y_col, real_col=real_col, imag_col=imag_col)
            self.notify(f"Hilbert transform completed: {real_col}, {imag_col}")
        except Exception as e:
            self.error_box("Hilbert transform failed", f"Reason: {e}")

    def feature_signal_envelope(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        res = self.ask_form("Envelope Detection", [
            {"name": "y_col", "label": "Signal column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
        ], description="Detect amplitude envelope via Hilbert analytic signal.")
        if res is None:
            return
        y_col = res["y_col"]
        try:
            new_col = f"{y_col}_envelope"
            self._df[new_col] = signal_envelope(self._df[y_col])
            self.add_y_column_option(new_col)
            self._sync_dataframe_after_column_edit()
            self._log_workflow("signal_envelope", col=y_col, new_col=new_col)
            self.notify(f"Envelope detected: {new_col}")
        except Exception as e:
            self.error_box("Envelope detection failed", f"Reason: {e}")

    def feature_signal_instantaneous_frequency(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        fs_guess = self._infer_fs_default()
        res = self.ask_form("Instantaneous Frequency", [
            {"name": "y_col", "label": "Signal column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "fs", "label": "fs (Hz)", "kind": "float",
             "default": round(fs_guess, 6), "min": 1e-9, "max": 1e12, "decimals": 6},
        ], description="Track frequency from the derivative of Hilbert phase.")
        if res is None:
            return
        y_col, fs = res["y_col"], float(res["fs"])
        try:
            new_col = f"{y_col}_instfreq_Hz"
            self._df[new_col] = instantaneous_frequency(self._df[y_col], fs=fs)
            self.add_y_column_option(new_col)
            self._sync_dataframe_after_column_edit()
            self._log_workflow("instantaneous_frequency", col=y_col, fs=fs, new_col=new_col)
            self.notify(f"Frequency tracking completed: {new_col}")
        except Exception as e:
            self.error_box("Frequency tracking failed", f"Reason: {e}")

    def feature_signal_autocorrelation(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        max_lag_default = max(0, len(self._df) - 1)
        res = self.ask_form("Auto-correlation", [
            {"name": "y_col", "label": "Signal column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "max_lag", "label": "Max lag (samples)", "kind": "int",
             "default": max_lag_default, "min": 0, "max": max_lag_default},
            {"name": "normalize", "label": "Normalize lag 0 to 1", "kind": "bool",
             "default": True},
            {"name": "demean", "label": "Remove mean first", "kind": "bool",
             "default": True},
        ], description="Create lag and normalized auto-correlation columns.")
        if res is None:
            return
        y_col = res["y_col"]
        try:
            lags, corr = autocorrelation(
                self._df[y_col],
                max_lag=int(res["max_lag"]),
                normalize=bool(res["normalize"]),
                demean=bool(res["demean"]),
            )
            lag_col = f"{y_col}_autocorr_lag"
            corr_col = f"{y_col}_autocorr"
            self._df[lag_col] = self._series_for_active_index(lags)
            self._df[corr_col] = self._series_for_active_index(corr)
            self.add_x_column_option(lag_col)
            self.add_y_column_option(corr_col)
            self._sync_dataframe_after_column_edit()
            self._log_workflow(
                "autocorrelation", col=y_col, max_lag=int(res["max_lag"]),
                normalize=bool(res["normalize"]), demean=bool(res["demean"]),
                lag_col=lag_col, corr_col=corr_col)
            self.notify(f"Auto-correlation completed: {corr_col}")
        except Exception as e:
            self.error_box("Auto-correlation failed", f"Reason: {e}")

    def feature_signal_convolution(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        second = cols[1] if len(cols) > 1 else cols[0]
        res = self.ask_form("Convolution", [
            {"name": "a_col", "label": "Signal A", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "b_col", "label": "Signal B / kernel", "kind": "choice",
             "options": cols, "default": second},
            {"name": "mode", "label": "Mode", "kind": "choice",
             "options": list(CONVOLUTION_MODES), "default": "same"},
        ], description="Linear convolution. Blank cells in A/B are ignored so shorter kernels work.")
        if res is None:
            return
        a_col, b_col, mode = res["a_col"], res["b_col"], res["mode"]
        try:
            a = self._numeric_column_values(a_col, drop_blank=True)
            b = self._numeric_column_values(b_col, drop_blank=True)
            values = convolve_signals(a, b, mode=mode)
            new_col = f"{a_col}_conv_{b_col}"
            if values.size == len(self._df):
                self._df[new_col] = values
                self.add_y_column_option(new_col)
                self._sync_dataframe_after_column_edit()
                target = new_col
            else:
                result_df = pd.DataFrame({
                    "sample": np.arange(values.size, dtype=float),
                    new_col: values,
                })
                target = self._open_signal_result_book(f"Convolution_{a_col}_{b_col}", result_df)
            self._log_workflow("convolve_signals", a_col=a_col, b_col=b_col, mode=mode, output=target)
            self.notify(f"Convolution completed ({mode}): {target}")
        except Exception as e:
            self.error_box("Convolution failed", f"Reason: {e}")

    def feature_signal_deconvolution(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        second = cols[1] if len(cols) > 1 else cols[0]
        res = self.ask_form("Deconvolution", [
            {"name": "observed_col", "label": "Observed / convolved signal", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "kernel_col", "label": "Kernel / impulse response", "kind": "choice",
             "options": cols, "default": second},
        ], description="Return quotient and remainder in a new Book. Blank cells in the kernel are ignored.")
        if res is None:
            return
        observed_col, kernel_col = res["observed_col"], res["kernel_col"]
        try:
            observed = self._numeric_column_values(observed_col, drop_blank=True)
            kernel = self._numeric_column_values(kernel_col, drop_blank=True)
            quotient, remainder = deconvolve_signals(observed, kernel)
            n = max(quotient.size, remainder.size)
            result_df = pd.DataFrame({"sample": np.arange(n, dtype=float)})
            result_df[f"{observed_col}_deconv_{kernel_col}"] = pd.Series(quotient)
            result_df[f"{observed_col}_deconv_remainder"] = pd.Series(remainder)
            target = self._open_signal_result_book(
                f"Deconvolution_{observed_col}_{kernel_col}", result_df)
            self._log_workflow(
                "deconvolve_signals", observed_col=observed_col,
                kernel_col=kernel_col, output=target)
            self.notify(f"Deconvolution completed: {target}")
        except Exception as e:
            self.error_box("Deconvolution failed", f"Reason: {e}")

    def feature_signal_ifft(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        imag_default = next(
            (c for c in cols if "imag" in c.lower() or c.lower().endswith("_im")),
            "<none>",
        )
        res = self.ask_form("Inverse FFT (IFFT)", [
            {"name": "real_col", "label": "Spectrum real / complex-real column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "imag_col", "label": "Spectrum imaginary column", "kind": "choice",
             "options": ["<none>"] + cols, "default": imag_default},
        ], description="Create a time-domain IFFT result Book from real plus optional imaginary columns.")
        if res is None:
            return
        real_col, imag_col = res["real_col"], res["imag_col"]
        try:
            real = self._numeric_column_values(real_col, drop_blank=True)
            if imag_col and imag_col != "<none>":
                imag = self._numeric_column_values(imag_col, drop_blank=True)
                n = min(real.size, imag.size)
                spectrum = real[:n] + 1j * imag[:n]
            else:
                spectrum = real
            out = np.asarray(compute_ifft(spectrum))
            result_df = pd.DataFrame({"sample": np.arange(out.size, dtype=float)})
            if np.iscomplexobj(out):
                result_df[f"{real_col}_ifft_real"] = np.real(out)
                result_df[f"{real_col}_ifft_imag"] = np.imag(out)
            else:
                result_df[f"{real_col}_ifft"] = out.astype(float)
            target = self._open_signal_result_book(f"IFFT_{real_col}", result_df)
            self._log_workflow("compute_ifft", real_col=real_col, imag_col=imag_col, output=target)
            self.notify(f"IFFT completed: {target}")
        except Exception as e:
            self.error_box("IFFT failed", f"Reason: {e}")

    def feature_signal_stft(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        fs_guess = self._infer_fs_default()
        n_default = max(2, min(256, len(self._df)))
        res = self.ask_form("STFT", [
            {"name": "y_col", "label": "Signal column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "fs", "label": "fs (Hz)", "kind": "float",
             "default": round(fs_guess, 6), "min": 1e-9, "max": 1e12, "decimals": 6},
            {"name": "window", "label": "Window", "kind": "choice",
             "options": ["hann", "hamming", "blackman"], "default": "hann"},
            {"name": "nperseg", "label": "Window length (samples)", "kind": "int",
             "default": n_default, "min": 2, "max": max(2, len(self._df))},
            {"name": "noverlap", "label": "Overlap (samples)", "kind": "int",
             "default": n_default // 2, "min": 0, "max": max(1, n_default - 1)},
        ], description="Short-time Fourier transform. Results open as a long-format Book.")
        if res is None:
            return
        y_col = res["y_col"]
        try:
            freqs, times, zxx = compute_stft(
                self._df[y_col],
                fs=float(res["fs"]),
                window=res["window"],
                nperseg=int(res["nperseg"]),
                noverlap=int(res["noverlap"]),
            )
            time_grid, freq_grid = np.meshgrid(times, freqs)
            magnitude = np.abs(zxx)
            result_df = pd.DataFrame({
                "time": time_grid.ravel(),
                "frequency_Hz": freq_grid.ravel(),
                "magnitude": magnitude.ravel(),
                "power": (magnitude ** 2).ravel(),
                "phase_rad": np.angle(zxx).ravel(),
            })
            target = self._open_signal_result_book(f"STFT_{y_col}", result_df)
            self._log_workflow(
                "compute_stft", col=y_col, fs=float(res["fs"]), window=res["window"],
                nperseg=int(res["nperseg"]), noverlap=int(res["noverlap"]), output=target)
            self.notify(f"STFT completed: {target}")
        except Exception as e:
            self.error_box("STFT failed", f"Reason: {e}")

    def feature_signal_zero_pad(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        n = max(1, len(self._df))
        default_target = 1 << (n - 1).bit_length()
        res = self.ask_form("Zero Padding", [
            {"name": "y_col", "label": "Signal column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "target_length", "label": "Target length", "kind": "int",
             "default": default_target, "min": n, "max": 100_000_000},
        ], description="Append zeros up to target length. Longer outputs open as a new Book.")
        if res is None:
            return
        y_col, target_length = res["y_col"], int(res["target_length"])
        try:
            padded = zero_pad(self._df[y_col], target_length=target_length)
            new_col = f"{y_col}_zeropad"
            if padded.size == len(self._df):
                self._df[new_col] = padded
                self.add_y_column_option(new_col)
                self._sync_dataframe_after_column_edit()
                target = new_col
            else:
                result_df = pd.DataFrame({
                    "sample": np.arange(padded.size, dtype=float),
                    new_col: padded,
                })
                target = self._open_signal_result_book(f"ZeroPad_{y_col}", result_df)
            self._log_workflow("zero_pad", col=y_col, target_length=target_length, output=target)
            self.notify(f"Zero padding completed: {target}")
        except Exception as e:
            self.error_box("Zero padding failed", f"Reason: {e}")

    def feature_signal_decimation(self):
        """Downsample a signal by an integer factor into a result Book."""
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        x_sel = self.selected_x_column()
        res = self.ask_form("Decimation", [
            {"name": "y_col", "label": "Signal column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "x_col", "label": "X column", "kind": "choice",
             "options": ["<row index>"] + cols,
             "default": x_sel if x_sel in cols else "<row index>"},
            {"name": "factor", "label": "Decimation factor", "kind": "int",
             "default": 2, "min": 2, "max": max(2, len(self._df))},
        ], description="Keep every Nth sample and open the shorter result as a new Book.")
        if res is None:
            return
        y_col = res["y_col"]
        x_col = res["x_col"]
        factor = int(res["factor"])
        try:
            source_index = np.arange(len(self._df), dtype=int)[::factor]
            y_values = pd.to_numeric(
                self._df[y_col], errors="coerce"
            ).to_numpy(dtype=float)[::factor]
            result = {
                "source_row": source_index + 1,
                f"{y_col}_decim{factor}": y_values,
            }
            if x_col != "<row index>" and x_col in cols:
                x_series = self._df[x_col].iloc[::factor].reset_index(drop=True)
                result = {
                    "source_row": source_index + 1,
                    str(x_col): x_series,
                    f"{y_col}_decim{factor}": y_values,
                }
            result_df = pd.DataFrame(result)
            target = self._open_signal_result_book(f"Decimation_{y_col}", result_df)
            self._log_workflow(
                "decimation", col=y_col, x_col=x_col, factor=factor, output=target
            )
            self.notify(f"Decimation complete: {target}")
        except Exception as e:
            self.error_box("Decimation failed", f"Reason: {e}")

    def feature_signal_harmonic_analysis(self):
        """Extract dominant harmonic frequencies into a result Book."""
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        fs_guess = self._infer_fs_default()
        res = self.ask_form("Harmonic Analysis", [
            {"name": "y_col", "label": "Signal column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "fs", "label": "Sampling rate fs (Hz)", "kind": "float",
             "default": round(fs_guess, 6), "min": 1e-9, "max": 1e12, "decimals": 6},
            {"name": "top_n", "label": "Number of components", "kind": "int",
             "default": 8, "min": 1, "max": max(1, min(len(self._df), 1000))},
            {"name": "window", "label": "Window", "kind": "choice",
             "options": ["hann", "hamming", "blackman", "kaiser", "none"], "default": "hann"},
        ], description="Find dominant frequency components and estimate harmonic order.")
        if res is None:
            return
        y_col = res["y_col"]
        try:
            result = harmonic_analysis(
                self._df[y_col],
                fs=float(res["fs"]),
                top_n=int(res["top_n"]),
                window=res["window"],
            )
            table = pd.DataFrame(result)
            table.insert(0, "source_column", y_col)
            target = self._open_signal_result_book(f"Harmonics_{y_col}", table)
            self._log_workflow(
                "harmonic_analysis",
                col=y_col,
                fs=float(res["fs"]),
                top_n=int(res["top_n"]),
                window=res["window"],
                output=target,
            )
            self.notify(f"Harmonic analysis complete -> {target}")
        except Exception as e:
            self.error_box("Harmonic Analysis failed", f"Reason: {e}")

    # ---------- Peak & signal-quality metrics (ROADMAP E) ----------
    def _finite_xy_for_metrics(self, y_name=None):
        """(x, y, x_name, y_name) เป็น float ที่ finite ทั้งคู่ — สำหรับ FWHM/พื้นที่พีค"""
        import numpy as np

        y_name = y_name or self.selected_y_column()
        y = pd.to_numeric(self._df[y_name], errors="coerce").to_numpy(dtype=float)
        x_name = self.selected_x_column()
        if x_name in [str(c) for c in self._df.columns]:
            ser = self._df[x_name]
            if pd.api.types.is_datetime64_any_dtype(ser):
                x = (ser - ser.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
            else:
                x = pd.to_numeric(ser, errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(x).any():
                # text X column (e.g. a result sheet's name column) → row index
                x_name = "index"
                x = np.arange(y.size, dtype=float)
        else:
            x_name = "index"
            x = np.arange(y.size, dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        return x[mask], y[mask], x_name, y_name

    def feature_peak_metrics(self):
        """Analysis → Peak Metrics: เลือกคอลัมน์ในฟอร์มเดียว → Book ผลลัพธ์
        (area / FWHM / ตำแหน่ง+ความสูงพีคหลัก) แบบ Origin result sheet"""
        if not self._has_y_data():
            return
        numeric = self._numeric_column_names()
        if not numeric:
            self.inform("ไม่มีคอลัมน์ตัวเลข", "ต้องมีคอลัมน์ตัวเลขอย่างน้อย 1 คอลัมน์")
            return
        x_name = self.selected_x_column()
        x_label = x_name if x_name in numeric else "row index"
        y_sel = self.selected_y_column()
        res = self.ask_form("Peak Metrics (FWHM / Area)", [
            {"name": "columns", "label": "Y column", "kind": "choice",
             "options": [self._ALL_NUMERIC_LABEL] + numeric,
             "default": y_sel if y_sel in numeric else self._ALL_NUMERIC_LABEL},
        ], description=(f"ข้อมูลจาก: {self._active_book_label()}\n"
                        f"พื้นที่ใต้กราฟ (trapezoid) + FWHM + ตำแหน่ง/ความสูงพีคหลัก "
                        f"เทียบแกน X = '{x_label}' → เปิดเป็น Book ผลลัพธ์"))
        if res is None:
            return
        if res["columns"] == self._ALL_NUMERIC_LABEL:
            chosen = [c for c in numeric if c != x_name] or numeric
        else:
            chosen = [res["columns"]]
        rows, errors = [], []
        for col in chosen:
            try:
                x, y, _, _ = self._finite_xy_for_metrics(col)
                summary = peak_metrics_summary(x, y)
                if summary.get("fwhm") is None:
                    summary["fwhm"] = float("nan")
                rows.append({"column": col, **summary})
            except Exception as e:
                errors.append(f"{col}: {e}")
        if not rows:
            self.error_box("คำนวณไม่สำเร็จ", "\n".join(errors) or "ไม่มีข้อมูลพอ")
            return
        table = pd.DataFrame(rows)[["column", "points", "area", "fwhm",
                                    "peak_x", "peak_height"]]
        book = self._open_signal_result_book("Peak Metrics", table)
        self._log_workflow("peak_metrics", columns=chosen, x=x_label, book=book)
        self.notify(f"Peak metrics ({len(rows)} คอลัมน์) → {book}")

    def feature_signal_quality(self):
        """Analysis → Signal Quality: คอลัมน์ + fs ในฟอร์มเดียว → Book ผลลัพธ์
        (SNR / noise floor จาก Welch PSD)"""
        if not self._has_y_data():
            return
        numeric = self._numeric_column_names()
        if not numeric:
            self.inform("ไม่มีคอลัมน์ตัวเลข", "ต้องมีคอลัมน์ตัวเลขอย่างน้อย 1 คอลัมน์")
            return
        y_sel = self.selected_y_column()
        res = self.ask_form("Signal Quality (SNR / Noise floor)", [
            {"name": "columns", "label": "Y column", "kind": "choice",
             "options": [self._ALL_NUMERIC_LABEL] + numeric,
             "default": y_sel if y_sel in numeric else self._ALL_NUMERIC_LABEL},
            {"name": "fs", "label": "Sampling rate fs (Hz)", "kind": "float",
             "default": round(self._infer_fs_default(), 6),
             "min": 1e-9, "max": 1e12, "decimals": 6},
        ], description=(f"ข้อมูลจาก: {self._active_book_label()}\n"
                        "SNR (พีคเทียบ median Welch PSD) และ noise floor "
                        "→ เปิดเป็น Book ผลลัพธ์ (fs เดาจากแกน X ให้แล้ว)"))
        if res is None:
            return
        fs = float(res["fs"])
        x_name = self.selected_x_column()
        if res["columns"] == self._ALL_NUMERIC_LABEL:
            chosen = [c for c in numeric if c != x_name] or numeric
        else:
            chosen = [res["columns"]]
        rows, errors = [], []
        for col in chosen:
            try:
                rows.append({"column": col,
                             **signal_quality_summary(self._df[col], fs=fs)})
            except Exception as e:
                errors.append(f"{col}: {e}")
        if not rows:
            self.error_box("คำนวณไม่สำเร็จ", "\n".join(errors) or "ไม่มีข้อมูลพอ")
            return
        table = pd.DataFrame(rows)[["column", "fs_hz", "snr_db", "noise_floor"]]
        book = self._open_signal_result_book("Signal Quality", table)
        self._log_workflow("signal_quality", columns=chosen, fs=fs, book=book)
        first = rows[0]
        self.notify(f"SNR {first['column']}: {first['snr_db']:.4g} dB → {book}")

    def feature_apply_window(self):
        """คูณสัญญาณด้วย window (hann/hamming/blackman/kaiser) → คอลัมน์ใหม่"""
        if not self._has_y_data():
            return
        y_col = self.selected_y_column()
        res = self.ask_form("Apply Window", [
            {"name": "window", "label": "Window type", "kind": "choice",
             "options": list(WINDOW_KINDS), "default": "hann"},
            {"name": "beta", "label": "Beta (Kaiser)", "kind": "float",
             "default": 14.0, "min": 0.0, "max": 100.0, "decimals": 2,
             "show_if": ("window", "kaiser")},
        ], description=f"Multiply '{y_col}' by a taper window → new column")
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
        """Analysis → Descriptive Statistics: เลือกคอลัมน์ → Book ผลลัพธ์
        (ตารางสถิติแบบ Origin result sheet แทน message box เดิม)"""
        if not self._has_y_data():
            return
        numeric = self._numeric_column_names()
        if not numeric:
            self.inform("ไม่มีคอลัมน์ตัวเลข", "ต้องมีคอลัมน์ตัวเลขอย่างน้อย 1 คอลัมน์")
            return
        y_sel = self.selected_y_column()
        res = self.ask_form("Descriptive Statistics", [
            {"name": "columns", "label": "Columns", "kind": "choice",
             "options": [self._ALL_NUMERIC_LABEL] + numeric,
             "default": y_sel if y_sel in numeric else self._ALL_NUMERIC_LABEL},
        ], description=(f"ข้อมูลจาก: {self._active_book_label()}\n"
                        "count / mean / median / mode / std / variance / "
                        "skewness / kurtosis / min / max → เปิดเป็น Book ผลลัพธ์"))
        if res is None:
            return
        cols = None if res["columns"] == self._ALL_NUMERIC_LABEL else [res["columns"]]
        try:
            table = descriptive_table(self._df, cols)
            book = self._open_signal_result_book("Descriptive Stats", table)
            self._log_workflow("descriptive_statistics",
                               columns=cols or numeric, book=book)
            self.notify(f"Descriptive statistics ({table.shape[1] - 1} คอลัมน์) → {book}")
        except Exception as e:
            self.error_box("คำนวณสถิติไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_show_covariance(self):
        """Analysis → Covariance Matrix: เลือกชนิด matrix → Book ผลลัพธ์
        (ตาราง matrix จริง copy/export ได้ แทนการยัด text ใน message box)"""
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล",
                        "เปิดไฟล์ หรือพิมพ์ข้อมูลลง Book แล้วกด 'ใช้ข้อมูลนี้' ก่อน")
            return
        numeric = self._numeric_column_names()
        if len(numeric) < 2:
            self.inform("ข้อมูลไม่พอ", "ต้องมีคอลัมน์ตัวเลขอย่างน้อย 2 คอลัมน์")
            return
        res = self.ask_form("Covariance / Correlation Matrix", [
            {"name": "kind", "label": "Matrix", "kind": "choice",
             "options": ["Covariance", "Correlation"], "default": "Covariance"},
        ], description=(f"ข้อมูลจาก: {self._active_book_label()}\n"
                        f"คำนวณจากคอลัมน์ตัวเลขทั้งหมด ({len(numeric)} คอลัมน์) "
                        "→ เปิดเป็น Book ผลลัพธ์"))
        if res is None:
            return
        kind = str(res["kind"]).lower()
        try:
            table = covariance_table(self._df, kind=kind)
            book = self._open_signal_result_book(f"{res['kind']} Matrix", table)
            self._log_workflow("covariance_matrix", kind=kind, book=book)
            self.notify(f"{res['kind']} matrix ({len(numeric)}×{len(numeric)}) → {book}")
        except Exception as e:
            self.error_box("คำนวณไม่สำเร็จ", f"สาเหตุ: {e}")

    def run_psd_dialog(self):
        if not self._has_y_data():
            return
        cols = [str(c) for c in self._df.columns]
        y_sel = self.selected_y_column()
        res = self.ask_form("PSD (Welch)", [
            {"name": "y_col", "label": "Y column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "fs", "label": "fs (Hz)", "kind": "float",
             "default": round(self._infer_fs_default(), 6), "min": 1e-9, "max": 1e12, "decimals": 6},
        ], description="Power spectral density (fs inferred from the X axis) → new graph")
        if res is None:
            return
        y_col, fs = res["y_col"], float(res["fs"])
        try:
            freqs, pxx = welch_psd(self._df[y_col], fs=fs)
            canvas = self._active_canvas() if hasattr(self, "_active_canvas") else getattr(self, "canvas", None)
            if canvas is None:
                self.inform("No graph", "Open or select a graph window first")
                return
            self.canvas = canvas
            try:
                if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE:
                    self.canvas.clear()
            except Exception:
                pass
            self.canvas.ax.semilogy(freqs, pxx, linewidth=2)
            self.canvas.ax.set_xlabel("Frequency (Hz)")
            self.canvas.ax.set_ylabel("PSD")
            beautify_axes(self.canvas.ax, title=f"Welch PSD of {y_col} (fs≈{fs:.4g} Hz)")
            try:
                self.canvas.draw()
            except Exception:
                pass
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
            {"name": "y_col", "label": "Y column", "kind": "choice",
             "options": cols, "default": y_sel if y_sel in cols else cols[0]},
            {"name": "window", "label": "Window", "kind": "choice",
             "options": ["hanning", "hamming", "none"], "default": "hanning"},
            {"name": "detrend", "label": "Remove mean first", "kind": "bool", "default": True},
        ], description="Fourier transform (fs inferred from the X axis) → spectrum in a new graph")
        if res is None:
            return
        y_col, window, detrend = res["y_col"], res["window"], bool(res["detrend"])

        x_col = self.selected_x_column()

        try:
            df_fft, fs = compute_fft(self._df, x_col=x_col, y_col=y_col, detrend=detrend, window=window)
            self._fft_df = df_fft
            self._fft_meta = {"fs": fs, "x_col": x_col, "y_col": y_col, "window": window, "detrend": detrend}
            canvas = self._active_canvas() if hasattr(self, "_active_canvas") else getattr(self, "canvas", None)
            if canvas is None:
                self.inform("No graph", "Open or select a graph window first")
                return
            self.canvas = canvas

            try:
                if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE:
                    self.canvas.clear()
            except Exception:
                pass
            self.canvas.ax.plot(df_fft["freq_Hz"].values, df_fft["amplitude"].values, linewidth=2)
            self.canvas.ax.set_xlabel("Frequency (Hz)")
            self.canvas.ax.set_ylabel("Amplitude")
            beautify_axes(self.canvas.ax, title=f"FFT of {y_col} (fs≈{fs:.3f} Hz, window={window}, detrend={detrend})")
            try:
                self.canvas.draw()
            except Exception:
                pass
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
