"""Scientific 3D plots for XYZ worksheets."""
from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.colors import Normalize
from matplotlib.tri import LinearTriInterpolator, Triangulation

from plots._common import color_cycle, numeric_columns, placeholder


def _xyz_data(
    df: pd.DataFrame,
    *,
    max_points: int = 2_000,
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray] | None:
    columns = numeric_columns(df)
    if len(columns) < 3:
        return None
    frame = (
        df[columns[:3]]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(frame) < 3:
        return None
    if len(frame) > max_points:
        indexes = np.linspace(0, len(frame) - 1, max_points, dtype=int)
        frame = frame.iloc[indexes]
    values = [frame[column].to_numpy(dtype=float) for column in columns[:3]]
    return [str(column) for column in columns[:3]], values[0], values[1], values[2]


def _require_3d(ax, df: pd.DataFrame):
    if not hasattr(ax, "zaxis"):
        placeholder(ax, "This chart requires a 3D graph.")
        return None
    prepared = _xyz_data(df)
    if prepared is None:
        placeholder(ax, "This 3D chart needs three numeric XYZ columns.")
        return None
    return prepared


def _triangulation(x: np.ndarray, y: np.ndarray) -> Triangulation | None:
    points = np.column_stack((x, y))
    if np.unique(points, axis=0).shape[0] < 3:
        return None
    centered = points - np.mean(points, axis=0)
    if np.linalg.matrix_rank(centered) < 2:
        return None
    try:
        return Triangulation(x, y)
    except (RuntimeError, ValueError):
        return None


def _surface_grid(x: np.ndarray, y: np.ndarray, z: np.ndarray):
    triangulation = _triangulation(x, y)
    if triangulation is None:
        return None
    gx, gy = np.meshgrid(
        np.linspace(float(np.min(x)), float(np.max(x)), 36),
        np.linspace(float(np.min(y)), float(np.max(y)), 36),
    )
    try:
        interpolated = LinearTriInterpolator(triangulation, z)(gx, gy)
    except (RuntimeError, ValueError):
        return None
    gz = np.asarray(np.ma.filled(interpolated, np.nan), dtype=float)
    if not np.isfinite(gz).any():
        return None
    return gx, gy, gz


def _label_xyz(ax, names: list[str], title: str) -> None:
    ax.set_xlabel(names[0])
    ax.set_ylabel(names[1])
    ax.set_zlabel(names[2])
    ax.set_title(title)


def scatter_3d(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _require_3d(ax, df)
    if prepared is None:
        return
    names, x, y, z = prepared
    ax.scatter(x, y, z, c=z, cmap="viridis", s=18, alpha=0.82, depthshade=True)
    _label_xyz(ax, names, "3D Scatter")


def trajectory_3d(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _require_3d(ax, df)
    if prepared is None:
        return
    names, x, y, z = prepared
    color = color_cycle(1)[0]
    ax.plot(x, y, z, color=color, linewidth=1.8)
    sample = np.linspace(0, len(x) - 1, min(18, len(x)), dtype=int)
    ax.scatter(x[sample], y[sample], z[sample], color=color, s=14, depthshade=True)
    _label_xyz(ax, names, "3D Trajectory")


def stem_3d(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _require_3d(ax, df)
    if prepared is None:
        return
    names, x, y, z = prepared
    if len(x) > 160:
        indexes = np.linspace(0, len(x) - 1, 160, dtype=int)
        x, y, z = x[indexes], y[indexes], z[indexes]
    markerline, stemlines, baseline = ax.stem(x, y, z, basefmt=" ")
    color = color_cycle(1)[0]
    markerline.set_color(color)
    markerline.set_markersize(3.5)
    stemlines.set_color(color)
    stemlines.set_alpha(0.72)
    baseline.set_visible(False)
    _label_xyz(ax, names, "3D Stem")


def bar_3d(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _require_3d(ax, df)
    if prepared is None:
        return
    names, x, y, z = prepared
    if len(x) > 225:
        indexes = np.linspace(0, len(x) - 1, 225, dtype=int)
        x, y, z = x[indexes], y[indexes], z[indexes]
    count_scale = max(1.0, np.sqrt(len(x)))
    dx = max(float(np.ptp(x)) / count_scale * 0.55, 0.08)
    dy = max(float(np.ptp(y)) / count_scale * 0.55, 0.08)
    base = np.minimum(z, 0.0)
    height = np.abs(z)
    z_min, z_max = float(np.min(z)), float(np.max(z))
    norm = Normalize(vmin=z_min, vmax=z_max if z_max > z_min else z_min + 1.0)
    colors = colormaps["viridis"](norm(z))
    ax.bar3d(x - dx / 2, y - dy / 2, base, dx, dy, height, color=colors, shade=True)
    _label_xyz(ax, names, "3D Bar")


def surface_3d(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _require_3d(ax, df)
    if prepared is None:
        return
    names, x, y, z = prepared
    grid = _surface_grid(x, y, z)
    if grid is None:
        placeholder(ax, "Surface needs non-collinear XYZ coordinates.")
        return
    gx, gy, gz = grid
    ax.plot_surface(gx, gy, gz, cmap="viridis", linewidth=0, antialiased=True)
    _label_xyz(ax, names, "3D Surface")


def wireframe_3d(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _require_3d(ax, df)
    if prepared is None:
        return
    names, x, y, z = prepared
    grid = _surface_grid(x, y, z)
    if grid is None:
        placeholder(ax, "Wireframe needs non-collinear XYZ coordinates.")
        return
    gx, gy, gz = grid
    ax.plot_wireframe(
        gx,
        gy,
        gz,
        rstride=2,
        cstride=2,
        color=color_cycle(1)[0],
        linewidth=0.65,
    )
    _label_xyz(ax, names, "3D Wireframe")


def contour_3d(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _require_3d(ax, df)
    if prepared is None:
        return
    names, x, y, z = prepared
    triangulation = _triangulation(x, y)
    if triangulation is None:
        placeholder(ax, "3D Contour needs non-collinear XYZ coordinates.")
        return
    try:
        ax.tricontour(triangulation, z, levels=14, cmap="viridis", linewidths=1.1)
    except (RuntimeError, ValueError):
        placeholder(ax, "XYZ points cannot form 3D contours.")
        return
    _label_xyz(ax, names, "3D Contour")


def trisurface_3d(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _require_3d(ax, df)
    if prepared is None:
        return
    names, x, y, z = prepared
    triangulation = _triangulation(x, y)
    if triangulation is None:
        placeholder(ax, "Tri-Surface needs non-collinear XYZ coordinates.")
        return
    ax.plot_trisurf(
        triangulation,
        z,
        cmap="viridis",
        linewidth=0.2,
        antialiased=True,
    )
    _label_xyz(ax, names, "3D Triangulated Surface")


def _entry(key: str, title: str, func, description: str) -> dict:
    return {
        "key": key,
        "title": title,
        "category": "3D",
        "func": func,
        "desc": description,
        "min_cols": 3,
        "multi": False,
        "is3d": True,
        "projection": "3d",
    }


PLOTS = [
    _entry("scatter_3d", "3D Scatter", scatter_3d, "Plot XYZ observations as colored points"),
    _entry("trajectory_3d", "3D Trajectory", trajectory_3d, "Connect ordered XYZ observations into a path"),
    _entry("stem_3d", "3D Stem", stem_3d, "Show discrete XYZ samples as stems from a baseline"),
    _entry("bar_3d", "3D Bar", bar_3d, "Use X and Y as positions and Z as bar height"),
    _entry("surface_3d", "3D Surface", surface_3d, "Interpolate XYZ samples onto a smooth colored surface"),
    _entry("wireframe_3d", "3D Wireframe", wireframe_3d, "Interpolate XYZ samples into a mesh wireframe"),
    _entry("contour_3d", "3D Contour", contour_3d, "Draw XYZ contour levels in three dimensions"),
    _entry(
        "trisurface_3d",
        "3D Triangulated Surface",
        trisurface_3d,
        "Connect irregular XYZ samples without requiring a rectangular grid",
    ),
]
