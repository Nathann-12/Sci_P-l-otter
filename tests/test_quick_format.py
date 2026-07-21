from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib.colors as mcolors
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from widgets.plot_tabs import GraphTab
from widgets.quick_format import QuickFormatWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _hex(value):
    return mcolors.to_hex(value, keep_alpha=False)


def test_quick_format_widget_requires_selection_and_emits_only_enabled_values(qapp):
    panel = QuickFormatWidget()
    try:
        assert panel.btnApply.isEnabled() is False
        panel.set_selection(["Signal A", "Signal B"])
        assert panel.btnApply.isEnabled() is True
        assert "2 layers selected" in panel.selectionLabel.text()

        panel.spAlpha.setValue(0.45)
        panel.spWidth.setValue(2.75)
        marker_index = panel.cboMarker.findData("s")
        panel.cboMarker.setCurrentIndex(marker_index)
        panel.cboMarker.activated.emit(marker_index)
        assert panel.style_values() == {
            "alpha": 0.45,
            "linewidth": 2.75,
            "marker": "s",
        }
        palette_index = panel.cboPalette.findData("Okabe-Ito (CB-safe)")
        panel.cboPalette.setCurrentIndex(palette_index)
        panel.cboPalette.activated.emit(palette_index)
        assert panel.style_values()["palette"] == "Okabe-Ito (CB-safe)"
    finally:
        panel.close()


def test_bulk_quick_format_is_one_undoable_graph_edit(qapp):
    tab = GraphTab("quick", "Quick")
    try:
        line, = tab.get_axes().plot([0, 1, 2], [1, 3, 2], color="#1976d2", marker="o")
        bars = tab.get_axes().bar([0, 1], [2, 4], color="#ffb300")
        line_id = tab.register_layer([line], "Signal", "line", kwargs={})
        bar_id = tab.register_layer(list(bars.patches), "Counts", "bar", kwargs={})
        tab.graph_undo_stack.clear()

        summary = tab.quick_layer_style_summary([line_id, bar_id])
        assert "color" in summary["mixed_fields"]
        assert summary["alpha"] == pytest.approx(1.0)

        changed = tab.apply_quick_layer_format(
            [line_id, bar_id],
            {"color": "#8e24aa", "alpha": 0.5, "linewidth": 3.0, "marker": "s"},
        )

        assert changed == 2
        assert tab.graph_undo_stack.count() == 1
        assert _hex(line.get_color()) == "#8e24aa"
        assert line.get_marker() == "s"
        assert line.get_alpha() == pytest.approx(0.5)
        assert all(_hex(patch.get_facecolor()) == "#8e24aa" for patch in bars.patches)
        assert all(patch.get_alpha() == pytest.approx(0.5) for patch in bars.patches)

        tab.graph_undo_stack.undo()
        assert _hex(line.get_color()) == "#1976d2"
        assert line.get_marker() == "o"
        assert all(_hex(patch.get_facecolor()) == "#ffb300" for patch in bars.patches)

        tab.graph_undo_stack.redo()
        assert _hex(line.get_color()) == "#8e24aa"
        assert line.get_marker() == "s"
    finally:
        tab.close()


def test_quick_color_does_not_destroy_mapped_scatter_data(qapp):
    tab = GraphTab("mapped", "Mapped")
    try:
        values = np.array([0.1, 0.4, 0.9])
        scatter = tab.get_axes().scatter([0, 1, 2], [3, 2, 4], c=values, cmap="viridis")
        layer_id = tab.register_layer([scatter], "Temperature", "scatter", kwargs={})
        before = scatter.get_array().copy()

        assert tab.apply_quick_layer_format([layer_id], {"color": "#ff0000"}) == 0
        assert np.array_equal(scatter.get_array(), before)
        assert scatter.get_cmap().name == "viridis"
        assert tab.graph_undo_stack.count() == 0
    finally:
        tab.close()


def test_quick_scientific_palette_assigns_distinct_selected_layer_colors(qapp):
    from core.plot_style import SCIENTIFIC_PALETTES

    tab = GraphTab("palette", "Palette")
    try:
        first, = tab.get_axes().plot([0, 1], [1, 2])
        second, = tab.get_axes().plot([0, 1], [2, 1])
        first_id = tab.register_layer([first], "A", "line")
        second_id = tab.register_layer([second], "B", "line")
        tab.graph_undo_stack.clear()

        assert tab.apply_quick_layer_format(
            [first_id, second_id], {"palette": "Okabe-Ito (CB-safe)"}
        ) == 2
        expected = SCIENTIFIC_PALETTES["Okabe-Ito (CB-safe)"][:2]
        assert [_hex(first.get_color()), _hex(second.get_color())] == [
            _hex(expected[0]), _hex(expected[1]),
        ]
        assert tab.graph_undo_stack.count() == 1
    finally:
        tab.close()


def test_quick_summary_reports_mixed_styles_inside_one_bar_layer(qapp):
    tab = GraphTab("mixed-bars", "Mixed bars")
    try:
        bars = tab.get_axes().bar(
            [0, 1, 2], [2, 4, 3],
            color=["#d62728", "#2ca02c", "#1f77b4"],
            linewidth=[1.0, 2.0, 3.0],
        )
        layer_id = tab.register_layer(list(bars.patches), "Categories", "bar")

        summary = tab.quick_layer_style_summary([layer_id])

        assert summary["color"] is None
        assert summary["linewidth"] is None
        assert "color" in summary["mixed_fields"]
        assert "linewidth" in summary["mixed_fields"]
        assert summary["alpha"] == pytest.approx(1.0)
    finally:
        tab.close()


def test_quick_format_undo_restores_per_point_scatter_colors(qapp):
    tab = GraphTab("point-colors", "Point colors")
    try:
        scatter = tab.get_axes().scatter(
            [0, 1, 2], [3, 1, 2],
            c=["#d62728", "#2ca02c", "#1f77b4"],
            s=[12.0, 24.0, 48.0],
        )
        layer_id = tab.register_layer([scatter], "Points", "scatter")
        before_colors = scatter.get_facecolors().copy()
        before_sizes = scatter.get_sizes().copy()
        tab.graph_undo_stack.clear()

        assert tab.apply_quick_layer_format([layer_id], {"color": "#000000"}) == 1
        assert np.allclose(scatter.get_facecolors()[0], mcolors.to_rgba("#000000"))

        tab.graph_undo_stack.undo()
        assert np.allclose(scatter.get_facecolors(), before_colors)
        assert np.allclose(scatter.get_sizes(), before_sizes)
    finally:
        tab.close()


def test_quick_color_rebuilds_auto_colored_line_decorations(qapp):
    from core.plot_style import apply_line_style

    tab = GraphTab("line-deco", "Line decorations")
    try:
        line, = tab.get_axes().plot([0, 1, 2], [1, 3, 2], color="#d62728")
        layer_id = tab.register_layer([line], "Signal", "line")
        apply_line_style(line, {
            "glow": True, "glow_color": "#d62728",
            "fill": "under", "fill_color": "",
            "errorbar_mode": "constant", "errorbar_value": 0.2,
        })
        tab.graph_undo_stack.clear()

        assert tab.apply_quick_layer_format([layer_id], {"color": "#1f77b4"}) == 1

        fill = next(
            item for item in tab.get_axes().collections
            if str(item.get_gid() or "").startswith("_ps_fill_")
        )
        assert _hex(fill.get_facecolors()[0]) == "#1f77b4"
        assert _hex(line._ps_effects["glow_color"]) == "#1f77b4"
    finally:
        tab.close()
