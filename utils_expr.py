# -*- coding: utf-8 -*-
"""
Safe helpers for evaluating expressions y = f(x).
- Only a curated namespace is exposed
- Supports user-specified scalar parameters such as a=1.2, b=-3
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional

import numpy as np

_ALLOWED: Dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "arcsin": np.arcsin,
    "arccos": np.arccos,
    "arctan": np.arctan,
    "sinh": np.sinh,
    "cosh": np.cosh,
    "tanh": np.tanh,
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "sqrt": np.sqrt,
    "abs": np.abs,
    "floor": np.floor,
    "ceil": np.ceil,
    "min": np.minimum,
    "max": np.maximum,
    "where": np.where,
}

_FORBIDDEN_PATTERN = re.compile(r"__|import|exec|eval|open|os\\.|sys\\.")


_DEF_RESERVED = {"x", "pi", "e"}


def parse_params(param_str: str) -> Dict[str, float]:
    """Parse a comma-separated string like "a=1, b=-0.5" into a dict."""
    params: Dict[str, float] = {}
    if not param_str.strip():
        return params

    parts = [part.strip() for part in param_str.split(",")]
    for part in parts:
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"Invalid parameter format: '{part}' (expected a=1)")
        key, value = part.split("=", 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r"[a-zA-Z]\\w*", key):
            raise ValueError(f"Invalid parameter name: '{key}'")
        if key in _DEF_RESERVED:
            raise ValueError(f"Parameter name '{key}' is reserved")
        try:
            params[key] = float(value)
        except Exception as exc:
            raise ValueError(f"Parameter values must be numeric: '{part}'") from exc
    return params


def safe_eval(
    expr: str,
    x: np.ndarray,
    user_params: Dict[str, float],
    extra_locals: Optional[Dict[str, Any]] = None,
) -> np.ndarray:
    """Evaluate y = f(x) using a restricted namespace."""
    if _FORBIDDEN_PATTERN.search(expr):
        raise ValueError("Expression contains forbidden tokens (e.g. __, import, eval)")

    local_ns: Dict[str, Any] = {"x": x}
    local_ns.update(_ALLOWED)

    if extra_locals:
        for name, value in extra_locals.items():
            if name in local_ns:
                raise ValueError(f"Extra variable '{name}' would overwrite a protected name")
            local_ns[name] = value

    for key, value in user_params.items():
        if key in _DEF_RESERVED:
            raise ValueError(f"Parameter name '{key}' is reserved")
        local_ns[key] = value

    try:
        y = eval(expr, {"__builtins__": {}}, local_ns)
    except NameError as exc:
        raise ValueError(f"Unknown function or variable: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Failed to evaluate expression: {exc}") from exc

    y_arr = np.asarray(y)
    if y_arr.shape != x.shape:
        if y_arr.ndim == 0:
            y_arr = np.full_like(x, float(y_arr))
        else:
            raise ValueError("Result shape does not match x")
    return y_arr