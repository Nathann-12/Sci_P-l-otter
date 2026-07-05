"""Gas-sensor response analysis (ROADMAP section H — the flagship module).

Pure numpy/pandas functions, no Qt and no hardware dependency, so the whole
suite is unit-testable. Conventions follow chemiresistive (MOS) gas-sensor
practice:

- ``Ra``  baseline resistance (before exposure)
- ``Rg``  steady resistance during gas exposure
- response %      = |Ra - Rg| / Ra * 100
- sensitivity     = max(Ra, Rg) / min(Ra, Rg)   (always >= 1)
- response time   = t90: time from gas ON until 90% of the full change
- recovery time   = t90: time from gas OFF until 90% recovered toward Ra
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np


def _as_xy(t, y) -> Tuple[np.ndarray, np.ndarray]:
    ta = np.asarray(t, dtype=float).ravel()
    ya = np.asarray(y, dtype=float).ravel()
    if ta.size != ya.size:
        raise ValueError("t and y must be the same length")
    if ta.size < 3:
        raise ValueError("need at least 3 samples")
    finite = np.isfinite(ta) & np.isfinite(ya)
    ta, ya = ta[finite], ya[finite]
    if ta.size < 3:
        raise ValueError("need at least 3 finite samples")
    order = np.argsort(ta, kind="stable")
    return ta[order], ya[order]


def baseline_value(t, y, t_on: float, window: Optional[float] = None) -> float:
    """Median signal before gas ON (``Ra``).

    ``window``: only use the last ``window`` time-units before ``t_on``
    (None = everything before ``t_on``).
    """
    ta, ya = _as_xy(t, y)
    mask = ta < t_on
    if window is not None:
        mask &= ta >= (t_on - window)
    if not mask.any():
        raise ValueError("no samples before gas-ON time (t_on)")
    return float(np.median(ya[mask]))


def _first_crossing(ta: np.ndarray, ya: np.ndarray, t_start: float, target: float,
                    rising: bool) -> Optional[float]:
    """Linear-interpolated time after ``t_start`` where y crosses ``target``."""
    seg = ta >= t_start
    ts, ys = ta[seg], ya[seg]
    if ts.size < 2:
        return None
    hit = ys >= target if rising else ys <= target
    if not hit.any():
        return None
    j = int(np.argmax(hit))
    if j == 0:
        return float(ts[0])
    y0, y1 = ys[j - 1], ys[j]
    if y1 == y0:
        return float(ts[j])
    frac = (target - y0) / (y1 - y0)
    return float(ts[j - 1] + frac * (ts[j] - ts[j - 1]))


@dataclass
class GasResponse:
    """ผลวิเคราะห์การตอบสนองต่อแก๊สหนึ่งรอบ (ON→OFF)"""
    t_on: float
    t_off: float
    baseline: float           # Ra
    steady: float             # Rg
    response_percent: float
    sensitivity: float
    response_time: Optional[float]   # t90 หลังเปิดแก๊ส (None = ไปไม่ถึง 90%)
    recovery_time: Optional[float]   # t90 หลังปิดแก๊ส (None = ฟื้นไม่ถึง 90%)


def analyze_response(t, y, t_on: float, t_off: float,
                     baseline_window: Optional[float] = None) -> GasResponse:
    """Full response analysis of one exposure cycle.

    ``Rg`` is the median of the last 25% of the exposure window (steady part).
    Times are t90 with linear interpolation at the crossing.
    """
    ta, ya = _as_xy(t, y)
    if not (t_on < t_off):
        raise ValueError("t_on must be before t_off")

    ra = baseline_value(ta, ya, t_on, window=baseline_window)
    exp_mask = (ta >= t_on) & (ta <= t_off)
    if exp_mask.sum() < 2:
        raise ValueError("exposure window contains fewer than 2 samples")
    exp_t, exp_y = ta[exp_mask], ya[exp_mask]
    tail_start = exp_t[0] + 0.75 * (exp_t[-1] - exp_t[0])
    tail = exp_y[exp_t >= tail_start]
    rg = float(np.median(tail if tail.size else exp_y[-max(1, exp_y.size // 4):]))

    if ra == 0:
        raise ValueError("baseline (Ra) is zero — response % undefined")
    delta = rg - ra
    response_percent = abs(delta) / abs(ra) * 100.0
    lo, hi = (min(ra, rg), max(ra, rg))
    sensitivity = float(hi / lo) if lo > 0 else float("inf")

    # response t90: cross Ra + 0.9*delta moving toward Rg
    target_on = ra + 0.9 * delta
    tc = _first_crossing(ta, ya, t_on, target_on, rising=delta > 0)
    response_time = None if tc is None else max(0.0, tc - t_on)

    # recovery t90: from the value at gas-OFF, recover 90% back toward Ra
    y_off = float(np.interp(t_off, ta, ya))
    target_off = y_off + 0.9 * (ra - y_off)
    tr = _first_crossing(ta, ya, t_off, target_off, rising=ra > y_off)
    recovery_time = None if tr is None else max(0.0, tr - t_off)

    return GasResponse(
        t_on=float(t_on), t_off=float(t_off),
        baseline=float(ra), steady=rg,
        response_percent=float(response_percent),
        sensitivity=sensitivity,
        response_time=response_time,
        recovery_time=recovery_time,
    )


def detect_gas_cycles(t, y, rel_threshold: float = 0.05,
                      min_points: int = 3) -> List[Tuple[float, float]]:
    """Auto-detect gas ON/OFF windows.

    Baseline = global median (valid when exposure duty cycle < ~50%).
    A cycle is a contiguous run (>= min_points) where the signal deviates
    from baseline by more than ``rel_threshold`` (fraction) in the dominant
    excursion direction. Returns [(t_start, t_end), ...].
    """
    ta, ya = _as_xy(t, y)
    base = float(np.median(ya))
    if base == 0:
        scale = float(np.max(np.abs(ya))) or 1.0
    else:
        scale = abs(base)
    dev = ya - base
    # dominant direction = sign of the largest excursion
    direction = 1.0 if abs(np.max(dev)) >= abs(np.min(dev)) else -1.0
    active = (dev * direction) > rel_threshold * scale

    cycles: List[Tuple[float, float]] = []
    start_idx: Optional[int] = None
    for i, flag in enumerate(active):
        if flag and start_idx is None:
            start_idx = i
        elif not flag and start_idx is not None:
            if i - start_idx >= min_points:
                cycles.append((float(ta[start_idx]), float(ta[i - 1])))
            start_idx = None
    if start_idx is not None and ta.size - start_idx >= min_points:
        cycles.append((float(ta[start_idx]), float(ta[-1])))
    return cycles


def calibration_curve(concentrations: Sequence[float], responses: Sequence[float],
                      model: str = "linear") -> dict:
    """Fit a concentration→response calibration curve.

    ``linear``: response = slope*conc + intercept
    ``power`` : response = a * conc**b   (fit in log-log space; needs > 0 data)
    Returns {"model", "slope"/"a", "intercept"/"b", "r_squared", "predict"}.
    """
    c = np.asarray(concentrations, dtype=float).ravel()
    r = np.asarray(responses, dtype=float).ravel()
    if c.size != r.size:
        raise ValueError("concentrations and responses must be the same length")
    finite = np.isfinite(c) & np.isfinite(r)
    c, r = c[finite], r[finite]
    if c.size < 2:
        raise ValueError("need at least 2 calibration points")

    def _r2(y_obs, y_fit) -> float:
        ss_res = float(np.sum((y_obs - y_fit) ** 2))
        ss_tot = float(np.sum((y_obs - np.mean(y_obs)) ** 2))
        return 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot

    if model == "linear":
        slope, intercept = np.polyfit(c, r, 1)
        fit = slope * c + intercept
        return {
            "model": "linear",
            "slope": float(slope),
            "intercept": float(intercept),
            "r_squared": _r2(r, fit),
            "predict": lambda x, s=float(slope), b=float(intercept): s * np.asarray(x, float) + b,
        }
    if model == "power":
        if np.any(c <= 0) or np.any(r <= 0):
            raise ValueError("power model needs positive concentrations and responses")
        b, log_a = np.polyfit(np.log(c), np.log(r), 1)
        a = float(np.exp(log_a))
        fit = a * c ** b
        return {
            "model": "power",
            "a": a,
            "b": float(b),
            "r_squared": _r2(r, fit),
            "predict": lambda x, a_=a, b_=float(b): a_ * np.asarray(x, float) ** b_,
        }
    raise ValueError(f"unknown calibration model: {model!r} (use 'linear' or 'power')")


def limit_of_detection(slope: float, noise_std: float) -> Tuple[float, float]:
    """(LOD, LOQ) = (3σ/|slope|, 10σ/|slope|) — IUPAC convention."""
    if slope == 0:
        raise ValueError("slope is zero — LOD undefined")
    if noise_std < 0:
        raise ValueError("noise_std must be >= 0")
    return 3.0 * noise_std / abs(slope), 10.0 * noise_std / abs(slope)


def dilution_ppm(source_ppm: float, flow_gas: float, flow_total: float) -> float:
    """Concentration after dilution: (source_ppm × flow_gas) / flow_total.

    Flows in any consistent unit (e.g. sccm). ``flow_total`` is the combined
    flow (gas + diluent) and must be >= flow_gas > 0.
    """
    if flow_gas <= 0 or flow_total <= 0:
        raise ValueError("flows must be > 0")
    if flow_total < flow_gas:
        raise ValueError("flow_total must be >= flow_gas")
    if source_ppm < 0:
        raise ValueError("source_ppm must be >= 0")
    return float(source_ppm) * float(flow_gas) / float(flow_total)


def format_response_report(res: GasResponse) -> str:
    """Human-readable (Thai) report for message boxes / logs."""
    def _fmt_t(v: Optional[float]) -> str:
        return "ไปไม่ถึง 90%" if v is None else f"{v:.4g} s"

    return "\n".join([
        f"ช่วงเปิดแก๊ส: {res.t_on:.6g} → {res.t_off:.6g}",
        f"Baseline (Ra): {res.baseline:.6g}",
        f"ค่าคงตัวช่วงแก๊ส (Rg): {res.steady:.6g}",
        f"Response: {res.response_percent:.4g} %",
        f"Sensitivity (Ra/Rg หรือ Rg/Ra): {res.sensitivity:.4g}",
        f"Response time (t90): {_fmt_t(res.response_time)}",
        f"Recovery time (t90): {_fmt_t(res.recovery_time)}",
    ])
