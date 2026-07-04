from __future__ import annotations

import os
import warnings

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QFileDialog, QMessageBox

from loaders import load_cdf_nc_on_demand, load_tabular


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
                raise ValueError("ไฟล์ตารางว่างหรืออ่านไม่สำเร็จ")
            return df, "ตาราง", enc_note
        if ext in [".nc", ".cdf"]:
            df = load_cdf_nc_on_demand(self, path)
            if df is None or df.empty:
                raise ValueError("ไฟล์ CDF/NetCDF ไม่มีข้อมูลที่ใช้พล็อตได้")
            return df, "CDF/NetCDF", None
        raise ValueError("นามสกุลไฟล์ไม่รองรับ")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "เลือกไฟล์ข้อมูล",
            "",
            "Data Files (*.csv *.tsv *.txt *.xlsx *.nc *.cdf);;All Files (*.*)",
        )
        if not path:
            return
        try:
            try:
                df, kind, _enc_note = self._load_dataframe_for_path(path)
            except Exception as e:
                ext = os.path.splitext(path)[1].lower()
                if ext in [".nc", ".cdf"]:
                    error_msg = f"ไม่สามารถอ่านไฟล์ CDF/NetCDF ได้:\n{str(e)}"
                    QMessageBox.critical(self, "ข้อผิดพลาด", error_msg)
                    return
                raise

            # Origin model: 1 ไฟล์ = 1 Book (สร้าง+activate ใน _stage_insert)
            name = f"{os.path.basename(path)} [{kind}]"
            self._stage_insert(name, df, path)
            self.statusBar().showMessage(
                f"เปิดเป็น Book แล้ว: {name} • เลือกคอลัมน์บนชีต แล้วคลิกไอคอนพล็อตด้านล่าง"
            )
        except Exception as e:
            QMessageBox.critical(self, "เปิดไฟล์ไม่สำเร็จ", f"สาเหตุ: {e}")

    def _open_book_for_dataset(self, name: str, df, path=None):
        """สร้าง Book window ใหม่ให้ dataset (Origin: 1 ชุดข้อมูล = 1 Book)

        คืน WorkbookWidget ที่สร้าง; ผูกสัญญาณ worksheet ครบชุดและ activate
        ทันที (ตัว handler bookActivated จะสลับ _df ให้เอง)
        """
        from widgets.workbook import WorkbookWidget

        wb = WorkbookWidget(self)
        wb.set_dataframe(df)
        wb.dataset_name = name
        try:
            wb.use_data_requested.connect(self.adopt_workbook_data)
            wb.plot_requested.connect(lambda s: self.plot_from_workbook(s, new_graph=True))
            wb.overlay_requested.connect(lambda s: self.plot_from_workbook(s, new_graph=False))
        except Exception:
            import logging
            logging.getLogger(__name__).debug("book signal wiring failed", exc_info=True)
        sub = self.mdi.add_book(wb, title=name)
        try:
            self.mdi.mdi.setActiveSubWindow(sub)
        except Exception:
            pass
        # activation signal may be suppressed while constructing — sync now
        self._on_book_activated(sub.windowTitle())
        return wb

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
                self.load_columns_from_df()
            except Exception:
                import logging
                logging.getLogger(__name__).debug("column reload on book switch failed", exc_info=True)
            try:
                self.lblFile.setText(f"ใช้งาน Book: {title}")
            except Exception:
                pass
            self.statusBar().showMessage(
                f"ใช้ข้อมูลจาก Book: {title} ({len(df):,} แถว × {len(df.columns)} คอลัมน์)")
        else:
            # Book เปล่า (เช่นพิมพ์เองยังไม่กด 'ใช้ข้อมูลนี้') — ชี้ workbook ไว้พอ
            self.statusBar().showMessage(
                f"Book: {title} ยังไม่มีข้อมูล — พิมพ์ข้อมูลแล้วกด 'ใช้ข้อมูลนี้' หรือกดพล็อตได้เลย")

    def load_data(self, path: str):
        """โหลดไฟล์ (เช่นจาก drag & drop) → Book ใหม่ตามโมเดล Origin"""
        try:
            try:
                df, kind, _enc_note = self._load_dataframe_for_path(path)
            except Exception as e:
                ext = os.path.splitext(path)[1].lower()
                if ext in [".nc", ".cdf"]:
                    QMessageBox.critical(
                        self, "ข้อผิดพลาด", f"ไม่สามารถอ่านไฟล์ CDF/NetCDF ได้:\n{e}")
                    self.statusBar().showMessage("เกิดข้อผิดพลาดในการเปิดไฟล์ CDF/NetCDF")
                    return
                raise
            name = f"{os.path.basename(path)} [{kind}]"
            self._stage_insert(name, df, path)
            self.statusBar().showMessage(
                f"เปิดเป็น Book แล้ว: {name} • เลือกคอลัมน์บนชีต แล้วคลิกไอคอนพล็อตด้านล่าง")
        except Exception as e:
            QMessageBox.critical(self, "เปิดไฟล์ไม่สำเร็จ", f"สาเหตุ: {e}")
            self.statusBar().showMessage("เกิดข้อผิดพลาดในการเปิดไฟล์")

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
            QMessageBox.critical(self, "อ่านตารางไม่สำเร็จ", f"สาเหตุ: {e}")
            return False
        if df is None or df.empty:
            QMessageBox.information(
                self, "ตารางยังว่าง",
                "พิมพ์ข้อมูลลงตาราง Book1 ก่อน (คอลัมน์ A = X, คอลัมน์ B = Y)")
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
            f"ใช้ข้อมูลจากตารางแล้ว ({len(df)} แถว × {len(df.columns)} คอลัมน์) → เลือก X/Y แล้วกดพล็อต")
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

    def load_columns_from_df(self):
        if self._df is None:
            try:
                if hasattr(self, "lstFiles") and hasattr(self, "_datasets"):
                    item = self.lstFiles.currentItem()
                    if item is not None:
                        data = self._datasets.get(item.text())
                        if data and isinstance(data.get("df"), pd.DataFrame):
                            self._df = data["df"].copy()
                            self._current_path = data.get("path")
            except Exception:
                pass
        if self._df is None:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน")
            return

        rows_count = len(self._df)
        cols_count = len(self._df.columns)

        cols = [str(c) for c in self._df.columns]
        self.cbX.clear()
        self.cbY.clear()
        self.cbX.addItems(cols)
        self.cbY.addItems(cols)

        try:
            self.cbHist.clear()
            self.cbHist.addItems(cols)
            try:
                if hasattr(self, "tbCbHist") and self.tbCbHist is not None:
                    self.tbCbHist.clear()
                    self.tbCbHist.addItems(cols)
            except Exception:
                pass
        except Exception:
            pass

        self.statusBar().showMessage(
            f"โหลดคอลัมน์เรียบร้อย • {rows_count:,} แถว, {cols_count} คอลัมน์ • เลือก X/Y แล้วพล็อตได้"
        )

        try:
            self._sb_rows.setText(f"rows: {rows_count:,}")
        except Exception:
            pass

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

    def _get_xy(self):
        print("Debug: _get_xy() called")
        if self._df is None:
            print("Debug: _get_xy() - no DataFrame (_df is None)")
            QMessageBox.warning(
                self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์/เลือกตัวแปร แล้วกด 'โหลดคอลัมน์'"
            )
            return None, None
        print(f"Debug: _get_xy() - DataFrame shape: {self._df.shape}")

        if self.cbX.count() == 0 or self.cbY.count() == 0:
            print(f"Debug: _get_xy() - cbX count: {self.cbX.count()}, cbY count: {self.cbY.count()}")
            QMessageBox.information(self, "ยังไม่ได้โหลดคอลัมน์", "กดปุ่ม 'โหลดคอลัมน์จากข้อมูล' ก่อน")
            return None, None

        x_col = self.cbX.currentText()
        y_col = self.cbY.currentText()
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

            print(
                f"Debug: X column '{x_col}' - dtype: {self._df[x_col].dtype}, sample: {x[:3] if len(x) > 0 else 'empty'}"
            )
            print(
                f"Debug: Y column '{y_col}' - dtype: {self._df[y_col].dtype}, sample: {y[:3] if len(y) > 0 else 'empty'}"
            )

            if len(x) > 0 and len(y) > 0:
                print(f"Debug: Data range - X: {x.min()} to {x.max()}, Y: {y.min():.6f} to {y.max():.6f}")

                try:
                    if pd.api.types.is_datetime64_any_dtype(x) or isinstance(x[0], str):
                        print("Debug: X is datetime/string, skipping range calculation")
                    else:
                        print(f"Debug: Data variation - X range: {x.max() - x.min()}, Y range: {y.max() - y.min():.6f}")
                except Exception as e:
                    print(f"Debug: Error calculating X range: {e}")

                if len(y) > 1:
                    y_diff = np.diff(y)
                    print(
                        f"Debug: Y variation - min diff: {y_diff.min():.6f}, max diff: {y_diff.max():.6f}, std: {y_diff.std():.6f}"
                    )

            try:
                y_original_count = len(y)
                y = pd.to_numeric(y, errors="coerce")
                y_nan_count = pd.isna(y).sum()
                print(
                    f"Debug: Y conversion - original: {y_original_count}, NaN after conversion: {y_nan_count}, valid: {y_original_count - y_nan_count}"
                )
            except Exception as e:
                print(f"Y column conversion error: {e}")
                y = pd.to_numeric(y, errors="coerce")

            if len(x) > 0 and (
                np.issubdtype(type(x[0]), np.datetime64)
                or pd.api.types.is_datetime64_any_dtype(self._df[x_col])
            ):
                print("Debug: X is datetime, filtering by Y NaN only")
                mask = ~pd.isna(y)
                x = x[mask]
                y = y[mask]
                print(f"Debug: After datetime filtering - X: {len(x)}, Y: {len(y)}")

                try:
                    x_dt = self._coerce_datetime(x)
                    x_rel = (x_dt - x_dt[0]).dt.total_seconds()
                    x = x_rel.values
                    print(f"Debug: Converted datetime X to relative seconds - range: {x.min():.3f} to {x.max():.3f}")
                except Exception as e:
                    print(f"Debug: Failed to convert datetime to relative seconds: {e}")
                    try:
                        x = np.arange(len(x))
                        print(f"Debug: Fallback to array index as X - range: {x.min()} to {x.max()}")
                    except Exception as e2:
                        print(f"Debug: All datetime conversion methods failed: {e2}")
            else:
                try:
                    # Numeric X (float/int) must NOT be coerced to datetime — pandas
                    # reads large numbers as epochs and collapses the axis to ~0.
                    if pd.api.types.is_numeric_dtype(x):
                        raise ValueError("X is numeric; skip datetime coercion")
                    x_dt = self._coerce_datetime(x)
                    if x_dt.notna().sum() > 0:
                        print("Debug: X is datetime string, converting to relative seconds")
                        x_rel = (x_dt - x_dt[0]).total_seconds()
                        x = x_rel.values
                        print(
                            f"Debug: Converted datetime string X to relative seconds - range: {x.min():.3f} to {x.max():.3f}"
                        )
                    else:
                        raise ValueError("Not a valid datetime string")
                except Exception as e:
                    print(f"Debug: X is not datetime string, trying numeric conversion: {e}")
                    try:
                        x_original_count = len(x)
                        x = pd.to_numeric(x, errors="coerce")
                        x_nan_count = pd.isna(x).sum()
                        print(
                            f"Debug: X conversion - original: {x_original_count}, NaN after conversion: {x_nan_count}, valid: {x_original_count - x_nan_count}"
                        )
                    except Exception as e2:
                        print(f"X column conversion error: {e2}")
                        x = pd.to_numeric(x, errors="coerce")

                    mask = ~(pd.isna(x) | pd.isna(y))
                    x = x[mask]
                    y = y[mask]
                    print(f"Debug: After NaN filtering - X: {len(x)}, Y: {len(y)}")

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

            if len(y) > 0:
                y_mean = np.mean(y)
                y_std = np.std(y)
                y_median = np.median(y)

                print(f"Debug: Y statistics - mean: {y_mean:.6f}, std: {y_std:.6f}, median: {y_median:.6f}")

                q1, q3 = np.percentile(y, [25, 75])
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr

                outliers = np.where((y < lower_bound) | (y > upper_bound))[0]
                if len(outliers) > 0:
                    print(
                        f"Debug: Found {len(outliers)} outliers in Y data (indices: {outliers[:10]}{'...' if len(outliers) > 10 else ''})"
                    )
                    print(f"Debug: Outlier percentage: {len(outliers)/len(y)*100:.2f}%")
                    outlier_values = y[outliers[:5]]
                    print(f"Debug: Sample outlier values: {outlier_values}")
                else:
                    print("Debug: No outliers detected in Y data")

            print(f"Debug: Final data ready for plotting - X: {len(x)}, Y: {len(y)}")
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
            sample = self._df[col_name].dropna().iloc[:5] if not self._df[col_name].empty else pd.Series()
            if not sample.empty:
                self._coerce_datetime(sample)
                return True
        except Exception:
            pass
        return False
