"""Bind a handful of SciPlotter capabilities as AI tools.

Handlers are thin, defensive adapters over existing MainWindow seams
(``_resolve_active_dataframe``, ``plot_from_workbook`` ...). They return short
text so the model can reason about the result. The window is captured lazily so
this module imports fine (and unit-tests) without a running app.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ai.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_PLOT_STYLES = {"line", "scatter", "bar", "histogram"}


def _active_df(window):
    getter = getattr(window, "_resolve_active_dataframe", None)
    return getter() if callable(getter) else None


def _tool_list_columns(window, _args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data. Ask the user to open a file or a Book first."
    cols = [str(c) for c in df.columns]
    return f"Active data has {len(df)} rows and {len(cols)} columns: {', '.join(cols)}."


def _tool_describe_data(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data to describe."
    try:
        from analysis.descriptive import descriptive_table

        requested = args.get("columns")
        cols = [str(c) for c in requested] if isinstance(requested, list) and requested else None
        table = descriptive_table(df, cols)
        return "Descriptive statistics:\n" + table.to_string()
    except Exception as exc:
        logger.debug("describe_data tool failed", exc_info=True)
        return f"Could not compute statistics: {exc}"


def _tool_plot(window, args: Dict[str, Any]) -> str:
    style = str(args.get("style", "line")).strip().lower()
    if style not in _PLOT_STYLES:
        return f"Unknown style '{style}'. Use one of: {', '.join(sorted(_PLOT_STYLES))}."
    plotter = getattr(window, "plot_from_workbook", None)
    if not callable(plotter):
        return "Plotting is not available in this context."
    try:
        plotter(style, new_graph=True)
        return f"Created a new {style} graph from the active Book's selected/designated columns."
    except Exception as exc:
        logger.debug("plot tool failed", exc_info=True)
        return f"Could not create the plot: {exc}"


def _tool_active_book(window, _args: Dict[str, Any]) -> str:
    label = getattr(window, "_active_book_label", None)
    name = label() if callable(label) else None
    return f"Active Book: {name}" if name else "No active Book."


def _tool_list_fit_models(_window, _args: Dict[str, Any]) -> str:
    try:
        from analysis.fitting import list_available_models

        return "Available fit models: " + ", ".join(list_available_models())
    except Exception as exc:
        logger.debug("list_fit_models tool failed", exc_info=True)
        return f"Could not list fit models: {exc}"


def _numeric_columns(df):
    return [c for c in df.columns if str(df[c].dtype) != "object"]


def _tool_fit_curve(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data to fit."
    model = str(args.get("model", "linear")).strip() or "linear"
    numeric = _numeric_columns(df)
    x_col = args.get("x_column") or (numeric[0] if len(numeric) >= 1 else None)
    y_col = args.get("y_column") or (numeric[1] if len(numeric) >= 2 else None)
    if x_col is None or y_col is None or x_col not in df.columns or y_col not in df.columns:
        return "Need at least two numeric columns (or pass x_column and y_column) to fit."
    try:
        from analysis.fitting import fit_curve

        result = fit_curve(df[x_col].to_numpy(), df[y_col].to_numpy(), model)
        params = ", ".join(f"{k}={v:.4g}" for k, v in result.params.items())
        return (
            f"Fit '{result.model}' of {y_col} vs {x_col}: {params} "
            f"(R^2 = {result.r_squared:.4f})."
        )
    except Exception as exc:
        logger.debug("fit_curve tool failed", exc_info=True)
        return f"Could not fit: {exc}"


def _resolve_y_column(window, df, args: Dict[str, Any]):
    """Pick the column to operate on: explicit arg -> selected Y -> last numeric."""
    requested = args.get("column")
    if requested and requested in df.columns:
        return requested
    getter = getattr(window, "selected_y_column", None)
    selected = getter() if callable(getter) else None
    if selected and selected in df.columns:
        return selected
    numeric = _numeric_columns(df)
    return numeric[-1] if numeric else None


def _tool_smooth(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data to smooth."
    if not callable(getattr(window, "smooth_column", None)):
        return "Smoothing is not available in this context."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column to smooth."
    method = str(args.get("method", "savitzky-golay")).strip().lower()
    try:
        new_col = window.smooth_column(
            col, method,
            window=int(args.get("window", 11)),
            kernel=int(args.get("kernel", 5)),
            sigma=float(args.get("sigma", 2.0)),
        )
        return f"Smoothed '{col}' ({method}) into new column '{new_col}'."
    except Exception as exc:
        logger.debug("smooth tool failed", exc_info=True)
        return f"Could not smooth: {exc}"


def _tool_filter_signal(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data to filter."
    if not callable(getattr(window, "filter_column_butterworth", None)):
        return "Filtering is not available in this context."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column to filter."
    try:
        fs = float(args.get("fs", 0) or 0)
    except (TypeError, ValueError):
        fs = 0.0
    if fs <= 0:
        return "Provide the sampling rate 'fs' (Hz)."
    kind = str(args.get("kind", "lowpass")).strip().lower()
    cutoff = args.get("cutoff")
    try:
        new_col = window.filter_column_butterworth(col, fs, kind=kind, cutoff=cutoff)
        return f"Filtered '{col}' ({kind}, fs={fs:g} Hz) into new column '{new_col}'."
    except Exception as exc:
        logger.debug("filter_signal tool failed", exc_info=True)
        return f"Could not filter: {exc}"


def _sync_new_column(window, new_col: str) -> None:
    adder = getattr(window, "add_y_column_option", None)
    if callable(adder):
        try:
            adder(new_col)
        except Exception:
            logger.debug("add_y_column_option failed for %s", new_col, exc_info=True)


def _swap_dataframe(window, new_df) -> None:
    swap = getattr(window, "_swap_dataframe", None)
    if callable(swap):
        swap(new_df)
    else:
        window._df = new_df


def _tool_moving_average(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        from processors import add_moving_average

        window_size = int(args.get("window", 25))
        new_col = add_moving_average(df, col, window=window_size)
        _sync_new_column(window, new_col)
        return f"Added moving average (window {window_size}) of '{col}' as '{new_col}'."
    except Exception as exc:
        logger.debug("moving_average tool failed", exc_info=True)
        return f"Could not compute moving average: {exc}"


def _tool_fill_missing(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    method = str(args.get("method", "mean")).strip().lower()
    value = args.get("value")
    try:
        from analysis.cleaning import fill_missing

        new_col = fill_missing(df, col, method=method, value=value)
        _sync_new_column(window, new_col)
        return f"Filled missing values in '{col}' (method {method}) into '{new_col}'."
    except Exception as exc:
        logger.debug("fill_missing tool failed", exc_info=True)
        return f"Could not fill missing values: {exc}"


def _tool_interpolate(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        from analysis.cleaning import interpolate_missing

        new_col = interpolate_missing(df, col)
        _sync_new_column(window, new_col)
        return f"Interpolated missing values in '{col}' into '{new_col}'."
    except Exception as exc:
        logger.debug("interpolate tool failed", exc_info=True)
        return f"Could not interpolate: {exc}"


def _tool_normalize(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    method = str(args.get("method", "zscore")).strip().lower()
    try:
        from analysis.cleaning import normalize_column

        new_col = normalize_column(df, col, method=method)
        _sync_new_column(window, new_col)
        return f"Normalized '{col}' ({method}) into '{new_col}'."
    except Exception as exc:
        logger.debug("normalize tool failed", exc_info=True)
        return f"Could not normalize: {exc}"


def _tool_detrend(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    x_getter = getattr(window, "selected_x_column", None)
    x_col = x_getter() if callable(x_getter) else None
    if x_col not in getattr(df, "columns", []):
        x_col = None
    try:
        from analysis.cleaning import detrend_polynomial

        order = int(args.get("order", 1))
        new_col = detrend_polynomial(df, col, order=order, x_col=x_col)
        _sync_new_column(window, new_col)
        return f"Removed order-{order} trend from '{col}' into '{new_col}'."
    except Exception as exc:
        logger.debug("detrend tool failed", exc_info=True)
        return f"Could not detrend: {exc}"


def _tool_remove_outliers(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    method = str(args.get("method", "zscore")).strip().lower()
    threshold = args.get("threshold")
    try:
        from analysis.cleaning import remove_outliers

        new_df, removed = remove_outliers(
            df, col, method=method,
            threshold=float(threshold) if threshold is not None else None,
        )
        _swap_dataframe(window, new_df)
        return f"Removed {removed} outlier rows from '{col}' (method {method}); {len(new_df)} rows remain."
    except Exception as exc:
        logger.debug("remove_outliers tool failed", exc_info=True)
        return f"Could not remove outliers: {exc}"


def _tool_remove_duplicates(window, _args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    try:
        from analysis.cleaning import remove_duplicates

        new_df, removed = remove_duplicates(df)
        _swap_dataframe(window, new_df)
        return f"Removed {removed} duplicate rows; {len(new_df)} rows remain."
    except Exception as exc:
        logger.debug("remove_duplicates tool failed", exc_info=True)
        return f"Could not remove duplicates: {exc}"


def _tool_sort_data(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = args.get("column")
    if not col or col not in df.columns:
        return f"Provide a valid 'column' to sort by. Available: {', '.join(str(c) for c in df.columns)}."
    ascending = args.get("ascending", True)
    ascending = str(ascending).strip().lower() not in {"false", "0", "desc", "descending", "no"}
    try:
        from analysis.cleaning import sort_dataframe

        new_df = sort_dataframe(df, col, ascending=ascending)
        _swap_dataframe(window, new_df)
        return f"Sorted data by '{col}' ({'ascending' if ascending else 'descending'})."
    except Exception as exc:
        logger.debug("sort_data tool failed", exc_info=True)
        return f"Could not sort: {exc}"


def _tool_list_books(window, _args: Dict[str, Any]) -> str:
    getter = getattr(window, "_dataset_names", None)
    names = getter() if callable(getter) else None
    if not names:
        label = getattr(window, "_active_book_label", None)
        active = label() if callable(label) else None
        return f"Open Books: {active}" if active else "No Books are open."
    active_getter = getattr(window, "_active_book_label", None)
    active = active_getter() if callable(active_getter) else None
    marked = [f"{n} (active)" if n == active else n for n in names]
    return f"Open Books ({len(names)}): " + ", ".join(marked)


def _tool_envelope(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        from analysis.signal_filters import signal_envelope

        env = signal_envelope(df[col])
        new_col = f"{col}_envelope"
        df[new_col] = env
        _sync_new_column(window, new_col)
        return f"Computed the amplitude envelope of '{col}' as '{new_col}'."
    except Exception as exc:
        logger.debug("envelope tool failed", exc_info=True)
        return f"Could not compute envelope: {exc}"


def _tool_signal_quality(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        fs = float(args.get("fs", 1.0) or 1.0)
    except (TypeError, ValueError):
        fs = 1.0
    try:
        from analysis.signal_filters import signal_quality_summary

        summary = signal_quality_summary(df[col], fs=fs)
        return (
            f"Signal quality of '{col}' (fs={summary['fs_hz']:g} Hz): "
            f"SNR ≈ {summary['snr_db']:.2f} dB, noise floor ≈ {summary['noise_floor']:.4g}."
        )
    except Exception as exc:
        logger.debug("signal_quality tool failed", exc_info=True)
        return f"Could not assess signal quality: {exc}"


def _tool_fft(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data for FFT."
    numeric = _numeric_columns(df)
    if not numeric:
        return "Need a numeric column for FFT."
    y_col = _resolve_y_column(window, df, args)
    x_req = args.get("x_column")
    x_getter = getattr(window, "selected_x_column", None)
    x_sel = x_getter() if callable(x_getter) else None
    x_col = (x_req if x_req in df.columns else None) or (x_sel if x_sel in df.columns else None) or numeric[0]
    if y_col is None or y_col == x_col:
        y_col = next((c for c in numeric if c != x_col), y_col)
    if y_col is None:
        return "Need a numeric signal column for FFT."
    try:
        from processors import compute_fft

        df_fft, fs = compute_fft(df, x_col=x_col, y_col=y_col)
        opener = getattr(window, "_open_signal_result_book", None)
        if callable(opener):
            opener(f"FFT_{y_col}", df_fft)
        peak_freq = float(df_fft.loc[df_fft["amplitude"].idxmax(), "freq_Hz"])
        return (
            f"Computed FFT of '{y_col}' (fs≈{fs:.4g} Hz). Dominant frequency "
            f"≈ {peak_freq:.4g} Hz. Spectrum opened as a result Book."
        )
    except Exception as exc:
        logger.debug("fft tool failed", exc_info=True)
        return f"Could not compute FFT: {exc}"


def _tool_open_file(window, args: Dict[str, Any]) -> str:
    import os

    path = str(args.get("path", "")).strip()
    if not path:
        return "Provide a 'path' to the data file to open."
    if not os.path.isfile(path):
        return f"File not found: {path}"
    inserter = getattr(window, "_stage_insert", None)
    if not callable(inserter):
        return "Opening files is not available in this context."
    try:
        from loaders import load_tabular

        df, name = load_tabular(path)
        inserter(name, df, path)
        return f"Opened '{name}' ({len(df)} rows, {len(df.columns)} columns) into a new Book."
    except Exception as exc:
        logger.debug("open_file tool failed", exc_info=True)
        return f"Could not open '{path}': {exc}"


def build_app_registry(window) -> ToolRegistry:
    """Registry of tools bound to *window* (a MainWindow-like object)."""
    registry = ToolRegistry()
    registry.add(
        "list_columns",
        "List the column names, row count and column count of the active data table (Book).",
        {},
        lambda args: _tool_list_columns(window, args),
    )
    registry.add(
        "describe_data",
        "Compute descriptive statistics (count, mean, std, min, max, ...) for the active data. "
        "Optional 'columns' is a list of column names; omit it for all numeric columns.",
        {"columns": {"type": "array", "description": "column names to describe", "required": False}},
        lambda args: _tool_describe_data(window, args),
    )
    registry.add(
        "plot_columns",
        "Plot the active Book's selected/designated columns on a NEW graph window.",
        {"style": {"type": "string", "description": "line | scatter | bar | histogram", "required": False}},
        lambda args: _tool_plot(window, args),
    )
    registry.add(
        "active_book",
        "Report which data Book (dataset) is currently active.",
        {},
        lambda args: _tool_active_book(window, args),
    )
    registry.add(
        "list_fit_models",
        "List the curve-fit models available (linear, exponential, gaussian, ...).",
        {},
        lambda args: _tool_list_fit_models(window, args),
    )
    registry.add(
        "fit_curve",
        "Fit a curve to the active data and return the parameters and R-squared. "
        "'model' is a fit model name; x_column/y_column are optional (default: first "
        "two numeric columns).",
        {
            "model": {"type": "string", "description": "fit model name", "required": True},
            "x_column": {"type": "string", "description": "x column name", "required": False},
            "y_column": {"type": "string", "description": "y column name", "required": False},
        },
        lambda args: _tool_fit_curve(window, args),
    )
    registry.add(
        "smooth_data",
        "Smooth a column and add the result as a new column. method: "
        "savitzky-golay | median | gaussian. column optional (default: active Y / last numeric).",
        {
            "method": {"type": "string", "description": "savitzky-golay|median|gaussian", "required": False},
            "column": {"type": "string", "description": "column to smooth", "required": False},
            "window": {"type": "number", "description": "savgol window (odd)", "required": False},
        },
        lambda args: _tool_smooth(window, args),
    )
    registry.add(
        "filter_signal",
        "Apply a zero-phase Butterworth filter and add the result as a new column. "
        "Requires 'fs' (Hz). kind: lowpass|highpass|bandpass|bandstop. cutoff is a "
        "number (low/high pass) or [low, high] (band pass/stop).",
        {
            "fs": {"type": "number", "description": "sampling rate in Hz", "required": True},
            "kind": {"type": "string", "description": "lowpass|highpass|bandpass|bandstop", "required": False},
            "cutoff": {"type": "number", "description": "cutoff Hz (or [low,high])", "required": False},
            "column": {"type": "string", "description": "column to filter", "required": False},
        },
        lambda args: _tool_filter_signal(window, args),
    )
    registry.add(
        "moving_average",
        "Add a moving-average (rolling mean) column. window optional (default 25).",
        {
            "window": {"type": "number", "description": "window size", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_moving_average(window, args),
    )
    registry.add(
        "fill_missing",
        "Fill missing (NaN) values in a column into a new column. method: "
        "mean | median | ffill | bfill | value (with 'value').",
        {
            "method": {"type": "string", "description": "fill method", "required": False},
            "value": {"type": "number", "description": "value when method=value", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_fill_missing(window, args),
    )
    registry.add(
        "interpolate",
        "Interpolate missing values in a column into a new column.",
        {"column": {"type": "string", "description": "column", "required": False}},
        lambda args: _tool_interpolate(window, args),
    )
    registry.add(
        "normalize",
        "Rescale a column into a new column. method: zscore (mean 0/std 1) or minmax (0-1).",
        {
            "method": {"type": "string", "description": "zscore|minmax", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_normalize(window, args),
    )
    registry.add(
        "detrend",
        "Remove a polynomial trend/baseline from a column into a new column. "
        "order optional (1 = linear).",
        {
            "order": {"type": "number", "description": "polynomial order", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_detrend(window, args),
    )
    registry.add(
        "remove_outliers",
        "Drop rows where a column is an outlier (replaces the active data). "
        "method: zscore | iqr; threshold optional.",
        {
            "method": {"type": "string", "description": "zscore|iqr", "required": False},
            "threshold": {"type": "number", "description": "threshold", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_remove_outliers(window, args),
    )
    registry.add(
        "remove_duplicates",
        "Remove duplicate rows from the active data (replaces it).",
        {},
        lambda args: _tool_remove_duplicates(window, args),
    )
    registry.add(
        "sort_data",
        "Sort the active data by a column (replaces it). ascending true/false.",
        {
            "column": {"type": "string", "description": "column to sort by", "required": True},
            "ascending": {"type": "boolean", "description": "ascending order", "required": False},
        },
        lambda args: _tool_sort_data(window, args),
    )
    registry.add(
        "run_fft",
        "Compute the FFT amplitude/power spectrum of a signal column and open it "
        "as a result Book; reports the dominant frequency. column/x_column optional.",
        {
            "column": {"type": "string", "description": "signal (Y) column", "required": False},
            "x_column": {"type": "string", "description": "time/X column for fs", "required": False},
        },
        lambda args: _tool_fft(window, args),
    )
    registry.add(
        "envelope",
        "Compute the amplitude (Hilbert) envelope of a signal column into a new column.",
        {"column": {"type": "string", "description": "signal column", "required": False}},
        lambda args: _tool_envelope(window, args),
    )
    registry.add(
        "signal_quality",
        "Report a signal's SNR (dB) and noise floor. fs optional (Hz).",
        {
            "fs": {"type": "number", "description": "sampling rate Hz", "required": False},
            "column": {"type": "string", "description": "signal column", "required": False},
        },
        lambda args: _tool_signal_quality(window, args),
    )
    registry.add(
        "list_books",
        "List the open data Books (datasets) and which one is active. "
        "Use this before operating on a specific Book.",
        {},
        lambda args: _tool_list_books(window, args),
    )
    registry.add(
        "open_file",
        "Open a data file (CSV/Excel/...) from an absolute path into a new Book.",
        {"path": {"type": "string", "description": "absolute file path", "required": True}},
        lambda args: _tool_open_file(window, args),
    )
    return registry
