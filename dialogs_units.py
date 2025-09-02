"""
Units and Calibration Dialog
Main interface for managing unit conversions and calibrations
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget, QFormLayout,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QComboBox, QPushButton, QLabel,
    QScrollArea, QMessageBox, QGroupBox, QHeaderView, QFrame
)
from PySide6.QtCore import Qt, QLocale, QTimer
from PySide6.QtGui import QFont, QColor

import pandas as pd
import numpy as np

from core.units import UNIT_REGISTRY, guess_unit_from_colname, apply_calibration_and_units, pretty_equation, convert_series
from dialogs_calibrate import CalibrateDialog

# ---- mini widget: พรีวิวกราฟของคอลัมน์ที่เลือก ----
class UnitsPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Import matplotlib here to avoid import issues
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            import numpy as np
            
            self.fig = Figure(figsize=(4.6, 2.8), dpi=100, constrained_layout=True)
            self.canvas = FigureCanvas(self.fig)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self.canvas)
            
            self._cfg = None
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._render_now)
            
        except ImportError:
            # Fallback if matplotlib not available
            self.canvas = QLabel("Matplotlib not available")
            lay = QVBoxLayout(self)
            lay.addWidget(self.canvas)
            self._cfg = None
            self._timer = None

    def render(self, cfg: dict, delay_ms=120):
        if self._timer:
            self._cfg = cfg
            self._timer.start(delay_ms)

    def _render_now(self):
        try:
            cfg = self._cfg or {}
            self.fig.clear()
            ax = self.fig.add_subplot(111)
            
            y_raw = cfg.get("y_raw")
            y_new = cfg.get("y_new")
            
            if y_raw is None:
                ax.text(0.5, 0.5, "เลือกแถวในตารางเพื่อพรีวิว", 
                       ha="center", va="center", transform=ax.transAxes)
            else:
                n = min(len(y_raw), 300)
                x = range(n)
                ax.plot(x, y_raw[:n], label="เดิม (raw)", linewidth=1.5, alpha=0.7)
                
                if y_new is not None:
                    ax.plot(x, y_new[:n], label=f"ใหม่ ({cfg.get('to_unit')})", 
                           linewidth=1.8, alpha=0.9)
                
                ax.grid(True, alpha=0.25)
                ax.legend(frameon=False, fontsize=9)
                ax.set_xlabel("Sample Index")
                ax.set_ylabel("Value")
            
            self.canvas.draw_idle()
            
        except Exception as e:
            print(f"Error rendering preview: {e}")


class UnitsDialog(QDialog):
    """Main dialog for units and calibration management"""
    
    def __init__(self, dataframe, parent=None):
        super().__init__(parent)
        
        # Force English locale for Arabic numerals
        self.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        
        self.dataframe = dataframe
        self.result = {}  # Will store the final configuration
        self.calib = {}  # Store calibration data per column
        
        self.setWindowTitle("การตั้งค่าหน่วยและการสอบเทียบ")
        self.setModal(True)
        self.resize(1600, 800)  # เพิ่มความกว้างจาก 1400 เป็น 1600 เพื่อรองรับคอลัมน์ที่ขยายขึ้น
        
        self.setup_ui()
        self.populate_table()
        self.setup_connections()
        
        # Select first row by default
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
            self.update_row_preview(0)
    
    def setup_ui(self):
        """Setup the user interface with splitter layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # ---------- Splitter: ซ้ายตาราง / ขวา inspector ----------
        splitter = QSplitter(Qt.Horizontal, self)
        
        # ซ้าย: มีแถบเครื่องมือ + ตาราง
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(10, 10, 10, 10)
        llay.setSpacing(10)
        
        # แถบเครื่องมือด้านบน
        bar = QHBoxLayout()
        self.btn_autodetect = QPushButton("🔍 Auto-Detect")
        self.btn_clear = QPushButton("🗑️ Clear All")
        self.btn_autodetect.setStyleSheet("""
            QPushButton {
                background: #4CAF50; color: white; font-weight: 600;
                padding: 10px 20px; border-radius: 8px; border: none;
                font-size: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
                min-width: 120px;
            }
            QPushButton:hover { 
                background: #45a049; 
            }
        """)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background: #f44336; color: white; font-weight: 600;
                padding: 10px 20px; border-radius: 8px; border: none;
                font-size: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
                min-width: 120px;
            }
            QPushButton:hover { 
                background: #da190b; 
            }
        """)
        bar.addWidget(self.btn_autodetect)
        bar.addWidget(self.btn_clear)
        bar.addStretch(1)
        llay.addLayout(bar)
        
        # ตาราง
        numeric_cols = [c for c in self.dataframe.columns 
                       if self.dataframe[c].dtype in ['float64', 'int64', 'datetime64[ns]']]
        
        self.table = QTableWidget(len(numeric_cols), 7, self)
        self.table.setHorizontalHeaderLabels([
            "Column", "Dimension", "From Unit", "To Unit", 
            "Calibrate...", "Preview (first 3)", "Formula"
        ])
        
        # Set table properties
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)             # Column - Fixed width
        header.setSectionResizeMode(1, QHeaderView.Fixed)             # Dimension - Fixed width
        header.setSectionResizeMode(2, QHeaderView.Fixed)             # From Unit - Fixed width
        header.setSectionResizeMode(3, QHeaderView.Fixed)             # To Unit - Fixed width
        header.setSectionResizeMode(4, QHeaderView.Fixed)             # Calibrate - Fixed width
        header.setSectionResizeMode(5, QHeaderView.Stretch)           # Preview - Stretch
        header.setSectionResizeMode(6, QHeaderView.Stretch)           # Formula - Stretch
        
        # Set fixed column widths for better readability
        header.resizeSection(0, 200)  # Column name - 200px
        header.resizeSection(1, 180)  # Dimension - 180px (เพิ่มจาก 120px)
        header.resizeSection(2, 160)  # From Unit - 160px (เพิ่มจาก 100px)
        header.resizeSection(3, 160)  # To Unit - 160px (เพิ่มจาก 100px)
        header.resizeSection(4, 120)  # Calibrate - 120px
        
        # Style the table
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(32)  # เพิ่มความสูงแถวจาก 28 เป็น 32
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #d0d0d0;
                background-color: white;
                alternate-background-color: rgba(125,125,125,0.08);
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 8px 6px;
                border: none;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QHeaderView::section {
                background-color: #e9ecef;
                padding: 8px 10px;
                border: 0px;
                border-bottom: 2px solid rgba(180,180,180,0.4);
                font-weight: 700;
                color: #2c3e50;
                font-size: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QHeaderView::section:hover {
                background-color: #dee2e6;
            }
        """)
        
        llay.addWidget(self.table, 1)
        
        # ใส่ splitter ฝั่งซ้าย
        leftScroll = QScrollArea()
        leftScroll.setWidgetResizable(True)
        leftScroll.setFrameShape(QScrollArea.NoFrame)
        leftScroll.setWidget(left)
        splitter.addWidget(leftScroll)
        
        # ขวา: Inspector + พรีวิว
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(12, 12, 12, 12)
        rlay.setSpacing(12)
        
        # Title and equation
        self.lbl_title = QLabel("รายละเอียดคอลัมน์")
        self.lbl_title.setStyleSheet("""
            font-weight: 700; 
            font-size: 16px; 
            color: #2c3e50;
            font-family: 'Segoe UI', Arial, sans-serif;
            padding: 8px 0px;
            border-bottom: 2px solid #e9ecef;
        """)
        
        self.lbl_eq = QLabel("สูตร: —")
        self.lbl_eq.setWordWrap(True)
        self.lbl_eq.setStyleSheet("""
            font-family: 'Consolas', 'Monaco', monospace; 
            font-size: 13px; 
            padding: 12px; 
            background-color: #f8f9fa; 
            border-radius: 6px; 
            border: 1px solid #dee2e6;
            color: #495057;
            line-height: 1.4;
        """)
        
        # Preview widget
        self.preview = UnitsPreview()
        
        rlay.addWidget(self.lbl_title)
        rlay.addWidget(self.lbl_eq)
        rlay.addWidget(self.preview, 1)
        
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1000, 600])  # เพิ่มความกว้างฝั่งซ้ายจาก 800 เป็น 1000 เพื่อรองรับคอลัมน์ที่ขยายขึ้น
        
        # ปุ่มล่าง
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addStretch()
        
        self.apply_btn = QPushButton("✅ Apply")
        self.close_btn = QPushButton("❌ Close")
        
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background: #2f80ed; color: white; font-weight: 600;
                padding: 12px 24px; border-radius: 8px; border: none;
                min-width: 100px;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton:hover { 
                background: #0056b3; 
            }
            QPushButton:pressed { background: #004085; }
        """)
        
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: #6c757d; color: white; font-weight: 600;
                padding: 12px 24px; border-radius: 8px; border: none;
                min-width: 100px;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton:hover { 
                background: #545b62; 
            }
            QPushButton:pressed { background: #3d4449; }
        """)
        
        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(self.close_btn)
        
        # Root layout
        layout.addWidget(splitter, 1)
        layout.addLayout(button_layout)
        
        # ---- FORCE DARK TEXT (dialog-scoped) ----
        from PySide6.QtGui import QPalette, QColor

        self.setObjectName("UnitsCalibDialog")  # ใช้เป็นตัวเลือก QSS เฉพาะไดอะล็อกนี้

        # 1) Palette: ให้ตาราง/ข้อความใช้สีเข้ม
        pal = self.palette()
        for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText, QPalette.HighlightedText):
            pal.setColor(role, QColor("#111827"))         # เทาเข้มอ่านง่าย
        pal.setColor(QPalette.PlaceholderText, QColor("#9CA3AF"))
        self.setPalette(pal)

        pal_tbl = self.table.palette()
        pal_tbl.setColor(QPalette.Text, QColor("#111827"))
        pal_tbl.setColor(QPalette.Base, QColor("#FFFFFF"))
        pal_tbl.setColor(QPalette.AlternateBase, QColor("#F6F7F9"))
        pal_tbl.setColor(QPalette.Highlight, QColor("#E5F0FF"))
        pal_tbl.setColor(QPalette.HighlightedText, QColor("#111827"))
        self.table.setPalette(pal_tbl)

        # 2) High-specificity QSS: ชนะธีมมืดเดิม
        self.setStyleSheet("""
        #UnitsCalibDialog * { color: #111827; }
        #UnitsCalibDialog QTableWidget { background: #FFFFFF; }
        #UnitsCalibDialog QTableWidget::item:selected { color:#111827; background:#E5F0FF; }
        #UnitsCalibDialog QHeaderView::section { color:#111827; background: #EEF2F7; }
        #UnitsCalibDialog QComboBox,
        #UnitsCalibDialog QLineEdit,
        #UnitsCalibDialog QSpinBox,
        #UnitsCalibDialog QDoubleSpinBox {
          color:#111827; background:#FFFFFF;
          selection-background-color:#2563EB; selection-color:#FFFFFF;
        }
        #UnitsCalibDialog QComboBox QAbstractItemView {
          color:#111827; background:#FFFFFF;
          selection-background-color:#E5F0FF; selection-color:#111827;
        }
        #UnitsCalibDialog QPushButton { color:#111827; }
        #UnitsCalibDialog QPushButton[text*="Apply"] { color:#FFFFFF; }   /* ปุ่ม Apply ยังเป็นอักษรขาว */
        """)

        # 3) เผื่อ QSS บางธีมดื้อ: บังคับสีให้ QComboBox ทีละตัว (รวมรายการ dropdown)
        # เรียกใช้กับทุกคอมโบในตาราง (Dimension/From/To) - จะเรียกใน populate_table
        # for r in range(self.table.rowCount()):
        #     w2 = self.table.cellWidget(r, 1)  # Dimension
        #     w3 = self.table.cellWidget(r, 2)  # From Unit
        #     w4 = self.table.cellWidget(r, 3)  # To Unit
        #     if w2: self._force_combo_dark(w2)
        #     if w3: self._force_combo_dark(w3)
        #     if w4: self._force_combo_dark(w4)

        # ถ้ายังมีแถว "ปิดใช้งาน" (disabled) ให้เทาอ่านง่ายขึ้น ใส่เพิ่มท้าย QSS:
        self.setStyleSheet(self.styleSheet() + """
        #UnitsCalibDialog QTableWidget::item:disabled { color:#6B7280; }
        """)
    
    def _force_combo_dark(self, combo):
        """Force dark text for QComboBox (override any dark theme)"""
        combo.setStyleSheet("color:#111827; background:#FFFFFF;")
        try:
            combo.view().setStyleSheet("color:#111827; background:#FFFFFF; "
                                       "selection-background-color:#E5F0FF; selection-color:#111827;")
        except Exception:
            pass
    
    def populate_table(self):
        """Populate the table with dataframe columns"""
        if self.dataframe is None or self.dataframe.empty:
            return
        
        # Get numeric columns only
        numeric_cols = [c for c in self.dataframe.columns 
                       if self.dataframe[c].dtype in ['float64', 'int64', 'datetime64[ns]']]
        
        self.table.setRowCount(len(numeric_cols))
        
        # Get available dimensions
        dimensions = UNIT_REGISTRY.get_dimensions()
        
        for row, col in enumerate(numeric_cols):
            # Column name
            col_item = QTableWidgetItem(col)
            col_item.setFlags(col_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, col_item)
            
            # Dimension combo
            dim_combo = QComboBox()
            dim_combo.addItem("Select dimension...")
            dim_combo.addItems(dimensions)
            dim_combo.setMinimumWidth(140)  # ตั้งค่าขนาดขั้นต่ำของ ComboBox
            dim_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)  # ปรับขนาดตามเนื้อหา
            dim_combo.setMaxVisibleItems(15)  # แสดงรายการได้มากขึ้น
            dim_combo.setStyleSheet("""
                QComboBox {
                    padding: 6px 8px;
                    border: 1px solid #ced4da;
                    border-radius: 4px;
                    background-color: white;
                    font-size: 11px;
                    font-family: 'Segoe UI', Arial, sans-serif;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 5px solid #6c757d;
                    margin-right: 5px;
                }
                QComboBox QAbstractItemView {
                    border: 1px solid #ced4da;
                    background-color: white;
                    selection-background-color: #007bff;
                    selection-color: white;
                }
            """)
            
            # From unit combo
            from_combo = QComboBox()
            from_combo.addItem("Auto-guess...")
            from_combo.setMinimumWidth(140)  # ตั้งค่าขนาดขั้นต่ำของ ComboBox
            from_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)  # ปรับขนาดตามเนื้อหา
            from_combo.setMaxVisibleItems(15)  # แสดงรายการได้มากขึ้น
            from_combo.setStyleSheet("""
                QComboBox {
                    padding: 6px 8px;
                    border: 1px solid #ced4da;
                    border-radius: 4px;
                    background-color: white;
                    font-size: 11px;
                    font-family: 'Segoe UI', Arial, sans-serif;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 5px solid #6c757d;
                    margin-right: 5px;
                }
                QComboBox QAbstractItemView {
                    border: 1px solid #ced4da;
                    background-color: white;
                    selection-background-color: #007bff;
                    selection-color: white;
                }
            """)
            
            # To unit combo
            to_combo = QComboBox()
            to_combo.addItem("Select unit...")
            to_combo.setMinimumWidth(140)  # ตั้งค่าขนาดขั้นต่ำของ ComboBox
            to_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)  # ปรับขนาดตามเนื้อหา
            to_combo.setMaxVisibleItems(15)  # แสดงรายการได้มากขึ้น
            to_combo.setStyleSheet("""
                QComboBox {
                    padding: 6px 8px;
                    border: 1px solid #ced4da;
                    border-radius: 4px;
                    background-color: white;
                    font-size: 11px;
                    font-family: 'Segoe UI', Arial, sans-serif;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QComboBox::down-arrow {
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 5px solid #6c757d;
                    margin-right: 5px;
                }
                QComboBox QAbstractItemView {
                    border: 1px solid #ced4da;
                    background-color: white;
                    selection-background-color: #007bff;
                    selection-color: white;
                }
            """)
            
            # Calibrate button
            calib_btn = QPushButton("🔧 Calibrate...")
            calib_btn.setStyleSheet("""
                QPushButton {
                    background: #FFB020; color: #1c1c1c; font-weight: 600;
                    padding: 8px 12px; border-radius: 6px; border: none;
                    min-width: 90px;
                    font-size: 11px;
                    font-family: 'Segoe UI', Arial, sans-serif;
                }
                QPushButton:hover { 
                    background: #e0a800; 
                }
                QPushButton:pressed { background: #d39e00; }
            """)
            
            # Set cell widgets
            self.table.setCellWidget(row, 1, dim_combo)
            self.table.setCellWidget(row, 2, from_combo)
            self.table.setCellWidget(row, 3, to_combo)
            self.table.setCellWidget(row, 4, calib_btn)
            
            # Force dark text for combos (override any dark theme)
            self._force_combo_dark(dim_combo)
            self._force_combo_dark(from_combo)
            self._force_combo_dark(to_combo)
            
            # Preview and Formula items
            preview_item = QTableWidgetItem("Select units to see preview...")
            preview_item.setFlags(preview_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 5, preview_item)
            
            formula_item = QTableWidgetItem("")
            formula_item.setFlags(formula_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 6, formula_item)
            
            # Check if column is datetime
            is_datetime = self.dataframe[col].dtype == 'datetime64[ns]'
            
            # Set default dimension based on column type
            if is_datetime:
                dim_combo.setCurrentText("time")
                calib_btn.setEnabled(False)  # Disable calibration for datetime
            else:
                # Try to auto-guess unit from column name
                guessed_unit = guess_unit_from_colname(col)
                if guessed_unit:
                    # Find the dimension
                    for dim in dimensions:
                        units = UNIT_REGISTRY.get_units_for_dimension(dim)
                        if any(u.name == guessed_unit.name for u in units):
                            dim_combo.setCurrentText(dim)
                            self.on_dimension_changed(row, dim)
                            
                            # Set the from unit
                            for i, unit in enumerate(units):
                                if unit.name == guessed_unit.name:
                                    from_combo.setCurrentIndex(i + 1)  # +1 for "Auto-guess..."
                                    break
                            break
            
            # Initialize calibration data
            self.calib[col] = {
                'dimension': dim_combo.currentText(),
                'from_unit': from_combo.currentText() if from_combo.currentText() != "Auto-guess..." else "",
                'to_unit': to_combo.currentText() if to_combo.currentText() != "Select unit..." else "",
                'a': 1.0,
                'b': 0.0
            }
        
        # Connect signals
        for row in range(self.table.rowCount()):
            dim_combo = self.table.cellWidget(row, 1)
            from_combo = self.table.cellWidget(row, 2)
            to_combo = self.table.cellWidget(row, 3)
            calib_btn = self.table.cellWidget(row, 4)
            
            dim_combo.currentTextChanged.connect(lambda text, r=row: self.on_dimension_changed(r, text))
            from_combo.currentTextChanged.connect(lambda text, r=row: self.on_from_unit_changed(r, text))
            to_combo.currentTextChanged.connect(lambda text, r=row: self.on_to_unit_changed(r, text))
            calib_btn.clicked.connect(lambda checked, r=row: self.open_calibration_dialog(r))
    
    def setup_connections(self):
        """Setup signal connections"""
        self.apply_btn.clicked.connect(self.apply_settings)
        self.close_btn.clicked.connect(self.reject)
        self.btn_autodetect.clicked.connect(self.auto_detect_all)
        self.btn_clear.clicked.connect(self.clear_units)
        self.table.selectionModel().selectionChanged.connect(self.update_inspector)
    
    def on_dimension_changed(self, row: int, dimension: str):
        """Handle dimension selection change"""
        if dimension == "Select dimension...":
            return
        
        # Update from unit combo
        from_combo = self.table.cellWidget(row, 2)
        from_combo.clear()
        from_combo.addItem("Auto-guess...")
        
        units = UNIT_REGISTRY.get_units_for_dimension(dimension)
        from_combo.addItems([u.name for u in units])
        
        # Update to unit combo
        to_combo = self.table.cellWidget(row, 3)
        to_combo.clear()
        to_combo.addItem("Select unit...")
        to_combo.addItems([u.name for u in units])
        
        # Reset preview and formula
        self.table.item(row, 5).setText("Select units to see preview...")
        self.table.item(row, 6).setText("")
        
        # Update calibration data
        col_name = self.table.item(row, 0).text()
        if col_name in self.calib:
            self.calib[col_name]['dimension'] = dimension
    
    def on_from_unit_changed(self, row: int, unit_name: str):
        """Handle from unit selection change"""
        col_name = self.table.item(row, 0).text()
        if col_name in self.calib:
            self.calib[col_name]['from_unit'] = unit_name
        self.update_row_preview(row)
    
    def on_to_unit_changed(self, row: int, unit_name: str):
        """Handle to unit selection change"""
        col_name = self.table.item(row, 0).text()
        if col_name in self.calib:
            self.calib[col_name]['to_unit'] = unit_name
        self.update_row_preview(row)
    
    def open_calibration_dialog(self, row: int):
        """Open calibration dialog for the specified row"""
        # Check if units are selected
        from_unit_name = self.table.cellWidget(row, 2).currentText()
        to_unit_name = self.table.cellWidget(row, 3).currentText()
        
        if from_unit_name == "Auto-guess..." or to_unit_name == "Select unit...":
            QMessageBox.warning(self, "Warning", "Please select both From and To units first.")
            return
        
        # Get the units
        dimension = self.table.cellWidget(row, 1).currentText()
        from_unit = UNIT_REGISTRY.find_unit(from_unit_name)
        to_unit = UNIT_REGISTRY.find_unit(to_unit_name)
        
        if not from_unit or not to_unit:
            QMessageBox.warning(self, "Warning", "Invalid units selected.")
            return
        
        # Open calibration dialog
        calib_dialog = CalibrateDialog(self)
        if calib_dialog.exec():
            a, b = calib_dialog.get_calibration()
            
            # Store calibration data
            col_name = self.table.item(row, 0).text()
            if col_name in self.calib:
                self.calib[col_name]['a'] = a
                self.calib[col_name]['b'] = b
            
            # Update preview and formula
            self.update_row_preview(row)
    
    def update_row_preview(self, row: int):
        """Update preview and formula for the specified row"""
        try:
            # Get selected values
            dimension = self.table.cellWidget(row, 1).currentText()
            from_unit_name = self.table.cellWidget(row, 2).currentText()
            to_unit_name = self.table.cellWidget(row, 3).currentText()
            
            if (dimension == "Select dimension..." or 
                from_unit_name == "Auto-guess..." or 
                to_unit_name == "Select unit..."):
                return
            
            # Get the units
            from_unit = UNIT_REGISTRY.find_unit(from_unit_name)
            to_unit = UNIT_REGISTRY.find_unit(to_unit_name)
            
            if not from_unit or not to_unit:
                return
            
            # Check dimension compatibility
            if from_unit.dimension != to_unit.dimension:
                self.table.item(row, 5).setText("ERR: Incompatible dimensions")
                self.table.item(row, 6).setText("")
                return
            
            # Get column data
            col_name = self.table.item(row, 0).text()
            if col_name not in self.dataframe.columns:
                self.table.item(row, 5).setText("ERR: Column not found")
                self.table.item(row, 6).setText("")
                return
            
            # Get sample values
            series = self.dataframe[col_name]
            
            # Handle datetime columns
            if series.dtype == 'datetime64[ns]':
                # Convert to seconds for preview
                vals = (pd.to_datetime(series) - pd.to_datetime(series.iloc[0])).dt.total_seconds()
                y_raw = vals.astype(float)
            else:
                y_raw = series.astype(float)
            
            # Get calibration data
            calib_data = self.calib.get(col_name, {})
            a = calib_data.get('a', 1.0)
            b = calib_data.get('b', 0.0)
            
            try:
                if a != 1.0 or b != 0.0:
                    # Apply calibration and conversion
                    converted_values = apply_calibration_and_units(
                        y_raw.head(3), a, b, from_unit, to_unit
                    )
                    
                    # Format preview
                    preview_text = " → ".join([
                        f"{v:.3f}" for v in converted_values.values
                    ])
                    self.table.item(row, 5).setText(preview_text)
                    
                    # Update formula
                    formula = pretty_equation(a, b, from_unit_name, to_unit_name)
                    self.table.item(row, 6).setText(formula)
                    
                    # Send to Inspector for graph preview
                    self._last_preview_payload = {
                        'y_raw': y_raw.values,
                        'y_new': apply_calibration_and_units(y_raw.head(300), a, b, from_unit, to_unit).values,
                        'to_unit': to_unit_name
                    }
                else:
                    # Just convert units (no calibration)
                    converted_values = convert_series(y_raw.head(3), from_unit, to_unit)
                    
                    # Format preview
                    preview_text = " → ".join([
                        f"{v:.3f}" for v in converted_values.values
                    ])
                    self.table.item(row, 5).setText(preview_text)
                    
                    # Update formula
                    formula = f"Convert: [{from_unit_name}] → [{to_unit_name}]"
                    self.table.item(row, 6).setText(formula)
                    
                    # Send to Inspector for graph preview
                    self._last_preview_payload = {
                        'y_raw': y_raw.values,
                        'y_new': convert_series(y_raw.head(300), from_unit, to_unit).values,
                        'to_unit': to_unit_name
                    }
                
                # Update inspector if this row is selected
                if self.table.currentRow() == row:
                    self.update_inspector()
                    
            except Exception as e:
                self.table.item(row, 5).setText(f"ERR: {str(e)}")
                self.table.item(row, 6).setText("")
                
        except Exception as e:
            self.table.item(row, 5).setText(f"ERR: {str(e)}")
            self.table.item(row, 6).setText("")
    
    def update_inspector(self, *args):
        """Update the inspector panel with selected row info"""
        row = self.table.currentRow()
        if row < 0:
            return
        
        col = self.table.item(row, 0).text()
        self.lbl_title.setText(f"คอลัมน์: {col}")
        
        # Get formula from table
        formula = self.table.item(row, 6).text()
        if formula:
            self.lbl_eq.setText(f"สูตร: {formula}")
        else:
            self.lbl_eq.setText("สูตร: —")
        
        # Update graph preview
        payload = getattr(self, "_last_preview_payload", {})
        self.preview.render(payload)
    
    def auto_detect_all(self):
        """Auto-detect units for all columns"""
        for row in range(self.table.rowCount()):
            col_name = self.table.item(row, 0).text()
            guessed_unit = guess_unit_from_colname(col_name)
            
            if guessed_unit:
                # Find the dimension
                for dim in UNIT_REGISTRY.get_dimensions():
                    units = UNIT_REGISTRY.get_units_for_dimension(dim)
                    if any(u.name == guessed_unit.name for u in units):
                        # Set dimension
                        dim_combo = self.table.cellWidget(row, 1)
                        dim_combo.setCurrentText(dim)
                        self.on_dimension_changed(row, dim)
                        
                        # Set from unit
                        from_combo = self.table.cellWidget(row, 2)
                        for i, unit in enumerate(units):
                            if unit.name == guessed_unit.name:
                                from_combo.setCurrentIndex(i + 1)
                                break
                        
                        # Set to unit (same as from initially)
                        to_combo = self.table.cellWidget(row, 3)
                        to_combo.setCurrentText(guessed_unit.name)
                        
                        # Update preview
                        self.update_row_preview(row)
                        break
        
        QMessageBox.information(self, "Auto-Detect", "Auto-detection completed!")
    
    def clear_units(self):
        """Clear all unit selections and reset to defaults"""
        for row in range(self.table.rowCount()):
            col_name = self.table.item(row, 0).text()
            
            # Reset calibration
            self.calib[col_name]['a'] = 1.0
            self.calib[col_name]['b'] = 0.0
            
            # Reset to unit to match from unit
            from_combo = self.table.cellWidget(row, 2)
            to_combo = self.table.cellWidget(row, 3)
            
            if from_combo.currentText() != "Auto-guess...":
                to_combo.setCurrentText(from_combo.currentText())
            
            # Update preview
            self.update_row_preview(row)
        
        QMessageBox.information(self, "Clear", "All units cleared and reset to defaults!")
    
    def apply_settings(self):
        """Apply the current settings and close dialog"""
        try:
            # Collect all configurations
            for row in range(self.table.rowCount()):
                col_name = self.table.item(row, 0).text()
                dimension = self.table.cellWidget(row, 1).currentText()
                from_unit_name = self.table.cellWidget(row, 2).currentText()
                to_unit_name = self.table.cellWidget(row, 3).currentText()
                
                # Skip incomplete rows
                if (dimension == "Select dimension..." or 
                    from_unit_name == "Auto-guess..." or 
                    to_unit_name == "Select unit..."):
                    continue
                
                # Get calibration data
                calib_data = self.calib.get(col_name, {})
                a = calib_data.get('a', 1.0)
                b = calib_data.get('b', 0.0)
                
                # Store configuration
                self.result[col_name] = {
                    'dimension': dimension,
                    'from_unit': from_unit_name,
                    'to_unit': to_unit_name,
                    'a': a,
                    'b': b
                }
            
            if not self.result:
                QMessageBox.warning(self, "Warning", "No valid configurations found.")
                return
            
            # Close dialog
            self.accept()
            
            # เชื่อมต่อกับ parent window ที่เป็น MainWindow เพื่อรีเฟรชกราฟ
            main = self.parent()  # หรือ self.window()
            if main is not None and hasattr(main, "refresh_plot"):
                main.refresh_plot()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {str(e)}")

if __name__ == "__main__":
    import sys
    import pandas as pd
    from PySide6.QtWidgets import QApplication
    
    # Create sample data
    data = {
        'Bx [mT]': [1.0, 2.0, 3.0],
        'Temperature (°C)': [20.0, 25.0, 30.0],
        'Pressure (psi)': [14.7, 29.4, 44.1]
    }
    df = pd.DataFrame(data)
    
    app = QApplication(sys.argv)
    dialog = UnitsDialog(df)
    if dialog.exec():
        print("Applied configurations:", dialog.result)
    sys.exit(app.exec())
