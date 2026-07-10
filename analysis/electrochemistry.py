"""Electrochemistry analysis helpers.

Pure numpy functions for CV, Tafel, GCD/supercapacitor, and EIS workflows.
UI code lives in ``main_window_electrochemistry_mixin.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np


def _paired_xy(x, y, *, min_points: int = 2) -> Tuple[np.ndarray, np.ndarray]:
    xa = np.asarray(x, dtype=float).ravel()
    ya = np.asarray(y, dtype=float).ravel()
    if xa.size != ya.size:
        raise ValueError("x and y must have the same length")
    finite = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[finite], ya[finite]
    if xa.size < min_points:
        raise ValueError(f"need at least {min_points} finite points")
    return xa, ya


def _r_squared(y_obs: np.ndarray, y_fit: np.ndarray) -> float:
    ss_res = float(np.sum((y_obs - y_fit) ** 2))
    ss_tot = float(np.sum((y_obs - np.mean(y_obs)) ** 2))
    return 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot


@dataclass(frozen=True)
class CvPeakMetrics:
    oxidation_peak_current: float
    oxidation_peak_potential: float
    reduction_peak_current: float
    reduction_peak_potential: float
    delta_ep: float
    peak_current_ratio: float


def cv_peak_metrics(potential, current) -> CvPeakMetrics:
    """Return simple CV oxidation/reduction peak metrics.

    Oxidation is the maximum current; reduction is the minimum current. This is
    intentionally conservative and works for a first production pass even when
    the scan contains a single cycle.
    """
    e, i = _paired_xy(potential, current, min_points=3)
    ox_idx = int(np.argmax(i))
    red_idx = int(np.argmin(i))
    red_i = float(i[red_idx])
    ox_i = float(i[ox_idx])
    ratio = float(abs(ox_i / red_i)) if red_i != 0 else float("inf")
    return CvPeakMetrics(
        oxidation_peak_current=ox_i,
        oxidation_peak_potential=float(e[ox_idx]),
        reduction_peak_current=red_i,
        reduction_peak_potential=float(e[red_idx]),
        delta_ep=abs(float(e[ox_idx] - e[red_idx])),
        peak_current_ratio=ratio,
    )


def randles_sevcik_fit(scan_rates: Sequence[float], peak_currents: Sequence[float]) -> dict:
    """Fit peak current against sqrt(scan rate)."""
    rates, currents = _paired_xy(scan_rates, peak_currents, min_points=2)
    if np.any(rates < 0):
        raise ValueError("scan rates must be >= 0")
    x = np.sqrt(rates)
    slope, intercept = np.polyfit(x, currents, 1)
    fit = slope * x + intercept
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": _r_squared(currents, fit),
        "x_sqrt_scan_rate": x,
        "fit": fit,
    }


def ecsa_from_randles_slope(
    slope: float,
    *,
    n: float = 1.0,
    diffusion_cm2_s: float = 1e-5,
    concentration_mol_cm3: float = 1e-6,
    temperature_k: float = 298.15,
) -> float:
    """Estimate electrochemically active surface area from Randles-Sevcik.

    At 298 K: ip = 2.69e5 n^(3/2) A D^(1/2) C v^(1/2). A temperature
    correction is included as sqrt(298.15 / T).
    """
    if n <= 0 or diffusion_cm2_s <= 0 or concentration_mol_cm3 <= 0 or temperature_k <= 0:
        raise ValueError("n, diffusion, concentration, and temperature must be > 0")
    coefficient = (
        2.69e5
        * (n ** 1.5)
        * np.sqrt(diffusion_cm2_s)
        * concentration_mol_cm3
        * np.sqrt(298.15 / temperature_k)
    )
    if coefficient == 0:
        raise ValueError("Randles-Sevcik coefficient is zero")
    return float(abs(slope) / coefficient)


def tafel_fit(overpotential_v, current_a) -> dict:
    """Fit eta = slope * log10(|i|) + intercept."""
    eta, current = _paired_xy(overpotential_v, current_a, min_points=3)
    mag = np.abs(current)
    mask = mag > 0
    eta, mag = eta[mask], mag[mask]
    if eta.size < 3:
        raise ValueError("need at least 3 non-zero current points")
    log_i = np.log10(mag)
    slope, intercept = np.polyfit(log_i, eta, 1)
    fit = slope * log_i + intercept
    exchange_current = 10 ** (-intercept / slope) if slope != 0 else float("nan")
    return {
        "slope_v_dec": float(slope),
        "slope_mv_dec": float(slope * 1000.0),
        "intercept_v": float(intercept),
        "exchange_current_a": float(exchange_current),
        "r_squared": _r_squared(eta, fit),
        "log_current": log_i,
        "fit": fit,
    }


@dataclass(frozen=True)
class GcdMetrics:
    discharge_time_s: float
    voltage_window_v: float
    capacitance_f: float
    specific_capacitance_f_g: Optional[float]
    energy_wh_kg: Optional[float]
    power_w_kg: Optional[float]


def gcd_discharge_metrics(time_s, voltage_v, *, current_a: float, mass_g: Optional[float] = None) -> GcdMetrics:
    """Estimate GCD discharge capacitance and optional gravimetric metrics."""
    t, v = _paired_xy(time_s, voltage_v, min_points=3)
    if current_a == 0:
        raise ValueError("current must be non-zero")
    peak_idx = int(np.argmax(v))
    td, vd = t[peak_idx:], v[peak_idx:]
    if td.size < 2:
        raise ValueError("not enough discharge points after voltage maximum")
    dt = float(td[-1] - td[0])
    dv = float(vd[0] - vd[-1])
    if dt <= 0 or dv <= 0:
        raise ValueError("discharge segment must have positive time and voltage drop")
    capacitance = abs(float(current_a)) * dt / dv
    specific = None
    energy = None
    power = None
    if mass_g is not None and mass_g > 0:
        specific = capacitance / float(mass_g)
        energy = 0.5 * specific * (dv ** 2) / 3.6
        power = energy * 3600.0 / dt
    return GcdMetrics(
        discharge_time_s=dt,
        voltage_window_v=dv,
        capacitance_f=float(capacitance),
        specific_capacitance_f_g=specific,
        energy_wh_kg=energy,
        power_w_kg=power,
    )


@dataclass(frozen=True)
class EisMetrics:
    rs_ohm: float
    rct_ohm: float
    zreal_at_low_freq_ohm: float
    zmod_min_ohm: float
    zmod_max_ohm: float


def eis_basic_metrics(frequency_hz, zreal_ohm, zimag_ohm) -> EisMetrics:
    """Return first-pass EIS metrics from Nyquist/Bode data."""
    freq, zr = _paired_xy(frequency_hz, zreal_ohm, min_points=2)
    _freq2, zi = _paired_xy(frequency_hz, zimag_ohm, min_points=2)
    n = min(freq.size, zr.size, zi.size)
    freq, zr, zi = freq[:n], zr[:n], zi[:n]
    rs = float(np.min(zr))
    low_idx = int(np.argmin(freq))
    low_zr = float(zr[low_idx])
    rct = max(0.0, low_zr - rs)
    zmod = np.sqrt(zr ** 2 + zi ** 2)
    return EisMetrics(
        rs_ohm=rs,
        rct_ohm=float(rct),
        zreal_at_low_freq_ohm=low_zr,
        zmod_min_ohm=float(np.min(zmod)),
        zmod_max_ohm=float(np.max(zmod)),
    )
