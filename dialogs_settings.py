"""
Settings dialog for SciPlotter
Provides UI for configuring appearance and matplotlib settings
"""

import re
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QListWidget, QListWidgetItem, QMessageBox, QFileDialog,
    QGroupBox, QFormLayout, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase, QColor, QPalette

from settings import SettingsManager, AppConfig

class ColorPicker(QWidget):
    """Simple color picker widget with hex input and color button"""
    
    colorChanged = Signal(str)
    
    def __init__(self, initial_color: str = "#000000", parent=None):
        super().__init__(parent)
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        
        self.color_edit = QLineEdit(initial_color)
        self.color_edit.setPlaceholderText("#RRGGBB")
        self.color_edit.textChanged.connect(self._validate_color)
        
        self.color_button = QPushButton()
        self.color_button.setFixedSize(24, 24)
        self.color_button.clicked.connect(self._pick_color)
        
        self.layout().addWidget(self.color_edit)
        self.layout().addWidget(self.color_button)
        
        self._update_button_color(initial_color)
    
    def _validate_color(self, text: str):
        """Validate hex color format"""
        if re.match(r'^#[0-9A-Fa-f]{6}$', text):
            self._update_button_color(text)
            self.colorChanged.emit(text)
            self.color_edit.setStyleSheet("")
        else:
            self.color_edit.setStyleSheet("QLineEdit { border: 1px solid red; }")
    
    def _update_button_color(self, color: str):
        """Update color button appearance"""
        try:
            qcolor = QColor(color)
            self.color_button.setStyleSheet(f"background-color: {color}; border: 1px solid #666;")
        except:
            pass
    
    def _pick_color(self):
        """Open color picker dialog"""
        color = QColor(self.color_edit.text())
        from PySide6.QtWidgets import QColorDialog
        new_color = QColorDialog.getColor(color, self)
        if new_color.isValid():
            hex_color = new_color.name()
            self.color_edit.setText(hex_color)
    
    def get_color(self) -> str:
        """Get current color value"""
        return self.color_edit.text()
    
    def set_color(self, color: str):
        """Set color value"""
        self.color_edit.setText(color)

class ColorCycleEditor(QWidget):
    """Editor for matplotlib color cycle"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QVBoxLayout())
        
        # Color list
        self.color_list = QListWidget()
        self.color_list.setMaximumHeight(120)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.edit_btn = QPushButton("Edit")
        self.remove_btn = QPushButton("Remove")
        self.move_up_btn = QPushButton("↑")
        self.move_down_btn = QPushButton("↓")
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.move_up_btn)
        btn_layout.addWidget(self.move_down_btn)
        btn_layout.addStretch()
        
        self.layout().addWidget(self.color_list)
        self.layout().addLayout(btn_layout)
        
        # Connect signals
        self.add_btn.clicked.connect(self._add_color)
        self.edit_btn.clicked.connect(self._edit_color)
        self.remove_btn.clicked.connect(self._remove_color)
        self.move_up_btn.clicked.connect(self._move_up)
        self.move_down_btn.clicked.connect(self._move_down)
        
        self._update_buttons()
        self.color_list.currentRowChanged.connect(self._update_buttons)
    
    def _add_color(self):
        """Add new color to cycle"""
        from PySide6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor("#4F9CF9"), self)
        if color.isValid():
            hex_color = color.name()
            item = QListWidgetItem(hex_color)
            item.setBackground(QColor(hex_color))
            item.setForeground(QColor("white") if self._is_dark_color(hex_color) else QColor("black"))
            self.color_list.addItem(item)
    
    def _edit_color(self):
        """Edit selected color"""
        current_item = self.color_list.currentItem()
        if current_item:
            from PySide6.QtWidgets import QColorDialog
            current_color = QColor(current_item.text())
            new_color = QColorDialog.getColor(current_color, self)
            if new_color.isValid():
                hex_color = new_color.name()
                current_item.setText(hex_color)
                current_item.setBackground(QColor(hex_color))
                current_item.setForeground(QColor("white") if self._is_dark_color(hex_color) else QColor("black"))
    
    def _remove_color(self):
        """Remove selected color"""
        current_row = self.color_list.currentRow()
        if current_row >= 0:
            self.color_list.takeItem(current_row)
    
    def _move_up(self):
        """Move selected color up"""
        current_row = self.color_list.currentRow()
        if current_row > 0:
            item = self.color_list.takeItem(current_row)
            self.color_list.insertItem(current_row - 1, item)
            self.color_list.setCurrentRow(current_row - 1)
    
    def _move_down(self):
        """Move selected color down"""
        current_row = self.color_list.currentRow()
        if current_row < self.color_list.count() - 1:
            item = self.color_list.takeItem(current_row)
            self.color_list.insertItem(current_row + 1, item)
            self.color_list.setCurrentRow(current_row + 1)
    
    def _update_buttons(self):
        """Update button states based on selection"""
        has_selection = self.color_list.currentRow() >= 0
        has_items = self.color_list.count() > 0
        current_row = self.color_list.currentRow()
        
        self.edit_btn.setEnabled(has_selection)
        self.remove_btn.setEnabled(has_selection)
        self.move_up_btn.setEnabled(has_selection and current_row > 0)
        self.move_down_btn.setEnabled(has_selection and current_row < self.color_list.count() - 1)
    
    def _is_dark_color(self, hex_color: str) -> bool:
        """Check if color is dark"""
        try:
            color = QColor(hex_color)
            return color.lightness() < 128
        except:
            return False
    
    def get_colors(self) -> list:
        """Get list of colors"""
        colors = []
        for i in range(self.color_list.count()):
            colors.append(self.color_list.item(i).text())
        return colors
    
    def set_colors(self, colors: list):
        """Set list of colors"""
        self.color_list.clear()
        for color in colors:
            item = QListWidgetItem(color)
            item.setBackground(QColor(color))
            item.setForeground(QColor("white") if self._is_dark_color(color) else QColor("black"))
            self.color_list.addItem(item)

class SettingsDialog(QDialog):
    """Main settings dialog with tabs for appearance and matplotlib"""
    
    settingsApplied = Signal()
    
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.original_config = self.settings_manager.config
        
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(600, 500)
        
        self.setup_ui()
        self.load_current_settings()
    
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_appearance_tab(), "Appearance")
        self.tab_widget.addTab(self._create_matplotlib_tab(), "Matplotlib")
        
        layout.addWidget(self.tab_widget)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                               QDialogButtonBox.StandardButton.Cancel | 
                               QDialogButtonBox.StandardButton.Apply)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_settings)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)
        
        # Custom buttons
        custom_layout = QHBoxLayout()
        self.restore_defaults_btn = QPushButton("Restore Defaults")
        self.restore_defaults_btn.clicked.connect(self.restore_defaults)
        custom_layout.addWidget(self.restore_defaults_btn)
        custom_layout.addStretch()
        
        layout.addLayout(custom_layout)
    
    def _create_appearance_tab(self) -> QWidget:
        """Create appearance settings tab"""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # QSS file picker
        self.qss_path_edit = QLineEdit()
        self.qss_browse_btn = QPushButton("Browse...")
        qss_layout = QHBoxLayout()
        qss_layout.addWidget(self.qss_path_edit)
        qss_layout.addWidget(self.qss_browse_btn)
        self.qss_browse_btn.clicked.connect(self._browse_qss)
        
        layout.addRow("QSS File:", qss_layout)
        
        # Font family
        self.font_family_combo = QComboBox()
        self.font_family_combo.addItems(QFontDatabase().families())
        
        layout.addRow("Font Family:", self.font_family_combo)
        
        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(10)
        
        layout.addRow("Font Size:", self.font_size_spin)
        
        return tab
    
    def _create_matplotlib_tab(self) -> QWidget:
        """Create matplotlib settings tab"""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # MPL style file picker
        self.mpl_style_path_edit = QLineEdit()
        self.mpl_style_browse_btn = QPushButton("Browse...")
        mpl_style_layout = QHBoxLayout()
        mpl_style_layout.addWidget(self.mpl_style_path_edit)
        mpl_style_layout.addWidget(self.mpl_style_browse_btn)
        self.mpl_style_browse_btn.clicked.connect(self._browse_mpl_style)
        
        layout.addRow("MPL Style File:", mpl_style_layout)
        
        # Grid settings
        self.grid_enabled_check = QCheckBox("Enable Grid")
        layout.addRow("Grid:", self.grid_enabled_check)
        
        self.grid_alpha_spin = QDoubleSpinBox()
        self.grid_alpha_spin.setRange(0.0, 1.0)
        self.grid_alpha_spin.setSingleStep(0.05)
        self.grid_alpha_spin.setValue(0.25)
        layout.addRow("Grid Alpha:", self.grid_alpha_spin)
        
        self.grid_linestyle_combo = QComboBox()
        self.grid_linestyle_combo.addItems(["-", "--", ":", "-."])
        layout.addRow("Grid Line Style:", self.grid_linestyle_combo)
        
        # Color settings
        self.axes_edgecolor_picker = ColorPicker()
        layout.addRow("Axes Edge Color:", self.axes_edgecolor_picker)
        
        self.text_color_picker = ColorPicker()
        layout.addRow("Text Color:", self.text_color_picker)
        
        # Color cycle
        self.color_cycle_editor = ColorCycleEditor()
        layout.addRow("Color Cycle:", self.color_cycle_editor)
        
        return tab
    
    def _browse_qss(self):
        """Browse for QSS file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select QSS File", "", "QSS Files (*.qss);;All Files (*)"
        )
        if file_path:
            self.qss_path_edit.setText(file_path)
    
    def _browse_mpl_style(self):
        """Browse for matplotlib style file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Matplotlib Style File", "", "Style Files (*.mplstyle);;All Files (*)"
        )
        if file_path:
            self.mpl_style_path_edit.setText(file_path)
    
    def load_current_settings(self):
        """Load current settings into UI"""
        app_config = self.settings_manager.get_appearance()
        mpl_config = self.settings_manager.get_matplotlib()
        
        # Appearance
        self.qss_path_edit.setText(app_config.qt_qss_path)
        self.font_family_combo.setCurrentText(app_config.font_family)
        self.font_size_spin.setValue(app_config.font_size)
        
        # Matplotlib
        self.mpl_style_path_edit.setText(mpl_config.mpl_style_path)
        self.grid_enabled_check.setChecked(mpl_config.grid_enabled)
        self.grid_alpha_spin.setValue(mpl_config.grid_alpha)
        self.grid_linestyle_combo.setCurrentText(mpl_config.grid_linestyle)
        self.axes_edgecolor_picker.set_color(mpl_config.axes_edgecolor)
        self.text_color_picker.set_color(mpl_config.text_color)
        self.color_cycle_editor.set_colors(mpl_config.color_cycle)
    
    def restore_defaults(self):
        """Restore default settings"""
        default_config = self.settings_manager.get_default_config()
        
        # Appearance
        self.qss_path_edit.setText(default_config.appearance.qt_qss_path)
        self.font_family_combo.setCurrentText(default_config.appearance.font_family)
        self.font_size_spin.setValue(default_config.appearance.font_size)
        
        # Matplotlib
        self.mpl_style_path_edit.setText(default_config.matplotlib.mpl_style_path)
        self.grid_enabled_check.setChecked(default_config.matplotlib.grid_enabled)
        self.grid_alpha_spin.setValue(default_config.matplotlib.grid_alpha)
        self.grid_linestyle_combo.setCurrentText(default_config.matplotlib.grid_linestyle)
        self.axes_edgecolor_picker.set_color(default_config.matplotlib.axes_edgecolor)
        self.text_color_picker.set_color(default_config.matplotlib.text_color)
        self.color_cycle_editor.set_colors(default_config.matplotlib.color_cycle)
    
    def apply_settings(self):
        """Apply current settings"""
        try:
            # Validate hex colors
            if not self._validate_hex_color(self.axes_edgecolor_picker.get_color()):
                QMessageBox.warning(self, "Invalid Color", "Axes edge color must be in #RRGGBB format")
                return
            
            if not self._validate_hex_color(self.text_color_picker.get_color()):
                QMessageBox.warning(self, "Invalid Color", "Text color must be in #RRGGBB format")
                return
            
            # Update appearance
            self.settings_manager.update_appearance(
                qt_qss_path=self.qss_path_edit.text(),
                font_family=self.font_family_combo.currentText(),
                font_size=self.font_size_spin.value()
            )
            
            # Update matplotlib
            self.settings_manager.update_matplotlib(
                mpl_style_path=self.mpl_style_path_edit.text(),
                grid_enabled=self.grid_enabled_check.isChecked(),
                grid_alpha=self.grid_alpha_spin.value(),
                grid_linestyle=self.grid_linestyle_combo.currentText(),
                axes_edgecolor=self.axes_edgecolor_picker.get_color(),
                text_color=self.text_color_picker.get_color(),
                color_cycle=self.color_cycle_editor.get_colors()
            )
            
            # Save and apply
            self.settings_manager.save()
            self.settingsApplied.emit()
            
            QMessageBox.information(self, "Success", "Settings applied successfully!")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {str(e)}")
    
    def _validate_hex_color(self, color: str) -> bool:
        """Validate hex color format"""
        return bool(re.match(r'^#[0-9A-Fa-f]{6}$', color))
    
    def accept(self):
        """Handle OK button click"""
        self.apply_settings()
        super().accept()
