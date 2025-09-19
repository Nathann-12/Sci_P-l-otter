from __future__ import annotations
from typing import Dict, List, Tuple, Callable
import re
import numpy as np
import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QListWidget, QLineEdit,
    QPushButton, QPlainTextEdit, QLabel, QGridLayout, QTableWidget, QTableWidgetItem,
    QMessageBox
)

ALLOWED_FUNCS = {
    "abs": np.abs, "sqrt": np.sqrt, "exp": np.exp, "log": np.log,
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "min": np.minimum, "max": np.maximum, "clip": np.clip, "round": np.round,
}
ALLOWED_CONSTS = {"pi": np.pi, "e": np.e}
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _safe_map_names(df: pd.DataFrame) -> Tuple[str, Dict[str, str], Dict[str, np.ndarray]]:
    """
    คืน (expr_prefix, mappingสำหรับแทน backtick, env สำหรับ eval)
    - ผู้ใช้สามารถเขียนชื่อคอลัมน์ที่มีช่องว่างได้ด้วย backticks: `Total Count`
    """
    env: Dict[str, np.ndarray] = {}
    name_map: Dict[str, str] = {}
    for i, c in enumerate(df.columns):
        safe = f"C{i}"
        name_map[str(c)] = safe
        try:
            env[safe] = df[c].to_numpy()
        except Exception:
            env[safe] = np.asarray(df[c])
    return "", name_map, env


def _rewrite_backticks(expr: str, name_map: Dict[str, str]) -> str:
    def repl(m):
        col = m.group(1)
        if col not in name_map:
            raise ValueError(f"ไม่พบคอลัมน์ชื่อ `{col}`")
        return name_map[col]
    return re.sub(r"`([^`]+)`", repl, expr)


def _validate_names(expr: str, env_keys: List[str]) -> None:
    # ชื่อที่เหลือ (ไม่ใช่ตัวเลข/โอเปอเรเตอร์) ต้องอยู่ใน env หรือเป็นฟังก์ชัน/คงที่ที่อนุญาต
    allowed = set(env_keys) | set(ALLOWED_FUNCS.keys()) | set(ALLOWED_CONSTS.keys())
    for tok in NAME_RE.findall(expr):
        if tok not in allowed:
            # อนุญาตให้ผ่าน เพื่อรองรับเลขแบบ 1e-6 ซึ่ง regex จะเจอ 'e' แยก
            continue


def evaluate_formula(df: pd.DataFrame, expr: str) -> np.ndarray:
    """
    ประเมินสูตรแบบปลอดภัยบน DataFrame
    - รองรับ backticks รอบชื่อคอลัมน์
    """
    _, name_map, env = _safe_map_names(df)
    expr2 = _rewrite_backticks(expr, name_map)
    env.update(ALLOWED_FUNCS)
    env.update(ALLOWED_CONSTS)
    _validate_names(expr2, list(env.keys()))
    try:
        result = eval(expr2, {"__builtins__": {}}, env)
    except Exception as e:
        raise ValueError(f"สูตรไม่ถูกต้อง: {e}")
    arr = np.asarray(result)
    if arr.ndim == 0:
        arr = np.full(len(df), float(arr))
    if arr.shape[0] != len(df):
        raise ValueError("ขนาดผลลัพธ์ไม่เท่ากับจำนวนแถวของข้อมูล")
    return arr


class CalculatedColumnsEditor(QWidget):
    """
    วิดเจ็ตจัดการ 'คอลัมน์คำนวณ'
    - get_df(): callable คืน DataFrame ปัจจุบัน
    - on_changed(list_of_tuples): callback เมื่อเพิ่ม/ลบ/อัปเดตสูตร [(name, expr), ...]
    """
    def __init__(self, get_df: Callable[[], pd.DataFrame], on_changed: Callable[[List[Tuple[str, str]]], None], parent=None):
        super().__init__(parent)
        self.get_df = get_df
        self.on_changed = on_changed
        self.formulas: List[Tuple[str, str]] = []

        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(8)

        # กล่องซ้าย: รายชื่อคอลัมน์ + ค้นหา
        gb_cols = QGroupBox("Columns"); left = QVBoxLayout(gb_cols)
        self.txt_search = QLineEdit(); self.txt_search.setPlaceholderText("ค้นหาคอลัมน์…")
        self.list_cols = QListWidget()
        left.addWidget(self.txt_search); left.addWidget(self.list_cols)

        # กลาง: สูตร + ชื่อคอลัมน์ใหม่ + ปุ่ม
        gb_expr = QGroupBox("Create / Edit formula"); mid = QGridLayout(gb_expr)
        self.ed_name = QLineEdit(); self.ed_name.setPlaceholderText("ชื่อคอลัมน์ใหม่ (เช่น B_mag)")
        self.ed_expr = QPlainTextEdit()
        fnt = QFont("Consolas"); fnt.setStyleHint(QFont.Monospace); self.ed_expr.setFont(fnt)
        self.ed_expr.setPlaceholderText("พิมพ์สูตรที่นี่ เช่น:\n  sqrt(`Bx`**2 + `By`**2 + `Bz`**2)\nรองรับ: + - * / ** () abs sqrt exp log sin cos tan min max clip round, pi, e")
        self.lbl_status = QLabel("")
        self.btn_validate = QPushButton("Validate")
        self.btn_preview  = QPushButton("Preview (head 20)")
        self.btn_add      = QPushButton("Add / Update")
        self.btn_remove   = QPushButton("Remove")

        mid.addWidget(QLabel("New column name:"), 0,0); mid.addWidget(self.ed_name, 0,1)
        mid.addWidget(QLabel("Formula:"), 1,0); mid.addWidget(self.ed_expr, 1,1)
        mid.addWidget(self.lbl_status, 2,1)
        rowbtn = QHBoxLayout(); rowbtn.addWidget(self.btn_validate); rowbtn.addWidget(self.btn_preview); rowbtn.addStretch(1); rowbtn.addWidget(self.btn_add); rowbtn.addWidget(self.btn_remove)
        mid.addLayout(rowbtn, 3, 1)

        # ขวา: Preview ตาราง
        gb_prev = QGroupBox("Preview"); right = QVBoxLayout(gb_prev)
        self.tbl = QTableWidget(0, 0); right.addWidget(self.tbl)

        # วาง 3 กล่องในแนวนอน
        line = QHBoxLayout()
        line.addWidget(gb_cols, 1)
        line.addWidget(gb_expr, 2)
        line.addWidget(gb_prev, 2)

        root.addLayout(line)

        # สัญญาณ
        self.txt_search.textChanged.connect(self._filter_cols)
        self.list_cols.itemDoubleClicked.connect(self._insert_col)
        self.btn_validate.clicked.connect(self._on_validate)
        self.btn_preview.clicked.connect(self._on_preview)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_remove.clicked.connect(self._on_remove)

        self.refresh_columns()

    # ---------- actions ----------
    def refresh_columns(self):
        df = self.get_df()
        if df is None:
            df = pd.DataFrame()
        self.list_cols.clear()
        try:
            cols = list(df.columns)
        except Exception:
            cols = []
        for c in cols:
            self.list_cols.addItem(str(c))

    def _filter_cols(self, q: str):
        q = q.strip().lower()
        for i in range(self.list_cols.count()):
            it = self.list_cols.item(i)
            it.setHidden(q not in it.text().lower())

    def _insert_col(self):
        it = self.list_cols.currentItem()
        if not it: return
        name = it.text()
        self.ed_expr.insertPlainText(f"`{name}`")

    def _on_validate(self):
        name = self.ed_name.text().strip()
        expr = self.ed_expr.toPlainText().strip()
        if not name:
            self.lbl_status.setText("⚠ ใส่ชื่อคอลัมน์ก่อน"); return
        if not expr:
            self.lbl_status.setText("⚠ ใส่สูตรก่อน"); return
        try:
            arr = evaluate_formula(self.get_df(), expr)
        except Exception as e:
            self.lbl_status.setText(f"❌ {e}")
            return
        self.lbl_status.setText(f"✅ OK  dtype={arr.dtype}  len={len(arr)}")

    def _on_preview(self):
        try:
            arr = evaluate_formula(self.get_df(), self.ed_expr.toPlainText().strip())
        except Exception as e:
            QMessageBox.warning(self, "Preview failed", str(e)); return
        head = min(20, len(arr))
        self.tbl.setRowCount(head); self.tbl.setColumnCount(1)
        self.tbl.setHorizontalHeaderLabels([self.ed_name.text().strip() or "preview"])
        for i in range(head):
            self.tbl.setItem(i, 0, QTableWidgetItem(str(arr[i])))

    def _on_add(self):
        name = self.ed_name.text().strip()
        expr = self.ed_expr.toPlainText().strip()
        if not name or not expr:
            QMessageBox.information(self, "Missing", "กรอกชื่อคอลัมน์และสูตรก่อน"); return
        try:
            evaluate_formula(self.get_df(), expr)
        except Exception as e:
            QMessageBox.warning(self, "Invalid formula", str(e)); return
        # เพิ่ม/อัปเดต
        names = [n for n,_ in self.formulas]
        if name in names:
            self.formulas = [(n, expr if n==name else e) for (n,e) in self.formulas]
        else:
            self.formulas.append((name, expr))
        self.on_changed(self.formulas)
        self.lbl_status.setText("✅ Added/Updated")

    def _on_remove(self):
        name = self.ed_name.text().strip()
        if not name: return
        self.formulas = [(n,e) for (n,e) in self.formulas if n!=name]
        self.on_changed(self.formulas)
        self.lbl_status.setText("🗑 Removed")
