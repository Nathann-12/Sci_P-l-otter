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
    for key in ("sigma", "size", "mode", "method", "level", "brightness",
                "contrast", "lower", "upper", "row0", "row1", "col0", "col1",
                "x0", "x1", "y0", "y1", "ny", "nx"):
        if args.get(key) is not None:
            params[key] = args[key]
    try:
        book, shape = window.matrix_transform_core(op, **params)
        return f"Applied {op}; result is a {shape[0]}x{shape[1]} matrix Book: {book}."
    except Exception as exc:
        logger.debug("matrix_transform tool failed", exc_info=True)
        return f"Could not apply {op}: {exc}"


def _tool_matrix_statistics(window, args: Dict[str, Any]) -> str:
    try:
        book, stats = window.matrix_statistics_core()
        return (
            f"Matrix statistics: min {stats['min']:.4g}, max {stats['max']:.4g} "
            f"at ({stats['max_x']:.4g}, {stats['max_y']:.4g}), mean "
            f"{stats['mean']:.4g}, std {stats['std']:.4g}. Table Book: {book}."
        )
    except Exception as exc:
        logger.debug("matrix_statistics tool failed", exc_info=True)
        return f"Could not compute matrix statistics: {exc}"


def _tool_line_profile(window, args: Dict[str, Any]) -> str:
    for key in ("x0", "y0", "x1", "y1"):
        if args.get(key) is None:
            return "Provide the line endpoints x0, y0, x1, y1 (data coordinates)."
    try:
        book, n = window.matrix_line_profile_core(
            (float(args["x0"]), float(args["y0"])),
            (float(args["x1"]), float(args["y1"])),
            samples=int(args.get("samples", 200) or 200),
        )
        return (
            f"Extracted a line profile with {n} finite samples; opened the "
            f"profile Book ({book}) and plotted the curve."
        )
    except Exception as exc:
        logger.debug("line_profile tool failed", exc_info=True)
        return f"Could not extract the line profile: {exc}"


def _tool_matrix_arithmetic(window, args: Dict[str, Any]) -> str:
    other = args.get("other_book")
    if not other:
        return "Specify 'other_book' — the name of the second matrix Book to combine with."
    op = str(args.get("op", "subtract") or "subtract")
    try:
        book, shape = window.matrix_arithmetic_core(str(other), op)
        return f"Computed A {op} B → {shape[0]}x{shape[1]} matrix Book: {book}."
    except Exception as exc:
        logger.debug("matrix_arithmetic tool failed", exc_info=True)
        return f"Could not combine the matrices: {exc}"


def _tool_surface_metrics(window, args: Dict[str, Any]) -> str:
    try:
        book, m = window.matrix_surface_metrics_core()
        return (
            f"Surface metrics: Ra {m['Ra']:.4g}, Rq {m['Rq']:.4g}, peak-to-valley "
            f"{m['peak_to_valley']:.4g}, volume {m['volume_above_min']:.4g}, "
            f"mean slope {m['mean_slope']:.4g}. Table Book: {book}."
        )
    except Exception as exc:
        logger.debug("surface_metrics tool failed", exc_info=True)
        return f"Could not compute surface metrics: {exc}"


def _tool_matrix_stack(window, args: Dict[str, Any]) -> str:
    books = args.get("books")
    if not isinstance(books, list) or len(books) < 2:
        return "Provide 'books' — a list of at least two matrix Book names to stack."
    mode = str(args.get("mode", "max") or "max")
    try:
        book, shape = window.matrix_stack_core(books, mode)
        return (
            f"{mode} projection of {len(books)} frames -> {shape[0]}x{shape[1]} "
            f"matrix Book: {book}."
        )
    except Exception as exc:
        logger.debug("matrix_stack tool failed", exc_info=True)
        return f"Could not project the stack: {exc}"


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
        "Transform, filter or image-process the active matrix Book into a new "
        "matrix Book. op: transpose, flip_horizontal, flip_vertical, rotate90, "
        "crop (row0..col1) or roi (x0/x1/y0/y1 in data coords), smooth_gaussian "
        "(sigma), smooth_median (size), subtract_background (mode: "
        "min/mean/median/plane), normalize (mode: minmax/zscore), clip "
        "(lower/upper), fft2, resize (ny/nx), threshold (level, mode: "
        "binary/mask/to_zero), edge_detect (method: sobel/prewitt/laplace), "
        "contrast (brightness, contrast), morphology (mode: "
        "erode/dilate/open/close, size), or gradient.",
        {
            "op": {"type": "string", "description": "operation name", "required": True},
            "sigma": {"type": "number", "description": "gaussian sigma", "required": False},
            "size": {"type": "integer", "description": "median/morphology window", "required": False},
            "mode": {"type": "string", "description": "background/normalize/threshold/morphology mode", "required": False},
            "method": {"type": "string", "description": "edge operator", "required": False},
            "level": {"type": "number", "description": "threshold level", "required": False},
            "brightness": {"type": "number", "description": "contrast brightness offset", "required": False},
            "contrast": {"type": "number", "description": "contrast multiplier", "required": False},
            "lower": {"type": "number", "description": "clip lower limit", "required": False},
            "upper": {"type": "number", "description": "clip upper limit", "required": False},
            "row0": {"type": "integer", "description": "crop first row", "required": False},
            "row1": {"type": "integer", "description": "crop last row (exclusive)", "required": False},
            "col0": {"type": "integer", "description": "crop first column", "required": False},
            "col1": {"type": "integer", "description": "crop last column (exclusive)", "required": False},
            "x0": {"type": "number", "description": "roi X from (data coords)", "required": False},
            "x1": {"type": "number", "description": "roi X to", "required": False},
            "y0": {"type": "number", "description": "roi Y from", "required": False},
            "y1": {"type": "number", "description": "roi Y to", "required": False},
            "ny": {"type": "integer", "description": "resize rows", "required": False},
            "nx": {"type": "integer", "description": "resize columns", "required": False},
        },
        lambda args: _tool_matrix_transform(window, args),
    )
    registry.add(
        "matrix_statistics",
        "Summarise the active matrix Book (min/max/mean/median/std/sum and the "
        "X/Y coordinates of the maximum and minimum) into a table Book.",
        {},
        lambda args: _tool_matrix_statistics(window, args),
    )
    registry.add(
        "line_profile",
        "Extract the Z profile along a straight line across the active matrix "
        "Book (data coordinates x0,y0 -> x1,y1), open it as a Book and plot it.",
        {
            "x0": {"type": "number", "description": "start X", "required": True},
            "y0": {"type": "number", "description": "start Y", "required": True},
            "x1": {"type": "number", "description": "end X", "required": True},
            "y1": {"type": "number", "description": "end Y", "required": True},
            "samples": {"type": "integer", "description": "points along the line (default 200)", "required": False},
        },
        lambda args: _tool_line_profile(window, args),
    )
    registry.add(
        "matrix_arithmetic",
        "Combine the active matrix Book with another matrix Book element-wise "
        "(subtract/add/multiply/divide) — e.g. a difference image A - B.",
        {
            "other_book": {"type": "string", "description": "name of the second matrix Book", "required": True},
            "op": {
                "type": "string", "required": False,
                "description": "subtract | add | multiply | divide",
                "enum": ["subtract", "add", "multiply", "divide"],
            },
        },
        lambda args: _tool_matrix_arithmetic(window, args),
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
    registry.add(
        "surface_metrics",
        "Compute surface metrics of the active matrix Book — roughness (Ra/Rq), "
        "peak-to-valley, volume above the minimum, and slope statistics — into "
        "a table Book.",
        {},
        lambda args: _tool_surface_metrics(window, args),
    )
    registry.add(
        "matrix_stack",
        "Project a stack of matrix Books (same shape) into one matrix Book — "
        "max/mean/min/sum/std across frames (e.g. maximum-intensity projection).",
        {
            "books": {"type": "array", "description": "matrix Book names to stack", "required": True},
            "mode": {
                "type": "string", "required": False,
                "description": "max | mean | min | sum | std",
                "enum": ["max", "mean", "min", "sum", "std"],
            },
        },
        lambda args: _tool_matrix_stack(window, args),
    )
