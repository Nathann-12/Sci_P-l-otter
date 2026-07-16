from __future__ import annotations

import logging
import os
from typing import Optional

import pandas as pd
from PySide6 import QtGui
from PySide6.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox

from core import session as session_store
from loaders import load_cdf_nc_on_demand, load_tabular


logger = logging.getLogger(__name__)


class MainWindowSessionMixin:
    """Reusable session and staging actions extracted from MainWindow."""

    def _load_staged_dataframe(self, path: str):
        # ใช้ตัวโหลดรวมของ data mixin (รองรับทุกฟอร์แมต รวม JSON/HDF5/MAT/XML)
        loader = getattr(self, "_load_dataframe_for_path", None)
        if callable(loader):
            df, kind, _note = loader(path)
            return df, kind
        # legacy fallback (สำหรับสตับ/เทสต์เก่าที่ mix เฉพาะ session mixin)
        ext = os.path.splitext(path)[1].lower()
        if ext in [".csv", ".txt", ".tsv", ".xlsx"]:
            df, _ = load_tabular(path, ext)
            if df is None or df.empty:
                raise ValueError("ไฟล์ตารางว่างหรืออ่านไม่สำเร็จ")
            return df, "ตาราง"
        if ext in [".nc", ".cdf"]:
            df = load_cdf_nc_on_demand(self, path)
            if df is None or df.empty:
                raise ValueError("ไฟล์ CDF/NetCDF ไม่มีข้อมูลที่ใช้พล็อตได้")
            return df, "CDF/NC"
        raise ValueError(f"unsupported extension: {ext}")

    def _load_dataset_from_path(self, path: str, name: Optional[str] = None):
        try:
            df, _kind = self._load_staged_dataframe(path)
        except Exception as exc:
            logger.warning("Failed to load dataset %s: %s", path, exc)
            return None

        dataset_name = name or f"{os.path.basename(path)}"
        try:
            self._stage_insert(dataset_name, df, path)
        except Exception:
            logger.warning("Failed to stage dataset during restore: %s", dataset_name, exc_info=True)
            return None
        return dataset_name

    def _stage_insert(self, name: str, df: pd.DataFrame, path: str):
        """ลงทะเบียน dataset แล้วเปิดเป็น Book window (Origin: 1 ชุดข้อมูล = 1 Book)

        ยังเติม lstFiles ด้วยถ้ามี (สะพานให้เทสต์/สตับเก่า — UI จริงไม่มีลิสต์แล้ว)
        """
        base = name
        i = 2
        while name in self._datasets:
            name = f"{base} ({i})"
            i += 1
        self._datasets[name] = {"df": df, "path": path}
        opener = getattr(self, "_open_book_for_dataset", None)
        if callable(opener):
            try:
                opener(name, df, path)
            except Exception as exc:
                self._datasets.pop(name, None)
                reporter = getattr(self, "report_ui_exception", None)
                if callable(reporter):
                    reporter("Open Book", exc)
                else:
                    logger.exception("open book for dataset failed: %s", name)
                return
        discard_starter = getattr(self, "_discard_unused_initial_book", None)
        if callable(discard_starter):
            discard_starter()
        show_workspace = getattr(self, "_show_workspace", None)
        if callable(show_workspace):
            show_workspace()
        lst = getattr(self, "lstFiles", None)
        if lst is not None:
            try:
                lst.addItem(QListWidgetItem(name))
            except Exception:
                logger.debug("legacy staging list append skipped", exc_info=True)
        self.statusBar().showMessage(f"Data ready: {name}")

    def stage_add_files(self):
        """Batch import: เลือกหลายไฟล์ → เปิดเป็น Book ไฟล์ละบาน (โมเดล Origin)"""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "เลือกไฟล์ข้อมูล (เลือกได้หลายไฟล์)",
            "",
            "Data Files (*.csv *.tsv *.txt *.xlsx *.nc *.cdf *.json *.h5 *.hdf5 *.hdf *.mat *.xml)"
            ";;All Files (*.*)",
        )
        if not paths:
            return

        for path in paths:
            try:
                df, kind = self._load_staged_dataframe(path)
                name = f"{os.path.basename(path)} [{kind}]"
                self._stage_insert(name, df, path)
            except ValueError as exc:
                ext = os.path.splitext(path)[1].lower()
                if ext not in [".csv", ".txt", ".tsv", ".xlsx", ".nc", ".cdf",
                               ".json", ".h5", ".hdf5", ".hdf", ".mat", ".xml"]:
                    QMessageBox.information(self, "ข้ามไฟล์", f"นามสกุลไม่รองรับ: {path}")
                    continue
                if ext in [".nc", ".cdf"]:
                    QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถอ่านไฟล์ CDF/NetCDF ได้:\n{str(exc)}")
                    continue
                QMessageBox.warning(self, "เพิ่มไฟล์ไม่สำเร็จ", f"{os.path.basename(path)}\nสาเหตุ: {exc}")
            except Exception as exc:
                QMessageBox.warning(self, "เพิ่มไฟล์ไม่สำเร็จ", f"{os.path.basename(path)}\nสาเหตุ: {exc}")

    def stage_use_selected(self):
        item = self.lstFiles.currentItem()
        if not item:
            QMessageBox.information(self, "ยังไม่ได้เลือก", "โปรดเลือกไฟล์จากรายการก่อน")
            return
        name = item.text()
        data = self._datasets.get(name)
        if not data:
            QMessageBox.warning(self, "ไม่พบข้อมูล", "รายการนี้ไม่มีข้อมูลแล้ว")
            return
        self._df = data["df"].copy()
        self._current_path = data["path"]
        self.lblFile.setText(f"ใช้งานไฟล์: {name}")
        self.statusBar().showMessage(
            "Dataset switched. Reload columns, then select worksheet columns or use their X/Y designations."
        )

    def stage_remove_selected(self):
        row = self.lstFiles.currentRow()
        if row < 0:
            QMessageBox.information(self, "ยังไม่ได้เลือก", "โปรดเลือกไฟล์จากรายการก่อน")
            return
        item = self.lstFiles.item(row)
        name = item.text()
        if self._current_path and name in self._datasets and self._datasets[name]["path"] == self._current_path:
            ans = QMessageBox.question(
                self,
                "กำลังใช้งานไฟล์นี้อยู่",
                "ไฟล์นี้กำลังถูกใช้งานอยู่ ต้องการลบออกจากรายการหรือไม่?",
            )
            if ans != QMessageBox.Yes:
                return
        self._datasets.pop(name, None)
        self.lstFiles.takeItem(row)
        self.statusBar().showMessage(f"Removed from list: {name}")

    # ---------------- Project files (*.sciproj) ----------------
    PROJECT_FILTER = "SciPlotter Project (*.sciproj);;All Files (*.*)"

    def save_project_as(self):
        """Save the whole app state (data + graphs + styles) to a .sciproj file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "project.sciproj", self.PROJECT_FILTER)
        if not path:
            return
        if not path.lower().endswith(".sciproj"):
            path += ".sciproj"
        try:
            session_store.save_project(self, path)
            self._current_project_path = path
            self.statusBar().showMessage(f"Project saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Project failed", f"Reason: {e}")

    def open_project(self):
        """Open a .sciproj file via a file dialog."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", self.PROJECT_FILTER)
        if path:
            self.open_project_path(path)

    def open_project_path(self, path: str) -> bool:
        """Open a .sciproj at ``path`` directly (used by the file dialog, the
        command line and the file association). Returns True on success."""
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "Open Project failed", f"File not found:\n{path}")
            return False
        try:
            session_store.load_project(self, path)
            self._current_project_path = path
            self.statusBar().showMessage(f"Project opened: {os.path.basename(path)}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Open Project failed", f"Reason: {e}")
            return False

    def register_file_association(self):
        """Associate .sciproj files with this app (Windows, current user)."""
        from core import file_assoc
        ok, msg = file_assoc.register()
        if ok:
            QMessageBox.information(self, "File Association", msg)
        else:
            QMessageBox.warning(self, "File Association", msg)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            session_store.save_session(self)  # silent crash-recovery snapshot
        except Exception:
            logger.warning("Failed to save session on close", exc_info=True)
        super().closeEvent(event)
