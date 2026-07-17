"""Tests for the Plot Details dialog + the plotstyle mixin end-to-end through
the real MainWindow (headless)."""
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

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from dialogs.plot_details_dialog import PlotDetailsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------------- dialog ----------------

def test_dialog_reads_back_edited_style(qapp):
    style = {
        "axes": {"title": "", "xlabel": "", "ylabel": "", "title_size": 12,
                 "label_size": 10, "tick_size": 10, "x_autoscale": True,
                 "xmin": 0, "xmax": 1, "y_autoscale": True, "ymin": 0, "ymax": 1,
                 "xscale": "linear", "yscale": "linear"},
        "grid": {"major": False}, "legend": {"visible": False},
        "figure": {"facecolor": "#1e2126"},
    }
    lines = [{"label": "s1", "color": "#112233", "linewidth": 1.0,
              "linestyle": "-", "marker": "None", "markersize": 6, "alpha": 1.0}]
    dlg = PlotDetailsDialog(style, lines)

    dlg.ed_title.setText("Result")
    dlg.ed_xlabel.setText("Time")
    dlg.chk_yauto.setChecked(False)
    dlg.sp_ymin.setValue(-5.0)
    dlg.sp_ymax.setValue(5.0)
    dlg.cb_yscale.setCurrentText("log")
    dlg.chk_grid.setChecked(True)
    dlg.chk_legend.setChecked(True)

    out = dlg.get_style()
    assert out["axes"]["title"] == "Result"
    assert out["axes"]["xlabel"] == "Time"
    assert out["axes"]["y_autoscale"] is False
    assert out["axes"]["ymin"] == -5.0 and out["axes"]["ymax"] == 5.0
    assert out["axes"]["yscale"] == "log"
    assert out["grid"]["major"] is True
    assert out["legend"]["visible"] is True


def test_dialog_edits_per_line_style(qapp):
    lines = [
        {"label": "a", "color": "#111111", "linewidth": 1.0, "linestyle": "-",
         "marker": "None", "markersize": 6, "alpha": 1.0},
        {"label": "b", "color": "#222222", "linewidth": 2.0, "linestyle": "--",
         "marker": "o", "markersize": 8, "alpha": 0.5},
    ]
    dlg = PlotDetailsDialog({"axes": {}, "grid": {}, "legend": {}, "figure": {}}, lines)

    # edit first curve
    dlg.sp_linewidth.setValue(4.0)
    dlg.cb_marker.setCurrentText("s")
    # switch to second curve then back — edits must persist
    dlg.cb_line.setCurrentIndex(1)
    dlg.cb_line.setCurrentIndex(0)
    result = dlg.get_line_styles()
    assert result[0]["linewidth"] == 4.0
    assert result[0]["marker"] == "s"
    assert result[1]["linestyle"] == "--"  # untouched curve keeps its style


def test_dialog_load_style_into_controls_and_template_list(qapp):
    dlg = PlotDetailsDialog(
        {"axes": {}, "grid": {}, "legend": {}, "figure": {}},
        [],
        template_names=["Base"],
    )

    dlg.set_template_names(["Base", "Paper"])
    assert dlg.cb_template.count() == 2
    assert dlg.btn_load_template.isEnabled() is True
    assert dlg.btn_delete_template.isEnabled() is True

    dlg.load_style_into_controls(
        {
            "axes": {
                "title": "Template Title",
                "xlabel": "Time",
                "ylabel": "Signal",
                "x_autoscale": False,
                "xmin": -1.0,
                "xmax": 5.0,
                "spine_top": False,
            },
            "tick_labels": {
                "enabled": True,
                "notation": "engineering",
                "formula": "2 * x",
            },
            "grid": {"major": True, "axis": "y"},
            "legend": {"visible": True, "title": "Curves"},
            "figure": {"width_in": 4.2, "dpi": 300},
            "effects": {"axes_shadow": True},
        }
    )

    out = dlg.get_style()
    assert out["axes"]["title"] == "Template Title"
    assert out["axes"]["xlabel"] == "Time"
    assert out["axes"]["ylabel"] == "Signal"
    assert out["axes"]["x_autoscale"] is False
    assert out["axes"]["xmin"] == -1.0 and out["axes"]["xmax"] == 5.0
    assert out["axes"]["spine_top"] is False
    assert out["tick_labels"]["enabled"] is True
    assert out["tick_labels"]["notation"] == "engineering"
    assert out["tick_labels"]["formula"] == "2 * x"
    assert out["grid"]["major"] is True
    assert out["grid"]["axis"] == "y"
    assert out["legend"]["visible"] is True
    assert out["legend"]["title"] == "Curves"
    assert out["figure"]["width_in"] == 4.2
    assert out["figure"]["dpi"] == 300
    assert out["effects"]["axes_shadow"] is True


# ---------------- mixin through MainWindow ----------------

@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    yield w
    w.close()


def _plot_something(win):
    df = pd.DataFrame({"t": [0.0, 1.0, 2.0, 3.0], "y": [1.0, 4.0, 9.0, 16.0]})
    win._stage_insert("g.csv [ตาราง]", df, None)
    win.plot_from_workbook("line")


def test_apply_plot_details_changes_the_axes(win):
    _plot_something(win)
    ax, fig, lines = win._active_graph_axes()
    assert ax is not None and lines

    style = {
        "axes": {"title": "Styled", "xlabel": "T", "ylabel": "Y",
                 "x_autoscale": False, "xmin": 0, "xmax": 5,
                 "yscale": "linear"},
        "grid": {"major": True, "color": "#3a3f44", "linestyle": "--", "alpha": 0.3},
        "legend": {"visible": True, "loc": "best", "fontsize": 10, "frame": True, "ncol": 1},
        "figure": {},
    }
    line_styles = [{"color": "#ff8800", "linewidth": 3.0, "linestyle": "-",
                    "marker": "o", "markersize": 7, "alpha": 1.0, "label": "curve"}]

    class _Dlg:
        def get_style(self): return style
        def get_line_styles(self): return line_styles

    win._apply_plot_details(ax, fig, lines, _Dlg())

    assert ax.get_title() == "Styled"
    assert ax.get_xlim() == (0.0, 5.0)
    assert lines[0].get_linewidth() == 3.0
    assert lines[0].get_marker() == "o"
    assert ax.get_legend() is not None


def test_apply_preset_does_not_shrink_onscreen_figure(win):
    """Regression for the 'apply preset squashes the graph' bug: a journal
    preset's tiny print size must NOT be applied to the live canvas."""
    _plot_something(win)
    ax, fig, lines = win._active_graph_axes()
    canvas = fig.canvas
    cw, ch = canvas.get_width_height()

    # a preset-style figure block (small print size) as the dialog would return
    style = {
        "axes": {"label_size": 8, "title_size": 9, "tick_size": 7},
        "grid": {}, "legend": {"visible": False},
        "figure": {"width_in": 3.5, "height_in": 2.6, "dpi": 300},
    }

    class _Dlg:
        def get_style(self): return style
        def get_line_styles(self): return [{}]

    win._apply_plot_details(ax, fig, lines, _Dlg())

    # figure now fills the canvas (fit-to-canvas at 100 dpi), not 3.5x2.6
    w_in, h_in = fig.get_size_inches()
    assert abs(w_in - cw / 100.0) < 0.5
    assert w_in > 3.5  # definitely not squashed to the print width
    # but the print size is remembered for export
    assert win.tabs.currentWidget()._print_figure["width_in"] == 3.5


def test_repeated_preset_apply_keeps_axes_fill_area(win, qapp):
    """Repeated Apply must NOT shrink the graph. The live canvas owns its own
    size (Qt/Matplotlib sync it, accounting for the display's devicePixelRatio);
    Apply only re-lays-out with tight_layout. So the figure size stays stable
    and the plot area stays large — no runaway shrink, and no HiDPI shrink from
    forcing set_size_inches() off Qt *logical* pixels."""
    _plot_something(win)
    ax, fig, lines = win._active_graph_axes()
    tab = win.tabs.currentWidget()
    tab.canvas.resize(720, 480)
    qapp.processEvents()

    style = {
        "axes": {"label_size": 8, "title_size": 9, "tick_size": 7},
        "grid": {},
        "legend": {"visible": False},
        "figure": {"width_in": 3.5, "height_in": 2.6, "dpi": 300},
    }

    class _Dlg:
        def get_style(self): return style
        def get_line_styles(self): return [{}]

    win._apply_plot_details(ax, fig, lines, _Dlg(), target_tab=tab)
    size_after_first = tuple(fig.get_size_inches())

    for _ in range(4):
        win._apply_plot_details(ax, fig, lines, _Dlg(), target_tab=tab)

    # the live figure size is stable across applies (never shrinks per-apply)
    size_after_many = tuple(fig.get_size_inches())
    assert abs(size_after_many[0] - size_after_first[0]) < 1e-6
    assert abs(size_after_many[1] - size_after_first[1]) < 1e-6
    # the tiny journal print size never leaked onto the live figure
    assert fig.get_size_inches()[0] > 3.5
    # and the plot area stays large (no squashed axes)
    pos = ax.get_position()
    assert pos.width > 0.45
    assert pos.height > 0.45
    # the print size is still remembered for export
    assert tab._print_figure["width_in"] == 3.5


def test_dialog_reads_back_advanced_decoration(qapp):
    dlg = PlotDetailsDialog(
        {
            "axes": {"spine_color": "#112233", "spine_width": 1.5},
            "grid": {},
            "legend": {"visible": True, "shadow": True, "fancybox": True},
            "figure": {"facecolor": "#ffffff", "fig_facecolor": "#eeeeee"},
            "effects": {"axes_shadow": True, "shadow_alpha": 0.4},
        },
        [{"label": "a", "color": "#111111", "linewidth": 1.0}],
    )

    dlg.chk_lineglow.setChecked(True)
    dlg.chk_lineshadow.setChecked(True)
    style = dlg.get_style()
    line_style = dlg.get_line_styles()[0]

    assert style["axes"]["spine_color"] == "#112233"
    assert style["legend"]["shadow"] is True
    assert style["effects"]["axes_shadow"] is True
    assert line_style["glow"] is True
    assert line_style["shadow"] is True


def _full_seed():
    """A full style + line-style dict as read_style/read_line_style would produce."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from core.plot_style import read_style, read_line_style
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9], label="series")
    style = read_style(ax, fig)
    lines = [read_line_style(ax.get_lines()[0])]
    plt.close(fig)
    return style, lines


def test_dialog_reads_back_new_advanced_controls(qapp):
    style, lines = _full_seed()
    dlg = PlotDetailsDialog(style, lines)

    # --- axes typography / ticks / spines / reflines ---
    dlg.btn_titlecolor.setColor(QColor("#abcdef"))
    dlg.chk_titlebold.setChecked(True)
    dlg.chk_titleital.setChecked(True)
    dlg.btn_labelcolor.setColor(QColor("#123456"))
    dlg.chk_labelbold.setChecked(True)
    dlg.cb_fontfamily.setCurrentText("serif")
    dlg.sp_labelpad.setValue(12.0)
    dlg.sp_ticklength.setValue(6.0)
    dlg.sp_tickwidth.setValue(1.5)
    dlg.btn_tickcolor.setColor(QColor("#0a0b0c"))
    dlg.btn_ticklabelcolor.setColor(QColor("#0d0e0f"))
    dlg.sp_tickxrot.setValue(45.0)
    dlg.chk_minorticks.setChecked(True)
    dlg.chk_mirrorticks.setChecked(True)
    dlg.chk_scinote.setChecked(True)
    dlg.chk_spinetop.setChecked(False)
    dlg.chk_spineright.setChecked(False)
    dlg.chk_reflineh.setChecked(True)
    dlg.sp_reflineh.setValue(3.14)
    dlg.ed_reflinehlabel.setText("limit")
    dlg.chk_reflinev.setChecked(False)  # stays None
    dlg.ed_reflinevlabel.setText("event")
    dlg.btn_reflinecolor.setColor(QColor("#ff0000"))
    dlg.cb_reflinestyle.setCurrentText(":")
    dlg.sp_reflinewidth.setValue(2.4)
    dlg.sp_reflinealpha.setValue(0.55)

    # --- tick-label display ---
    dlg.chk_ticklabeloverride.setChecked(True)
    dlg.cb_ticklabelaxis.setCurrentText("y")
    dlg.cb_ticklabelnotation.setCurrentText("decimal")
    dlg.chk_ticklabeldecimals.setChecked(True)
    dlg.sp_ticklabeldecimals.setValue(1)
    dlg.chk_ticklabelthousands.setChecked(True)
    dlg.sp_ticklabeldivide.setValue(1000.0)
    dlg.ed_ticklabelprefix.setText("$")
    dlg.ed_ticklabelsuffix.setText("k")
    dlg.chk_ticklabelplus.setChecked(True)
    dlg.chk_ticklabelminus.setChecked(False)

    # --- grid (minor styling) ---
    dlg.cb_gridaxis.setCurrentText("x")
    dlg.sp_gridwidth.setValue(1.25)
    dlg.btn_gridmincolor.setColor(QColor("#010203"))
    dlg.cb_gridminstyle.setCurrentText("-.")
    dlg.sp_gridminwidth.setValue(0.75)
    dlg.sp_gridminalpha.setValue(0.2)

    # --- legend extras ---
    dlg.ed_legtitle.setText("Legend Title")
    dlg.sp_legtitlesize.setValue(13.0)
    dlg.sp_legcolspacing.setValue(3.5)
    dlg.sp_leglabelspacing.setValue(1.25)
    dlg.sp_legmarkerscale.setValue(2.0)
    dlg.sp_legborderpad.setValue(1.5)
    dlg.sp_leghandlelen.setValue(4.0)

    # --- per-line marker/draw/zorder ---
    dlg.btn_mfc.setColor(QColor("#aa1122"))
    dlg.btn_mec.setColor(QColor("#22aa11"))
    dlg.sp_mew.setValue(2.5)
    dlg.cb_fillstyle.setCurrentText("left")
    dlg.cb_drawstyle.setCurrentText("steps-mid")
    dlg.sp_zorder.setValue(7.0)

    s = dlg.get_style()
    ax = s["axes"]
    assert ax["title_color"] == "#abcdef"
    assert ax["title_bold"] is True and ax["title_italic"] is True
    assert ax["label_color"] == "#123456" and ax["label_bold"] is True
    assert ax["font_family"] == "serif"
    assert ax["label_pad"] == 12.0
    assert ax["tick_length"] == 6.0 and ax["tick_width"] == 1.5
    assert ax["tick_color"] == "#0a0b0c" and ax["tick_label_color"] == "#0d0e0f"
    assert ax["tick_x_rotation"] == 45.0
    assert ax["minor_ticks"] is True and ax["mirror_ticks"] is True
    assert ax["sci_notation"] is True
    assert ax["spine_top"] is False and ax["spine_right"] is False
    assert ax["spine_left"] is True and ax["spine_bottom"] is True
    assert ax["refline_h"] == 3.14
    assert ax["refline_v"] is None  # disabled → None
    assert ax["refline_color"] == "#ff0000" and ax["refline_style"] == ":"
    assert ax["refline_h_label"] == "limit" and ax["refline_v_label"] == "event"
    assert ax["refline_width"] == 2.4 and ax["refline_alpha"] == 0.55

    tick_labels = s["tick_labels"]
    assert tick_labels["enabled"] is True
    assert tick_labels["axis"] == "y"
    assert tick_labels["notation"] == "decimal"
    assert tick_labels["decimals_enabled"] is True
    assert tick_labels["decimals"] == 1
    assert tick_labels["divide_by"] == 1000.0
    assert tick_labels["prefix"] == "$" and tick_labels["suffix"] == "k"
    assert tick_labels["plus_sign"] is True and tick_labels["minus_sign"] is False
    assert tick_labels["thousands"] is True

    g = s["grid"]
    assert g["axis"] == "x"
    assert g["linewidth"] == 1.25
    assert g["minor_color"] == "#010203"
    assert g["minor_linestyle"] == "-."
    assert g["minor_linewidth"] == 0.75
    assert g["minor_alpha"] == 0.2

    leg = s["legend"]
    assert leg["title"] == "Legend Title"
    assert leg["title_size"] == 13.0
    assert leg["columnspacing"] == 3.5
    assert leg["labelspacing"] == 1.25
    assert leg["markerscale"] == 2.0
    assert leg["borderpad"] == 1.5
    assert leg["handlelength"] == 4.0

    line = dlg.get_line_styles()[0]
    assert line["markerfacecolor"] == "#aa1122"
    assert line["markeredgecolor"] == "#22aa11"
    assert line["markeredgewidth"] == 2.5
    assert line["fillstyle"] == "left"
    assert line["drawstyle"] == "steps-mid"
    assert line["zorder"] == 7.0


def test_dialog_output_roundtrips_through_engine(qapp):
    """get_style()/get_line_styles() must feed straight back into the engine
    without raising, including a full canvas draw."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from core.plot_style import (
        apply_line_style, apply_style, read_line_style, read_style,
    )

    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9], label="series")
    seed_style = read_style(ax, fig)
    seed_lines = [read_line_style(ln) for ln in ax.get_lines()]
    dlg = PlotDetailsDialog(seed_style, seed_lines)

    # touch a representative subset across every group
    dlg.chk_titlebold.setChecked(True)
    dlg.sp_labelpad.setValue(10.0)
    dlg.chk_minorticks.setChecked(True)
    dlg.chk_mirrorticks.setChecked(True)
    dlg.chk_reflineh.setChecked(True)
    dlg.sp_reflineh.setValue(2.0)
    dlg.ed_reflinehlabel.setText("cutoff")
    dlg.chk_ticklabeloverride.setChecked(True)
    dlg.cb_ticklabelaxis.setCurrentText("y")
    dlg.cb_ticklabelnotation.setCurrentText("engineering")
    dlg.chk_grid.setChecked(True)
    dlg.chk_gridminor.setChecked(True)
    dlg.cb_gridaxis.setCurrentText("y")
    dlg.chk_legend.setChecked(True)
    dlg.ed_legtitle.setText("Curves")
    dlg.cb_drawstyle.setCurrentText("steps-post")
    dlg.cb_fillstyle.setCurrentText("top")
    dlg.sp_zorder.setValue(5.0)

    out_style = dlg.get_style()
    out_lines = dlg.get_line_styles()

    apply_style(ax, out_style, fig)
    for ln, d in zip(ax.get_lines(), out_lines):
        apply_line_style(ln, d)
    fig.canvas.draw()  # must not raise

    assert ax.get_lines()[0].get_zorder() == 5.0
    assert ax.get_lines()[0].get_drawstyle() == "steps-post"
    # horizontal reference line was drawn
    assert any(getattr(ln, "get_gid", lambda: None)() == "_ps_refline_h"
               for ln in ax.lines)
    assert any(getattr(txt, "get_gid", lambda: None)() == "_ps_refline_h_label"
               and txt.get_text() == "cutoff"
               for txt in ax.texts)
    plt.close(fig)


def test_format_action_wired(win):
    assert callable(getattr(win, "open_plot_details_dialog", None))
    assert hasattr(win, "actFormatGraph")
    # Graph Data / Ctrl+Plot Details double-click binding is present.
    win.tabs.add_tab()
    win.bind_graph_dblclick()
    tab = win.tabs.currentWidget()
    assert getattr(tab.canvas, "_plotdetails_bound", False) is True


def test_open_plot_details_on_empty_graph_is_polite(win, monkeypatch):
    infos = []
    monkeypatch.setattr(type(win), "inform",
                        lambda self, t, x: infos.append(t), raising=False)
    win.open_plot_details_dialog()  # no curves yet
    assert infos  # informed, did not crash


def test_scale_tab_and_formula_roundtrip(qapp):
    """Origin Scale tab (anchor/minor-counts/margin) + tick-label Formula come
    back from get_style() under the right keys."""
    import matplotlib.pyplot as plt
    from core.plot_style import read_style, apply_style

    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [0, 1, 0], label="s")
    style = read_style(ax, fig)
    dlg = PlotDetailsDialog(style, [], template_names=[])

    # Scale tab controls
    dlg.chk_xauto.setChecked(False)
    dlg.sp_xmin.setValue(-0.1)
    dlg.sp_xmax.setValue(2.1)
    dlg.sp_xmajor.setValue(0.5)
    dlg.chk_xanchor.setChecked(True)
    dlg.sp_xanchor.setValue(0.25)
    dlg.sp_xminorcount.setValue(1)
    dlg.sp_xmargin.setValue(3.0)
    # Formula on the Tick Labels tab
    dlg.chk_ticklabeloverride.setChecked(True)
    dlg.ed_ticklabelformula.setText("2 * x")

    s = dlg.get_style()
    assert s["axes"]["xmin"] == -0.1 and s["axes"]["xmax"] == 2.1
    assert s["axes"]["x_major_spacing"] == 0.5
    assert s["axes"]["x_anchor_tick"] == 0.25
    assert s["axes"]["x_minor_count"] == 1
    assert s["axes"]["x_rescale_margin"] == 3.0
    assert s["tick_labels"]["formula"] == "2 * x"

    # anchor disabled → None (0.0 is a legitimate anchor, so use the toggle)
    dlg.chk_xanchor.setChecked(False)
    assert dlg.get_style()["axes"]["x_anchor_tick"] is None

    # the full dialog output applies + renders without raising
    apply_style(ax, s, fig, live=True)
    fig.canvas.draw()
    ticks = [round(t, 4) for t in ax.xaxis.get_majorticklocs() if -0.1 <= t <= 2.1]
    assert ticks == [0.25, 0.75, 1.25, 1.75]
    plt.close(fig)
    dlg.close()


# ---------------- decoration stability (diff-apply contract) ----------------

def _open_real_dialog_for(win):
    """Plot data through the real window and build the dialog exactly like
    open_plot_details_dialog does (read_style seed + internal baseline)."""
    from core.plot_style import read_style, read_line_style
    _plot_something(win)
    ax, fig, lines = win._active_graph_axes()
    style = read_style(ax, fig)
    dlg = PlotDetailsDialog(style, [read_line_style(ln) for ln in lines],
                            template_names=[])
    return ax, fig, lines, dlg


def _visual_state(ax, fig):
    return {
        "n_lines": len([l for l in ax.lines
                        if not (l.get_gid() or "").startswith("_ps")]),
        "xlim": ax.get_xlim(), "ylim": ax.get_ylim(),
        "xscale": ax.get_xscale(), "yscale": ax.get_yscale(),
        "axfc": ax.get_facecolor(), "figfc": fig.get_facecolor(),
        "fmt_y": type(ax.yaxis.get_major_formatter()).__name__,
    }


def test_identity_apply_is_a_visual_noop(win):
    """Opening Plot Details and pressing Apply without touching ANY control
    must not change the graph at all — the decisive fix for 'changing one
    thing blanked my graph' (untouched seeds can never restyle)."""
    ax, fig, lines, dlg = _open_real_dialog_for(win)
    before = _visual_state(ax, fig)
    win._apply_plot_details(ax, fig, lines, dlg, target_tab=win.tabs.currentWidget())
    fig.canvas.draw()
    after = _visual_state(ax, fig)
    assert after == before


def test_changing_only_title_color_touches_nothing_else(win):
    import matplotlib.colors as mcolors
    ax, fig, lines, dlg = _open_real_dialog_for(win)
    before = _visual_state(ax, fig)

    dlg.btn_titlecolor.setColor(QColor("#ff2200"))
    win._apply_plot_details(ax, fig, lines, dlg, target_tab=win.tabs.currentWidget())
    fig.canvas.draw()

    # the edited property landed…
    assert mcolors.to_hex(ax.title.get_color()) == "#ff2200"
    # …and nothing else moved: data line, limits, scales, colors all intact
    assert _visual_state(ax, fig) == before


def test_revert_after_apply_applies_again(win):
    """Re-baselining after each Apply: change → Apply → change back → Apply
    must restore the original look (diff is against the last applied state)."""
    import matplotlib.colors as mcolors
    ax, fig, lines, dlg = _open_real_dialog_for(win)
    original = mcolors.to_hex(ax.title.get_color())

    dlg.btn_titlecolor.setColor(QColor("#ff2200"))
    win._apply_plot_details(ax, fig, lines, dlg, target_tab=win.tabs.currentWidget())
    assert mcolors.to_hex(ax.title.get_color()) == "#ff2200"

    dlg.btn_titlecolor.setColor(QColor(original))
    win._apply_plot_details(ax, fig, lines, dlg, target_tab=win.tabs.currentWidget())
    assert mcolors.to_hex(ax.title.get_color()) == original


def test_loading_template_updates_dialog_state_before_apply(win, monkeypatch):
    ax, fig, lines, dlg = _open_real_dialog_for(win)
    template_style = {
        "axes": {"title": "Template Title", "xlabel": "Elapsed"},
        "grid": {"major": True},
        "legend": {"visible": False},
        "figure": {"facecolor": "#f8f8f8"},
    }

    from core import plot_templates

    monkeypatch.setattr(plot_templates, "load_template", lambda name: template_style)
    win._load_plot_template_into_dialog(
        dlg,
        "Paper",
        ax=ax,
        fig=fig,
        lines=lines,
        target_tab=win.tabs.currentWidget(),
    )

    assert dlg.get_style()["axes"]["title"] == "Template Title"
    assert dlg.get_style()["axes"]["xlabel"] == "Elapsed"
    assert ax.get_title() == "Template Title"
    assert ax.get_xlabel() == "Elapsed"

    before = _visual_state(ax, fig)
    win._apply_plot_details(ax, fig, lines, dlg, target_tab=win.tabs.currentWidget())
    fig.canvas.draw()
    assert _visual_state(ax, fig) == before
