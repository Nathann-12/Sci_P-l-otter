from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class LinearFitResult:
    slope: float
    intercept: float
    r_squared: float
    slope_std: float
    intercept_std: float
    fit_y: np.ndarray


@dataclass(frozen=True)
class OhmLawResult:
    resistance_ohm: float
    conductance_s: float
    intercept_v: float
    r_squared: float
    fit_voltage: np.ndarray


@dataclass(frozen=True)
class RcResult:
    tau_s: float
    initial_value: float
    final_value: float
    r_squared: float
    fit_y: np.ndarray


@dataclass(frozen=True)
class PendulumResult:
    gravity_m_s2: float
    slope_s2_m: float
    intercept_s2: float
    r_squared: float
    fit_period_squared: np.ndarray


@dataclass(frozen=True)
class PropagationResult:
    value: float
    uncertainty: float
    relative_uncertainty: float


def _finite_xy(x: Sequence[float], y: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    if xa.shape != ya.shape:
        raise ValueError("x and y must have the same shape")
    mask = np.isfinite(xa) & np.isfinite(ya)
    xa = xa[mask]
    ya = ya[mask]
    if xa.size < 2:
        raise ValueError("need at least two finite points")
    return xa, ya


def linear_least_squares(x: Sequence[float], y: Sequence[float]) -> LinearFitResult:
    x, y = _finite_xy(x, y)
    if np.allclose(x, x[0]):
        raise ValueError("x values must not all be identical")
    slope, intercept = np.polyfit(x, y, 1)
    fit_y = slope * x + intercept
    residuals = y - fit_y
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    dof = max(1, x.size - 2)
    sigma2 = ss_res / dof
    sxx = float(np.sum((x - np.mean(x)) ** 2))
    slope_std = float(np.sqrt(sigma2 / sxx)) if sxx > 0 else np.nan
    intercept_std = float(np.sqrt(sigma2 * (1.0 / x.size + np.mean(x) ** 2 / sxx))) if sxx > 0 else np.nan
    return LinearFitResult(float(slope), float(intercept), float(r2), slope_std, intercept_std, fit_y)


def ohms_law_fit(current_a: Sequence[float], voltage_v: Sequence[float]) -> OhmLawResult:
    current, voltage = _finite_xy(current_a, voltage_v)
    fit = linear_least_squares(current, voltage)
    resistance = fit.slope
    if resistance == 0:
        raise ValueError("fitted resistance is zero")
    return OhmLawResult(float(resistance), float(1.0 / resistance), fit.intercept, fit.r_squared, fit.fit_y)


def rc_time_constant(time_s: Sequence[float], value: Sequence[float], mode: str = "charge") -> RcResult:
    t, y = _finite_xy(time_s, value)
    order = np.argsort(t)
    t = t[order]
    y = y[order]
    if t.size < 4:
        raise ValueError("need at least four points")
    mode = str(mode).lower()
    y0 = float(y[0])
    yinf_guess = float(np.median(y[-max(3, t.size // 10) :]))
    tau_guess = max(float((t[-1] - t[0]) / 3.0), np.finfo(float).eps)
    try:
        from scipy.optimize import curve_fit

        if mode == "charge":
            def model(tt, yinf, amp, tau):
                return yinf - amp * np.exp(-(tt - t[0]) / tau)
            p0 = [max(yinf_guess, float(np.nanmax(y))), max(yinf_guess - y0, np.finfo(float).eps), tau_guess]
        elif mode == "discharge":
            def model(tt, yinf, amp, tau):
                return yinf + amp * np.exp(-(tt - t[0]) / tau)
            p0 = [min(yinf_guess, float(np.nanmin(y))), max(y0 - yinf_guess, np.finfo(float).eps), tau_guess]
        else:
            raise ValueError("mode must be charge or discharge")
        params, _cov = curve_fit(
            model,
            t,
            y,
            p0=p0,
            bounds=([-np.inf, 0.0, np.finfo(float).eps], [np.inf, np.inf, np.inf]),
            maxfev=20000,
        )
        yinf = float(params[0])
        tau = float(params[2])
        fit_y = model(t, *params)
        ss_res = float(np.sum((y - fit_y) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
        return RcResult(tau, y0, yinf, r2, fit_y)
    except ImportError:
        yinf = yinf_guess
    except RuntimeError:
        yinf = yinf_guess

    if mode == "charge":
        norm = (yinf - y) / (yinf - y0)
    elif mode == "discharge":
        norm = (y - yinf) / (y0 - yinf)
    else:
        raise ValueError("mode must be charge or discharge")
    mask = np.isfinite(norm) & (norm > 0) & (norm < 1)
    if mask.sum() < 3:
        raise ValueError("not enough exponential-region points")
    fit = linear_least_squares(t[mask], np.log(norm[mask]))
    if fit.slope >= 0:
        raise ValueError("exponential fit did not decay")
    tau = -1.0 / fit.slope
    if mode == "charge":
        fit_y = yinf - (yinf - y0) * np.exp(-(t - t[0]) / tau)
    else:
        fit_y = yinf + (y0 - yinf) * np.exp(-(t - t[0]) / tau)
    return RcResult(float(tau), y0, yinf, fit.r_squared, fit_y)


def pendulum_gravity(length_m: Sequence[float], period_s: Sequence[float]) -> PendulumResult:
    length, period = _finite_xy(length_m, period_s)
    if np.any(length <= 0) or np.any(period <= 0):
        raise ValueError("length and period values must be positive")
    y = period ** 2
    fit = linear_least_squares(length, y)
    if fit.slope <= 0:
        raise ValueError("pendulum slope must be positive")
    g = 4.0 * np.pi ** 2 / fit.slope
    return PendulumResult(float(g), fit.slope, fit.intercept, fit.r_squared, fit.fit_y)


def propagate_power_product(
    values: Sequence[float],
    uncertainties: Sequence[float],
    powers: Sequence[float],
    coefficient: float = 1.0,
) -> PropagationResult:
    vals = np.asarray(values, dtype=float)
    uncs = np.asarray(uncertainties, dtype=float)
    pows = np.asarray(powers, dtype=float)
    if vals.shape != uncs.shape or vals.shape != pows.shape:
        raise ValueError("values, uncertainties, and powers must have the same shape")
    if vals.size == 0:
        raise ValueError("need at least one variable")
    if np.any(~np.isfinite(vals)) or np.any(~np.isfinite(uncs)) or np.any(~np.isfinite(pows)):
        raise ValueError("all inputs must be finite")
    if np.any(vals == 0):
        raise ValueError("values must be non-zero for power-product propagation")
    if np.any(uncs < 0):
        raise ValueError("uncertainties must be non-negative")
    value = float(coefficient) * float(np.prod(vals ** pows))
    rel = float(np.sqrt(np.sum((pows * uncs / vals) ** 2)))
    return PropagationResult(float(value), abs(float(value)) * rel, rel)
