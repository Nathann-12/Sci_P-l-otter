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
    QGroupBox, QFormLayout, QDialogButtonBox, QSlider, QFrame, QSplitter,
    QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSettings, QLocale
from PySide6.QtGui import QFontDatabase, QColor, QPalette, QFont
from PySide6.QtWidgets import QApplication

from settings import SettingsManager, AppConfig
from widgets.color_button import ColorButton, ColorButtonWithLabel
from widgets.mpl_preview import MatplotlibPreview


ACCENT_PRESETS = (
    ("Origin Blue", "#4F9CF9"),
    ("Ocean Teal", "#20B8A6"),
    ("Emerald", "#34C77B"),
    ("Amber", "#F0A638"),
    ("Coral", "#F06B5D"),
    ("Magenta", "#D768D7"),
)

BACKGROUND_PRESETS = (
    ("Theme Default", ""),
    ("Graphite", "#1E2126"),
    ("Midnight Navy", "#111827"),
    ("Deep Forest", "#10231D"),
    ("Warm Paper", "#F4EFE6"),
    ("Cool Paper", "#EEF3F7"),
)

class ColorCycleEditor(QWidget):
    """Editor for matplotlib color cycle"""
    
    colorsChanged = Signal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        
        # Color list
        self.color_list = QListWidget()
        self.color_list.setMaximumHeight(76)
        
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
        
        root.addWidget(self.color_list)
        root.addLayout(btn_layout)
        
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

        self.settings_manager = settings_manager
        self.original_config = self.settings_manager.config
        self._last_apply_ok = False
        
        # Force English locale for number inputs
        self.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        
        self.setWindowTitle("Settings - SciPlotter")
        self.setModal(True)
        self.resize(900, 620)
        self.setMinimumSize(720, 480)
        
        self.setup_ui()
        self.load_current_settings()
        self.setup_connections()
        self._apply_baseline = self._settings_apply_snapshot()
    
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_appearance_tab(), "Appearance")
        self.tab_widget.addTab(self._create_matplotlib_tab(), "Matplotlib")
        
        layout.addWidget(self.tab_widget)
        
        self.status_label = QLabel("")
        self.status_label.setObjectName("SettingsStatusLabel")
        self.status_label.setMinimumHeight(20)
        layout.addWidget(self.status_label)

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

    def _scroll_tab(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _styles_path(self, filename: str) -> str:
        return str((Path(__file__).resolve().parent / "styles" / filename).resolve())

    def _theme_from_qss_path(self, qss_path: str) -> str:
        name = Path(qss_path or "").name.lower()
        if not qss_path or name in {"qdark.qss", "dark_modern.qss", "dark.qss"}:
            return "Built-in Dark"
        if name == "light.qss":
            return "Built-in Light"
        return "Custom QSS"

    def _theme_text_from_mode(self, mode: str, qss_path: str = "") -> str:
        normalized = str(mode or "").strip().lower()
        if normalized == "light":
            return "Built-in Light"
        if normalized == "custom":
            return "Custom QSS"
        if normalized == "dark":
            return "Built-in Dark"
        return self._theme_from_qss_path(qss_path)

    def _theme_mode(self) -> str:
        return {
            "Built-in Light": "light",
            "Custom QSS": "custom",
        }.get(self.theme_combo.currentText(), "dark")

    def _qss_path_for_theme(self, theme: str) -> str:
        if theme == "Custom QSS":
            return self.qss_path_edit.text().strip()
        return ""

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.setText(text)
        color = "#ff9b9b" if error else "#9fd3a7"
        self.status_label.setStyleSheet(f"color: {color};")
    
    def _create_appearance_tab(self) -> QWidget:
        """Create appearance settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Theme Section
        theme_group = QGroupBox("Theme")
        theme_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        theme_layout = QFormLayout(theme_group)
        theme_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # Allow fields to expand
        theme_layout.setVerticalSpacing(8)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Built-in Dark", "Built-in Light", "Custom QSS"])
        self.theme_combo.setMinimumWidth(180)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)

        self.accent_preset_combo = QComboBox()
        self.accent_preset_combo.setMinimumWidth(180)
        for name, color in ACCENT_PRESETS:
            self.accent_preset_combo.addItem(name, color)
        self.accent_preset_combo.addItem("Custom...", None)
        self.accent_preset_combo.setToolTip("Choose the color used for selections, active tools, and primary actions")

        self.accent_color_button = ColorButton(QColor(ACCENT_PRESETS[0][1]))
        self.accent_color_button.setFixedSize(52, 28)
        self.accent_color_button.setToolTip("Choose a custom theme color")
        self.accent_hex_label = QLabel(ACCENT_PRESETS[0][1])
        self.accent_hex_label.setMinimumWidth(68)

        accent_layout = QHBoxLayout()
        accent_layout.setContentsMargins(0, 0, 0, 0)
        accent_layout.setSpacing(8)
        accent_layout.addWidget(self.accent_preset_combo, 1)
        accent_layout.addWidget(self.accent_color_button)
        accent_layout.addWidget(self.accent_hex_label)

        self.background_preset_combo = QComboBox()
        self.background_preset_combo.setMinimumWidth(180)
        for name, color in BACKGROUND_PRESETS:
            self.background_preset_combo.addItem(name, color)
        self.background_preset_combo.addItem("Custom...", None)
        self.background_preset_combo.setToolTip(
            "Choose the app background; text, surfaces, borders, and icons adapt automatically"
        )

        self.background_color_button = ColorButton(QColor("#1E2126"))
        self.background_color_button.setFixedSize(52, 28)
        self.background_color_button.setToolTip("Choose any custom application background color")
        self.background_hex_label = QLabel("Auto")
        self.background_hex_label.setMinimumWidth(68)

        background_layout = QHBoxLayout()
        background_layout.setContentsMargins(0, 0, 0, 0)
        background_layout.setSpacing(8)
        background_layout.addWidget(self.background_preset_combo, 1)
        background_layout.addWidget(self.background_color_button)
        background_layout.addWidget(self.background_hex_label)
        
        self.qss_path_edit = QLineEdit()
        self.qss_path_edit.setPlaceholderText("Path to custom QSS file")
        self.qss_browse_btn = QPushButton("Browse...")
        self.qss_browse_btn.clicked.connect(self._browse_qss)
        
        qss_layout = QHBoxLayout()
        qss_layout.addWidget(self.qss_path_edit, 1)  # Give more space to path edit
        qss_layout.addWidget(self.qss_browse_btn)
        
        theme_layout.addRow("Theme:", self.theme_combo)
        theme_layout.addRow("Accent Color:", accent_layout)
        theme_layout.addRow("Background:", background_layout)
        theme_layout.addRow("Custom QSS:", qss_layout)
        
        layout.addWidget(theme_group)
        
        # Fonts Section
        font_group = QGroupBox("Fonts")
        font_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        font_layout = QFormLayout(font_group)
        font_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # Allow fields to expand
        font_layout.setVerticalSpacing(8)
        
        self.font_family_combo = QComboBox()
        # Get available fonts and prioritize common fonts that support multiple languages
        from styles.theme import register_bundled_qt_fonts
        register_bundled_qt_fonts()
        available_fonts = list(QFontDatabase.families())
        # Prioritize fonts that are known to work well with multiple languages
        priority_fonts = [
            "Segoe UI", "Tahoma", "TH Sarabun New", "Sarabun", "Noto Sans Thai",
            "Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "Ubuntu", "Noto Sans",
        ]
        if not available_fonts:
            available_fonts = priority_fonts.copy()
        
        # Add priority fonts first if they exist
        for font in priority_fonts:
            if font in available_fonts:
                self.font_family_combo.addItem(font)
                available_fonts.remove(font)
        
        # Add remaining fonts
        self.font_family_combo.addItems(available_fonts)
        self.font_family_combo.setMinimumWidth(220)
        self.font_family_combo.currentTextChanged.connect(self._update_font_preview)
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(10)
        self.font_size_spin.setMaximumWidth(90)
        self.font_size_spin.valueChanged.connect(self._update_font_preview)
        
        self.apply_to_matplotlib_check = QCheckBox("Apply to Matplotlib")
        self.apply_to_matplotlib_check.setChecked(True)
        
        font_layout.addRow("Font Family:", self.font_family_combo)
        font_layout.addRow("Font Size:", self.font_size_spin)
        font_layout.addRow("", self.apply_to_matplotlib_check)
        
        layout.addWidget(font_group)

        # Plot behavior Section
        behavior_group = QGroupBox("Plot Behavior")
        behavior_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        behavior_layout = QFormLayout(behavior_group)
        behavior_layout.setVerticalSpacing(8)

        self.plot_mode_combo = QComboBox()
        self.plot_mode_combo.addItems([
            "Overlay on selected graph",
            "Replace selected graph",
        ])
        self.plot_mode_combo.setToolTip(
            "Controls toolbar/menu plot commands. Worksheet plot buttons still create a new Graph window."
        )
        behavior_layout.addRow("Default Plot Mode:", self.plot_mode_combo)

        hint = QLabel("Worksheet Plot buttons keep the Origin workflow: selected columns -> new Graph.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa3af;")
        behavior_layout.addRow("", hint)

        layout.addWidget(behavior_group)
        
        # Preview Section
        preview_group = QGroupBox("Preview")
        preview_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(6)
        
        # Font preview
        self.font_preview_label = QLabel("Font Preview: AaBbCc 123")
        self.font_preview_label.setAlignment(Qt.AlignCenter)
        self.font_preview_label.setFrameStyle(QFrame.Box)
        self.font_preview_label.setFixedHeight(42)
        preview_layout.addWidget(self.font_preview_label)
        
        # Theme preview
        self.theme_preview_label = QLabel("Theme Preview")
        self.theme_preview_label.setAlignment(Qt.AlignCenter)
        self.theme_preview_label.setFrameStyle(QFrame.Box)
        self.theme_preview_label.setFixedHeight(42)
        self.theme_preview_label.setProperty("sciplotterThemeBypass", True)
        preview_layout.addWidget(self.theme_preview_label)
        
        layout.addWidget(preview_group)
        layout.addStretch(1)
        
        return self._scroll_tab(tab)
    
    def _create_matplotlib_tab(self) -> QWidget:
        """Create matplotlib settings tab"""
        tab = QWidget()
        layout = QHBoxLayout(tab)  # Changed from QVBoxLayout to QHBoxLayout
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        
        # Left side - Settings
        left_layout = QVBoxLayout()
        
        # Mode Section
        mode_group = QGroupBox("Mode")
        mode_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        mode_layout = QFormLayout(mode_group)
        mode_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # Allow fields to expand
        mode_layout.setVerticalSpacing(8)
        
        self.mpl_mode_combo = QComboBox()
        self.mpl_mode_combo.addItems(["Use .mplstyle file", "Custom overrides"])
        self.mpl_mode_combo.setMinimumWidth(180)
        self.mpl_mode_combo.currentTextChanged.connect(self._on_mpl_mode_changed)
        
        self.mpl_style_path_edit = QLineEdit()
        self.mpl_style_path_edit.setPlaceholderText("Path to .mplstyle file")
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
        overrides_layout.setVerticalSpacing(8)
        
        # Grid settings
        self.grid_enabled_check = QCheckBox("Enable Grid")
        self.grid_enabled_check.toggled.connect(self._update_mpl_preview)
        
        self.grid_alpha_spin = QDoubleSpinBox()
        self.grid_alpha_spin.setRange(0.0, 1.0)
        self.grid_alpha_spin.setSingleStep(0.05)
        self.grid_alpha_spin.setValue(0.25)
        self.grid_alpha_spin.setMaximumWidth(90)
        self.grid_alpha_spin.valueChanged.connect(self._update_mpl_preview)
        
        self.grid_linestyle_combo = QComboBox()
        self.grid_linestyle_combo.addItems([
            "Solid (-)", 
            "Dashed (--)", 
            "Dotted (:)", 
            "Dash-Dot (-.)"
        ])
        self.grid_linestyle_combo.setMinimumWidth(140)
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

        self.mpl_font_size_spin = QSpinBox()
        self.mpl_font_size_spin.setRange(6, 32)
        self.mpl_font_size_spin.setValue(10)
        self.mpl_font_size_spin.setMaximumWidth(90)
        overrides_layout.addRow("Font Size:", self.mpl_font_size_spin)
        
        left_layout.addWidget(self.overrides_group)
        
        # Right side - Preview
        right_layout = QVBoxLayout()
        
        # Preview Section
        preview_group = QGroupBox("Matplotlib Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.mpl_preview = MatplotlibPreview()
        self.mpl_preview.preview_frame.setMinimumSize(300, 210)
        preview_layout.addWidget(self.mpl_preview)
        
        right_layout.addWidget(preview_group)
        
        # Add layouts to main layout
        layout.addLayout(left_layout, 2)   # Settings take 2 parts (more space for text)
        layout.addLayout(right_layout, 1)  # Preview takes 1 part
        
        return self._scroll_tab(tab)
    
    def setup_connections(self):
        """Setup signal connections"""
        # Theme changes
        self.theme_combo.currentTextChanged.connect(self._update_theme_preview)
        self.accent_preset_combo.currentIndexChanged.connect(self._on_accent_preset_changed)
        self.accent_color_button.colorChanged.connect(self._on_accent_color_changed)
        self.background_preset_combo.currentIndexChanged.connect(self._on_background_preset_changed)
        self.background_color_button.colorChanged.connect(self._on_background_color_changed)
        
        # Font changes
        self.font_family_combo.currentTextChanged.connect(self._update_font_preview)
        self.font_size_spin.valueChanged.connect(self._update_font_preview)
    
    def _on_theme_changed(self, theme_text):
        """Handle theme selection change"""
        is_custom = theme_text == "Custom QSS"
        self.qss_path_edit.setEnabled(is_custom)
        self.qss_browse_btn.setEnabled(is_custom)
        if self.background_preset_combo.currentData() == "":
            self._on_background_preset_changed(self.background_preset_combo.currentIndex())
        self._update_theme_preview()

    def _on_accent_preset_changed(self, _index: int) -> None:
        color_value = self.accent_preset_combo.currentData()
        if not color_value:
            return
        color = QColor(str(color_value))
        self.accent_color_button.blockSignals(True)
        self.accent_color_button.setColor(color)
        self.accent_color_button.blockSignals(False)
        self.accent_hex_label.setText(color.name().upper())
        self._update_theme_preview()

    def _on_accent_color_changed(self, color: QColor) -> None:
        color_name = color.name().upper()
        self.accent_hex_label.setText(color_name)
        matching_index = self.accent_preset_combo.count() - 1
        for index in range(self.accent_preset_combo.count() - 1):
            if str(self.accent_preset_combo.itemData(index)).upper() == color_name:
                matching_index = index
                break
        self.accent_preset_combo.blockSignals(True)
        self.accent_preset_combo.setCurrentIndex(matching_index)
        self.accent_preset_combo.blockSignals(False)
        self._update_theme_preview()

    def _default_background_color(self) -> QColor:
        from styles.theme import build_theme_palette

        mode = "light" if self.theme_combo.currentText() == "Built-in Light" else "dark"
        return QColor(build_theme_palette(mode).background)

    def _background_color_value(self) -> str:
        if self.background_preset_combo.currentData() == "":
            return ""
        return self.background_color_button.color().name().upper()

    def _on_background_preset_changed(self, _index: int) -> None:
        color_value = self.background_preset_combo.currentData()
        if color_value is None:
            self.background_hex_label.setText(self.background_color_button.color().name().upper())
            self._update_theme_preview()
            return
        color = self._default_background_color() if color_value == "" else QColor(str(color_value))
        self.background_color_button.blockSignals(True)
        self.background_color_button.setColor(color)
        self.background_color_button.blockSignals(False)
        self.background_hex_label.setText("Auto" if color_value == "" else color.name().upper())
        self._update_theme_preview()

    def _on_background_color_changed(self, color: QColor) -> None:
        color_name = color.name().upper()
        matching_index = self.background_preset_combo.count() - 1
        for index in range(1, self.background_preset_combo.count() - 1):
            if str(self.background_preset_combo.itemData(index)).upper() == color_name:
                matching_index = index
                break
        self.background_preset_combo.blockSignals(True)
        self.background_preset_combo.setCurrentIndex(matching_index)
        self.background_preset_combo.blockSignals(False)
        self.background_hex_label.setText(color_name)
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
        from styles.theme import build_theme_palette

        preview_mode = "light" if theme == "Built-in Light" else "dark"
        background = self._background_color_value()
        palette = build_theme_palette(
            preview_mode,
            self.accent_color_button.color().name(),
            background,
        )
        if background:
            self.theme_preview_label.setText(
                f"Custom Background  |  automatic {palette.mode.title()} contrast"
            )
        elif theme == "Built-in Dark":
            self.theme_preview_label.setText("Dark Theme  |  menus, tools, workbooks, and dialogs")
        elif theme == "Built-in Light":
            self.theme_preview_label.setText("Light Theme  |  menus, tools, workbooks, and dialogs")
        else:  # Custom QSS
            self.theme_preview_label.setText("Custom QSS  |  app font and popup safety remain active")
        self.theme_preview_label.setStyleSheet(
            f"background-color: {palette.surface}; color: {palette.text}; "
            f"border: 2px solid {palette.accent}; border-radius: 7px; padding: 8px;"
        )
    
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
            theme = self._theme_text_from_mode(
                getattr(app_config, "theme_mode", ""),
                app_config.qt_qss_path,
            )
            self.theme_combo.setCurrentText(theme)
            self.qss_path_edit.setText(app_config.qt_qss_path if theme == "Custom QSS" else "")
            accent = QColor(getattr(app_config, "accent_color", ACCENT_PRESETS[0][1]))
            if not accent.isValid():
                accent = QColor(ACCENT_PRESETS[0][1])
            self.accent_color_button.setColor(accent)
            self._on_accent_color_changed(accent)
            background = QColor(getattr(app_config, "background_color", ""))
            if background.isValid():
                self.background_color_button.setColor(background)
                self._on_background_color_changed(background)
            else:
                self.background_preset_combo.setCurrentIndex(0)
                self._on_background_preset_changed(0)
            
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
            self.apply_to_matplotlib_check.setChecked(
                bool(getattr(mpl_config, "font_family", "")) and mpl_config.font_family == app_config.font_family
            )

            # Plot behavior
            qsettings = QSettings("SciPlotter", "SciPlotter")
            mode = str(qsettings.value("plot/mode", "overlay")).lower()
            self.plot_mode_combo.setCurrentText(
                "Replace selected graph" if mode.endswith("replace") else "Overlay on selected graph"
            )
            
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
            self.mpl_font_size_spin.setValue(
                int(getattr(mpl_config, "font_size", app_config.font_size) or app_config.font_size)
            )
            
            # Update previews
            self._on_theme_changed(self.theme_combo.currentText())
            self._update_font_preview()
            self._update_theme_preview()
            self._update_mpl_preview()
            
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def collect(self) -> dict:
        """Collect all current settings into a dictionary"""
        app_font = self.font_family_combo.currentText()
        mpl_font = (
            app_font if self.apply_to_matplotlib_check.isChecked()
            else (
                app_font if self.mpl_font_combo.currentText() == "Same as App"
                else ("" if self.mpl_font_combo.currentText().startswith("Auto") else self.mpl_font_combo.currentText())
            )
        )
        return {
            'appearance': {
                'theme': self.theme_combo.currentText(),
                'theme_mode': self._theme_mode(),
                'accent_color': self.accent_color_button.color().name().upper(),
                'background_color': self._background_color_value(),
                'qt_qss_path': self._qss_path_for_theme(self.theme_combo.currentText()),
                'font_family': app_font,
                'font_size': self.font_size_spin.value(),
                'apply_to_matplotlib': self.apply_to_matplotlib_check.isChecked()
            },
            'application': {
                'plot_mode': "replace" if self.plot_mode_combo.currentText().startswith("Replace") else "overlay",
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
                'font_family': mpl_font,
                'font_size': (
                    self.font_size_spin.value()
                    if self.apply_to_matplotlib_check.isChecked()
                    or self.mpl_font_combo.currentText() == "Same as App"
                    else self.mpl_font_size_spin.value()
                ),
            }
        }
    
    def restore_defaults(self):
        """Restore default settings"""
        try:
            default_config = self.settings_manager.get_default_config()
            
            # Appearance
            self.theme_combo.setCurrentText("Built-in Dark")
            self.accent_color_button.setColor(QColor(default_config.appearance.accent_color))
            self._on_accent_color_changed(self.accent_color_button.color())
            self.background_preset_combo.setCurrentIndex(0)
            self._on_background_preset_changed(0)
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
            self.plot_mode_combo.setCurrentText("Overlay on selected graph")
            
            # Matplotlib
            self.mpl_mode_combo.setCurrentText("Custom overrides")
            self.mpl_style_path_edit.clear()
            self.grid_enabled_check.setChecked(default_config.matplotlib.grid_enabled)
            self.grid_alpha_spin.setValue(default_config.matplotlib.grid_alpha)
            # Set default grid linestyle
            self.grid_linestyle_combo.setCurrentText("Solid (-)")
            
            # Reset colors to the same defaults used by persisted config.
            self.axes_color_button.setColor(QColor(default_config.matplotlib.axes_edgecolor))
            self.text_color_button.setColor(QColor(default_config.matplotlib.text_color))
            self.color_cycle_editor.set_colors(default_config.matplotlib.color_cycle)
            self.mpl_font_combo.setCurrentText("Auto (Thai)")
            self.mpl_font_size_spin.setValue(default_config.matplotlib.font_size)
            
            # Update previews
            self._update_font_preview()
            self._update_theme_preview()
            self._update_mpl_preview()
            
        except Exception as e:
            print(f"Error restoring defaults: {e}")

    def _validate_settings(self, settings: dict) -> bool:
        theme = settings['appearance']['theme']
        qss_path = settings['appearance']['qt_qss_path']
        if theme == "Custom QSS" and (not qss_path or not os.path.isfile(qss_path)):
            self._set_status(f"QSS file not found: {qss_path}", error=True)
            return False

        mpl_path = settings['matplotlib']['mpl_style_path']
        if settings['matplotlib']['mode'] == "Use .mplstyle file" and (not mpl_path or not os.path.isfile(mpl_path)):
            self._set_status(f"Matplotlib style file not found: {mpl_path}", error=True)
            return False
        return True

    def _apply_mpl_font(self, font_family: str, font_size: int) -> None:
        try:
            import matplotlib
            if font_family:
                matplotlib.rcParams["font.family"] = [
                    font_family,
                    "Noto Sans Thai",
                    "TH Sarabun New",
                    "Sarabun",
                    "Tahoma",
                    "Segoe UI",
                    "Arial",
                    "DejaVu Sans",
                ]
            matplotlib.rcParams["font.size"] = int(font_size)
            matplotlib.rcParams["axes.unicode_minus"] = False
            matplotlib.rcParams["text.usetex"] = False
        except Exception:
            pass

    def _current_appearance_dict(self) -> dict:
        config = self.settings_manager.get_appearance()
        return {
            "theme_mode": getattr(config, "theme_mode", "dark"),
            "accent_color": str(getattr(config, "accent_color", ACCENT_PRESETS[0][1])).upper(),
            "background_color": str(getattr(config, "background_color", "") or "").upper(),
            "qt_qss_path": getattr(config, "qt_qss_path", ""),
            "font_family": getattr(config, "font_family", ""),
            "font_size": int(getattr(config, "font_size", 0) or 0),
        }

    def _current_matplotlib_dict(self) -> dict:
        config = self.settings_manager.get_matplotlib()
        return {
            "mpl_style_path": getattr(config, "mpl_style_path", ""),
            "grid_enabled": bool(getattr(config, "grid_enabled", True)),
            "grid_alpha": float(getattr(config, "grid_alpha", 0.0)),
            "grid_linestyle": getattr(config, "grid_linestyle", "-"),
            "axes_edgecolor": str(getattr(config, "axes_edgecolor", "")),
            "text_color": str(getattr(config, "text_color", "")),
            "color_cycle": list(getattr(config, "color_cycle", []) or []),
            "font_family": getattr(config, "font_family", ""),
            "font_size": int(getattr(config, "font_size", 10) or 10),
        }

    def _settings_apply_snapshot(self) -> dict:
        settings = self.collect()
        return {
            "appearance": {
                "theme_mode": settings['appearance']['theme_mode'],
                "accent_color": settings['appearance']['accent_color'],
                "background_color": settings['appearance']['background_color'],
                "qt_qss_path": settings['appearance']['qt_qss_path'],
                "font_family": settings['appearance']['font_family'],
                "font_size": int(settings['appearance']['font_size']),
            },
            "matplotlib": {
                "mpl_style_path": settings['matplotlib']['mpl_style_path'],
                "grid_enabled": bool(settings['matplotlib']['grid_enabled']),
                "grid_alpha": float(settings['matplotlib']['grid_alpha']),
                "grid_linestyle": settings['matplotlib']['grid_linestyle'],
                "axes_edgecolor": settings['matplotlib']['axes_edgecolor'],
                "text_color": settings['matplotlib']['text_color'],
                "color_cycle": list(settings['matplotlib']['color_cycle']),
                "font_family": settings['matplotlib']['font_family'],
                "font_size": int(settings['matplotlib']['font_size']),
            },
        }
    
    def apply_settings(self):
        """Apply current settings"""
        try:
            settings = self.collect()
            if not self._validate_settings(settings):
                self._last_apply_ok = False
                return False

            new_appearance = {
                "theme_mode": settings['appearance']['theme_mode'],
                "accent_color": settings['appearance']['accent_color'],
                "background_color": settings['appearance']['background_color'],
                "qt_qss_path": settings['appearance']['qt_qss_path'],
                "font_family": settings['appearance']['font_family'],
                "font_size": int(settings['appearance']['font_size']),
            }
            new_matplotlib = {
                "mpl_style_path": settings['matplotlib']['mpl_style_path'],
                "grid_enabled": bool(settings['matplotlib']['grid_enabled']),
                "grid_alpha": float(settings['matplotlib']['grid_alpha']),
                "grid_linestyle": settings['matplotlib']['grid_linestyle'],
                "axes_edgecolor": settings['matplotlib']['axes_edgecolor'],
                "text_color": settings['matplotlib']['text_color'],
                "color_cycle": list(settings['matplotlib']['color_cycle']),
                "font_family": settings['matplotlib']['font_family'],
                "font_size": int(settings['matplotlib']['font_size']),
            }
            baseline = getattr(self, "_apply_baseline", None)
            if isinstance(baseline, dict):
                appearance_changed = new_appearance != baseline.get("appearance", {})
                matplotlib_changed = new_matplotlib != baseline.get("matplotlib", {})
            else:
                appearance_changed = new_appearance != self._current_appearance_dict()
                matplotlib_changed = new_matplotlib != self._current_matplotlib_dict()
            
            # Update appearance
            self.settings_manager.update_appearance(**new_appearance)
            
            # Apply the complete appearance in one pass. The runtime signature
            # check also repairs sessions created by older Settings code, which
            # used to reset QApplication's font as soon as the dialog opened.
            app = QApplication.instance()
            runtime_matches = False
            if app:
                app_font = app.font()
                runtime_matches = (
                    str(app.property("sciplotterThemeMode") or "") == new_appearance["theme_mode"]
                    and str(app.property("sciplotterAccentColor") or "").upper() == new_appearance["accent_color"]
                    and str(app.property("sciplotterBackgroundColor") or "").upper() == new_appearance["background_color"]
                    and app_font.family().casefold() == new_appearance["font_family"].casefold()
                    and app_font.pointSize() == new_appearance["font_size"]
                )
            if app and (appearance_changed or not runtime_matches):
                from styles.theme import apply_theme_from_config
                apply_theme_from_config(app, self.settings_manager.get_appearance())
            
            # Apply matplotlib settings only when they changed. Re-applying font
            # managers and stylesheets gets very expensive when the QApplication
            # already owns many widgets in long user-flow test runs.
            if matplotlib_changed:
                from styles.theme import apply_mpl_style, apply_mpl_overrides
                if settings['matplotlib']['mode'] == "Use .mplstyle file" and settings['matplotlib']['mpl_style_path']:
                    apply_mpl_style(settings['matplotlib']['mpl_style_path'])
                    self._apply_mpl_font(
                        settings['matplotlib']['font_family'],
                        settings['matplotlib']['font_size'],
                    )
                else:
                    apply_mpl_overrides(
                        grid_enabled=settings['matplotlib']['grid_enabled'],
                        grid_alpha=settings['matplotlib']['grid_alpha'],
                        grid_linestyle=settings['matplotlib']['grid_linestyle'],
                        axes_color=settings['matplotlib']['axes_edgecolor'],
                        text_color=settings['matplotlib']['text_color'],
                        color_cycle=settings['matplotlib']['color_cycle'],
                        font_family=settings['matplotlib']['font_family'],
                        font_size=settings['matplotlib']['font_size'],
                    )
            
            # Update matplotlib
            self.settings_manager.update_matplotlib(**new_matplotlib)

            # Apply runtime application behavior
            qsettings = QSettings("SciPlotter", "SciPlotter")
            qsettings.setValue("plot/mode", settings['application']['plot_mode'])
            parent = self.parent()
            if parent is not None and hasattr(parent, "plot_mode"):
                try:
                    from core.plot_mode import PlotMode
                    parent.plot_mode = PlotMode(settings['application']['plot_mode'])
                except Exception:
                    parent.plot_mode = settings['application']['plot_mode']
            
            # Save and apply
            self.settings_manager.save()
            self.settingsApplied.emit()
            self._apply_baseline = {
                "appearance": dict(new_appearance),
                "matplotlib": dict(new_matplotlib),
            }
            
            self._last_apply_ok = True
            self._set_status("Settings applied.")
            return True
            
        except Exception as e:
            self._last_apply_ok = False
            self._set_status(f"Failed to apply settings: {e}", error=True)
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {str(e)}")
            return False
    
    def accept(self):
        """Handle OK button click"""
        if self.apply_settings():
            super().accept()
