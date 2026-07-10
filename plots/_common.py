"""Shared helpers for the Origin-style plot library (:mod:`plots`).

Keep these small and dependency-light (numpy / pandas / matplotlib only). Plot
functions should lean on these so behaviour (numeric-column selection, empty
handling, down-sampling, placeholder text) stays consistent across modules.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


MAX_POINTS = 5000


def numeric_columns(df: pd.DataFrame) -> List[str]:
    """Names of the numeric columns in *df* (order preserved)."""
    if df is None or getattr(df, "empty", True):
        return []
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def numeric_series(df: pd.DataFrame, max_n: int | None = None) -> List[Tuple[str, np.ndarray]]:
    """Return ``[(name, values), ...]`` for numeric columns, NaNs dropped.

    Each array is 1-D float with NaN/inf removed. Empty columns are skipped.
    ``max_n`` caps how many columns come back (None = all).
    """
    out: List[Tuple[str, np.ndarray]] = []
    for name in numeric_columns(df):
        arr = pd.to_numeric(df[name], errors="coerce").to_numpy(dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size:
            out.append((str(name), arr))
        if max_n is not None and len(out) >= max_n:
            break
    return out


def clean_pair(x, y) -> Tuple[np.ndarray, np.ndarray]:
    """Two arrays -> finite, equal-length, row-aligned float arrays."""
    x = pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(pd.Series(y), errors="coerce").to_numpy(dtype=float)
    n = min(x.size, y.size)
    x, y = x[:n], y[:n]
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask]


def downsample(arr: np.ndarray, max_points: int = MAX_POINTS) -> np.ndarray:
    """Evenly stride *arr* down to at most *max_points* samples."""
    arr = np.asarray(arr)
    if arr.ndim == 0 or arr.shape[0] <= max_points:
        return arr
    step = int(np.ceil(arr.shape[0] / max_points))
    return arr[::step]


def placeholder(ax, message: str) -> None:
    """Clear *ax* and show a centered message (used when data is insufficient)."""
    try:
        ax.clear()
        text_method = getattr(ax, "text2D", None)
        if callable(text_method):
            text_method(
                0.5, 0.5, message,
                ha="center", va="center", transform=ax.transAxes,
                fontsize=10, color=_muted_color(),
            )
        else:
            ax.text(
                0.5, 0.5, message,
                ha="center", va="center", transform=ax.transAxes,
                fontsize=10, color=_muted_color(),
            )
        ax.set_xticks([])
        ax.set_yticks([])
    except Exception:
        pass


def _muted_color() -> str:
    import matplotlib as mpl
    return mpl.rcParams.get("text.color", "#b8bec6") or "#b8bec6"


def color_cycle(n: int) -> List[str]:
    """First *n* colors of the active property cycle (wraps if needed)."""
    import matplotlib as mpl
    cyc = mpl.rcParams["axes.prop_cycle"].by_key().get("color", ["#4F9CF9"])
    if not cyc:
        cyc = ["#4F9CF9"]
    return [cyc[i % len(cyc)] for i in range(max(n, 0))]
