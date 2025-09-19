# -*- coding: utf-8 -*-
"""Helper for plotting expressions onto a Matplotlib Axes."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from utils_expr import parse_params, safe_eval


def _evaluate_expression(
    expr: str,
    x: np.ndarray,
    user_params: Dict[str, float],
    aliases: Dict[str, np.ndarray],
) -> Tuple[str, np.ndarray, np.ndarray]:
    """Interpret the expression and return plotting instructions.

    Returns a tuple of (mode, x_values, y_values) where mode is one of:
    - 'plot': standard y versus x line using the returned arrays
    - 'param': parametric curve where x_values corresponds to the horizontal axis
    - 'vline': vertical line at x_values[0] (y_values ignored)
    """
    cleaned = expr.strip()
    if not cleaned:
        raise ValueError("Empty expression")

    if "=" not in cleaned:
        y = safe_eval(cleaned, x, user_params, extra_locals=aliases)
        return "plot", x, y

    lhs, rhs = cleaned.split("=", 1)
    lhs, rhs = lhs.strip().lower(), rhs.strip()
    if not rhs:
        raise ValueError(f"Equation '{expr}' missing right-hand side")

    if lhs in {"", "y", "z"}:
        y = safe_eval(rhs, x, user_params, extra_locals=aliases)
        return "plot", x, y

    if lhs == "x":
        # Evaluate RHS; detect scalar versus array to decide vertical vs parametric line.
        result = safe_eval(rhs, x, user_params, extra_locals=aliases)
        # If all values are (almost) the same, treat as vertical line.
        if np.allclose(result, result.flat[0]):
            v = float(result.flat[0])
            return "vline", np.array([v], dtype=float), np.array([], dtype=float)
        if result.shape == x.shape:
            return "param", result, x
        raise ValueError("Equation for x must yield a scalar or an array matching the domain")

    raise ValueError(f"Unsupported equation format: '{expr}'")


def plot_equations_on_axes(
    ax,
    expressions: List[str],
    x_min: float,
    x_max: float,
    n_points: int,
    params_str: str,
    y_scale: str = "linear",
    overlay: bool = True,
) -> None:
    """Plot multiple equations y = f(x) on the given axes."""
    if x_max <= x_min:
        raise ValueError("x_max must be greater than x_min")

    x = np.linspace(x_min, x_max, n_points, dtype=float)
    user_params: Dict[str, float] = parse_params(params_str)

    aliases: Dict[str, np.ndarray] = {}
    if "y" not in user_params:
        aliases["y"] = x
    if "z" not in user_params:
        aliases["z"] = x

    if not overlay:
        ax.clear()

    ax.set_yscale("log" if y_scale == "log" else "linear")

    for expr in expressions:
        mode, x_vals, y_vals = _evaluate_expression(expr, x, user_params, aliases)
        if mode == "plot":
            ax.plot(x_vals, y_vals, label=expr)
        elif mode == "param":
            ax.plot(x_vals, y_vals, label=expr)
        elif mode == "vline":
            ax.axvline(x_vals[0], label=expr)
        else:
            raise ValueError(f"Unknown plotting mode '{mode}' for expression '{expr}'")

    ax.legend(loc="best")
    ax.figure.canvas.draw_idle()