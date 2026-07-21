"""In-memory graph-format clipboard.

The clipboard deliberately captures *appearance*, not graph content.  Titles,
axis labels, scales, limits, locators/formatters, reference-line positions,
annotations, data mappings and layer visibility always belong to the target
graph.  Artist styles are matched by logical ``GraphTab.layers`` first, with a
safe Matplotlib-artist fallback for gallery and analysis plots.
"""
from __future__ import annotations

import copy
import json
import logging
import math
from collections.abc import Iterable
from typing import Any

import numpy as np
from matplotlib.artist import Artist
from matplotlib.collections import Collection, PathCollection
from matplotlib.image import AxesImage
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from core.plot_style import (
    COLORBAR_DEFAULTS,
    INSET_DEFAULTS,
    LINE_DECO_DEFAULTS,
    apply_line_style,
    apply_style,
    read_line_style,
)


FORMAT_CLIPBOARD_VERSION = 1
PERSISTED_FORMAT_VERSION = 2
LOG = logging.getLogger(__name__)

_LINE_KEYS = (
    "color", "linewidth", "linestyle", "marker", "markersize",
    "markerfacecolor", "markeredgecolor", "markeredgewidth", "fillstyle",
    "drawstyle", "zorder",
)
_LINE_EFFECT_KEYS = (
    "glow", "glow_color", "glow_width", "glow_alpha", "shadow",
    "shadow_alpha", "shadow_offset_x", "shadow_offset_y",
)


def _json_value(value: Any) -> Any:
    """Return a strict-JSON value or raise for unsupported runtime objects."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.floating)):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Non-finite values cannot be saved in a graph format")
        return result
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist())
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise TypeError(f"Unsupported graph-format value: {type(value).__name__}")


def _encode_path_effects(effects: Any) -> list[dict[str, Any]]:
    """Encode the supported Matplotlib path effects without pickle/repr."""
    from matplotlib import patheffects as pe

    encoded: list[dict[str, Any]] = []
    for effect in effects or ():
        data: dict[str, Any]
        if isinstance(effect, pe.Normal):
            data = {"type": "Normal", "offset": getattr(effect, "_offset", (0, 0))}
        elif isinstance(effect, pe.Stroke):
            data = {
                "type": "Stroke", "offset": getattr(effect, "_offset", (0, 0)),
                "kwargs": getattr(effect, "_gc", {}) or {},
            }
        elif isinstance(effect, pe.SimpleLineShadow):
            data = {
                "type": "SimpleLineShadow",
                "offset": getattr(effect, "_offset", (2, -2)),
                "shadow_color": getattr(effect, "_shadow_color", "#000000"),
                "alpha": getattr(effect, "_alpha", 0.3),
                "rho": getattr(effect, "_rho", 0.3),
                "kwargs": getattr(effect, "_gc", {}) or {},
            }
        elif isinstance(effect, pe.SimplePatchShadow):
            data = {
                "type": "SimplePatchShadow",
                "offset": getattr(effect, "_offset", (2, -2)),
                "shadow_rgbFace": getattr(effect, "_shadow_rgbFace", None),
                "alpha": getattr(effect, "_alpha", None),
                "rho": getattr(effect, "_rho", 0.3),
                "kwargs": getattr(effect, "_gc", {}) or {},
            }
        else:
            LOG.warning("Skipping unsupported path effect %s", type(effect).__name__)
            continue
        try:
            encoded.append(_json_value(data))
        except (TypeError, ValueError):
            LOG.warning("Skipping non-serializable path effect %s", type(effect).__name__)
    return encoded


def _decode_path_effects(items: Any) -> list[Any]:
    """Decode only the explicit path-effect whitelist used above."""
    from matplotlib import patheffects as pe

    result: list[Any] = []
    for item in items or ():
        if not isinstance(item, dict):
            # Compatibility with pre-codec in-memory snapshots.
            if hasattr(item, "draw_path"):
                result.append(copy.deepcopy(item))
            continue
        kind = item.get("type")
        offset = tuple(item.get("offset", (0, 0)))
        kwargs = dict(item.get("kwargs", {}) or {})
        try:
            if kind == "Normal":
                result.append(pe.Normal(offset=offset))
            elif kind == "Stroke":
                result.append(pe.Stroke(offset=offset, **kwargs))
            elif kind == "SimpleLineShadow":
                result.append(pe.SimpleLineShadow(
                    offset=offset,
                    shadow_color=item.get("shadow_color", "#000000"),
                    alpha=item.get("alpha", 0.3),
                    rho=item.get("rho", 0.3),
                    **kwargs,
                ))
            elif kind == "SimplePatchShadow":
                result.append(pe.SimplePatchShadow(
                    offset=offset,
                    shadow_rgbFace=item.get("shadow_rgbFace"),
                    alpha=item.get("alpha"),
                    rho=item.get("rho", 0.3),
                    **kwargs,
                ))
        except Exception:
            LOG.warning("Ignoring invalid persisted path effect %r", kind, exc_info=True)
    return result


def _hex(color: Any) -> str | None:
    try:
        from matplotlib.colors import to_hex

        return to_hex(color, keep_alpha=False)
    except Exception:
        return None


def _first_color(colors: Any) -> str | None:
    try:
        array = np.asarray(colors)
        if array.size == 0:
            return None
        if array.ndim > 1:
            array = array[0]
        return _hex(array)
    except Exception:
        return _hex(colors)


def _uniform_color(colors: Any) -> str | None:
    """Return one colour only when the artist does not encode per-item colour."""
    try:
        array = np.asarray(colors, dtype=float)
        if array.size == 0:
            return None
        rows = array.reshape(-1, array.shape[-1]) if array.ndim > 1 else array.reshape(1, -1)
        if rows.shape[0] > 1 and not np.allclose(rows, rows[0], equal_nan=True):
            return None
        return _hex(rows[0])
    except Exception:
        return _first_color(colors)


def _uniform_float(values: Any) -> float | None:
    try:
        array = np.asarray(values, dtype=float).ravel()
        if array.size == 0 or not np.all(np.isfinite(array)):
            return None
        if array.size > 1 and not np.allclose(array, array[0], equal_nan=True):
            return None
        return float(array[0])
    except Exception:
        return None


def _plain_float(value: Any) -> float | None:
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _artist_gid(artist: Any) -> str:
    try:
        return str(artist.get_gid() or "")
    except Exception:
        return ""


def _is_transferable_artist(artist: Any, ax: Any) -> bool:
    if not isinstance(artist, Artist) or getattr(artist, "axes", None) is not ax:
        return False
    if _artist_gid(artist).startswith("_ps_"):
        return False
    if isinstance(artist, Line2D):
        # axhline/axvline, break marks and cursor guides use blended/axes
        # transforms.  They are graph content, not a data-series format.
        try:
            if artist.get_transform() is not ax.transData:
                return False
        except Exception:
            pass
    return isinstance(artist, (Line2D, Collection, Patch, AxesImage))


def _flatten_artists(value: Any) -> list[Artist]:
    result: list[Artist] = []

    def visit(item: Any) -> None:
        if isinstance(item, Artist):
            result.append(item)
        elif isinstance(item, Iterable) and not isinstance(item, (str, bytes, dict)):
            for child in item:
                visit(child)

    visit(value)
    return result


def _format_axes(tab: Any) -> tuple[Any, list[Any]]:
    if tab is None or not hasattr(tab, "get_axes"):
        raise ValueError("The target is not a graph")
    primary = tab.get_axes()
    if primary is None:
        raise ValueError("The graph has no axes")
    fig = tab.get_figure() if hasattr(tab, "get_figure") else primary.figure
    inset_axes = {
        getattr(candidate, "_ps_inset_ax", None)
        for candidate in getattr(fig, "axes", ())
    }
    axes: list[Any] = [primary]
    for candidate in getattr(fig, "axes", ()):
        if candidate is primary or candidate in inset_axes:
            continue
        try:
            if candidate.get_label() in {"<colorbar>", "_ps_inset"}:
                continue
            if _artist_gid(candidate).startswith("_ps_"):
                continue
        except Exception:
            pass
        axes.append(candidate)
    return fig, axes


def _series_groups(tab: Any, ax: Any) -> list[dict[str, Any]]:
    """Return logical data-series groups, preferring GraphTab layer records."""
    groups: list[dict[str, Any]] = []
    seen: set[int] = set()

    for info in (getattr(tab, "layers", {}) or {}).values():
        artists = [
            artist for artist in _flatten_artists(info.get("artists", []))
            if _is_transferable_artist(artist, ax)
        ]
        if not artists:
            continue
        groups.append({"artists": artists, "layer": info})
        seen.update(id(artist) for artist in artists)

    # Matplotlib containers keep N bar/histogram patches or the pieces of one
    # error-bar series together.  Treat each as one logical series.
    for container in getattr(ax, "containers", ()):
        artists = [
            artist for artist in _flatten_artists(container)
            if id(artist) not in seen and _is_transferable_artist(artist, ax)
        ]
        if artists:
            groups.append({"artists": artists, "layer": None})
            seen.update(id(artist) for artist in artists)

    for artist in list(getattr(ax, "lines", ())):
        if id(artist) not in seen and _is_transferable_artist(artist, ax):
            groups.append({"artists": [artist], "layer": None})
            seen.add(id(artist))
    for artist in list(getattr(ax, "collections", ())):
        if id(artist) not in seen and _is_transferable_artist(artist, ax):
            groups.append({"artists": [artist], "layer": None})
            seen.add(id(artist))
    for artist in list(getattr(ax, "images", ())):
        if id(artist) not in seen and _is_transferable_artist(artist, ax):
            groups.append({"artists": [artist], "layer": None})
            seen.add(id(artist))

    # Unregistered bar-like patches are included only when they have a public
    # label.  Anonymous annotation shapes are intentionally left alone.
    for artist in list(getattr(ax, "patches", ())):
        try:
            label = str(artist.get_label() or "")
        except Exception:
            label = ""
        if (id(artist) not in seen and label and not label.startswith("_")
                and _is_transferable_artist(artist, ax)):
            groups.append({"artists": [artist], "layer": None})
            seen.add(id(artist))
    return groups


def _capture_text(text: Any) -> dict[str, Any]:
    family = text.get_fontfamily()
    return {
        "color": _hex(text.get_color()),
        "fontsize": _plain_float(text.get_fontsize()),
        "fontfamily": list(family) if isinstance(family, (list, tuple)) else family,
        "fontweight": str(text.get_fontweight()),
        "fontstyle": str(text.get_fontstyle()),
        "rotation": _plain_float(text.get_rotation()),
        "horizontalalignment": str(text.get_horizontalalignment()),
        "verticalalignment": str(text.get_verticalalignment()),
        "alpha": text.get_alpha(),
    }


def _apply_text(text: Any, style: dict[str, Any]) -> None:
    setters = {
        "color": "set_color",
        "fontsize": "set_fontsize",
        "fontfamily": "set_fontfamily",
        "fontweight": "set_fontweight",
        "fontstyle": "set_fontstyle",
        "rotation": "set_rotation",
        "horizontalalignment": "set_horizontalalignment",
        "verticalalignment": "set_verticalalignment",
        "alpha": "set_alpha",
    }
    for key, setter in setters.items():
        if key in style and (style[key] is not None or key == "alpha"):
            try:
                getattr(text, setter)(style[key])
            except Exception:
                pass


def _first_tick(axis: Any, which: str) -> Any:
    try:
        ticks = axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
        return ticks[0] if ticks else None
    except Exception:
        return None


def _capture_tick(axis: Any, which: str) -> dict[str, Any] | None:
    tick = _first_tick(axis, which)
    if tick is None:
        return None
    line = tick.tick1line
    label = tick.label1
    return {
        "direction": getattr(tick, "_tickdir", None),
        "length": _plain_float(line.get_markersize()),
        "width": _plain_float(line.get_markeredgewidth()),
        "color": _hex(line.get_color()),
        "line_alpha": line.get_alpha(),
        "label": _capture_text(label),
        "pad": _plain_float(tick.get_pad()),
        "tick1": bool(tick.tick1line.get_visible()),
        "tick2": bool(tick.tick2line.get_visible()),
        "label1": bool(tick.label1.get_visible()),
        "label2": bool(tick.label2.get_visible()),
    }


def _apply_tick(ax: Any, axis_name: str, which: str, style: dict[str, Any] | None) -> None:
    if not style:
        return
    kwargs = {
        key: style[key]
        for key in ("direction", "length", "width", "color", "pad")
        if style.get(key) is not None
    }
    label_style = style.get("label", {})
    if label_style.get("color"):
        kwargs["labelcolor"] = label_style["color"]
    if label_style.get("fontsize") is not None:
        kwargs["labelsize"] = label_style["fontsize"]
    if label_style.get("rotation") is not None:
        kwargs["labelrotation"] = label_style["rotation"]
    try:
        ax.tick_params(axis=axis_name, which=which, **kwargs)
    except Exception:
        pass
    axis = getattr(ax, f"{axis_name}axis", None)
    if axis is None:
        return
    try:
        ticks = axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
    except Exception:
        ticks = []
    for tick in ticks:
        for line in (tick.tick1line, tick.tick2line):
            try:
                line.set_alpha(style.get("line_alpha"))
            except Exception:
                pass
        for label in (tick.label1, tick.label2):
            _apply_text(label, label_style)
        for key, obj in (
            ("tick1", tick.tick1line), ("tick2", tick.tick2line),
            ("label1", tick.label1), ("label2", tick.label2),
        ):
            try:
                obj.set_visible(bool(style[key]))
            except Exception:
                pass


def _capture_grid(axis: Any, which: str) -> dict[str, Any] | None:
    try:
        ticks = axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
        lines = [tick.gridline for tick in ticks]
    except Exception:
        lines = []
    if not lines:
        return None
    ref = next((line for line in lines if line.get_visible()), lines[0])
    return {
        "visible": any(line.get_visible() for line in lines),
        "color": _hex(ref.get_color()),
        "linestyle": ref.get_linestyle(),
        "linewidth": _plain_float(ref.get_linewidth()),
        "alpha": ref.get_alpha(),
    }


def _apply_grid(axis: Any, which: str, style: dict[str, Any] | None) -> None:
    if not style:
        return
    visible = bool(style.get("visible"))
    try:
        if visible:
            kwargs = {
                key: style[key]
                for key in ("color", "linestyle", "linewidth", "alpha")
                if style.get(key) is not None
            }
            axis.grid(True, which=which, **kwargs)
        else:
            axis.grid(False, which=which)
    except Exception:
        pass


def _capture_legend(ax: Any) -> dict[str, Any]:
    legend = ax.get_legend()
    handles, labels = ax.get_legend_handles_labels()
    public = [(h, str(lbl)) for h, lbl in zip(handles, labels)
              if lbl and not str(lbl).startswith("_")]
    if legend is None:
        return {
            "format": {"exists": False, "visible": False},
            "content": {"exists": False, "handles": [h for h, _ in public],
                        "labels": [lbl for _, lbl in public], "title": ""},
        }

    legend_labels = [text.get_text() for text in legend.get_texts()]
    available = list(public)
    selected_handles: list[Any] = []
    for label in legend_labels:
        match = next((i for i, (_handle, candidate) in enumerate(available)
                      if candidate == label), None)
        if match is None:
            continue
        selected_handles.append(available.pop(match)[0])
    if len(selected_handles) != len(legend_labels):
        proxies = list(getattr(legend, "legend_handles",
                               getattr(legend, "legendHandles", ())))
        selected_handles = proxies[:len(legend_labels)]

    texts = legend.get_texts()
    text_style = _capture_text(texts[0]) if texts else {}
    frame = legend.get_frame()
    title = legend.get_title()
    fmt = {
        "exists": True,
        "visible": bool(legend.get_visible()),
        "loc": copy.deepcopy(getattr(legend, "_loc", "best")),
        "ncol": int(getattr(legend, "_ncols", getattr(legend, "_ncol", 1)) or 1),
        "frameon": bool(legend.get_frame_on()),
        "fancybox": "round" in type(frame.get_boxstyle()).__name__.lower(),
        "shadow": bool(getattr(legend, "shadow", False)),
        "markerscale": _plain_float(getattr(legend, "markerscale", 1.0)),
        "borderpad": _plain_float(getattr(legend, "borderpad", 0.4)),
        "labelspacing": _plain_float(getattr(legend, "labelspacing", 0.5)),
        "handlelength": _plain_float(getattr(legend, "handlelength", 2.0)),
        "columnspacing": _plain_float(getattr(legend, "columnspacing", 2.0)),
        "facecolor": _hex(frame.get_facecolor()),
        "edgecolor": _hex(frame.get_edgecolor()),
        "frame_alpha": frame.get_alpha(),
        "frame_linewidth": _plain_float(frame.get_linewidth()),
        "frame_linestyle": frame.get_linestyle(),
        "text": text_style,
        "title": _capture_text(title),
        "draggable": bool(legend.get_draggable()),
    }
    return {
        "format": fmt,
        "content": {
            "exists": True,
            "handles": selected_handles,
            "labels": legend_labels,
            "title": title.get_text(),
        },
    }


def _apply_legend(ax: Any, style: dict[str, Any], content: dict[str, Any]) -> None:
    existing = ax.get_legend()
    if not style.get("exists"):
        if existing is not None:
            existing.remove()
        return
    if not style.get("visible"):
        if existing is not None:
            existing.set_visible(False)
        return
    handles = list(content.get("handles", ()))
    labels = list(content.get("labels", ()))
    if not handles or len(handles) != len(labels):
        handles, labels = ax.get_legend_handles_labels()
        pairs = [(h, lbl) for h, lbl in zip(handles, labels)
                 if lbl and not str(lbl).startswith("_")]
        handles = [h for h, _ in pairs]
        labels = [lbl for _, lbl in pairs]
    if not handles:
        if existing is not None:
            existing.remove()
        return
    kwargs = {
        "loc": style.get("loc", "best"),
        "ncol": max(1, int(style.get("ncol", 1))),
        "frameon": bool(style.get("frameon", True)),
        "fancybox": bool(style.get("fancybox", True)),
        "shadow": bool(style.get("shadow", False)),
        "title": content.get("title") or None,
    }
    for key in ("markerscale", "borderpad", "labelspacing", "handlelength",
                "columnspacing"):
        if style.get(key) is not None:
            kwargs[key] = style[key]
    text_style = style.get("text", {})
    if text_style.get("fontsize") is not None:
        kwargs["fontsize"] = text_style["fontsize"]
    legend = ax.legend(handles, labels, **kwargs)
    frame = legend.get_frame()
    for key, setter in (
        ("facecolor", "set_facecolor"), ("edgecolor", "set_edgecolor"),
        ("frame_alpha", "set_alpha"), ("frame_linewidth", "set_linewidth"),
        ("frame_linestyle", "set_linestyle"),
    ):
        if style.get(key) is not None:
            try:
                getattr(frame, setter)(style[key])
            except Exception:
                pass
    for text in legend.get_texts():
        _apply_text(text, text_style)
    _apply_text(legend.get_title(), style.get("title", {}))
    try:
        draggable = bool(style.get("draggable"))
        legend._ps_drag_enabled = draggable
        legend.set_draggable(draggable)
    except Exception:
        pass


def _capture_spines(ax: Any) -> dict[str, Any]:
    result = {}
    for name, spine in getattr(ax, "spines", {}).items():
        result[name] = {
            "visible": bool(spine.get_visible()),
            "color": _hex(spine.get_edgecolor()),
            "linewidth": _plain_float(spine.get_linewidth()),
            "linestyle": spine.get_linestyle(),
            "alpha": spine.get_alpha(),
        }
    return result


def _apply_spines(ax: Any, styles: dict[str, Any]) -> None:
    for name, style in styles.items():
        spine = getattr(ax, "spines", {}).get(name)
        if spine is None:
            continue
        try:
            spine.set_visible(bool(style.get("visible")))
            if style.get("color"):
                spine.set_edgecolor(style["color"])
            if style.get("linewidth") is not None:
                spine.set_linewidth(style["linewidth"])
            if style.get("linestyle") is not None:
                spine.set_linestyle(style["linestyle"])
            spine.set_alpha(style.get("alpha"))
        except Exception:
            pass


def _capture_3d_axes(ax: Any) -> dict[str, Any]:
    result = {}
    for name in ("x", "y", "z"):
        axis = getattr(ax, f"{name}axis", None)
        pane = getattr(axis, "pane", None)
        if axis is None or pane is None:
            continue
        grid = dict(getattr(axis, "_axinfo", {}).get("grid", {}))
        result[name] = {
            "pane_facecolor": _hex(pane.get_facecolor()),
            "pane_edgecolor": _hex(pane.get_edgecolor()),
            "pane_alpha": pane.get_alpha(),
            "pane_visible": bool(pane.get_visible()),
            "grid": {
                key: (_hex(value) if key == "color" else copy.deepcopy(value))
                for key, value in grid.items()
                if key in {"color", "linewidth", "linestyle"}
            },
        }
    return result


def _apply_3d_axes(ax: Any, styles: dict[str, Any]) -> None:
    for name, style in styles.items():
        axis = getattr(ax, f"{name}axis", None)
        pane = getattr(axis, "pane", None)
        if axis is None or pane is None:
            continue
        try:
            if style.get("pane_facecolor"):
                pane.set_facecolor(style["pane_facecolor"])
            if style.get("pane_edgecolor"):
                pane.set_edgecolor(style["pane_edgecolor"])
            pane.set_alpha(style.get("pane_alpha"))
            pane.set_visible(bool(style.get("pane_visible", True)))
            getattr(axis, "_axinfo", {}).setdefault("grid", {}).update(style.get("grid", {}))
        except Exception:
            pass


def _capture_axes_effect_state(ax: Any) -> dict[str, Any]:
    """Return semantic shadow controls reconciled with the actual patch."""
    cfg = dict(getattr(ax, "_ps_axes_effects", None) or {})
    encoded = _encode_path_effects(ax.patch.get_path_effects())
    shadow = next(
        (item for item in encoded if item.get("type") == "SimplePatchShadow"),
        None,
    )
    cfg["axes_shadow"] = shadow is not None
    if shadow is not None:
        offset = list(shadow.get("offset", (3.0, -3.0)))
        if len(offset) >= 2:
            cfg["shadow_offset_x"] = float(offset[0])
            cfg["shadow_offset_y"] = float(-offset[1])
        if shadow.get("shadow_rgbFace") is not None:
            color = _hex(shadow["shadow_rgbFace"])
            if color:
                cfg["shadow_color"] = color
        if shadow.get("alpha") is not None:
            cfg["shadow_alpha"] = float(shadow["alpha"])
    return cfg


def _capture_axis_appearance(ax: Any) -> dict[str, Any]:
    labels = {}
    ticks = {}
    grids = {}
    for name in ("x", "y", "z"):
        axis = getattr(ax, f"{name}axis", None)
        if axis is None:
            continue
        labels[name] = {
            "text": _capture_text(axis.label),
            "pad": _plain_float(getattr(axis, "labelpad", None)),
            "offset_text": _capture_text(axis.get_offset_text()),
        }
        ticks[name] = {
            "major": _capture_tick(axis, "major"),
            "minor": _capture_tick(axis, "minor"),
        }
        grids[name] = {
            "major": _capture_grid(axis, "major"),
            "minor": _capture_grid(axis, "minor"),
        }
    get_frame_on = getattr(ax, "get_frame_on", None)
    return {
        "facecolor": _hex(ax.get_facecolor()),
        "frameon": bool(get_frame_on()) if callable(get_frame_on) else True,
        "axisbelow": ax.get_axisbelow(),
        "title": _capture_text(ax.title),
        "titles": {
            loc: _capture_text(getattr(ax, f"_{loc}_title", ax.title))
            for loc in ("left", "right")
        },
        "labels": labels,
        "spines": _capture_spines(ax),
        "ticks": ticks,
        "grids": grids,
        "patch_alpha": ax.patch.get_alpha(),
        "patch_effects": _encode_path_effects(ax.patch.get_path_effects()),
        "effects_semantic": _capture_axes_effect_state(ax),
        "three_d": _capture_3d_axes(ax),
    }


def _apply_axis_appearance(ax: Any, style: dict[str, Any]) -> None:
    try:
        if style.get("facecolor"):
            ax.set_facecolor(style["facecolor"])
        set_frame_on = getattr(ax, "set_frame_on", None)
        if callable(set_frame_on):
            set_frame_on(bool(style.get("frameon", True)))
        ax.set_axisbelow(style.get("axisbelow", "line"))
        ax.patch.set_alpha(style.get("patch_alpha"))
        ax.patch.set_path_effects(_decode_path_effects(style.get("patch_effects", [])))
        if isinstance(style.get("effects_semantic"), dict):
            ax._ps_axes_effects = copy.deepcopy(style["effects_semantic"])
    except Exception:
        pass
    _apply_text(ax.title, style.get("title", {}))
    for loc, title_style in style.get("titles", {}).items():
        if loc not in {"left", "right"}:
            continue
        _apply_text(getattr(ax, f"_{loc}_title", ax.title), title_style)
    for name, label_style in style.get("labels", {}).items():
        axis = getattr(ax, f"{name}axis", None)
        if axis is None:
            continue
        _apply_text(axis.label, label_style.get("text", {}))
        _apply_text(axis.get_offset_text(), label_style.get("offset_text", {}))
        if label_style.get("pad") is not None:
            try:
                axis.labelpad = label_style["pad"]
            except Exception:
                pass
    _apply_spines(ax, style.get("spines", {}))
    for name, tick_styles in style.get("ticks", {}).items():
        _apply_tick(ax, name, "major", tick_styles.get("major"))
        _apply_tick(ax, name, "minor", tick_styles.get("minor"))
    for name, grid_styles in style.get("grids", {}).items():
        axis = getattr(ax, f"{name}axis", None)
        if axis is None:
            continue
        _apply_grid(axis, "major", grid_styles.get("major"))
        _apply_grid(axis, "minor", grid_styles.get("minor"))
    _apply_3d_axes(ax, style.get("three_d", {}))


def _capture_line_format(line: Line2D) -> dict[str, Any]:
    current = read_line_style(line)
    semantic_keys = (*_LINE_KEYS, *_LINE_EFFECT_KEYS, *LINE_DECO_DEFAULTS)
    values = {key: copy.deepcopy(current[key]) for key in semantic_keys if key in current}
    values["alpha"] = line.get_alpha()
    return {
        "kind": "line",
        "line": values,
        "path_effects": _encode_path_effects(line.get_path_effects()),
        "color": current.get("color"),
        "edgecolor": current.get("markeredgecolor"),
        "linewidth": current.get("linewidth"),
        "alpha": line.get_alpha(),
        "zorder": _plain_float(line.get_zorder()),
    }


def _capture_collection_format(
    artist: Collection, *, exact_style: bool = False,
) -> dict[str, Any]:
    try:
        mapped = artist.get_array() is not None
    except Exception:
        mapped = False
    try:
        cmap = (
            artist.get_cmap().name
            if mapped and artist.get_cmap() is not None
            else None
        )
    except Exception:
        cmap = None
    result = {
        "kind": "collection",
        "mapped": mapped,
        "cmap": cmap,
        "color": None if mapped else _uniform_color(artist.get_facecolors()),
        "edgecolor": _uniform_color(artist.get_edgecolors()),
        "zorder": _plain_float(artist.get_zorder()),
        "path_effects": _encode_path_effects(artist.get_path_effects()),
    }
    try:
        alpha = artist.get_alpha()
        alpha_array = np.asarray(alpha) if alpha is not None else np.asarray([])
        if alpha_array.ndim == 0:
            result["alpha"] = alpha
        elif exact_style:
            # Keep the compact ndarray by reference. Matplotlib formatting
            # setters replace these arrays; they do not mutate them in place.
            result["alpha"] = alpha_array
    except Exception:
        result["alpha"] = None
    if mapped:
        try:
            result["norm"] = _capture_norm(artist.norm)
            result["clim"] = [_plain_float(value) for value in artist.get_clim()]
        except Exception:
            pass
    elif exact_style:
        # Runtime history and project persistence need exact categorical /
        # per-point styling. Keep compact ndarray references instead of Python
        # lists; project serialization converts them only at the JSON boundary.
        result["restore_exact"] = True
        try:
            facecolors = np.asarray(artist.get_facecolors())
            if len(facecolors) > 1:
                result["facecolors"] = facecolors
        except Exception:
            pass
        try:
            edgecolors = np.asarray(artist.get_edgecolors())
            if len(edgecolors) > 1:
                result["edgecolors"] = edgecolors
        except Exception:
            pass
    try:
        width = _uniform_float(artist.get_linewidths())
        if width is not None:
            result["linewidth"] = width
    except Exception:
        pass
    try:
        result["hatch"] = artist.get_hatch()
    except Exception:
        pass
    if isinstance(artist, PathCollection):
        try:
            size = _uniform_float(artist.get_sizes())
            if size is not None:
                result["marker_size"] = size
            elif exact_style:
                sizes = np.asarray(artist.get_sizes(), dtype=float).ravel()
                if len(sizes) > 1:
                    result["marker_sizes"] = sizes
        except Exception:
            pass
    if exact_style:
        result["restore_exact"] = True
        try:
            if isinstance(artist, PathCollection):
                result["exact_count"] = int(len(artist.get_offsets()))
            else:
                result["exact_count"] = int(len(artist.get_paths()))
        except Exception:
            pass
    return result


def _capture_patch_format(artist: Patch) -> dict[str, Any]:
    return {
        "kind": "patch",
        "color": _hex(artist.get_facecolor()),
        "edgecolor": _hex(artist.get_edgecolor()),
        "linewidth": _plain_float(artist.get_linewidth()),
        "linestyle": artist.get_linestyle(),
        "hatch": artist.get_hatch(),
        "alpha": artist.get_alpha(),
        "zorder": _plain_float(artist.get_zorder()),
        "path_effects": _encode_path_effects(artist.get_path_effects()),
    }


def _capture_image_format(artist: AxesImage) -> dict[str, Any]:
    cmap = artist.get_cmap()
    return {
        "kind": "image",
        "cmap": cmap.name if cmap is not None else None,
        "interpolation": artist.get_interpolation(),
        "alpha": artist.get_alpha(),
        "zorder": _plain_float(artist.get_zorder()),
        "norm": _capture_norm(artist.norm),
        "clim": [_plain_float(value) for value in artist.get_clim()],
    }


def _capture_norm(norm: Any) -> dict[str, Any] | None:
    if norm is None:
        return None
    name = type(norm).__name__
    supported = {
        "Normalize": ("vmin", "vmax", "clip"),
        "LogNorm": ("vmin", "vmax", "clip"),
        "SymLogNorm": ("vmin", "vmax", "clip", "linthresh", "linscale", "base"),
        "PowerNorm": ("vmin", "vmax", "clip", "gamma"),
        "TwoSlopeNorm": ("vmin", "vmax", "vcenter"),
        "BoundaryNorm": ("boundaries", "Ncmap", "clip", "extend"),
        "NoNorm": ("vmin", "vmax", "clip"),
    }
    keys = supported.get(name)
    if keys is None:
        return None
    values = {"type": name}
    for key in keys:
        value = getattr(norm, key, None)
        if value is None and name == "SymLogNorm" and key in {
            "linthresh", "linscale", "base",
        }:
            # Matplotlib exposes linthresh but keeps linscale/base on the
            # version-dependent transform object.
            transform = getattr(norm, "_trf", None)
            if transform is None:
                transform = getattr(getattr(norm, "_scale", None), "_transform", None)
            value = getattr(transform, key, None)
        if isinstance(value, np.ndarray):
            value = value.tolist()
        values[key] = copy.deepcopy(value)
    return values


def _decode_norm(state: Any) -> Any:
    if not isinstance(state, dict):
        return None
    from matplotlib import colors

    kind = str(state.get("type", ""))
    cls = getattr(colors, kind, None)
    if kind not in {
        "Normalize", "LogNorm", "SymLogNorm", "PowerNorm", "TwoSlopeNorm",
        "BoundaryNorm", "NoNorm",
    } or cls is None:
        return None
    kwargs = {key: value for key, value in state.items() if key != "type" and value is not None}
    if kind == "BoundaryNorm" and "Ncmap" in kwargs:
        kwargs["ncolors"] = kwargs.pop("Ncmap")
    try:
        return cls(**kwargs)
    except Exception:
        return None


def _capture_artist_format(
    artist: Any, *, exact_style: bool = False,
) -> dict[str, Any] | None:
    if isinstance(artist, Line2D):
        return _capture_line_format(artist)
    if isinstance(artist, AxesImage):
        return _capture_image_format(artist)
    if isinstance(artist, Collection):
        return _capture_collection_format(artist, exact_style=exact_style)
    if isinstance(artist, Patch):
        return _capture_patch_format(artist)
    return None


def _capture_series_format(
    group: dict[str, Any], *, exact_style: bool = False,
) -> dict[str, Any] | None:
    artists = group.get("artists", [])
    representative = next((artist for artist in artists if isinstance(artist, Line2D)), None)
    if representative is None:
        representative = next((artist for artist in artists
                               if isinstance(artist, Collection)), None)
    if representative is None:
        representative = next((artist for artist in artists
                               if isinstance(artist, Patch)), None)
    if representative is None:
        representative = next((artist for artist in artists
                               if isinstance(artist, AxesImage)), None)
    result = _capture_artist_format(representative, exact_style=exact_style)
    if result is None:
        return None
    members = [
        member for artist in artists
        if (member := _capture_artist_format(
            artist, exact_style=exact_style,
        )) is not None
    ] if len(artists) > 1 else []
    if len(members) > 1:
        result["members"] = members
    return result


def _series_descriptor(group: dict[str, Any], style: dict[str, Any]) -> dict[str, Any]:
    """Stable logical identity used only for fail-safe project restoration."""
    layer = group.get("layer")
    artists = list(group.get("artists", ()))
    label = ""
    layer_style = ""
    if isinstance(layer, dict):
        label = str(layer.get("label", "") or "")
        layer_style = str(layer.get("style", "") or "")
    if not label:
        for artist in artists:
            try:
                candidate = str(artist.get_label() or "")
            except Exception:
                candidate = ""
            if candidate and not candidate.startswith("_"):
                label = candidate
                break
    return {
        "label": label,
        "layer_style": layer_style,
        "kind": str(style.get("kind", "")),
    }


def _axis_series_descriptors(tab: Any, ax: Any) -> list[dict[str, Any]]:
    descriptors = []
    for group in _series_groups(tab, ax):
        style = _capture_series_format(group, exact_style=False)
        if style is not None:
            descriptors.append(_series_descriptor(group, style))
    return descriptors


def _apply_line_format(line: Line2D, style: dict[str, Any]) -> None:
    if style.get("kind") == "line":
        values = dict(style.get("line", {}))
    else:
        values = {
            key: style[key] for key in ("color", "linewidth", "alpha", "zorder")
            if style.get(key) is not None
        }
    values.pop("label", None)
    apply_line_style(line, values)
    if "alpha" in style:
        try:
            line.set_alpha(style.get("alpha"))
        except Exception:
            pass
    try:
        line.set_path_effects(_decode_path_effects(style.get("path_effects", [])))
    except Exception:
        pass


def _apply_collection_format(artist: Collection, style: dict[str, Any]) -> None:
    try:
        target_mapped = artist.get_array() is not None
    except Exception:
        target_mapped = False
    if style.get("cmap") and hasattr(artist, "set_cmap"):
        try:
            artist.set_cmap(style["cmap"])
        except Exception:
            pass
    if style.get("restore_mapping"):
        norm = _decode_norm(style.get("norm"))
        if norm is not None:
            try:
                artist.set_norm(norm)
            except Exception:
                pass
        clim = style.get("clim")
        if isinstance(clim, (list, tuple)) and len(clim) == 2:
            try:
                artist.set_clim(*clim)
            except Exception:
                pass
    exact_compatible = bool(style.get("restore_exact"))
    if exact_compatible and style.get("exact_count") is not None:
        try:
            current_count = (
                len(artist.get_offsets())
                if isinstance(artist, PathCollection)
                else len(artist.get_paths())
            )
            exact_compatible = int(current_count) == int(style["exact_count"])
        except Exception:
            exact_compatible = False
    if exact_compatible:
        if style.get("facecolors") is not None:
            try:
                artist.set_facecolors(style["facecolors"])
            except Exception:
                pass
        if style.get("edgecolors") is not None:
            try:
                artist.set_edgecolors(style["edgecolors"])
            except Exception:
                pass
        if isinstance(artist, PathCollection) and style.get("marker_sizes") is not None:
            try:
                artist.set_sizes(style["marker_sizes"])
            except Exception:
                pass
    if not target_mapped and style.get("color"):
        try:
            artist.set_facecolor(style["color"])
        except Exception:
            try:
                artist.set_color(style["color"])
            except Exception:
                pass
    edge_is_scalar = True
    width_is_scalar = True
    if isinstance(artist, PathCollection):
        try:
            edge_is_scalar = _uniform_color(artist.get_edgecolors()) is not None
        except Exception:
            pass
        try:
            width_is_scalar = _uniform_float(artist.get_linewidths()) is not None
        except Exception:
            pass
    if style.get("edgecolor") and edge_is_scalar:
        try:
            artist.set_edgecolor(style["edgecolor"])
        except Exception:
            pass
    if style.get("linewidth") is not None and width_is_scalar:
        try:
            artist.set_linewidth(style["linewidth"])
        except Exception:
            pass
    if style.get("hatch") is not None:
        try:
            artist.set_hatch(style["hatch"])
        except Exception:
            pass
    if isinstance(artist, PathCollection) and style.get("marker_size") is not None:
        try:
            target_sizes = np.asarray(artist.get_sizes())
            if target_sizes.size <= 1:
                artist.set_sizes([style["marker_size"]])
        except Exception:
            pass
    if "alpha" in style:
        try:
            alpha = style["alpha"]
            alpha_array = np.asarray(alpha) if alpha is not None else np.asarray(0.0)
            if alpha_array.ndim == 0 or exact_compatible:
                artist.set_alpha(alpha)
        except Exception:
            pass
    if "zorder" in style:
        try:
            artist.set_zorder(style["zorder"])
        except Exception:
            pass
    try:
        artist.set_path_effects(_decode_path_effects(style.get("path_effects", [])))
    except Exception:
        pass


def _apply_patch_format(artist: Patch, style: dict[str, Any]) -> None:
    if style.get("color"):
        try:
            artist.set_facecolor(style["color"])
        except Exception:
            pass
    setters = {
        "edgecolor": "set_edgecolor", "linewidth": "set_linewidth",
        "linestyle": "set_linestyle", "hatch": "set_hatch",
        "alpha": "set_alpha", "zorder": "set_zorder",
    }
    for key, setter in setters.items():
        if key in style:
            try:
                getattr(artist, setter)(style[key])
            except Exception:
                pass
    try:
        artist.set_path_effects(_decode_path_effects(style.get("path_effects", [])))
    except Exception:
        pass


def _apply_image_format(artist: AxesImage, style: dict[str, Any]) -> None:
    if style.get("cmap"):
        try:
            artist.set_cmap(style["cmap"])
        except Exception:
            pass
    if style.get("kind") == "image" and style.get("interpolation"):
        try:
            artist.set_interpolation(style["interpolation"])
        except Exception:
            pass
    if style.get("restore_mapping"):
        norm = _decode_norm(style.get("norm"))
        if norm is not None:
            try:
                artist.set_norm(norm)
            except Exception:
                pass
        clim = style.get("clim")
        if isinstance(clim, (list, tuple)) and len(clim) == 2:
            try:
                artist.set_clim(*clim)
            except Exception:
                pass
    for key, setter in (("alpha", "set_alpha"), ("zorder", "set_zorder")):
        if key in style:
            try:
                getattr(artist, setter)(style[key])
            except Exception:
                pass


def _apply_series_format(group: dict[str, Any], style: dict[str, Any]) -> None:
    members = style.get("members") if isinstance(style.get("members"), list) else []
    for index, artist in enumerate(group.get("artists", [])):
        member_style = members[index % len(members)] if members else style
        if isinstance(artist, Line2D):
            _apply_line_format(artist, member_style)
        elif isinstance(artist, AxesImage):
            _apply_image_format(artist, member_style)
        elif isinstance(artist, Collection):
            _apply_collection_format(artist, member_style)
        elif isinstance(artist, Patch):
            _apply_patch_format(artist, member_style)


def _layer_kwargs(group: dict[str, Any]) -> dict[str, Any]:
    artists = group.get("artists", [])
    representative = artists[0] if artists else None
    layer = group.get("layer") or {}
    layer_style = str(layer.get("style", ""))
    if isinstance(representative, Line2D):
        current = read_line_style(representative)
        result = {key: current[key] for key in _LINE_KEYS if key in current}
        alpha = representative.get_alpha()
        if alpha is not None:
            result["alpha"] = float(alpha)
        return result
    if isinstance(representative, Collection):
        fmt = _capture_collection_format(representative)
        result: dict[str, Any] = {}
        if fmt.get("mapped"):
            if fmt.get("cmap"):
                result["cmap"] = str(fmt["cmap"])
        elif fmt.get("color"):
            result["color" if layer_style == "scatter" else "facecolor"] = fmt["color"]
        if fmt.get("edgecolor"):
            result["edgecolors" if layer_style == "scatter" else "edgecolor"] = fmt["edgecolor"]
        if fmt.get("linewidth") is not None:
            result["linewidths" if layer_style == "scatter" else "linewidth"] = float(fmt["linewidth"])
        if fmt.get("marker_size") is not None and layer_style == "scatter":
            result["s"] = float(fmt["marker_size"])
        if fmt.get("alpha") is not None:
            result["alpha"] = float(fmt["alpha"])
        if fmt.get("zorder") is not None:
            result["zorder"] = float(fmt["zorder"])
        return result
    if isinstance(representative, Patch):
        fmt = _capture_patch_format(representative)
        result = {
            key: fmt[key] for key in ("edgecolor", "linewidth", "linestyle", "hatch")
            if fmt.get(key) is not None
        }
        if fmt.get("color"):
            result["facecolor"] = fmt["color"]
        for key in ("alpha", "zorder"):
            if fmt.get(key) is not None:
                result[key] = float(fmt[key])
        return result
    return {}


def _sync_layer_metadata(group: dict[str, Any]) -> None:
    layer = group.get("layer")
    if not isinstance(layer, dict):
        return
    values = _layer_kwargs(group)
    if not values:
        return
    style = str(layer.get("style", ""))
    alias_groups = {
        "color": {"c", "color", "facecolor", "facecolors", "fc"},
        "facecolor": {"c", "color", "facecolor", "facecolors", "fc"},
        "edgecolor": {"edgecolor", "edgecolors", "ec"},
        "edgecolors": {"edgecolor", "edgecolors", "ec"},
        "linewidth": {"linewidth", "linewidths", "lw"},
        "linewidths": {"linewidth", "linewidths", "lw"},
        "linestyle": {"linestyle", "linestyles", "ls"},
        "marker": {"marker"},
        "markersize": {"markersize", "ms"},
        "markerfacecolor": {"markerfacecolor", "mfc"},
        "markeredgecolor": {"markeredgecolor", "mec"},
        "markeredgewidth": {"markeredgewidth", "mew"},
        "s": {"s"},
        "alpha": {"alpha"},
        "cmap": {"cmap"},
        "hatch": {"hatch"},
        "fillstyle": {"fillstyle"},
        "drawstyle": {"drawstyle"},
        "zorder": {"zorder"},
    }
    aliases = set()
    for key in values:
        aliases.update(alias_groups.get(key, {key}))
    if style == "line":
        # A Line2D snapshot is complete for every safe base property.
        aliases.update({"c", "lw", "ls", "ms", "mfc", "mec", "mew"})
    kwargs = layer.setdefault("kwargs", {})
    for key in aliases:
        kwargs.pop(key, None)
    kwargs.update(values)
    meta = layer.setdefault("meta", {})
    style_kwargs = dict(meta.get("style_kwargs", {}))
    for key in aliases:
        style_kwargs.pop(key, None)
    style_kwargs.update(values)
    meta["style_kwargs"] = style_kwargs


def _capture_axis_content(ax: Any) -> dict[str, Any]:
    content = {
        "title": ax.get_title(),
        "xlabel": ax.get_xlabel(),
        "ylabel": ax.get_ylabel(),
        "xscale": ax.get_xscale(),
        "yscale": ax.get_yscale(),
        "xlim": tuple(ax.get_xlim()),
        "ylim": tuple(ax.get_ylim()),
        "autoscalex": bool(ax.get_autoscalex_on()),
        "autoscaley": bool(ax.get_autoscaley_on()),
    }
    if hasattr(ax, "get_zlim"):
        content.update({
            "zlabel": ax.get_zlabel(),
            "zscale": getattr(ax, "get_zscale", lambda: "linear")(),
            "zlim": tuple(ax.get_zlim()),
            "autoscalez": bool(getattr(ax, "get_autoscalez_on", lambda: False)()),
        })
    return content


def _restore_axis_content(ax: Any, content: dict[str, Any]) -> None:
    # Restore scales before ordered limits; the ordered tuples retain inversion.
    for name in ("x", "y"):
        try:
            getter = getattr(ax, f"get_{name}scale")
            if getter() != content[f"{name}scale"]:
                getattr(ax, f"set_{name}scale")(content[f"{name}scale"])
        except Exception:
            pass
    try:
        # ``Axes.set_title`` reapplies rcParams defaults and would undo the
        # transferred typography.  Updating Text content directly does not.
        ax.title.set_text(content["title"])
        ax.xaxis.label.set_text(content["xlabel"])
        ax.yaxis.label.set_text(content["ylabel"])
        ax.set_xlim(content["xlim"])
        ax.set_ylim(content["ylim"])
        ax.set_autoscalex_on(content["autoscalex"])
        ax.set_autoscaley_on(content["autoscaley"])
    except Exception:
        pass
    if "zlim" in content:
        try:
            if content.get("zscale"):
                getattr(ax, "set_zscale", lambda *_: None)(content["zscale"])
            ax.zaxis.label.set_text(content["zlabel"])
            ax.set_zlim(content["zlim"])
            getattr(ax, "set_autoscalez_on", lambda *_: None)(content["autoscalez"])
        except Exception:
            pass


def _capture_state(
    tab: Any, *, include_content: bool, exact_style: bool = False,
) -> dict[str, Any]:
    fig, axes = _format_axes(tab)
    axis_states = []
    series_count = 0
    for ax in axes:
        groups = _series_groups(tab, ax)
        series = [fmt for group in groups
                  if (fmt := _capture_series_format(
                      group, exact_style=exact_style,
                  )) is not None]
        series_count += len(series)
        legend = _capture_legend(ax)
        if not include_content:
            # Legend handles are live Artist objects.  Only the target's
            # handles/order are ever used during paste, so keeping source
            # handles would retain a closed source graph for no benefit.
            legend = {"format": legend.get("format", {})}
        state = {
            "appearance": _capture_axis_appearance(ax),
            "legend": legend,
            "series": series,
        }
        if include_content:
            state["content"] = _capture_axis_content(ax)
        axis_states.append(state)
    return {
        "version": FORMAT_CLIPBOARD_VERSION,
        "figure_facecolor": _hex(fig.get_facecolor()),
        "figure_text": {
            "suptitle": _capture_text(fig._suptitle)
            if getattr(fig, "_suptitle", None) is not None else None,
        },
        "axes": axis_states,
        "series_count": series_count,
        "print_figure_present": hasattr(tab, "_print_figure"),
        "print_figure": copy.deepcopy(getattr(tab, "_print_figure", None)),
    }


def capture_graph_format(tab: Any) -> dict[str, Any]:
    """Capture an accurate, transferable appearance snapshot for ``tab``."""
    return _capture_state(tab, include_content=False, exact_style=False)


def _capture_owned_axis_state(ax: Any) -> dict[str, Any]:
    owned: dict[str, Any] = {}
    for key, attr in (
        ("tick_labels", "_ps_tick_label_cfg"),
        ("reference_lines", "_ps_refline_cfg"),
        ("inset", "_ps_inset_cfg"),
        ("colorbar", "_ps_colorbar_cfg"),
    ):
        value = getattr(ax, attr, None)
        if value is not None:
            owned[key] = copy.deepcopy(value)
    owned["effects"] = _capture_axes_effect_state(ax)
    scale = dict(getattr(ax, "_ps_scale_cfg", None) or {})
    try:
        xmin, xmax = ax.get_xlim()
        ymin, ymax = ax.get_ylim()
        scale.update({
            "xscale": ax.get_xscale(),
            "yscale": ax.get_yscale(),
            "x_autoscale": bool(ax.get_autoscalex_on()),
            "y_autoscale": bool(ax.get_autoscaley_on()),
            "invert_x": bool(xmin > xmax),
            "invert_y": bool(ymin > ymax),
        })
    except Exception:
        pass
    if scale:
        owned["scale"] = scale
    colorbar_cfg = owned.get("colorbar")
    if isinstance(colorbar_cfg, dict):
        try:
            target = getattr(ax, "_ps_colorbar", None)
            if target is None:
                target = next(
                    (item.colorbar for item in _axes_mappables(ax)
                     if getattr(item, "colorbar", None) is not None),
                    None,
                )
            if target is not None:
                colorbar_cfg["label"] = str(target.ax.get_ylabel() or "")
        except Exception:
            pass
    if hasattr(ax, "elev") and hasattr(ax, "azim"):
        owned["view_3d"] = {
            "elev": _plain_float(getattr(ax, "elev", None)),
            "azim": _plain_float(getattr(ax, "azim", None)),
            "roll": _plain_float(getattr(ax, "roll", None)),
        }
    return owned


def capture_persisted_graph_format(tab: Any) -> dict[str, Any]:
    """Capture a strict-JSON graph appearance for a project file.

    Unlike the transferable clipboard, this also retains semantic generated
    decorations and legend ordering, and records an axes signature so a
    damaged or incompatible project cannot style the wrong subplot.
    """
    state = _capture_state(tab, include_content=False, exact_style=True)
    _fig, axes = _format_axes(tab)
    state["persistent_version"] = PERSISTED_FORMAT_VERSION
    for index, (ax, axis_state) in enumerate(zip(axes, state["axes"])):
        legend = _capture_legend(ax)
        content = legend.get("content", {})
        axis_state["legend"]["content"] = {
            "exists": bool(content.get("exists")),
            "labels": [str(label) for label in content.get("labels", ())],
            "title": str(content.get("title", "") or ""),
        }
        axis_state["descriptor"] = {
            "index": index,
            "projection": str(getattr(ax, "name", "rectilinear")),
        }
        axis_state["series_descriptors"] = _axis_series_descriptors(tab, ax)
        axis_state["owned"] = _capture_owned_axis_state(ax)
        axis_state["project_content"] = _capture_axis_content(ax)
        for series_style in axis_state.get("series", ()):
            candidates = [series_style, *series_style.get("members", ())]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                if candidate.get("kind") in {"collection", "image"}:
                    candidate["restore_mapping"] = True
                    candidate["restore_exact"] = True
    # Round-trip here, rather than at session save, so callers can rely on the
    # public API returning data that strict JSON accepts without repr/pickle.
    return json.loads(json.dumps(_json_value(state), ensure_ascii=False, allow_nan=False))


def is_persisted_graph_format(value: Any) -> bool:
    return (
        is_graph_format_snapshot(value)
        and value.get("persistent_version") == PERSISTED_FORMAT_VERSION
        and all(isinstance(item, dict)
                and isinstance(item.get("descriptor"), dict)
                and isinstance(item.get("series_descriptors"), list)
                for item in value.get("axes", ()))
    )


def is_graph_format_snapshot(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("version") == FORMAT_CLIPBOARD_VERSION
        and isinstance(value.get("axes"), list)
        and bool(value.get("axes"))
    )


def _apply_state(tab: Any, source: dict[str, Any], target_state: dict[str, Any], *,
                 restore_print_presence: bool = False) -> int:
    fig, target_axes = _format_axes(tab)
    source_axes = source.get("axes", [])
    target_axes_state = target_state.get("axes", [])
    if not source_axes:
        raise ValueError("The copied graph format is empty")
    if source.get("figure_facecolor"):
        fig.set_facecolor(source["figure_facecolor"])
    source_suptitle = source.get("figure_text", {}).get("suptitle")
    target_suptitle = getattr(fig, "_suptitle", None)
    if source_suptitle and target_suptitle is not None:
        _apply_text(target_suptitle, source_suptitle)

    applied_series = 0
    for index, ax in enumerate(target_axes):
        source_axis = source_axes[index % len(source_axes)]
        target_axis_state = target_axes_state[index]
        _apply_axis_appearance(ax, source_axis.get("appearance", {}))

        target_groups = _series_groups(tab, ax)
        source_series = source_axis.get("series", [])
        if source_series:
            colors = [item.get("color") for item in source_series if item.get("color")]
            if colors:
                try:
                    ax.set_prop_cycle(color=colors)
                except Exception:
                    pass
            for group_index, group in enumerate(target_groups):
                _apply_series_format(group, source_series[group_index % len(source_series)])
                _sync_layer_metadata(group)
                applied_series += 1

        # Rebuild only after the target artists have their new appearance, and
        # use the target legend's handles/order/title (never the source text).
        source_legend = source_axis.get("legend", {}).get("format", {})
        target_legend_content = target_axis_state.get("legend", {}).get("content", {})
        _apply_legend(ax, source_legend, target_legend_content)
        _restore_axis_content(ax, target_axis_state["content"])

    if source.get("print_figure_present"):
        tab._print_figure = copy.deepcopy(source.get("print_figure"))
    elif restore_print_presence:
        try:
            delattr(tab, "_print_figure")
        except AttributeError:
            pass
    return applied_series


def apply_graph_format(tab: Any, snapshot: dict[str, Any]) -> int:
    """Apply ``snapshot`` transactionally while preserving target content.

    If any adapter raises, the target's appearance and print settings are put
    back before the exception is re-raised.
    """
    if not is_graph_format_snapshot(snapshot):
        raise ValueError("The copied graph format is invalid or from a newer version")
    target_state = _capture_state(tab, include_content=True, exact_style=True)
    layer_state = []
    for info in (getattr(tab, "layers", {}) or {}).values():
        if not isinstance(info, dict):
            continue
        kwargs = dict(info.get("kwargs", {}))
        meta = dict(info.get("meta", {}))
        if isinstance(meta.get("style_kwargs"), dict):
            meta["style_kwargs"] = dict(meta["style_kwargs"])
        layer_state.append((info, kwargs, meta))
    try:
        return _apply_state(tab, snapshot, target_state)
    except Exception:
        try:
            _apply_state(
                tab,
                target_state,
                target_state,
                restore_print_presence=not target_state.get("print_figure_present"),
            )
        except Exception:
            pass
        # Rollback is exact for project-persistence metadata as well as the
        # live artists.  The rollback render pass intentionally recalculates
        # safe kwargs, so replace them with the original dictionaries here.
        for info, kwargs, meta in layer_state:
            info["kwargs"] = kwargs
            info["meta"] = meta
        raise


def _persisted_legend_content(ax: Any, content: dict[str, Any]) -> dict[str, Any]:
    """Resolve saved label occurrences to this graph's live handles."""
    handles, labels = ax.get_legend_handles_labels()
    available = [
        (handle, str(label)) for handle, label in zip(handles, labels)
        if label and not str(label).startswith("_")
    ]
    resolved_handles: list[Any] = []
    resolved_labels: list[str] = []
    for wanted in (str(value) for value in content.get("labels", ())):
        match = next((i for i, (_handle, label) in enumerate(available)
                      if label == wanted), None)
        if match is None:
            continue
        handle, label = available.pop(match)
        resolved_handles.append(handle)
        resolved_labels.append(label)
    return {
        "exists": bool(content.get("exists")),
        "handles": resolved_handles,
        "labels": resolved_labels,
        "title": str(content.get("title", "") or ""),
    }


def _apply_owned_axis_state(ax: Any, owned: dict[str, Any], fig: Any) -> None:
    style: dict[str, Any] = {}
    if "effects" in owned:
        # The encoded patch effects applied by _apply_axis_appearance are the
        # visual source of truth. Keep only the semantic controls for the next
        # Plot Details opening; re-applying stale metadata could resurrect an
        # effect that Paste Format just removed.
        ax._ps_axes_effects = dict(owned.get("effects") or {})
    if "tick_labels" in owned:
        style["tick_labels"] = dict(owned.get("tick_labels") or {})
    axes_style = {}
    if "scale" in owned:
        scale = dict(owned.get("scale") or {})
        # Exact scales, ordered limits and autoscale flags already came from
        # project_content. Apply only semantic locator/formatter controls.
        for key in (
            "xscale", "yscale", "x_autoscale", "y_autoscale",
            "invert_x", "invert_y",
        ):
            scale.pop(key, None)
        axes_style.update(scale)
    if "reference_lines" in owned:
        axes_style.update(dict(owned.get("reference_lines") or {}))
    if axes_style:
        style["axes"] = axes_style
    if "inset" in owned:
        style["inset"] = {**INSET_DEFAULTS, **dict(owned.get("inset") or {})}
    if "colorbar" in owned:
        style["colorbar"] = {**COLORBAR_DEFAULTS, **dict(owned.get("colorbar") or {})}
    if style:
        apply_style(ax, style, fig=fig, live=True)
    if "scale" in owned:
        scale_state = dict(owned.get("scale") or {})
        try:
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            scale_state.update({
                "xscale": ax.get_xscale(),
                "yscale": ax.get_yscale(),
                "x_autoscale": bool(ax.get_autoscalex_on()),
                "y_autoscale": bool(ax.get_autoscaley_on()),
                "invert_x": bool(xmin > xmax),
                "invert_y": bool(ymin > ymax),
            })
        except Exception:
            pass
        ax._ps_scale_cfg = scale_state
    view = owned.get("view_3d")
    if isinstance(view, dict) and hasattr(ax, "view_init"):
        kwargs = {
            key: view[key] for key in ("elev", "azim", "roll")
            if view.get(key) is not None
        }
        try:
            ax.view_init(**kwargs)
        except TypeError:  # Matplotlib versions before ``roll`` support
            kwargs.pop("roll", None)
            ax.view_init(**kwargs)


def apply_persisted_graph_format(tab: Any, snapshot: dict[str, Any]) -> int:
    """Restore a project appearance using strict axes/projection matching."""
    if not is_persisted_graph_format(snapshot):
        raise ValueError("The saved graph appearance is invalid or unsupported")
    fig, axes = _format_axes(tab)
    source_axes = snapshot.get("axes", [])
    if len(source_axes) != len(axes):
        raise ValueError(
            f"Saved graph has {len(source_axes)} axes but restored graph has {len(axes)}"
        )
    for index, (ax, axis_state) in enumerate(zip(axes, source_axes)):
        descriptor = axis_state.get("descriptor", {})
        expected = str(descriptor.get("projection", "rectilinear"))
        actual = str(getattr(ax, "name", "rectilinear"))
        if descriptor.get("index") != index or expected != actual:
            raise ValueError(
                f"Saved axes signature does not match at index {index}: "
                f"expected {expected}, got {actual}"
            )
        saved_series = axis_state.get("series_descriptors")
        current_series = _axis_series_descriptors(tab, ax)
        if saved_series != current_series:
            raise ValueError(
                f"Saved series topology does not match at axes {index}; "
                "appearance was skipped to avoid styling the wrong data"
            )

    target_state = _capture_state(tab, include_content=True, exact_style=False)
    for ax, source_axis, target_axis in zip(axes, source_axes, target_state["axes"]):
        saved_content = source_axis.get("legend", {}).get("content", {})
        target_axis["legend"]["content"] = _persisted_legend_content(ax, saved_content)
        saved_axis_content = source_axis.get("project_content")
        if isinstance(saved_axis_content, dict):
            target_axis["content"] = copy.deepcopy(saved_axis_content)
    applied = _apply_state(tab, snapshot, target_state)
    for ax, axis_state in zip(axes, source_axes):
        _apply_owned_axis_state(ax, axis_state.get("owned", {}), fig)
    return applied
