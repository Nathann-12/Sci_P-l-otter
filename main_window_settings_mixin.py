from __future__ import annotations

import os
import json
import logging

from PySide6.QtWidgets import QApplication, QMessageBox

from settings import settings_manager
from dialogs_settings import SettingsDialog

logger = logging.getLogger(__name__)


class MainWindowSettingsMixin:
    """Config persistence and the Settings dialog wiring extracted from MainWindow."""

    def _get_config_path(self):
        """Get path to configuration file"""
        import os
        # Try project root first, then user home
        project_root = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(project_root, ".sciplotter_config.json")
        if not os.path.exists(config_path):
            config_path = os.path.join(os.path.expanduser("~"), ".sciplotter_config.json")
        return config_path

    def _load_plot_style_config(self):
        """Load plot style preference from config file"""
        try:
            config_path = self._get_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    style = config.get('plot_style', 'dark')
                    self.change_plot_style(style, save_config=False)
            else:
                # No config file, default to dark style
                self.change_plot_style('dark', save_config=False)
        except Exception:
            # Use default if loading fails
            self.change_plot_style('dark', save_config=False)

    def _save_plot_style_config(self, style):
        """Save plot style preference to config file"""
        try:
            config_path = self._get_config_path()
            config = {'plot_style': style}
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass  # Ignore save errors

    def _load_and_apply_settings(self):
        """Load and apply settings from configuration"""
        try:
            # Apply Qt theme from config
            from styles.theme import apply_theme_from_config
            app_config = settings_manager.get_appearance()
            apply_theme_from_config(QApplication.instance(), app_config)

            # Apply matplotlib settings from config
            from styles.theme import apply_mpl_from_config
            mpl_config = settings_manager.get_matplotlib()
            apply_mpl_from_config(mpl_config)

            logger.info("Settings loaded and applied successfully")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")

    def show_settings(self):
        """Show settings dialog"""
        try:
            dialog = SettingsDialog(settings_manager, self)
            dialog.settingsApplied.connect(self._on_settings_applied)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open settings: {str(e)}")

    def _on_settings_applied(self):
        """Handle settings applied signal"""
        try:
            # Refresh all canvases to apply new settings
            self.refresh_all_canvases()
            logger.info("Settings applied and canvases refreshed")
        except Exception as e:
            logger.error(f"Error applying settings: {e}")
