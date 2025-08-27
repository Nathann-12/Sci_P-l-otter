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

logger = logging.getLogger(__name__)

@dataclass
class AppearanceConfig:
    """Appearance settings for Qt UI"""
    qt_qss_path: str = "styles/qdark.qss"
    font_family: str = "Segoe UI"
    font_size: int = 10

@dataclass
class MatplotlibConfig:
    """Matplotlib style and plot settings"""
    mpl_style_path: str = "styles/mpl_style_dark_pro.mplstyle"
    grid_enabled: bool = True
    grid_alpha: float = 0.25
    grid_linestyle: str = "-"
    axes_edgecolor: str = "#3b3f46"
    text_color: str = "#d7d7d7"
    color_cycle: List[str] = None

    def __post_init__(self):
        if self.color_cycle is None:
            self.color_cycle = [
                "#4F9CF9", "#FFB020", "#6EE7B7", "#F472B6",
                "#A78BFA", "#F87171", "#22D3EE", "#94A3B8"
            ]

@dataclass
class AppConfig:
    """Main application configuration"""
    appearance: AppearanceConfig = None
    matplotlib: MatplotlibConfig = None

    def __post_init__(self):
        if self.appearance is None:
            self.appearance = AppearanceConfig()
        if self.matplotlib is None:
            self.matplotlib = MatplotlibConfig()

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
                self.config.appearance.qt_qss_path = app_data.get('qt_qss_path', self.config.appearance.qt_qss_path)
                self.config.appearance.font_family = app_data.get('font_family', self.config.appearance.font_family)
                self.config.appearance.font_size = app_data.get('font_size', self.config.appearance.font_size)
            
            # Load matplotlib
            if 'matplotlib' in data:
                mpl_data = data['matplotlib']
                self.config.matplotlib.mpl_style_path = mpl_data.get('mpl_style_path', self.config.matplotlib.mpl_style_path)
                self.config.matplotlib.grid_enabled = mpl_data.get('grid_enabled', self.config.matplotlib.grid_enabled)
                self.config.matplotlib.grid_alpha = mpl_data.get('grid_alpha', self.config.matplotlib.grid_alpha)
                self.config.matplotlib.grid_linestyle = mpl_data.get('grid_linestyle', self.config.matplotlib.grid_linestyle)
                self.config.matplotlib.axes_edgecolor = mpl_data.get('axes_edgecolor', self.config.matplotlib.axes_edgecolor)
                self.config.matplotlib.text_color = mpl_data.get('text_color', self.config.matplotlib.text_color)
                self.config.matplotlib.color_cycle = mpl_data.get('color_cycle', self.config.matplotlib.color_cycle)
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
