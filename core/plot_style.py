"""Graph-customization engine (OriginPro-style "Plot Details").

Pure matplotlib logic, no Qt, so the whole style layer is unit-testable and
reusable (session save, workflow, templates). A *style* is a plain nested dict
so it round-trips through JSON.

Top-level keys: ``axes``, ``grid``, ``legend``, ``figure``. Per-curve styling
lives in :func:`read_line_style` / :func:`apply_line_style`.
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
SCALES = ["linear", "log"]
TICK_DIRECTIONS = ["out", "in", "inout"]
LEGEND_LOCS = [
    "best", "upper right", "upper left", "lower left", "lower right",
    "right", "center left", "center right", "lower center",
    "upper center", "center",
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
        },
        "grid": {
            "major": bool(grid_on),
            "color": grid_ref.get_color() if grid_ref else "#3a3f44",
            "linestyle": grid_ref.get_linestyle() if grid_ref else "-",
            "alpha": float(grid_ref.get_alpha() or 1.0) if grid_ref else 0.3,
        },
        "legend": {
            "visible": legend is not None and legend.get_visible(),
            "loc": "best",
            "fontsize": 10.0,
            "frame": legend.get_frame_on() if legend else True,
            "ncol": 1,
        },
        "figure": {
            "facecolor": _to_hex(ax.get_facecolor()),
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
    if fig is not None:
        style["figure"]["fig_facecolor"] = _to_hex(fig.get_facecolor())
    return style


# --- apply ------------------------------------------------------------------
def apply_style(ax, style: Dict[str, Any], fig=None) -> None:
    """Apply a style dict to ``ax`` (and ``fig``). Unknown keys are ignored."""
    a = style.get("axes", {})
    if "title" in a:
        ax.set_title(a["title"], fontsize=a.get("title_size"))
    if "xlabel" in a:
        ax.set_xlabel(a["xlabel"], fontsize=a.get("label_size"))
    if "ylabel" in a:
        ax.set_ylabel(a["ylabel"], fontsize=a.get("label_size"))
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

    # custom tick spacing (MultipleLocator); None/0 = leave matplotlib's auto
    _apply_locator(ax.xaxis, a.get("x_major_spacing"), major=True)
    _apply_locator(ax.xaxis, a.get("x_minor_spacing"), major=False)
    _apply_locator(ax.yaxis, a.get("y_major_spacing"), major=True)
    _apply_locator(ax.yaxis, a.get("y_minor_spacing"), major=False)

    g = style.get("grid", {})
    if g:
        if g.get("major"):
            ax.grid(True, which="major",
                    color=g.get("color", "#3a3f44"),
                    linestyle=g.get("linestyle", "-"),
                    alpha=float(g.get("alpha", 0.3)))
        else:
            ax.grid(False)
        if g.get("minor"):
            ax.minorticks_on()
            ax.grid(True, which="minor",
                    color=g.get("color", "#3a3f44"),
                    linestyle=g.get("linestyle", ":"),
                    alpha=float(g.get("alpha", 0.3)) * 0.5)

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
                )
                if new_leg is not None:
                    new_leg.set_visible(True)
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
    if fig is not None and (f.get("width_in") or f.get("height_in")):
        try:
            cur_w, cur_h = fig.get_size_inches()
            fig.set_size_inches(float(f.get("width_in", cur_w)),
                                float(f.get("height_in", cur_h)))
        except Exception:
            pass
    if fig is not None and f.get("dpi"):
        try:
            fig.set_dpi(float(f["dpi"]))
        except Exception:
            pass


def _apply_locator(axis, spacing, major: bool) -> None:
    """Set a MultipleLocator at ``spacing`` on a matplotlib axis (major/minor).

    ``spacing`` None or <= 0 leaves matplotlib's automatic locator in place.
    """
    s = _num_or_none(spacing)
    if s is None or s <= 0:
        return
    from matplotlib.ticker import MultipleLocator
    if major:
        axis.set_major_locator(MultipleLocator(s))
    else:
        axis.set_minor_locator(MultipleLocator(s))


# --- per-curve --------------------------------------------------------------
def read_line_style(line) -> Dict[str, Any]:
    """Capture a Line2D's style as a dict."""
    marker = line.get_marker()
    return {
        "label": line.get_label(),
        "color": _to_hex(line.get_color()),
        "linewidth": float(line.get_linewidth()),
        "linestyle": _normalize_linestyle(line.get_linestyle()),
        "marker": "None" if marker in (None, "", "none", " ") else str(marker),
        "markersize": float(line.get_markersize()),
        "alpha": float(line.get_alpha()) if line.get_alpha() is not None else 1.0,
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
    if "alpha" in d and d["alpha"] is not None:
        line.set_alpha(float(d["alpha"]))
    if "label" in d and d["label"]:
        line.set_label(d["label"])


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


def list_line_artists(ax) -> List[Any]:
    """The Line2D artists that carry a real (non-underscore) label, in order."""
    return [ln for ln in ax.get_lines()]
