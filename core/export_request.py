from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import matplotlib.dates as mdates
import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class ExportSeries:
    x: Any
    y: Any
    label: str


@dataclass(frozen=True, slots=True)
class VisibleRangeExportRequest:
    dataframe: pd.DataFrame
    x_column: str
    lower: float
    upper: float
    series: tuple[ExportSeries, ...] = ()


@dataclass(frozen=True, slots=True)
class FigureExportOptions:
    format_name: str
    dpi: int = 300
    transparent: bool = False
    tight: bool = True

    def __post_init__(self) -> None:
        if self.dpi <= 0:
            raise ValueError("dpi must be positive")


@dataclass(frozen=True, slots=True)
class BatchFigureExportOptions:
    format_name: str
    directory: str
    dpi: int = 300
    transparent: bool = False
    tight: bool = True
    include_empty: bool = False

    def __post_init__(self) -> None:
        if self.dpi <= 0:
            raise ValueError("dpi must be positive")
        if not str(self.directory).strip():
            raise ValueError("directory is required")


def safe_export_stem(name: object, fallback: str = "figure") -> str:
    """Return a Windows-safe filename stem while preserving readable titles."""
    raw = str(name or "").strip()
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem or fallback


def batch_export_filename(
    directory: str | Path,
    title: object,
    index: int,
    extension: str,
) -> Path:
    ext = str(extension).lstrip(".").lower()
    fallback = f"Graph_{max(index, 1)}"
    stem = safe_export_stem(title, fallback=fallback)
    return Path(directory) / f"{index:02d}_{stem}.{ext}"


def line_to_numeric(values: Any) -> tuple[np.ndarray, bool]:
    arr = np.asarray(values)
    if arr.size == 0:
        return arr.astype(float), False
    if np.issubdtype(arr.dtype, np.datetime64):
        dates = pd.Series(pd.to_datetime(arr, errors="coerce"))
        valid = dates.notna()
        numeric_arr = np.full(len(dates), np.nan, dtype=float)
        numeric_arr[valid.to_numpy()] = mdates.date2num(
            dates[valid].to_numpy(dtype="datetime64[ns]")
        )
        return numeric_arr, True
    if np.issubdtype(arr.dtype, np.number):
        return arr.astype(float), False
    numeric = pd.to_numeric(arr, errors="coerce")
    numeric_arr = numeric.to_numpy() if hasattr(numeric, "to_numpy") else np.asarray(numeric, dtype=float)
    if numeric_arr.size and np.isfinite(numeric_arr).any():
        return numeric_arr, False
    dt_series = pd.Series(pd.to_datetime(arr, errors="coerce", format="mixed"))
    valid = dt_series.notna()
    if not valid.any():
        return numeric_arr, False
    numeric_arr = np.full(len(dt_series), np.nan, dtype=float)
    numeric_arr[valid.to_numpy()] = mdates.date2num(
        dt_series[valid].to_numpy(dtype="datetime64[ns]")
    )
    return numeric_arr, True


def dataframe_for_visible_range(request: VisibleRangeExportRequest) -> pd.DataFrame:
    lower = min(request.lower, request.upper)
    upper = max(request.lower, request.upper)
    dataframe = request.dataframe
    x_column = request.x_column

    if x_column in dataframe.columns:
        x_series = dataframe[x_column]
        x_numeric, x_is_datetime = line_to_numeric(x_series)
        mask = np.isfinite(x_numeric) & (x_numeric >= lower) & (x_numeric <= upper)
        if mask.any():
            return dataframe.loc[mask].copy()
    else:
        x_is_datetime = False

    fallback = None
    fallback_is_datetime = x_is_datetime
    label_counts: dict[str, int] = {}
    for index, series in enumerate(request.series):
        x_numeric, series_is_datetime = line_to_numeric(series.x)
        y_values = np.asarray(series.y)
        length = min(x_numeric.size, y_values.size)
        if length == 0:
            continue
        x_numeric = x_numeric[:length]
        y_values = y_values[:length]
        mask = np.isfinite(x_numeric) & (x_numeric >= lower) & (x_numeric <= upper)
        if not mask.any():
            continue
        label = series.label if series.label and not series.label.startswith("_") else f"y{index + 1}"
        label_counts[label] = label_counts.get(label, 0) + 1
        if label_counts[label] > 1:
            label = f"{label} ({label_counts[label]})"
        series_frame = pd.DataFrame({"__x__": x_numeric[mask], label: y_values[mask]})
        series_frame["__occurrence__"] = series_frame.groupby(
            "__x__", sort=False
        ).cumcount()
        fallback = (
            series_frame
            if fallback is None
            else pd.merge(
                fallback,
                series_frame,
                on=["__x__", "__occurrence__"],
                how="outer",
            )
        )
        fallback_is_datetime = fallback_is_datetime or series_is_datetime

    if fallback is None or fallback.empty:
        return pd.DataFrame()

    fallback.sort_values(["__x__", "__occurrence__"], inplace=True)
    fallback.reset_index(drop=True, inplace=True)
    if fallback_is_datetime:
        dates = pd.Series(pd.to_datetime(mdates.num2date(fallback["__x__"].to_numpy())))
        try:
            dates = dates.dt.tz_localize(None)
        except (TypeError, AttributeError, ValueError):
            pass
        fallback[x_column] = dates.to_numpy()
    else:
        fallback[x_column] = fallback["__x__"]
    ordered = [x_column] + [
        column
        for column in fallback.columns
        if column not in {"__x__", "__occurrence__", x_column}
    ]
    return fallback[ordered]
