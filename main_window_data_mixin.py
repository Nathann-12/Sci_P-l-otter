from __future__ import annotations

import logging
import os
import warnings

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QFileDialog, QMessageBox

from core.plot_request import BarRequest, HistogramRequest, PlotOptions, PlotRequest
from loaders import (
    load_cdf_nc_on_demand, load_hdf5, load_json, load_mat, load_tabular, load_xml,
)

# ฟิลเตอร์ไฟล์ข้อมูลที่รองรับ (ใช้ทั้ง open เดี่ยวและ batch)
DATA_FILE_FILTER = (
    "Data Files (*.csv *.tsv *.txt *.xlsx *.nc *.cdf *.json *.h5 *.hdf5 *.hdf *.mat *.xml)"
    ";;All Files (*.*)"
)


class MainWindowDataMixin:
    def _coerce_datetime(self, values):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Could not infer format, so each element will be parsed individually.*",
                category=UserWarning,
            )
            return pd.to_datetime(values, errors="coerce")

    def _load_dataframe_for_path(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext in [".csv", ".txt", ".tsv", ".xlsx"]:
            df, enc_note = load_tabular(path, ext)
            if df is None or df.empty:
                raise ValueError("The table file is empty or could not be read.")
            return df, "table", enc_note
        if ext in [".nc", ".cdf"]:
            df = load_cdf_nc_on_demand(self, path)
            if df is None or df.empty:
                raise ValueError("The CDF/NetCDF file has no plottable data.")
            return df, "CDF/NetCDF", None
        if ext == ".json":
            df, note = load_json(path)
            return df, "JSON", note
        if ext in (".h5", ".hdf5", ".hdf"):
            df, note = load_hdf5(path)
            return df, "HDF5", note
        if ext == ".mat":
            df, note = load_mat(path)
            return df, "MAT", note
        if ext == ".xml":
            df, note = load_xml(path)
            return df, "XML", note
        raise ValueError("Unsupported file extension.")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Data File", "", DATA_FILE_FILTER)
        if not path:
            return
        try:
            try:
                df, kind, _enc_note = self._load_dataframe_for_path(path)
            except Exception as e:
                ext = os.path.splitext(path)[1].lower()
                if ext in [".nc", ".cdf"]:
                    error_msg = f"Unable to read the CDF/NetCDF file:\n{str(e)}"
                    QMessageBox.critical(self, "Error", error_msg)
                    return
                raise

            # Origin model: 1 ไฟล์ = 1 Book (สร้าง+activate ใน _stage_insert)
            name = f"{os.path.basename(path)} [{kind}]"
            self._stage_insert(name, df, path)
            self.statusBar().showMessage(
                f"Opened as Book: {name} - select worksheet columns, then click a plot icon."
            )
        except Exception as e:
            QMessageBox.critical(self, "Open File Failed", f"Reason: {e}")

    def _open_book_for_dataset(self, name: str, df, path=None):
        """สร้าง Book window ใหม่ให้ dataset (Origin: 1 ชุดข้อมูล = 1 Book)

        คืน WorkbookWidget ที่สร้าง; ผูกสัญญาณ worksheet ครบชุดและ activate
        ทันที (ตัว handler bookActivated จะสลับ _df ให้เอง)
        """
        from widgets.workbook import WorkbookWidget

        wb = WorkbookWidget(self)
        wb.set_dataframe(df)
        wb.dataset_name = name
        self._wire_book_signals(wb)
        sub = self.mdi.add_book(wb, title=name)
        try:
            self.mdi.mdi.setActiveSubWindow(sub)
        except Exception:
            pass
        # activation signal may be suppressed while constructing — sync now
        self._on_book_activated(sub.windowTitle())
        # On the real desktop a closing modal dialog restores focus to the
        # previously active window right after this call, hiding a freshly
        # opened result Book behind a maximized Graph. Re-assert activation on
        # the next event-loop turn so the new Book always ends up on top.
        try:
            from PySide6.QtCore import QTimer

            def _surface(sub_ref=sub):
                try:
                    if sub_ref is not None and sub_ref.isVisible():
                        self.mdi.mdi.setActiveSubWindow(sub_ref)
                        sub_ref.raise_()
                except RuntimeError:
                    pass  # subwindow already deleted

            QTimer.singleShot(0, _surface)
        except Exception:
            logging.getLogger(__name__).debug(
                "result book surfacing skipped", exc_info=True)
        return wb

    def _wire_book_signals(self, wb) -> None:
        """Connect a Book worksheet's signals to the MainWindow handlers."""
        try:
            wb.use_data_requested.connect(self.adopt_workbook_data)
            wb.plot_requested.connect(lambda s: self.plot_from_workbook(s, new_graph=True))
            wb.overlay_requested.connect(lambda s: self.plot_from_workbook(s, new_graph=False))
            wb.status_message.connect(self._show_workbook_status)
            connect_state = getattr(self, "_connect_workbook_state_signal", None)
            if callable(connect_state):
                connect_state(wb)
            connect_recipes = getattr(self, "_connect_analysis_recipe_book", None)
            if callable(connect_recipes):
                connect_recipes(wb)
        except Exception:
            logging.getLogger(__name__).debug("book signal wiring failed", exc_info=True)

    def _new_blank_book(self, title: str = "Book1"):
        """Open a fresh empty worksheet so the app always has a Book to work in
        (used when the user closes the last remaining Book)."""
        from widgets.workbook import WorkbookWidget

        wb = WorkbookWidget(self)
        wb.dataset_name = title
        self._wire_book_signals(wb)
        sub = self.mdi.add_book(wb, title=title)
        self.workbook = wb
        self._book_sub = sub
        self._df = None
        self._current_path = None
        try:
            self.mdi.mdi.setActiveSubWindow(sub)
        except Exception:
            logging.getLogger(__name__).debug("activate blank book failed", exc_info=True)
        self._on_book_activated(sub.windowTitle())
        return wb

    def _discard_unused_initial_book(self) -> bool:
        """Close the untouched startup Book1 after the first real Book opens."""
        starter = getattr(self, "_initial_workbook", None)
        if starter is None or starter is getattr(self, "workbook", None):
            return False
        source_df = getattr(starter, "source_df", None)
        has_source = isinstance(source_df, pd.DataFrame) and not source_df.empty
        if has_source or bool(getattr(starter, "is_dirty", False)):
            return False
        remover = getattr(getattr(self, "mdi", None), "remove_book", None)
        if not callable(remover) or not remover(widget=starter):
            return False
        self._initial_workbook = None
        self._book_sub = None
        return True

    def _show_workbook_status(self, message: str) -> None:
        """Surface transient worksheet feedback (e.g. 'select a column first')."""
        try:
            self.statusBar().showMessage(str(message), 4000)
        except Exception:
            logging.getLogger(__name__).debug("workbook status show failed", exc_info=True)

    def _on_book_closed(self, title: str):
        """After a Book window is closed, keep the active data valid.

        The closed Book's widget is deleted right after this returns, so if it
        was the active worksheet we switch ``self.workbook``/``self._df`` to a
        surviving Book now (QMdiArea may otherwise activate a Graph, leaving a
        dangling reference). If it was the *last* Book, open a fresh blank one so
        the app always has a worksheet to type/plot into.
        """
        ws = getattr(self, "mdi", None)
        books = getattr(ws, "_books", {}) or {}
        active = getattr(self, "workbook", None)
        active_still_open = any(entry[0] is active for entry in books.values())
        try:
            if not books:
                self._new_blank_book()
            elif not active_still_open:
                self._activate_book_by_name(next(iter(books)))
        except Exception:
            logging.getLogger(__name__).debug(
                "recover active book after close failed", exc_info=True
            )
        refresh = getattr(self, "_refresh_action_states", None)
        if callable(refresh):
            refresh()

    def _on_book_activated(self, title: str):
        """สลับข้อมูลทำงานตาม Book ที่ active (หัวใจของ Origin multi-book)"""
        wb = self.mdi.book_widget(title)
        if wb is None:
            return
        self.workbook = wb
        df = getattr(wb, "source_df", None)
        registry = getattr(self, "_datasets", {}).get(getattr(wb, "dataset_name", "") or title)
        if df is None and registry:
            df = registry.get("df")
        if df is not None and not getattr(df, "empty", True):
            self._df = df
            self._current_path = (registry or {}).get("path")
            try:
                self.load_columns_from_df(show_status=False)
            except Exception:
                import logging
                logging.getLogger(__name__).debug("column reload on book switch failed", exc_info=True)
            try:
                self.lblFile.setText(f"Active Book: {title}")
            except Exception:
                pass
            self.statusBar().showMessage(
                f"Using data from Book: {title} ({len(df):,} rows x {len(df.columns)} columns)")
        else:
            self._df = None
            self._current_path = None
            # Book เปล่า (เช่นพิมพ์เองยังไม่กด 'ใช้ข้อมูลนี้') — ชี้ workbook ไว้พอ
            self.statusBar().showMessage(
                f"Book: {title} has no data yet - type data and click 'Use This Data' or plot from the worksheet.")
        _refresh_states = getattr(self, "_refresh_action_states", None)
        if callable(_refresh_states):
            _refresh_states()
        refresh_ai = getattr(self, "_refresh_ai_context", None)
        if callable(refresh_ai):
            refresh_ai()
        refresh_processing = getattr(self, "_refresh_processing_context", None)
        if callable(refresh_processing):
            refresh_processing()

    def load_data(self, path: str):
        """โหลดไฟล์ (เช่นจาก drag & drop) → Book ใหม่ตามโมเดล Origin"""
        try:
            try:
                df, kind, _enc_note = self._load_dataframe_for_path(path)
            except Exception as e:
                ext = os.path.splitext(path)[1].lower()
                if ext in [".nc", ".cdf"]:
                    QMessageBox.critical(
                        self, "Error", f"Unable to read the CDF/NetCDF file:\n{e}")
                    self.statusBar().showMessage("Error opening CDF/NetCDF file.")
                    return
                raise
            name = f"{os.path.basename(path)} [{kind}]"
            self._stage_insert(name, df, path)
            self.statusBar().showMessage(
                f"Opened as Book: {name} - select worksheet columns, then click a plot icon.")
        except Exception as e:
            QMessageBox.critical(self, "Open File Failed", f"Reason: {e}")
            self.statusBar().showMessage("Error opening file.")

    def adopt_workbook_data(self) -> bool:
        """ขั้น ① ของ workflow: นำข้อมูลที่พิมพ์/แก้ใน Book1 มาเป็น DataFrame หลัก

        คืน True เมื่อสำเร็จ (มีข้อมูลจริงและคอลัมน์ถูกโหลดเข้า X/Y แล้ว)
        """
        wb = getattr(self, "workbook", None)
        if wb is None:
            return False
        try:
            df = wb.dataframe()
        except Exception as e:
            QMessageBox.critical(self, "Read Worksheet Failed", f"Reason: {e}")
            return False
        if df is None or df.empty:
            QMessageBox.information(
                self, "Worksheet is Empty",
                "Type data into Book1 first (column A = X, column B = Y).")
            return False
        self._df = df.copy()
        self._current_path = None
        # multi-book: ข้อมูลที่พิมพ์เป็นของ Book นี้ — เก็บไว้กับตัว Book และ
        # ลงทะเบียนใน registry เพื่อให้สลับ Book ไป-กลับแล้วข้อมูลไม่หาย
        try:
            wb.source_df = self._df
            if hasattr(wb, "mark_clean"):
                wb.mark_clean()
            key = getattr(wb, "dataset_name", "") or self._book_title_for(wb) or "Book1"
            wb.dataset_name = key
            if hasattr(self, "_datasets"):
                # อย่าทับ path เดิม — Book ที่มาจากไฟล์ต้อง restore ได้จาก session
                existing = self._datasets.get(key) or {}
                self._datasets[key] = {"df": self._df, "path": existing.get("path")}
        except Exception:
            import logging
            logging.getLogger(__name__).debug("book registry sync failed", exc_info=True)
        self.load_columns_from_df()
        self.statusBar().showMessage(
            f"Worksheet data is active ({len(df)} rows x {len(df.columns)} columns). "
            "Select worksheet columns or use the X/Y column designations, then plot.")
        refresh_ai = getattr(self, "_refresh_ai_context", None)
        if callable(refresh_ai):
            refresh_ai()
        return True

    def _activate_book_by_name(self, name: str) -> bool:
        """Activate (raise + switch data to) the Book titled/registered as ``name``."""
        try:
            for kind, title, sub in self.mdi.sub_windows():
                if kind != "book":
                    continue
                widget = sub.widget()
                if title == name or getattr(widget, "dataset_name", "") == name:
                    self.mdi.mdi.setActiveSubWindow(sub)
                    self._on_book_activated(title)
                    return True
        except Exception:
            import logging
            logging.getLogger(__name__).debug("activate book by name failed", exc_info=True)
        return False

    def _book_title_for(self, wb) -> str:
        """คืน title ของ Book window ที่ถือ widget นี้อยู่ ('' ถ้าไม่พบ)"""
        try:
            for kind, title, sub in self.mdi.sub_windows():
                if kind == "book" and sub.widget() is wb:
                    return title
        except Exception:
            pass
        return ""

    def load_columns_from_df(self, *, show_status: bool = True):
        self._df = self._resolve_active_dataframe()
        if not isinstance(self._df, pd.DataFrame):
            QMessageBox.information(self, "No Data", "Open a data file first.")
            return

        rows_count = len(self._df)
        cols_count = len(self._df.columns)

        cols = [str(c) for c in self._df.columns]
        self.cbX.clear()
        self.cbY.clear()
        self.cbX.addItems(cols)
        self.cbY.addItems(cols)
        # ค่าเริ่มต้นอัจฉริยะ: X = คอลัมน์เวลา (ถ้ามี) ไม่งั้นคอลัมน์แรก,
        # Y = คอลัมน์แรกที่ไม่ใช่ X — ไม่งั้น operation ต่าง ๆ (cleaning/filter/
        # สถิติ) จะไปลงคอลัมน์เวลาแทนสัญญาณจริง
        try:
            time_like = [c for c in cols
                         if str(c).lower() == "t"
                         or any(k in str(c).lower() for k in ("time", "timestamp", "datetime", "date"))]
            x_guess = time_like[0] if time_like else cols[0]
            self.cbX.setCurrentText(x_guess)
            y_pref = [c for c in cols if c != x_guess]
            if y_pref:
                self.cbY.setCurrentText(y_pref[0])
        except Exception:
            import logging
            logging.getLogger(__name__).debug("smart X/Y default skipped", exc_info=True)

        if show_status:
            self.statusBar().showMessage(
                f"Columns loaded - {rows_count:,} rows, {cols_count} columns. "
                "Select columns in the worksheet or use the X/Y designations, then plot."
            )

        try:
            self._sb_rows.setText(f"rows: {rows_count:,}")
        except Exception:
            pass

        _refresh_states = getattr(self, "_refresh_action_states", None)
        if callable(_refresh_states):
            _refresh_states()
        refresh_processing = getattr(self, "_refresh_processing_context", None)
        if callable(refresh_processing):
            refresh_processing()

    def _convert_to_datetime_if_possible(self, col_name):
        if col_name not in self._df.columns:
            return False, None

        col_data = self._df[col_name]
        if pd.api.types.is_datetime64_any_dtype(col_data):
            return True, col_data

        try:
            datetime_data = self._coerce_datetime(col_data)
            valid_count = datetime_data.notna().sum()
            total_count = len(col_data)

            if valid_count > total_count * 0.5:
                return True, datetime_data
            return False, None
        except Exception:
            return False, None

    def _check_column_numeric(self, col_name):
        if col_name not in self._df.columns:
            return False, f"คอลัมน์ '{col_name}' ไม่มีในข้อมูล"

        col_data = self._df[col_name]
        if col_data.empty:
            return False, f"คอลัมน์ '{col_name}' ว่าง"
        if col_data.isna().all():
            return False, f"คอลัมน์ '{col_name}' มีแต่ค่า NaN"
        if pd.api.types.is_datetime64_any_dtype(col_data):
            return True, f"คอลัมน์ '{col_name}' เป็นข้อมูลเวลา (datetime) - ใช้ได้สำหรับแกน X"

        try:
            numeric_data = pd.to_numeric(col_data, errors="coerce")
            valid_count = numeric_data.notna().sum()
            total_count = len(col_data)

            if valid_count == 0:
                try:
                    datetime_data = self._coerce_datetime(col_data)
                    datetime_valid_count = datetime_data.notna().sum()
                    if datetime_valid_count > 0:
                        return True, f"คอลัมน์ '{col_name}' เป็นข้อมูลเวลา (datetime) - ใช้ได้สำหรับแกน X"
                except Exception:
                    pass

                return False, f"คอลัมน์ '{col_name}' ไม่สามารถแปลงเป็นตัวเลขหรือเวลาได้"
            if valid_count < total_count * 0.5:
                return (
                    False,
                    f"คอลัมน์ '{col_name}' มีข้อมูลตัวเลขเพียง {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)",
                )
            return (
                True,
                f"คอลัมน์ '{col_name}' มีข้อมูลตัวเลข {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)",
            )
        except Exception as e:
            return False, f"เกิดข้อผิดพลาดในการตรวจสอบคอลัมน์ '{col_name}': {e}"

    def build_plot_request(
        self,
        x_column: str | None = None,
        y_column: str | None = None,
    ) -> PlotRequest | None:
        """Build a widget-independent request from explicit or selected columns."""
        if x_column is None:
            x_column = self.selected_x_column()
        if y_column is None:
            y_column = self.selected_y_column()
        x, y = self._get_xy(x_column, y_column)
        if x is None:
            return None
        return PlotRequest(
            x=x,
            y=y,
            x_column=x_column,
            y_column=y_column,
            x_is_datetime=self._is_datetime_column(x_column),
        )

    def build_histogram_request(
        self,
        column: str | None = None,
        options: PlotOptions | None = None,
    ) -> HistogramRequest | None:
        """Build histogram input from an explicit or currently selected Y column."""
        df = self._resolve_active_dataframe()
        column = column or self.selected_y_column()
        if not isinstance(df, pd.DataFrame) or not column or column not in df.columns:
            return None
        values = pd.to_numeric(df[column], errors="coerce").dropna().to_numpy()
        if values.size == 0:
            return None
        return HistogramRequest(
            values=values,
            column=column,
            options=options or self.current_plot_options(),
        )

    def build_bar_request(
        self,
        x_column: str,
        y_column: str,
        *,
        title: str = "",
        options: PlotOptions | None = None,
    ) -> BarRequest | None:
        """Build a bar request; categorical X values are valid for this plot."""
        df = self._resolve_active_dataframe()
        if (
            not isinstance(df, pd.DataFrame)
            or x_column not in df.columns
            or y_column not in df.columns
        ):
            return None
        y_values = pd.to_numeric(df[y_column], errors="coerce")
        mask = df[x_column].notna() & y_values.notna()
        if not mask.any():
            return None
        return BarRequest(
            x=df.loc[mask, x_column].to_numpy(),
            y=y_values.loc[mask].to_numpy(),
            x_column=x_column,
            y_column=y_column,
            title=title,
            options=options or self.current_plot_options(),
        )

    def _get_xy(self, x_col: str | None = None, y_col: str | None = None):
        if self._df is None:
            QMessageBox.warning(
                self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์/เลือกตัวแปร แล้วกด 'โหลดคอลัมน์'"
            )
            return None, None

        if (x_col is None or y_col is None) and (self.x_column_count() == 0 or self.y_column_count() == 0):
            QMessageBox.information(self, "ยังไม่ได้โหลดคอลัมน์", "กดปุ่ม 'โหลดคอลัมน์จากข้อมูล' ก่อน")
            return None, None

        x_col = x_col if x_col is not None else self.selected_x_column()
        y_col = y_col if y_col is not None else self.selected_y_column()
        if x_col not in self._df.columns or y_col not in self._df.columns:
            QMessageBox.warning(self, "คอลัมน์ไม่ถูกต้อง", "โปรดเลือกคอลัมน์ X/Y ใหม่")
            return None, None

        x_valid, x_msg = self._check_column_numeric(x_col)
        y_valid, y_msg = self._check_column_numeric(y_col)

        if not x_valid and not y_valid:
            QMessageBox.warning(self, "ไม่มีข้อมูลที่ใช้ได้", f"ทั้งสองคอลัมน์มีปัญหา:\n• {x_msg}\n• {y_msg}")
            return None, None
        if not x_valid:
            QMessageBox.warning(self, "คอลัมน์ X มีปัญหา", x_msg)
            return None, None
        if not y_valid:
            QMessageBox.warning(self, "คอลัมน์ Y มีปัญหา", y_msg)
            return None, None

        try:
            x = self._df[x_col].values
            y = self._df[y_col].values

            try:
                y = pd.to_numeric(y, errors="coerce")
            except Exception:
                y = pd.to_numeric(y, errors="coerce")

            if len(x) > 0 and (
                np.issubdtype(type(x[0]), np.datetime64)
                or pd.api.types.is_datetime64_any_dtype(self._df[x_col])
            ):
                mask = ~pd.isna(y)
                x = x[mask]
                y = y[mask]
                try:
                    x_dt = self._coerce_datetime(x)
                    x = (x_dt - x_dt[0]).dt.total_seconds().values
                except Exception:
                    x = np.arange(len(x))
            else:
                try:
                    # Numeric X (float/int) must NOT be coerced to datetime — pandas
                    # reads large numbers as epochs and collapses the axis to ~0.
                    if pd.api.types.is_numeric_dtype(x):
                        raise ValueError("X is numeric; skip datetime coercion")
                    x_dt = self._coerce_datetime(x)
                    if x_dt.notna().sum() > 0:
                        x = (x_dt - x_dt[0]).total_seconds().values
                    else:
                        raise ValueError("Not a valid datetime string")
                except Exception:
                    x = pd.to_numeric(x, errors="coerce")

                mask = ~(pd.isna(x) | pd.isna(y))
                x = x[mask]
                y = y[mask]

            if len(x) == 0 or len(y) == 0:
                x_col_info = f"X column '{x_col}' (dtype: {self._df[x_col].dtype})"
                y_col_info = f"Y column '{y_col}' (dtype: {self._df[y_col].dtype})"

                x_empty = self._df[x_col].isna().all() if len(self._df[x_col]) > 0 else True
                y_empty = self._df[y_col].isna().all() if len(self._df[y_col]) > 0 else True

                if x_empty and y_empty:
                    error_msg = f"ทั้งสองคอลัมน์ไม่มีข้อมูล:\n• {x_col_info}\n• {y_col_info}"
                elif x_empty:
                    error_msg = f"คอลัมน์ X ไม่มีข้อมูล: {x_col_info}"
                elif y_empty:
                    error_msg = f"คอลัมน์ Y ไม่มีข้อมูล: {y_col_info}"
                else:
                    x_is_datetime = pd.api.types.is_datetime64_any_dtype(self._df[x_col])
                    y_is_datetime = pd.api.types.is_datetime64_any_dtype(self._df[y_col])

                    if x_is_datetime and not y_is_datetime:
                        error_msg = (
                            f"คอลัมน์ X เป็นข้อมูลเวลา (datetime) ซึ่งใช้ได้สำหรับแกน X:\n• {x_col_info}\n\n"
                            f"คอลัมน์ Y ไม่สามารถแปลงเป็นตัวเลขได้:\n• {y_col_info}\n\n"
                            "ลองใช้ 'กำหนดชนิดคอลัมน์' เพื่อแปลงคอลัมน์ Y เป็น Float"
                        )
                    elif not x_is_datetime and y_is_datetime:
                        error_msg = (
                            f"คอลัมน์ X ไม่สามารถแปลงเป็นตัวเลขได้:\n• {x_col_info}\n\n"
                            f"คอลัมน์ Y เป็นข้อมูลเวลา (datetime):\n• {y_col_info}\n\n"
                            "ลองใช้ 'กำหนดชนิดคอลัมน์' เพื่อแปลงคอลัมน์ X เป็น Float หรือใช้คอลัมน์ Y เป็นแกน X"
                        )
                    elif x_is_datetime and y_is_datetime:
                        error_msg = (
                            f"ทั้งสองคอลัมน์เป็นข้อมูลเวลา (datetime):\n• {x_col_info}\n• {y_col_info}\n\n"
                            "ลองใช้ 'กำหนดชนิดคอลัมน์' เพื่อแปลงคอลัมน์หนึ่งเป็น Float"
                        )
                    else:
                        error_msg = (
                            f"ไม่สามารถแปลงข้อมูลเป็นตัวเลขได้:\n• {x_col_info}\n• {y_col_info}\n\n"
                            "ลองใช้ 'กำหนดชนิดคอลัมน์' เพื่อแปลงข้อมูลก่อน"
                        )

                QMessageBox.warning(self, "ไม่มีข้อมูลที่ใช้ได้", error_msg)
                return None, None

            if len(x) != len(y):
                QMessageBox.warning(self, "ข้อมูลไม่ตรงกัน", f"จำนวนข้อมูล X ({len(x)}) และ Y ({len(y)}) ไม่เท่ากัน")
                return None, None

            return x, y
        except Exception as e:
            QMessageBox.critical(self, "เกิดข้อผิดพลาดในการประมวลผลข้อมูล", f"สาเหตุ: {e}")
            import traceback

            traceback.print_exc()
            return None, None

    def _is_datetime_column(self, col_name):
        if self._df is None or col_name not in self._df.columns:
            return False
        try:
            if pd.api.types.is_datetime64_any_dtype(self._df[col_name]):
                return True
            # Numeric columns are never datetime. pd.to_datetime() happily reads
            # a large number as an epoch offset (e.g. 5.5e7 -> 1970-01-01), which
            # would flag the column as datetime and put a DATE locator on a
            # numeric axis. On draw, num2date(5.5e7) overflows the year range
            # (year 152500) and raises, blanking/hanging the graph. This mirrors
            # the numeric guard in _get_xy.
            if pd.api.types.is_numeric_dtype(self._df[col_name]):
                return False
            sample = self._df[col_name].dropna().iloc[:5] if not self._df[col_name].empty else pd.Series()
            if not sample.empty:
                self._coerce_datetime(sample)
                return True
        except Exception:
            pass
        return False
