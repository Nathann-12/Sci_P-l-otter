"""Behavioral tests for analysis.gas_sensor (ROADMAP section H).

Synthetic exposure curves with known theory:
- exponential approach y(t) = Rg + (Ra-Rg)·exp(-(t-t_on)/τ)
  → t90 = τ·ln(10) ≈ 2.3026τ
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.gas_sensor import (
    GasResponse,
    analyze_response,
    baseline_value,
    calibration_curve,
    detect_gas_cycles,
    dilution_ppm,
    format_response_report,
    limit_of_detection,
)


RA, RG, TAU = 100.0, 20.0, 5.0
T_ON, T_OFF = 50.0, 150.0


def _exposure_curve(t):
    """Ra before ON; exp decay to Rg during ON; exp recovery after OFF."""
    y = np.full_like(t, RA, dtype=float)
    on = (t >= T_ON) & (t < T_OFF)
    y[on] = RG + (RA - RG) * np.exp(-(t[on] - T_ON) / TAU)
    y_off = RG + (RA - RG) * np.exp(-(T_OFF - T_ON) / TAU)  # ≈ RG
    rec = t >= T_OFF
    y[rec] = RA + (y_off - RA) * np.exp(-(t[rec] - T_OFF) / TAU)
    return y


T = np.linspace(0, 300, 6001)  # dt = 0.05 s
Y = _exposure_curve(T)


def test_baseline_value_median_before_on():
    assert baseline_value(T, Y, T_ON) == pytest.approx(RA)
    with pytest.raises(ValueError):
        baseline_value(T, Y, t_on=-1.0)  # nothing before t_on


def test_analyze_response_matches_theory():
    res = analyze_response(T, Y, T_ON, T_OFF)
    assert isinstance(res, GasResponse)
    assert res.baseline == pytest.approx(RA, rel=1e-6)
    assert res.steady == pytest.approx(RG, rel=1e-3)
    assert res.response_percent == pytest.approx((RA - RG) / RA * 100, rel=1e-2)
    assert res.sensitivity == pytest.approx(RA / RG, rel=1e-2)
    # t90 of an exponential approach = τ·ln(10)
    assert res.response_time == pytest.approx(TAU * np.log(10), rel=0.02)
    assert res.recovery_time == pytest.approx(TAU * np.log(10), rel=0.02)


def test_analyze_response_unsorted_input_is_handled():
    rng = np.random.default_rng(1)
    idx = rng.permutation(T.size)
    res = analyze_response(T[idx], Y[idx], T_ON, T_OFF)
    assert res.response_percent == pytest.approx(80.0, rel=1e-2)


def test_analyze_response_validates_window():
    with pytest.raises(ValueError):
        analyze_response(T, Y, t_on=200.0, t_off=100.0)


def test_detect_gas_cycles_finds_three_pulses():
    t = np.linspace(0, 600, 6001)
    y = np.full_like(t, 100.0)
    pulses = [(100, 150), (300, 350), (500, 550)]
    for on, off in pulses:
        mask = (t >= on) & (t <= off)
        y[mask] = 30.0  # strong drop while gas is on
    cycles = detect_gas_cycles(t, y, rel_threshold=0.05)
    assert len(cycles) == 3
    for (found_on, found_off), (true_on, true_off) in zip(cycles, pulses):
        assert found_on == pytest.approx(true_on, abs=1.0)
        assert found_off == pytest.approx(true_off, abs=1.0)


def test_detect_gas_cycles_upward_direction():
    t = np.linspace(0, 100, 1001)
    y = np.full_like(t, 10.0)
    y[(t >= 40) & (t <= 60)] = 25.0  # rising response (p-type / oxidizing)
    cycles = detect_gas_cycles(t, y)
    assert len(cycles) == 1
    assert cycles[0][0] == pytest.approx(40.0, abs=0.5)


def test_calibration_curve_linear_recovers_known_line():
    conc = np.array([10, 20, 50, 100, 200], dtype=float)
    resp = 0.4 * conc + 2.0
    fit = calibration_curve(conc, resp, model="linear")
    assert fit["slope"] == pytest.approx(0.4)
    assert fit["intercept"] == pytest.approx(2.0)
    assert fit["r_squared"] == pytest.approx(1.0)
    assert fit["predict"](300) == pytest.approx(122.0)


def test_calibration_curve_power_recovers_known_law():
    conc = np.array([1, 5, 10, 50, 100], dtype=float)
    resp = 3.0 * conc ** 0.7
    fit = calibration_curve(conc, resp, model="power")
    assert fit["a"] == pytest.approx(3.0, rel=1e-6)
    assert fit["b"] == pytest.approx(0.7, rel=1e-6)
    assert fit["r_squared"] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        calibration_curve([0.0, 1.0], [1.0, 2.0], model="power")
    with pytest.raises(ValueError):
        calibration_curve(conc, resp, model="quadratic")


def test_limit_of_detection_iupac():
    lod, loq = limit_of_detection(slope=0.4, noise_std=0.2)
    assert lod == pytest.approx(3 * 0.2 / 0.4)
    assert loq == pytest.approx(10 * 0.2 / 0.4)
    with pytest.raises(ValueError):
        limit_of_detection(slope=0.0, noise_std=0.1)


def test_dilution_ppm():
    # 2 sccm of 1000 ppm source into 100 sccm total → 20 ppm
    assert dilution_ppm(1000.0, 2.0, 100.0) == pytest.approx(20.0)
    with pytest.raises(ValueError):
        dilution_ppm(1000.0, 10.0, 5.0)  # total < gas flow
    with pytest.raises(ValueError):
        dilution_ppm(1000.0, 0.0, 5.0)


def test_format_response_report_contains_all_metrics():
    res = analyze_response(T, Y, T_ON, T_OFF)
    text = format_response_report(res)
    for key in ("Baseline", "Response", "Sensitivity", "Response time", "Recovery time"):
        assert key in text
