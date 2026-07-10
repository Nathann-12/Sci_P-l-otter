from __future__ import annotations

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
from PySide6.QtWidgets import QApplication, QWidget

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


def test_settings_collect_has_real_theme_and_matplotlib_font_values(qapp, tmp_path):
    manager = _manager(tmp_path)
    dialog = SettingsDialog(manager)

    dialog.theme_combo.setCurrentText("Built-in Light")
    app_font = dialog.font_family_combo.currentText()
    dialog.apply_to_matplotlib_check.setChecked(True)

    settings = dialog.collect()

    assert settings["appearance"]["qt_qss_path"].endswith("styles\\light.qss") or settings["appearance"]["qt_qss_path"].endswith("styles/light.qss")
    assert settings["matplotlib"]["font_family"] == app_font


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

    monkeypatch.setattr(theme_module, "apply_qss", lambda *_args, **_kwargs: calls.append("qss"))
    monkeypatch.setattr(theme_module, "apply_font", lambda *_args, **_kwargs: calls.append("font"))
    monkeypatch.setattr(theme_module, "apply_mpl_style", lambda *_args, **_kwargs: calls.append("mpl_style"))
    monkeypatch.setattr(theme_module, "apply_mpl_overrides", lambda *_args, **_kwargs: calls.append("mpl_overrides"))

    dialog.plot_mode_combo.setCurrentText("Replace selected graph")

    assert dialog.apply_settings() is True
    assert str(qsettings.value("plot/mode")).endswith("replace")
    assert str(host.plot_mode).lower().endswith("replace")
    assert calls == []
