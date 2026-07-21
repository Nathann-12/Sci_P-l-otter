"""Color-mapped line plots — a curve whose colour varies along its length.

Origin's "color mapped" line: the line is coloured by a value (a third data
column, or the Y value / row index when there isn't one), with a colourbar
legend. Implemented with a matplotlib ``LineCollection`` so each segment gets
its own colour from the chosen colormap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection

from plots._common import numeric_columns, placeholder


def _xyc(df: pd.DataFrame):
    """Resolve (x, y, c, labels) from the worksheet's numeric columns.

    - 1 numeric column  -> Y = that column vs Row, colour by Y
    - 2 numeric columns -> X, Y, colour by Y
    - 3+ numeric columns -> X, Y, colour by the 3rd column
    """
    cols = numeric_columns(df)
    if not cols:
        return None
    to_num = lambda name: pd.to_numeric(df[name], errors="coerce").to_numpy(dtype=float)

    if len(cols) == 1:
        y = to_num(cols[0])
        x = np.arange(y.size, dtype=float)
        c = y
        xlabel, ylabel, clabel = "Row", str(cols[0]), str(cols[0])
    elif len(cols) == 2:
        x, y = to_num(cols[0]), to_num(cols[1])
        c = y
        xlabel, ylabel, clabel = str(cols[0]), str(cols[1]), str(cols[1])
    else:
        x, y, c = to_num(cols[0]), to_num(cols[1]), to_num(cols[2])
        xlabel, ylabel, clabel = str(cols[0]), str(cols[1]), str(cols[2])

    n = min(x.size, y.size, c.size)
    x, y, c = x[:n], y[:n], c[:n]
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(c)
    x, y, c = x[mask], y[mask], c[mask]
    if x.size < 2:
        return None
    return x, y, c, (xlabel, ylabel, clabel)


def _draw_color_mapped(ax, df, *, marker: bool, opts: dict) -> None:
    ax.clear()
    prepared = _xyc(df)
    if prepared is None:
        placeholder(ax, "Color-mapped line needs at least 2 finite points.")
        return
    x, y, c, (xlabel, ylabel, clabel) = prepared
    cmap = str(opts.get("cmap", "viridis"))
    lw = float(opts.get("linewidth", 2.0))

    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    lc = LineCollection(segments, cmap=cmap, linewidth=lw)
    # colour each segment by the mean of its two endpoints' values
    lc.set_array((c[:-1] + c[1:]) / 2.0)
    lc.set_clim(float(np.min(c)), float(np.max(c)))
    ax.add_collection(lc)

    if marker:
        ax.scatter(x, y, c=c, cmap=cmap, s=18, zorder=3, edgecolors="none")

    pad_x = (np.ptp(x) or 1.0) * 0.03
    pad_y = (np.ptp(y) or 1.0) * 0.05
    ax.set_xlim(x.min() - pad_x, x.max() + pad_x)
    ax.set_ylim(y.min() - pad_y, y.max() + pad_y)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title("Color-Mapped Line")
    try:
        ax.figure.colorbar(lc, ax=ax, fraction=0.046, pad=0.04, label=clabel)
    except Exception:
        pass


def color_mapped_line(ax, df: pd.DataFrame, **opts) -> None:
    _draw_color_mapped(ax, df, marker=False, opts=opts)


def color_mapped_line_markers(ax, df: pd.DataFrame, **opts) -> None:
    _draw_color_mapped(ax, df, marker=True, opts=opts)


PLOTS = [
    {
        "key": "color_mapped_line",
        "title": "Color-Mapped Line",
        "category": "Multi-Column",
        "func": color_mapped_line,
        "desc": "Line coloured by a Z column (or Y / row) with a colourbar",
        "min_cols": 1,
        "multi": False,
    },
    {
        "key": "color_mapped_line_markers",
        "title": "Color-Mapped Line + Markers",
        "category": "Multi-Column",
        "func": color_mapped_line_markers,
        "desc": "Color-mapped line with each data point marked",
        "min_cols": 1,
        "multi": False,
    },
]
