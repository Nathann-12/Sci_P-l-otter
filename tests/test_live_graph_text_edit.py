"""Behavioral coverage for editing authored graph text directly on-canvas.

The live editor intentionally targets semantic text (titles, axis labels and
legend labels), not formatter-owned tick labels or arbitrary generated text.
These tests use a small mixin harness for fast interaction checks and one real
MainWindow round-trip to protect project persistence.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from main_window_plotstyle_mixin import MainWindowPlotStyleMixin
from widgets.plot_tabs import GraphTab


class _CurrentTabs:
    def __init__(self, tab):
        self.tab = tab

    def currentWidget(self):
        return self.tab


class _PlotStyleHarness(MainWindowPlotStyleMixin):
    """Only the collaborators used by the live-text portion of the mixin."""

    def __init__(self, tab):
        self.tabs = _CurrentTabs(tab)
        self.opened = []
        self.messages = []

    def _get_current_tab(self):
        return self.tabs.currentWidget()

    def open_graph_data_panel(self):
        self.opened.append("data")
        return True

    def open_plot_details_dialog(self, preselect_line=None):
        self.opened.append(("style", preselect_line))

    def notify(self, message):
        self.messages.append(message)

    def inform(self, title, message):
        self.messages.append((title, message))


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def graph_env(qapp):
    tab = GraphTab("live_text", "Live text")
    tab.resize(840, 620)
    tab.canvas.resize(840, 570)
    tab.show()
    qapp.processEvents()
    harness = _PlotStyleHarness(tab)
    yield harness, tab
    tab.close()
    tab.deleteLater()
    qapp.processEvents()


def _target(harness, *, artist=None, kind=None, axes=None, legend_index=None):
    matches = []
    for candidate in harness._graph_text_targets():
        if artist is not None and candidate.artist is not artist:
            continue
        if kind is not None and candidate.kind != kind:
            continue
        if axes is not None and candidate.axes is not axes:
            continue
        if legend_index is not None and candidate.legend_index != legend_index:
            continue
        matches.append(candidate)
    assert len(matches) == 1, [
        (
            item.kind,
            item.artist.get_text(),
            item.axes,
            item.legend_index,
            item.layer_id,
        )
        for item in harness._graph_text_targets()
    ]
    return matches[0]


_DEFAULT_AXES = object()


def _event_for_artist(artist, canvas, *, key=None, inaxes=_DEFAULT_AXES):
    canvas.draw()
    bbox = artist.get_window_extent(renderer=canvas.get_renderer())
    if inaxes is _DEFAULT_AXES:
        inaxes = getattr(artist, "axes", None)
    return SimpleNamespace(
        name="button_press_event",
        canvas=canvas,
        guiEvent=None,
        button=1,
        dblclick=True,
        key=key,
        x=float((bbox.xmin + bbox.xmax) / 2.0),
        y=float((bbox.ymin + bbox.ymax) / 2.0),
        xdata=None,
        ydata=None,
        inaxes=inaxes,
    )


def _active_inline_editor(harness, tab):
    editor = getattr(harness, "_graph_text_editor", None)
    if isinstance(editor, QLineEdit):
        return editor
    editors = tab.canvas.findChildren(QLineEdit)
    assert editors, "live graph text edit did not create an on-canvas QLineEdit"
    return editors[-1]


def test_targets_and_commits_axis_titles_labels_and_figure_title(graph_env):
    harness, tab = graph_env
    ax = tab.get_axes()
    ax.set_title(
        "Centered title",
        color="#4f9cf9",
        fontsize=17,
        fontweight="bold",
        rotation=3,
    )
    ax.set_title("Left note", loc="left")
    ax.set_xlabel("Elapsed time")
    ax.set_ylabel("Response")
    figure_title = tab.get_figure().suptitle("Experiment A")

    center = _target(harness, artist=ax.title, kind="title")
    left = _target(harness, artist=ax._left_title, kind="title")
    xlabel = _target(harness, artist=ax.xaxis.label, kind="xlabel")
    ylabel = _target(harness, artist=ax.yaxis.label, kind="ylabel")
    suptitle = _target(harness, artist=figure_title, kind="figure_title")
    typography = (
        center.artist.get_color(),
        center.artist.get_fontsize(),
        center.artist.get_fontweight(),
        center.artist.get_rotation(),
        center.artist.get_position(),
    )

    assert center.title_loc == "center"
    assert left.title_loc == "left"
    assert all(item.tab is tab and item.axes is ax for item in (center, left, xlabel, ylabel))

    assert harness._commit_graph_text(center, "ผลการทดลอง") is True
    assert harness._commit_graph_text(left, "ชุด A") is True
    assert harness._commit_graph_text(xlabel, "เวลา (วินาที)") is True
    assert harness._commit_graph_text(ylabel, "อัตรา μmol·s⁻¹") is True
    assert harness._commit_graph_text(suptitle, "รายงานรวม") is True

    assert ax.get_title() == "ผลการทดลอง"
    assert ax.get_title(loc="left") == "ชุด A"
    assert ax.get_xlabel() == "เวลา (วินาที)"
    assert ax.get_ylabel() == "อัตรา μmol·s⁻¹"
    assert tab.get_figure()._suptitle.get_text() == "รายงานรวม"
    assert (
        center.artist.get_color(),
        center.artist.get_fontsize(),
        center.artist.get_fontweight(),
        center.artist.get_rotation(),
        center.artist.get_position(),
    ) == typography

    # Clearing an authored label is a legitimate edit.  A discoverable context
    # menu command can create it again even though an empty string has no bbox.
    assert harness._commit_graph_text(center, "") is True
    assert ax.get_title() == ""


def test_3d_z_label_is_a_first_class_live_text_target(graph_env):
    harness, tab = graph_env
    fig = tab.get_figure()
    fig.clear()
    ax = fig.add_subplot(111, projection="3d")
    tab.canvas.ax = ax
    ax.set_title("Surface")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Intensity")

    target = _target(harness, artist=ax.zaxis.label, kind="zlabel", axes=ax)
    assert harness._commit_graph_text(target, "ความเข้ม (a.u.)") is True
    assert ax.get_zlabel() == "ความเข้ม (a.u.)"


def test_multi_axes_targets_keep_their_own_axis(graph_env):
    harness, tab = graph_env
    primary = tab.get_axes()
    primary.set_ylabel("Temperature")
    secondary = primary.twinx()
    secondary.set_ylabel("Pressure")

    primary_target = _target(
        harness, artist=primary.yaxis.label, kind="ylabel", axes=primary
    )
    secondary_target = _target(
        harness, artist=secondary.yaxis.label, kind="ylabel", axes=secondary
    )

    assert harness._commit_graph_text(secondary_target, "Pressure (kPa)") is True
    assert primary.get_ylabel() == "Temperature"
    assert secondary.get_ylabel() == "Pressure (kPa)"
    assert primary_target.axes is not secondary_target.axes


def test_legend_title_and_duplicate_items_update_the_exact_backing_layer(graph_env):
    harness, tab = graph_env
    ax = tab.get_axes()
    first, = ax.plot([0, 1], [1, 2], label="Repeated")
    second, = ax.plot([0, 1], [2, 3], label="Repeated")
    first_id = tab.register_layer([first], "Repeated", "line", meta={"label": "Repeated"})
    second_id = tab.register_layer([second], "Repeated", "line", meta={"label": "Repeated"})
    legend = ax.legend(title="Measurements")

    title_target = _target(
        harness, artist=legend.get_title(), kind="legend_title", axes=ax
    )
    first_target = _target(harness, kind="legend_item", axes=ax, legend_index=0)
    second_target = _target(harness, kind="legend_item", axes=ax, legend_index=1)

    assert first_target.layer_id == first_id
    assert second_target.layer_id == second_id
    assert first_target.source_handle is first
    assert second_target.source_handle is second

    assert harness._commit_graph_text(title_target, "ชุดข้อมูล") is True
    assert harness._commit_graph_text(second_target, "Repeated B") is True

    assert legend.get_title().get_text() == "ชุดข้อมูล"
    assert [text.get_text() for text in legend.get_texts()] == [
        "Repeated",
        "Repeated B",
    ]
    assert first.get_label() == "Repeated"
    assert second.get_label() == "Repeated B"
    assert tab.layers[first_id]["label"] == "Repeated"
    assert tab.layers[second_id]["label"] == "Repeated B"
    assert tab.layers[second_id]["meta"]["label"] == "Repeated B"
    serialized = {entry["id"]: entry for entry in tab.serialize_layers()}
    assert serialized[first_id]["label"] == "Repeated"
    assert serialized[second_id]["label"] == "Repeated B"

    # Visibility changes and later plots rebuild the legend, so a live rename
    # must live in the source layer and the authored legend title must survive.
    tab._refresh_legend()
    refreshed = ax.get_legend()
    assert refreshed.get_title().get_text() == "ชุดข้อมูล"
    assert [text.get_text() for text in refreshed.get_texts()] == [
        "Repeated",
        "Repeated B",
    ]


@pytest.mark.parametrize("plot_kind", ["bar", "histogram"])
def test_container_layer_rename_stays_one_legend_row_and_preserves_format(
    graph_env, plot_kind
):
    harness, tab = graph_env
    ax = tab.get_axes()
    if plot_kind == "bar":
        container = ax.bar([0, 1, 2], [2, 4, 3], label="Old")
        artists = list(container)
    else:
        _counts, _bins, patches = ax.hist([1, 1, 2, 3, 3], label="Old")
        artists = list(patches)
    layer_id = tab.register_layer(
        artists, "Old", plot_kind, meta={"label": "Old"}
    )
    legend = ax.legend(title="Summary", loc="lower left", frameon=True)
    legend.get_texts()[0].set_color("#4f9cf9")
    legend.get_frame().set_alpha(0.42)
    old_loc = legend._loc

    target = _target(harness, kind="legend_item", axes=ax, legend_index=0)
    assert target.layer_id == layer_id
    assert harness._commit_graph_text(target, "New") is True

    refreshed = ax.get_legend()
    source_labels = [
        label for label in ax.get_legend_handles_labels()[1]
        if label and not str(label).startswith("_")
    ]
    assert source_labels == ["New"]
    assert [text.get_text() for text in refreshed.get_texts()] == ["New"]
    assert refreshed.get_title().get_text() == "Summary"
    assert refreshed._loc == old_loc
    assert refreshed.get_frame().get_alpha() == pytest.approx(0.42)
    assert tab.layers[layer_id]["label"] == "New"
    assert tab.layers[layer_id]["meta"]["label"] == "New"


def test_hit_testing_text_works_when_event_is_outside_axes(graph_env):
    harness, tab = graph_env
    ax = tab.get_axes()
    ax.set_title("Editable title")
    event = _event_for_artist(ax.title, tab.canvas, inaxes=None)

    target = harness._graph_text_target_at_event(event)

    assert target is not None
    assert target.kind == "title"
    assert target.artist is ax.title


def test_tick_labels_and_generated_plot_text_are_not_live_edit_targets(graph_env):
    harness, tab = graph_env
    ax = tab.get_axes()
    ax.plot([0, 1, 2], [1, 4, 9])
    generated = ax.text(0.5, 0.5, "R² = 0.99", transform=ax.transAxes)
    tab.canvas.draw()
    tick = next(text for text in ax.get_xticklabels() if text.get_visible() and text.get_text())

    assert all(target.artist is not generated for target in harness._graph_text_targets())
    assert harness._graph_text_target_at_event(
        _event_for_artist(tick, tab.canvas, inaxes=None)
    ) is None


@pytest.mark.parametrize("modifier", ["control", "shift"])
def test_modified_double_click_bypasses_live_text_for_graph_data(
    graph_env, monkeypatch, modifier
):
    harness, tab = graph_env
    ax = tab.get_axes()
    ax.set_title("Do not edit")
    started = []
    monkeypatch.setattr(
        harness,
        "_start_graph_text_edit",
        lambda target, event=None: started.append(target) or True,
    )

    harness._on_canvas_click(
        _event_for_artist(ax.title, tab.canvas, key=modifier, inaxes=None)
    )

    assert harness.opened == ["data"]
    assert started == []


def test_blank_double_click_keeps_plot_details_fallback(graph_env):
    harness, tab = graph_env
    ax = tab.get_axes()
    tab.canvas.draw()
    bbox = ax.get_window_extent(renderer=tab.canvas.get_renderer())
    event = SimpleNamespace(
        dblclick=True,
        key=None,
        button=1,
        x=float(bbox.xmin + bbox.width * 0.8),
        y=float(bbox.ymin + bbox.height * 0.8),
        xdata=None,
        ydata=None,
        inaxes=ax,
        canvas=tab.canvas,
        guiEvent=None,
        name="button_press_event",
    )

    harness._on_canvas_click(event)

    assert harness.opened == [("style", None)]


def test_annotation_double_click_wins_over_graph_text_and_plot_details(
    graph_env, monkeypatch
):
    harness, tab = graph_env
    ax = tab.get_axes()
    ax.set_title("Graph title")
    started = []
    monkeypatch.setattr(harness, "_annotation_dblclick_target", lambda _event: True)
    monkeypatch.setattr(
        harness,
        "_start_graph_text_edit",
        lambda target, event=None: started.append(target) or True,
    )

    harness._on_canvas_click(_event_for_artist(ax.title, tab.canvas, inaxes=None))

    assert started == []
    assert harness.opened == []


def test_inline_editor_commits_unicode_on_enter_and_escape_cancels(graph_env, qapp):
    harness, tab = graph_env
    ax = tab.get_axes()
    ax.set_xlabel("Time")
    target = _target(harness, artist=ax.xaxis.label, kind="xlabel")

    assert harness._start_graph_text_edit(target) is True
    editor = _active_inline_editor(harness, tab)
    geometry = editor.geometry()
    assert editor.parentWidget() is tab.canvas
    assert geometry.left() >= 0 and geometry.top() >= 0
    assert geometry.right() < tab.canvas.width()
    assert geometry.bottom() < tab.canvas.height()
    editor.setText("เวลา Δt (วินาที)")
    QTest.keyClick(editor, Qt.Key_Return)
    qapp.processEvents()
    assert ax.get_xlabel() == "เวลา Δt (วินาที)"

    target = _target(harness, artist=ax.xaxis.label, kind="xlabel")
    assert harness._start_graph_text_edit(target) is True
    editor = _active_inline_editor(harness, tab)
    editor.setText("Focus-out commit")
    editor.clearFocus()
    qapp.processEvents()
    assert ax.get_xlabel() == "Focus-out commit"

    target = _target(harness, artist=ax.xaxis.label, kind="xlabel")
    assert harness._start_graph_text_edit(target) is True
    editor = _active_inline_editor(harness, tab)
    editor.setText("must not be committed")
    QTest.keyClick(editor, Qt.Key_Escape)
    qapp.processEvents()
    assert ax.get_xlabel() == "Focus-out commit"


def test_project_round_trip_restores_live_graph_text(qapp, tmp_path):
    from core import session as session_store
    import main as app_main

    source = app_main.MainWindow()
    restored = None
    try:
        tab_id = source.tabs.add_tab("Text persistence")
        tab = source.tabs.tabs[tab_id]
        source.tabs.add_series_to_tabs(
            [tab_id], [0.0, 1.0, 2.0], [2.0, 3.0, 5.0], label="Signal"
        )
        ax = tab.get_axes()
        ax.set_title("ผลการทดลอง")
        ax.set_xlabel("เวลา (s)")
        ax.set_ylabel("สัญญาณ (mV)")
        tab.get_figure().suptitle("Batch 42")
        assert ax.get_legend() is not None
        ax.get_legend().set_title("Channels")

        project = tmp_path / "live-text.sciproj"
        session_store.save_project(source, project)

        restored = app_main.MainWindow()
        session_store.load_project(restored, project)
        restored_tab = next(
            tab
            for index in range(restored.tabs.count())
            if restored.tabs.tabText(index) == "Text persistence"
            for tab in [restored.tabs.widget(index)]
        )
        restored_ax = restored_tab.get_axes()

        assert restored_ax.get_title() == "ผลการทดลอง"
        assert restored_ax.get_xlabel() == "เวลา (s)"
        assert restored_ax.get_ylabel() == "สัญญาณ (mV)"
        assert restored_tab.get_figure()._suptitle.get_text() == "Batch 42"
        assert restored_ax.get_legend().get_title().get_text() == "Channels"
    finally:
        source.close()
        if restored is not None:
            restored.close()
        qapp.processEvents()


def test_live_graph_text_edit_is_one_undoable_graph_command(graph_env):
    harness, tab = graph_env
    ax = tab.get_axes()
    ax.set_title("Before")
    tab.graph_undo_stack.clear()
    target = _target(harness, artist=ax.title, kind="title")

    assert harness._commit_graph_text(target, "After") is True
    assert tab.graph_undo_stack.count() == 1
    assert ax.get_title() == "After"

    tab.graph_undo_stack.undo()
    assert ax.get_title() == "Before"
    tab.graph_undo_stack.redo()
    assert ax.get_title() == "After"


def test_single_click_selects_canvas_layers_for_quick_format(graph_env):
    harness, tab = graph_env
    tab.clear()
    ax = tab.get_axes()
    first, = ax.plot([0, 1, 2], [1, 1, 1], label="First")
    second, = ax.plot([0, 1, 2], [3, 3, 3], label="Second")
    first_id = tab.register_layer([first], "First", "line")
    second_id = tab.register_layer([second], "Second", "line")
    tab.draw()

    def click(line, key=None):
        x = float(line.get_xdata()[1])
        y = float(line.get_ydata()[1])
        px, py = ax.transData.transform((x, y))
        return SimpleNamespace(
            dblclick=False, button=1, key=key, inaxes=ax,
            x=float(px), y=float(py), xdata=x, ydata=y,
            canvas=tab.canvas,
        )

    harness._on_canvas_click(click(first))
    assert tab.layer_manager.selected_layer_ids() == [first_id]
    harness._on_canvas_click(click(second, "control"))
    assert tab.layer_manager.selected_layer_ids() == [first_id, second_id]


def test_legend_is_directly_draggable_and_move_records_history(graph_env, qapp):
    harness, tab = graph_env
    tab.clear()
    ax = tab.get_axes()
    line, = ax.plot([0, 1], [1, 2], label="Signal")
    tab.register_layer([line], "Signal", "line")
    legend = ax.legend(loc="upper right")
    harness.bind_graph_dblclick()
    assert legend.get_draggable() is True
    tab.draw()
    bbox = legend.get_window_extent(renderer=tab.canvas.get_renderer())
    initial_loc = legend._loc
    event = SimpleNamespace(
        dblclick=False, button=1, key=None, inaxes=ax,
        x=float((bbox.xmin + bbox.xmax) / 2),
        y=float((bbox.ymin + bbox.ymax) / 2),
        canvas=tab.canvas,
    )
    tab.graph_undo_stack.clear()
    harness._on_canvas_click(event)
    legend._loc = (0.2, 0.3)
    harness._on_canvas_release(event)
    qapp.processEvents()

    assert tab.graph_undo_stack.count() == 1
    tab.graph_undo_stack.undo()
    assert tab.get_axes().get_legend()._loc == initial_loc
