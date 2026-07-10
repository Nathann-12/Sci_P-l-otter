"""Contour and heatmap plots for worksheet XYZ and matrix-like data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from plots._common import numeric_columns, placeholder


def _xyz_data(df: pd.DataFrame):
    columns = numeric_columns(df)
    if len(columns) < 3:
        return None
    frame = df[columns[:3]].apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return None
    x, y, z = (frame[column].to_numpy(dtype=float) for column in columns[:3])
    if np.unique(x).size < 2 or np.unique(y).size < 2:
        return None
    return columns[:3], x, y, z


def _draw_xyz_contour(ax, df: pd.DataFrame, *, filled: bool) -> None:
    ax.clear()
    prepared = _xyz_data(df)
    if prepared is None:
        placeholder(ax, "Contour needs 3 varying numeric XYZ columns.")
        return
    columns, x, y, z = prepared
    try:
        if filled:
            artist = ax.tricontourf(x, y, z, levels=16, cmap="viridis")
            ax.figure.colorbar(artist, ax=ax, fraction=0.046, pad=0.04, label=str(columns[2]))
            ax.set_title("Filled Contour")
        else:
            artist = ax.tricontour(x, y, z, levels=12, cmap="viridis")
            ax.clabel(artist, inline=True, fontsize=7)
            ax.set_title("Contour Lines")
    except (RuntimeError, ValueError):
        placeholder(ax, "XYZ points cannot form a contour surface.")
        return
    ax.set_xlabel(str(columns[0]))
    ax.set_ylabel(str(columns[1]))


def filled_contour(ax, df: pd.DataFrame, **opts) -> None:
    _draw_xyz_contour(ax, df, filled=True)


def contour_lines(ax, df: pd.DataFrame, **opts) -> None:
    _draw_xyz_contour(ax, df, filled=False)


def heatmap(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    columns = numeric_columns(df)
    if not columns:
        placeholder(ax, "Heatmap needs at least one numeric column.")
        return
    matrix = (
        df[columns]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .to_numpy(dtype=float)
        .T
    )
    if matrix.size == 0 or not np.isfinite(matrix).any():
        placeholder(ax, "Heatmap has no finite numeric values.")
        return
    masked = np.ma.masked_invalid(matrix)
    image = ax.imshow(masked, aspect="auto", origin="lower", cmap="viridis")
    ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="Value")
    ax.set_yticks(range(len(columns)))
    ax.set_yticklabels([str(column) for column in columns])
    ax.set_xlabel("Observation")
    ax.set_ylabel("Column")
    ax.set_title("Heatmap")


PLOTS = [
    {
        "key": "filled_contour",
        "title": "Filled Contour",
        "category": "Contour, Heatmap",
        "func": filled_contour,
        "desc": "Color-filled contour from the first three numeric XYZ columns",
        "min_cols": 3,
        "multi": False,
    },
    {
        "key": "contour_lines",
        "title": "Contour Lines",
        "category": "Contour, Heatmap",
        "func": contour_lines,
        "desc": "Labeled contour lines from the first three numeric XYZ columns",
        "min_cols": 3,
        "multi": False,
    },
    {
        "key": "matrix_heatmap",
        "title": "Heatmap",
        "category": "Contour, Heatmap",
        "func": heatmap,
        "desc": "Heatmap of all numeric worksheet columns",
        "min_cols": 1,
        "multi": False,
    },
]
