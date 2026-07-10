"""Polar plots using worksheet angle/radius columns."""
from __future__ import annotations

import numpy as np
import pandas as pd

from plots._common import color_cycle, numeric_columns, placeholder


def _polar_series(df: pd.DataFrame):
    columns = numeric_columns(df)
    if not columns:
        return None
    if len(columns) == 1:
        radius = pd.to_numeric(df[columns[0]], errors="coerce").to_numpy(dtype=float)
        theta = np.linspace(0.0, 2.0 * np.pi, radius.size, endpoint=False)
        radius_columns = columns
        angle_name = "Angle"
    else:
        theta = pd.to_numeric(df[columns[0]], errors="coerce").to_numpy(dtype=float)
        finite_theta = theta[np.isfinite(theta)]
        if finite_theta.size and np.nanmax(np.abs(finite_theta)) > 2.0 * np.pi + 0.1:
            theta = np.deg2rad(theta)
        radius_columns = columns[1:]
        angle_name = str(columns[0])

    series = []
    for column in radius_columns:
        radius = pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)
        length = min(theta.size, radius.size)
        angles = theta[:length]
        values = radius[:length]
        mask = np.isfinite(angles) & np.isfinite(values)
        if mask.any():
            series.append((str(column), angles[mask], values[mask]))
    return angle_name, series


def polar_line(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _polar_series(df)
    if prepared is None or not prepared[1]:
        placeholder(ax, "Polar plot needs numeric angle/radius data.")
        return
    angle_name, series = prepared
    colors = color_cycle(len(series))
    for index, (name, theta, radius) in enumerate(series):
        ax.plot(theta, radius, color=colors[index], linewidth=1.5, label=name)
    ax.set_title(f"Polar Line ({angle_name})")
    ax.legend(loc="upper right", bbox_to_anchor=(1.22, 1.12), fontsize=8)


def polar_scatter(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _polar_series(df)
    if prepared is None or not prepared[1]:
        placeholder(ax, "Polar scatter needs numeric angle/radius data.")
        return
    angle_name, series = prepared
    colors = color_cycle(len(series))
    for index, (name, theta, radius) in enumerate(series):
        ax.scatter(theta, radius, s=14, alpha=0.7, color=colors[index], label=name)
    ax.set_title(f"Polar Scatter ({angle_name})")
    ax.legend(loc="upper right", bbox_to_anchor=(1.22, 1.12), fontsize=8)


def wind_rose(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _polar_series(df)
    if prepared is None or not prepared[1]:
        placeholder(ax, "Wind rose needs numeric angle/radius data.")
        return
    _, series = prepared
    _, theta, weights = series[0]
    bins = np.linspace(0.0, 2.0 * np.pi, 17)
    totals, edges = np.histogram(
        np.mod(theta, 2.0 * np.pi),
        bins=bins,
        weights=np.abs(weights),
    )
    centers = (edges[:-1] + edges[1:]) / 2.0
    width = np.diff(edges) * 0.9
    ax.bar(centers, totals, width=width, bottom=0.0, color=color_cycle(1)[0], alpha=0.8)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_title("Wind Rose")


PLOTS = [
    {
        "key": "polar_line",
        "title": "Polar Line",
        "category": "Polar",
        "func": polar_line,
        "desc": "Line plot using angle and radius worksheet columns",
        "min_cols": 1,
        "multi": False,
        "projection": "polar",
    },
    {
        "key": "polar_scatter",
        "title": "Polar Scatter",
        "category": "Polar",
        "func": polar_scatter,
        "desc": "Scatter plot using angle and radius worksheet columns",
        "min_cols": 1,
        "multi": False,
        "projection": "polar",
    },
    {
        "key": "wind_rose",
        "title": "Wind Rose",
        "category": "Polar",
        "func": wind_rose,
        "desc": "Direction histogram weighted by radius or magnitude",
        "min_cols": 1,
        "multi": False,
        "projection": "polar",
    },
]
