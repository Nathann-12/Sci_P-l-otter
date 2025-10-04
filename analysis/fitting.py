from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:
    from scipy.optimize import curve_fit  # type: ignore
    from scipy import special as _scipy_special  # type: ignore
    _SCIPY_AVAILABLE = True
except Exception:  # pragma: no cover - gracefully degrade when SciPy is missing
    curve_fit = None  # type: ignore
    _scipy_special = None  # type: ignore
    _SCIPY_AVAILABLE = False


__all__ = [
    "FitError",
    "FitResult",
    "list_available_models",
    "get_model_description",
    "fit_curve",
]


class FitError(RuntimeError):
    """Raised when curve fitting fails."""


@dataclass
class FitResult:
    model: str
    params: Dict[str, float]
    errors: Dict[str, float]
    r_squared: float
    x_eval: np.ndarray
    y_eval: np.ndarray
    y_pred: np.ndarray


_MODEL_DESCRIPTIONS: Dict[str, str] = {
    "linear": "y = m * x + b",
    "polynomial": "y = a_n x^n + ... + a_0 (ปรับ degree ได้)",
    "exponential": "y = A * exp(B * x) + C",
    "power_law": "y = A * x^B + C (x>0)",
    "gaussian": "y = A * exp(-0.5 * ((x - μ)/σ)^2) + C",
    "sine": "y = A * sin(ω x + φ) + C",
    "logistic": "y = A / (1 + exp(-(x - x0)/k)) + C",
    "lorentzian": "y = A * γ^2 / ((x - x0)^2 + γ^2) + C",
    "voigt": "y = A * Voigt(x; x0, σ, γ) + C",
    "custom": "กำหนดสมการเอง เช่น A*exp(-((x-x0)/σ)**2) + B*sin(ω*x)",
}

_ALLOWED_MODELS: Tuple[str, ...] = (
    "linear",
    "polynomial",
    "exponential",
    "power_law",
    "gaussian",
    "sine",
    "logistic",
    "lorentzian",
    "voigt",
    "custom",
)

_CUSTOM_ALLOWED_FUNCS: Dict[str, Callable[[np.ndarray], np.ndarray]] = {
    name: getattr(np, name)
    for name in [
        "sin",
        "cos",
        "tan",
        "arcsin",
        "arccos",
        "arctan",
        "sinh",
        "cosh",
        "tanh",
        "exp",
        "log",
        "log10",
        "sqrt",
        "abs",
    ]
}
_CUSTOM_CONSTANTS: Dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}
_FORBIDDEN_NAMES = {
    "x",
    "np",
    "numpy",
    "math",
}
_FORBIDDEN_NAMES.update(_CUSTOM_ALLOWED_FUNCS.keys())
_FORBIDDEN_NAMES.update(_CUSTOM_CONSTANTS.keys())
_FORBIDDEN_NAMES.update({"sin", "cos", "tan", "exp", "log", "sqrt"})
_KEYWORD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOKEN_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


def list_available_models() -> List[str]:
    """Return display names for supported models."""
    return [
        "Linear",
        "Polynomial",
        "Exponential",
        "Power-Law",
        "Gaussian",
        "Sine",
        "Logistic",
        "Lorentzian",
        "Voigt",
        "Custom",
    ]


def get_model_description(model: str) -> str:
    key = _normalise_model_key(model)
    return _MODEL_DESCRIPTIONS.get(key, "")


def fit_curve(
    x: Sequence[float],
    y: Sequence[float],
    model: str,
    *,
    degree: Optional[int] = None,
    expression: Optional[str] = None,
) -> FitResult:
    """Fit a curve to the provided x/y data using the requested model."""
    if curve_fit is None and _normalise_model_key(model) not in {"linear", "polynomial"}:
        raise FitError("ต้องติดตั้ง SciPy เพื่อใช้โมเดลนี้")

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    x_arr = x_arr[mask]
    y_arr = y_arr[mask]
    if x_arr.size < 3:
        raise FitError("มีข้อมูลไม่พอสำหรับการฟิต")

    key = _normalise_model_key(model)
    if key not in _ALLOWED_MODELS:
        raise FitError(f"ไม่รู้จักโมเดล '{model}'")

    if key == "polynomial" and (degree is None or degree < 1):
        degree = 2

    if key == "polynomial":
        return _fit_polynomial(x_arr, y_arr, degree or 2)

    func, param_names, initial, bounds = _get_callable(key, x_arr, y_arr, expression)
    try:
        popt, pcov = curve_fit(
            func,
            x_arr,
            y_arr,
            p0=initial,
            bounds=bounds if bounds is not None else (-np.inf, np.inf),
            maxfev=20000,
        )
    except Exception as exc:  # pragma: no cover - SciPy runtime errors
        raise FitError(str(exc))

    y_pred = func(x_arr, *popt)
    r2 = _r_squared(y_arr, y_pred)

    if pcov is None:
        perr = np.full_like(popt, np.nan)
    else:
        diag = np.diag(pcov)
        diag = np.where(diag < 0, np.nan, diag)
        perr = np.sqrt(diag)

    params = {name: float(val) for name, val in zip(param_names, popt)}
    errors = {name: float(err) if np.isfinite(err) else float("nan") for name, err in zip(param_names, perr)}

    x_eval = np.linspace(float(x_arr.min()), float(x_arr.max()), min(600, max(200, x_arr.size * 3)))
    y_eval = func(x_eval, *popt)

    return FitResult(
        model=model,
        params=params,
        errors=errors,
        r_squared=float(r2),
        x_eval=x_eval,
        y_eval=y_eval,
        y_pred=y_pred,
    )


def _fit_polynomial(x: np.ndarray, y: np.ndarray, degree: int) -> FitResult:
    degree = int(max(1, min(degree, 12)))
    coeffs = np.polyfit(x, y, degree)
    poly = np.poly1d(coeffs)
    y_pred = poly(x)
    r2 = _r_squared(y, y_pred)
    param_names = [f"a{i}" for i in range(degree, -1, -1)]
    params = {name: float(coeff) for name, coeff in zip(param_names, coeffs)}
    errors = {name: float("nan") for name in param_names}
    x_eval = np.linspace(float(x.min()), float(x.max()), min(600, max(200, x.size * 3)))
    y_eval = poly(x_eval)
    return FitResult(
        model="Polynomial",
        params=params,
        errors=errors,
        r_squared=float(r2),
        x_eval=x_eval,
        y_eval=y_eval,
        y_pred=y_pred,
    )


def _normalise_model_key(model: str) -> str:
    key = model.strip().lower().replace(" ", "_").replace("-", "_")
    return key


def _r_squared(y_obs: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = np.sum((y_obs - y_pred) ** 2)
    ss_tot = np.sum((y_obs - np.mean(y_obs)) ** 2)
    if ss_tot == 0:
        return 1.0
    return 1.0 - ss_res / ss_tot


def _get_callable(
    key: str,
    x: np.ndarray,
    y: np.ndarray,
    expression: Optional[str],
) -> Tuple[Callable[[np.ndarray, *Tuple[float, ...]], np.ndarray], Tuple[str, ...], List[float], Optional[Tuple[Iterable[float], Iterable[float]]]]:
    if key == "linear":
        def _linear(x_arr: np.ndarray, m: float, b: float) -> np.ndarray:
            return m * x_arr + b

        m, b = _initial_linear(x, y)
        return _linear, ("m", "b"), [m, b], None

    if key == "exponential":
        def _exp(x_arr: np.ndarray, A: float, B: float, C: float) -> np.ndarray:
            return A * np.exp(B * x_arr) + C

        p0 = _initial_exponential(x, y)
        return _exp, ("A", "B", "C"), p0, None

    if key == "power_law":
        def _power(x_arr: np.ndarray, A: float, B: float, C: float) -> np.ndarray:
            x_pos = np.where(x_arr <= 0, np.nan, x_arr)
            return A * np.power(x_pos, B) + C

        p0 = _initial_power(x, y)
        lower = [0.0, -10.0, -np.inf]
        upper = [np.inf, 10.0, np.inf]
        return _power, ("A", "B", "C"), p0, (lower, upper)

    if key == "gaussian":
        def _gauss(x_arr: np.ndarray, A: float, mu: float, sigma: float, C: float) -> np.ndarray:
            sigma = np.clip(sigma, 1e-12, np.inf)
            return A * np.exp(-0.5 * ((x_arr - mu) / sigma) ** 2) + C

        p0 = _initial_gaussian(x, y)
        lower = [-np.inf, x.min(), 1e-9, -np.inf]
        upper = [np.inf, x.max(), np.inf, np.inf]
        return _gauss, ("A", "mu", "sigma", "C"), p0, (lower, upper)

    if key == "sine":
        def _sine(x_arr: np.ndarray, A: float, omega: float, phi: float, C: float) -> np.ndarray:
            return A * np.sin(omega * x_arr + phi) + C

        p0 = _initial_sine(x, y)
        return _sine, ("A", "omega", "phi", "C"), p0, None

    if key == "logistic":
        def _logistic(x_arr: np.ndarray, A: float, x0: float, k: float, C: float) -> np.ndarray:
            k = np.clip(k, 1e-12, np.inf)
            return A / (1.0 + np.exp(-(x_arr - x0) / k)) + C

        p0 = _initial_logistic(x, y)
        lower = [0.0, x.min(), 1e-9, -np.inf]
        upper = [np.inf, x.max(), np.inf, np.inf]
        return _logistic, ("A", "x0", "k", "C"), p0, (lower, upper)

    if key == "lorentzian":
        def _lorentz(x_arr: np.ndarray, A: float, x0: float, gamma: float, C: float) -> np.ndarray:
            gamma = np.clip(gamma, 1e-12, np.inf)
            return A * (gamma ** 2) / ((x_arr - x0) ** 2 + gamma ** 2) + C

        p0 = _initial_lorentzian(x, y)
        lower = [-np.inf, x.min(), 1e-9, -np.inf]
        upper = [np.inf, x.max(), np.inf, np.inf]
        return _lorentz, ("A", "x0", "gamma", "C"), p0, (lower, upper)

    if key == "voigt":
        if not _SCIPY_AVAILABLE:
            raise FitError("Voigt ต้องใช้ SciPy")

        def _voigt(x_arr: np.ndarray, A: float, x0: float, sigma: float, gamma: float, C: float) -> np.ndarray:
            sigma = np.clip(sigma, 1e-12, np.inf)
            gamma = np.clip(gamma, 1e-12, np.inf)
            z = ((x_arr - x0) + 1j * gamma) / (sigma * math.sqrt(2.0))
            profile = np.real(_scipy_special.wofz(z)) / (sigma * math.sqrt(2.0 * math.pi))
            return A * profile + C

        p0 = _initial_voigt(x, y)
        lower = [-np.inf, x.min(), 1e-9, 1e-9, -np.inf]
        upper = [np.inf, x.max(), np.inf, np.inf, np.inf]
        return _voigt, ("A", "x0", "sigma", "gamma", "C"), p0, (lower, upper)

    if key == "custom":
        if not expression:
            raise FitError("โปรดกรอกสมการสำหรับ Custom model")
        expr = expression.strip()
        param_names = _extract_param_names(expr)
        if not param_names:
            raise FitError("ไม่พบชื่อพารามิเตอร์ในสมการ")
        func = _build_custom_function(expr, param_names)
        p0 = [1.0 for _ in param_names]
        return func, tuple(param_names), p0, None

    raise FitError(f"โมเดล '{key}' ยังไม่รองรับ")


def _extract_param_names(expression: str) -> List[str]:
    tokens = set(_TOKEN_PATTERN.findall(expression))
    params: List[str] = []
    for token in tokens:
        if token in _FORBIDDEN_NAMES:
            continue
        if token in dir(np):
            continue
        if token in {"if", "else", "for", "while", "return", "lambda"}:
            continue
        if not _KEYWORD_PATTERN.match(token):
            continue
        params.append(token)
    params.sort()
    return params


def _build_custom_function(expression: str, param_names: Sequence[str]) -> Callable[[np.ndarray, *Tuple[float, ...]], np.ndarray]:
    safe_globals = {name: func for name, func in _CUSTOM_ALLOWED_FUNCS.items()}
    safe_globals.update({"np": np})
    safe_globals.update(_CUSTOM_CONSTANTS)
    code = compile(expression, "<custom_fit>", "eval")

    def _custom(x_arr: np.ndarray, *values: float) -> np.ndarray:
        local_env = {name: value for name, value in zip(param_names, values)}
        local_env["x"] = x_arr
        return np.asarray(eval(code, {"__builtins__": {}}, {**safe_globals, **local_env}), dtype=float)

    return _custom


def _initial_linear(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    m, b = np.polyfit(x, y, 1)
    return float(m), float(b)


def _initial_exponential(x: np.ndarray, y: np.ndarray) -> List[float]:
    y_min = float(np.nanmin(y))
    y_shifted = np.clip(y - y_min + 1e-9, 1e-9, np.inf)
    m, c = np.polyfit(x, np.log(y_shifted), 1)
    A = float(np.exp(c))
    B = float(m)
    C = y_min
    return [A, B, C]


def _initial_power(x: np.ndarray, y: np.ndarray) -> List[float]:
    x_pos = np.clip(x, 1e-9, np.inf)
    y_pos = np.clip(y - np.min(y) + 1e-9, 1e-9, np.inf)
    m, c = np.polyfit(np.log(x_pos), np.log(y_pos), 1)
    A = float(np.exp(c))
    B = float(m)
    C = float(np.min(y))
    return [A, B, C]


def _initial_gaussian(x: np.ndarray, y: np.ndarray) -> List[float]:
    idx = int(np.argmax(y))
    mu = float(x[idx])
    A = float(y[idx] - np.min(y))
    sigma = float((np.max(x) - np.min(x)) / 6.0) or 1.0
    C = float(np.min(y))
    return [A or 1.0, mu, abs(sigma), C]


def _initial_sine(x: np.ndarray, y: np.ndarray) -> List[float]:
    A = (float(np.max(y)) - float(np.min(y))) / 2.0 or 1.0
    y_detrended = y - np.mean(y)
    fft = np.fft.rfft(y_detrended)
    freqs = np.fft.rfftfreq(y.size, d=np.median(np.diff(np.sort(x))) or 1.0)
    idx = np.argmax(np.abs(fft[1:])) + 1 if fft.size > 1 else 1
    omega = 2 * math.pi * freqs[idx]
    return [A, float(omega or 1.0), 0.0, float(np.mean(y))]


def _initial_logistic(x: np.ndarray, y: np.ndarray) -> List[float]:
    A = float(np.max(y) - np.min(y)) or 1.0
    x0 = float(x[int(np.argmax(y))])
    k = float((np.max(x) - np.min(x)) / 4.0) or 1.0
    C = float(np.min(y))
    return [abs(A), x0, abs(k), C]


def _initial_lorentzian(x: np.ndarray, y: np.ndarray) -> List[float]:
    A = float(np.max(y) - np.min(y)) or 1.0
    x0 = float(x[int(np.argmax(y))])
    gamma = float((np.max(x) - np.min(x)) / 6.0) or 1.0
    C = float(np.min(y))
    return [A, x0, abs(gamma), C]


def _initial_voigt(x: np.ndarray, y: np.ndarray) -> List[float]:
    A = float(np.max(y) - np.min(y)) or 1.0
    x0 = float(x[int(np.argmax(y))])
    width = float((np.max(x) - np.min(x)) / 8.0) or 1.0
    sigma = width / 2.0
    gamma = width / 2.0
    C = float(np.min(y))
    return [A, x0, abs(sigma), abs(gamma), C]
