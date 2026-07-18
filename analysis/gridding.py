"""XYZ <-> matrix gridding (OriginPro-style Matrix conversion).

Pure numerical logic: scattered or regular XYZ triplets become a dense Z
matrix with X/Y coordinate vectors, and back. No Qt, no DataFrame mutation —
the UI/AI layers wrap these with Books.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


class GriddingError(ValueError):
    pass


GRID_METHODS = ("nearest", "linear", "cubic")


@dataclass(frozen=True)
class GridResult:
    z: np.ndarray          # (ny, nx) — row i is y[i], column j is x[j]
    x: np.ndarray          # (nx,) column coordinates
    y: np.ndarray          # (ny,) row coordinates
    method: str            # "regular" for the exact pivot fast path
    n_points: int          # finite input triplets used
    n_missing: int         # cells left NaN (outside the convex hull / holes)

    @property
    def shape(self) -> tuple[int, int]:
        return tuple(self.z.shape)


def _clean_xyz(x, y, z):
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    z = np.asarray(z, dtype=float).ravel()
    if not (x.size == y.size == z.size):
        raise GriddingError("X, Y and Z must have the same length")
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x, y, z = x[ok], y[ok], z[ok]
    if x.size < 3:
        raise GriddingError("Need at least 3 finite XYZ points to grid")
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        raise GriddingError("X and Y must each span a non-zero range")
    return x, y, z


def _try_regular(x, y, z):
    """Exact pivot when the points already form a complete rectangular grid."""
    ux = np.unique(x)
    uy = np.unique(y)
    if ux.size * uy.size != x.size or ux.size < 2 or uy.size < 2:
        return None
    zz = np.full((uy.size, ux.size), np.nan)
    ix = np.searchsorted(ux, x)
    iy = np.searchsorted(uy, y)
    zz[iy, ix] = z
    if np.isnan(zz).any():  # duplicates left holes -> not a complete grid
        return None
    return GridResult(zz, ux, uy, "regular", int(x.size), 0)


def grid_xyz(
    x: Sequence[float],
    y: Sequence[float],
    z: Sequence[float],
    *,
    nx: int = 50,
    ny: int = 50,
    method: str = "linear",
) -> GridResult:
    """Grid scattered XYZ onto an (ny, nx) matrix.

    A complete rectangular input grid is pivoted exactly (no interpolation and
    ``nx``/``ny`` are ignored). Scattered data is interpolated with scipy's
    ``griddata``; cells outside the convex hull stay NaN and are counted in
    ``n_missing`` rather than silently invented.
    """
    method = str(method).strip().lower()
    if method not in GRID_METHODS:
        raise GriddingError(
            f"Unknown gridding method '{method}'. Choose one of: {', '.join(GRID_METHODS)}"
        )
    x, y, z = _clean_xyz(x, y, z)

    regular = _try_regular(x, y, z)
    if regular is not None:
        return regular

    nx = int(nx)
    ny = int(ny)
    if not (2 <= nx <= 2000 and 2 <= ny <= 2000):
        raise GriddingError("Grid size must be between 2 and 2000 per axis")
    if method == "cubic" and x.size < 16:
        method = "linear"  # cubic needs a healthy neighbourhood; degrade honestly
    from scipy.interpolate import griddata

    gx = np.linspace(float(np.min(x)), float(np.max(x)), nx)
    gy = np.linspace(float(np.min(y)), float(np.max(y)), ny)
    mesh_x, mesh_y = np.meshgrid(gx, gy)
    zz = griddata((x, y), z, (mesh_x, mesh_y), method=method)
    zz = np.asarray(zz, dtype=float)
    missing = int(np.count_nonzero(~np.isfinite(zz)))
    return GridResult(zz, gx, gy, method, int(x.size), missing)


def matrix_to_xyz(z, x=None, y=None) -> pd.DataFrame:
    """Flatten a matrix back to long-form X/Y/Z rows (NaN cells dropped)."""
    zz = np.asarray(z, dtype=float)
    if zz.ndim != 2 or zz.size == 0:
        raise GriddingError("Matrix must be a non-empty 2-D array")
    ny, nx = zz.shape
    gx = np.asarray(x, dtype=float) if x is not None else np.arange(nx, dtype=float)
    gy = np.asarray(y, dtype=float) if y is not None else np.arange(ny, dtype=float)
    if gx.size != nx or gy.size != ny:
        raise GriddingError("Coordinate vectors do not match the matrix shape")
    mesh_x, mesh_y = np.meshgrid(gx, gy)
    ok = np.isfinite(zz)
    return pd.DataFrame({
        "x": mesh_x[ok].ravel(),
        "y": mesh_y[ok].ravel(),
        "z": zz[ok].ravel(),
    })


def matrix_dataframe(result: GridResult, *, decimals: int = 6) -> pd.DataFrame:
    """Matrix Book representation: columns are X coordinates, index is Y.

    Coordinates are encoded in the labels themselves so the Book round-trips
    through sessions/projects with no side-channel metadata.
    """
    columns = [str(round(float(v), decimals)) for v in result.x]
    frame = pd.DataFrame(result.z, columns=columns)
    frame.insert(0, "y", np.round(result.y.astype(float), decimals))
    return frame


def dataframe_to_matrix(frame: pd.DataFrame):
    """Parse a matrix Book (numeric columns; optional leading ``y`` column).

    Returns ``(z, x, y)``. Column labels that parse as numbers become X
    coordinates; otherwise 0..nx-1 is used. A leading ``y`` column supplies Y.
    """
    if frame is None or frame.empty:
        raise GriddingError("The active Book is empty")
    work = frame.copy()
    y = None
    first = str(work.columns[0]).strip().lower()
    if first == "y":
        y = pd.to_numeric(work.iloc[:, 0], errors="coerce").to_numpy(dtype=float)
        work = work.iloc[:, 1:]
    numeric = work.select_dtypes(include=[np.number])
    if numeric.shape[1] < 2 or len(numeric) < 2:
        raise GriddingError("A matrix Book needs at least a 2x2 numeric block")
    z = numeric.to_numpy(dtype=float)
    try:
        x = np.asarray([float(str(c)) for c in numeric.columns], dtype=float)
    except (TypeError, ValueError):
        x = np.arange(z.shape[1], dtype=float)
    if y is None or not np.isfinite(y).all() or y.size != z.shape[0]:
        y = np.arange(z.shape[0], dtype=float)
    return z, x, y
