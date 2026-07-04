"""Data-cleaning primitives (ROADMAP section B).

Pure pandas/numpy functions with no Qt dependency so they can be unit-tested
headless. Column-adding helpers follow the ``processors.add_*`` convention:
mutate the DataFrame in place, return the new column name. Row-changing
operations (duplicates/outliers/sort/resample) never mutate — they return a
new DataFrame so callers decide when to swap ``self._df``.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


FILL_METHODS = ("value", "mean", "median", "ffill", "bfill")
OUTLIER_METHODS = ("zscore", "iqr")
NORMALIZE_METHODS = ("zscore", "minmax")


def fill_missing(
    df: pd.DataFrame,
    col: str,
    method: str = "mean",
    value: Optional[float] = None,
    new_col: Optional[str] = None,
) -> str:
    """Fill NaN in ``df[col]`` into a new column; returns the new column name.

    ``method``: one of FILL_METHODS. ``value`` is only used for ``"value"``.
    """
    if method not in FILL_METHODS:
        raise ValueError(f"unknown fill method: {method!r} (use one of {FILL_METHODS})")
    if new_col is None:
        new_col = f"{col}_filled"
    s = df[col]
    if method == "value":
        if value is None:
            raise ValueError("method='value' requires a fill value")
        filled = s.fillna(value)
    elif method == "mean":
        filled = s.fillna(pd.to_numeric(s, errors="coerce").mean())
    elif method == "median":
        filled = s.fillna(pd.to_numeric(s, errors="coerce").median())
    elif method == "ffill":
        filled = s.ffill()
    else:  # bfill
        filled = s.bfill()
    df[new_col] = filled
    return new_col


def interpolate_missing(
    df: pd.DataFrame,
    col: str,
    method: str = "linear",
    new_col: Optional[str] = None,
) -> str:
    """Interpolate NaN gaps in ``df[col]`` into a new column; returns its name."""
    if new_col is None:
        new_col = f"{col}_interp"
    s = pd.to_numeric(df[col], errors="coerce")
    df[new_col] = s.interpolate(method=method, limit_direction="both")
    return new_col


def remove_duplicates(
    df: pd.DataFrame, subset: Optional[Iterable[str]] = None
) -> Tuple[pd.DataFrame, int]:
    """Return ``(deduplicated_df, n_removed)``; keeps the first occurrence."""
    out = df.drop_duplicates(subset=list(subset) if subset else None).reset_index(drop=True)
    return out, len(df) - len(out)


def _default_threshold(method: str) -> float:
    return 3.0 if method == "zscore" else 1.5


def detect_outliers(
    series: pd.Series, method: str = "zscore", threshold: Optional[float] = None
) -> pd.Series:
    """Boolean mask (aligned to ``series``) marking outliers.

    ``zscore``: |x - mean| / std > threshold (default 3.0).
    ``iqr``: outside [Q1 - k*IQR, Q3 + k*IQR] with k = threshold (default 1.5).
    NaN values are never flagged.
    """
    if method not in OUTLIER_METHODS:
        raise ValueError(f"unknown outlier method: {method!r} (use one of {OUTLIER_METHODS})")
    if threshold is None:
        threshold = _default_threshold(method)
    x = pd.to_numeric(series, errors="coerce")
    if method == "zscore":
        std = x.std()
        if not np.isfinite(std) or std == 0:
            return pd.Series(False, index=series.index)
        mask = (x - x.mean()).abs() / std > threshold
    else:
        q1, q3 = x.quantile(0.25), x.quantile(0.75)
        iqr = q3 - q1
        mask = (x < q1 - threshold * iqr) | (x > q3 + threshold * iqr)
    return mask.fillna(False)


def remove_outliers(
    df: pd.DataFrame,
    col: str,
    method: str = "zscore",
    threshold: Optional[float] = None,
) -> Tuple[pd.DataFrame, int]:
    """Return ``(df_without_outlier_rows, n_removed)`` based on ``df[col]``."""
    mask = detect_outliers(df[col], method=method, threshold=threshold)
    out = df.loc[~mask].reset_index(drop=True)
    return out, int(mask.sum())


def normalize_column(
    df: pd.DataFrame,
    col: str,
    method: str = "zscore",
    new_col: Optional[str] = None,
) -> str:
    """Standardize (``zscore``) or min-max scale (``minmax``) ``df[col]``.

    Adds the result as a new column; returns its name.
    """
    if method not in NORMALIZE_METHODS:
        raise ValueError(f"unknown normalize method: {method!r} (use one of {NORMALIZE_METHODS})")
    x = pd.to_numeric(df[col], errors="coerce")
    if method == "zscore":
        std = x.std()
        if not np.isfinite(std) or std == 0:
            raise ValueError(f"column {col!r} has zero variance — cannot z-score")
        result = (x - x.mean()) / std
        suffix = "zscore"
    else:
        rng = x.max() - x.min()
        if not np.isfinite(rng) or rng == 0:
            raise ValueError(f"column {col!r} has zero range — cannot min-max scale")
        result = (x - x.min()) / rng
        suffix = "minmax"
    if new_col is None:
        new_col = f"{col}_{suffix}"
    df[new_col] = result
    return new_col


def detrend_polynomial(
    df: pd.DataFrame,
    col: str,
    order: int = 1,
    x_col: Optional[str] = None,
    new_col: Optional[str] = None,
) -> str:
    """Subtract a fitted polynomial baseline of ``order`` from ``df[col]``.

    Fits on finite points only (against ``x_col`` values or the row index),
    writes the residual to a new column, returns its name. ``order=1`` is a
    linear detrend; higher orders serve as polynomial baseline subtraction.
    """
    if order < 0:
        raise ValueError("order must be >= 0")
    y = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
    if x_col is not None:
        x = pd.to_numeric(df[x_col], errors="coerce").to_numpy(dtype=float)
    else:
        x = np.arange(len(y), dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.sum() <= order:
        raise ValueError(f"not enough finite points ({int(finite.sum())}) to fit order {order}")
    coeffs = np.polyfit(x[finite], y[finite], order)
    baseline = np.polyval(coeffs, x)
    if new_col is None:
        new_col = f"{col}_detrend{order}"
    df[new_col] = y - baseline
    return new_col


# Baseline subtraction is the same operation exposed under its ROADMAP name.
baseline_subtract = detrend_polynomial


def resample_uniform(
    df: pd.DataFrame,
    x_col: str,
    y_cols: Optional[List[str]] = None,
    n_points: Optional[int] = None,
) -> pd.DataFrame:
    """Resample numeric columns onto a uniform ``x_col`` grid (linear interp).

    Returns a new DataFrame with ``x_col`` evenly spaced over its original
    range and every requested (or every numeric) y column interpolated onto it.
    """
    x = pd.to_numeric(df[x_col], errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(x)
    if finite.sum() < 2:
        raise ValueError(f"column {x_col!r} needs at least 2 finite values to resample")
    if y_cols is None:
        y_cols = [
            c for c in df.columns
            if c != x_col and pd.api.types.is_numeric_dtype(df[c])
        ]
    if n_points is None:
        n_points = int(finite.sum())
    if n_points < 2:
        raise ValueError("n_points must be >= 2")

    order = np.argsort(x[finite])
    x_sorted = x[finite][order]
    grid = np.linspace(x_sorted[0], x_sorted[-1], n_points)
    out = {x_col: grid}
    for c in y_cols:
        y = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)[finite][order]
        good = np.isfinite(y)
        if good.sum() < 2:
            out[c] = np.full(n_points, np.nan)
        else:
            out[c] = np.interp(grid, x_sorted[good], y[good])
    return pd.DataFrame(out)


def sort_dataframe(df: pd.DataFrame, col: str, ascending: bool = True) -> pd.DataFrame:
    """Return a copy of ``df`` sorted by ``col`` with a clean index."""
    return df.sort_values(col, ascending=ascending).reset_index(drop=True)
