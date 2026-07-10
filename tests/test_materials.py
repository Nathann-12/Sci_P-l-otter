from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.materials import (
    K_B_EV_PER_K,
    arrhenius_activation_energy,
    conductivity_from_iv,
    rank_materials,
    thermal_transition_metrics,
)


def test_conductivity_from_iv_geometry_metrics():
    current = np.array([-1e-3, 0.0, 1e-3, 2e-3])
    voltage = 100.0 * current

    metrics = conductivity_from_iv(voltage, current, length_m=0.01, area_m2=1e-6, thickness_m=1e-6)

    assert metrics.resistance_ohm == pytest.approx(100.0)
    assert metrics.resistivity_ohm_m == pytest.approx(0.01)
    assert metrics.conductivity_s_m == pytest.approx(100.0)
    assert metrics.sheet_resistance_ohm_sq == pytest.approx(10000.0)
    assert metrics.r_squared == pytest.approx(1.0)


def test_arrhenius_activation_energy_recovers_ea():
    temp = np.linspace(280.0, 420.0, 12)
    ea = 0.32
    prefactor = 2.5e4
    conductivity = prefactor * np.exp(-ea / (K_B_EV_PER_K * temp))

    metrics = arrhenius_activation_energy(temp, conductivity)

    assert metrics.activation_energy_ev == pytest.approx(ea, rel=0.01)
    assert metrics.prefactor == pytest.approx(prefactor, rel=0.03)
    assert metrics.r_squared > 0.999


def test_thermal_transition_metrics_tga_loss():
    temp = np.linspace(30, 800, 300)
    mass = 100.0 - 35.0 / (1.0 + np.exp(-(temp - 430.0) / 18.0))

    metrics = thermal_transition_metrics(temp, mass, mode="tga_loss", onset_fraction=0.05)

    assert metrics.onset_temperature < metrics.peak_temperature
    assert metrics.peak_temperature == pytest.approx(430.0, abs=8.0)
    assert metrics.peak_rate < 0
    assert metrics.final_value < 70


def test_rank_materials_global_and_grouped():
    df = pd.DataFrame({
        "sample": ["A", "B", "C", "D"],
        "composition": ["x", "x", "y", "y"],
        "conductivity": [5.0, 10.0, 3.0, 9.0],
    })

    ranked = rank_materials(df, sample_col="sample", metric_col="conductivity", higher_is_better=True)
    grouped = rank_materials(df, sample_col="sample", metric_col="conductivity", group_col="composition", higher_is_better=True)

    assert ranked.iloc[0]["sample"] == "B"
    assert grouped[grouped["sample"] == "B"]["rank"].iloc[0] == 1
    assert grouped[grouped["sample"] == "D"]["rank"].iloc[0] == 1
