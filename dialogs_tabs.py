# dialogs_tabs.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, 
    QListWidgetItem, QPushButton, QCheckBox, QGroupBox
)


class SelectTabsDialog(QDialog):
    """
    Dialog for selecting which tabs to plot to when multiple tabs are available.
    """
    def __init__(self, parent, open_tabs):
        super().__init__(parent)
        self.setWindowTitle("เลือกแท็บที่ต้องการพล็อต")
        self.resize(400, 300)
        self.open_tabs = open_tabs
        self.selected_tabs = []
        
        self._setup_ui()
        self._populate_tabs()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Instructions
        instruction_label = QLabel("เลือกแท็บที่ต้องการพล็อตข้อมูลลง:")
        instruction_label.setWordWrap(True)
        layout.addWidget(instruction_label)
        
        # Tab selection group
        group = QGroupBox("แท็บที่เปิดอยู่")
        group_layout = QVBoxLayout(group)
        
        self.tab_list = QListWidget()
        self.tab_list.setSelectionMode(QListWidget.MultiSelection)
        group_layout.addWidget(self.tab_list)
        
        # Select all/none buttons
        button_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("เลือกทั้งหมด")
        self.btn_select_none = QPushButton("ไม่เลือกเลย")
        button_layout.addWidget(self.btn_select_all)
        button_layout.addWidget(self.btn_select_none)
        button_layout.addStretch()
        group_layout.addLayout(button_layout)
        
        layout.addWidget(group)
        
        # Dialog buttons
        dialog_buttons = QHBoxLayout()
        self.btn_ok = QPushButton("ตกลง")
        self.btn_cancel = QPushButton("ยกเลิก")
        dialog_buttons.addStretch()
        dialog_buttons.addWidget(self.btn_ok)
        dialog_buttons.addWidget(self.btn_cancel)
        layout.addLayout(dialog_buttons)
        
        # Connect signals
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_select_none.clicked.connect(self._select_none)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        
    def _populate_tabs(self):
        """Populate the list with available tabs"""
        self.tab_list.clear()
        for tab_id, tab_name in self.open_tabs:
            item = QListWidgetItem(tab_name)
            item.setData(Qt.UserRole, tab_id)
            self.tab_list.addItem(item)
            
        # Select first tab by default if available
        if self.tab_list.count() > 0:
            self.tab_list.item(0).setSelected(True)
            
    def _select_all(self):
        """Select all tabs"""
        for i in range(self.tab_list.count()):
            self.tab_list.item(i).setSelected(True)
            
    def _select_none(self):
        """Deselect all tabs"""
        for i in range(self.tab_list.count()):
            self.tab_list.item(i).setSelected(False)
            
    def get_selection(self):
        """Get the selected tab IDs"""
        selected_items = self.tab_list.selectedItems()
        return [item.data(Qt.UserRole) for item in selected_items]
        
    @staticmethod
    def get_selection(parent, open_tabs):
        """
        Static method to show dialog and get selection.
        
        Args:
            parent: Parent widget
            open_tabs: List of tuples (tab_id, tab_name)
            
        Returns:
            List of selected tab IDs, or empty list if cancelled
        """
        if len(open_tabs) <= 1:
            # If only one tab or no tabs, return the first tab ID
            if open_tabs:
                return [open_tabs[0][0]]
            else:
                return []
            
        dialog = SelectTabsDialog(parent, open_tabs)
        if dialog.exec() == QDialog.Accepted:
            return dialog.get_selection()
        return []
