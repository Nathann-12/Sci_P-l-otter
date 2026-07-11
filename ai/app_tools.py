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
    return registry
