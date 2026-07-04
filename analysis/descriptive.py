"""Descriptive statistics (ROADMAP section D).

Pure pandas/numpy helpers, no Qt.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd


def describe_series(series: pd.Series) -> dict:
    """Full descriptive summary of a numeric series (NaN ignored).

    Keys: count, mean, median, mode, std, variance, skewness, kurtosis
    (Fisher — normal = 0), min, max. Empty/all-NaN input raises ValueError.
    """
    x = pd.to_numeric(series, errors="coerce").dropna()
    if x.empty:
        raise ValueError("no numeric data to describe")
    mode_values = x.mode()
    return {
        "count": int(x.count()),
        "mean": float(x.mean()),
        "median": float(x.median()),
        "mode": float(mode_values.iloc[0]) if not mode_values.empty else float("nan"),
        "std": float(x.std()),
        "variance": float(x.var()),
        "skewness": float(x.skew()),
        "kurtosis": float(x.kurt()),
        "min": float(x.min()),
        "max": float(x.max()),
    }


def covariance_matrix(df: pd.DataFrame, cols: Optional[List[str]] = None) -> pd.DataFrame:
    """Covariance matrix of the numeric columns (or the requested subset)."""
    if cols:
        sub = df[cols]
    else:
        sub = df.select_dtypes(include=[np.number])
    sub = sub.apply(lambda c: pd.to_numeric(c, errors="coerce"))
    if sub.shape[1] < 2:
        raise ValueError("need at least 2 numeric columns for a covariance matrix")
    return sub.cov()


def format_describe(stats: dict, title: str = "") -> str:
    """Human-readable rendering of :func:`describe_series` for message boxes."""
    order = ["count", "mean", "median", "mode", "std", "variance",
             "skewness", "kurtosis", "min", "max"]
    lines = [title] if title else []
    for key in order:
        if key in stats:
            value = stats[key]
            if key == "count":
                lines.append(f"{key:<10} {int(value)}")
            else:
                lines.append(f"{key:<10} {value:.6g}")
    return "\n".join(lines)
