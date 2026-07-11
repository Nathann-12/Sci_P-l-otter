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
        "open_file",
        "Open a data file (CSV/Excel/...) from an absolute path into a new Book.",
        {"path": {"type": "string", "description": "absolute file path", "required": True}},
        lambda args: _tool_open_file(window, args),
    )
    return registry
