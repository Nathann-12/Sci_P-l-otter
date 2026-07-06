"""Project file (*.sciproj) save/open — self-contained data + graphs, and the
removal of the startup restore prompt."""
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

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from core import session as session_store


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    yield w
    w.close()


def test_save_project_embeds_dataset_data(win, tmp_path):
    df = pd.DataFrame({"t": [0.0, 1.0, 2.0], "y": [3.0, 4.0, 5.0]})
    win._stage_insert("data.csv [ตาราง]", df, None)  # typed/loaded data, no real path

    proj = tmp_path / "p.sciproj"
    session_store.save_project(win, str(proj))
    assert proj.exists()

    import json
    payload = json.loads(proj.read_text(encoding="utf-8"))
    assert payload["format"] == "sciplotter_project"
    # dataset data is embedded (self-contained), not just a path
    ds = payload["staging"][0]
    assert ds["data"] and ds["data"][0]["y"] == 3.0


def test_open_project_restores_data_and_graph(win, tmp_path):
    df = pd.DataFrame({"t": [0.0, 1.0, 2.0, 3.0], "y": [1.0, 2.0, 3.0, 4.0]})
    win._stage_insert("src.csv [ตาราง]", df, None)
    win.plot_from_workbook("line")
    graphs = sum(1 for _k, _t in win.mdi._graph_subs.items())

    proj = tmp_path / "q.sciproj"
    session_store.save_project(win, str(proj))

    # fresh window → open the project
    import main as app_main
    w2 = app_main.MainWindow()
    try:
        session_store.load_project(w2, str(proj))
        # dataset restored from embedded data (path was None → still present)
        assert any("src.csv" in name for name in w2._datasets)
        restored = next(v["df"] for k, v in w2._datasets.items() if "src.csv" in k)
        assert restored["y"].tolist() == [1.0, 2.0, 3.0, 4.0]
        # at least one graph restored
        assert sum(1 for _ in w2.mdi._graph_subs) >= 1
    finally:
        w2.close()


def test_no_restore_prompt_on_startup(win, monkeypatch):
    # the old QMessageBox.question restore prompt must be gone
    from PySide6.QtWidgets import QMessageBox
    called = {"q": False}
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: called.__setitem__("q", True) or QMessageBox.No))
    win._prompt_restore_session()
    assert called["q"] is False


def test_save_project_action_wired(win):
    assert callable(getattr(win, "save_project_as", None))
    assert callable(getattr(win, "open_project", None))
    titles = []
    for a in win.menuBar().actions():
        if a.menu() and a.text().replace("&", "") == "File":
            titles = [x.text().replace("&", "") for x in a.menu().actions()]
    assert any("Save Project" in t for t in titles)
    assert any("Open Project" in t for t in titles)
