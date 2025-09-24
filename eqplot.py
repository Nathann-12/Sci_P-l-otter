# -*- coding: utf-8 -*-
"""Helper for plotting expressions onto a Matplotlib Axes."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from utils_expr import parse_params, safe_eval


def _expression_error_message(expr: str, exc: Exception) -> str:
    reason = str(exc)
    hint = ''
    lowered = reason.lower()
    if 'unknown function or variable' in lowered:
        hint = ' Check the spelling of variables or parameters, or define them in the parameter list.'
    elif 'math domain error' in lowered:
        hint = ' Ensure the expression stays within the valid domain (e.g. log(x) requires x > 0).'
    elif 'result shape does not match' in lowered or 'surface does not match' in lowered:
        hint = ' The expression must return the same number of points as the generated X values.'
    elif 'invalid parameter' in lowered or 'parameter name' in lowered:
        hint = ' Parameters must use the format name=value with unique names.'
    message = f"Failed to plot expression '{expr}': {reason}"
    if hint:
        message = f"{message} Hint:{hint}"
    return message


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
) -> List[Dict[str, Any]]:
    """Plot multiple equations y = f(x) and return layer metadata."""
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

    layer_infos: List[Dict[str, Any]] = []
    for expr in expressions:
        try:
            mode, x_vals, y_vals = _evaluate_expression(expr, x, user_params, aliases)
            artists: List[Any] = []
            if mode in {"plot", "param"}:
                artists = list(ax.plot(x_vals, y_vals, label=expr))
            elif mode == "vline":
                artists = [ax.axvline(x_vals[0], label=expr)]
            else:
                raise ValueError(f"Unknown plotting mode '{mode}' for expression '{expr}'")

            style_kwargs: Dict[str, Any] = {}
            if artists:
                try:
                    color = artists[0].get_color()
                    style_kwargs['color'] = color
                except Exception:
                    pass

            layer_infos.append({
                'label': expr,
                'artists': artists,
                'style': 'line',
                'style_kwargs': style_kwargs,
            })
        except Exception as exc:
            raise ValueError(_expression_error_message(expr, exc)) from exc

    if any(info.get('artists') for info in layer_infos):
        ax.legend(loc="best")

    ax.figure.canvas.draw_idle()
    return layer_infos
