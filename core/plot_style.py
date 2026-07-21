"""Graph-customization engine (OriginPro-style "Plot Details").

Pure matplotlib logic, no Qt, so the whole style layer is unit-testable and
reusable (session save, workflow, templates). A *style* is a plain nested dict
so it round-trips through JSON.

Top-level keys: ``axes``, ``tick_labels``, ``grid``, ``legend``, ``figure``,
``inset``, ``colorbar``.
Per-curve styling lives in :func:`read_line_style` / :func:`apply_line_style`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# --- choices exposed to the dialog -----------------------------------------
LINE_STYLES = ["-", "--", "-.", ":", "None"]
LINE_STYLE_NAMES = {
    "-": "Solid", "--": "Dashed", "-.": "Dash-dot", ":": "Dotted", "None": "None",
}
MARKERS = ["None", "o", "s", "^", "v", "D", "x", "+", "*", ".", "p", "h"]
MARKER_NAMES = {
    "None": "None", "o": "Circle", "s": "Square", "^": "Triangle up",
    "v": "Triangle down", "D": "Diamond", "x": "Cross", "+": "Plus",
    "*": "Star", ".": "Point", "p": "Pentagon", "h": "Hexagon",
}
SCALES = ["linear", "log", "symlog", "logit"]
TICK_DIRECTIONS = ["out", "in", "inout"]
TICK_LABEL_AXES = ["both", "x", "y"]
TICK_LABEL_NOTATIONS = ["auto", "decimal", "scientific", "engineering", "percent"]
LEGEND_LOCS = [
    "best", "upper right", "upper left", "lower left", "lower right",
    "right", "center left", "center right", "lower center",
    "upper center", "center",
]
FONT_FAMILIES = [
    "sans-serif", "serif", "monospace", "Segoe UI", "Arial", "Times New Roman",
    "DejaVu Sans", "Tahoma", "Calibri", "Courier New",
]
FONT_WEIGHTS = ["normal", "bold"]
FONT_STYLES = ["normal", "italic", "oblique"]
GRID_AXES = ["both", "x", "y"]
FILL_STYLES = ["full", "left", "right", "bottom", "top", "none"]
DRAW_STYLES = ["default", "steps-pre", "steps-mid", "steps-post"]
CAP_STYLES = ["butt", "round", "projecting"]
COLORMAPS = [
    "viridis", "plasma", "inferno", "magma", "cividis", "coolwarm",
    "RdBu", "jet", "turbo", "gray", "hot", "cool", "spring", "autumn",
]

# Journal figure presets: publication-ready figure sizes + font sizes.
# Widths are the common single-column sizes (inches). Merge onto a style
# with get_preset_style(name).
# Curated, publication-grade qualitative palettes. Five of these are verified
# colour-vision-deficiency (CVD) safe — the property Origin's default colour
# cycle does not guarantee — so a one-click recolour is genuinely accessible.
SCIENTIFIC_PALETTES = {
    "Okabe-Ito (CB-safe)": [
        "#0072B2", "#E69F00", "#009E73", "#D55E00",
        "#CC79A7", "#56B4E9", "#F0E442", "#000000",
    ],
    "Tol Bright (CB-safe)": [
        "#4477AA", "#EE6677", "#228833", "#CCBB44",
        "#66CCEE", "#AA3377", "#BBBBBB",
    ],
    "Tol Muted (CB-safe)": [
        "#CC6677", "#332288", "#DDCC77", "#117733", "#88CCEE",
        "#882255", "#44AA99", "#999933", "#AA4499",
    ],
    "Tol Vibrant (CB-safe)": [
        "#EE7733", "#0077BB", "#33BBEE", "#EE3377",
        "#CC3311", "#009988", "#BBBBBB",
    ],
    "Viridis (CB-safe)": [
        "#440154", "#414487", "#2A788E", "#22A884", "#7AD151", "#FDE725",
    ],
    "ColorBrewer Set2": [
        "#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3",
        "#A6D854", "#FFD92F", "#E5C494", "#B3B3B3",
    ],
    "Grayscale (print-safe)": [
        "#000000", "#4D4D4D", "#7F7F7F", "#A6A6A6", "#CCCCCC",
    ],
    "SciPlotter": [
        "#4F9CF9", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9",
    ],
}

# Palettes whose ordering keeps all pairs distinguishable under the common
# colour-vision deficiencies (used by the AI ``colorblind`` shortcut).
COLORBLIND_SAFE_PALETTES = (
    "Okabe-Ito (CB-safe)", "Tol Bright (CB-safe)", "Tol Muted (CB-safe)",
    "Tol Vibrant (CB-safe)", "Viridis (CB-safe)",
)


def list_palettes():
    """Return the available scientific palette names (colour-safe first)."""
    return list(SCIENTIFIC_PALETTES.keys())


# Curated colormaps for images/heatmaps — perceptually-uniform CVD-safe first.
COLORMAPS = (
    "viridis", "cividis", "plasma", "inferno", "magma",
    "coolwarm", "RdBu_r", "Spectral_r", "Greys", "hot", "terrain", "turbo",
)

FILL_MODES = ("none", "under", "between_next")
ERRORBAR_MODES = ("none", "constant", "percent")
INSET_LOCS = ("upper right", "upper left", "lower right", "lower left")

# Section defaults: identity Apply must diff to a no-op, and a Cancel snapshot
# taken before any inset/colorbar existed must remove one added by live preview.
INSET_DEFAULTS = {
    "enabled": False, "loc": "upper right", "size": 38.0,
    "xmin": 0.0, "xmax": 1.0, "indicate": True,
}
COLORBAR_DEFAULTS = {
    "enabled": False, "cmap": "", "label": "",
    "shrink": 1.0, "tick_size": 8.0,
}
# Fill hatch patterns (Origin "Pattern" fill). "" = solid.
HATCH_PATTERNS = ("", "/", "\\", "x", "-", "|", "+", "//", "xx", "o", "O", ".", "*")

LINE_DECO_DEFAULTS = {
    "fill": "none", "fill_color": "", "fill_alpha": 0.25,
    "fill_hatch": "", "fill_gradient": False,
    "value_labels": False, "value_labels_fmt": "%.3g",
    "value_labels_size": 8.0, "value_labels_every": 1,
    "errorbar_mode": "none", "errorbar_value": 5.0,
    "errorbar_capsize": 3.0, "errorbar_alpha": 0.9,
    "drop_lines": False, "drop_line_color": "", "drop_line_style": "-",
    "drop_line_width": 0.8,
    "label_extrema": False, "extrema_fmt": "%.3g", "extrema_size": 9.0,
}

LINE_EFFECT_KEYS = (
    "glow", "glow_color", "glow_width", "glow_alpha", "shadow",
    "shadow_alpha", "shadow_offset_x", "shadow_offset_y",
)

SCALE_STATE_KEYS = (
    "xscale", "yscale", "x_autoscale", "y_autoscale", "invert_x", "invert_y",
    "x_major_spacing", "y_major_spacing", "x_minor_spacing", "y_minor_spacing",
    "x_anchor_tick", "y_anchor_tick", "x_minor_count", "y_minor_count",
    "x_rescale_margin", "y_rescale_margin", "sci_notation",
)


# Complete, ready-to-publish journal styles: not just point sizes but tick
# direction, minor ticks, open (top/right hidden) spines, font family, grid
# off, and a CVD-safe palette + line width — one click gets a submission-ready
# figure, which Origin needs a hand-built template to match.
JOURNAL_PRESETS = {
    "IEEE (single column)": {
        "figure": {"width_in": 3.5, "height_in": 2.6, "dpi": 300,
                   "fig_facecolor": "#ffffff", "facecolor": "#ffffff"},
        "axes": {"title_size": 9, "label_size": 8, "tick_size": 7,
                 "font_family": "serif", "tick_direction": "in",
                 "minor_ticks": True, "spine_top": False, "spine_right": False,
                 "spine_width": 0.8,
                 "title_color": "#000000", "label_color": "#000000",
                 "tick_color": "#000000", "tick_label_color": "#000000",
                 "spine_color": "#000000"},
        "grid": {"major": False, "minor": False},
        "legend": {"fontsize": 7, "frame": False},
        "palette": "Okabe-Ito (CB-safe)", "line_width": 1.1,
    },
    "Nature (single column)": {
        "figure": {"width_in": 3.50, "height_in": 2.63, "dpi": 300,
                   "fig_facecolor": "#ffffff", "facecolor": "#ffffff"},
        "axes": {"title_size": 8, "label_size": 7, "tick_size": 6,
                 "font_family": "sans-serif", "tick_direction": "out",
                 "minor_ticks": True, "spine_top": False, "spine_right": False,
                 "spine_width": 0.8,
                 "title_color": "#000000", "label_color": "#000000",
                 "tick_color": "#000000", "tick_label_color": "#000000",
                 "spine_color": "#000000"},
        "grid": {"major": False, "minor": False},
        "legend": {"fontsize": 6, "frame": False},
        "palette": "Tol Bright (CB-safe)", "line_width": 1.0,
    },
    "Science (single column)": {
        "figure": {"width_in": 2.24, "height_in": 2.0, "dpi": 300,
                   "fig_facecolor": "#ffffff", "facecolor": "#ffffff"},
        "axes": {"title_size": 8, "label_size": 7, "tick_size": 6,
                 "font_family": "sans-serif", "tick_direction": "out",
                 "minor_ticks": True, "spine_top": False, "spine_right": False,
                 "spine_width": 0.8,
                 "title_color": "#000000", "label_color": "#000000",
                 "tick_color": "#000000", "tick_label_color": "#000000",
                 "spine_color": "#000000"},
        "grid": {"major": False, "minor": False},
        "legend": {"fontsize": 6, "frame": False},
        "palette": "Okabe-Ito (CB-safe)", "line_width": 1.0,
    },
    "ACS (single column)": {
        "figure": {"width_in": 3.33, "height_in": 2.5, "dpi": 300,
                   "fig_facecolor": "#ffffff", "facecolor": "#ffffff"},
        "axes": {"title_size": 9, "label_size": 8, "tick_size": 7,
                 "font_family": "sans-serif", "tick_direction": "in",
                 "minor_ticks": True, "spine_top": False, "spine_right": False,
                 "spine_width": 0.9,
                 "title_color": "#000000", "label_color": "#000000",
                 "tick_color": "#000000", "tick_label_color": "#000000",
                 "spine_color": "#000000"},
        "grid": {"major": False, "minor": False},
        "legend": {"fontsize": 7, "frame": False},
        "palette": "ColorBrewer Set2", "line_width": 1.2,
    },
    "Thesis (large)": {
        "figure": {"width_in": 6.5, "height_in": 4.5, "dpi": 300,
                   "fig_facecolor": "#ffffff", "facecolor": "#ffffff"},
        "axes": {"title_size": 14, "label_size": 12, "tick_size": 10,
                 "font_family": "serif", "tick_direction": "out",
                 "minor_ticks": True, "spine_top": False, "spine_right": False,
                 "spine_width": 1.0,
                 "title_color": "#000000", "label_color": "#1a1a1a",
                 "tick_color": "#1a1a1a", "tick_label_color": "#1a1a1a",
                 "spine_color": "#333333"},
        "grid": {"major": True, "minor": False, "color": "#dddddd",
                 "linestyle": "-", "alpha": 0.5},
        "legend": {"fontsize": 11, "frame": True},
        "palette": "Tol Muted (CB-safe)", "line_width": 1.6,
    },
    "Excel Pro (presentation)": {
        "figure": {
            "width_in": 7.5,
            "height_in": 4.4,
            "dpi": 160,
            "fig_facecolor": "#ffffff",
            "facecolor": "#ffffff",
        },
        "axes": {
            "title_size": 16,
            "label_size": 12,
            "tick_size": 10,
            "spine_color": "#9aa4b2",
            "spine_width": 1.2,
            "title_color": "#1f2937",
            "label_color": "#1f2937",
            "tick_color": "#54606f",
            "tick_label_color": "#1f2937",
        },
        "grid": {"major": True, "minor": False, "color": "#d8dee9", "linestyle": "-", "alpha": 0.45},
        "legend": {
            "visible": True,
            "fontsize": 10,
            "frame": True,
            "facecolor": "#ffffff",
            "edgecolor": "#d8dee9",
            "alpha": 0.92,
            "shadow": True,
            "fancybox": True,
        },
        "effects": {
            "axes_shadow": True,
            "shadow_color": "#000000",
            "shadow_alpha": 0.18,
            "shadow_offset_x": 3.0,
            "shadow_offset_y": 3.0,
        },
        "palette": "SciPlotter", "line_width": 2.4,
    },
    "Dark Pro (presentation)": {
        "figure": {
            "width_in": 7.5,
            "height_in": 4.4,
            "dpi": 160,
            "fig_facecolor": "#151922",
            "facecolor": "#1f2530",
        },
        "axes": {
            "title_size": 16,
            "label_size": 12,
            "tick_size": 10,
            "spine_color": "#5b6472",
            "spine_width": 1.2,
            "title_color": "#f0f2f5",
            "label_color": "#dfe4ea",
            "tick_color": "#9aa4b2",
            "tick_label_color": "#c7ccd6",
        },
        "grid": {"major": True, "minor": False, "color": "#3d4655", "linestyle": "-", "alpha": 0.38},
        "legend": {
            "visible": True,
            "fontsize": 10,
            "frame": True,
            "facecolor": "#202733",
            "edgecolor": "#4b5565",
            "alpha": 0.92,
            "shadow": True,
            "fancybox": True,
        },
        "effects": {
            "axes_shadow": True,
            "shadow_color": "#000000",
            "shadow_alpha": 0.35,
            "shadow_offset_x": 3.0,
            "shadow_offset_y": 3.0,
        },
        "palette": "Tol Vibrant (CB-safe)", "line_width": 2.4,
    },
}


def get_preset_style(name: str) -> Dict[str, Any]:
    """Return a deep copy of the named journal preset's style fragment."""
    import copy
    preset = JOURNAL_PRESETS.get(name)
    if preset is None:
        raise ValueError(f"unknown journal preset: {name!r}")
    return copy.deepcopy(preset)


def preset_palette(name: str):
    """Return ``(palette_name, line_width)`` carried by a preset, or ``(None, None)``."""
    preset = JOURNAL_PRESETS.get(name) or {}
    return preset.get("palette"), preset.get("line_width")


def apply_palette(ax, name, *, line_width=None, recolor_markers=True) -> int:
    """Recolour every line on ``ax`` in order from a scientific palette.

    Returns the number of artists recoloured. Markers are tinted to match the
    line by default, an existing legend is rebuilt so its swatches stay in sync,
    and an optional uniform ``line_width`` is applied. Unknown palette names
    raise ``ValueError`` so callers can report the mistake.
    """
    colors = SCIENTIFIC_PALETTES.get(name)
    if colors is None:
        raise ValueError(f"unknown palette: {name!r}")
    artists = list_line_artists(ax)
    for index, line in enumerate(artists):
        color = colors[index % len(colors)]
        line.set_color(color)
        if recolor_markers:
            line.set_markerfacecolor(color)
            line.set_markeredgecolor(color)
        if line_width is not None:
            line.set_linewidth(float(line_width))
    legend = ax.get_legend()
    if legend is not None and artists:
        title = legend.get_title()
        title_text = title.get_text() if title is not None else ""
        try:
            ncol = legend._ncols  # matplotlib >= 3.6
        except AttributeError:
            ncol = getattr(legend, "_ncol", 1)
        new_legend = ax.legend(ncol=max(1, int(ncol or 1)))
        if title_text:
            new_legend.set_title(title_text)
    return len(artists)


def _num_or_none(v):
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# --- read -------------------------------------------------------------------
def read_style(ax, fig=None) -> Dict[str, Any]:
    """Capture the current appearance of ``ax`` (and ``fig``) as a style dict."""
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x_gridlines = ax.get_xgridlines()
    grid_on = any(gl.get_visible() for gl in x_gridlines) if x_gridlines else False
    grid_ref = x_gridlines[0] if x_gridlines else None

    legend = ax.get_legend()
    title_obj = ax.title

    style: Dict[str, Any] = {
        "axes": {
            "title": ax.get_title(),
            "title_size": float(title_obj.get_fontsize()),
            "xlabel": ax.get_xlabel(),
            "ylabel": ax.get_ylabel(),
            "label_size": float(ax.xaxis.label.get_fontsize()),
            "xmin": float(xmin), "xmax": float(xmax),
            "ymin": float(ymin), "ymax": float(ymax),
            "x_autoscale": bool(ax.get_autoscalex_on()),
            "y_autoscale": bool(ax.get_autoscaley_on()),
            "xscale": ax.get_xscale(),
            "yscale": ax.get_yscale(),
            "invert_x": bool(xmin > xmax),
            "invert_y": bool(ymin > ymax),
            "tick_size": float(ax.xaxis.get_ticklabels()[0].get_fontsize())
            if ax.xaxis.get_ticklabels() else 10.0,
            "x_major_spacing": None,  # None = auto (custom locators aren't read back)
            "x_minor_spacing": None,
            "y_major_spacing": None,
            "y_minor_spacing": None,
            # Origin Scale tab: anchor tick for "By Increment" majors,
            # "By Counts" minors, and the autoscale rescale margin (%)
            "x_anchor_tick": None,
            "y_anchor_tick": None,
            "x_minor_count": None,
            "y_minor_count": None,
            "x_rescale_margin": None,
            "y_rescale_margin": None,
            "spine_color": _to_hex(next(iter(ax.spines.values())).get_edgecolor())
            if ax.spines else "#3a3f44",
            "spine_width": float(next(iter(ax.spines.values())).get_linewidth())
            if ax.spines else 1.0,
            # --- title / label typography ---
            "title_color": _to_hex(title_obj.get_color()),
            "title_bold": str(title_obj.get_fontweight()) in ("bold", "semibold", "heavy", "black"),
            "title_italic": str(title_obj.get_fontstyle()) in ("italic", "oblique"),
            "label_color": _to_hex(ax.xaxis.label.get_color()),
            "label_bold": str(ax.xaxis.label.get_fontweight()) in ("bold", "semibold", "heavy", "black"),
            "font_family": "sans-serif",
            "label_pad": float(ax.xaxis.labelpad),
            # --- ticks ---
            "tick_direction": "out",
            "tick_length": float(ax.xaxis.get_tick_params().get("length", 3.5) or 3.5)
            if hasattr(ax.xaxis, "get_tick_params") else 3.5,
            "tick_width": float(ax.xaxis.get_tick_params().get("width", 0.8) or 0.8)
            if hasattr(ax.xaxis, "get_tick_params") else 0.8,
            "tick_color": _to_hex(next(iter(ax.spines.values())).get_edgecolor())
            if ax.spines else "#3a3f44",
            "tick_label_color": _to_hex(ax.xaxis.get_ticklabels()[0].get_color())
            if ax.xaxis.get_ticklabels() else "#e6e6e6",
            "tick_x_rotation": 0.0,
            "minor_ticks": bool(ax.xaxis.get_minor_ticks()),
            "mirror_ticks": False,
            "sci_notation": False,
            # --- spine visibility (per side) ---
            "spine_top": bool(ax.spines["top"].get_visible()) if "top" in ax.spines else True,
            "spine_right": bool(ax.spines["right"].get_visible()) if "right" in ax.spines else True,
            "spine_left": bool(ax.spines["left"].get_visible()) if "left" in ax.spines else True,
            "spine_bottom": bool(ax.spines["bottom"].get_visible()) if "bottom" in ax.spines else True,
            # --- reference lines ---
            "refline_h": None,
            "refline_v": None,
            "refline_h_label": "",
            "refline_v_label": "",
            "refline_color": "#ff6b6b",
            "refline_style": "--",
            "refline_width": 1.2,
            "refline_alpha": 1.0,
        },
        "tick_labels": {
            "enabled": False,
            "axis": "both",
            "notation": "auto",
            "decimals_enabled": False,
            "decimals": 2,
            "divide_by": 1.0,
            "formula": "",
            "prefix": "",
            "suffix": "",
            "plus_sign": False,
            "minus_sign": True,
            "thousands": False,
        },
        "grid": {
            "major": bool(grid_on),
            "minor": False,
            "axis": "both",
            "color": _to_hex(grid_ref.get_color()) if grid_ref else "#3a3f44",
            "linestyle": grid_ref.get_linestyle() if grid_ref else "-",
            "linewidth": float(grid_ref.get_linewidth()) if grid_ref else 0.8,
            "alpha": float(grid_ref.get_alpha() or 1.0) if grid_ref else 0.3,
            "minor_color": _to_hex(grid_ref.get_color()) if grid_ref else "#3a3f44",
            "minor_linestyle": ":",
            "minor_linewidth": 0.5,
            "minor_alpha": 0.15,
        },
        "legend": {
            "visible": legend is not None and legend.get_visible(),
            "loc": "best",
            "fontsize": 10.0,
            "frame": legend.get_frame_on() if legend else True,
            "ncol": 1,
            "facecolor": "#1e2126",
            "edgecolor": "#3a3f44",
            "alpha": 1.0,
            "shadow": False,
            "fancybox": True,
            "title": legend.get_title().get_text() if legend and legend.get_title() else "",
            "title_size": 10.0,
            "columnspacing": 2.0,
            "labelspacing": 0.5,
            "markerscale": 1.0,
            "borderpad": 0.4,
            "handlelength": 2.0,
            "draggable": bool(legend.get_draggable()) if legend else True,
        },
        "figure": {
            "facecolor": _to_hex(ax.get_facecolor()),
        },
        "effects": {
            "axes_shadow": bool(ax.patch.get_path_effects()),
            "shadow_color": "#000000",
            "shadow_alpha": 0.25,
            "shadow_offset_x": 3.0,
            "shadow_offset_y": 3.0,
        },
        # Decoration state we own is stored on the axes when applied, so the
        # dialog reopens showing reality and a Cancel snapshot reverts it.
        "inset": dict(getattr(ax, "_ps_inset_cfg", None) or INSET_DEFAULTS),
        "colorbar": dict(getattr(ax, "_ps_colorbar_cfg", None) or COLORBAR_DEFAULTS),
    }
    if fig is not None:
        w, h = fig.get_size_inches()
        style["figure"]["width_in"] = float(w)
        style["figure"]["height_in"] = float(h)
        style["figure"]["dpi"] = float(fig.get_dpi())
    if legend is not None:
        try:
            texts = legend.get_texts()
            if texts:
                style["legend"]["fontsize"] = float(texts[0].get_fontsize())
        except Exception:
            pass
        try:
            frame = legend.get_frame()
            style["legend"]["facecolor"] = _to_hex(frame.get_facecolor())
            style["legend"]["edgecolor"] = _to_hex(frame.get_edgecolor())
            alpha = frame.get_alpha()
            style["legend"]["alpha"] = float(alpha if alpha is not None else 1.0)
        except Exception:
            pass
    if fig is not None:
        style["figure"]["fig_facecolor"] = _to_hex(fig.get_facecolor())
    # Some controls rebuild generated artists or custom formatters and cannot
    # be reconstructed reliably by inspecting Matplotlib alone.  Keep their
    # last semantic configuration on the axes and prefer it when reopening
    # Plot Details, copying a format, or saving a project.
    style["effects"].update(getattr(ax, "_ps_axes_effects", None) or {})
    style["tick_labels"].update(getattr(ax, "_ps_tick_label_cfg", None) or {})
    style["axes"].update(getattr(ax, "_ps_refline_cfg", None) or {})
    style["axes"].update(getattr(ax, "_ps_scale_cfg", None) or {})
    return style


# --- diff (stability seam for the Plot Details dialog) ----------------------
# Keys that must travel together: applying one without its partners would give
# apply_style an inconsistent picture (e.g. new xmin without x_autoscale).
_AXES_KEY_GROUPS = (
    ("x_autoscale", "xmin", "xmax", "invert_x", "x_rescale_margin"),
    ("y_autoscale", "ymin", "ymax", "invert_y", "y_rescale_margin"),
    ("x_major_spacing", "x_anchor_tick"),
    ("y_major_spacing", "y_anchor_tick"),
    ("x_minor_spacing", "x_minor_count"),
    ("y_minor_spacing", "y_minor_count"),
    ("refline_h", "refline_v", "refline_h_label", "refline_v_label",
     "refline_color", "refline_style", "refline_width", "refline_alpha"),
)
# Sections that are rebuilt as a whole, so they diff as a whole.
_ATOMIC_SECTIONS = ("grid", "legend", "tick_labels", "effects", "inset", "colorbar")


def diff_style(baseline: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """Style containing only what *changed* between two dialog snapshots.

    This is the Plot Details stability contract: pressing Apply must only
    touch what the user actually edited. Untouched controls — even ones seeded
    from a mis-read of the figure — can then never restyle (or break) the
    graph. Axes keys diff per-key with dependent keys grouped; ``grid`` /
    ``legend`` / ``tick_labels`` / ``effects`` are all-or-nothing because
    apply rebuilds those objects wholesale.
    """
    if not baseline:
        return current
    out: Dict[str, Any] = {}

    base_axes = baseline.get("axes", {}) or {}
    cur_axes = current.get("axes", {}) or {}
    grouped = {k for group in _AXES_KEY_GROUPS for k in group}
    changed_axes: Dict[str, Any] = {}
    for key, value in cur_axes.items():
        if key in grouped:
            continue
        if key not in base_axes or base_axes.get(key) != value:
            changed_axes[key] = value
    for group in _AXES_KEY_GROUPS:
        if any(base_axes.get(k) != cur_axes.get(k) for k in group if k in cur_axes):
            for k in group:
                if k in cur_axes:
                    changed_axes[k] = cur_axes[k]
    if changed_axes:
        out["axes"] = changed_axes

    for section in _ATOMIC_SECTIONS:
        if baseline.get(section) != current.get(section) and section in current:
            out[section] = current[section]

    base_fig = baseline.get("figure", {}) or {}
    cur_fig = current.get("figure", {}) or {}
    changed_fig = {k: v for k, v in cur_fig.items()
                   if k not in base_fig or base_fig.get(k) != v}
    if changed_fig:
        out["figure"] = changed_fig
    return out


# --- apply ------------------------------------------------------------------
def apply_style(ax, style: Dict[str, Any], fig=None, live: bool = True) -> None:
    """Apply a style dict to ``ax`` (and ``fig``). Unknown keys are ignored.

    ``live=True`` (on-screen, the default) never touches the figure size or DPI
    — those are print/export concerns; changing them on an embedded Qt canvas
    breaks the on-screen layout. Pass ``live=False`` for export rendering.
    """
    a = style.get("axes", {})
    if any(key in a for key in SCALE_STATE_KEYS):
        scale_state = dict(getattr(ax, "_ps_scale_cfg", None) or {})
        scale_state.update({key: a[key] for key in SCALE_STATE_KEYS if key in a})
        ax._ps_scale_cfg = scale_state
    # NOTE: with diff-apply a key can arrive alone — never pass fontsize=None
    if "title" in a:
        if a.get("title_size"):
            ax.set_title(a["title"], fontsize=a["title_size"])
        else:
            ax.set_title(a["title"])
    if "xlabel" in a:
        if a.get("label_size"):
            ax.set_xlabel(a["xlabel"], fontsize=a["label_size"])
        else:
            ax.set_xlabel(a["xlabel"])
    if "ylabel" in a:
        if a.get("label_size"):
            ax.set_ylabel(a["ylabel"], fontsize=a["label_size"])
        else:
            ax.set_ylabel(a["ylabel"])
    # font sizes apply even when the text itself is unchanged (e.g. presets)
    if a.get("title_size"):
        ax.title.set_fontsize(a["title_size"])
    if a.get("label_size"):
        ax.xaxis.label.set_fontsize(a["label_size"])
        ax.yaxis.label.set_fontsize(a["label_size"])

    # scales (guard log against non-positive limits)
    for axis, key in (("x", "xscale"), ("y", "yscale")):
        scale = a.get(key)
        if scale in SCALES:
            try:
                (ax.set_xscale if axis == "x" else ax.set_yscale)(scale)
            except Exception:
                pass

    # limits: manual unless autoscale requested
    if a.get("x_autoscale"):
        ax.autoscale(enable=True, axis="x")
    else:
        xmin, xmax = _num_or_none(a.get("xmin")), _num_or_none(a.get("xmax"))
        if xmin is not None and xmax is not None and xmin != xmax:
            lo, hi = (xmax, xmin) if a.get("invert_x") else (xmin, xmax)
            ax.set_xlim(lo, hi)
    if a.get("y_autoscale"):
        ax.autoscale(enable=True, axis="y")
    else:
        ymin, ymax = _num_or_none(a.get("ymin")), _num_or_none(a.get("ymax"))
        if ymin is not None and ymax is not None and ymin != ymax:
            lo, hi = (ymax, ymin) if a.get("invert_y") else (ymin, ymax)
            ax.set_ylim(lo, hi)

    if "invert_x" in a and a.get("x_autoscale", False) is False:
        pass  # handled above via limit ordering
    if a.get("tick_size"):
        ax.tick_params(labelsize=a["tick_size"])
    if a.get("tick_direction") in TICK_DIRECTIONS:
        ax.tick_params(direction=a["tick_direction"])
    if "spine_color" in a or "spine_width" in a:
        for spine in ax.spines.values():
            try:
                if "spine_color" in a:
                    spine.set_edgecolor(a["spine_color"])
                if "spine_width" in a:
                    spine.set_linewidth(float(a["spine_width"]))
            except Exception:
                pass

    # per-side spine visibility (Origin: hide top/right for an open frame)
    for side in ("top", "right", "left", "bottom"):
        key = f"spine_{side}"
        if key in a and side in ax.spines:
            try:
                ax.spines[side].set_visible(bool(a[key]))
            except Exception:
                pass

    # title / label typography (color, weight, italic, family, pad)
    _apply_text_typography(ax, a)

    # tick appearance (length/width/colors/rotation/minor/mirror)
    _apply_tick_style(ax, a)

    # scientific-notation offset on both axes
    if "sci_notation" in a:
        try:
            ax.ticklabel_format(style="sci" if a.get("sci_notation") else "plain",
                                axis="both", scilimits=(0, 0))
        except Exception:
            pass

    # Origin-style tick-label display options. This is opt-in so a normal style
    # read/apply roundtrip keeps matplotlib's automatic formatter.
    _apply_tick_label_format(ax, style.get("tick_labels", {}))

    # Reference lines form one atomic group.  A partial/diff style that does
    # not mention them must leave existing guides alone (important for format
    # paste and for unrelated Plot Details edits).
    if any(str(key).startswith("refline_") for key in a):
        _apply_reference_lines(ax, a)

    # custom tick spacing (MultipleLocator); None/0 = leave matplotlib's auto.
    # Majors honor the Origin "Anchor Tick" (offset), minors fall back to
    # "By Counts" (AutoMinorLocator) when no increment is given.
    _apply_locator(ax.xaxis, a.get("x_major_spacing"), major=True,
                   anchor=a.get("x_anchor_tick"))
    _apply_locator(ax.xaxis, a.get("x_minor_spacing"), major=False)
    _apply_locator(ax.yaxis, a.get("y_major_spacing"), major=True,
                   anchor=a.get("y_anchor_tick"))
    _apply_locator(ax.yaxis, a.get("y_minor_spacing"), major=False)
    _apply_minor_count(ax.xaxis, a.get("x_minor_count"), a.get("x_minor_spacing"))
    _apply_minor_count(ax.yaxis, a.get("y_minor_count"), a.get("y_minor_spacing"))

    # rescale margin (%) — only meaningful while the axis autoscales
    _apply_rescale_margin(ax, a)

    g = style.get("grid", {})
    if g:
        axis = g.get("axis", "both")
        if axis not in GRID_AXES:
            axis = "both"
        if g.get("major"):
            ax.grid(True, which="major", axis=axis,
                    color=g.get("color", "#3a3f44"),
                    linestyle=g.get("linestyle", "-"),
                    linewidth=float(g.get("linewidth", 0.8)),
                    alpha=float(g.get("alpha", 0.3)))
        else:
            ax.grid(False, which="major")
        if g.get("minor"):
            ax.minorticks_on()
            ax.grid(True, which="minor", axis=axis,
                    color=g.get("minor_color", g.get("color", "#3a3f44")),
                    linestyle=g.get("minor_linestyle", ":"),
                    linewidth=float(g.get("minor_linewidth", 0.5)),
                    alpha=float(g.get("minor_alpha", 0.15)))
        else:
            ax.grid(False, which="minor")

    leg = style.get("legend", {})
    if leg:
        if leg.get("visible"):
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                new_leg = ax.legend(
                    loc=leg.get("loc", "best"),
                    fontsize=leg.get("fontsize", 10.0),
                    ncol=max(1, int(leg.get("ncol", 1))),
                    frameon=bool(leg.get("frame", True)),
                    fancybox=bool(leg.get("fancybox", True)),
                    shadow=bool(leg.get("shadow", False)),
                    title=leg.get("title") or None,
                    columnspacing=float(leg.get("columnspacing", 2.0)),
                    labelspacing=float(leg.get("labelspacing", 0.5)),
                    markerscale=float(leg.get("markerscale", 1.0)),
                    borderpad=float(leg.get("borderpad", 0.4)),
                    handlelength=float(leg.get("handlelength", 2.0)),
                )
                if new_leg is not None:
                    new_leg.set_visible(True)
                    try:
                        draggable = bool(leg.get("draggable", True))
                        new_leg._ps_drag_enabled = draggable
                        new_leg.set_draggable(draggable)
                    except Exception:
                        pass
                    frame = new_leg.get_frame()
                    try:
                        frame.set_facecolor(leg.get("facecolor", "#1e2126"))
                        frame.set_edgecolor(leg.get("edgecolor", "#3a3f44"))
                        frame.set_alpha(float(leg.get("alpha", 1.0)))
                    except Exception:
                        pass
                    # Legend text should track the axis text colour so it never
                    # washes out — e.g. dark-theme light text left on a white
                    # journal preset, or black text on the Dark Pro background.
                    text_color = None
                    try:
                        ticklabels = ax.xaxis.get_ticklabels()
                        text_color = (ticklabels[0].get_color() if ticklabels
                                      else ax.xaxis.label.get_color())
                        for txt in new_leg.get_texts():
                            txt.set_color(text_color)
                    except Exception:
                        pass
                    title_obj = new_leg.get_title()
                    if title_obj is not None:
                        if text_color:
                            try:
                                title_obj.set_color(text_color)
                            except Exception:
                                pass
                        if leg.get("title"):
                            try:
                                title_obj.set_fontsize(float(leg.get("title_size", 10.0)))
                            except Exception:
                                pass
        else:
            existing = ax.get_legend()
            if existing is not None:
                existing.set_visible(False)

    f = style.get("figure", {})
    if "facecolor" in f:
        try:
            ax.set_facecolor(f["facecolor"])
        except Exception:
            pass
    if fig is not None and f.get("fig_facecolor"):
        try:
            fig.set_facecolor(f["fig_facecolor"])
        except Exception:
            pass
    if "effects" in style:
        _apply_axes_effects(ax, style.get("effects", {}))
    if "inset" in style:
        _apply_inset(ax, style.get("inset") or {})
    if "colorbar" in style:
        _apply_colorbar(ax, style.get("colorbar") or {})
    # figure size / DPI are export-only: applying them to a live embedded Qt
    # canvas squashes the on-screen layout (see the "apply preset" bug)
    if not live and fig is not None and (f.get("width_in") or f.get("height_in")):
        try:
            cur_w, cur_h = fig.get_size_inches()
            fig.set_size_inches(float(f.get("width_in", cur_w)),
                                float(f.get("height_in", cur_h)))
        except Exception:
            pass
    if not live and fig is not None and f.get("dpi"):
        try:
            fig.set_dpi(float(f["dpi"]))
        except Exception:
            pass


def _apply_locator(axis, spacing, major: bool, anchor=None) -> None:
    """Set a MultipleLocator at ``spacing`` on a matplotlib axis (major/minor).

    ``spacing`` None or <= 0 leaves matplotlib's automatic locator in place.
    ``anchor`` (Origin "Anchor Tick") shifts the grid so a tick lands exactly
    on that value: ticks at ``anchor + n * spacing``.
    """
    s = _num_or_none(spacing)
    if s is None or s <= 0:
        return
    from matplotlib.ticker import MultipleLocator
    offset = _num_or_none(anchor)
    if offset is not None:
        try:
            locator = MultipleLocator(s, offset=offset % s)
        except TypeError:  # matplotlib < 3.8 has no offset
            locator = MultipleLocator(s)
    else:
        locator = MultipleLocator(s)
    if major:
        axis.set_major_locator(locator)
    else:
        axis.set_minor_locator(locator)


def _apply_minor_count(axis, count, spacing) -> None:
    """Origin "Minor Ticks → By Counts": *count* minor ticks between majors.

    Skipped when a minor increment (``spacing``) is set — By Increment wins,
    matching the dialog where the two modes are alternatives.
    """
    s = _num_or_none(spacing)
    if s is not None and s > 0:
        return
    n = _num_or_none(count)
    if n is None or n < 1:
        return
    from matplotlib.ticker import AutoMinorLocator
    # count minor ticks between majors = count + 1 subdivisions
    axis.set_minor_locator(AutoMinorLocator(int(n) + 1))


def _apply_rescale_margin(ax, a: Dict[str, Any]) -> None:
    """Origin "Rescale Margin (%)": padding around autoscaled data limits."""
    try:
        mx = _num_or_none(a.get("x_rescale_margin"))
        my = _num_or_none(a.get("y_rescale_margin"))
        if mx is not None and a.get("x_autoscale"):
            ax.margins(x=max(0.0, mx) / 100.0)
            ax.autoscale(enable=True, axis="x")
        if my is not None and a.get("y_autoscale"):
            ax.margins(y=max(0.0, my) / 100.0)
            ax.autoscale(enable=True, axis="y")
    except Exception:
        pass


# --- tick-label formula (Origin "Formula", e.g. "2 * x") --------------------
_FORMULA_CACHE: Dict[str, Any] = {}


def compile_tick_formula(expr: str):
    """Compile a tick-label formula like ``2 * x`` into ``f(x) -> float``.

    Only plain arithmetic on ``x`` (+ - * / // % ** and parentheses), numeric
    literals, the constants ``pi``/``e`` and a small math-function whitelist
    are allowed — anything else returns None (formula silently ignored), so a
    style dict loaded from a file can never execute arbitrary code.
    """
    import ast
    import math

    expr = str(expr or "").strip()
    if not expr:
        return None
    if expr in _FORMULA_CACHE:
        return _FORMULA_CACHE[expr]

    allowed_funcs = {
        "abs": abs, "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
        "log2": math.log2, "exp": math.exp, "sin": math.sin, "cos": math.cos,
        "tan": math.tan,
    }
    allowed_names = {"pi": math.pi, "e": math.e}

    def _check(node) -> bool:
        if isinstance(node, ast.Expression):
            return _check(node.body)
        if isinstance(node, ast.BinOp):
            ok_ops = (ast.Add, ast.Sub, ast.Mult, ast.Div,
                      ast.FloorDiv, ast.Mod, ast.Pow)
            return isinstance(node.op, ok_ops) and _check(node.left) and _check(node.right)
        if isinstance(node, ast.UnaryOp):
            return isinstance(node.op, (ast.UAdd, ast.USub)) and _check(node.operand)
        if isinstance(node, ast.Constant):
            return isinstance(node.value, (int, float))
        if isinstance(node, ast.Name):
            return node.id == "x" or node.id in allowed_names
        if isinstance(node, ast.Call):
            return (isinstance(node.func, ast.Name)
                    and node.func.id in allowed_funcs
                    and not node.keywords
                    and all(_check(arg) for arg in node.args))
        return False

    try:
        tree = ast.parse(expr, mode="eval")
        if not _check(tree):
            raise ValueError("disallowed expression")
        code = compile(tree, "<tick formula>", "eval")
        env = {"__builtins__": {}, **allowed_funcs, **allowed_names}

        def fn(x: float) -> float:
            return float(eval(code, env, {"x": float(x)}))  # noqa: S307 — AST whitelisted above

        fn(1.0)  # sanity run so a broken formula fails here, not per tick
    except Exception:
        fn = None
    _FORMULA_CACHE[expr] = fn
    return fn


# --- per-curve --------------------------------------------------------------
def read_line_style(line) -> Dict[str, Any]:
    """Capture a Line2D's style as a dict."""
    marker = line.get_marker()
    mfc = line.get_markerfacecolor()
    mec = line.get_markeredgecolor()
    effects = {
        "glow": False,
        "glow_color": _to_hex(line.get_color()),
        "glow_width": 5.0,
        "glow_alpha": 0.35,
        "shadow": False,
        "shadow_alpha": 0.25,
        "shadow_offset_x": 1.5,
        "shadow_offset_y": 1.5,
    }
    effects.update(getattr(line, "_ps_effects", None) or {})
    return {
        "label": line.get_label(),
        "color": _to_hex(line.get_color()),
        "linewidth": float(line.get_linewidth()),
        "linestyle": _normalize_linestyle(line.get_linestyle()),
        "marker": "None" if marker in (None, "", "none", " ") else str(marker),
        "markersize": float(line.get_markersize()),
        "markerfacecolor": _to_hex(mfc) if mfc not in (None, "none") else _to_hex(line.get_color()),
        "markeredgecolor": _to_hex(mec) if mec not in (None, "none") else _to_hex(line.get_color()),
        "markeredgewidth": float(line.get_markeredgewidth()),
        "fillstyle": str(line.get_fillstyle()),
        "drawstyle": str(line.get_drawstyle()),
        "zorder": float(line.get_zorder()),
        "alpha": float(line.get_alpha()) if line.get_alpha() is not None else 1.0,
        **effects,
        # decorations we applied earlier are remembered on the artist so the
        # dialog reopens showing them (and Cancel snapshots can revert them)
        **{**LINE_DECO_DEFAULTS, **(getattr(line, "_ps_deco", None) or {})},
    }


def apply_line_style(line, d: Dict[str, Any]) -> None:
    """Apply a style dict to a Line2D."""
    if "color" in d:
        line.set_color(d["color"])
    if "linewidth" in d:
        line.set_linewidth(float(d["linewidth"]))
    if "linestyle" in d:
        ls = d["linestyle"]
        line.set_linestyle("None" if ls in ("None", "none", None) else ls)
    if "marker" in d:
        mk = d["marker"]
        line.set_marker("None" if mk in ("None", "none", None) else mk)
    if "markersize" in d:
        line.set_markersize(float(d["markersize"]))
    if d.get("markerfacecolor"):
        try:
            line.set_markerfacecolor(d["markerfacecolor"])
        except Exception:
            pass
    if d.get("markeredgecolor"):
        try:
            line.set_markeredgecolor(d["markeredgecolor"])
        except Exception:
            pass
    if "markeredgewidth" in d:
        try:
            line.set_markeredgewidth(float(d["markeredgewidth"]))
        except Exception:
            pass
    if d.get("fillstyle") in FILL_STYLES:
        try:
            line.set_fillstyle(d["fillstyle"])
        except Exception:
            pass
    if d.get("drawstyle") in DRAW_STYLES:
        try:
            line.set_drawstyle(d["drawstyle"])
        except Exception:
            pass
    if "zorder" in d:
        try:
            line.set_zorder(float(d["zorder"]))
        except Exception:
            pass
    if "alpha" in d and d["alpha"] is not None:
        line.set_alpha(float(d["alpha"]))
    if "label" in d and d["label"]:
        line.set_label(d["label"])
    if any(key in d for key in LINE_EFFECT_KEYS):
        _apply_line_effects(line, d)
    if any(key in d for key in LINE_DECO_DEFAULTS):
        _apply_line_decorations(line, d)


# --- helpers ----------------------------------------------------------------
def _normalize_linestyle(ls) -> str:
    if isinstance(ls, str):
        return ls if ls in LINE_STYLES else "-"
    # matplotlib may return a dash tuple
    return "-"


def _to_hex(color) -> str:
    """Any matplotlib color spec → #rrggbb hex."""
    try:
        import matplotlib.colors as mcolors
        return mcolors.to_hex(color)
    except Exception:
        return "#000000"


def _apply_axes_effects(ax, effects: Dict[str, Any]) -> None:
    ax._ps_axes_effects = dict(effects or {})
    try:
        if not effects.get("axes_shadow"):
            ax.patch.set_path_effects([])
            return
        import matplotlib.patheffects as pe

        ox = float(effects.get("shadow_offset_x", 3.0))
        oy = float(effects.get("shadow_offset_y", 3.0))
        ax.patch.set_path_effects([
            pe.SimplePatchShadow(
                offset=(ox, -oy),
                shadow_rgbFace=effects.get("shadow_color", "#000000"),
                alpha=float(effects.get("shadow_alpha", 0.25)),
                rho=0.95,
            ),
            pe.Normal(),
        ])
    except Exception:
        pass


def _apply_text_typography(ax, a: Dict[str, Any]) -> None:
    """Title/label color, weight, italic, font family and label padding."""
    try:
        fam = a.get("font_family")
        if a.get("title_color"):
            ax.title.set_color(a["title_color"])
        if "title_bold" in a:
            ax.title.set_fontweight("bold" if a.get("title_bold") else "normal")
        if "title_italic" in a:
            ax.title.set_fontstyle("italic" if a.get("title_italic") else "normal")
        for lbl in (ax.xaxis.label, ax.yaxis.label):
            if a.get("label_color"):
                lbl.set_color(a["label_color"])
            if "label_bold" in a:
                lbl.set_fontweight("bold" if a.get("label_bold") else "normal")
            if fam:
                lbl.set_fontfamily(fam)
        if fam:
            ax.title.set_fontfamily(fam)
        pad = _num_or_none(a.get("label_pad"))
        if pad is not None:
            ax.xaxis.labelpad = pad
            ax.yaxis.labelpad = pad
    except Exception:
        pass


def _apply_tick_style(ax, a: Dict[str, Any]) -> None:
    """Tick length/width/colors/rotation + minor and mirrored ticks."""
    try:
        params: Dict[str, Any] = {}
        length = _num_or_none(a.get("tick_length"))
        if length is not None:
            params["length"] = length
        width = _num_or_none(a.get("tick_width"))
        if width is not None:
            params["width"] = width
        if a.get("tick_color"):
            params["color"] = a["tick_color"]
        if a.get("tick_label_color"):
            params["labelcolor"] = a["tick_label_color"]
        if a.get("tick_direction") in TICK_DIRECTIONS:
            params["direction"] = a["tick_direction"]
        if "mirror_ticks" in a:
            params["top"] = bool(a["mirror_ticks"])
            params["right"] = bool(a["mirror_ticks"])
        if params:
            ax.tick_params(axis="both", which="major", **params)
        if a.get("minor_ticks"):
            ax.minorticks_on()
        rot = _num_or_none(a.get("tick_x_rotation"))
        if rot is not None:
            for lbl in ax.get_xticklabels():
                lbl.set_rotation(rot)
                if abs(rot) >= 1:
                    lbl.set_ha("right" if rot > 0 else "left")
    except Exception:
        pass


def _apply_tick_label_format(ax, cfg: Dict[str, Any]) -> None:
    """Apply user-controlled major tick-label formatting.

    Disabling the override restores a plain ScalarFormatter, but only on axes
    still carrying *our* formatter (tagged) — a date axis or another custom
    formatter is left alone.
    """
    if not cfg:
        return
    ax._ps_tick_label_cfg = dict(cfg)
    try:
        from matplotlib.ticker import FuncFormatter, ScalarFormatter

        if not cfg.get("enabled"):
            for axis in (ax.xaxis, ax.yaxis):
                if getattr(axis.get_major_formatter(), "_ps_tick_label_fmt", False):
                    axis.set_major_formatter(ScalarFormatter())
            return
        axis_choice = cfg.get("axis", "both")
        if axis_choice not in TICK_LABEL_AXES:
            axis_choice = "both"
        formatter = FuncFormatter(lambda value, pos: _format_tick_label(value, cfg))
        formatter._ps_tick_label_fmt = True
        if axis_choice in ("both", "x"):
            ax.xaxis.set_major_formatter(formatter)
        elif getattr(ax.xaxis.get_major_formatter(), "_ps_tick_label_fmt", False):
            ax.xaxis.set_major_formatter(ScalarFormatter())
        if axis_choice in ("both", "y"):
            ax.yaxis.set_major_formatter(formatter)
        elif getattr(ax.yaxis.get_major_formatter(), "_ps_tick_label_fmt", False):
            ax.yaxis.set_major_formatter(ScalarFormatter())
    except Exception:
        pass


def _format_tick_label(value: float, cfg: Dict[str, Any]) -> str:
    # Origin rule: "Divide by Factor" is ignored when a Formula is used
    formula = compile_tick_formula(cfg.get("formula", ""))
    if formula is not None:
        try:
            scaled = formula(float(value))
        except Exception:
            scaled = float(value)
    else:
        divide_by = _num_or_none(cfg.get("divide_by"))
        if divide_by is None or divide_by == 0:
            divide_by = 1.0
        scaled = float(value) / divide_by

    notation = str(cfg.get("notation", "auto")).lower()
    if notation not in TICK_LABEL_NOTATIONS:
        notation = "auto"
    decimals_enabled = bool(cfg.get("decimals_enabled", False))
    decimals = int(max(0, min(12, int(cfg.get("decimals", 2) or 0))))
    thousands = bool(cfg.get("thousands", False))

    suffix = str(cfg.get("suffix", "") or "")
    if notation == "percent":
        scaled *= 100.0
        if not suffix:
            suffix = "%"

    sign = ""
    abs_value = abs(scaled)
    if scaled < 0:
        sign = "-" if bool(cfg.get("minus_sign", True)) else ""
    elif scaled > 0 and bool(cfg.get("plus_sign", False)):
        sign = "+"

    if notation == "scientific":
        body = f"{abs_value:.{decimals if decimals_enabled else 2}e}"
    elif notation == "engineering":
        body = _format_engineering(abs_value, decimals if decimals_enabled else 2, thousands)
    elif notation in ("decimal", "percent") or decimals_enabled:
        comma = "," if thousands else ""
        body = f"{abs_value:{comma}.{decimals}f}"
    else:
        comma = "," if thousands else ""
        body = f"{abs_value:{comma}.6g}"

    prefix = str(cfg.get("prefix", "") or "")
    return f"{prefix}{sign}{body}{suffix}"


def _format_engineering(value: float, decimals: int, thousands: bool) -> str:
    if value == 0:
        return f"{value:.{decimals}f}"
    import math

    exp = int(math.floor(math.log10(abs(value)) / 3.0) * 3)
    exp = max(-24, min(24, exp))
    scaled = value / (10 ** exp)
    comma = "," if thousands else ""
    body = f"{scaled:{comma}.{decimals}f}"
    suffix = {
        -24: "y",
        -21: "z",
        -18: "a",
        -15: "f",
        -12: "p",
        -9: "n",
        -6: "u",
        -3: "m",
        0: "",
        3: "k",
        6: "M",
        9: "G",
        12: "T",
        15: "P",
        18: "E",
        21: "Z",
        24: "Y",
    }.get(exp, f"e{exp}")
    return f"{body}{suffix}"


def _apply_reference_lines(ax, a: Dict[str, Any]) -> None:
    """Draw/refresh a horizontal and/or vertical guide line at a value.

    Tagged with a gid so re-applying replaces the old guides instead of
    stacking new ones every time the dialog re-applies.
    """
    try:
        ax._ps_refline_cfg = {
            key: a.get(key)
            for key in (
                "refline_h", "refline_v", "refline_h_label", "refline_v_label",
                "refline_color", "refline_style", "refline_width", "refline_alpha",
                "tick_size",
            )
            if key in a
        }
        color = a.get("refline_color", "#ff6b6b")
        style = a.get("refline_style", "--")
        width = float(a.get("refline_width", 1.2) or 1.2)
        alpha = float(a.get("refline_alpha", 1.0) or 1.0)
        for ln in list(ax.lines):
            if getattr(ln, "get_gid", lambda: None)() in ("_ps_refline_h", "_ps_refline_v"):
                ln.remove()
        for text in list(ax.texts):
            if getattr(text, "get_gid", lambda: None)() in (
                "_ps_refline_h_label",
                "_ps_refline_v_label",
            ):
                text.remove()
        hy = _num_or_none(a.get("refline_h"))
        if hy is not None:
            ax.axhline(
                hy,
                color=color,
                linestyle=style,
                linewidth=width,
                alpha=alpha,
                gid="_ps_refline_h",
            )
            label = str(a.get("refline_h_label", "") or "")
            if label:
                ax.text(
                    0.99,
                    hy,
                    label,
                    transform=ax.get_yaxis_transform(),
                    ha="right",
                    va="bottom",
                    color=color,
                    alpha=alpha,
                    fontsize=float(a.get("tick_size", 10) or 10),
                    gid="_ps_refline_h_label",
                )
        vx = _num_or_none(a.get("refline_v"))
        if vx is not None:
            ax.axvline(
                vx,
                color=color,
                linestyle=style,
                linewidth=width,
                alpha=alpha,
                gid="_ps_refline_v",
            )
            label = str(a.get("refline_v_label", "") or "")
            if label:
                ax.text(
                    vx,
                    0.99,
                    label,
                    transform=ax.get_xaxis_transform(),
                    ha="left",
                    va="top",
                    color=color,
                    alpha=alpha,
                    fontsize=float(a.get("tick_size", 10) or 10),
                    rotation=90,
                    gid="_ps_refline_v_label",
                )
    except Exception:
        pass


def _apply_line_effects(line, d: Dict[str, Any]) -> None:
    line._ps_effects = {
        key: d.get(key, default)
        for key, default in {
            "glow": False,
            "glow_color": _to_hex(line.get_color()),
            "glow_width": 5.0,
            "glow_alpha": 0.35,
            "shadow": False,
            "shadow_alpha": 0.25,
            "shadow_offset_x": 1.5,
            "shadow_offset_y": 1.5,
        }.items()
    }
    effects = []
    try:
        import matplotlib.patheffects as pe

        if d.get("shadow"):
            effects.append(
                pe.SimpleLineShadow(
                    offset=(float(d.get("shadow_offset_x", 1.5)), -float(d.get("shadow_offset_y", 1.5))),
                    alpha=float(d.get("shadow_alpha", 0.25)),
                )
            )
        if d.get("glow"):
            base_width = float(d.get("linewidth", line.get_linewidth() or 1.5))
            effects.append(
                pe.Stroke(
                    linewidth=base_width + float(d.get("glow_width", 5.0)),
                    foreground=d.get("glow_color", d.get("color", "#4F9CF9")),
                    alpha=float(d.get("glow_alpha", 0.35)),
                )
            )
        if effects:
            effects.append(pe.Normal())
        line.set_path_effects(effects)
    except Exception:
        try:
            line.set_path_effects([])
        except Exception:
            pass


def list_line_artists(ax) -> List[Any]:
    """The user's data curves, in order — excluding artists this module owns.

    Reference lines, error-bar caps and other decorations carry a ``_ps_``
    gid; without this filter a palette recolour (or the Lines tab) would
    treat them as data curves.
    """
    return [
        ln for ln in ax.get_lines()
        if not str(ln.get_gid() or "").startswith("_ps_")
    ]


# --- decorations: fill / value labels / error bars / inset / colorbar --------
def _line_gid(line, kind: str) -> str:
    return f"_ps_{kind}_{id(line)}"


def _remove_gid_artists(ax, gid: str) -> None:
    # containers first: ErrorbarContainer.remove() drops its child artists, so
    # removing children individually beforehand would double-remove them
    for container in list(getattr(ax, "containers", [])):
        if getattr(container, "_ps_gid", None) == gid:
            try:
                container.remove()
            except Exception:
                logger.debug("errorbar container removal failed", exc_info=True)
    for group in (ax.lines, ax.collections, ax.texts, ax.patches, ax.images):
        for artist in list(group):
            if str(artist.get_gid() or "") == gid:
                try:
                    artist.remove()
                except Exception:
                    logger.debug("decoration artist removal failed", exc_info=True)


def set_line_decorations_visible(line, visible: bool) -> None:
    """Toggle every generated dependent of ``line`` with its logical layer."""
    ax = getattr(line, "axes", None)
    if ax is None:
        return
    gids = {_line_gid(line, kind) for kind in ("fill", "vlab", "err", "drop", "extrema")}
    for container in list(getattr(ax, "containers", ())):
        if getattr(container, "_ps_gid", None) not in gids:
            continue
        for artist in getattr(container, "get_children", lambda: ())():
            try:
                artist.set_visible(bool(visible))
            except Exception:
                pass
    for group in (ax.lines, ax.collections, ax.texts, ax.patches, ax.images):
        for artist in list(group):
            try:
                if str(artist.get_gid() or "") in gids:
                    artist.set_visible(bool(visible))
            except Exception:
                pass


def remove_line_decorations(line) -> None:
    """Remove generated dependents before a logical line is deleted."""
    ax = getattr(line, "axes", None)
    if ax is None:
        return
    for kind in ("fill", "vlab", "err", "drop", "extrema"):
        _remove_gid_artists(ax, _line_gid(line, kind))
    try:
        line._ps_deco = None
    except Exception:
        pass


def _finite_xy(line):
    x = np.asarray(line.get_xdata(), dtype=float)
    y = np.asarray(line.get_ydata(), dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    return x[ok], y[ok]


def _apply_line_fill(line, d: Dict[str, Any]) -> None:
    """Fill under the curve or between this curve and the next one."""
    ax = line.axes
    if ax is None:
        return
    gid = _line_gid(line, "fill")
    _remove_gid_artists(ax, gid)
    mode = str(d.get("fill", "none"))
    if mode not in FILL_MODES or mode == "none":
        return
    x, y = _finite_xy(line)
    if x.size < 2:
        return
    color = d.get("fill_color") or _to_hex(line.get_color())
    alpha = float(d.get("fill_alpha", 0.25))
    hatch = str(d.get("fill_hatch", "") or "")
    if hatch and hatch not in HATCH_PATTERNS:
        hatch = ""
    if mode == "under":
        y2 = 0.0
    else:  # between_next
        curves = list_line_artists(ax)
        try:
            index = curves.index(line)
        except ValueError:
            return
        if index + 1 >= len(curves):
            return  # no next curve — quietly nothing to fill against
        other = curves[index + 1]
        ox, oy = _finite_xy(other)
        if ox.size < 2:
            return
        y2 = np.interp(x, ox, oy)
    artist = ax.fill_between(x, y, y2, color=color, alpha=alpha, linewidth=0)
    if hatch:
        # Hatch needs a visible edge to draw the pattern strokes.
        artist.set_hatch(hatch)
        try:
            artist.set_edgecolor(color)
            artist.set_linewidth(0.0)
        except Exception:
            pass
    artist.set_gid(gid)
    artist.set_zorder(line.get_zorder() - 0.5)
    if d.get("fill_gradient"):
        _apply_fill_gradient(ax, artist, x, y, y2, color, gid, line.get_zorder() - 0.5)


def _apply_fill_gradient(ax, poly, x, y, y2, color, gid, zorder) -> None:
    """Vertical alpha gradient clipped to the fill polygon (Origin gradient
    fill). The flat ``fill_between`` becomes the clip mask for a gradient image
    so opacity fades from the curve down to the baseline."""
    try:
        import numpy as _np
        from matplotlib.colors import to_rgb
        y_arr = _np.asarray(y, dtype=float)
        base = float(_np.min(y2)) if _np.ndim(y2) else float(y2)
        top = float(_np.nanmax(y_arr))
        lo = min(base, float(_np.nanmin(y_arr)))
        if not _np.isfinite(top) or not _np.isfinite(lo) or top == lo:
            return
        r, g, b = to_rgb(color)
        grad = _np.linspace(0.0, 1.0, 256).reshape(-1, 1)
        rgba = _np.zeros((256, 1, 4))
        rgba[..., 0] = r
        rgba[..., 1] = g
        rgba[..., 2] = b
        rgba[..., 3] = grad * 0.9  # fade to transparent at the baseline
        img = ax.imshow(
            rgba, aspect="auto", origin="lower",
            extent=[float(_np.nanmin(x)), float(_np.nanmax(x)), lo, top],
            zorder=zorder,
        )
        img.set_clip_path(poly.get_paths()[0], transform=ax.transData)
        img.set_gid(gid)
        poly.set_alpha(0.0)  # the gradient image is the visible fill now
    except Exception:
        logger.debug("gradient fill failed", exc_info=True)


def _apply_line_drop_lines(line, d: Dict[str, Any]) -> None:
    """Vertical drop lines from each data point down to the baseline (y=0) —
    Origin's classic 'drop lines' decoration."""
    ax = line.axes
    if ax is None:
        return
    gid = _line_gid(line, "drop")
    _remove_gid_artists(ax, gid)
    if not d.get("drop_lines"):
        return
    x, y = _finite_xy(line)
    if x.size == 0:
        return
    # thin the same way value labels do so dense data stays readable
    every = 1
    if x.size > 200:
        every = int(np.ceil(x.size / 200))
    color = d.get("drop_line_color") or _to_hex(line.get_color())
    style = str(d.get("drop_line_style", "-") or "-")
    width = float(d.get("drop_line_width", 0.8) or 0.8)
    z = line.get_zorder() - 0.4
    segs = np.column_stack([
        np.repeat(x[::every], 2),
        np.column_stack([np.zeros_like(y[::every]), y[::every]]).ravel(),
    ]).reshape(-1, 2, 2)
    from matplotlib.collections import LineCollection
    lc = LineCollection(segs, colors=color, linewidths=width, linestyles=style,
                        zorder=z)
    lc.set_gid(gid)
    ax.add_collection(lc)


def _apply_line_extrema(line, d: Dict[str, Any]) -> None:
    """Mark and label the maximum and minimum data points."""
    ax = line.axes
    if ax is None:
        return
    gid = _line_gid(line, "extrema")
    _remove_gid_artists(ax, gid)
    if not d.get("label_extrema"):
        return
    x, y = _finite_xy(line)
    if x.size == 0:
        return
    fmt = str(d.get("extrema_fmt") or "%.3g")
    try:
        fmt % 1.0
    except (TypeError, ValueError):
        fmt = "%.3g"
    size = float(d.get("extrema_size", 9.0) or 9.0)
    color = _to_hex(line.get_color())
    z = line.get_zorder() + 0.5
    for idx, dy in ((int(np.argmax(y)), 8), (int(np.argmin(y)), -12)):
        xv, yv = float(x[idx]), float(y[idx])
        marker = ax.plot([xv], [yv], marker="o", markersize=size * 0.7,
                         markerfacecolor=color, markeredgecolor="white",
                         markeredgewidth=0.8, linestyle="None", zorder=z)[0]
        marker.set_gid(gid)
        ax.annotate(fmt % yv, (xv, yv), textcoords="offset points",
                    xytext=(0, dy), ha="center", fontsize=size, color=color,
                    fontweight="bold", gid=gid, clip_on=True, zorder=z)


def _apply_line_value_labels(line, d: Dict[str, Any]) -> None:
    """Numeric labels above every Nth data point (auto-thinned when dense)."""
    ax = line.axes
    if ax is None:
        return
    gid = _line_gid(line, "vlab")
    _remove_gid_artists(ax, gid)
    if not d.get("value_labels"):
        return
    x, y = _finite_xy(line)
    if x.size == 0:
        return
    every = max(1, int(d.get("value_labels_every", 1) or 1))
    # never draw an unreadable wall of text on dense data
    if x.size / every > 200:
        every = int(np.ceil(x.size / 200))
    fmt = str(d.get("value_labels_fmt") or "%.3g")
    try:
        fmt % 1.0
    except (TypeError, ValueError):
        fmt = "%.3g"
    color = d.get("value_labels_color") or _to_hex(line.get_color())
    size = float(d.get("value_labels_size", 8.0) or 8.0)
    for xv, yv in zip(x[::every], y[::every]):
        ax.annotate(
            fmt % yv, (xv, yv), textcoords="offset points", xytext=(0, 6),
            ha="center", fontsize=size, color=color, gid=gid, clip_on=True,
        )


def _apply_line_errorbars(line, d: Dict[str, Any]) -> None:
    """Constant or percent Y error bars as a decoration on an existing curve."""
    ax = line.axes
    if ax is None:
        return
    gid = _line_gid(line, "err")
    _remove_gid_artists(ax, gid)
    mode = str(d.get("errorbar_mode", "none"))
    if mode not in ERRORBAR_MODES or mode == "none":
        return
    x, y = _finite_xy(line)
    if x.size == 0:
        return
    value = float(d.get("errorbar_value", 5.0) or 0.0)
    err = np.abs(y) * value / 100.0 if mode == "percent" else np.full_like(y, abs(value))
    color = d.get("errorbar_color") or _to_hex(line.get_color())
    container = ax.errorbar(
        x, y, yerr=err, fmt="none", ecolor=color,
        elinewidth=max(0.8, float(line.get_linewidth()) * 0.75),
        capsize=float(d.get("errorbar_capsize", 3.0) or 0.0),
        alpha=float(d.get("errorbar_alpha", 0.9)),
        zorder=line.get_zorder() - 0.25,
    )
    container._ps_gid = gid
    for group in container.lines[1:]:  # caplines + barlinecols
        for artist in group:
            artist.set_gid(gid)


def _apply_line_decorations(line, d: Dict[str, Any]) -> None:
    _apply_line_fill(line, d)
    _apply_line_value_labels(line, d)
    _apply_line_errorbars(line, d)
    _apply_line_drop_lines(line, d)
    _apply_line_extrema(line, d)
    # remember what was applied so read_line_style reports reality
    try:
        line._ps_deco = {k: d.get(k, v) for k, v in LINE_DECO_DEFAULTS.items()}
    except Exception:
        logger.debug("line decoration state store failed", exc_info=True)
    set_line_decorations_visible(line, bool(line.get_visible()))


def _apply_inset(ax, cfg: Dict[str, Any]) -> None:
    """Create/refresh/remove a zoomed inset panel of the axes' own curves."""
    try:
        prev = getattr(ax, "_ps_inset_ax", None)
        if prev is not None:
            try:
                prev.remove()
            except Exception:
                logger.debug("inset removal failed", exc_info=True)
            ax._ps_inset_ax = None
        for mark in getattr(ax, "_ps_inset_marks", ()) or ():
            try:
                mark.remove()
            except Exception:
                logger.debug("inset indicator removal failed", exc_info=True)
        ax._ps_inset_marks = ()
        ax._ps_inset_cfg = None
        if not cfg.get("enabled"):
            return

        loc = str(cfg.get("loc", "upper right"))
        size = max(15.0, min(60.0, float(cfg.get("size", 38.0) or 38.0))) / 100.0
        pad = 0.06
        x0 = 1.0 - size - pad if "right" in loc else pad
        y0 = 1.0 - size - pad if "upper" in loc else pad
        axins = ax.inset_axes([x0, y0, size, size])
        axins.set_gid("_ps_inset")
        axins.set_in_layout(False)  # keep tight_layout away from the child axes

        xmin = float(cfg.get("xmin", 0.0))
        xmax = float(cfg.get("xmax", 1.0))
        if xmax <= xmin:
            xmin, xmax = sorted((xmin, xmax)) or (xmin, xmin + 1.0)
            if xmax == xmin:
                xmax = xmin + 1.0
        ys = []
        for curve in list_line_artists(ax):
            x, y = _finite_xy(curve)
            if x.size < 2:
                continue
            axins.plot(
                x, y,
                color=curve.get_color(), linewidth=curve.get_linewidth(),
                linestyle=curve.get_linestyle(), marker=curve.get_marker(),
                markersize=curve.get_markersize(), alpha=curve.get_alpha() or 1.0,
            )
            inside = y[(x >= xmin) & (x <= xmax)]
            if inside.size:
                ys.append((float(np.min(inside)), float(np.max(inside))))
        axins.set_xlim(xmin, xmax)
        if ys:
            lo = min(pair[0] for pair in ys)
            hi = max(pair[1] for pair in ys)
            span = (hi - lo) or 1.0
            axins.set_ylim(lo - 0.08 * span, hi + 0.08 * span)
        axins.tick_params(labelsize=7)
        marks = []
        if cfg.get("indicate", True):
            try:
                indicator = ax.indicate_inset_zoom(axins, edgecolor="0.5")
                if isinstance(indicator, tuple):  # matplotlib < 3.10
                    rect, connectors = indicator
                    rect.set_gid("_ps_inset_box")
                    marks = [rect, *connectors]
                else:  # >= 3.10: one InsetIndicator that removes as a unit
                    indicator.set_gid("_ps_inset_box")
                    marks = [indicator]
            except Exception:
                logger.debug("indicate_inset_zoom failed", exc_info=True)
        ax._ps_inset_ax = axins
        ax._ps_inset_marks = tuple(marks)
        ax._ps_inset_cfg = {k: cfg.get(k, v) for k, v in INSET_DEFAULTS.items()}
    except Exception:
        logger.debug("inset apply failed", exc_info=True)


def _axes_mappables(ax):
    """Colormapped artists (images, pcolormesh/scatter with array data)."""
    mappables = list(ax.images)
    for coll in ax.collections:
        try:
            if coll.get_array() is not None and getattr(coll.get_array(), "size", 0):
                mappables.append(coll)
        except Exception:
            continue
    return mappables


def _apply_colorbar(ax, cfg: Dict[str, Any]) -> None:
    """Restyle the colormap/colorbar of image-like plots (heatmap, spectrogram)."""
    try:
        mappables = _axes_mappables(ax)
        if not mappables:
            ax._ps_colorbar_cfg = None
            return
        cmap = str(cfg.get("cmap", "") or "")
        if cmap:
            for mappable in mappables:
                mappable.set_cmap(cmap)
        target = getattr(ax, "_ps_colorbar", None)
        if target is None:
            # a colorbar the plot module already made hangs off the mappable
            target = next(
                (m.colorbar for m in mappables if getattr(m, "colorbar", None)), None
            )
        if cfg.get("enabled") and target is None and ax.figure is not None:
            target = ax.figure.colorbar(
                mappables[0], ax=ax, shrink=float(cfg.get("shrink", 1.0) or 1.0)
            )
            ax._ps_colorbar = target
        elif not cfg.get("enabled") and getattr(ax, "_ps_colorbar", None) is not None:
            try:
                ax._ps_colorbar.remove()
            except Exception:
                logger.debug("colorbar removal failed", exc_info=True)
            ax._ps_colorbar = None
            target = next(
                (m.colorbar for m in mappables if getattr(m, "colorbar", None)), None
            )
        if target is not None:
            if cfg.get("label"):
                target.set_label(str(cfg["label"]))
            target.ax.tick_params(labelsize=float(cfg.get("tick_size", 8.0) or 8.0))
        ax._ps_colorbar_cfg = {k: cfg.get(k, v) for k, v in COLORBAR_DEFAULTS.items()}
    except Exception:
        logger.debug("colorbar apply failed", exc_info=True)
