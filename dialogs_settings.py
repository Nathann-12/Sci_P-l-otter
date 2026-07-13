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
from widgets.color_button import ColorButton
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
        self._mpl_preview_suspended = True
        
        # Force English locale for number inputs
        self.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        
        self.setWindowTitle("Settings - SciPlotter")
        self.setModal(True)
        self.resize(900, 620)
        self.setMinimumSize(720, 480)
        
        self.setup_ui()
        self.load_current_settings()
        self.setup_connections()
        self._mpl_preview_suspended = False
        self._on_mpl_mode_changed(self.mpl_mode_combo.currentText())
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
        """Create production Matplotlib settings with an isolated preview."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        def double_spin(minimum, maximum, step, value, decimals=2):
            spin = QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setValue(value)
            spin.setMaximumWidth(90)
            spin.valueChanged.connect(self._update_mpl_preview)
            return spin

        def int_spin(minimum, maximum, value):
            spin = QSpinBox()
            spin.setRange(minimum, maximum)
            spin.setValue(value)
            spin.setMaximumWidth(90)
            spin.valueChanged.connect(self._update_mpl_preview)
            return spin

        left_layout = QVBoxLayout()

        mode_group = QGroupBox("Style Source")
        mode_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        mode_layout = QFormLayout(mode_group)
        mode_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        mode_layout.setVerticalSpacing(8)

        self.mpl_mode_combo = QComboBox()
        self.mpl_mode_combo.addItems([
            "Follow app theme",
            "Custom overrides",
            "Use .mplstyle file",
        ])
        self.mpl_mode_combo.setMinimumWidth(180)
        self.mpl_mode_combo.currentTextChanged.connect(self._on_mpl_mode_changed)

        self.mpl_style_path_edit = QLineEdit()
        self.mpl_style_path_edit.setPlaceholderText("Path to .mplstyle file")
        self.mpl_style_path_edit.editingFinished.connect(self._update_mpl_preview)
        self.mpl_style_browse_btn = QPushButton("Browse...")
        self.mpl_style_browse_btn.clicked.connect(self._browse_mpl_style)

        mpl_style_layout = QHBoxLayout()
        mpl_style_layout.setContentsMargins(0, 0, 0, 0)
        mpl_style_layout.addWidget(self.mpl_style_path_edit, 1)
        mpl_style_layout.addWidget(self.mpl_style_browse_btn)
        mode_layout.addRow("Mode:", self.mpl_mode_combo)
        mode_layout.addRow("Style File:", mpl_style_layout)
        self.mpl_source_hint = QLabel()
        self.mpl_source_hint.setWordWrap(True)
        self.mpl_source_hint.setObjectName("SettingsHint")
        mode_layout.addRow("", self.mpl_source_hint)
        left_layout.addWidget(mode_group)

        self.overrides_group = QGroupBox("Plot Colors")
        colors_layout = QFormLayout(self.overrides_group)
        colors_layout.setVerticalSpacing(7)
        self.figure_color_button = ColorButton(QColor("#1E2126"))
        self.axes_facecolor_button = ColorButton(QColor("#1E2126"))
        self.axes_color_button = ColorButton(QColor("#3A3F44"))
        self.text_color_button = ColorButton(QColor("#E6E6E6"))
        self.grid_color_button = ColorButton(QColor("#3A3F44"))
        for button in (
            self.figure_color_button,
            self.axes_facecolor_button,
            self.axes_color_button,
            self.text_color_button,
            self.grid_color_button,
        ):
            button.colorChanged.connect(self._update_mpl_preview)
        colors_layout.addRow("Figure Background:", self.figure_color_button)
        colors_layout.addRow("Plot Background:", self.axes_facecolor_button)
        colors_layout.addRow("Spines / Border:", self.axes_color_button)
        colors_layout.addRow("Text / Ticks:", self.text_color_button)
        colors_layout.addRow("Grid Color:", self.grid_color_button)
        left_layout.addWidget(self.overrides_group)

        grid_group = QGroupBox("Grid")
        grid_layout = QFormLayout(grid_group)
        grid_layout.setVerticalSpacing(7)
        self.grid_enabled_check = QCheckBox("Enable Grid")
        self.grid_enabled_check.toggled.connect(self._update_mpl_preview)
        self.grid_alpha_spin = double_spin(0.0, 1.0, 0.05, 0.25)
        self.grid_linestyle_combo = QComboBox()
        self.grid_linestyle_combo.addItems([
            "Solid (-)",
            "Dashed (--)",
            "Dotted (:)",
            "Dash-Dot (-.)",
        ])
        self.grid_linestyle_combo.setMinimumWidth(140)
        self.grid_linestyle_combo.currentTextChanged.connect(self._update_mpl_preview)
        self.grid_linewidth_spin = double_spin(0.1, 5.0, 0.1, 0.6)
        grid_layout.addRow("Visible:", self.grid_enabled_check)
        grid_layout.addRow("Opacity:", self.grid_alpha_spin)
        grid_layout.addRow("Line Style:", self.grid_linestyle_combo)
        grid_layout.addRow("Line Width:", self.grid_linewidth_spin)
        left_layout.addWidget(grid_group)

        series_group = QGroupBox("Series Defaults")
        series_layout = QFormLayout(series_group)
        series_layout.setVerticalSpacing(7)
        self.line_width_spin = double_spin(0.1, 10.0, 0.25, 2.0)
        self.marker_size_spin = double_spin(0.0, 30.0, 0.5, 5.5, decimals=1)
        self.color_cycle_editor = ColorCycleEditor()
        self.color_cycle_editor.colorsChanged.connect(self._update_mpl_preview)
        series_layout.addRow("Line Width:", self.line_width_spin)
        series_layout.addRow("Marker Size:", self.marker_size_spin)
        series_layout.addRow("Color Cycle:", self.color_cycle_editor)
        left_layout.addWidget(series_group)

        type_group = QGroupBox("Typography")
        type_layout = QFormLayout(type_group)
        type_layout.setVerticalSpacing(7)
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
        self.mpl_font_combo.currentTextChanged.connect(self._update_mpl_preview)
        self.mpl_font_size_spin = int_spin(6, 40, 10)
        self.title_size_spin = int_spin(6, 48, 12)
        self.label_size_spin = int_spin(6, 40, 11)
        self.tick_size_spin = int_spin(6, 32, 10)
        self.legend_size_spin = int_spin(6, 32, 10)
        type_layout.addRow("Font Family:", self.mpl_font_combo)
        type_layout.addRow("Base Size:", self.mpl_font_size_spin)
        type_layout.addRow("Title Size:", self.title_size_spin)
        type_layout.addRow("Axis Label Size:", self.label_size_spin)
        type_layout.addRow("Tick Size:", self.tick_size_spin)
        type_layout.addRow("Legend Size:", self.legend_size_spin)
        left_layout.addWidget(type_group)

        output_group = QGroupBox("Canvas & Export")
        output_layout = QFormLayout(output_group)
        output_layout.setVerticalSpacing(7)
        self.figure_dpi_spin = int_spin(50, 600, 130)
        self.savefig_dpi_spin = int_spin(72, 1200, 220)
        self.savefig_transparent_check = QCheckBox("Transparent background")
        self.savefig_transparent_check.toggled.connect(self._update_mpl_preview)
        output_layout.addRow("Canvas DPI:", self.figure_dpi_spin)
        output_layout.addRow("Export DPI:", self.savefig_dpi_spin)
        output_layout.addRow("Export:", self.savefig_transparent_check)
        left_layout.addWidget(output_group)
        left_layout.addStretch(1)

        right_layout = QVBoxLayout()
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.mpl_preview = MatplotlibPreview()
        self.mpl_preview.preview_frame.setMinimumSize(300, 210)
        preview_layout.addWidget(self.mpl_preview)
        preview_note = QLabel(
            "Preview changes are isolated. Open graphs and global defaults update only after Apply."
        )
        preview_note.setWordWrap(True)
        preview_note.setObjectName("SettingsHint")
        preview_layout.addWidget(preview_note)
        right_layout.addWidget(preview_group)
        right_layout.addStretch(1)

        layout.addLayout(left_layout, 3)
        layout.addLayout(right_layout, 2)
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
        self.font_family_combo.currentTextChanged.connect(self._update_mpl_preview)
        self.font_size_spin.valueChanged.connect(self._update_mpl_preview)
        self.apply_to_matplotlib_check.toggled.connect(self._update_mpl_preview)
    
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
        mode = self._matplotlib_mode()
        is_custom = mode == "custom"
        is_file = mode == "file"
        self.overrides_group.setEnabled(is_custom)
        self.mpl_style_path_edit.setEnabled(is_file)
        self.mpl_style_browse_btn.setEnabled(is_file)
        if mode == "theme":
            self.mpl_source_hint.setText(
                "Canvas colors follow the active app theme and custom app background."
            )
        elif mode == "custom":
            self.mpl_source_hint.setText(
                "Use explicit plot colors. Grid, series, typography, and output settings always apply."
            )
        else:
            self.mpl_source_hint.setText(
                "Load colors and layout from a .mplstyle file, then apply the common settings below."
            )
        self._update_mpl_preview()

    def _matplotlib_mode(self) -> str:
        return {
            "Follow app theme": "theme",
            "Use .mplstyle file": "file",
            "Custom overrides": "custom",
        }.get(self.mpl_mode_combo.currentText(), "theme")
    
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
        if (
            hasattr(self, "mpl_mode_combo")
            and self._matplotlib_mode() == "theme"
        ):
            self._update_mpl_preview()
    
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
        """Render proposed settings without changing global Matplotlib state."""
        if self._mpl_preview_suspended:
            return
        mode = self._matplotlib_mode()
        family_text = self.mpl_font_combo.currentText()
        if self.apply_to_matplotlib_check.isChecked() or family_text == "Same as App":
            preview_family = self.font_family_combo.currentText()
        elif family_text.startswith("Auto"):
            preview_family = ""
        else:
            preview_family = family_text

        style_dict = {
            "grid": {
                "enabled": self.grid_enabled_check.isChecked(),
                "alpha": self.grid_alpha_spin.value(),
                "linestyle": self._get_linestyle_from_description(
                    self.grid_linestyle_combo.currentText()
                ),
                "linewidth": self.grid_linewidth_spin.value(),
            },
            "color_cycle": self.color_cycle_editor.get_colors(),
            "line_width": self.line_width_spin.value(),
            "marker_size": self.marker_size_spin.value(),
            "font": {
                "family": preview_family,
                "title_size": self.title_size_spin.value(),
                "label_size": self.label_size_spin.value(),
                "tick_size": self.tick_size_spin.value(),
                "legend_size": self.legend_size_spin.value(),
            },
        }
        style_file = None
        if mode == "theme":
            from styles.theme import build_theme_palette

            palette = build_theme_palette(
                "light" if self.theme_combo.currentText() == "Built-in Light" else "dark",
                self.accent_color_button.color().name(),
                self._background_color_value(),
            )
            style_dict.update({
                "figure_facecolor": palette.background,
                "axes_facecolor": palette.surface,
                "axes_color": palette.border,
                "text_color": palette.text,
                "grid_color": palette.border,
            })
        elif mode == "custom":
            style_dict.update({
                "figure_facecolor": self.figure_color_button.color().name(),
                "axes_facecolor": self.axes_facecolor_button.color().name(),
                "axes_color": self.axes_color_button.color().name(),
                "text_color": self.text_color_button.color().name(),
                "grid_color": self.grid_color_button.color().name(),
            })
        else:
            candidate = self._resolved_mpl_style_path(self.mpl_style_path_edit.text())
            if candidate and os.path.isfile(candidate):
                style_file = candidate

        self.mpl_preview.render_style(style_dict, style_file=style_file)
    
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
            self._update_mpl_preview()

    def _resolved_mpl_style_path(self, path: str) -> str:
        raw_path = str(path or "").strip()
        if not raw_path:
            return ""
        requested = Path(raw_path).expanduser()
        candidates = [requested]
        if not requested.is_absolute():
            candidates.extend((Path(__file__).resolve().parent / requested, Path(self._styles_path(requested.name))))
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate.resolve())
        return str(requested)
    
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
            mode_text = {
                "theme": "Follow app theme",
                "custom": "Custom overrides",
                "file": "Use .mplstyle file",
            }.get(str(getattr(mpl_config, "mode", "theme")).casefold(), "Follow app theme")
            self.mpl_mode_combo.setCurrentText(mode_text)
            self.mpl_style_path_edit.setText(str(mpl_config.mpl_style_path or ""))
             
            self.grid_enabled_check.setChecked(mpl_config.grid_enabled)
            self.grid_alpha_spin.setValue(mpl_config.grid_alpha)
            self.grid_linewidth_spin.setValue(
                float(getattr(mpl_config, "grid_linewidth", 0.6))
            )
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
            self.figure_color_button.setColor(
                QColor(getattr(mpl_config, "figure_facecolor", "#1E2126"))
            )
            self.axes_facecolor_button.setColor(
                QColor(getattr(mpl_config, "axes_facecolor", "#1E2126"))
            )
            if mpl_config.axes_edgecolor:
                self.axes_color_button.setColor(QColor(mpl_config.axes_edgecolor))
            if mpl_config.text_color:
                self.text_color_button.setColor(QColor(mpl_config.text_color))
            self.grid_color_button.setColor(
                QColor(getattr(mpl_config, "grid_color", "#3A3F44"))
            )
             
            self.color_cycle_editor.set_colors(mpl_config.color_cycle)
            self.line_width_spin.setValue(float(getattr(mpl_config, "line_width", 2.0)))
            self.marker_size_spin.setValue(float(getattr(mpl_config, "marker_size", 5.5)))

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
            self.title_size_spin.setValue(int(getattr(mpl_config, "title_size", 12)))
            self.label_size_spin.setValue(int(getattr(mpl_config, "label_size", 11)))
            self.tick_size_spin.setValue(int(getattr(mpl_config, "tick_size", 10)))
            self.legend_size_spin.setValue(int(getattr(mpl_config, "legend_size", 10)))
            self.figure_dpi_spin.setValue(int(getattr(mpl_config, "figure_dpi", 130)))
            self.savefig_dpi_spin.setValue(int(getattr(mpl_config, "savefig_dpi", 220)))
            self.savefig_transparent_check.setChecked(
                bool(getattr(mpl_config, "savefig_transparent", False))
            )
            
            # Update previews
            self._on_theme_changed(self.theme_combo.currentText())
            self._update_font_preview()
            self._update_theme_preview()
            self._on_mpl_mode_changed(self.mpl_mode_combo.currentText())
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
                'mode': self._matplotlib_mode(),
                'mpl_style_path': self.mpl_style_path_edit.text().strip(),
                'grid_enabled': self.grid_enabled_check.isChecked(),
                'grid_alpha': self.grid_alpha_spin.value(),
                'grid_linestyle': self._get_linestyle_from_description(self.grid_linestyle_combo.currentText()),
                'grid_linewidth': self.grid_linewidth_spin.value(),
                'grid_color': self.grid_color_button.color().name().upper(),
                'figure_facecolor': self.figure_color_button.color().name().upper(),
                'axes_facecolor': self.axes_facecolor_button.color().name().upper(),
                'axes_edgecolor': self.axes_color_button.color().name().upper(),
                'text_color': self.text_color_button.color().name().upper(),
                'color_cycle': self.color_cycle_editor.get_colors(),
                'font_family': mpl_font,
                'font_size': (
                    self.font_size_spin.value()
                    if self.apply_to_matplotlib_check.isChecked()
                    or self.mpl_font_combo.currentText() == "Same as App"
                    else self.mpl_font_size_spin.value()
                ),
                'title_size': self.title_size_spin.value(),
                'label_size': self.label_size_spin.value(),
                'tick_size': self.tick_size_spin.value(),
                'legend_size': self.legend_size_spin.value(),
                'line_width': self.line_width_spin.value(),
                'marker_size': self.marker_size_spin.value(),
                'figure_dpi': self.figure_dpi_spin.value(),
                'savefig_dpi': self.savefig_dpi_spin.value(),
                'savefig_transparent': self.savefig_transparent_check.isChecked(),
            }
        }
    
    def restore_defaults(self):
        """Restore default settings"""
        previous_preview_state = self._mpl_preview_suspended
        self._mpl_preview_suspended = True
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
            self.apply_to_matplotlib_check.setChecked(False)
            self.plot_mode_combo.setCurrentText("Overlay on selected graph")
             
            # Matplotlib
            self.mpl_mode_combo.setCurrentText("Follow app theme")
            self.mpl_style_path_edit.setText(default_config.matplotlib.mpl_style_path)
            self.grid_enabled_check.setChecked(default_config.matplotlib.grid_enabled)
            self.grid_alpha_spin.setValue(default_config.matplotlib.grid_alpha)
            self.grid_linewidth_spin.setValue(default_config.matplotlib.grid_linewidth)
            # Set default grid linestyle
            self.grid_linestyle_combo.setCurrentText("Solid (-)")
             
            # Reset colors to the same defaults used by persisted config.
            self.figure_color_button.setColor(QColor(default_config.matplotlib.figure_facecolor))
            self.axes_facecolor_button.setColor(QColor(default_config.matplotlib.axes_facecolor))
            self.axes_color_button.setColor(QColor(default_config.matplotlib.axes_edgecolor))
            self.text_color_button.setColor(QColor(default_config.matplotlib.text_color))
            self.grid_color_button.setColor(QColor(default_config.matplotlib.grid_color))
            self.color_cycle_editor.set_colors(default_config.matplotlib.color_cycle)
            self.mpl_font_combo.setCurrentText("Auto (Thai)")
            self.mpl_font_size_spin.setValue(default_config.matplotlib.font_size)
            self.title_size_spin.setValue(default_config.matplotlib.title_size)
            self.label_size_spin.setValue(default_config.matplotlib.label_size)
            self.tick_size_spin.setValue(default_config.matplotlib.tick_size)
            self.legend_size_spin.setValue(default_config.matplotlib.legend_size)
            self.line_width_spin.setValue(default_config.matplotlib.line_width)
            self.marker_size_spin.setValue(default_config.matplotlib.marker_size)
            self.figure_dpi_spin.setValue(default_config.matplotlib.figure_dpi)
            self.savefig_dpi_spin.setValue(default_config.matplotlib.savefig_dpi)
            self.savefig_transparent_check.setChecked(
                default_config.matplotlib.savefig_transparent
            )
            
            # Update previews
            self._update_font_preview()
            self._update_theme_preview()
            self._update_mpl_preview()
            
        except Exception as e:
            print(f"Error restoring defaults: {e}")
        finally:
            self._mpl_preview_suspended = previous_preview_state
        if not previous_preview_state:
            self._update_font_preview()
            self._update_theme_preview()
            self._on_mpl_mode_changed(self.mpl_mode_combo.currentText())

    def _validate_settings(self, settings: dict) -> bool:
        theme = settings['appearance']['theme']
        qss_path = settings['appearance']['qt_qss_path']
        if theme == "Custom QSS" and (not qss_path or not os.path.isfile(qss_path)):
            self._set_status(f"QSS file not found: {qss_path}", error=True)
            return False

        mpl_path = settings['matplotlib']['mpl_style_path']
        if settings['matplotlib']['mode'] == "file":
            resolved_path = self._resolved_mpl_style_path(mpl_path)
            if not resolved_path or not os.path.isfile(resolved_path):
                self._set_status(f"Matplotlib style file not found: {mpl_path}", error=True)
                return False
            try:
                import matplotlib
                from matplotlib import style as mpl_style

                with matplotlib.rc_context():
                    mpl_style.use(resolved_path)
            except Exception as exc:
                self._set_status(f"Invalid Matplotlib style file: {exc}", error=True)
                return False
        if not settings['matplotlib']['color_cycle']:
            self._set_status("Color cycle needs at least one color.", error=True)
            return False
        return True

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
                "mode": settings['matplotlib']['mode'],
                "mpl_style_path": settings['matplotlib']['mpl_style_path'],
                "grid_enabled": bool(settings['matplotlib']['grid_enabled']),
                "grid_alpha": float(settings['matplotlib']['grid_alpha']),
                "grid_linestyle": settings['matplotlib']['grid_linestyle'],
                "grid_linewidth": float(settings['matplotlib']['grid_linewidth']),
                "grid_color": settings['matplotlib']['grid_color'],
                "figure_facecolor": settings['matplotlib']['figure_facecolor'],
                "axes_facecolor": settings['matplotlib']['axes_facecolor'],
                "axes_edgecolor": settings['matplotlib']['axes_edgecolor'],
                "text_color": settings['matplotlib']['text_color'],
                "color_cycle": list(settings['matplotlib']['color_cycle']),
                "font_family": settings['matplotlib']['font_family'],
                "font_size": int(settings['matplotlib']['font_size']),
                "title_size": int(settings['matplotlib']['title_size']),
                "label_size": int(settings['matplotlib']['label_size']),
                "tick_size": int(settings['matplotlib']['tick_size']),
                "legend_size": int(settings['matplotlib']['legend_size']),
                "line_width": float(settings['matplotlib']['line_width']),
                "marker_size": float(settings['matplotlib']['marker_size']),
                "figure_dpi": int(settings['matplotlib']['figure_dpi']),
                "savefig_dpi": int(settings['matplotlib']['savefig_dpi']),
                "savefig_transparent": bool(
                    settings['matplotlib']['savefig_transparent']
                ),
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
                "mode": settings['matplotlib']['mode'],
                "mpl_style_path": settings['matplotlib']['mpl_style_path'],
                "grid_enabled": bool(settings['matplotlib']['grid_enabled']),
                "grid_alpha": float(settings['matplotlib']['grid_alpha']),
                "grid_linestyle": settings['matplotlib']['grid_linestyle'],
                "grid_linewidth": float(settings['matplotlib']['grid_linewidth']),
                "grid_color": settings['matplotlib']['grid_color'],
                "figure_facecolor": settings['matplotlib']['figure_facecolor'],
                "axes_facecolor": settings['matplotlib']['axes_facecolor'],
                "axes_edgecolor": settings['matplotlib']['axes_edgecolor'],
                "text_color": settings['matplotlib']['text_color'],
                "color_cycle": list(settings['matplotlib']['color_cycle']),
                "font_family": settings['matplotlib']['font_family'],
                "font_size": int(settings['matplotlib']['font_size']),
                "title_size": int(settings['matplotlib']['title_size']),
                "label_size": int(settings['matplotlib']['label_size']),
                "tick_size": int(settings['matplotlib']['tick_size']),
                "legend_size": int(settings['matplotlib']['legend_size']),
                "line_width": float(settings['matplotlib']['line_width']),
                "marker_size": float(settings['matplotlib']['marker_size']),
                "figure_dpi": int(settings['matplotlib']['figure_dpi']),
                "savefig_dpi": int(settings['matplotlib']['savefig_dpi']),
                "savefig_transparent": bool(
                    settings['matplotlib']['savefig_transparent']
                ),
            }
            baseline = getattr(self, "_apply_baseline", None)
            if isinstance(baseline, dict):
                appearance_changed = new_appearance != baseline.get("appearance", {})
            else:
                appearance_changed = new_appearance != self._current_appearance_dict()
            
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
            
            self.settings_manager.update_matplotlib(**new_matplotlib)
            from styles.theme import apply_mpl_from_config, refresh_matplotlib_canvases

            if not apply_mpl_from_config(
                self.settings_manager.get_matplotlib(),
                app=app,
            ):
                raise RuntimeError("Matplotlib rejected the selected settings")
            refresh_matplotlib_canvases()

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
