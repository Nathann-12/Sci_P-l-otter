from __future__ import annotations

import json
import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QWidget,
)

from dialogs_settings import SettingsDialog
from settings import SettingsManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _manager(tmp_path):
    return SettingsManager(str(tmp_path / "config.json"))


def test_settings_dialog_opens_compact_and_defaults_to_dark(qapp, tmp_path):
    manager = _manager(tmp_path)
    manager.update_appearance(qt_qss_path="")
    dialog = SettingsDialog(manager)

    assert dialog.width() <= 920
    assert dialog.height() <= 640
    assert dialog.minimumWidth() <= 720
    assert dialog.theme_combo.currentText() == "Built-in Dark"
    assert dialog.qss_path_edit.isEnabled() is False
    assert dialog.accent_preset_combo.count() >= 7
    assert dialog.accent_color_button.color().name().upper() == "#4F9CF9"
    assert dialog.background_preset_combo.currentText() == "Theme Default"
    assert dialog.collect()["appearance"]["background_color"] == ""


def test_opening_settings_does_not_reset_application_font(qapp, tmp_path):
    manager = _manager(tmp_path)
    selected_font = qapp.font().family()
    qapp.setFont(QFont(selected_font, 15))

    dialog = SettingsDialog(manager)

    assert qapp.font().family() == selected_font
    assert qapp.font().pointSize() == 15
    dialog.close()


def test_settings_collect_has_real_theme_and_matplotlib_font_values(qapp, tmp_path):
    manager = _manager(tmp_path)
    dialog = SettingsDialog(manager)

    dialog.theme_combo.setCurrentText("Built-in Light")
    app_font = dialog.font_family_combo.currentText()
    dialog.apply_to_matplotlib_check.setChecked(True)

    settings = dialog.collect()

    assert settings["appearance"]["theme_mode"] == "light"
    assert settings["appearance"]["qt_qss_path"] == ""
    assert settings["appearance"]["accent_color"] == "#4F9CF9"
    assert settings["appearance"]["background_color"] == ""
    assert settings["matplotlib"]["font_family"] == app_font
    assert settings["matplotlib"]["font_size"] == dialog.font_size_spin.value()


def test_accent_presets_and_custom_color_are_collected(qapp, tmp_path):
    dialog = SettingsDialog(_manager(tmp_path))

    dialog.accent_preset_combo.setCurrentText("Ocean Teal")
    assert dialog.collect()["appearance"]["accent_color"] == "#20B8A6"

    dialog.accent_color_button.setColor(QColor("#B14DFF"))
    assert dialog.accent_preset_combo.currentText() == "Custom..."
    assert dialog.collect()["appearance"]["accent_color"] == "#B14DFF"


def test_background_presets_and_any_custom_color_are_collected(qapp, tmp_path):
    dialog = SettingsDialog(_manager(tmp_path))

    dialog.background_preset_combo.setCurrentText("Warm Paper")
    assert dialog.collect()["appearance"]["background_color"] == "#F4EFE6"

    dialog.background_color_button.setColor(QColor("#D7F2E3"))
    assert dialog.background_preset_combo.currentText() == "Custom..."
    assert dialog.collect()["appearance"]["background_color"] == "#D7F2E3"

    dialog.background_preset_combo.setCurrentText("Theme Default")
    assert dialog.collect()["appearance"]["background_color"] == ""
    assert dialog.background_hex_label.text() == "Auto"


def test_settings_apply_rejects_missing_custom_qss(qapp, tmp_path):
    manager = _manager(tmp_path)
    dialog = SettingsDialog(manager)

    dialog.theme_combo.setCurrentText("Custom QSS")
    dialog.qss_path_edit.setText(str(tmp_path / "missing.qss"))

    assert dialog.apply_settings() is False
    assert "QSS file not found" in dialog.status_label.text()


def test_settings_apply_updates_runtime_plot_mode(qapp, tmp_path, monkeypatch):
    class Host(QWidget):
        def __init__(self):
            super().__init__()
            self.plot_mode = None
            self.refreshed = 0

        def refresh_all_canvases(self):
            self.refreshed += 1

    manager = _manager(tmp_path)
    host = Host()
    dialog = SettingsDialog(manager, host)
    qsettings = QSettings("SciPlotter", "SciPlotter")
    qsettings.remove("plot/mode")
    calls = []

    import styles.theme as theme_module

    monkeypatch.setattr(theme_module, "apply_theme_from_config", lambda *_args, **_kwargs: calls.append("appearance"))
    monkeypatch.setattr(theme_module, "apply_mpl_style", lambda *_args, **_kwargs: calls.append("mpl_style"))
    monkeypatch.setattr(theme_module, "apply_mpl_overrides", lambda *_args, **_kwargs: calls.append("mpl_overrides"))

    dialog.plot_mode_combo.setCurrentText("Replace selected graph")
    appearance = manager.get_appearance()
    qapp.setProperty("sciplotterThemeMode", appearance.theme_mode)
    qapp.setProperty("sciplotterAccentColor", appearance.accent_color)
    qapp.setProperty("sciplotterBackgroundColor", appearance.background_color)
    qapp.setFont(QFont(dialog.font_family_combo.currentText(), appearance.font_size))

    assert dialog.apply_settings() is True
    assert str(qsettings.value("plot/mode")).endswith("replace")
    assert str(host.plot_mode).lower().endswith("replace")
    assert calls == []


def test_apply_updates_existing_and_future_popups(qapp, tmp_path):
    manager = _manager(tmp_path)
    dialog = SettingsDialog(manager)
    existing_popup = QDialog()
    existing_label = QLabel("Existing", existing_popup)
    existing_label.setStyleSheet(
        "background:#1e2126;color:#e6e6e6;border:1px solid #4F9CF9;"
    )
    existing_popup.show()
    qapp.processEvents()

    dialog.theme_combo.setCurrentText("Built-in Light")
    dialog.accent_preset_combo.setCurrentText("Ocean Teal")
    dialog.font_size_spin.setValue(13)

    assert dialog.apply_settings() is True
    qapp.processEvents()

    assert qapp.property("sciplotterThemeMode") == "light"
    assert qapp.property("sciplotterAccentColor") == "#20B8A6"
    assert qapp.palette().color(QPalette.Highlight).name().upper() == "#20B8A6"
    assert qapp.palette().color(QPalette.Window).lightness() > 200
    assert qapp.font().pointSize() == 13
    assert "#20B8A6" in existing_label.styleSheet()
    assert "#F4F6F8" in existing_label.styleSheet()
    assert existing_label.font().pointSize() == 13

    future_popup = QDialog()
    future_popup.setStyleSheet(
        "background:#1e2126;color:#e6e6e6;border:1px solid #4F9CF9;"
    )
    future_popup.show()
    qapp.processEvents()

    assert "#20B8A6" in future_popup.styleSheet()
    assert "#F4F6F8" in future_popup.styleSheet()
    assert future_popup.font().pointSize() == 13
    future_popup.close()
    existing_popup.close()


def test_standard_popup_families_inherit_active_theme(qapp, tmp_path):
    manager = _manager(tmp_path)
    dialog = SettingsDialog(manager)
    dialog.theme_combo.setCurrentText("Built-in Dark")
    dialog.accent_color_button.setColor(QColor("#D768D7"))
    dialog.font_size_spin.setValue(12)
    assert dialog.apply_settings() is True

    menu = QMenu("Menu")
    menu.addAction("Action")
    message = QMessageBox(QMessageBox.Information, "Title", "Message")
    file_dialog = QFileDialog()
    file_dialog.setOption(QFileDialog.DontUseNativeDialog, True)
    color_dialog = QColorDialog()
    color_dialog.setOption(QColorDialog.DontUseNativeDialog, True)
    popups = [menu, message, file_dialog, color_dialog]

    for popup in popups:
        popup.show()
    qapp.processEvents()

    for popup in popups:
        assert popup.palette().color(QPalette.Highlight).name().upper() == "#D768D7"
        assert popup.font().pointSize() == 12
        assert popup.palette().color(QPalette.Window).lightness() < 80
        popup.close()


def test_custom_background_auto_selects_contrast_for_whole_app(qapp, tmp_path):
    dialog = SettingsDialog(_manager(tmp_path))
    dialog.theme_combo.setCurrentText("Built-in Dark")
    dialog.background_color_button.setColor(QColor("#F7E7CE"))
    dialog.accent_color_button.setColor(QColor("#B14DFF"))

    assert dialog.apply_settings() is True
    qapp.processEvents()

    assert qapp.property("sciplotterThemeMode") == "dark"
    assert qapp.property("sciplotterEffectiveThemeMode") == "light"
    assert qapp.property("sciplotterBackgroundColor") == "#F7E7CE"
    assert qapp.palette().color(QPalette.Window).name().upper() == "#F7E7CE"
    assert qapp.palette().color(QPalette.WindowText).lightness() < 80
    assert qapp.property("sciplotterIconNormalColor") == "#344252"


def test_theme_and_accent_persist_across_manager_reload(qapp, tmp_path):
    config_path = tmp_path / "config.json"
    manager = SettingsManager(str(config_path))
    manager.update_appearance(
        theme_mode="light",
        accent_color="#20B8A6",
        background_color="#EEF3F7",
        font_family="Arial",
        font_size=12,
    )
    manager.save()

    reloaded = SettingsManager(str(config_path)).get_appearance()

    assert reloaded.theme_mode == "light"
    assert reloaded.accent_color == "#20B8A6"
    assert reloaded.background_color == "#EEF3F7"
    assert reloaded.font_family == "Arial"
    assert reloaded.font_size == 12


def test_legacy_light_qss_config_migrates_to_theme_mode(qapp, tmp_path):
    config_path = tmp_path / "legacy.json"
    config_path.write_text(
        json.dumps({"appearance": {"qt_qss_path": "styles/light.qss"}}),
        encoding="utf-8",
    )

    appearance = SettingsManager(str(config_path)).get_appearance()

    assert appearance.theme_mode == "light"
    assert appearance.accent_color == "#4F9CF9"
