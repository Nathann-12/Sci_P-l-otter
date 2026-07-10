"""Origin-style plots for worksheets containing multiple Y columns."""
from __future__ import annotations

import numpy as np
import pandas as pd

from plots._common import color_cycle, numeric_columns, placeholder


def _xy_series(df: pd.DataFrame):
    columns = numeric_columns(df)
    if not columns:
        return None
    if len(columns) == 1:
        x_name = "Row"
        x_values = np.arange(len(df), dtype=float)
        y_columns = columns
    else:
        x_name = str(columns[0])
        x_values = pd.to_numeric(df[columns[0]], errors="coerce").to_numpy(dtype=float)
        y_columns = columns[1:]

    series = []
    for column in y_columns:
        y_values = pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)
        length = min(x_values.size, y_values.size)
        x = x_values[:length]
        y = y_values[:length]
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.any():
            series.append((str(column), x[mask], y[mask]))
    return x_name, series


def _offset_step(series) -> float:
    spans = [
        float(np.ptp(values))
        for _, _, values in series
        if values.size and np.ptp(values) > 0
    ]
    return (float(np.median(spans)) if spans else 1.0) * 1.2


def stacked_lines_y_offset(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _xy_series(df)
    if prepared is None or not prepared[1]:
        placeholder(ax, "Stacked lines need at least one numeric Y column.")
        return
    x_name, series = prepared
    offset = _offset_step(series)
    colors = color_cycle(len(series))
    for index, (name, x, y) in enumerate(series):
        shifted = y + index * offset
        ax.plot(x, shifted, color=colors[index], linewidth=1.5, label=name)
    ax.set_xlabel(x_name)
    ax.set_ylabel("Y + offset")
    ax.set_title("Stacked Lines by Y Offset")
    ax.legend(loc="best", fontsize=8)


def waterfall_3d(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _xy_series(df)
    if prepared is None or not prepared[1]:
        placeholder(ax, "Waterfall needs at least one numeric Y column.")
        return
    if not hasattr(ax, "zaxis"):
        placeholder(ax, "Waterfall requires a 3D graph.")
        return
    x_name, series = prepared
    colors = color_cycle(len(series))
    for index, (name, x, values) in enumerate(series):
        plane = np.full(values.size, index, dtype=float)
        ax.plot(x, plane, values, color=colors[index], linewidth=1.4, label=name)
    ax.set_xlabel(x_name)
    ax.set_ylabel("Series")
    ax.set_zlabel("Value")
    ax.set_yticks(range(len(series)))
    ax.set_yticklabels([name for name, _, _ in series])
    ax.set_title("3D Waterfall")


def subplot_grid(ax, df: pd.DataFrame, **opts) -> None:
    prepared = _xy_series(df)
    if prepared is None or not prepared[1]:
        placeholder(ax, "Subplot grid needs at least one numeric Y column.")
        return
    x_name, series = prepared
    figure = ax.figure
    figure.clf()
    count = len(series)
    columns = min(3, max(1, int(np.ceil(np.sqrt(count)))))
    rows = int(np.ceil(count / columns))
    axes = np.atleast_1d(figure.subplots(rows, columns)).ravel()
    colors = color_cycle(count)
    for index, (name, x, values) in enumerate(series):
        subplot = axes[index]
        subplot.plot(x, values, color=colors[index], linewidth=1.2)
        subplot.set_title(name, fontsize=9)
        subplot.set_xlabel(x_name, fontsize=8)
        subplot.tick_params(labelsize=7)
        subplot.grid(True, alpha=0.2)
    for unused in axes[count:]:
        unused.set_visible(False)
    figure.suptitle("Subplot Grid")
    try:
        figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    except Exception:
        pass


PLOTS = [
    {
        "key": "stacked_lines_y_offset",
        "title": "Stacked Lines by Y Offset",
        "category": "Multi-Column",
        "func": stacked_lines_y_offset,
        "desc": "Stack multiple Y columns with automatic vertical offsets",
        "min_cols": 1,
        "multi": False,
    },
    {
        "key": "waterfall_3d",
        "title": "3D Waterfall",
        "category": "Multi-Column",
        "func": waterfall_3d,
        "desc": "Plot multiple Y columns as lines on successive 3D planes",
        "min_cols": 1,
        "multi": False,
        "is3d": True,
    },
    {
        "key": "subplot_grid",
        "title": "Subplot Grid",
        "category": "Multi-Panel",
        "func": subplot_grid,
        "desc": "Arrange each Y column in its own subplot",
        "min_cols": 1,
        "multi": True,
    },
]
