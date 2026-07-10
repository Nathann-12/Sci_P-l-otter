from __future__ import annotations

import math
import numbers
import warnings
from datetime import date, datetime
from typing import Any

import matplotlib.dates as mdates
import matplotlib.ticker as mticker


def to_sequence_for_plot(values: Any) -> list[Any]:
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        return list(values)
    try:
        import numpy as np
        if isinstance(values, np.ndarray):
            return values.tolist()
    except Exception:
        pass
    try:
        import pandas as pd
        if isinstance(values, (pd.Series, pd.Index)):
            return values.tolist()
    except Exception:
        pass
    try:
        return list(values)
    except TypeError:
        return [values]


def is_invalid_plot_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd
        if isinstance(value, pd.Timestamp):
            try:
                if not (1 <= value.year <= 9999):
                    return True
            except Exception:
                return True
        if pd.isna(value):
            return True
    except Exception:
        pass
    try:
        import numpy as np
        if isinstance(value, np.datetime64):
            try:
                import pandas as pd
                ts = pd.Timestamp(value)
                if not (1 <= ts.year <= 9999):
                    return True
                value = ts.to_pydatetime()
            except Exception:
                return True
    except Exception:
        pass
    if isinstance(value, (datetime, date)):
        year = value.year
        return year < 1 or year > 9999
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        return stripped.lower() in {"nan", "nat", "none"}
    try:
        import numpy as np
        if isinstance(value, (np.floating, float)):
            return not math.isfinite(float(value))
        if isinstance(value, (np.integer, int)):
            return False
        if isinstance(value, (np.complexfloating, complex)):
            return not (math.isfinite(value.real) and math.isfinite(value.imag))
    except Exception:
        pass
    return False


def sanitize_plot_xy(x: Any, y: Any) -> tuple[list[Any], list[Any]]:
    x_seq = to_sequence_for_plot(x)
    y_seq = to_sequence_for_plot(y)
    if not x_seq or not y_seq:
        return [], []
    length = min(len(x_seq), len(y_seq))
    filtered_x: list[Any] = []
    filtered_y: list[Any] = []
    for xv, yv in zip(x_seq[:length], y_seq[:length]):
        if is_invalid_plot_value(xv) or is_invalid_plot_value(yv):
            continue
        filtered_x.append(xv)
        filtered_y.append(yv)
    return filtered_x, filtered_y


def mostly_numeric(values: Any) -> bool:
    numeric = 0
    total = 0
    for value in to_sequence_for_plot(values):
        if value is None:
            continue
        if isinstance(value, bool):
            total += 1
            continue
        if isinstance(value, numbers.Real):
            total += 1
            try:
                if math.isfinite(float(value)):
                    numeric += 1
            except Exception:
                pass
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                continue
            try:
                float(stripped)
            except Exception:
                total += 1
            else:
                numeric += 1
                total += 1
            continue
        total += 1
    return total > 0 and (numeric / total) >= 0.8


def prepare_plot_data(x: Any, y: Any) -> tuple[list[Any], list[Any], bool]:
    filtered_x, filtered_y = sanitize_plot_xy(x, y)
    if not filtered_x or not filtered_y:
        return [], [], False

    ser = None
    if not mostly_numeric(filtered_x):
        try:
            import pandas as pd
            ser = pd.to_datetime(filtered_x, errors="coerce", format="mixed")
            mask = ser.notna()
            valid = mask.sum()
            if valid >= max(2, int(0.6 * len(filtered_x))):
                filtered_y = [filtered_y[i] for i, ok in enumerate(mask) if ok]
                filtered_x = ser[mask].to_pydatetime().tolist()
            else:
                ser = None
        except Exception:
            ser = None

    x_is_datetime = False
    if filtered_y:
        if ser is not None:
            try:
                filtered_x = mdates.date2num(filtered_x)
                x_is_datetime = True
            except Exception:
                filtered_x = [fx for fx in filtered_x]
        elif isinstance(filtered_x[0], (datetime, date)):
            try:
                filtered_x = mdates.date2num(filtered_x)
                x_is_datetime = True
            except Exception:
                filtered_x = [fx for fx in filtered_x]
    return list(filtered_x), list(filtered_y), x_is_datetime


def axis_uses_dates(axis: Any) -> bool:
    try:
        if isinstance(axis.get_major_locator(), mdates.DateLocator):
            return True
        if hasattr(axis, "get_converter"):
            converter = axis.get_converter()
        else:
            converter = getattr(axis, "converter", None)
        return isinstance(converter, mdates.DateConverter)
    except Exception:
        return False


def reset_numeric_axis(ax: Any) -> None:
    try:
        ax.xaxis.set_units(None)
        if hasattr(ax.xaxis, "set_converter"):
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="This axis already has a converter set.*",
                    category=UserWarning,
                )
                ax.xaxis.set_converter(None)
        else:
            ax.xaxis.converter = None
        ax.xaxis.set_major_locator(mticker.AutoLocator())
        ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
        try:
            ax.xaxis.set_minor_locator(mticker.AutoMinorLocator())
        except Exception:
            pass
        ax.figure.autofmt_xdate(False)
    except Exception:
        pass


def clamp_date_limits(ax: Any) -> None:
    min_ord = mdates.date2num(datetime(1, 1, 1))
    max_ord = mdates.date2num(datetime(9999, 12, 31))
    targets = ((ax.get_xlim, ax.set_xlim, ax.xaxis), (ax.get_ylim, ax.set_ylim, ax.yaxis))
    for getter, setter, axis in targets:
        if not axis_uses_dates(axis):
            continue
        try:
            lo, hi = getter()
            if not (math.isfinite(lo) and math.isfinite(hi)):
                continue
            original_lo, original_hi = lo, hi
            if lo < min_ord:
                lo = min_ord
            if hi > max_ord:
                hi = max_ord
            if lo >= hi:
                lo, hi = min_ord, max_ord
            if lo != original_lo or hi != original_hi:
                setter(lo, hi)
        except Exception:
            continue
