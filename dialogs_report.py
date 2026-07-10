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
        self.setWindowTitle("Export Report Settings")
        self.setMinimumSize(500, 520)
        self.setModal(True)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title section
        title_group = QGroupBox("Report Title")
        title_layout = QVBoxLayout(title_group)
        
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("SciPlotter Data Analysis Report")
        self.title_edit.setText("SciPlotter Data Analysis Report")
        title_layout.addWidget(self.title_edit)
        
        main_layout.addWidget(title_group)
        
        # Content options section
        content_group = QGroupBox("Report Content")
        content_layout = QVBoxLayout(content_group)
        
        self.include_meta = QCheckBox("File metadata (file name, columns used)")
        self.include_meta.setChecked(True)
        content_layout.addWidget(self.include_meta)
        
        self.include_stats = QCheckBox("Statistics table (mean, standard deviation, min/max)")
        self.include_stats.setChecked(True)
        content_layout.addWidget(self.include_stats)
        
        self.include_fig = QCheckBox("Current graph image")
        self.include_fig.setChecked(True)
        content_layout.addWidget(self.include_fig)
        
        main_layout.addWidget(content_group)
        
        # Column selection section
        column_group = QGroupBox("Columns for Statistics")
        column_layout = QVBoxLayout(column_group)
        
        # Instructions
        instruction_label = QLabel("Select columns to include in the statistics section. If none are selected, all columns are used.")
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
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all_columns)
        select_buttons_layout.addWidget(self.select_all_btn)
        
        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self.select_none_columns)
        select_buttons_layout.addWidget(self.select_none_btn)
        
        select_buttons_layout.addStretch()
        column_layout.addLayout(select_buttons_layout)
        
        main_layout.addWidget(column_group)
        
        # Buttons section
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setMinimumWidth(80)
        buttons_layout.addWidget(self.cancel_btn)
        
        self.ok_btn = QPushButton("OK")
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
    
    def _dedupe_columns(self, columns):
        """Remove duplicate columns while preserving order"""
        seen = set()
        deduped = []
        for col in columns:
            if col not in seen:
                seen.add(col)
                deduped.append(col)
        return deduped
    
    def get_selected_columns(self):
        """Get list of selected column names"""
        selected_columns = []
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_columns.append(item.text())
        return selected_columns
    
    def get_options(self):
        """Get all selected options as a dictionary with deduplication and default title"""
        # Get title and set default if empty
        title = self.title_edit.text().strip()
        if not title:
            title = "SciPlotter Data Analysis Report"
        
        # Get columns and dedupe them
        columns = self.get_selected_columns()
        if columns:
            columns = self._dedupe_columns(columns)
        
        return {
            "title": title,
            "include_meta": self.include_meta.isChecked(),
            "include_stats": self.include_stats.isChecked(),
            "include_fig": self.include_fig.isChecked(),
            "columns": columns
        }
