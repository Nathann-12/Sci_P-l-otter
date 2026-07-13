"""
Settings management for SciPlotter
Handles configuration loading, saving, and application
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import logging
import re

logger = logging.getLogger(__name__)


_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _hex_color(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text.upper() if _HEX_COLOR_RE.fullmatch(text) else fallback.upper()


def _bounded_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def _bounded_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))

@dataclass
class AppearanceConfig:
    """Appearance settings for Qt UI"""
    # qt_qss_path is retained for custom themes and migration from older
    # configs. Built-in themes are selected explicitly with theme_mode.
    theme_mode: str = "dark"
    accent_color: str = "#4F9CF9"
    background_color: str = ""  # empty = use the selected theme's default
    qt_qss_path: str = ""
    font_family: str = "Segoe UI"
    font_size: int = 10

@dataclass
class MatplotlibConfig:
    """Matplotlib style and plot settings"""
    mode: str = "theme"  # theme, custom, or file
    mpl_style_path: str = ""
    font_family: str = ""  # empty = Auto (Thai-capable)
    font_size: int = 10
    title_size: int = 12
    label_size: int = 11
    tick_size: int = 10
    legend_size: int = 10
    grid_enabled: bool = True
    grid_alpha: float = 0.25
    grid_linestyle: str = "-"
    grid_linewidth: float = 0.6
    grid_color: str = "#3A3F44"
    figure_facecolor: str = "#1E2126"
    axes_facecolor: str = "#1E2126"
    axes_edgecolor: str = "#3b3f46"
    text_color: str = "#d7d7d7"
    line_width: float = 2.0
    marker_size: float = 5.5
    figure_dpi: int = 130
    savefig_dpi: int = 220
    savefig_transparent: bool = False
    color_cycle: List[str] = None

    def __post_init__(self):
        if self.color_cycle is None:
            self.color_cycle = [
                "#4F9CF9", "#FFB020", "#6EE7B7", "#F472B6",
                "#A78BFA", "#F87171", "#22D3EE", "#94A3B8"
            ]
        self.normalize()

    def normalize(self) -> None:
        mode_aliases = {
            "follow app theme": "theme",
            "use .mplstyle file": "file",
            "custom overrides": "custom",
        }
        mode = str(self.mode or "theme").strip().casefold()
        self.mode = mode_aliases.get(mode, mode if mode in {"theme", "custom", "file"} else "theme")
        self.mpl_style_path = str(self.mpl_style_path or "").strip()
        self.font_family = str(self.font_family or "").strip()
        self.font_size = _bounded_int(self.font_size, 10, 6, 40)
        self.title_size = _bounded_int(self.title_size, 12, 6, 48)
        self.label_size = _bounded_int(self.label_size, 11, 6, 40)
        self.tick_size = _bounded_int(self.tick_size, 10, 6, 32)
        self.legend_size = _bounded_int(self.legend_size, 10, 6, 32)
        self.grid_enabled = bool(self.grid_enabled)
        self.grid_alpha = _bounded_float(self.grid_alpha, 0.25, 0.0, 1.0)
        linestyle = str(self.grid_linestyle or "-").strip()
        self.grid_linestyle = linestyle if linestyle in {"-", "--", ":", "-."} else "-"
        self.grid_linewidth = _bounded_float(self.grid_linewidth, 0.6, 0.1, 5.0)
        self.grid_color = _hex_color(self.grid_color, "#3A3F44")
        self.figure_facecolor = _hex_color(self.figure_facecolor, "#1E2126")
        self.axes_facecolor = _hex_color(self.axes_facecolor, "#1E2126")
        self.axes_edgecolor = _hex_color(self.axes_edgecolor, "#3B3F46")
        self.text_color = _hex_color(self.text_color, "#D7D7D7")
        self.line_width = _bounded_float(self.line_width, 2.0, 0.1, 10.0)
        self.marker_size = _bounded_float(self.marker_size, 5.5, 0.0, 30.0)
        self.figure_dpi = _bounded_int(self.figure_dpi, 130, 50, 600)
        self.savefig_dpi = _bounded_int(self.savefig_dpi, 220, 72, 1200)
        self.savefig_transparent = bool(self.savefig_transparent)
        colors = [
            _hex_color(color, "")
            for color in (self.color_cycle or [])
            if _HEX_COLOR_RE.fullmatch(str(color or "").strip())
        ]
        self.color_cycle = colors or [
            "#4F9CF9", "#FFB020", "#6EE7B7", "#F472B6",
            "#A78BFA", "#F87171", "#22D3EE", "#94A3B8",
        ]

@dataclass
class AIConfig:
    """Local AI assistant settings (Ollama-backed)."""
    enabled: bool = True
    # Lightest broadly-capable tool router. Swap for a stronger local model
    # (e.g. qwen2.5:7b) on machines with a GPU for more reliable tool use.
    model: str = "gemma2:2b"
    base_url: str = "http://127.0.0.1:11434"

@dataclass
class AppConfig:
    """Main application configuration"""
    appearance: AppearanceConfig = None
    matplotlib: MatplotlibConfig = None
    ai: AIConfig = None

    def __post_init__(self):
        if self.appearance is None:
            self.appearance = AppearanceConfig()
        if self.matplotlib is None:
            self.matplotlib = MatplotlibConfig()
        if self.ai is None:
            self.ai = AIConfig()

class SettingsManager:
    """Manages application settings loading, saving, and application"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = AppConfig()
        self._load()
    
    def _load(self) -> None:
        """Load configuration from file or create default"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._load_from_dict(data)
                    logger.info(f"Configuration loaded from {self.config_path}")
            else:
                logger.info("No config file found, using defaults")
                self._create_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self._create_default_config()
    
    def _load_from_dict(self, data: Dict[str, Any]) -> None:
        """Load configuration from dictionary"""
        try:
            # Load appearance
            if 'appearance' in data:
                app_data = data['appearance']
                qss_path = app_data.get('qt_qss_path', self.config.appearance.qt_qss_path)
                self.config.appearance.qt_qss_path = qss_path
                theme_mode = str(app_data.get('theme_mode', '')).strip().lower()
                if theme_mode not in {'dark', 'light', 'custom'}:
                    qss_name = Path(qss_path or '').name.lower()
                    if qss_name == 'light.qss':
                        theme_mode = 'light'
                    elif qss_path and qss_name not in {'dark.qss', 'dark_modern.qss', 'qdark.qss'}:
                        theme_mode = 'custom'
                    else:
                        theme_mode = 'dark'
                self.config.appearance.theme_mode = theme_mode
                accent = str(app_data.get('accent_color', self.config.appearance.accent_color)).strip()
                if len(accent) == 7 and accent.startswith('#'):
                    try:
                        int(accent[1:], 16)
                        self.config.appearance.accent_color = accent.upper()
                    except ValueError:
                        pass
                background = str(app_data.get('background_color', '')).strip()
                if background:
                    if len(background) == 7 and background.startswith('#'):
                        try:
                            int(background[1:], 16)
                            self.config.appearance.background_color = background.upper()
                        except ValueError:
                            pass
                self.config.appearance.font_family = app_data.get('font_family', self.config.appearance.font_family)
                self.config.appearance.font_size = app_data.get('font_size', self.config.appearance.font_size)
            
            # Load matplotlib
            if 'matplotlib' in data:
                mpl_data = dict(data['matplotlib'])
                style_path = str(mpl_data.get('mpl_style_path', '') or '')
                if not str(mpl_data.get('mode', '') or '').strip():
                    built_in_styles = {
                        'mpl_style_dark.mplstyle',
                        'mpl_style_dark_pro.mplstyle',
                        'mpl_style_light.mplstyle',
                    }
                    if Path(style_path).name.casefold() in built_in_styles:
                        mpl_data['mode'] = 'theme'
                    else:
                        mpl_data['mode'] = 'file' if style_path else 'custom'
                for key in vars(self.config.matplotlib):
                    if key in mpl_data:
                        setattr(self.config.matplotlib, key, mpl_data[key])
                self.config.matplotlib.normalize()

            # Load AI assistant settings
            if 'ai' in data and isinstance(data['ai'], dict):
                ai_data = data['ai']
                self.config.ai.enabled = bool(ai_data.get('enabled', self.config.ai.enabled))
                self.config.ai.model = str(ai_data.get('model', self.config.ai.model) or self.config.ai.model)
                self.config.ai.base_url = str(ai_data.get('base_url', self.config.ai.base_url) or self.config.ai.base_url)
        except Exception as e:
            logger.error(f"Error parsing config data: {e}")
            self._create_default_config()
    
    def _create_default_config(self) -> None:
        """Create default configuration"""
        self.config = AppConfig()
        self.save()
    
    def save(self) -> None:
        """Save configuration to file"""
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to dict and save
            config_dict = asdict(self.config)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get_appearance(self) -> AppearanceConfig:
        """Get appearance configuration"""
        return self.config.appearance
    
    def get_matplotlib(self) -> MatplotlibConfig:
        """Get matplotlib configuration"""
        return self.config.matplotlib

    def get_ai(self) -> AIConfig:
        """Get AI assistant configuration"""
        return self.config.ai
    
    def update_appearance(self, **kwargs) -> None:
        """Update appearance configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.appearance, key):
                setattr(self.config.appearance, key, value)
    
    def update_matplotlib(self, **kwargs) -> None:
        """Update matplotlib configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.matplotlib, key):
                setattr(self.config.matplotlib, key, value)
        self.config.matplotlib.normalize()
    
    def validate_paths(self) -> Dict[str, bool]:
        """Validate that all configured paths exist"""
        paths = {
            'qss': self.config.appearance.qt_qss_path,
            'mpl_style': self.config.matplotlib.mpl_style_path
        }
        
        results = {}
        for name, path in paths.items():
            full_path = Path(path)
            results[name] = full_path.exists()
            if not results[name]:
                logger.warning(f"Path not found: {path}")
        
        return results
    
    def get_default_config(self) -> AppConfig:
        """Get a copy of default configuration"""
        return AppConfig()

# Global settings manager instance
settings_manager = SettingsManager()
