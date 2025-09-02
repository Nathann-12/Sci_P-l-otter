# UI/widgets/error_panel.py
from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QDateTime, QTimer
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QTextEdit, QComboBox, QLineEdit, QPushButton,
    QLabel, QSplitter, QHeaderView, QMessageBox, QFileDialog
)
from PySide6.QtGui import QFont, QColor, QPalette

from core.logging_setup import qt_log_emitter

class ErrorPanel(QDockWidget):
    """
    Error Panel ที่แสดง log และ error messages
    รองรับการ copy/save/clear log และกรองตามระดับ
    """
    
    def __init__(self, parent=None):
        super().__init__("Error Panel", parent)
        self.setObjectName("ErrorPanel")
        
        # ตั้งค่าพื้นฐาน
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        
        # ตั้งค่าเป็น floating window โดย default
        self.setFloating(True)
        self.resize(800, 400)
        
        # สร้าง UI
        self._setup_ui()
        self._connect_signals()
        
        # เก็บ log records
        self._log_records = []
        self._filtered_records = []
        
        # ตั้งค่า timer สำหรับ auto-refresh
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_display)
        self._refresh_timer.start(100)  # อัปเดตทุก 100ms
        
    def _setup_ui(self):
        """สร้าง UI components"""
        # Main widget
        main_widget = QWidget()
        self.setWidget(main_widget)
        
        # Main layout
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # Controls panel
        controls_layout = QHBoxLayout()
        
        # Level filter
        controls_layout.addWidget(QLabel("Level:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.level_combo.setCurrentText("ALL")
        controls_layout.addWidget(self.level_combo)
        
        # Search box
        controls_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search in messages...")
        controls_layout.addWidget(self.search_edit)
        
        # Buttons
        self.clear_btn = QPushButton("Clear")
        self.copy_btn = QPushButton("Copy")
        self.save_btn = QPushButton("Save")
        controls_layout.addWidget(self.clear_btn)
        controls_layout.addWidget(self.copy_btn)
        controls_layout.addWidget(self.save_btn)
        
        controls_layout.addStretch()
        main_layout.addLayout(controls_layout)
        
        # Splitter for table and detail
        splitter = QSplitter(Qt.Horizontal)
        
        # Log table
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(4)
        self.log_table.setHorizontalHeaderLabels(["Time", "Level", "Source", "Message"])
        
        # ตั้งค่าตาราง
        header = self.log_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Time
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Level
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Source
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # Message
        
        # ตั้งค่าฟอนต์
        font = QFont("Consolas", 9)
        self.log_table.setFont(font)
        
        # ตั้งค่าการเลือก
        self.log_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.log_table.setAlternatingRowColors(True)
        
        splitter.addWidget(self.log_table)
        
        # Detail panel
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        
        detail_layout.addWidget(QLabel("Details:"))
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setFont(font)
        self.detail_text.setMaximumHeight(200)
        detail_layout.addWidget(self.detail_text)
        
        splitter.addWidget(detail_widget)
        splitter.setSizes([400, 200])
        
        main_layout.addWidget(splitter)
        
    def _connect_signals(self):
        """เชื่อมต่อสัญญาณ"""
        # Qt log emitter
        qt_log_emitter.log_record.connect(self._add_log_record)
        
        # Controls
        self.level_combo.currentTextChanged.connect(self._apply_filters)
        self.search_edit.textChanged.connect(self._apply_filters)
        self.clear_btn.clicked.connect(self._clear_logs)
        self.copy_btn.clicked.connect(self._copy_logs)
        self.save_btn.clicked.connect(self._save_logs)
        
        # Table selection
        self.log_table.itemSelectionChanged.connect(self._on_selection_changed)
        
    def _add_log_record(self, record: logging.LogRecord):
        """เพิ่ม log record ใหม่"""
        self._log_records.append(record)
        
        # จำกัดจำนวน records (เก็บแค่ 1000 รายการล่าสุด)
        if len(self._log_records) > 1000:
            self._log_records = self._log_records[-1000:]
            
        self._apply_filters()
        
    def _apply_filters(self):
        """กรอง log records ตาม level และ search text"""
        level_filter = self.level_combo.currentText()
        search_text = self.search_edit.text().lower()
        
        self._filtered_records = []
        
        for record in self._log_records:
            # Level filter
            if level_filter != "ALL" and record.levelname != level_filter:
                continue
                
            # Search filter
            if search_text and search_text not in record.getMessage().lower():
                continue
                
            self._filtered_records.append(record)
            
        self._refresh_display()
        
    def _refresh_display(self):
        """อัปเดตการแสดงผลในตาราง"""
        if not self._filtered_records:
            self.log_table.setRowCount(0)
            return
            
        # อัปเดตจำนวนแถว
        self.log_table.setRowCount(len(self._filtered_records))
        
        # เติมข้อมูล
        for row, record in enumerate(self._filtered_records):
            # Time
            time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            time_item = QTableWidgetItem(time_str)
            time_item.setData(Qt.UserRole, record)
            self.log_table.setItem(row, 0, time_item)
            
            # Level
            level_item = QTableWidgetItem(record.levelname)
            level_item.setData(Qt.UserRole, record)
            
            # ตั้งสีตาม level
            if record.levelname == "ERROR":
                level_item.setBackground(QColor(255, 200, 200))
            elif record.levelname == "WARNING":
                level_item.setBackground(QColor(255, 255, 200))
            elif record.levelname == "CRITICAL":
                level_item.setBackground(QColor(255, 150, 150))
            elif record.levelname == "INFO":
                level_item.setBackground(QColor(200, 255, 200))
            elif record.levelname == "DEBUG":
                level_item.setBackground(QColor(200, 200, 255))
                
            self.log_table.setItem(row, 1, level_item)
            
            # Source
            source_item = QTableWidgetItem(record.name)
            source_item.setData(Qt.UserRole, record)
            self.log_table.setItem(row, 2, source_item)
            
            # Message
            message_item = QTableWidgetItem(record.getMessage())
            message_item.setData(Qt.UserRole, record)
            self.log_table.setItem(row, 3, message_item)
            
        # เลื่อนไปแถวล่าสุด
        if self._filtered_records:
            self.log_table.scrollToBottom()
            
    def _on_selection_changed(self):
        """เมื่อเลือกแถวในตาราง"""
        current_row = self.log_table.currentRow()
        if current_row >= 0 and current_row < len(self._filtered_records):
            record = self._filtered_records[current_row]
            self._show_record_details(record)
        else:
            self.detail_text.clear()
            
    def _show_record_details(self, record: logging.LogRecord):
        """แสดงรายละเอียดของ log record"""
        details = []
        details.append(f"Time: {datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')}")
        details.append(f"Level: {record.levelname}")
        details.append(f"Source: {record.name}")
        details.append(f"Message: {record.getMessage()}")
        details.append(f"Module: {record.module}")
        details.append(f"Function: {record.funcName}")
        details.append(f"Line: {record.lineno}")
        
        if record.exc_info:
            details.append("\nException Info:")
            import traceback
            details.append(traceback.format_exception(*record.exc_info))
            
        self.detail_text.setPlainText("\n".join(details))
        
    def _clear_logs(self):
        """ล้าง logs ทั้งหมด"""
        self._log_records.clear()
        self._filtered_records.clear()
        self.log_table.setRowCount(0)
        self.detail_text.clear()
        
    def _copy_logs(self):
        """คัดลอก logs ที่แสดงอยู่"""
        if not self._filtered_records:
            return
            
        text_lines = []
        for record in self._filtered_records:
            time_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
            text_lines.append(f"{time_str} | {record.levelname} | {record.name} | {record.getMessage()}")
            
        text = "\n".join(text_lines)
        
        # คัดลอกไปยัง clipboard
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        QMessageBox.information(self, "Copied", f"Copied {len(text_lines)} log entries to clipboard")
        
    def _save_logs(self):
        """บันทึก logs ลงไฟล์"""
        if not self._filtered_records:
            return
            
        # เลือกไฟล์
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Logs", "sciplotter_logs.txt", "Text Files (*.txt);;All Files (*)"
        )
        
        if not filename:
            return
            
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for record in self._filtered_records:
                    time_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"{time_str} | {record.levelname} | {record.name} | {record.getMessage()}\n")
                    
            QMessageBox.information(self, "Saved", f"Logs saved to {filename}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save logs: {e}")
            
    def add_test_log(self, level: str, message: str):
        """เพิ่ม log ทดสอบ"""
        logger = logging.getLogger("Test")
        if level == "DEBUG":
            logger.debug(message)
        elif level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
        elif level == "CRITICAL":
            logger.critical(message)
