"""Additional high-value 2D plots for the chart registry."""
from __future__ import annotations

import numpy as np
import pandas as pd

from plots._common import color_cycle, downsample, numeric_columns, placeholder


def _clean_columns(df: pd.DataFrame, count: int) -> tuple[list[str], list[np.ndarray]] | None:
    columns = numeric_columns(df)
    if len(columns) < count:
        return None
    frame = (
        df[columns[:count]]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if frame.empty:
        return None
    if len(frame) > 5_000:
        indexes = np.linspace(0, len(frame) - 1, 5_000, dtype=int)
        frame = frame.iloc[indexes]
    return [str(column) for column in columns[:count]], [
        frame[column].to_numpy(dtype=float) for column in columns[:count]
    ]


def _xy_data(df: pd.DataFrame) -> tuple[str, str, np.ndarray, np.ndarray] | None:
    columns = numeric_columns(df)
    if not columns:
        return None
    if len(columns) == 1:
        name = str(columns[0])
        values = pd.to_numeric(df[columns[0]], errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(values)
        y = downsample(values[mask])
        return "Row", name, np.arange(y.size, dtype=float), y
    prepared = _clean_columns(df, 2)
    if prepared is None:
        return None
    names, values = prepared
    return names[0], names[1], downsample(values[0]), downsample(values[1])


def step_plot(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _xy_data(df)
    if prepared is None:
        placeholder(ax, "Step Plot needs one or two numeric columns.")
        return
    x_name, y_name, x, y = prepared
    ax.step(x, y, where="mid", color=color_cycle(1)[0], linewidth=1.8)
    ax.set_title("Step Plot")
    ax.set_xlabel(x_name)
    ax.set_ylabel(y_name)


def stem_plot(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _xy_data(df)
    if prepared is None:
        placeholder(ax, "Stem Plot needs one or two numeric columns.")
        return
    x_name, y_name, x, y = prepared
    markerline, stemlines, baseline = ax.stem(x, y, basefmt=" ")
    color = color_cycle(1)[0]
    markerline.set_color(color)
    markerline.set_markersize(4)
    stemlines.set_color(color)
    stemlines.set_alpha(0.75)
    baseline.set_visible(False)
    ax.axhline(0.0, color="#7b8794", linewidth=0.8)
    ax.set_title("Stem Plot")
    ax.set_xlabel(x_name)
    ax.set_ylabel(y_name)


def error_bar_plot(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _clean_columns(df, 3)
    if prepared is None:
        placeholder(ax, "Error Bar needs numeric X, Y, and uncertainty columns.")
        return
    names, (x, y, uncertainty) = prepared
    uncertainty = np.abs(uncertainty)
    ax.errorbar(
        x,
        y,
        yerr=uncertainty,
        fmt="o-",
        markersize=4,
        linewidth=1.3,
        capsize=3,
        color=color_cycle(1)[0],
        ecolor="#f2a541",
    )
    ax.set_title("Error Bar Plot")
    ax.set_xlabel(names[0])
    ax.set_ylabel(f"{names[1]} +/- {names[2]}")


def bubble_plot(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    columns = numeric_columns(df)
    required = 4 if len(columns) >= 4 else 3
    prepared = _clean_columns(df, required)
    if prepared is None:
        placeholder(ax, "Bubble Plot needs X, Y, and size columns.")
        return
    names, values = prepared
    x, y, size_values = values[:3]
    span = float(np.ptp(size_values))
    sizes = 35.0 + 210.0 * (
        (size_values - np.min(size_values)) / span if span > 0 else np.ones_like(size_values) * 0.5
    )
    colors = values[3] if len(values) >= 4 else size_values
    artist = ax.scatter(
        x,
        y,
        s=sizes,
        c=colors,
        cmap="viridis",
        alpha=0.72,
        edgecolors="white",
        linewidths=0.35,
    )
    artist.set_rasterized(len(x) >= 10_000)
    ax.set_title("Bubble Plot")
    ax.set_xlabel(names[0])
    ax.set_ylabel(names[1])


def hexbin_plot(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _clean_columns(df, 2)
    if prepared is None:
        placeholder(ax, "Hexbin Plot needs two numeric columns.")
        return
    names, (x, y) = prepared
    ax.hexbin(x, y, gridsize=24, mincnt=1, cmap="viridis", linewidths=0.15)
    ax.set_title("Hexbin Density")
    ax.set_xlabel(names[0])
    ax.set_ylabel(names[1])


PLOTS = [
    {
        "key": "step_plot",
        "title": "Step Plot",
        "category": "Basic 2D",
        "func": step_plot,
        "desc": "Show discrete level changes with horizontal steps",
        "min_cols": 1,
        "multi": False,
    },
    {
        "key": "stem_plot",
        "title": "Stem Plot",
        "category": "Basic 2D",
        "func": stem_plot,
        "desc": "Show discrete samples as markers connected to a baseline",
        "min_cols": 1,
        "multi": False,
    },
    {
        "key": "error_bar_plot",
        "title": "Error Bar",
        "category": "Basic 2D",
        "func": error_bar_plot,
        "desc": "Plot X and Y with a third column as symmetric uncertainty",
        "min_cols": 3,
        "multi": False,
    },
    {
        "key": "bubble_plot",
        "title": "Bubble Plot",
        "category": "Basic 2D",
        "func": bubble_plot,
        "desc": "Encode a third measurement as point size and an optional fourth as color",
        "min_cols": 3,
        "multi": False,
    },
    {
        "key": "hexbin_plot",
        "title": "Hexbin Density",
        "category": "Basic 2D",
        "func": hexbin_plot,
        "desc": "Reveal dense structure in a large two-variable point cloud",
        "min_cols": 2,
        "multi": False,
    },
]
