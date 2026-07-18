"""AI tools for the Matrix / Image / Surface workflow.

Wrap the same param-taking cores the Matrix menu uses
(``main_window_matrix_mixin``): no dialogs, defensive, short strings back.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

from ai.app_tools import _active_df, _numeric_columns, _resolve_column_name


def _resolve(df, value, fallback=None):
    if value is not None:
        resolved = _resolve_column_name(df, value)
        if resolved is not None:
            return resolved
    return fallback


def _tool_grid_xyz(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data. Open a Book with XYZ columns first."
    numeric = _numeric_columns(df)
    if len(numeric) < 3:
        return "Gridding needs three numeric columns (X, Y, Z)."
    x = _resolve(df, args.get("x_column"), numeric[0])
    y = _resolve(df, args.get("y_column"), numeric[1])
    z = _resolve(df, args.get("z_column"), numeric[2])
    if len({x, y, z}) != 3:
        return "X, Y and Z must be three different columns."
    try:
        book, result = window.matrix_grid_core(
            x, y, z,
            nx=int(args.get("nx", 50) or 50),
            ny=int(args.get("ny", 50) or 50),
            method=str(args.get("method", "linear") or "linear"),
        )
        note = (
            f"Gridded {result.n_points} points into a "
            f"{result.shape[0]}x{result.shape[1]} matrix ({result.method}). "
            f"Matrix Book: {book}."
        )
        if result.n_missing:
            note += f" {result.n_missing} cells outside the data hull are empty."
        return note
    except Exception as exc:
        logger.debug("grid_xyz tool failed", exc_info=True)
        return f"Could not grid the data: {exc}"


def _tool_matrix_transform(window, args: Dict[str, Any]) -> str:
    op = str(args.get("op", "")).strip().lower()
    if not op:
        return (
            "Specify 'op': transpose, flip_horizontal, flip_vertical, rotate90, "
            "crop, smooth_gaussian, smooth_median, subtract_background, "
            "normalize or clip."
        )
    params: Dict[str, Any] = {}
    for key in ("sigma", "size", "mode", "lower", "upper",
                "row0", "row1", "col0", "col1"):
        if args.get(key) is not None:
            params[key] = args[key]
    try:
        book, shape = window.matrix_transform_core(op, **params)
        return f"Applied {op}; result is a {shape[0]}x{shape[1]} matrix Book: {book}."
    except Exception as exc:
        logger.debug("matrix_transform tool failed", exc_info=True)
        return f"Could not apply {op}: {exc}"


def _tool_plot_matrix(window, args: Dict[str, Any]) -> str:
    kind = str(args.get("kind", "heatmap") or "heatmap").strip().lower()
    try:
        note = window.matrix_plot_core(kind)
        return f"Plotted a {note} in a new Graph window."
    except Exception as exc:
        logger.debug("plot_matrix tool failed", exc_info=True)
        return f"Could not plot the matrix: {exc}"


def register_matrix_tools(registry, window) -> None:
    registry.add(
        "grid_xyz",
        "Convert scattered XYZ columns in the active Book into a dense matrix "
        "Book (gridding). A complete rectangular grid is pivoted exactly; "
        "scattered data is interpolated (nearest/linear/cubic).",
        {
            "x_column": {"type": "string", "description": "X column", "required": False},
            "y_column": {"type": "string", "description": "Y column", "required": False},
            "z_column": {"type": "string", "description": "Z value column", "required": False},
            "nx": {"type": "integer", "description": "grid columns (default 50)", "required": False},
            "ny": {"type": "integer", "description": "grid rows (default 50)", "required": False},
            "method": {
                "type": "string", "required": False,
                "description": "nearest | linear | cubic",
                "enum": ["nearest", "linear", "cubic"],
            },
        },
        lambda args: _tool_grid_xyz(window, args),
    )
    registry.add(
        "matrix_transform",
        "Transform or filter the active matrix Book into a new matrix Book: "
        "transpose, flip_horizontal, flip_vertical, rotate90, crop "
        "(row0/row1/col0/col1), smooth_gaussian (sigma), smooth_median (size), "
        "subtract_background (mode: min/mean/median/plane), normalize "
        "(mode: minmax/zscore) or clip (lower/upper).",
        {
            "op": {"type": "string", "description": "operation name", "required": True},
            "sigma": {"type": "number", "description": "gaussian sigma", "required": False},
            "size": {"type": "integer", "description": "median window (odd)", "required": False},
            "mode": {"type": "string", "description": "background/normalize mode", "required": False},
            "lower": {"type": "number", "description": "clip lower limit", "required": False},
            "upper": {"type": "number", "description": "clip upper limit", "required": False},
            "row0": {"type": "integer", "description": "crop first row", "required": False},
            "row1": {"type": "integer", "description": "crop last row (exclusive)", "required": False},
            "col0": {"type": "integer", "description": "crop first column", "required": False},
            "col1": {"type": "integer", "description": "crop last column (exclusive)", "required": False},
        },
        lambda args: _tool_matrix_transform(window, args),
    )
    registry.add(
        "plot_matrix",
        "Plot the active matrix Book with its real X/Y coordinates in a new "
        "Graph: heatmap, filled contour, or 3D surface.",
        {
            "kind": {
                "type": "string", "required": False,
                "description": "heatmap | contour | surface",
                "enum": ["heatmap", "contour", "surface"],
            },
        },
        lambda args: _tool_plot_matrix(window, args),
    )
