"""Behavioral tests for core.plot_style (Origin-style graph customization)."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.plot_style import (
    apply_line_style,
    apply_style,
    read_line_style,
    read_style,
)


@pytest.fixture()
def ax():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9], label="series")
    yield ax
    plt.close(fig)


def test_apply_titles_labels_and_fonts(ax):
    apply_style(ax, {"axes": {
        "title": "My Graph", "title_size": 16,
        "xlabel": "Time (s)", "ylabel": "Signal", "label_size": 13}})
    assert ax.get_title() == "My Graph"
    assert ax.title.get_fontsize() == 16
    assert ax.get_xlabel() == "Time (s)"
    assert ax.get_ylabel() == "Signal"
    assert ax.xaxis.label.get_fontsize() == 13


def test_manual_limits_and_invert(ax):
    apply_style(ax, {"axes": {
        "x_autoscale": False, "xmin": 0, "xmax": 10,
        "y_autoscale": False, "ymin": 0, "ymax": 100, "invert_y": True}})
    assert ax.get_xlim() == (0.0, 10.0)
    # inverted y → hi, lo order
    ylo, yhi = ax.get_ylim()
    assert ylo == 100.0 and yhi == 0.0


def test_log_scale(ax):
    apply_style(ax, {"axes": {"yscale": "log"}})
    assert ax.get_yscale() == "log"
    apply_style(ax, {"axes": {"yscale": "linear"}})
    assert ax.get_yscale() == "linear"


def test_grid_major_toggle_and_color(ax):
    apply_style(ax, {"grid": {"major": True, "color": "#ff0000",
                              "linestyle": "--", "alpha": 0.5}})
    gl = ax.get_xgridlines()
    assert any(g.get_visible() for g in gl)
    apply_style(ax, {"grid": {"major": False}})
    assert not any(g.get_visible() for g in ax.get_xgridlines())


def test_legend_show_hide(ax):
    apply_style(ax, {"legend": {"visible": True, "loc": "upper left",
                                "fontsize": 12, "frame": False}})
    leg = ax.get_legend()
    assert leg is not None and leg.get_visible()
    apply_style(ax, {"legend": {"visible": False}})
    assert ax.get_legend() is None or not ax.get_legend().get_visible()


def test_read_apply_roundtrip(ax):
    apply_style(ax, {"axes": {"title": "T", "xlabel": "X", "ylabel": "Y",
                              "x_autoscale": False, "xmin": -1, "xmax": 5,
                              "yscale": "log"},
                     "grid": {"major": True}})
    captured = read_style(ax, ax.figure)
    # apply the captured style to a fresh axes → same key properties
    fig2, ax2 = plt.subplots()
    ax2.plot([1, 2], [1, 2], label="s")
    apply_style(ax2, captured, fig2)
    assert ax2.get_title() == "T"
    assert ax2.get_xlabel() == "X"
    assert ax2.get_yscale() == "log"
    assert ax2.get_xlim() == (-1.0, 5.0)
    plt.close(fig2)


def test_line_style_read_apply(ax):
    line = ax.get_lines()[0]
    apply_line_style(line, {"color": "#00ff00", "linewidth": 3.5,
                            "linestyle": "--", "marker": "o",
                            "markersize": 8, "alpha": 0.7, "label": "renamed"})
    assert line.get_linewidth() == 3.5
    assert line.get_linestyle() == "--"
    assert line.get_marker() == "o"
    assert line.get_markersize() == 8
    assert line.get_label() == "renamed"
    d = read_line_style(line)
    assert d["color"] == "#00ff00"
    assert d["linewidth"] == 3.5
    assert d["marker"] == "o"
    assert d["alpha"] == pytest.approx(0.7)


def test_apply_ignores_unknown_and_empty(ax):
    # must not raise on partial/empty styles
    apply_style(ax, {})
    apply_style(ax, {"axes": {}, "grid": {}, "legend": {}, "figure": {}})
    apply_style(ax, {"nonsense": {"x": 1}})


# ---------------- expanded OriginPro-level decoration ----------------

def test_title_and_label_typography(ax):
    apply_style(ax, {"axes": {
        "title": "T", "title_color": "#ff0000", "title_bold": True, "title_italic": True,
        "xlabel": "x", "ylabel": "y", "label_color": "#00aa00", "label_bold": True,
        "font_family": "serif", "label_pad": 9.0}})
    import matplotlib.colors as mcolors
    assert mcolors.to_hex(ax.title.get_color()) == "#ff0000"
    assert ax.title.get_fontweight() == "bold"
    assert ax.title.get_fontstyle() == "italic"
    assert mcolors.to_hex(ax.xaxis.label.get_color()) == "#00aa00"
    assert ax.xaxis.labelpad == 9.0


def test_tick_appearance_and_minor_and_rotation(ax):
    apply_style(ax, {"axes": {
        "tick_length": 7.0, "tick_width": 1.6, "tick_color": "#112233",
        "tick_label_color": "#445566", "tick_x_rotation": 45.0,
        "minor_ticks": True, "mirror_ticks": True, "tick_direction": "in"}})
    # minor ticks turned on
    assert ax.xaxis.get_minor_ticks()
    # x tick labels rotated
    assert any(abs(lbl.get_rotation() - 45.0) < 1e-6 for lbl in ax.get_xticklabels())


def test_per_side_spine_visibility(ax):
    apply_style(ax, {"axes": {"spine_top": False, "spine_right": False,
                              "spine_left": True, "spine_bottom": True}})
    assert ax.spines["top"].get_visible() is False
    assert ax.spines["right"].get_visible() is False
    assert ax.spines["left"].get_visible() is True


def test_reference_lines_added_and_not_stacked(ax):
    style = {"axes": {"refline_h": 4.0, "refline_v": 2.0,
                      "refline_color": "#ff00ff", "refline_style": ":"}}
    apply_style(ax, style)
    apply_style(ax, style)  # re-apply must not duplicate guides
    guides = [ln for ln in ax.lines if (ln.get_gid() or "").startswith("_ps_refline")]
    assert len(guides) == 2  # exactly one h + one v, not four


def test_reference_lines_support_labels_width_and_opacity(ax):
    apply_style(ax, {"axes": {
        "refline_h": 4.0,
        "refline_h_label": "upper limit",
        "refline_v": 2.0,
        "refline_v_label": "event",
        "refline_width": 2.5,
        "refline_alpha": 0.4,
    }})
    apply_style(ax, {"axes": {
        "refline_h": 4.0,
        "refline_h_label": "upper limit",
        "refline_v": 2.0,
        "refline_v_label": "event",
        "refline_width": 2.5,
        "refline_alpha": 0.4,
    }})
    guides = [ln for ln in ax.lines if (ln.get_gid() or "").startswith("_ps_refline")]
    labels = [t for t in ax.texts if (t.get_gid() or "").startswith("_ps_refline")]
    assert len(guides) == 2
    assert len(labels) == 2
    assert guides[0].get_linewidth() == 2.5
    assert guides[0].get_alpha() == 0.4
    assert {t.get_text() for t in labels} == {"upper limit", "event"}


def test_reference_lines_can_be_cleared(ax):
    apply_style(ax, {"axes": {"refline_h": 4.0}})
    assert any((ln.get_gid() or "") == "_ps_refline_h" for ln in ax.lines)
    apply_style(ax, {"axes": {"refline_h": None}})
    assert not any((ln.get_gid() or "") == "_ps_refline_h" for ln in ax.lines)


def test_tick_label_formatter_display_options(ax):
    apply_style(ax, {"tick_labels": {
        "enabled": True,
        "axis": "y",
        "notation": "decimal",
        "decimals_enabled": True,
        "decimals": 1,
        "divide_by": 1000.0,
        "prefix": "$",
        "suffix": "k",
        "plus_sign": True,
        "minus_sign": True,
        "thousands": True,
    }})
    fmt = ax.yaxis.get_major_formatter()

    assert fmt(2500000.0, 0) == "$+2,500.0k"
    assert fmt(-1250.0, 0) == "$-1.2k"


def test_tick_label_formatter_engineering_and_percent(ax):
    apply_style(ax, {"tick_labels": {
        "enabled": True,
        "axis": "x",
        "notation": "engineering",
        "decimals_enabled": True,
        "decimals": 2,
    }})
    assert ax.xaxis.get_major_formatter()(12000.0, 0) == "12.00k"

    apply_style(ax, {"tick_labels": {
        "enabled": True,
        "axis": "x",
        "notation": "percent",
        "decimals_enabled": True,
        "decimals": 0,
    }})
    assert ax.xaxis.get_major_formatter()(0.25, 0) == "25%"


def test_grid_minor_and_axis_and_widths(ax):
    apply_style(ax, {"grid": {
        "major": True, "minor": True, "axis": "y", "color": "#333333",
        "linewidth": 1.3, "minor_color": "#666666", "minor_linestyle": ":",
        "minor_linewidth": 0.4, "minor_alpha": 0.2}})
    # both major and minor gridlines exist on the y axis
    assert ax.yaxis.get_gridlines()
    assert ax.yaxis.get_minor_ticks()


def test_legend_title_and_spacing(ax):
    ax.plot([1, 2, 3], [2, 3, 4], label="second")
    apply_style(ax, {"legend": {
        "visible": True, "title": "My Series", "title_size": 12,
        "ncol": 2, "columnspacing": 3.0, "labelspacing": 0.9,
        "markerscale": 1.4, "borderpad": 0.6, "handlelength": 3.0}})
    leg = ax.get_legend()
    assert leg is not None
    assert leg.get_title().get_text() == "My Series"


def test_line_marker_face_edge_fill_draw_zorder(ax):
    line = ax.get_lines()[0]
    apply_line_style(line, {
        "marker": "o", "markerfacecolor": "#ff0000", "markeredgecolor": "#0000ff",
        "markeredgewidth": 2.0, "fillstyle": "left", "drawstyle": "steps-mid",
        "zorder": 6.0})
    import matplotlib.colors as mcolors
    assert mcolors.to_hex(line.get_markerfacecolor()) == "#ff0000"
    assert mcolors.to_hex(line.get_markeredgecolor()) == "#0000ff"
    assert line.get_markeredgewidth() == 2.0
    assert line.get_fillstyle() == "left"
    assert line.get_drawstyle() == "steps-mid"
    assert line.get_zorder() == 6.0
    # read back round-trips the new fields
    d = read_line_style(line)
    assert d["fillstyle"] == "left"
    assert d["drawstyle"] == "steps-mid"
    assert d["zorder"] == 6.0


def test_full_readback_roundtrip_renders(ax):
    """read_style → apply_style → real draw must not raise, and keeps the many
    new keys."""
    fig = ax.figure
    style = read_style(ax, fig)
    assert "title_color" in style["axes"]
    assert style["tick_labels"]["enabled"] is False
    assert "minor_linewidth" in style["grid"]
    assert "handlelength" in style["legend"]
    apply_style(ax, style, fig, live=True)
    fig.canvas.draw()  # must not raise


# ---------------- Origin Scale tab + tick-label Formula ----------------

def test_compile_tick_formula_arithmetic_and_safety():
    from core.plot_style import compile_tick_formula
    assert compile_tick_formula("2 * x")(5.0) == 10.0
    assert compile_tick_formula("x / 1000 + 1")(500.0) == pytest.approx(1.5)
    assert compile_tick_formula("sqrt(x)")(9.0) == pytest.approx(3.0)
    # anything beyond plain arithmetic is rejected, never executed
    assert compile_tick_formula("__import__('os').system('x')") is None
    assert compile_tick_formula("x.__class__") is None
    assert compile_tick_formula("open('f')") is None
    assert compile_tick_formula("") is None


def test_tick_label_formula_overrides_divide_by(ax):
    """Origin rule: 'Divide by Factor' is ignored when a Formula is used."""
    from core.plot_style import _format_tick_label
    cfg = {"enabled": True, "notation": "decimal", "decimals_enabled": True,
           "decimals": 1, "divide_by": 1000.0, "formula": "2 * x"}
    assert _format_tick_label(50.0, cfg) == "100.0"
    # broken formula falls back to divide-by
    cfg["formula"] = "not a formula ("
    assert _format_tick_label(50.0, cfg) == "0.1"


def test_major_anchor_tick_shifts_grid(ax):
    """Scale tab: By Increment 0.5 + Anchor 0.25 → ticks at 0.25, 0.75, ..."""
    ax.plot([0, 2], [0, 1])
    apply_style(ax, {"axes": {
        "x_autoscale": False, "xmin": -0.1, "xmax": 2.1,
        "x_major_spacing": 0.5, "x_anchor_tick": 0.25}})
    ax.figure.canvas.draw()
    ticks = [round(t, 4) for t in ax.xaxis.get_majorticklocs() if -0.1 <= t <= 2.1]
    assert ticks == [0.25, 0.75, 1.25, 1.75]


def test_minor_ticks_by_counts(ax):
    """Scale tab: Minor 'By Counts' = N minor ticks between adjacent majors."""
    ax.plot([0, 2], [0, 1])
    apply_style(ax, {"axes": {
        "x_autoscale": False, "xmin": 0.0, "xmax": 2.0,
        "x_major_spacing": 1.0, "x_minor_count": 3}})
    ax.figure.canvas.draw()
    minors = [t for t in ax.xaxis.get_minorticklocs() if 0.0 < t < 1.0]
    assert len(minors) == 3
    # an explicit minor increment wins over counts
    apply_style(ax, {"axes": {
        "x_autoscale": False, "xmin": 0.0, "xmax": 2.0,
        "x_major_spacing": 1.0, "x_minor_spacing": 0.5, "x_minor_count": 9}})
    ax.figure.canvas.draw()
    minors = [round(t, 4) for t in ax.xaxis.get_minorticklocs() if 0.0 < t < 1.0]
    assert minors == [0.5]


def test_rescale_margin_pads_autoscaled_limits(ax):
    ax.clear()
    ax.plot([0.0, 10.0], [0.0, 1.0])
    apply_style(ax, {"axes": {"x_autoscale": True, "x_rescale_margin": 3.0}})
    ax.figure.canvas.draw()
    lo, hi = ax.get_xlim()
    assert lo == pytest.approx(-0.3, abs=1e-6)
    assert hi == pytest.approx(10.3, abs=1e-6)


def test_read_style_exposes_scale_and_formula_defaults(ax):
    style = read_style(ax, ax.figure)
    for key in ("x_anchor_tick", "y_anchor_tick", "x_minor_count",
                "y_minor_count", "x_rescale_margin", "y_rescale_margin"):
        assert key in style["axes"]
    assert "formula" in style["tick_labels"]


# ---------------- diff_style (Plot Details stability contract) ----------------

def test_diff_style_empty_when_unchanged():
    from core.plot_style import diff_style
    style = {"axes": {"title": "T", "xmin": 0.0}, "grid": {"major": True},
             "legend": {"visible": False}, "figure": {"facecolor": "#111111"}}
    import copy
    assert diff_style(copy.deepcopy(style), copy.deepcopy(style)) == {}


def test_diff_style_reports_only_changes_and_groups():
    from core.plot_style import diff_style
    base = {"axes": {"title": "T", "title_color": "#ffffff",
                     "x_autoscale": True, "xmin": 0.0, "xmax": 1.0,
                     "invert_x": False, "x_rescale_margin": 5.0},
            "grid": {"major": False}, "legend": {"visible": False},
            "figure": {"facecolor": "#111111"}}
    cur = {"axes": {"title": "T", "title_color": "#ff0000",
                    "x_autoscale": True, "xmin": 0.0, "xmax": 1.0,
                    "invert_x": False, "x_rescale_margin": 5.0},
           "grid": {"major": False}, "legend": {"visible": False},
           "figure": {"facecolor": "#111111"}}
    d = diff_style(base, cur)
    assert d == {"axes": {"title_color": "#ff0000"}}
    # a range-group member change pulls the whole group (apply consistency)
    cur2 = {**cur, "axes": {**cur["axes"], "xmin": -1.0, "x_autoscale": False}}
    d2 = diff_style(base, cur2)
    assert set(d2["axes"]) >= {"x_autoscale", "xmin", "xmax", "invert_x",
                               "x_rescale_margin"}
    assert "title_color" in d2["axes"]  # still a per-key change


def test_disabling_tick_label_override_restores_scalar_formatter(ax):
    from matplotlib.ticker import ScalarFormatter
    apply_style(ax, {"tick_labels": {"enabled": True, "axis": "both",
                                     "notation": "decimal", "decimals_enabled": True,
                                     "decimals": 0}})
    assert getattr(ax.yaxis.get_major_formatter(), "_ps_tick_label_fmt", False)
    apply_style(ax, {"tick_labels": {"enabled": False}})
    assert isinstance(ax.yaxis.get_major_formatter(), ScalarFormatter)
    assert not getattr(ax.yaxis.get_major_formatter(), "_ps_tick_label_fmt", False)
