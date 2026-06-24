"""
Settings dialog for SciPlotter
Provides UI for configuring appearance and matplotlib settings with live previews
"""

# Set encoding to UTF-8 for proper text display (only once at module level)
import sys
if hasattr(sys, 'setdefaultencoding'):
    sys.setdefaultencoding('utf-8')

import re
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QListWidget, QListWidgetItem, QMessageBox, QFileDialog,
    QGroupBox, QFormLayout, QDialogButtonBox, QSlider, QFrame, QSplitter
)
from PySide6.QtCore import Qt, Signal, QSettings, QLocale
from PySide6.QtGui import QFontDatabase, QColor, QPalette, QFont
from PySide6.QtWidgets import QApplication

from settings import SettingsManager, AppConfig
from widgets.color_button import ColorButtonWithLabel
from widgets.mpl_preview import MatplotlibPreview

class ColorCycleEditor(QWidget):
    """Editor for matplotlib color cycle"""
    
    colorsChanged = Signal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set font that supports multiple languages
        self.setFont(QFont("Segoe UI", 9))
            
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
        # Cosmetic: tooltips for better UX (no logic change)
        self.add_btn.setToolTip("Add a new color to the cycle")
        self.edit_btn.setToolTip("Edit the selected color")
        self.remove_btn.setToolTip("Remove the selected color")
        self.move_up_btn.setToolTip("Move the selected color up")
        self.move_down_btn.setToolTip("Move the selected color down")
        
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
        
        # Add some default colors
        self._add_default_colors()
    
    def _add_default_colors(self):
        """Add some default colors to start with"""
        default_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
        for color in default_colors:
            self._add_color_item(color)
    
    def _add_color(self):
        """Add new color to cycle"""
        from PySide6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor("#4F9CF9"), self)
        if color.isValid():
            self._add_color_item(color.name())
            self._emit_colors_changed()
    
    def _add_color_item(self, hex_color):
        """Add a color item to the list"""
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
                self._emit_colors_changed()
    
    def _remove_color(self):
        """Remove selected color"""
        current_row = self.color_list.currentRow()
        if current_row >= 0:
            self.color_list.takeItem(current_row)
            self._emit_colors_changed()
    
    def _move_up(self):
        """Move selected color up"""
        current_row = self.color_list.currentRow()
        if current_row > 0:
            item = self.color_list.takeItem(current_row)
            self.color_list.insertItem(current_row - 1, item)
            self.color_list.setCurrentRow(current_row - 1)
            self._emit_colors_changed()
    
    def _move_down(self):
        """Move selected color down"""
        current_row = self.color_list.currentRow()
        if current_row < self.color_list.count() - 1:
            item = self.color_list.takeItem(current_row)
            self.color_list.insertItem(current_row + 1, item)
            self.color_list.setCurrentRow(current_row + 1)
            self._emit_colors_changed()
    
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
        except Exception:
            return False
    
    def _emit_colors_changed(self):
        """Emit colors changed signal"""
        self.colorsChanged.emit(self.get_colors())
    
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
            self._add_color_item(color)

class SettingsDialog(QDialog):
    """Main settings dialog with tabs for appearance and matplotlib"""
    
    settingsApplied = Signal()
    
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        
        # Set font that supports multiple languages
        self.setFont(QFont("Segoe UI", 9))
            
        self.settings_manager = settings_manager
        self.original_config = self.settings_manager.config
        
        # Force English locale for number inputs
        self.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        
        # Set default font that supports multiple languages
        app = QApplication.instance()
        if app:
            # Try to set a font that supports multiple languages
            default_font = QFont("Segoe UI", 9)
            if not default_font.exactMatch():
                default_font = QFont("Arial", 9)
            if not default_font.exactMatch():
                default_font = QFont("Helvetica", 9)
            app.setFont(default_font)
            
            # Set font for this dialog
            self.setFont(default_font)
        
        self.setWindowTitle("Settings - SciPlotter")
        self.setModal(True)
        self.resize(1200, 800)  # Increased size for better text display and side-by-side layout
        
        self.setup_ui()
        self.load_current_settings()
        self.setup_connections()
    
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_appearance_tab(), "Appearance")
        self.tab_widget.addTab(self._create_matplotlib_tab(), "Matplotlib")
        
        layout.addWidget(self.tab_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Left side buttons
        self.restore_defaults_btn = QPushButton("Restore Defaults")
        self.restore_defaults_btn.clicked.connect(self.restore_defaults)
        button_layout.addWidget(self.restore_defaults_btn)
        
        button_layout.addStretch()
        
        # Right side buttons
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_settings)
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _create_appearance_tab(self) -> QWidget:
        """Create appearance settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Theme Section
        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout(theme_group)
        theme_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # Allow fields to expand
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Built-in Dark", "Built-in Light", "Custom QSS"])
        self.theme_combo.setMinimumWidth(200)  # Set minimum width for better text display
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        
        self.qss_path_edit = QLineEdit()
        self.qss_path_edit.setPlaceholderText("Path to custom QSS file")
        self.qss_path_edit.setMinimumWidth(300)  # Set minimum width for better text display
        self.qss_browse_btn = QPushButton("Browse...")
        self.qss_browse_btn.clicked.connect(self._browse_qss)
        
        qss_layout = QHBoxLayout()
        qss_layout.addWidget(self.qss_path_edit, 1)  # Give more space to path edit
        qss_layout.addWidget(self.qss_browse_btn)
        
        theme_layout.addRow("Theme:", self.theme_combo)
        theme_layout.addRow("Custom QSS:", qss_layout)
        
        layout.addWidget(theme_group)
        
        # Fonts Section
        font_group = QGroupBox("Fonts")
        font_layout = QFormLayout(font_group)
        font_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # Allow fields to expand
        
        self.font_family_combo = QComboBox()
        # Get available fonts and prioritize common fonts that support multiple languages
        available_fonts = QFontDatabase().families()
        # Prioritize fonts that are known to work well with multiple languages
        priority_fonts = ["Segoe UI", "Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "Ubuntu", "Noto Sans"]
        
        # Add priority fonts first if they exist
        for font in priority_fonts:
            if font in available_fonts:
                self.font_family_combo.addItem(font)
                available_fonts.remove(font)
        
        # Add remaining fonts
        self.font_family_combo.addItems(available_fonts)
        self.font_family_combo.setMinimumWidth(250)  # Set minimum width for better text display
        self.font_family_combo.currentTextChanged.connect(self._update_font_preview)
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(10)
        self.font_size_spin.setMinimumWidth(100)  # Set minimum width for better text display
        self.font_size_spin.valueChanged.connect(self._update_font_preview)
        
        self.apply_to_matplotlib_check = QCheckBox("Apply to Matplotlib")
        self.apply_to_matplotlib_check.setChecked(True)
        
        font_layout.addRow("Font Family:", self.font_family_combo)
        font_layout.addRow("Font Size:", self.font_size_spin)
        font_layout.addRow("", self.apply_to_matplotlib_check)
        
        layout.addWidget(font_group)
        
        # Preview Section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        # Font preview
        self.font_preview_label = QLabel("Font Preview: AaBbCc 123")
        self.font_preview_label.setAlignment(Qt.AlignCenter)
        self.font_preview_label.setFrameStyle(QFrame.Box)
        self.font_preview_label.setMinimumHeight(40)
        preview_layout.addWidget(self.font_preview_label)
        
        # Theme preview
        self.theme_preview_label = QLabel("Theme Preview")
        self.theme_preview_label.setAlignment(Qt.AlignCenter)
        self.theme_preview_label.setFrameStyle(QFrame.Box)
        self.theme_preview_label.setMinimumHeight(40)
        preview_layout.addWidget(self.theme_preview_label)
        
        layout.addWidget(preview_group)
        
        return tab
    
    def _create_matplotlib_tab(self) -> QWidget:
        """Create matplotlib settings tab"""
        tab = QWidget()
        layout = QHBoxLayout(tab)  # Changed from QVBoxLayout to QHBoxLayout
        
        # Left side - Settings
        left_layout = QVBoxLayout()
        
        # Mode Section
        mode_group = QGroupBox("Mode")
        mode_layout = QFormLayout(mode_group)
        mode_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # Allow fields to expand
        
        self.mpl_mode_combo = QComboBox()
        self.mpl_mode_combo.addItems(["Use .mplstyle file", "Custom overrides"])
        self.mpl_mode_combo.setMinimumWidth(200)  # Set minimum width for better text display
        self.mpl_mode_combo.currentTextChanged.connect(self._on_mpl_mode_changed)
        
        self.mpl_style_path_edit = QLineEdit()
        self.mpl_style_path_edit.setPlaceholderText("Path to .mplstyle file")
        self.mpl_style_path_edit.setMinimumWidth(300)  # Set minimum width for better text display
        self.mpl_style_browse_btn = QPushButton("Browse...")
        self.mpl_style_browse_btn.clicked.connect(self._browse_mpl_style)
        
        mpl_style_layout = QHBoxLayout()
        mpl_style_layout.addWidget(self.mpl_style_path_edit, 1)  # Give more space to path edit
        mpl_style_layout.addWidget(self.mpl_style_browse_btn)
        
        mode_layout.addRow("Mode:", self.mpl_mode_combo)
        mode_layout.addRow("Style File:", mpl_style_layout)
        
        left_layout.addWidget(mode_group)
        
        # Overrides Section
        self.overrides_group = QGroupBox("Custom Overrides")
        overrides_layout = QFormLayout(self.overrides_group)
        overrides_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # Allow fields to expand
        
        # Grid settings
        self.grid_enabled_check = QCheckBox("Enable Grid")
        self.grid_enabled_check.toggled.connect(self._update_mpl_preview)
        
        self.grid_alpha_spin = QDoubleSpinBox()
        self.grid_alpha_spin.setRange(0.0, 1.0)
        self.grid_alpha_spin.setSingleStep(0.05)
        self.grid_alpha_spin.setValue(0.25)
        self.grid_alpha_spin.setMinimumWidth(100)  # Set minimum width for better text display
        self.grid_alpha_spin.valueChanged.connect(self._update_mpl_preview)
        
        self.grid_linestyle_combo = QComboBox()
        self.grid_linestyle_combo.addItems([
            "Solid (-)", 
            "Dashed (--)", 
            "Dotted (:)", 
            "Dash-Dot (-.)"
        ])
        self.grid_linestyle_combo.setMinimumWidth(150)  # Set minimum width for better text display
        self.grid_linestyle_combo.currentTextChanged.connect(self._update_mpl_preview)
        
        overrides_layout.addRow("Grid:", self.grid_enabled_check)
        overrides_layout.addRow("Grid Alpha:", self.grid_alpha_spin)
        overrides_layout.addRow("Grid Line Style:", self.grid_linestyle_combo)
        
        # Color settings
        self.axes_color_button = ColorButtonWithLabel("Axes Color")
        self.axes_color_button.setColor(QColor("#000000"))
        self.axes_color_button.colorChanged.connect(self._update_mpl_preview)
        
        self.text_color_button = ColorButtonWithLabel("Text Color")
        self.text_color_button.setColor(QColor("#000000"))
        self.text_color_button.colorChanged.connect(self._update_mpl_preview)
        
        overrides_layout.addRow("Axes Color:", self.axes_color_button)
        overrides_layout.addRow("Text Color:", self.text_color_button)
        
        # Color cycle
        self.color_cycle_editor = ColorCycleEditor()
        self.color_cycle_editor.colorsChanged.connect(self._update_mpl_preview)
        overrides_layout.addRow("Color Cycle:", self.color_cycle_editor)

        # Matplotlib font family (Thai-friendly)
        self.mpl_font_combo = QComboBox()
        self.mpl_font_combo.addItems([
            "Auto (Thai)",
            "Same as App",
            "Noto Sans Thai",
            "TH Sarabun New",
            "Sarabun",
            "Tahoma",
            "Segoe UI",
            "Arial",
            "DejaVu Sans",
        ])
        overrides_layout.addRow("Font Family:", self.mpl_font_combo)
        
        left_layout.addWidget(self.overrides_group)
        
        # Right side - Preview
        right_layout = QVBoxLayout()
        
        # Preview Section
        preview_group = QGroupBox("Matplotlib Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.mpl_preview = MatplotlibPreview()
        preview_layout.addWidget(self.mpl_preview)
        
        right_layout.addWidget(preview_group)
        
        # Add layouts to main layout
        layout.addLayout(left_layout, 2)   # Settings take 2 parts (more space for text)
        layout.addLayout(right_layout, 1)  # Preview takes 1 part
        
        return tab
    
    def setup_connections(self):
        """Setup signal connections"""
        # Theme changes
        self.theme_combo.currentTextChanged.connect(self._update_theme_preview)
        
        # Font changes
        self.font_family_combo.currentTextChanged.connect(self._update_font_preview)
        self.font_size_spin.valueChanged.connect(self._update_font_preview)
    
    def _on_theme_changed(self, theme_text):
        """Handle theme selection change"""
        is_custom = theme_text == "Custom QSS"
        self.qss_path_edit.setEnabled(is_custom)
        self.qss_browse_btn.setEnabled(is_custom)
        self._update_theme_preview()
    
    def _on_mpl_mode_changed(self, mode_text):
        """Handle matplotlib mode change"""
        is_custom = mode_text == "Custom overrides"
        self.overrides_group.setEnabled(is_custom)
        
        if is_custom:
            self._update_mpl_preview()
        else:
            # Apply mplstyle file if available
            style_path = self.mpl_style_path_edit.text()
            if style_path and os.path.exists(style_path):
                self.mpl_preview.apply_mplstyle(style_path)
    
    def _update_font_preview(self):
        """Update font preview"""
        font_family = self.font_family_combo.currentText()
        font_size = self.font_size_spin.value()
        
        font = QFont(font_family, font_size)
        self.font_preview_label.setFont(font)
        self.font_preview_label.setText(f"Font Preview: {font_family} {font_size}pt")
    
    def _update_theme_preview(self):
        """Update theme preview"""
        theme = self.theme_combo.currentText()
        if theme == "Built-in Dark":
            self.theme_preview_label.setText("🌙 Dark Theme - Dark background with light text")
            self.theme_preview_label.setStyleSheet("background-color: #2b2b2b; color: #ffffff; padding: 10px;")
        elif theme == "Built-in Light":
            self.theme_preview_label.setText("☀️ Light Theme - Light background with dark text")
            self.theme_preview_label.setStyleSheet("background-color: #f0f0f0; color: #000000; padding: 10px;")
        else:  # Custom QSS
            self.theme_preview_label.setText("🎨 Custom QSS - Use custom QSS file")
            self.theme_preview_label.setStyleSheet("background-color: #e8f4fd; color: #0066cc; padding: 10px;")
    
    def _get_linestyle_from_description(self, description_text: str) -> str:
        """Convert description to matplotlib linestyle value"""
        if "Solid" in description_text:
            return "-"
        elif "Dashed" in description_text:
            return "--"
        elif "Dotted" in description_text:
            return ":"
        elif "Dash-Dot" in description_text:
            return "-."
        else:
            return "-"
    
    def _update_mpl_preview(self):
        """Update matplotlib preview with current settings"""
        if self.mpl_mode_combo.currentText() == "Custom overrides":
            # Convert description to actual linestyle value
            linestyle = self._get_linestyle_from_description(self.grid_linestyle_combo.currentText())
            
            style_dict = {
                'grid': {
                    'enabled': self.grid_enabled_check.isChecked(),
                    'alpha': self.grid_alpha_spin.value(),
                    'linestyle': linestyle
                },
                'axes_color': self.axes_color_button.color().name(),
                'text_color': self.text_color_button.color().name(),
                'color_cycle': self.color_cycle_editor.get_colors()
            }
            self.mpl_preview.update_style(style_dict)
    
    def _browse_qss(self):
        """Browse for QSS file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select QSS File", "", "QSS Files (*.qss);;All Files (*)"
        )
        if file_path:
            self.qss_path_edit.setText(file_path)
            self._update_theme_preview()
    
    def _browse_mpl_style(self):
        """Browse for matplotlib style file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Matplotlib Style File", "", "Style Files (*.mplstyle);;All Files (*)"
        )
        if file_path:
            self.mpl_style_path_edit.setText(file_path)
            if self.mpl_mode_combo.currentText() == "Use .mplstyle file":
                self.mpl_preview.apply_mplstyle(file_path)
    
    def load_current_settings(self):
        """Load current settings into UI"""
        try:
            app_config = self.settings_manager.get_appearance()
            mpl_config = self.settings_manager.get_matplotlib()
            
            # Appearance
            if app_config.qt_qss_path:
                self.theme_combo.setCurrentText("Custom QSS")
                self.qss_path_edit.setText(app_config.qt_qss_path)
            else:
                self.theme_combo.setCurrentText("Built-in Light")
            
            # Set font family, fallback to a known working font if the saved font doesn't exist
            if app_config.font_family in [self.font_family_combo.itemText(i) for i in range(self.font_family_combo.count())]:
                self.font_family_combo.setCurrentText(app_config.font_family)
            else:
                # Fallback to a known working font
                fallback_fonts = ["Segoe UI", "Arial", "Helvetica"]
                for font in fallback_fonts:
                    if font in [self.font_family_combo.itemText(i) for i in range(self.font_family_combo.count())]:
                        self.font_family_combo.setCurrentText(font)
                        break
                else:
                    # If no fallback font found, use the first available font
                    if self.font_family_combo.count() > 0:
                        self.font_family_combo.setCurrentIndex(0)
            
            self.font_size_spin.setValue(app_config.font_size)
            
            # Matplotlib
            if mpl_config.mpl_style_path:
                self.mpl_mode_combo.setCurrentText("Use .mplstyle file")
                self.mpl_style_path_edit.setText(mpl_config.mpl_style_path)
            else:
                self.mpl_mode_combo.setCurrentText("Custom overrides")
            
            self.grid_enabled_check.setChecked(mpl_config.grid_enabled)
            self.grid_alpha_spin.setValue(mpl_config.grid_alpha)
            # Set grid linestyle combo box based on current setting
            if mpl_config.grid_linestyle == "-":
                self.grid_linestyle_combo.setCurrentText("Solid (-)")
            elif mpl_config.grid_linestyle == "--":
                self.grid_linestyle_combo.setCurrentText("Dashed (--)")
            elif mpl_config.grid_linestyle == ":":
                self.grid_linestyle_combo.setCurrentText("Dotted (:)")
            elif mpl_config.grid_linestyle == "-.":
                self.grid_linestyle_combo.setCurrentText("Dash-Dot (-.)")
            else:
                self.grid_linestyle_combo.setCurrentText("Solid (-)")
            
            # Convert hex colors to QColor
            if mpl_config.axes_edgecolor:
                self.axes_color_button.setColor(QColor(mpl_config.axes_edgecolor))
            if mpl_config.text_color:
                self.text_color_button.setColor(QColor(mpl_config.text_color))
            
            self.color_cycle_editor.set_colors(mpl_config.color_cycle)

            # Matplotlib font family
            try:
                fam = getattr(mpl_config, 'font_family', '') or ''
            except Exception:
                fam = ''
            if fam:
                if fam == app_config.font_family:
                    self.mpl_font_combo.setCurrentText("Same as App")
                elif self.mpl_font_combo.findText(fam) >= 0:
                    self.mpl_font_combo.setCurrentText(fam)
                else:
                    self.mpl_font_combo.insertItem(0, fam)
                    self.mpl_font_combo.setCurrentText(fam)
            else:
                self.mpl_font_combo.setCurrentText("Auto (Thai)")
            
            # Update previews
            self._update_font_preview()
            self._update_theme_preview()
            self._update_mpl_preview()
            
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def collect(self) -> dict:
        """Collect all current settings into a dictionary"""
        return {
            'appearance': {
                'theme': self.theme_combo.currentText(),
                'qt_qss_path': self.qss_path_edit.text() if self.theme_combo.currentText() == "Custom QSS" else "",
                'font_family': self.font_family_combo.currentText(),
                'font_size': self.font_size_spin.value(),
                'apply_to_matplotlib': self.apply_to_matplotlib_check.isChecked()
            },
            'matplotlib': {
                'mode': self.mpl_mode_combo.currentText(),
                'mpl_style_path': self.mpl_style_path_edit.text() if self.mpl_mode_combo.currentText() == "Use .mplstyle file" else "",
                'grid_enabled': self.grid_enabled_check.isChecked(),
                'grid_alpha': self.grid_alpha_spin.value(),
                'grid_linestyle': self._get_linestyle_from_description(self.grid_linestyle_combo.currentText()),
                'axes_edgecolor': self.axes_color_button.color().name(),
                'text_color': self.text_color_button.color().name(),
                'color_cycle': self.color_cycle_editor.get_colors(),
                'font_family': (
                    self.font_family_combo.currentText() if self.mpl_font_combo.currentText() == "Same as App"
                    else ("" if self.mpl_font_combo.currentText().startswith("Auto") else self.mpl_font_combo.currentText())
                )
            }
        }
    
    def restore_defaults(self):
        """Restore default settings"""
        try:
            default_config = self.settings_manager.get_default_config()
            
            # Appearance
            self.theme_combo.setCurrentText("Built-in Light")
            self.qss_path_edit.clear()
            # Set default font family, fallback to a known working font
            if default_config.appearance.font_family in [self.font_family_combo.itemText(i) for i in range(self.font_family_combo.count())]:
                self.font_family_combo.setCurrentText(default_config.appearance.font_family)
            else:
                # Fallback to a known working font
                fallback_fonts = ["Segoe UI", "Arial", "Helvetica"]
                for font in fallback_fonts:
                    if font in [self.font_family_combo.itemText(i) for i in range(self.font_family_combo.count())]:
                        self.font_family_combo.setCurrentText(font)
                        break
                else:
                    # If no fallback font found, use the first available font
                    if self.font_family_combo.count() > 0:
                        self.font_family_combo.setCurrentIndex(0)
            self.font_size_spin.setValue(default_config.appearance.font_size)
            self.apply_to_matplotlib_check.setChecked(True)
            
            # Matplotlib
            self.mpl_mode_combo.setCurrentText("Custom overrides")
            self.mpl_style_path_edit.clear()
            self.grid_enabled_check.setChecked(default_config.matplotlib.grid_enabled)
            self.grid_alpha_spin.setValue(default_config.matplotlib.grid_alpha)
            # Set default grid linestyle
            self.grid_linestyle_combo.setCurrentText("Solid (-)")
            
            # Reset colors to defaults
            self.axes_color_button.setColor(QColor("#000000"))
            self.text_color_button.setColor(QColor("#000000"))
            self.color_cycle_editor.set_colors([])
            
            # Update previews
            self._update_font_preview()
            self._update_theme_preview()
            self._update_mpl_preview()
            
        except Exception as e:
            print(f"Error restoring defaults: {e}")
    
    def apply_settings(self):
        """Apply current settings"""
        try:
            settings = self.collect()
            
            # Import theme functions
            from styles.theme import apply_qss, apply_font, apply_mpl_style, apply_mpl_overrides
            
            # Update appearance
            self.settings_manager.update_appearance(
                qt_qss_path=settings['appearance']['qt_qss_path'],
                font_family=settings['appearance']['font_family'],
                font_size=settings['appearance']['font_size']
            )
            
            # Apply QSS theme
            app = QApplication.instance()
            if app:
                if settings['appearance']['theme'] == "Built-in Dark":
                    apply_qss(app, os.path.join(os.path.dirname(__file__), "..", "styles", "qdark.qss"))
                elif settings['appearance']['theme'] == "Built-in Light":
                    apply_qss(app, os.path.join(os.path.dirname(__file__), "..", "styles", "light.qss"))
                elif settings['appearance']['theme'] == "Custom QSS" and settings['appearance']['qt_qss_path']:
                    apply_qss(app, settings['appearance']['qt_qss_path'])
                
                # Apply font
                apply_font(app, settings['appearance']['font_family'], settings['appearance']['font_size'])
            
            # Apply matplotlib settings
            if settings['matplotlib']['mode'] == "Use .mplstyle file" and settings['matplotlib']['mpl_style_path']:
                apply_mpl_style(settings['matplotlib']['mpl_style_path'])
            else:
                # Apply custom overrides
                apply_mpl_overrides(
                    grid_enabled=settings['matplotlib']['grid_enabled'],
                    grid_alpha=settings['matplotlib']['grid_alpha'],
                    grid_linestyle=settings['matplotlib']['grid_linestyle'],
                    axes_color=settings['matplotlib']['axes_edgecolor'],
                    text_color=settings['matplotlib']['text_color'],
                    color_cycle=settings['matplotlib']['color_cycle'],
                    font_family=settings['matplotlib']['font_family']
                )
            
            # Update matplotlib
            self.settings_manager.update_matplotlib(
                mpl_style_path=settings['matplotlib']['mpl_style_path'],
                grid_enabled=settings['matplotlib']['grid_enabled'],
                grid_alpha=settings['matplotlib']['grid_alpha'],
                grid_linestyle=settings['matplotlib']['grid_linestyle'],
                axes_edgecolor=settings['matplotlib']['axes_edgecolor'],
                text_color=settings['matplotlib']['text_color'],
                color_cycle=settings['matplotlib']['color_cycle'],
                font_family=settings['matplotlib']['font_family']
            )
            
            # Save and apply
            self.settings_manager.save()
            self.settingsApplied.emit()
            
            QMessageBox.information(self, "Success", "Settings applied successfully!")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {str(e)}")
    
    def accept(self):
        """Handle OK button click"""
        self.apply_settings()
        super().accept()
