"""Graph-customization engine (OriginPro-style "Plot Details").

Pure matplotlib logic, no Qt, so the whole style layer is unit-testable and
reusable (session save, workflow, templates). A *style* is a plain nested dict
so it round-trips through JSON.

Top-level keys: ``axes``, ``tick_labels``, ``grid``, ``legend``, ``figure``.
Per-curve styling lives in :func:`read_line_style` / :func:`apply_line_style`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

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
JOURNAL_PRESETS = {
    "IEEE (single column)": {
        "figure": {"width_in": 3.5, "height_in": 2.6, "dpi": 300},
        "axes": {"title_size": 9, "label_size": 8, "tick_size": 7},
        "legend": {"fontsize": 7},
    },
    "Nature (single column)": {
        "figure": {"width_in": 3.50, "height_in": 2.63, "dpi": 300},
        "axes": {"title_size": 8, "label_size": 7, "tick_size": 6},
        "legend": {"fontsize": 6},
    },
    "Science (single column)": {
        "figure": {"width_in": 2.24, "height_in": 2.0, "dpi": 300},
        "axes": {"title_size": 8, "label_size": 7, "tick_size": 6},
        "legend": {"fontsize": 6},
    },
    "ACS (single column)": {
        "figure": {"width_in": 3.33, "height_in": 2.5, "dpi": 300},
        "axes": {"title_size": 9, "label_size": 8, "tick_size": 7},
        "legend": {"fontsize": 7},
    },
    "Thesis (large)": {
        "figure": {"width_in": 6.5, "height_in": 4.5, "dpi": 300},
        "axes": {"title_size": 14, "label_size": 12, "tick_size": 10},
        "legend": {"fontsize": 11},
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
    },
}


def get_preset_style(name: str) -> Dict[str, Any]:
    """Return a deep copy of the named journal preset's style fragment."""
    import copy
    preset = JOURNAL_PRESETS.get(name)
    if preset is None:
        raise ValueError(f"unknown journal preset: {name!r}")
    return copy.deepcopy(preset)


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
_ATOMIC_SECTIONS = ("grid", "legend", "tick_labels", "effects")


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

    # reference lines (horizontal / vertical guide at a value)
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
                    frame = new_leg.get_frame()
                    try:
                        frame.set_facecolor(leg.get("facecolor", "#1e2126"))
                        frame.set_edgecolor(leg.get("edgecolor", "#3a3f44"))
                        frame.set_alpha(float(leg.get("alpha", 1.0)))
                    except Exception:
                        pass
                    title_obj = new_leg.get_title()
                    if title_obj is not None and leg.get("title"):
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
        "glow": False,
        "glow_color": _to_hex(line.get_color()),
        "glow_width": 5.0,
        "glow_alpha": 0.35,
        "shadow": False,
        "shadow_alpha": 0.25,
        "shadow_offset_x": 1.5,
        "shadow_offset_y": 1.5,
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
    _apply_line_effects(line, d)


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
    """The Line2D artists that carry a real (non-underscore) label, in order."""
    return [ln for ln in ax.get_lines()]
