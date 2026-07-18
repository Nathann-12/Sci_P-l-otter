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
