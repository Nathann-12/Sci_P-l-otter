"""Behavioral tests for the in-memory Copy/Paste Graph Format clipboard."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

import matplotlib

matplotlib.use("Agg")

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pytest

from core import format_clipboard
from core.format_clipboard import (
    apply_graph_format,
    apply_persisted_graph_format,
    capture_graph_format,
    capture_persisted_graph_format,
    is_graph_format_snapshot,
)
from core.plot_style import apply_line_style, apply_style


def _hex(value) -> str:
    return mcolors.to_hex(value, keep_alpha=False)


@dataclass
class FakeTab:
    """Small GraphTab adapter that keeps these tests independent of Qt."""

    ax: object
    layers: dict = field(default_factory=dict)
    draw_count: int = 0

    def get_axes(self):
        return self.ax

    def get_figure(self):
        return self.ax.figure

    def draw(self):
        self.draw_count += 1
        self.ax.figure.canvas.draw()


@pytest.fixture()
def make_tab():
    figures = []

    def factory(**subplot_kwargs):
        fig, ax = plt.subplots(subplot_kw=subplot_kwargs or None)
        figures.append(fig)
        return FakeTab(ax)

    yield factory

    for fig in figures:
        plt.close(fig)


def test_line_format_transfers_but_target_scientific_content_is_preserved(make_tab):
    source = make_tab()
    source_line, = source.ax.plot(
        [1, 2, 3], [2, 4, 8],
        color="#d62728", linewidth=4.25, linestyle="--", marker="s",
        markersize=9, markerfacecolor="#2ca02c", markeredgecolor="#1f77b4",
        markeredgewidth=1.75, alpha=0.35, zorder=7, label="source",
    )
    source.ax.set_title("Source title", color="#9467bd", fontsize=18,
                        fontweight="bold")
    source.ax.set_xlabel("Source x", color="#8c564b", fontsize=13)
    source.ax.set_ylabel("Source y", color="#8c564b", fontsize=13)
    source.ax.set_facecolor("#f1f3f5")
    source.ax.grid(True, color="#17becf", linestyle=":", linewidth=1.5,
                   alpha=0.6)
    source.ax.legend(title="Source legend", loc="lower right", ncol=2,
                     frameon=True)
    source.get_figure().set_facecolor("#e9ecef")

    target = make_tab()
    first, = target.ax.plot([2, 5, 9], [3, 10, 30], label="A")
    second, = target.ax.plot([2, 5, 9], [6, 20, 60], label="B")
    target.layers = {
        "first": {
            "artists": [first], "style": "line",
            "kwargs": {"c": "green", "lw": 1.0},
            "meta": {"style_kwargs": {"c": "green", "lw": 1.0}},
        },
        "second": {
            "artists": [second], "style": "line",
            "kwargs": {}, "meta": {},
        },
    }
    target.ax.set_title("Target title")
    target.ax.set_xlabel("Elapsed time (s)")
    target.ax.set_ylabel("Response (a.u.)")
    target.ax.set_xscale("log")
    target.ax.set_yscale("log")
    target.ax.set_xlim(100.0, 1.0)  # ordered limits also encode inversion
    target.ax.set_ylim(2.0, 200.0)
    target.ax.set_autoscalex_on(True)
    target.ax.set_autoscaley_on(False)
    guide = target.ax.axvline(7.5, color="black", linestyle=":",
                              label="threshold")
    guide.set_gid("_ps_refline_v")
    target.ax.legend([second, first], ["B", "A"], title="Target legend",
                     loc="upper left")

    before = {
        "title": target.ax.get_title(),
        "xlabel": target.ax.get_xlabel(),
        "ylabel": target.ax.get_ylabel(),
        "xscale": target.ax.get_xscale(),
        "yscale": target.ax.get_yscale(),
        "xlim": target.ax.get_xlim(),
        "ylim": target.ax.get_ylim(),
        "autoscalex": target.ax.get_autoscalex_on(),
        "autoscaley": target.ax.get_autoscaley_on(),
        "guide_x": tuple(guide.get_xdata()),
    }

    applied = apply_graph_format(target, capture_graph_format(source))

    assert applied == 2
    assert target.ax.get_title() == before["title"]
    assert target.ax.get_xlabel() == before["xlabel"]
    assert target.ax.get_ylabel() == before["ylabel"]
    assert target.ax.get_xscale() == before["xscale"]
    assert target.ax.get_yscale() == before["yscale"]
    assert target.ax.get_xlim() == pytest.approx(before["xlim"])
    assert target.ax.get_ylim() == pytest.approx(before["ylim"])
    assert target.ax.xaxis_inverted()
    assert target.ax.get_autoscalex_on() is before["autoscalex"]
    assert target.ax.get_autoscaley_on() is before["autoscaley"]
    assert guide in target.ax.lines
    assert tuple(guide.get_xdata()) == before["guide_x"]
    assert guide.get_label() == "threshold"

    # Text itself stays target-owned, while typography and graph appearance copy.
    assert target.ax.title.get_fontsize() == pytest.approx(18)
    assert target.ax.title.get_fontweight() == "bold"
    assert _hex(target.ax.title.get_color()) == "#9467bd"
    assert _hex(target.ax.get_facecolor()) == "#f1f3f5"
    assert _hex(target.get_figure().get_facecolor()) == "#e9ecef"
    assert any(line.get_visible() for line in target.ax.get_xgridlines())

    for line in (first, second):
        assert _hex(line.get_color()) == _hex(source_line.get_color())
        assert line.get_linewidth() == pytest.approx(4.25)
        assert line.get_linestyle() == "--"
        assert line.get_marker() == "s"
        assert line.get_markersize() == pytest.approx(9)
        assert _hex(line.get_markerfacecolor()) == "#2ca02c"
        assert _hex(line.get_markeredgecolor()) == "#1f77b4"
        assert line.get_alpha() == pytest.approx(0.35)
    assert [first.get_label(), second.get_label()] == ["A", "B"]
    assert "c" not in target.layers["first"]["kwargs"]
    assert "lw" not in target.layers["first"]["kwargs"]
    assert target.layers["first"]["kwargs"]["color"] == "#d62728"
    assert target.layers["first"]["kwargs"]["linewidth"] == pytest.approx(4.25)

    legend = target.ax.get_legend()
    assert legend.get_title().get_text() == "Target legend"
    assert [text.get_text() for text in legend.get_texts()] == ["B", "A"]
    assert legend._loc == source.ax.get_legend()._loc


def test_multiple_source_series_cycle_across_more_target_series(make_tab):
    source = make_tab()
    source.ax.plot([0, 1], [0, 1], color="#ff0000", linewidth=1.5,
                   linestyle="--", marker="o", label="red")
    source.ax.plot([0, 1], [1, 0], color="#0000ff", linewidth=3.0,
                   linestyle=":", marker="^", label="blue")

    target = make_tab()
    target_lines = [
        target.ax.plot([0, 1], [i, i + 1], label=f"target-{i}")[0]
        for i in range(5)
    ]

    snapshot = capture_graph_format(source)
    assert snapshot["series_count"] == 2
    assert apply_graph_format(target, snapshot) == 5

    assert [_hex(line.get_color()) for line in target_lines] == [
        "#ff0000", "#0000ff", "#ff0000", "#0000ff", "#ff0000",
    ]
    assert [line.get_linestyle() for line in target_lines] == [
        "--", ":", "--", ":", "--",
    ]
    assert [line.get_marker() for line in target_lines] == [
        "o", "^", "o", "^", "o",
    ]
    assert [line.get_label() for line in target_lines] == [
        "target-0", "target-1", "target-2", "target-3", "target-4",
    ]


def test_constant_scatter_style_transfers_without_changing_offsets(make_tab):
    source = make_tab()
    source_scatter = source.ax.scatter(
        [1, 2], [3, 4], s=81, c="#00bcd4", edgecolors="#5d1049",
        linewidths=2.25, alpha=0.45, label="source scatter",
    )
    target = make_tab()
    target_scatter = target.ax.scatter(
        [10, 20, 30], [5, 6, 9], s=12, c="#ffd54f", edgecolors="black",
        linewidths=0.5, label="measurements",
    )
    offsets = target_scatter.get_offsets().copy()

    apply_graph_format(target, capture_graph_format(source))

    assert np.array_equal(target_scatter.get_offsets(), offsets)
    assert _hex(target_scatter.get_facecolors()[0]) == _hex(
        source_scatter.get_facecolors()[0]
    )
    assert _hex(target_scatter.get_edgecolors()[0]) == "#5d1049"
    assert target_scatter.get_sizes().tolist() == pytest.approx([81])
    assert target_scatter.get_linewidths().tolist() == pytest.approx([2.25])
    assert target_scatter.get_alpha() == pytest.approx(0.45)
    assert target_scatter.get_label() == "measurements"


def test_mapped_scatter_keeps_mapping_and_norm_while_adopting_source_cmap(make_tab):
    source = make_tab()
    source_values = np.array([0.0, 0.5, 1.0])
    source_scatter = source.ax.scatter(
        [0, 1, 2], [2, 1, 0], c=source_values, cmap="plasma",
    )
    source_scatter.set_clim(0.0, 1.0)

    target = make_tab()
    target_values = np.array([10.0, 20.0, 40.0, 80.0])
    target_scatter = target.ax.scatter(
        [3, 4, 5, 6], [1, 3, 2, 4], c=target_values,
        s=[10, 20, 30, 40], cmap="viridis",
    )
    target.layers = {
        "mapped": {
            "artists": [target_scatter], "style": "scatter",
            "kwargs": {"c": target_values.tolist(), "s": [10, 20, 30, 40],
                       "cmap": "viridis"},
            "meta": {},
        }
    }
    target_scatter.set_clim(5.0, 100.0)
    before_offsets = target_scatter.get_offsets().copy()
    before_array = target_scatter.get_array().copy()
    before_clim = target_scatter.get_clim()

    apply_graph_format(target, capture_graph_format(source))

    assert target_scatter.get_cmap().name == "plasma"
    assert np.array_equal(target_scatter.get_offsets(), before_offsets)
    assert np.array_equal(target_scatter.get_array(), before_array)
    assert target_scatter.get_clim() == pytest.approx(before_clim)
    assert target_scatter.get_sizes().tolist() == pytest.approx([10, 20, 30, 40])
    assert target.layers["mapped"]["kwargs"]["c"] == target_values.tolist()
    assert target.layers["mapped"]["kwargs"]["s"] == [10, 20, 30, 40]
    assert target.layers["mapped"]["kwargs"]["cmap"] == "plasma"


def test_persisted_format_is_strict_json_and_restores_semantic_effects(make_tab):
    source = make_tab()
    line, = source.ax.plot([0, 1, 2], [1, 4, 2], label="signal")
    apply_line_style(line, {
        "color": "#d81b60", "linewidth": 2.75,
        "glow": True, "glow_color": "#ffc107", "glow_width": 7.0,
        "glow_alpha": 0.42, "shadow": True, "shadow_alpha": 0.31,
        "fill": "under", "fill_color": "#4f9cf9", "fill_alpha": 0.2,
        "value_labels": True, "value_labels_every": 2,
    })
    apply_style(source.ax, {
        "effects": {
            "axes_shadow": True, "shadow_color": "#112233",
            "shadow_alpha": 0.4, "shadow_offset_x": 4.0,
            "shadow_offset_y": 5.0,
        },
        "tick_labels": {
            "enabled": True, "axis": "x", "notation": "decimal",
            "decimals_enabled": True, "decimals": 1, "divide_by": 2.0,
            "formula": "", "prefix": "[", "suffix": "]",
            "plus_sign": False, "minus_sign": True, "thousands": False,
        },
        "axes": {
            "refline_h": 3.0, "refline_v": None,
            "refline_h_label": "limit", "refline_v_label": "",
            "refline_color": "#009688", "refline_style": "--",
            "refline_width": 1.4, "refline_alpha": 0.8,
        },
    }, source.get_figure())
    source.ax.set_title("left", loc="left", color="#7b1fa2", fontsize=15)
    source.ax.legend(title="Measurements")

    snapshot = capture_persisted_graph_format(source)
    encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
    decoded = json.loads(encoded)
    assert "SimpleLineShadow" in encoded
    assert "SimplePatchShadow" in encoded

    target = make_tab()
    target_line, = target.ax.plot([0, 1, 2], [9, 8, 7], label="signal")
    target.ax.set_title("keep this text", loc="left")
    target.ax.legend(title="old")
    applied = apply_persisted_graph_format(target, decoded)

    assert applied == 1
    assert _hex(target_line.get_color()) == "#d81b60"
    assert target_line.get_linewidth() == pytest.approx(2.75)
    assert getattr(target_line, "_ps_effects")["glow"] is True
    assert getattr(target_line, "_ps_deco")["fill"] == "under"
    assert len(target_line.get_path_effects()) == 3
    assert getattr(target.ax, "_ps_tick_label_cfg")["divide_by"] == 2.0
    assert getattr(target.ax, "_ps_refline_cfg")["refline_h"] == 3.0
    assert any(item.get_gid() == "_ps_refline_h" for item in target.ax.lines)
    assert target.ax.get_title(loc="left") == "keep this text"
    assert target.ax._left_title.get_fontsize() == pytest.approx(15)
    assert target.ax.get_legend().get_title().get_text() == "Measurements"


def test_persisted_format_rejects_axes_projection_mismatch_before_mutation(make_tab):
    source = make_tab(projection="3d")
    source.ax.plot([0, 1], [0, 1], [0, 2], color="#e53935")
    snapshot = capture_persisted_graph_format(source)

    target = make_tab()
    line, = target.ax.plot([0, 1], [2, 3], color="#1976d2")
    before = _hex(line.get_color())
    with pytest.raises(ValueError, match="axes signature"):
        apply_persisted_graph_format(target, snapshot)
    assert _hex(line.get_color()) == before


def test_multicolour_bar_member_styles_round_trip_in_visual_order(make_tab):
    source = make_tab()
    bars = source.ax.bar([0, 1, 2], [2, 4, 3], label="groups")
    colors = ["#e53935", "#43a047", "#1e88e5"]
    hatches = ["/", "x", "o"]
    for patch, color, hatch in zip(bars.patches, colors, hatches):
        patch.set_facecolor(color)
        patch.set_hatch(hatch)
    source.layers = {"bars": {"artists": list(bars.patches), "style": "bar"}}

    target = make_tab()
    target_bars = target.ax.bar([10, 20, 30, 40, 50], [1, 2, 3, 4, 5], label="target")
    target.layers = {"bars": {"artists": list(target_bars.patches), "style": "bar"}}
    apply_graph_format(target, capture_graph_format(source))

    assert [_hex(patch.get_facecolor()) for patch in target_bars.patches] == [
        colors[0], colors[1], colors[2], colors[0], colors[1],
    ]
    assert [patch.get_hatch() for patch in target_bars.patches] == [
        "/", "x", "o", "/", "x",
    ]


def test_persisted_mapped_scatter_restores_norm_and_clim_only_for_project(make_tab):
    from matplotlib.colors import LogNorm

    source = make_tab()
    source_scatter = source.ax.scatter(
        [0, 1, 2], [1, 2, 3], c=[1.0, 10.0, 100.0], cmap="magma",
        norm=LogNorm(vmin=0.5, vmax=200.0),
    )
    source.layers = {"mapped": {"artists": [source_scatter], "style": "scatter"}}
    snapshot = capture_persisted_graph_format(source)

    target = make_tab()
    target_scatter = target.ax.scatter(
        [4, 5, 6], [3, 2, 1], c=[10.0, 20.0, 30.0], cmap="viridis",
    )
    target.layers = {"mapped": {"artists": [target_scatter], "style": "scatter"}}
    apply_persisted_graph_format(target, snapshot)

    assert isinstance(target_scatter.norm, LogNorm)
    assert target_scatter.get_clim() == pytest.approx((0.5, 200.0))
    assert target_scatter.get_cmap().name == "magma"


def test_project_restore_rejects_series_topology_before_styling_wrong_layer(make_tab):
    source = make_tab()
    first, = source.ax.plot([0, 1], [1, 2], color="#d62728", label="A")
    second, = source.ax.plot([0, 1], [2, 1], color="#1f77b4", label="B")
    source.layers = {
        "a": {"artists": [first], "label": "A", "style": "line"},
        "b": {"artists": [second], "label": "B", "style": "line"},
    }
    snapshot = capture_persisted_graph_format(source)

    target = make_tab()
    remaining, = target.ax.plot([0, 1], [9, 8], color="#2ca02c", label="B")
    target.layers = {
        "b": {"artists": [remaining], "label": "B", "style": "line"},
    }

    with pytest.raises(ValueError, match="series topology"):
        apply_persisted_graph_format(target, snapshot)
    assert _hex(remaining.get_color()) == "#2ca02c"


def test_runtime_exact_scatter_state_is_compact_and_transfer_clipboard_omits_it(make_tab):
    from core.graph_format_history import capture_graph_format_state

    tab = make_tab()
    count = 10_000
    colors = np.column_stack([
        np.linspace(0.0, 1.0, count),
        np.linspace(1.0, 0.0, count),
        np.full(count, 0.4),
        np.ones(count),
    ])
    sizes = np.linspace(5.0, 25.0, count)
    scatter = tab.ax.scatter(np.arange(count), np.arange(count), c=colors, s=sizes)
    tab.layers = {
        "points": {
            "artists": [scatter], "label": "Points", "style": "scatter",
            "kwargs": {"c": colors, "s": sizes}, "meta": {},
        }
    }

    runtime = capture_graph_format_state(tab)
    runtime_style = runtime["format"]["axes"][0]["series"][0]
    assert "members" not in runtime_style
    assert isinstance(runtime_style["facecolors"], np.ndarray)
    assert isinstance(runtime_style["marker_sizes"], np.ndarray)
    assert runtime_style["facecolors"].nbytes < 400_000
    assert runtime["layers"]["points"]["kwargs"]["c"] is colors

    transferable = capture_graph_format(tab)["axes"][0]["series"][0]
    assert "facecolors" not in transferable
    assert "marker_sizes" not in transferable
    assert "members" not in transferable


def test_persisted_scatter_alpha_array_is_json_safe_and_restored(make_tab):
    source = make_tab()
    alpha = np.array([0.2, 0.5, 0.9])
    scatter = source.ax.scatter(
        [0, 1, 2], [2, 1, 3], color="#7b1fa2", alpha=alpha, label="Points",
    )
    source.layers = {
        "points": {"artists": [scatter], "label": "Points", "style": "scatter"},
    }
    snapshot = capture_persisted_graph_format(source)
    encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False)

    target = make_tab()
    target_scatter = target.ax.scatter(
        [4, 5, 6], [1, 2, 1], color="#000000", label="Points",
    )
    target.layers = {
        "points": {
            "artists": [target_scatter], "label": "Points", "style": "scatter",
        },
    }
    apply_persisted_graph_format(target, json.loads(encoded))
    assert np.asarray(target_scatter.get_alpha()).tolist() == pytest.approx(alpha.tolist())


def test_symlog_norm_round_trip_preserves_nondefault_transform(make_tab):
    from matplotlib.colors import SymLogNorm

    source = make_tab()
    scatter = source.ax.scatter(
        [0, 1, 2], [1, 2, 3], c=[-8.0, 0.0, 8.0],
        norm=SymLogNorm(2.0, linscale=3.0, base=2.0, vmin=-16.0, vmax=16.0),
        label="Signal",
    )
    source.layers = {
        "signal": {"artists": [scatter], "label": "Signal", "style": "scatter"},
    }
    snapshot = capture_persisted_graph_format(source)

    target = make_tab()
    target_scatter = target.ax.scatter(
        [0, 1, 2], [3, 2, 1], c=[-1.0, 0.0, 1.0], label="Signal",
    )
    target.layers = {
        "signal": {
            "artists": [target_scatter], "label": "Signal", "style": "scatter",
        },
    }
    apply_persisted_graph_format(target, snapshot)

    assert isinstance(target_scatter.norm, SymLogNorm)
    transform = target_scatter.norm._trf
    assert transform.base == pytest.approx(2.0)
    assert transform.linscale == pytest.approx(3.0)
    assert transform.linthresh == pytest.approx(2.0)


def test_hidden_line_keeps_generated_decorations_hidden_after_paste(make_tab):
    source = make_tab()
    source_line, = source.ax.plot([0, 1, 2], [1, 3, 2], label="Signal")
    apply_line_style(source_line, {
        "fill": "under", "value_labels": True,
        "errorbar_mode": "constant", "errorbar_value": 0.2,
        "drop_lines": True, "label_extrema": True,
    })

    target = make_tab()
    target_line, = target.ax.plot([0, 1, 2], [4, 5, 3], label="Signal")
    target_line.set_visible(False)
    target.layers = {
        "signal": {
            "artists": [target_line], "label": "Signal", "style": "line",
            "visible": False,
        },
    }
    apply_graph_format(target, capture_graph_format(source))

    generated = [
        artist for group in (
            target.ax.lines, target.ax.collections, target.ax.texts,
            target.ax.patches, target.ax.images,
        )
        for artist in group
        if str(artist.get_gid() or "").startswith("_ps_")
    ]
    assert generated
    assert all(not artist.get_visible() for artist in generated)


def test_persisted_capture_uses_actual_scale_and_axes_effects_over_stale_metadata(make_tab):
    source = make_tab()
    source_line, = source.ax.plot([1, 2, 3], [2, 3, 4], label="Signal")
    source.layers = {
        "signal": {
            "artists": [source_line], "label": "Signal", "style": "line",
        },
    }
    source.ax.set_xscale("linear")
    source.ax._ps_scale_cfg = {"xscale": "log", "yscale": "log"}
    apply_style(source.ax, {
        "effects": {
            "axes_shadow": True, "shadow_color": "#000000",
            "shadow_alpha": 0.4, "shadow_offset_x": 3.0,
            "shadow_offset_y": 3.0,
        },
    }, source.get_figure())
    source.ax.patch.set_path_effects([])  # direct/manual edit after Plot Details

    snapshot = capture_persisted_graph_format(source)
    owned = snapshot["axes"][0]["owned"]
    assert owned["scale"]["xscale"] == "linear"
    assert owned["effects"]["axes_shadow"] is False

    target = make_tab()
    target_line, = target.ax.plot([1, 2, 3], [5, 4, 6], label="Signal")
    target.layers = {
        "signal": {
            "artists": [target_line], "label": "Signal", "style": "line",
        },
    }
    apply_persisted_graph_format(target, snapshot)
    assert target.ax.get_xscale() == "linear"
    assert target.ax.patch.get_path_effects() == []
    assert target.ax._ps_axes_effects["axes_shadow"] is False


def test_paste_clears_stale_axes_shadow_semantics_with_visual_effect(make_tab):
    source = make_tab()
    source.ax.plot([0, 1], [1, 2])

    target = make_tab()
    target.ax.plot([0, 1], [2, 1])
    apply_style(target.ax, {
        "effects": {
            "axes_shadow": True, "shadow_color": "#000000",
            "shadow_alpha": 0.3, "shadow_offset_x": 3.0,
            "shadow_offset_y": 3.0,
        },
    }, target.get_figure())
    assert target.ax._ps_axes_effects["axes_shadow"] is True

    apply_graph_format(target, capture_graph_format(source))

    assert target.ax.patch.get_path_effects() == []
    assert target.ax._ps_axes_effects["axes_shadow"] is False


def test_bar_container_is_one_logical_layer_and_all_patches_receive_style(make_tab):
    source = make_tab()
    source_bars = source.ax.bar(
        [0, 1, 2], [2, 5, 3], color="#ff8c00", edgecolor="#2f2f2f",
        linewidth=2.5, hatch="//", alpha=0.65, label="source bars",
    )
    source.layers = {
        "source-bars": {
            "artists": list(source_bars.patches),
            "style": "bar",
            "kwargs": {},
            "meta": {},
        }
    }

    target = make_tab()
    target_bars = target.ax.bar(
        [10, 20, 30, 40], [7, 6, 9, 4], color="#90caf9",
        label="target bars",
    )
    target.layers = {
        "target-bars": {
            "artists": list(target_bars.patches),
            "style": "bar",
            "kwargs": {"fc": "#90caf9", "lw": 0.5},
            "meta": {"style_kwargs": {"fc": "#90caf9", "lw": 0.5}},
        }
    }
    geometry = [(patch.get_x(), patch.get_width(), patch.get_height())
                for patch in target_bars.patches]

    snapshot = capture_graph_format(source)
    assert snapshot["series_count"] == 1
    assert apply_graph_format(target, snapshot) == 1

    assert [(patch.get_x(), patch.get_width(), patch.get_height())
            for patch in target_bars.patches] == geometry
    for patch in target_bars.patches:
        assert _hex(patch.get_facecolor()) == "#ff8c00"
        assert _hex(patch.get_edgecolor()) == "#2f2f2f"
        assert patch.get_linewidth() == pytest.approx(2.5)
        assert patch.get_hatch() == "//"
        assert patch.get_alpha() == pytest.approx(0.65)
    assert target_bars.get_label() == "target bars"
    assert target.layers["target-bars"]["kwargs"]["facecolor"] == "#ff8c00"
    assert "fc" not in target.layers["target-bars"]["kwargs"]
    assert "lw" not in target.layers["target-bars"]["kwargs"]
    assert target.layers["target-bars"]["meta"]["style_kwargs"]["hatch"] == "//"


def test_optimized_polycollection_bar_keeps_lod_payload_and_adopts_style(make_tab):
    from core.render_optimization import FAST_BAR_THRESHOLD, draw_bar_series

    count = FAST_BAR_THRESHOLD
    source = make_tab()
    source_artists, _ = draw_bar_series(
        source.ax, range(count), np.linspace(1, 5, count), label="source",
        facecolor="#6a4c93", edgecolor="#ffca3a", linewidth=1.75,
    )
    source.layers = {
        "source": {"artists": source_artists, "style": "bar", "kwargs": {}, "meta": {}}
    }
    target = make_tab()
    target_artists, _ = draw_bar_series(
        target.ax, range(count), np.linspace(50, 10, count), label="target",
        facecolor="#8ac926",
    )
    target.layers = {
        "target": {"artists": target_artists, "style": "bar", "kwargs": {}, "meta": {}}
    }
    target_artist = target_artists[0]
    before_y = list(target_artist._sciplotter_y_values)
    before_vertices = [path.vertices.copy() for path in target_artist.get_paths()]

    assert apply_graph_format(target, capture_graph_format(source)) == 1

    assert list(target_artist._sciplotter_y_values) == before_y
    assert all(np.array_equal(path.vertices, vertices)
               for path, vertices in zip(target_artist.get_paths(), before_vertices))
    assert _hex(target_artist.get_facecolors()[0]) == "#6a4c93"
    assert _hex(target_artist.get_edgecolors()[0]) == "#ffca3a"
    assert target_artist.get_label() == "target"


def test_explicit_print_format_is_deep_copied(make_tab):
    source = make_tab()
    source.ax.plot([0, 1], [0, 1])
    source._print_figure = {
        "width_in": 7.25,
        "height_in": 4.5,
        "dpi": 600,
        "metadata": {"profile": "journal"},
    }
    target = make_tab()
    target.ax.plot([0, 1], [1, 0])
    target._print_figure = {"width_in": 3.0, "height_in": 2.0, "dpi": 96}

    snapshot = capture_graph_format(source)
    apply_graph_format(target, snapshot)

    assert target._print_figure == source._print_figure
    assert target._print_figure is not source._print_figure
    assert target._print_figure["metadata"] is not source._print_figure["metadata"]
    snapshot["print_figure"]["metadata"]["profile"] = "mutated"
    assert target._print_figure["metadata"]["profile"] == "journal"


def test_secondary_axes_are_formatted_independently_without_copying_content(make_tab):
    source = make_tab()
    source_right = source.ax.twinx()
    source_left_line, = source.ax.plot([0, 1], [1, 2], color="#ef476f")
    source_right_line, = source_right.plot([0, 1], [10, 30], color="#118ab2")
    source.ax.set_facecolor("#fff4e6")
    source_right.spines["right"].set_color("#118ab2")
    source.layers = {
        "left": {"artists": [source_left_line], "style": "line", "kwargs": {}, "meta": {}},
        "right": {"artists": [source_right_line], "style": "line", "kwargs": {}, "meta": {}},
    }

    target = make_tab()
    target_right = target.ax.twinx()
    target_left_line, = target.ax.plot([2, 4], [4, 8], label="left target")
    target_right_line, = target_right.plot([2, 4], [100, 500], label="right target")
    target.ax.set_ylabel("Primary response")
    target_right.set_ylabel("Secondary response")
    target.ax.set_ylim(2, 9)
    target_right.set_ylim(50, 900)
    target.layers = {
        "left": {"artists": [target_left_line], "style": "line", "kwargs": {}, "meta": {}},
        "right": {"artists": [target_right_line], "style": "line", "kwargs": {}, "meta": {}},
    }
    before = (
        target.ax.get_ylabel(), target_right.get_ylabel(),
        target.ax.get_ylim(), target_right.get_ylim(),
    )

    snapshot = capture_graph_format(source)
    assert len(snapshot["axes"]) == 2
    assert snapshot["series_count"] == 2
    assert apply_graph_format(target, snapshot) == 2

    assert _hex(target_left_line.get_color()) == "#ef476f"
    assert _hex(target_right_line.get_color()) == "#118ab2"
    assert target_left_line.get_label() == "left target"
    assert target_right_line.get_label() == "right target"
    assert target.ax.get_ylabel() == before[0]
    assert target_right.get_ylabel() == before[1]
    assert target.ax.get_ylim() == pytest.approx(before[2])
    assert target_right.get_ylim() == pytest.approx(before[3])


def test_heatmap_copies_cmap_and_interpolation_not_array_extent_or_clim(make_tab):
    source = make_tab()
    source_image = source.ax.imshow(
        np.arange(9).reshape(3, 3), cmap="plasma", interpolation="nearest",
        extent=(0, 3, 0, 3), vmin=0, vmax=8,
    )
    target = make_tab()
    target_data = np.arange(16).reshape(4, 4) * 10
    target_image = target.ax.imshow(
        target_data, cmap="viridis", interpolation="bicubic",
        origin="upper", extent=(10, 20, -4, 4), vmin=20, vmax=120,
    )
    before = {
        "array": target_image.get_array().copy(),
        "extent": target_image.get_extent(),
        "clim": target_image.get_clim(),
        "origin": target_image.origin,
    }

    assert apply_graph_format(target, capture_graph_format(source)) == 1

    assert target_image.get_cmap().name == source_image.get_cmap().name
    assert target_image.get_interpolation() == "nearest"
    assert np.array_equal(target_image.get_array(), before["array"])
    assert target_image.get_extent() == before["extent"]
    assert target_image.get_clim() == pytest.approx(before["clim"])
    assert target_image.origin == before["origin"]


def test_3d_surface_copies_colormap_and_panes_but_keeps_z_content(make_tab):
    source = make_tab(projection="3d")
    sx, sy = np.meshgrid(np.linspace(-1, 1, 5), np.linspace(-1, 1, 5))
    source_surface = source.ax.plot_surface(sx, sy, sx ** 2 + sy ** 2, cmap="plasma")
    source.ax.zaxis.pane.set_facecolor("#ffe0b2")

    target = make_tab(projection="3d")
    tx, ty = np.meshgrid(np.linspace(10, 20, 6), np.linspace(30, 40, 6))
    target_values = np.sin(tx) + np.cos(ty)
    target_surface = target.ax.plot_surface(tx, ty, target_values, cmap="viridis")
    target.ax.set_zlabel("Measured intensity")
    target.ax.set_zlim(-5, 5)
    before_array = target_surface.get_array().copy()
    before_clim = target_surface.get_clim()

    assert apply_graph_format(target, capture_graph_format(source)) == 1

    assert target_surface.get_cmap().name == source_surface.get_cmap().name
    assert np.array_equal(target_surface.get_array(), before_array)
    assert target_surface.get_clim() == pytest.approx(before_clim)
    assert target.ax.get_zlabel() == "Measured intensity"
    assert target.ax.get_zlim() == pytest.approx((-5, 5))
    assert _hex(target.ax.zaxis.pane.get_facecolor()) == "#ffe0b2"


def test_invalid_snapshot_is_rejected_without_mutating_target(make_tab):
    target = make_tab()
    line, = target.ax.plot([1, 2], [3, 5], color="#123456")
    target.ax.set_title("Keep me")
    before = (_hex(line.get_color()), target.ax.get_title(), target.ax.get_xlim())

    invalid = {"version": 999, "axes": []}
    assert not is_graph_format_snapshot(invalid)
    with pytest.raises(ValueError, match="invalid|newer"):
        apply_graph_format(target, invalid)

    assert (_hex(line.get_color()), target.ax.get_title(), target.ax.get_xlim()) == before


def test_apply_rolls_back_appearance_when_a_mid_apply_adapter_fails(
    make_tab, monkeypatch,
):
    source = make_tab()
    source.ax.set_facecolor("#fff3e0")
    source.ax.plot([0, 1], [0, 1], color="#e65100", linewidth=5)

    target = make_tab()
    target.ax.set_facecolor("#e8f5e9")
    target_line, = target.ax.plot([0, 1], [1, 0], color="#1b5e20", linewidth=1.25)
    target.layers = {
        "line": {
            "artists": [target_line], "style": "line", "kwargs": {}, "meta": {},
        }
    }
    before = capture_graph_format(target)
    before_kwargs = copy.deepcopy(target.layers["line"]["kwargs"])
    before_meta = copy.deepcopy(target.layers["line"]["meta"])
    original_sync = format_clipboard._sync_layer_metadata
    calls = 0

    def fail_once(group):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic adapter failure")
        return original_sync(group)

    monkeypatch.setattr(format_clipboard, "_sync_layer_metadata", fail_once)
    with pytest.raises(RuntimeError, match="synthetic adapter failure"):
        apply_graph_format(target, capture_graph_format(source))

    restored = capture_graph_format(target)
    assert restored["figure_facecolor"] == before["figure_facecolor"]
    assert restored["axes"][0]["appearance"] == before["axes"][0]["appearance"]
    assert restored["axes"][0]["series"] == before["axes"][0]["series"]
    assert target.layers["line"]["kwargs"] == before_kwargs
    assert target.layers["line"]["meta"] == before_meta


def test_snapshot_is_detached_from_later_source_mutations(make_tab):
    source = make_tab()
    source_line, = source.ax.plot([0, 1], [0, 1], color="#aa0000")
    source._print_figure = {"width_in": 8, "height_in": 5, "dpi": 300}
    snapshot = capture_graph_format(source)
    frozen = copy.deepcopy(snapshot)

    source_line.set_color("#00aa00")
    source.ax.set_facecolor("black")
    source._print_figure["dpi"] = 72

    assert snapshot == frozen

    from matplotlib.artist import Artist

    def contains_artist(value):
        if isinstance(value, Artist):
            return True
        if isinstance(value, dict):
            return any(contains_artist(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(contains_artist(item) for item in value)
        return False

    assert not contains_artist(snapshot)
