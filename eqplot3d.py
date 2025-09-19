# -*- coding: utf-8 -*-
"""Helpers for plotting 3D equation surfaces."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from matplotlib.lines import Line2D

from utils_expr import parse_params, safe_eval

_MAX_DISPLAY_SAMPLES = 140  # target max samples per axis when rendering


def _surface_error_message(expr: str, exc: Exception) -> str:
    reason = str(exc)
    hint = ''
    lowered = reason.lower()
    if 'unknown function or variable' in lowered:
        hint = ' Check the spelling of variables or parameters, or define them in the parameter list.'
    elif 'math domain error' in lowered:
        hint = ' Ensure the expression stays within the valid domain (e.g. sqrt expects non-negative inputs).'
    elif 'meshgrid' in lowered or 'does not match' in lowered:
        hint = ' The surface must evaluate to the same shape as the generated X/Y grid.'
    elif 'empty expression' in lowered:
        hint = ' Provide an equation such as z = sin(x) * cos(y).'
    message = f"Failed to plot surface '{expr}': {reason}"
    if hint:
        message = f"{message} Hint:{hint}"
    return message


def _normalize_surface_expression(expr: str) -> str:
    cleaned = expr.strip()
    if not cleaned:
        raise ValueError("Empty expression")
    if "=" not in cleaned:
        return cleaned
    lhs, rhs = cleaned.split("=", 1)
    lhs, rhs = lhs.strip().lower(), rhs.strip()
    if lhs in {"", "z"}:
        if not rhs:
            raise ValueError(f"Equation '{expr}' missing right-hand side")
        return rhs
    raise ValueError(f"รองรับเฉพาะสมการรูป z = f(x, y): '{expr}'")


def _downsample_step(length: int, target: int) -> int:
    if length <= target:
        return 1
    return max(int(np.ceil(length / target)), 1)


def plot_surfaces_on_axes(
    ax,
    expressions: List[str],
    x_min: float,
    x_max: float,
    n_points: int,
    y_min: float,
    y_max: float,
    n_y_points: int,
    params_str: str,
    wireframe: bool = False,
    overlay: bool = True,
) -> None:
    """Plot one or more surfaces z = f(x, y) on a Matplotlib 3D axes."""
    if x_max <= x_min:
        raise ValueError("x_max must be greater than x_min")
    if y_max <= y_min:
        raise ValueError("y_max must be greater than y_min")
    if n_points < 2 or n_y_points < 2:
        raise ValueError("Number of points for X and Y must be at least 2")

    user_params: Dict[str, float] = parse_params(params_str)

    x_full = np.linspace(x_min, x_max, n_points, dtype=float)
    y_full = np.linspace(y_min, y_max, n_y_points, dtype=float)
    X_full, Y_full = np.meshgrid(x_full, y_full)

    if not overlay:
        ax.cla()

    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")

    handles: List[Line2D] = []
    for expr in expressions:
        try:
            rhs = _normalize_surface_expression(expr)
            Z_full = safe_eval(rhs, X_full, user_params, extra_locals={"y": Y_full})
            if Z_full.shape != X_full.shape:
                raise ValueError("Resulting surface does not match the generated meshgrid")

            step_x = _downsample_step(Z_full.shape[1], _MAX_DISPLAY_SAMPLES)
            step_y = _downsample_step(Z_full.shape[0], _MAX_DISPLAY_SAMPLES)
            X = X_full[::step_y, ::step_x]
            Y = Y_full[::step_y, ::step_x]
            Z = Z_full[::step_y, ::step_x]

            try:
                color = ax._get_lines.get_next_color()
            except Exception:
                color = None
            if color is None:
                color = "C0"

            if wireframe:
                artist = ax.plot_wireframe(
                    X,
                    Y,
                    Z,
                    color=color,
                    linewidth=0.8,
                )
            else:
                artist = ax.plot_surface(
                    X,
                    Y,
                    Z,
                    alpha=0.8,
                    color=color,
                    antialiased=False,
                )

            handles.append(Line2D([0], [0], color=color, label=expr))
        except Exception as exc:
            raise ValueError(_surface_error_message(expr, exc)) from exc

    if handles:
        ax.legend(handles=handles, loc="best")

    ax.figure.canvas.draw_idle()