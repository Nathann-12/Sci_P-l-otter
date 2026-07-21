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
import matplotlib.colors as mcolors
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
    assert payload["version"] >= 2
    # dataset data is embedded (self-contained), not just a path
    ds = payload["staging"][0]
    assert ds["data"] and ds["data"][0]["y"] == 3.0


def test_project_persists_recipe_hook_and_dataset_provenance(win, tmp_path):
    df = pd.DataFrame({"x": [1.0], "y": [2.0]})
    win._datasets["Result"] = {
        "df": df,
        "path": None,
        "analysis_provenance": {"operation": "welch_t_test", "source_checksum": "sha256:abc"},
    }
    win.serialize_analysis_recipes = lambda: [{"id": "recipe-1", "name": "Welch"}]
    project = tmp_path / "recipes.sciproj"
    session_store.save_project(win, project)

    import json
    payload = json.loads(project.read_text(encoding="utf-8"))
    assert payload["analysis_recipes"][0]["id"] == "recipe-1"
    result_entry = next(item for item in payload["staging"] if item["name"] == "Result")
    assert result_entry["metadata"]["analysis_provenance"]["operation"] == "welch_t_test"


def test_load_project_calls_recipe_restore_hook(win, tmp_path):
    project = tmp_path / "restore-recipes.sciproj"
    project.write_text(
        '{"format":"sciplotter_project","version":2,"staging":[],"tabs":[],"analysis_recipes":[{"id":"r1"}]}',
        encoding="utf-8",
    )
    restored = []
    win.restore_analysis_recipes = lambda recipes: restored.extend(recipes)
    session_store.load_project(win, project)
    assert restored == [{"id": "r1"}]


def test_explicit_project_save_does_not_report_success_after_write_failure(
    win, tmp_path, monkeypatch
):
    def fail_write(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(session_store, "_atomic_write_json", fail_write)
    with pytest.raises(OSError, match="disk full"):
        session_store.save_project(win, tmp_path / "cannot-save.sciproj")


def test_explicit_project_load_rejects_corrupt_and_future_files(win, tmp_path):
    corrupt = tmp_path / "corrupt.sciproj"
    corrupt.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid session/project file"):
        session_store.load_project(win, corrupt)

    future = tmp_path / "future.sciproj"
    future.write_text(
        '{"format":"sciplotter_project","version":999,"staging":[],"tabs":[]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unsupported project schema version"):
        session_store.load_project(win, future)


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


def test_project_round_trip_restores_full_supported_graph_appearance(win, tmp_path):
    from core.plot_style import apply_line_style, apply_style

    df = pd.DataFrame({"t": [1.0, 2.0, 4.0], "y": [2.0, 5.0, 3.0]})
    win._stage_insert("appearance.csv", df, None)
    win.plot_from_workbook("line")
    tab = win.tabs.currentWidget()
    ax = tab.get_axes()
    line = next(line for line in ax.lines if not str(line.get_gid() or "").startswith("_ps_"))
    apply_line_style(line, {
        "color": "#d81b60", "linewidth": 3.25, "marker": "s",
        "glow": True, "glow_color": "#ffc107", "glow_width": 6.0,
        "shadow": True, "fill": "under", "fill_color": "#4f9cf9",
        "fill_alpha": 0.22, "errorbar_mode": "constant",
        "errorbar_value": 0.25,
    })
    apply_style(ax, {
        "effects": {"axes_shadow": True, "shadow_color": "#101820",
                    "shadow_alpha": 0.3, "shadow_offset_x": 3.0,
                    "shadow_offset_y": 4.0},
        "tick_labels": {"enabled": True, "axis": "x", "notation": "decimal",
                        "decimals_enabled": True, "decimals": 1,
                        "divide_by": 1.0, "formula": "", "prefix": "t=",
                        "suffix": "s", "plus_sign": False, "minus_sign": True,
                        "thousands": False},
        "axes": {"refline_h": 4.0, "refline_v": None,
                 "refline_h_label": "threshold", "refline_v_label": "",
                 "refline_color": "#00897b", "refline_style": "--",
                 "refline_width": 1.5, "refline_alpha": 0.9},
    }, tab.get_figure())
    ax.set_title("ผลการทดลอง", loc="left", color="#7b1fa2", fontsize=16)
    ax.set_xscale("log")
    ax.set_xlim(1.0, 4.0)

    project = tmp_path / "appearance.sciproj"
    session_store.save_project(win, project)

    import json
    payload = json.loads(project.read_text(encoding="utf-8"))
    saved_format = next(item["graph_format"] for item in payload["tabs"]
                        if item.get("graph_format"))
    assert saved_format["persistent_version"] == 2

    import main as app_main
    restored = app_main.MainWindow()
    try:
        session_store.load_project(restored, project)
        restored_tab = next(
            restored.tabs.widget(index) for index in range(restored.tabs.count())
            if restored.tabs.widget(index).layers
        )
        restored_ax = restored_tab.get_axes()
        restored_line = next(
            item for item in restored_ax.lines
            if not str(item.get_gid() or "").startswith("_ps_")
        )
        assert mcolors.to_hex(restored_line.get_color()) == "#d81b60"
        assert restored_line.get_linewidth() == pytest.approx(3.25)
        assert restored_line.get_marker() == "s"
        assert getattr(restored_line, "_ps_effects")["glow"] is True
        assert getattr(restored_line, "_ps_deco")["fill"] == "under"
        assert getattr(restored_ax, "_ps_tick_label_cfg")["prefix"] == "t="
        assert getattr(restored_ax, "_ps_refline_cfg")["refline_h"] == 4.0
        assert any(item.get_gid() == "_ps_refline_h" for item in restored_ax.lines)
        assert restored_ax.get_title(loc="left") == "ผลการทดลอง"
        assert restored_ax._left_title.get_fontsize() == pytest.approx(16)
        assert restored_ax.get_xscale() == "log"
        assert restored_ax.get_xlim() == pytest.approx((1.0, 4.0))
    finally:
        restored.close()


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


def test_second_graph_text_restore_recovers_colorbar_text_without_resetting_fonts():
    from matplotlib.figure import Figure

    fig = Figure()
    ax = fig.add_subplot(111)
    image = ax.imshow([[0.0, 1.0], [2.0, 3.0]])
    colorbar = fig.colorbar(image, ax=ax)
    ax.set_title("Result", fontsize=17)
    colorbar.set_label("Edited scale")
    colorbar.ax.set_title("Intensity")

    class _Widget:
        def get_figure(self):
            return fig

    widget = _Widget()
    state = session_store._serialize_graph_text(widget)
    colorbar.set_label("")
    colorbar.ax.set_title("")
    before_size = ax.title.get_fontsize()

    session_store._restore_graph_text(widget, state, preserve_style=True)

    assert colorbar.ax.get_ylabel() == "Edited scale"
    assert colorbar.ax.get_title() == "Intensity"
    assert ax.title.get_fontsize() == pytest.approx(before_size)
