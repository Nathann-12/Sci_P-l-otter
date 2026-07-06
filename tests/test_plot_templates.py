"""Tests for journal presets, custom ticks (core.plot_style) and the template
store (core.plot_templates)."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.plot_style import (
    JOURNAL_PRESETS,
    apply_style,
    get_preset_style,
    read_style,
)
from core import plot_templates


@pytest.fixture()
def axfig():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2, 3, 4], [0, 1, 4, 9, 16], label="s")
    yield ax, fig
    plt.close(fig)


# ---------------- journal presets ----------------

def test_presets_exist_and_have_sizes():
    assert "IEEE (single column)" in JOURNAL_PRESETS
    for name, preset in JOURNAL_PRESETS.items():
        assert "figure" in preset and "width_in" in preset["figure"]
        assert "axes" in preset and "label_size" in preset["axes"]


def test_get_preset_style_is_a_copy():
    a = get_preset_style("IEEE (single column)")
    a["figure"]["width_in"] = 99
    b = get_preset_style("IEEE (single column)")
    assert b["figure"]["width_in"] != 99
    with pytest.raises(ValueError):
        get_preset_style("nope")


def test_preset_sets_fonts_but_not_figure_size_when_live(axfig):
    ax, fig = axfig
    w0, h0 = fig.get_size_inches()
    apply_style(ax, get_preset_style("IEEE (single column)"), fig, live=True)
    # live (on-screen) must NOT resize the figure — that squashes an embedded
    # Qt canvas; only fonts change
    assert tuple(fig.get_size_inches()) == (w0, h0)
    assert ax.xaxis.label.get_fontsize() == 8


def test_preset_applies_figure_size_for_export(axfig):
    ax, fig = axfig
    apply_style(ax, get_preset_style("IEEE (single column)"), fig, live=False)
    w, h = fig.get_size_inches()
    assert round(w, 2) == 3.5


# ---------------- custom ticks ----------------

def test_custom_major_and_minor_tick_spacing(axfig):
    ax, fig = axfig
    apply_style(ax, {"axes": {"x_autoscale": False, "xmin": 0, "xmax": 4,
                              "x_major_spacing": 1.0, "x_minor_spacing": 0.25}})
    from matplotlib.ticker import MultipleLocator
    assert isinstance(ax.xaxis.get_major_locator(), MultipleLocator)
    majors = [t for t in ax.xaxis.get_majorticklocs() if 0 <= t <= 4]
    assert majors == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert isinstance(ax.xaxis.get_minor_locator(), MultipleLocator)


def test_zero_spacing_leaves_auto(axfig):
    ax, fig = axfig
    from matplotlib.ticker import MultipleLocator
    apply_style(ax, {"axes": {"x_major_spacing": 0, "x_minor_spacing": None}})
    assert not isinstance(ax.xaxis.get_major_locator(), MultipleLocator)


def test_read_style_captures_figure_size(axfig):
    ax, fig = axfig
    fig.set_size_inches(5.0, 3.0)
    s = read_style(ax, fig)
    assert round(s["figure"]["width_in"], 2) == 5.0
    assert round(s["figure"]["height_in"], 2) == 3.0


# ---------------- template store ----------------

def test_save_load_list_delete_roundtrip(tmp_path):
    style = {"axes": {"title": "T", "yscale": "log"}, "grid": {"major": True}}
    path = plot_templates.save_template("My Style", style, directory=tmp_path)
    assert path.exists()
    assert "My Style" in plot_templates.list_templates(directory=tmp_path)

    loaded = plot_templates.load_template("My Style", directory=tmp_path)
    assert loaded == style

    assert plot_templates.delete_template("My Style", directory=tmp_path) is True
    assert "My Style" not in plot_templates.list_templates(directory=tmp_path)


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        plot_templates.load_template("ghost", directory=tmp_path)


def test_name_is_sanitised(tmp_path):
    plot_templates.save_template("a/b:c*?", {"axes": {}}, directory=tmp_path)
    files = list(Path(tmp_path).glob("*.json"))
    assert len(files) == 1
    assert "/" not in files[0].name and ":" not in files[0].name


def test_template_applied_to_axes(tmp_path, axfig):
    ax, fig = axfig
    plot_templates.save_template(
        "log-grid", {"axes": {"yscale": "log", "title": "Z"},
                     "grid": {"major": True}}, directory=tmp_path)
    tpl = plot_templates.load_template("log-grid", directory=tmp_path)
    apply_style(ax, tpl, fig)
    assert ax.get_yscale() == "log"
    assert ax.get_title() == "Z"
