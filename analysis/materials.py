from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

K_B_EV_PER_K = 8.617333262145e-5


@dataclass(frozen=True)
class ConductivityMetrics:
    resistance_ohm: float
    resistivity_ohm_m: float
    conductivity_s_m: float
    sheet_resistance_ohm_sq: float | None
    r_squared: float


@dataclass(frozen=True)
class ArrheniusMetrics:
    activation_energy_ev: float
    prefactor: float
    slope: float
    intercept: float
    r_squared: float
    inv_temperature: np.ndarray
    fit_ln_conductivity: np.ndarray


@dataclass(frozen=True)
class ThermalMetrics:
    onset_temperature: float
    peak_temperature: float
    peak_rate: float
    final_value: float


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


def _linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float, np.ndarray]:
    slope, intercept = np.polyfit(x, y, 1)
    fit = slope * x + intercept
    ss_res = float(np.sum((y - fit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return float(slope), float(intercept), float(r2), fit


def conductivity_from_iv(
    voltage: Sequence[float],
    current: Sequence[float],
    *,
    length_m: float,
    area_m2: float,
    thickness_m: float | None = None,
) -> ConductivityMetrics:
    voltage, current = _finite_xy(voltage, current)
    if length_m <= 0 or area_m2 <= 0:
        raise ValueError("length_m and area_m2 must be positive")
    if thickness_m is not None and thickness_m <= 0:
        raise ValueError("thickness_m must be positive when provided")
    slope, _intercept, r2, _fit = _linear_fit(current, voltage)
    resistance = abs(slope)
    resistivity = resistance * float(area_m2) / float(length_m)
    if resistivity <= 0:
        raise ValueError("computed resistivity is not positive")
    conductivity = 1.0 / resistivity
    sheet = resistivity / float(thickness_m) if thickness_m else None
    return ConductivityMetrics(resistance, resistivity, conductivity, sheet, r2)


def arrhenius_activation_energy(
    temperature_k: Sequence[float],
    conductivity: Sequence[float],
) -> ArrheniusMetrics:
    temp, sigma = _finite_xy(temperature_k, conductivity)
    mask = (temp > 0) & (sigma > 0)
    temp = temp[mask]
    sigma = sigma[mask]
    if temp.size < 3:
        raise ValueError("need at least three positive temperature/conductivity points")
    x = 1.0 / temp
    y = np.log(sigma)
    slope, intercept, r2, fit = _linear_fit(x, y)
    ea_ev = -slope * K_B_EV_PER_K
    return ArrheniusMetrics(float(ea_ev), float(np.exp(intercept)), slope, intercept, r2, x, fit)


def thermal_transition_metrics(
    temperature: Sequence[float],
    value: Sequence[float],
    *,
    mode: str = "tga_loss",
    onset_fraction: float = 0.05,
) -> ThermalMetrics:
    temp, val = _finite_xy(temperature, value)
    order = np.argsort(temp)
    temp = temp[order]
    val = val[order]
    if temp.size < 4:
        raise ValueError("need at least four thermal points")
    if not 0 < float(onset_fraction) < 1:
        raise ValueError("onset_fraction must be in (0, 1)")
    derivative = np.gradient(val, temp)
    mode = str(mode).lower()
    if mode == "tga_loss":
        idx_peak = int(np.nanargmin(derivative))
        peak_rate = float(derivative[idx_peak])
        initial = float(val[0])
        final = float(val[-1])
        threshold = initial + float(onset_fraction) * (final - initial)
        crossing = np.where(val <= threshold)[0] if final < initial else np.where(val >= threshold)[0]
    elif mode == "dsc_peak":
        idx_peak = int(np.nanargmax(np.abs(derivative)))
        peak_rate = float(derivative[idx_peak])
        base = float(val[0])
        amplitude = float(val[idx_peak] - base)
        threshold = base + float(onset_fraction) * amplitude
        crossing = np.where(val >= threshold)[0] if amplitude >= 0 else np.where(val <= threshold)[0]
        final = float(val[-1])
    else:
        raise ValueError("mode must be tga_loss or dsc_peak")
    onset = float(temp[int(crossing[0])]) if crossing.size else float(temp[0])
    return ThermalMetrics(onset, float(temp[idx_peak]), peak_rate, final)


def rank_materials(
    df: pd.DataFrame,
    *,
    sample_col: str,
    metric_col: str,
    group_col: str | None = None,
    higher_is_better: bool = True,
) -> pd.DataFrame:
    if sample_col not in df.columns or metric_col not in df.columns:
        raise ValueError("sample_col and metric_col must exist")
    columns = [sample_col, metric_col] + ([group_col] if group_col else [])
    work = df[columns].copy()
    work[metric_col] = pd.to_numeric(work[metric_col], errors="coerce")
    work = work.dropna(subset=[metric_col])
    if work.empty:
        raise ValueError("no numeric metric values")
    sort_cols = [metric_col]
    ascending = [not higher_is_better]
    if group_col:
        sort_cols = [group_col, metric_col]
        ascending = [True, not higher_is_better]
    ranked = work.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)
    if group_col:
        ranked["rank"] = ranked.groupby(group_col)[metric_col].rank(
            method="dense",
            ascending=not higher_is_better,
        ).astype(int)
    else:
        ranked["rank"] = ranked[metric_col].rank(method="dense", ascending=not higher_is_better).astype(int)
    return ranked
