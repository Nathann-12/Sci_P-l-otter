from __future__ import annotations

import numpy as np

from analysis.electrochemistry import (
    cv_peak_metrics,
    ecsa_from_randles_slope,
    eis_basic_metrics,
    gcd_discharge_metrics,
    randles_sevcik_fit,
    tafel_fit,
)


def test_cv_peak_metrics_identifies_oxidation_reduction_and_delta_ep():
    potential = np.array([-0.2, 0.0, 0.25, 0.5, 0.2, -0.1])
    current = np.array([0.0, 0.2, 1.8, 0.4, -0.3, -1.2])

    metrics = cv_peak_metrics(potential, current)

    assert metrics.oxidation_peak_current == 1.8
    assert metrics.oxidation_peak_potential == 0.25
    assert metrics.reduction_peak_current == -1.2
    assert metrics.reduction_peak_potential == -0.1
    assert round(metrics.delta_ep, 3) == 0.35
    assert round(metrics.peak_current_ratio, 3) == 1.5


def test_randles_sevcik_fit_and_ecsa():
    scan_rates = np.array([0.01, 0.04, 0.09, 0.16])
    peak_current = 2.0 * np.sqrt(scan_rates) + 0.1

    fit = randles_sevcik_fit(scan_rates, peak_current)
    ecsa = ecsa_from_randles_slope(fit["slope"], n=1, diffusion_cm2_s=1e-5, concentration_mol_cm3=1e-6)

    assert round(fit["slope"], 6) == 2.0
    assert round(fit["intercept"], 6) == 0.1
    assert round(fit["r_squared"], 6) == 1.0
    assert ecsa > 0


def test_tafel_fit_returns_slope_in_mv_per_decade():
    currents = np.array([1e-6, 1e-5, 1e-4, 1e-3])
    eta = 0.12 * np.log10(currents) + 0.7

    fit = tafel_fit(eta, currents)

    assert round(fit["slope_mv_dec"], 6) == 120.0
    assert round(fit["r_squared"], 6) == 1.0
    assert fit["exchange_current_a"] > 0


def test_gcd_discharge_metrics_computes_supercapacitor_values():
    time = np.array([0.0, 1.0, 2.0, 12.0])
    voltage = np.array([0.0, 1.0, 0.8, 0.0])

    metrics = gcd_discharge_metrics(time, voltage, current_a=0.002, mass_g=0.01)

    assert metrics.discharge_time_s == 11.0
    assert metrics.voltage_window_v == 1.0
    assert round(metrics.capacitance_f, 6) == 0.022
    assert round(metrics.specific_capacitance_f_g, 6) == 2.2
    assert metrics.energy_wh_kg is not None
    assert metrics.power_w_kg is not None


def test_eis_basic_metrics_estimates_rs_and_rct():
    freq = np.array([10000.0, 1000.0, 10.0, 1.0])
    zreal = np.array([5.0, 8.0, 18.0, 25.0])
    zimag = np.array([-0.5, -5.0, -8.0, -2.0])

    metrics = eis_basic_metrics(freq, zreal, zimag)

    assert metrics.rs_ohm == 5.0
    assert metrics.zreal_at_low_freq_ohm == 25.0
    assert metrics.rct_ohm == 20.0
    assert metrics.zmod_max_ohm > metrics.zmod_min_ohm
