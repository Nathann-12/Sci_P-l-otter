"""Decoration engine: area fill, value labels, error bars, inset, colorbar."""
from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from core.plot_style import (
    COLORBAR_DEFAULTS,
    INSET_DEFAULTS,
    apply_line_style,
    apply_palette,
    apply_style,
    list_line_artists,
    read_line_style,
    read_style,
)


def _fig_axes(n_lines=2, points=120):
    fig = Figure()
    ax = fig.add_subplot(111)
    x = np.linspace(0, 10, points)
    for i in range(n_lines):
        ax.plot(x, np.sin(x) + i, label=f"s{i}")
    return fig, ax


def _gid_artists(ax, prefix):
    found = []
    for group in (ax.lines, ax.collections, ax.texts, ax.patches):
        found += [a for a in group if str(a.get_gid() or "").startswith(prefix)]
    return found


# ------------------------------------------------------------------ area fill

def test_fill_under_creates_one_artist_and_reapply_does_not_stack():
    _fig, ax = _fig_axes()
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d["fill"] = "under"
    apply_line_style(line, d)
    apply_line_style(line, d)
    assert len(_gid_artists(ax, "_ps_fill")) == 1


def test_fill_between_next_uses_the_following_curve_and_none_removes():
    _fig, ax = _fig_axes(n_lines=2)
    first = ax.get_lines()[0]
    d = read_line_style(first)
    d["fill"] = "between_next"
    apply_line_style(first, d)
    assert len(_gid_artists(ax, "_ps_fill")) == 1
    d["fill"] = "none"
    apply_line_style(first, d)
    assert len(_gid_artists(ax, "_ps_fill")) == 0


def test_fill_on_last_curve_with_no_next_is_a_quiet_no_op():
    _fig, ax = _fig_axes(n_lines=1)
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d["fill"] = "between_next"
    apply_line_style(line, d)  # must not raise
    assert len(_gid_artists(ax, "_ps_fill")) == 0


# --------------------------------------------------------------- value labels

def test_value_labels_every_n_and_format():
    _fig, ax = _fig_axes(n_lines=1, points=20)
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d.update(value_labels=True, value_labels_every=5, value_labels_fmt="%.2f")
    apply_line_style(line, d)
    labels = _gid_artists(ax, "_ps_vlab")
    assert len(labels) == 4  # 20 points, every 5th
    assert all("." in t.get_text() for t in labels)


def test_value_labels_auto_thin_on_dense_data_and_bad_format_falls_back():
    _fig, ax = _fig_axes(n_lines=1, points=1000)
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d.update(value_labels=True, value_labels_every=1, value_labels_fmt="%broken")
    apply_line_style(line, d)
    labels = _gid_artists(ax, "_ps_vlab")
    assert 0 < len(labels) <= 200  # never a wall of 1000 texts


# ----------------------------------------------------------------- error bars

def test_percent_errorbars_add_container_and_off_removes_cleanly():
    _fig, ax = _fig_axes(n_lines=1, points=30)
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d.update(errorbar_mode="percent", errorbar_value=10.0)
    apply_line_style(line, d)
    apply_line_style(line, d)  # re-apply must not stack or double-remove
    assert len([c for c in ax.containers if getattr(c, "_ps_gid", None)]) == 1
    # decoration artists never pollute the user's curve list
    assert len(list_line_artists(ax)) == 1
    d["errorbar_mode"] = "none"
    apply_line_style(line, d)
    assert len([c for c in ax.containers if getattr(c, "_ps_gid", None)]) == 0


def test_decoration_state_reads_back_from_the_artist():
    _fig, ax = _fig_axes(n_lines=1)
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d.update(fill="under", value_labels=True, errorbar_mode="constant",
             errorbar_value=0.5)
    apply_line_style(line, d)
    back = read_line_style(line)
    assert back["fill"] == "under"
    assert back["value_labels"] is True
    assert back["errorbar_mode"] == "constant"
    assert back["errorbar_value"] == 0.5


# ---------------------------------------------------------------------- inset

def test_inset_apply_copies_curves_zooms_and_disable_removes():
    fig, ax = _fig_axes(n_lines=2)
    apply_style(ax, {"inset": {**INSET_DEFAULTS, "enabled": True,
                               "xmin": 2.0, "xmax": 4.0}}, fig)
    axins = getattr(ax, "_ps_inset_ax", None)
    assert axins is not None
    assert len(axins.get_lines()) == 2
    assert axins.get_xlim() == (2.0, 4.0)
    assert len(getattr(ax, "_ps_inset_marks", ())) >= 1  # zoom indicator
    # state reads back so the dialog reopens showing reality
    assert read_style(ax, fig)["inset"]["enabled"] is True
    # re-apply replaces, never stacks (inset axes are children of the parent ax)
    apply_style(ax, {"inset": {**INSET_DEFAULTS, "enabled": True,
                               "xmin": 1.0, "xmax": 2.0}}, fig)
    insets = [a for a in ax.child_axes if a.get_gid() == "_ps_inset"]
    assert len(insets) == 1
    apply_style(ax, {"inset": dict(INSET_DEFAULTS)}, fig)
    assert getattr(ax, "_ps_inset_ax", None) is None
    assert [a for a in ax.child_axes if a.get_gid() == "_ps_inset"] == []


def test_inset_ignores_decoration_artists_when_copying():
    fig, ax = _fig_axes(n_lines=1)
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d.update(errorbar_mode="constant", errorbar_value=0.2)
    apply_line_style(line, d)  # adds _ps_ caplines to ax.lines
    apply_style(ax, {"inset": {**INSET_DEFAULTS, "enabled": True,
                               "xmin": 2.0, "xmax": 4.0}}, fig)
    assert len(ax._ps_inset_ax.get_lines()) == 1  # only the real curve


# ------------------------------------------------------------------- colorbar

def test_colorbar_sets_cmap_creates_and_removes():
    fig = Figure()
    ax = fig.add_subplot(111)
    image = ax.imshow(np.random.default_rng(0).random((5, 5)))
    apply_style(ax, {"colorbar": {**COLORBAR_DEFAULTS, "enabled": True,
                                  "cmap": "cividis", "label": "Z"}}, fig)
    assert image.get_cmap().name == "cividis"
    assert getattr(ax, "_ps_colorbar", None) is not None
    assert read_style(ax, fig)["colorbar"]["enabled"] is True
    apply_style(ax, {"colorbar": dict(COLORBAR_DEFAULTS)}, fig)
    assert getattr(ax, "_ps_colorbar", None) is None


def test_colorbar_on_line_plot_is_a_quiet_no_op():
    fig, ax = _fig_axes()
    apply_style(ax, {"colorbar": {**COLORBAR_DEFAULTS, "enabled": True,
                                  "cmap": "viridis"}}, fig)
    assert getattr(ax, "_ps_colorbar", None) is None


# ------------------------------------------------- palette respects ownership

def test_palette_does_not_recolor_decoration_artists():
    _fig, ax = _fig_axes(n_lines=2)
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d.update(errorbar_mode="constant", errorbar_value=0.2)
    apply_line_style(line, d)
    n = apply_palette(ax, "Okabe-Ito (CB-safe)")
    assert n == 2  # the two data curves only, not the error-bar caps


# ---------------------------------------- Origin-parity fill / drop / extrema

def _gid_all(ax, prefix):
    found = []
    for group in (ax.lines, ax.collections, ax.texts, ax.patches, ax.images):
        found += [a for a in group if str(a.get_gid() or "").startswith(prefix)]
    return found


def test_hatch_pattern_fill_is_applied_and_round_trips():
    _fig, ax = _fig_axes()
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d.update(fill="under", fill_hatch="//")
    apply_line_style(line, d)
    fills = _gid_all(ax, "_ps_fill")
    assert len(fills) == 1 and fills[0].get_hatch() == "//"
    assert read_line_style(line)["fill_hatch"] == "//"


def test_gradient_fill_adds_a_clipped_image_and_off_removes_it():
    fig, ax = _fig_axes()
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d.update(fill="under", fill_gradient=True)
    apply_line_style(line, d)
    # poly + gradient image, both tagged _ps_fill
    assert len(_gid_all(ax, "_ps_fill")) == 2
    assert any(a in ax.images for a in _gid_all(ax, "_ps_fill"))
    assert read_line_style(line)["fill_gradient"] is True
    d.update(fill="none", fill_gradient=False)
    apply_line_style(line, d)
    assert len(_gid_all(ax, "_ps_fill")) == 0


def test_drop_lines_add_one_collection_and_toggle_off_cleanly():
    _fig, ax = _fig_axes()
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d["drop_lines"] = True
    apply_line_style(line, d)
    apply_line_style(line, d)  # re-apply must not stack
    assert len(_gid_all(ax, "_ps_drop")) == 1
    assert read_line_style(line)["drop_lines"] is True
    d["drop_lines"] = False
    apply_line_style(line, d)
    assert len(_gid_all(ax, "_ps_drop")) == 0


def test_extrema_labels_mark_peak_and_valley():
    _fig, ax = _fig_axes(n_lines=1, points=50)
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d["label_extrema"] = True
    apply_line_style(line, d)
    artists = _gid_all(ax, "_ps_extrema")
    markers = [a for a in artists if a in ax.lines]
    labels = [a for a in artists if a in ax.texts]
    assert len(markers) == 2 and len(labels) == 2   # max + min, each marker+label
    d["label_extrema"] = False
    apply_line_style(line, d)
    assert len(_gid_all(ax, "_ps_extrema")) == 0


def test_new_decorations_do_not_leak_into_data_curve_list():
    _fig, ax = _fig_axes(n_lines=1)
    line = ax.get_lines()[0]
    d = read_line_style(line)
    d.update(fill="under", fill_gradient=True, drop_lines=True, label_extrema=True)
    apply_line_style(line, d)
    # palette / Lines tab must still see exactly one real curve
    assert len(list_line_artists(ax)) == 1
