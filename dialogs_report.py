from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QCheckBox, QListWidget, QListWidgetItem, QPushButton, 
    QGroupBox, QScrollArea, QWidget, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class ExportReportDialog(QDialog):
    def __init__(self, df, parent=None):
        super().__init__(parent)
        self.df = df
        self.setup_ui()
        self.populate_columns()
        
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("ตั้งค่า Export Report")
        self.setMinimumSize(500, 600)
        self.setModal(True)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title section
        title_group = QGroupBox("หัวข้อรายงาน")
        title_layout = QVBoxLayout(title_group)
        
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("รายงานการวิเคราะห์ข้อมูล SciPlotter")
        self.title_edit.setText("รายงานการวิเคราะห์ข้อมูล SciPlotter")
        title_layout.addWidget(self.title_edit)
        
        main_layout.addWidget(title_group)
        
        # Content options section
        content_group = QGroupBox("เนื้อหาที่จะรวมในรายงาน")
        content_layout = QVBoxLayout(content_group)
        
        self.include_meta = QCheckBox("ข้อมูลไฟล์ (ชื่อไฟล์, คอลัมน์ที่ใช้)")
        self.include_meta.setChecked(True)
        content_layout.addWidget(self.include_meta)
        
        self.include_stats = QCheckBox("ตารางสถิติ (ค่าเฉลี่ย, ส่วนเบี่ยงเบน, ค่าต่ำสุด/สูงสุด)")
        self.include_stats.setChecked(True)
        content_layout.addWidget(self.include_stats)
        
        self.include_fig = QCheckBox("รูปกราฟที่สร้าง")
        self.include_fig.setChecked(True)
        content_layout.addWidget(self.include_fig)
        
        main_layout.addWidget(content_group)
        
        # Column selection section
        column_group = QGroupBox("เลือกคอลัมน์ที่จะคำนวณสถิติ")
        column_layout = QVBoxLayout(column_group)
        
        # Instructions
        instruction_label = QLabel("เลือกคอลัมน์ที่ต้องการคำนวณสถิติ (ถ้าไม่เลือกจะใช้คอลัมน์ทั้งหมด)")
        instruction_label.setWordWrap(True)
        instruction_label.setStyleSheet("color: #666; font-size: 11px;")
        column_layout.addWidget(instruction_label)
        
        # Column list with scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(200)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        self.column_list = QListWidget()
        self.column_list.setSelectionMode(QListWidget.MultiSelection)
        scroll_area.setWidget(self.column_list)
        
        column_layout.addWidget(scroll_area)
        
        # Select all/none buttons
        select_buttons_layout = QHBoxLayout()
        
        self.select_all_btn = QPushButton("เลือกทั้งหมด")
        self.select_all_btn.clicked.connect(self.select_all_columns)
        select_buttons_layout.addWidget(self.select_all_btn)
        
        self.select_none_btn = QPushButton("ไม่เลือกเลย")
        self.select_none_btn.clicked.connect(self.select_none_columns)
        select_buttons_layout.addWidget(self.select_none_btn)
        
        select_buttons_layout.addStretch()
        column_layout.addLayout(select_buttons_layout)
        
        main_layout.addWidget(column_group)
        
        # Buttons section
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.cancel_btn = QPushButton("ยกเลิก")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setMinimumWidth(80)
        buttons_layout.addWidget(self.cancel_btn)
        
        self.ok_btn = QPushButton("ตกลง")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setMinimumWidth(80)
        self.ok_btn.setDefault(True)
        buttons_layout.addWidget(self.ok_btn)
        
        main_layout.addLayout(buttons_layout)
        
        # Set focus to title edit
        self.title_edit.setFocus()
        
    def populate_columns(self):
        """Populate the column list with DataFrame columns"""
        if self.df is not None:
            for col in self.df.columns:
                item = QListWidgetItem(str(col))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)  # Default to checked
                self.column_list.addItem(item)
    
    def select_all_columns(self):
        """Select all columns"""
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            item.setCheckState(Qt.Checked)
    
    def select_none_columns(self):
        """Select no columns"""
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            item.setCheckState(Qt.Unchecked)
    
    def get_selected_columns(self):
        """Get list of selected column names"""
        selected_columns = []
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_columns.append(item.text())
        return selected_columns
    
    def get_options(self):
        """Get all selected options as a dictionary"""
        return {
            "title": self.title_edit.text().strip(),
            "include_meta": self.include_meta.isChecked(),
            "include_stats": self.include_stats.isChecked(),
            "include_fig": self.include_fig.isChecked(),
            "columns": self.get_selected_columns()
        }
