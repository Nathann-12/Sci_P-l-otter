"""Tests for the .sciproj file association helper + opening a project by path
(the double-click / command-line entry point)."""
from __future__ import annotations

import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pytest

from core import file_assoc


def test_launch_command_quotes_interpreter_and_main_with_arg():
    cmd = file_assoc.launch_command()
    assert '"%1"' in cmd
    assert "main.py" in cmd
    # interpreter path is quoted
    assert cmd.startswith('"')


@pytest.mark.skipif(not file_assoc.is_windows(), reason="Windows-only registry")
def test_register_is_registered_unregister_roundtrip():
    was = file_assoc.is_registered()
    try:
        ok, msg = file_assoc.register()
        assert ok, msg
        assert file_assoc.is_registered() is True
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            rf"Software\Classes\{file_assoc.PROG_ID}\shell\open\command") as k:
            val, _ = winreg.QueryValueEx(k, "")
        assert "main.py" in val and val.endswith('"%1"')
    finally:
        if not was:
            ok, _ = file_assoc.unregister()
            assert ok
            assert file_assoc.is_registered() is False


def test_non_windows_register_is_polite(monkeypatch):
    monkeypatch.setattr(file_assoc, "is_windows", lambda: False)
    ok, msg = file_assoc.register()
    assert ok is False
    assert "Windows" in msg


# ---------------- open project by path (double-click entry) ----------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    yield w
    w.close()


def test_open_project_path_loads_file(win, tmp_path):
    from core import session as session_store
    win._stage_insert("d.csv [ตาราง]", pd.DataFrame({"t": [0, 1], "y": [2.0, 3.0]}), None)
    proj = tmp_path / "assoc.sciproj"
    session_store.save_project(win, str(proj))

    import main as app_main
    w2 = app_main.MainWindow()
    try:
        assert w2.open_project_path(str(proj)) is True
        assert any("d.csv" in n for n in w2._datasets)
    finally:
        w2.close()


def test_open_project_path_missing_file_returns_false(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    assert win.open_project_path("C:/nope/none.sciproj") is False
