"""Focused behavior tests for per-GraphTab graph-format undo/redo."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.colors as mcolors
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QUndoStack
from PySide6.QtWidgets import QApplication

from core.graph_format_history import (
    capture_graph_format_state,
    restore_graph_format_state,
)
from core.plot_style import apply_style
from widgets.plot_tabs import GraphTab
from main_window_plotstyle_mixin import MainWindowPlotStyleMixin


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def graph(qapp):
    tab = GraphTab("history")
    ax = tab.get_axes()
    line, = ax.plot([0.0, 1.0, 2.0], [1.0, 3.0, 2.0], label="Signal")
    layer_id = tab.register_layer(
        [line], "Signal", "line",
        meta={"label": "Signal", "style_kwargs": {"color": "#1f77b4"}},
        kwargs={"color": "#1f77b4", "linewidth": 1.5},
    )
    ax.legend(title="Series")
    tab.draw()
    tab.graph_format_history.clear()
    yield tab, ax, line, layer_id
    tab.close()


def _hex(value):
    return mcolors.to_hex(value, keep_alpha=False)


def test_graph_tab_owns_bounded_qt_undo_stack(graph):
    tab, _ax, _line, _layer_id = graph

    assert isinstance(tab.graph_undo_stack, QUndoStack)
    assert tab.graph_undo_stack.undoLimit() == 30
    assert tab.graph_format_history.stack is tab.graph_undo_stack


def test_already_applied_transaction_undoes_and_redoes_without_double_apply(graph):
    tab, ax, _line, _layer_id = graph
    initial_xlim = ax.get_xlim()

    with tab.graph_format_transaction("Edit graph titles"):
        ax.set_title("After")
        ax.set_title("Left after", loc="left")
        ax.figure.suptitle("Figure after")
        ax.set_xlim(8.0, -2.0)

    # QUndoStack.push() called redo(), but the already-visible state was not
    # applied a second time or normalized (the inverted range remains exact).
    assert tab.graph_undo_stack.count() == 1
    assert tab.graph_undo_stack.undoText() == "Edit graph titles"
    assert ax.get_title() == "After"
    assert ax.get_xlim() == pytest.approx((8.0, -2.0))

    tab.graph_undo_stack.undo()
    assert ax.get_title() == ""
    assert ax.get_title(loc="left") == ""
    assert getattr(ax.figure, "_suptitle", None) is None
    assert ax.get_xlim() == pytest.approx(initial_xlim)

    tab.graph_undo_stack.redo()
    assert ax.get_title() == "After"
    assert ax.get_title(loc="left") == "Left after"
    assert ax.figure._suptitle.get_text() == "Figure after"
    assert ax.get_xlim() == pytest.approx((8.0, -2.0))


def test_noop_and_nested_transactions_do_not_pollute_history(graph):
    tab, ax, _line, _layer_id = graph

    with tab.graph_format_transaction("No change"):
        pass
    assert tab.graph_undo_stack.count() == 0

    with tab.graph_format_transaction("One logical edit"):
        ax.set_xlabel("Time")
        with tab.graph_format_transaction("Nested implementation detail"):
            ax.set_ylabel("Response")

    assert tab.graph_undo_stack.count() == 1
    assert tab.graph_undo_stack.undoText() == "One logical edit"
    tab.graph_undo_stack.undo()
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""


def test_failed_transaction_rolls_back_and_adds_no_command(graph):
    tab, ax, _line, _layer_id = graph

    with pytest.raises(RuntimeError, match="preview failed"):
        with tab.graph_format_transaction("Broken preview"):
            ax.set_title("Must roll back")
            raise RuntimeError("preview failed")

    assert ax.get_title() == ""
    assert tab.graph_undo_stack.count() == 0


def test_layer_rename_and_visibility_restore_model_manager_artist_and_legend(graph):
    tab, ax, line, layer_id = graph

    tab._on_layer_rename(layer_id, "Renamed")
    assert tab.layers[layer_id]["label"] == "Renamed"
    assert tab.layers[layer_id]["meta"]["label"] == "Renamed"
    assert line.get_label() == "Renamed"
    assert tab.layer_manager._items[layer_id].text(0) == "Renamed"
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["Renamed"]

    tab.graph_undo_stack.undo()
    assert tab.layers[layer_id]["label"] == "Signal"
    assert tab.layers[layer_id]["meta"]["label"] == "Signal"
    assert line.get_label() == "Signal"
    assert tab.layer_manager._items[layer_id].text(0) == "Signal"
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["Signal"]

    tab.graph_undo_stack.redo()
    assert tab.layers[layer_id]["label"] == "Renamed"
    assert line.get_label() == "Renamed"

    tab._on_layer_visibility_changed(layer_id, False)
    assert not line.get_visible()
    assert not tab.layers[layer_id]["visible"]
    assert ax.get_legend() is None

    tab.graph_undo_stack.undo()
    assert line.get_visible()
    assert tab.layers[layer_id]["visible"]
    assert tab.layer_manager._items[layer_id].checkState(0).value == 2
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["Renamed"]

    tab.graph_undo_stack.redo()
    assert not line.get_visible()
    assert not tab.layers[layer_id]["visible"]


def test_layer_style_undo_restores_artist_and_persistent_metadata(graph, monkeypatch):
    tab, _ax, line, layer_id = graph
    before_kwargs = dict(tab.layers[layer_id]["kwargs"])
    before_meta = dict(tab.layers[layer_id]["meta"]["style_kwargs"])
    before_color = _hex(line.get_color())
    before_width = line.get_linewidth()

    monkeypatch.setattr(tab.layer_manager, "prompt_color", lambda *_: QColor("#d62728"))
    monkeypatch.setattr(
        "widgets.plot_tabs.QInputDialog.getDouble",
        lambda *_args, **_kwargs: (4.5, True),
    )

    tab._on_layer_style_request(layer_id)
    assert _hex(line.get_color()) == "#d62728"
    assert line.get_linewidth() == pytest.approx(4.5)
    assert tab.layers[layer_id]["kwargs"]["color"] == "#d62728"

    tab.graph_undo_stack.undo()
    assert _hex(line.get_color()) == before_color
    assert line.get_linewidth() == pytest.approx(before_width)
    assert tab.layers[layer_id]["kwargs"] == before_kwargs
    assert tab.layers[layer_id]["meta"]["style_kwargs"] == before_meta

    tab.graph_undo_stack.redo()
    assert _hex(line.get_color()) == "#d62728"
    assert line.get_linewidth() == pytest.approx(4.5)
    assert tab.layers[layer_id]["kwargs"]["color"] == "#d62728"


def test_public_capture_restore_includes_reference_guides_and_clears_on_topology(graph):
    tab, ax, _line, _layer_id = graph
    apply_style(ax, {"axes": {
        "refline_h": 2.5,
        "refline_h_label": "Limit",
        "refline_color": "#ff0000",
        "refline_style": "--",
        "refline_width": 2.0,
        "refline_alpha": 0.8,
    }}, ax.figure, live=True)
    before = capture_graph_format_state(tab)

    apply_style(ax, {"axes": {
        "refline_h": 9.0,
        "refline_h_label": "Changed",
        "refline_color": "#00ff00",
        "refline_style": ":",
        "refline_width": 1.0,
        "refline_alpha": 1.0,
    }}, ax.figure, live=True)
    restore_graph_format_state(tab, before)

    guide = next(line for line in ax.lines if line.get_gid() == "_ps_refline_h")
    label = next(text for text in ax.texts if text.get_gid() == "_ps_refline_h_label")
    assert float(guide.get_ydata()[0]) == pytest.approx(2.5)
    assert _hex(guide.get_color()) == "#ff0000"
    assert label.get_text() == "Limit"

    with tab.graph_format_transaction("Temporary title"):
        ax.set_title("Temporary")
    assert tab.graph_undo_stack.canUndo()
    extra, = ax.plot([0, 1], [0, 1], label="Extra")
    tab.register_layer([extra], "Extra", "line")
    assert not tab.graph_undo_stack.canUndo()


def test_paste_graph_format_is_one_undoable_target_edit(qapp):
    source = GraphTab("source")
    target = GraphTab("target")
    try:
        source_line, = source.get_axes().plot([0, 1], [1, 2], color="#d62728")
        target_line, = target.get_axes().plot([0, 1], [3, 4], color="#1f77b4")
        source.register_layer([source_line], "Source", "line")
        target.register_layer([target_line], "Target", "line")
        target.graph_undo_stack.clear()

        class _Tabs:
            current = source

            def currentWidget(self):
                return self.current

        class _Harness(MainWindowPlotStyleMixin):
            def __init__(self):
                self.tabs = _Tabs()
                self.messages = []

            def notify(self, value):
                self.messages.append(value)

            def inform(self, *_args):
                pass

            def error_box(self, *_args):
                pytest.fail(str(_args))

            def _refresh_action_states(self):
                pass

        harness = _Harness()
        assert harness.copy_graph_format() is True
        harness.tabs.current = target
        assert harness.paste_graph_format() is True

        assert _hex(target_line.get_color()) == "#d62728"
        assert target.graph_undo_stack.count() == 1
        assert target.graph_undo_stack.undoText() == "Paste graph format"
        target.graph_undo_stack.undo()
        assert _hex(target_line.get_color()) == "#1f77b4"
        target.graph_undo_stack.redo()
        assert _hex(target_line.get_color()) == "#d62728"
    finally:
        source.close()
        target.close()


def test_layer_visibility_toggles_generated_line_dependents_and_bar_legend(qapp):
    tab = GraphTab("visibility", "Visibility")
    try:
        line, = tab.get_axes().plot([0, 1, 2], [1, 3, 2], label="Signal")
        line_id = tab.register_layer([line], "Signal", "line")
        from core.plot_style import apply_line_style

        apply_line_style(line, {"fill": "under", "value_labels": True})
        bars = tab.get_axes().bar([0, 1], [2, 4], label="Counts")
        bar_id = tab.register_layer(list(bars.patches), "Counts", "bar")
        tab.get_axes().legend()

        tab._set_layer_visibility(line_id, False)
        line_gid = str(id(line))
        dependents = [
            artist for group in (
                tab.get_axes().collections, tab.get_axes().texts,
                tab.get_axes().lines, tab.get_axes().images,
            )
            for artist in group
            if line_gid in str(artist.get_gid() or "")
        ]
        assert dependents and all(not artist.get_visible() for artist in dependents)

        tab._set_layer_visibility(bar_id, False)
        legend = tab.get_axes().get_legend()
        labels = [] if legend is None else [text.get_text() for text in legend.get_texts()]
        assert "Counts" not in labels

        tab._set_layer_visibility(line_id, True)
        assert all(artist.get_visible() for artist in dependents)
    finally:
        tab.close()


def test_unrelated_graph_undo_keeps_line_glow_and_shadow(qapp):
    from core.plot_style import apply_line_style

    tab = GraphTab("effects-history", "Effects history")
    try:
        line, = tab.get_axes().plot([0, 1, 2], [1, 3, 2])
        tab.register_layer([line], "Signal", "line")
        apply_line_style(line, {
            "glow": True, "glow_color": "#ffc107", "glow_width": 6.0,
            "shadow": True, "shadow_alpha": 0.3,
            "fill": "under", "fill_alpha": 0.2,
        })
        tab.graph_undo_stack.clear()

        with tab.graph_format_transaction("Edit title"):
            tab.get_axes().set_title("Changed")
        tab.graph_undo_stack.undo()

        assert line._ps_effects["glow"] is True
        assert line._ps_effects["shadow"] is True
        assert len(line.get_path_effects()) == 3
    finally:
        tab.close()
