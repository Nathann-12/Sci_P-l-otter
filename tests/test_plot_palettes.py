"""Scientific colour palettes + complete journal presets (decoration engine)."""
from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from core.plot_style import (
    COLORBLIND_SAFE_PALETTES,
    JOURNAL_PRESETS,
    SCIENTIFIC_PALETTES,
    apply_palette,
    get_preset_style,
    list_palettes,
    preset_palette,
)


def _axes_with_lines(n: int):
    fig = Figure()
    ax = fig.add_subplot(111)
    x = np.linspace(0, 10, 40)
    for i in range(n):
        ax.plot(x, np.sin(x) + i, label=f"series {i}")
    ax.legend()
    return ax


def test_apply_palette_recolours_every_series_in_order():
    ax = _axes_with_lines(3)
    count = apply_palette(ax, "Okabe-Ito (CB-safe)")
    assert count == 3
    expected = SCIENTIFIC_PALETTES["Okabe-Ito (CB-safe)"][:3]
    got = [line.get_color() for line in ax.get_lines()]
    assert [c.upper() for c in got] == [c.upper() for c in expected]


def test_apply_palette_cycles_when_more_series_than_colors_and_sets_width():
    palette = "Grayscale (print-safe)"  # 5 colours
    ax = _axes_with_lines(7)
    apply_palette(ax, palette, line_width=2.5)
    colors = SCIENTIFIC_PALETTES[palette]
    got = [c.upper() for c in (line.get_color() for line in ax.get_lines())]
    assert got[5].upper() == colors[0].upper()  # wrapped around
    assert all(line.get_linewidth() == 2.5 for line in ax.get_lines())


def test_apply_palette_tints_markers_and_keeps_legend_in_sync():
    ax = _axes_with_lines(2)
    for line in ax.get_lines():
        line.set_marker("o")
    apply_palette(ax, "Tol Bright (CB-safe)")
    first = ax.get_lines()[0]
    assert first.get_markerfacecolor().upper() == first.get_color().upper()
    legend = ax.get_legend()
    assert legend is not None
    # legend swatch colour now matches the recoloured line
    assert legend.legend_handles[0].get_color().upper() == first.get_color().upper()


def test_unknown_palette_raises():
    ax = _axes_with_lines(1)
    try:
        apply_palette(ax, "not a palette")
    except ValueError as exc:
        assert "unknown palette" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_list_palettes_leads_with_colorblind_safe_options():
    names = list_palettes()
    assert len(names) >= 6
    assert all(p in SCIENTIFIC_PALETTES for p in COLORBLIND_SAFE_PALETTES)
    # at least five verified colour-vision-deficiency-safe palettes
    assert len(COLORBLIND_SAFE_PALETTES) >= 5


def test_journal_presets_are_publication_complete_not_just_font_sizes():
    for name in ("Nature (single column)", "IEEE (single column)",
                 "Science (single column)", "ACS (single column)"):
        preset = get_preset_style(name)
        axes = preset["axes"]
        # complete styling: open frame, explicit tick direction, minor ticks
        assert axes["spine_top"] is False and axes["spine_right"] is False
        assert axes["tick_direction"] in ("in", "out", "inout")
        assert axes["minor_ticks"] is True
        # every journal preset ships a colour-safe palette + line width
        pal_name, line_width = preset_palette(name)
        assert pal_name in SCIENTIFIC_PALETTES
        assert isinstance(line_width, (int, float)) and line_width > 0


def test_nature_preset_is_colorblind_safe():
    pal_name, _ = preset_palette("Nature (single column)")
    assert pal_name in COLORBLIND_SAFE_PALETTES


def _contrast(c1: str, c2: str) -> float:
    import matplotlib.colors as mcolors

    def lum(c):
        r, g, b = mcolors.to_rgb(c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    hi, lo = sorted((lum(c1), lum(c2)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_every_preset_pins_readable_text_colors_on_its_background():
    """A preset that recolours the background must also pin the text colours.

    Regression: journal presets set a white background but left the dark-theme
    light-gray text in place, so labels/ticks washed out to near-invisible.
    """
    from core.plot_style import JOURNAL_PRESETS

    for name, preset in JOURNAL_PRESETS.items():
        axes = preset.get("axes", {})
        bg = preset.get("figure", {}).get("facecolor")
        assert bg, f"{name} has no facecolor"
        for key in ("title_color", "label_color", "tick_label_color"):
            color = axes.get(key)
            assert color, f"{name} does not pin {key}"
            ratio = _contrast(color, bg)
            assert ratio >= 3.0, f"{name}.{key}={color} washes out on {bg} ({ratio:.2f})"


def test_apply_style_recolors_legend_text_to_match_axis_text():
    """Legend text must track the axis text colour so it never washes out."""
    from core.plot_style import apply_style, get_preset_style

    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1], label="s")
    preset = get_preset_style("Science (single column)")
    preset.pop("palette", None)
    preset.pop("line_width", None)
    preset.setdefault("legend", {})["visible"] = True
    apply_style(ax, preset, fig)

    assert ax.title.get_color() == "#000000"
    assert ax.xaxis.get_ticklabels()[0].get_color() == "#000000"
    legend = ax.get_legend()
    assert legend is not None
    assert legend.get_texts()[0].get_color() == "#000000"
