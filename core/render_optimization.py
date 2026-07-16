"""Render-level optimisation for large scientific plots.

The analytical DataFrame is never changed here.  Artists retain their complete
source arrays while their visible representation is adapted to the current
pixel budget.  This keeps statistics, project files and data export exact.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
from matplotlib.collections import PolyCollection

from core.plot_data import sanitize_plot_xy, to_sequence_for_plot


FAST_BAR_THRESHOLD = 256
LINE_LOD_THRESHOLD = 5_000
SCATTER_RASTER_THRESHOLD = 10_000
SCATTER_DENSITY_THRESHOLD = 100_000
MAX_CATEGORICAL_TICKS = 20
DEFAULT_PIXEL_WIDTH = 800


def canvas_pixel_width(ax, fallback: int = DEFAULT_PIXEL_WIDTH) -> int:
    """Return the usable axes width in physical pixels."""
    try:
        width = int(round(float(ax.bbox.width)))
        if width > 1:
            return width
    except Exception:
        pass
    try:
        width, _height = ax.figure.canvas.get_width_height()
        if int(width) > 1:
            return int(width)
    except Exception:
        pass
    return max(2, int(fallback))


def render_info_for(
    style: str,
    x: Any,
    y: Any,
    *,
    pixel_width: int = DEFAULT_PIXEL_WIDTH,
    bar_reducer: str = "none",
    scatter_mode: str = "auto",
) -> dict[str, Any]:
    """Describe the rendering plan without changing source data."""
    x_source = to_sequence_for_plot(x)
    y_source = to_sequence_for_plot(y)
    source_count = min(len(x_source), len(y_source))
    valid_x, valid_y = sanitize_plot_xy(x_source, y_source)
    rendered_count = min(len(valid_x), len(valid_y))
    normalized = str(style or "").casefold()
    pixel_width = max(2, int(pixel_width))
    lod_applied = False
    if normalized == "bar":
        reducer = normalize_bar_reducer(bar_reducer)
        if reducer != "none" and rendered_count > pixel_width:
            mode = f"pixel-{reducer}"
            artist_count = 1
            lod_applied = True
        else:
            mode = "polycollection" if rendered_count >= FAST_BAR_THRESHOLD else "patches"
            artist_count = 1 if mode == "polycollection" and rendered_count else rendered_count
    elif normalized == "scatter":
        resolved_mode = normalize_scatter_mode(scatter_mode)
        density = resolved_mode == "density" or (
            resolved_mode == "auto" and rendered_count >= SCATTER_DENSITY_THRESHOLD
        )
        if density:
            mode = "density"
            lod_applied = True
        else:
            mode = "rasterized" if rendered_count >= SCATTER_RASTER_THRESHOLD else "vector"
        artist_count = 1 if rendered_count else 0
    elif normalized == "line":
        mode = "minmax" if rendered_count > max(LINE_LOD_THRESHOLD, pixel_width * 2) else "vector"
        artist_count = 1 if rendered_count else 0
        lod_applied = mode == "minmax"
    else:
        mode = "vector"
        artist_count = 1 if rendered_count else 0
    return {
        "source_count": source_count,
        "rendered_count": rendered_count,
        "render_mode": mode,
        "artist_count": artist_count,
        "lod_applied": lod_applied,
    }


def normalize_bar_reducer(value: Any) -> str:
    value = str(value or "none").casefold()
    if value not in {"none", "sum", "mean"}:
        raise ValueError("bar reducer must be one of: none, sum, mean")
    return value


def normalize_scatter_mode(value: Any) -> str:
    value = str(value or "auto").casefold()
    if value not in {"auto", "points", "density"}:
        raise ValueError("scatter mode must be one of: auto, points, density")
    return value


def scatter_kwargs_for_count(point_count: int, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return scatter kwargs with automatic rasterization for large series."""
    resolved = dict(kwargs)
    if int(point_count) >= SCATTER_RASTER_THRESHOLD:
        resolved.setdefault("rasterized", True)
    return resolved


def categorical_tick_indexes(count: int, limit: int = MAX_CATEGORICAL_TICKS) -> list[int]:
    """Return evenly spaced tick positions, always retaining both endpoints."""
    count = max(0, int(count))
    limit = max(2, int(limit))
    if count <= limit:
        return list(range(count))
    return np.unique(np.linspace(0, count - 1, limit, dtype=int)).tolist()


def set_categorical_bar_ticks(ax, labels: Iterable[Any]) -> int:
    """Set a readable, bounded number of category ticks and return its count."""
    label_list = list(labels)
    indexes = categorical_tick_indexes(len(label_list))
    ax.set_xticks(indexes)
    ax.set_xticklabels(
        [str(label_list[index]) for index in indexes],
        rotation=45,
        ha="right",
    )
    return len(indexes)


def _ordered_minmax_indexes(y: np.ndarray, bucket_ids: np.ndarray) -> np.ndarray:
    """Return min/max source indexes per bucket in original sample order."""
    if y.size == 0:
        return np.asarray([], dtype=int)
    chosen: list[int] = []
    starts = np.r_[0, np.flatnonzero(np.diff(bucket_ids)) + 1]
    ends = np.r_[starts[1:], y.size]
    for start, end in zip(starts, ends):
        segment = y[start:end]
        finite = np.flatnonzero(np.isfinite(segment))
        if finite.size == 0:
            continue
        finite_values = segment[finite]
        lo = start + int(finite[int(np.argmin(finite_values))])
        hi = start + int(finite[int(np.argmax(finite_values))])
        if lo == hi:
            chosen.append(lo)
        elif lo < hi:
            chosen.extend((lo, hi))
        else:
            chosen.extend((hi, lo))
    if not chosen:
        return np.asarray([], dtype=int)
    return np.unique(np.asarray(chosen, dtype=int))


def minmax_decimate(
    x_values: Iterable[Any],
    y_values: Iterable[Any],
    *,
    pixel_width: int,
    pixel_positions: Iterable[float] | None = None,
) -> tuple[list[Any], list[float], np.ndarray]:
    """Min/max envelope decimation, preserving spikes and source order."""
    x = list(x_values)
    y = np.asarray(list(y_values), dtype=float)
    count = min(len(x), int(y.size))
    x = x[:count]
    y = y[:count]
    if count == 0:
        return [], [], np.asarray([], dtype=int)
    budget = max(2, int(pixel_width))
    if count <= max(LINE_LOD_THRESHOLD, budget * 2):
        indexes = np.arange(count, dtype=int)
        return x, y.tolist(), indexes
    if pixel_positions is None:
        pixels = np.linspace(0.0, float(budget - 1), count)
    else:
        pixels = np.asarray(list(pixel_positions), dtype=float)[:count]
    finite_pixels = np.isfinite(pixels)
    visible = np.flatnonzero(finite_pixels & (pixels >= -1.0) & (pixels <= budget + 1.0))
    if visible.size == 0:
        return [], [], np.asarray([], dtype=int)
    visible_pixels = pixels[visible]
    order = np.argsort(visible_pixels, kind="stable")
    sorted_source = visible[order]
    bucket_ids = np.floor(visible_pixels[order]).astype(np.int64)
    local = _ordered_minmax_indexes(y[sorted_source], bucket_ids)
    selected = np.sort(sorted_source[local]) if local.size else np.asarray([], dtype=int)
    # Exact viewport endpoints make pan/zoom boundaries visually continuous.
    selected = np.unique(np.r_[visible[0], selected, visible[-1]]).astype(int)
    return [x[i] for i in selected], y[selected].tolist(), selected


def _numeric_x_values(ax, artist, x_values: list[Any]) -> np.ndarray:
    cached = getattr(artist, "_sciplotter_x_numeric", None)
    if cached is not None and len(cached) == len(x_values):
        return np.asarray(cached, dtype=float)
    try:
        numeric = np.asarray(ax.convert_xunits(x_values), dtype=float)
    except Exception:
        try:
            numeric = np.asarray(x_values, dtype=float)
        except Exception:
            numeric = np.arange(len(x_values), dtype=float)
    artist._sciplotter_x_numeric = numeric
    return numeric


def _numeric_x_to_pixels(ax, numeric: np.ndarray) -> np.ndarray:
    try:
        points = np.column_stack((numeric, np.zeros(numeric.size, dtype=float)))
        return np.asarray(ax.get_xaxis_transform().transform(points)[:, 0], dtype=float)
    except Exception:
        return np.asarray(numeric, dtype=float)


def apply_line_lod(ax, artist, *, pixel_width: int | None = None) -> dict[str, Any]:
    """Re-render one Line2D from its retained full arrays for this viewport."""
    full_x = list(getattr(artist, "_sciplotter_x_values", artist.get_xdata()))
    full_y = list(getattr(artist, "_sciplotter_y_values", artist.get_ydata()))
    count = min(len(full_x), len(full_y))
    full_x, full_y = full_x[:count], full_y[:count]
    artist._sciplotter_x_values = full_x
    artist._sciplotter_y_values = full_y
    width = max(2, int(pixel_width or canvas_pixel_width(ax)))
    numeric_x = _numeric_x_values(ax, artist, full_x)
    try:
        lo, hi = sorted(map(float, ax.get_xlim()))
        visible = np.flatnonzero(
            np.isfinite(numeric_x) & (numeric_x >= lo) & (numeric_x <= hi)
        )
    except Exception:
        visible = np.arange(count, dtype=int)
    if visible.size:
        # Keep one neighbour on each side so clipped lines meet the viewport.
        first = max(0, int(visible[0]) - 1)
        last = min(count, int(visible[-1]) + 2)
        candidates = np.arange(first, last, dtype=int)
    else:
        candidates = np.arange(count, dtype=int)
    candidate_x = [full_x[i] for i in candidates]
    candidate_y = [full_y[i] for i in candidates]
    pixels = _numeric_x_to_pixels(ax, numeric_x[candidates])
    left = float(ax.bbox.x0)
    display_pixels = pixels - left
    x_render, y_render, _indexes = minmax_decimate(
        candidate_x,
        candidate_y,
        pixel_width=width,
        pixel_positions=display_pixels,
    )
    artist.set_data(x_render, y_render)
    mode = "minmax" if len(x_render) < count else "vector"
    return {
        "source_count": count,
        "rendered_count": len(x_render),
        "visible_count": int(candidates.size),
        "render_mode": mode,
        "artist_count": 1 if count else 0,
        "lod_applied": mode == "minmax",
        "pixel_width": width,
    }


def _bar_vertices(
    centers: np.ndarray,
    values: np.ndarray,
    widths: np.ndarray,
    bottoms: np.ndarray,
) -> np.ndarray:
    left = centers - widths / 2.0
    right = centers + widths / 2.0
    top = bottoms + values
    vertices = np.empty((values.size, 4, 2), dtype=float)
    vertices[:, 0, :] = np.column_stack((left, bottoms))
    vertices[:, 1, :] = np.column_stack((left, top))
    vertices[:, 2, :] = np.column_stack((right, top))
    vertices[:, 3, :] = np.column_stack((right, bottoms))
    return vertices


def aggregate_bars_for_pixels(
    y_values: Iterable[float],
    *,
    pixel_width: int,
    reducer: str,
    visible_indexes: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Aggregate contiguous categorical bars into explicit screen buckets."""
    reducer = normalize_bar_reducer(reducer)
    y = np.asarray(list(y_values), dtype=float)
    indexes = (
        np.arange(y.size, dtype=int)
        if visible_indexes is None
        else np.asarray(visible_indexes, dtype=int)
    )
    indexes = indexes[(indexes >= 0) & (indexes < y.size)]
    if indexes.size == 0:
        empty = np.asarray([], dtype=float)
        return empty, empty, empty, np.asarray([], dtype=int)
    budget = max(2, int(pixel_width))
    if reducer == "none" or indexes.size <= budget:
        return indexes.astype(float), y[indexes], np.full(indexes.size, 0.8), indexes
    group = np.floor(np.arange(indexes.size) * budget / indexes.size).astype(int)
    starts = np.r_[0, np.flatnonzero(np.diff(group)) + 1]
    ends = np.r_[starts[1:], indexes.size]
    centers, values, widths, representatives = [], [], [], []
    for start, end in zip(starts, ends):
        source = indexes[start:end]
        segment = y[source]
        finite = segment[np.isfinite(segment)]
        value = float(np.sum(finite) if reducer == "sum" else np.mean(finite)) if finite.size else np.nan
        centers.append(float(np.mean(source)))
        values.append(value)
        widths.append(float(source[-1] - source[0] + 0.8))
        representatives.append(int(source[0]))
    return (
        np.asarray(centers, dtype=float),
        np.asarray(values, dtype=float),
        np.asarray(widths, dtype=float),
        np.asarray(representatives, dtype=int),
    )


def apply_bar_lod(ax, artist, *, pixel_width: int | None = None) -> dict[str, Any]:
    """Update an existing bar PolyCollection without replacing its reference."""
    labels = list(getattr(artist, "_sciplotter_x_values", []))
    values = list(getattr(artist, "_sciplotter_y_values", []))
    count = min(len(labels), len(values))
    reducer = normalize_bar_reducer(getattr(artist, "_sciplotter_bar_reducer", "none"))
    width = max(2, int(pixel_width or canvas_pixel_width(ax)))
    try:
        lo, hi = sorted(map(float, ax.get_xlim()))
        first = max(0, int(np.floor(lo)) - 1)
        last = min(count, int(np.ceil(hi)) + 2)
        visible = np.arange(first, last, dtype=int)
    except Exception:
        visible = np.arange(count, dtype=int)
    centers, aggregated, widths, _representatives = aggregate_bars_for_pixels(
        values,
        pixel_width=width,
        reducer=reducer,
        visible_indexes=visible,
    )
    widths = widths * (float(getattr(artist, "_sciplotter_bar_width", 0.8)) / 0.8)
    bottoms = np.zeros(aggregated.size, dtype=float)
    artist.set_verts(_bar_vertices(centers, aggregated, widths, bottoms), closed=True)
    applied = reducer != "none" and aggregated.size < visible.size
    return {
        "source_count": count,
        "visible_count": int(visible.size),
        "rendered_count": int(aggregated.size),
        "render_mode": f"pixel-{reducer}" if applied else "polycollection",
        "artist_count": 1 if count else 0,
        "bar_reducer": reducer,
        "lod_applied": applied,
        "pixel_width": width,
    }


def draw_bar_series(
    ax,
    x_values: Iterable[Any],
    y_values: Iterable[Any],
    *,
    label: str = "",
    bar_reducer: str = "none",
    pixel_width: int | None = None,
    **kwargs,
) -> tuple[list[Any], dict[str, Any]]:
    """Draw categorical bars with one collection and optional pixel reducer."""
    x_vals = list(x_values)
    y_vals = np.asarray(list(y_values), dtype=float)
    count = min(len(x_vals), int(y_vals.size))
    x_vals = x_vals[:count]
    y_vals = y_vals[:count]
    positions = np.arange(count, dtype=float)
    local_kwargs = dict(kwargs)
    base_width = float(local_kwargs.pop("width", 0.8))
    reducer = normalize_bar_reducer(bar_reducer)
    px_width = max(2, int(pixel_width or canvas_pixel_width(ax)))
    should_collect = count >= FAST_BAR_THRESHOLD or (reducer != "none" and count > px_width)

    if not should_collect:
        container = ax.bar(positions, y_vals, width=base_width, label=label, **local_kwargs)
        artists = list(container)
        mode = "patches"
        rendered_count = count
        if artists:
            artists[0]._sciplotter_x_values = list(x_vals)
            artists[0]._sciplotter_y_values = y_vals.tolist()
    else:
        align = str(local_kwargs.pop("align", "center"))
        bottom = local_kwargs.pop("bottom", 0.0)
        bottoms_source = np.asarray(bottom, dtype=float)
        if bottoms_source.ndim == 0:
            bottoms_source = np.full(count, float(bottoms_source))
        else:
            bottoms_source = np.resize(bottoms_source, count)
        centers, rendered_y, widths, representatives = aggregate_bars_for_pixels(
            y_vals,
            pixel_width=px_width,
            reducer=reducer,
        )
        widths = widths * (base_width / 0.8)
        if align == "edge":
            centers = centers + widths / 2.0
        rendered_bottoms = bottoms_source[representatives] if representatives.size else np.asarray([])
        if not any(key in local_kwargs for key in ("color", "facecolor", "facecolors")):
            try:
                local_kwargs["facecolor"] = ax._get_patches_for_fill.get_next_color()
            except Exception:
                pass
        collection = PolyCollection(
            _bar_vertices(centers, rendered_y, widths, rendered_bottoms),
            closed=True,
            label=label,
            **local_kwargs,
        )
        collection._sciplotter_x_values = list(x_vals)
        collection._sciplotter_y_values = y_vals.tolist()
        collection._sciplotter_bar_reducer = reducer
        collection._sciplotter_bar_width = base_width
        ax.add_collection(collection, autolim=True)
        artists = [collection]
        rendered_count = int(rendered_y.size)
        mode = f"pixel-{reducer}" if rendered_count < count else "polycollection"

    tick_count = set_categorical_bar_ticks(ax, x_vals)
    info = {
        "source_count": count,
        "rendered_count": rendered_count,
        "render_mode": mode,
        "artist_count": len(artists),
        "tick_count": tick_count,
        "bar_reducer": reducer,
        "lod_applied": rendered_count < count,
        "pixel_width": px_width,
    }
    return artists, info


def draw_scatter_series(
    ax,
    x_values: Iterable[Any],
    y_values: Iterable[Any],
    *,
    label: str = "",
    scatter_mode: str = "auto",
    pixel_width: int | None = None,
    **kwargs,
) -> tuple[list[Any], dict[str, Any]]:
    """Draw points or an explicit hex-density representation for huge data."""
    x_vals = list(x_values)
    y_vals = list(y_values)
    count = min(len(x_vals), len(y_vals))
    x_vals, y_vals = x_vals[:count], y_vals[:count]
    resolved = normalize_scatter_mode(scatter_mode)
    density = resolved == "density" or (resolved == "auto" and count >= SCATTER_DENSITY_THRESHOLD)
    local_kwargs = dict(kwargs)
    if density:
        gridsize = max(40, min(250, int((pixel_width or canvas_pixel_width(ax)) / 4)))
        alpha = local_kwargs.pop("alpha", None)
        color = local_kwargs.pop("color", local_kwargs.pop("c", None))
        cmap = local_kwargs.pop("cmap", "viridis")
        for key in ("s", "marker", "rasterized", "facecolor", "edgecolor"):
            local_kwargs.pop(key, None)
        if color is not None:
            local_kwargs.setdefault("color", color)
            cmap = None
        artist = ax.hexbin(
            x_vals,
            y_vals,
            gridsize=gridsize,
            mincnt=1,
            bins="log",
            cmap=cmap,
            alpha=alpha,
            linewidths=0,
            label=label,
            **local_kwargs,
        )
        mode = "density"
        bin_count = int(np.asarray(artist.get_array()).size)
        lod_applied = True
    else:
        local_kwargs = scatter_kwargs_for_count(count, local_kwargs)
        artist = ax.scatter(x_vals, y_vals, label=label, **local_kwargs)
        mode = "rasterized" if bool(local_kwargs.get("rasterized")) else "vector"
        bin_count = None
        lod_applied = False
    artist._sciplotter_x_values = list(x_vals)
    artist._sciplotter_y_values = list(y_vals)
    artist._sciplotter_scatter_mode = resolved
    info = {
        "source_count": count,
        "rendered_count": count,
        "render_mode": mode,
        "artist_count": 1 if count else 0,
        "lod_applied": lod_applied,
    }
    if bin_count is not None:
        info["bin_count"] = bin_count
    return [artist], info


def render_status(kind: str, info: dict[str, Any]) -> str:
    """Create concise, auditable status-bar feedback for a rendered series."""
    source = int(info.get("source_count", 0))
    rendered = int(info.get("rendered_count", 0))
    mode = str(info.get("render_mode", "vector"))
    unit = "bars" if str(kind).casefold() == "bar" else "points"
    suffix = {
        "polycollection": "optimized collection",
        "rasterized": "rasterized",
        "patches": "standard bars",
        "vector": "vector",
        "minmax": "min-max LOD",
        "density": f"density ({int(info.get('bin_count', 0)):,} bins)",
        "pixel-sum": "pixel buckets (sum)",
        "pixel-mean": "pixel buckets (mean)",
    }.get(mode, mode)
    return f"Rendered {rendered:,} of {source:,} {unit} • {suffix}."
