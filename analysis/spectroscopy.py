from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class PeakMetric:
    x: float
    y: float
    fwhm: float | None
    area: float


@dataclass(frozen=True)
class TaucResult:
    band_gap_ev: float
    slope: float
    intercept: float
    r_squared: float
    fit_x: np.ndarray
    fit_y: np.ndarray


def _finite_xy(x: Sequence[float], y: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    if xa.shape != ya.shape:
        raise ValueError("x and y must have the same shape")
    mask = np.isfinite(xa) & np.isfinite(ya)
    xa = xa[mask]
    ya = ya[mask]
    if xa.size < 3:
        raise ValueError("need at least three finite points")
    order = np.argsort(xa)
    return xa[order], ya[order]


def polynomial_baseline(x: Sequence[float], y: Sequence[float], degree: int = 2, quantile: float = 0.2) -> np.ndarray:
    x, y = _finite_xy(x, y)
    degree = int(degree)
    if degree < 0 or degree > 5:
        raise ValueError("degree must be between 0 and 5")
    if not 0 < float(quantile) <= 1:
        raise ValueError("quantile must be in (0, 1]")
    cutoff = np.quantile(y, float(quantile))
    mask = y <= cutoff
    if int(mask.sum()) <= degree:
        mask = np.ones_like(y, dtype=bool)
    coeff = np.polyfit(x[mask], y[mask], degree)
    return np.polyval(coeff, x)


def baseline_correct(x: Sequence[float], y: Sequence[float], degree: int = 2, quantile: float = 0.2) -> dict:
    x, y = _finite_xy(x, y)
    baseline = polynomial_baseline(x, y, degree=degree, quantile=quantile)
    corrected = y - baseline
    return {"x": x, "raw": y, "baseline": baseline, "corrected": corrected}


def normalize_spectrum(y: Sequence[float], mode: str = "max") -> np.ndarray:
    arr = np.asarray(y, dtype=float)
    if arr.size == 0:
        raise ValueError("empty spectrum")
    finite = np.isfinite(arr)
    if not finite.any():
        raise ValueError("no finite intensity values")
    result = arr.astype(float).copy()
    mode = str(mode).lower()
    if mode == "max":
        denom = np.nanmax(np.abs(result[finite]))
        if denom <= 0:
            raise ValueError("cannot max-normalize a zero spectrum")
        result[finite] = result[finite] / denom
    elif mode == "minmax":
        lo = np.nanmin(result[finite])
        hi = np.nanmax(result[finite])
        if hi == lo:
            raise ValueError("cannot minmax-normalize a constant spectrum")
        result[finite] = (result[finite] - lo) / (hi - lo)
    elif mode == "area":
        area = np.nansum(np.abs(result[finite]))
        if area <= 0:
            raise ValueError("cannot area-normalize a zero spectrum")
        result[finite] = result[finite] / area
    else:
        raise ValueError("mode must be max, minmax, or area")
    return result


def detect_spectrum_peaks(
    x: Sequence[float],
    y: Sequence[float],
    *,
    threshold_rel: float = 0.1,
    min_distance: int = 1,
) -> list[PeakMetric]:
    x, y = _finite_xy(x, y)
    if x.size < 3:
        return []
    min_distance = max(1, int(min_distance))
    threshold = float(np.nanmin(y) + threshold_rel * (np.nanmax(y) - np.nanmin(y)))
    candidates = np.where((y[1:-1] >= y[:-2]) & (y[1:-1] >= y[2:]) & (y[1:-1] >= threshold))[0] + 1
    if candidates.size == 0:
        return []
    chosen: list[int] = []
    for idx in sorted(candidates.tolist(), key=lambda i: y[i], reverse=True):
        if all(abs(idx - old) >= min_distance for old in chosen):
            chosen.append(idx)
    chosen.sort()
    return [_peak_metric(x, y, idx) for idx in chosen]


def _peak_metric(x: np.ndarray, y: np.ndarray, idx: int) -> PeakMetric:
    half = y[idx] / 2.0
    left = idx
    while left > 0 and y[left] > half:
        left -= 1
    right = idx
    while right < y.size - 1 and y[right] > half:
        right += 1
    fwhm = float(x[right] - x[left]) if right > left else None
    area = float(np.trapezoid(np.clip(y[left : right + 1], 0, None), x[left : right + 1])) if right > left else 0.0
    return PeakMetric(float(x[idx]), float(y[idx]), fwhm, area)


def raman_d_g_ratio(x: Sequence[float], y: Sequence[float], d_range=(1200.0, 1450.0), g_range=(1500.0, 1700.0)) -> dict:
    x, y = _finite_xy(x, y)
    def _max_in(window):
        lo, hi = map(float, window)
        mask = (x >= lo) & (x <= hi)
        if not mask.any():
            raise ValueError(f"no points inside range {lo:g}-{hi:g}")
        local_x = x[mask]
        local_y = y[mask]
        idx = int(np.nanargmax(local_y))
        return float(local_x[idx]), float(local_y[idx])

    d_pos, d_int = _max_in(d_range)
    g_pos, g_int = _max_in(g_range)
    if g_int == 0:
        raise ValueError("G peak intensity is zero")
    return {
        "d_position": d_pos,
        "d_intensity": d_int,
        "g_position": g_pos,
        "g_intensity": g_int,
        "id_ig": d_int / g_int,
    }


def tauc_band_gap(
    energy_ev: Sequence[float],
    absorbance: Sequence[float],
    *,
    exponent: float = 2.0,
    fit_fraction: float = 0.35,
) -> TaucResult:
    energy, absorbance = _finite_xy(energy_ev, absorbance)
    y = np.power(np.clip(absorbance * energy, 0, None), float(exponent))
    valid = np.isfinite(y) & (y > 0)
    energy = energy[valid]
    y = y[valid]
    if energy.size < 4:
        raise ValueError("need at least four positive Tauc points")
    order = np.argsort(y)
    count = max(4, int(round(float(fit_fraction) * energy.size)))
    sel = np.sort(order[-count:])
    slope, intercept = np.polyfit(energy[sel], y[sel], 1)
    if slope == 0:
        raise ValueError("Tauc fit slope is zero")
    fit_y = slope * energy[sel] + intercept
    ss_res = float(np.sum((y[sel] - fit_y) ** 2))
    ss_tot = float(np.sum((y[sel] - np.mean(y[sel])) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return TaucResult(float(-intercept / slope), float(slope), float(intercept), float(r2), energy[sel], fit_y)


def scherrer_crystallite_size(two_theta_deg: float, fwhm_deg: float, wavelength_angstrom: float = 1.5406, shape_factor: float = 0.9) -> float:
    theta = np.radians(float(two_theta_deg) / 2.0)
    beta = np.radians(float(fwhm_deg))
    if beta <= 0:
        raise ValueError("fwhm_deg must be positive")
    if wavelength_angstrom <= 0 or shape_factor <= 0:
        raise ValueError("wavelength and shape factor must be positive")
    return float(shape_factor * wavelength_angstrom / (beta * np.cos(theta)))
