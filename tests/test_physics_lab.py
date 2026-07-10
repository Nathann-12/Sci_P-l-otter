from __future__ import annotations

import numpy as np
import pytest

from analysis.physics_lab import (
    ohms_law_fit,
    pendulum_gravity,
    propagate_power_product,
    rc_time_constant,
)


def test_ohms_law_fit_recovers_resistance():
    current = np.array([-0.002, -0.001, 0.0, 0.001, 0.002])
    voltage = 220.0 * current + 0.01

    result = ohms_law_fit(current, voltage)

    assert result.resistance_ohm == pytest.approx(220.0)
    assert result.conductance_s == pytest.approx(1.0 / 220.0)
    assert result.intercept_v == pytest.approx(0.01)
    assert result.r_squared == pytest.approx(1.0)


def test_rc_time_constant_charge_curve():
    t = np.linspace(0, 5, 100)
    tau = 1.25
    y = 5.0 * (1.0 - np.exp(-t / tau))

    result = rc_time_constant(t, y, mode="charge")

    assert result.tau_s == pytest.approx(tau, rel=0.08)
    assert result.r_squared > 0.98


def test_pendulum_gravity_from_period_squared_fit():
    length = np.array([0.25, 0.5, 0.75, 1.0])
    g = 9.81
    period = 2 * np.pi * np.sqrt(length / g)

    result = pendulum_gravity(length, period)

    assert result.gravity_m_s2 == pytest.approx(g, rel=0.01)
    assert result.r_squared == pytest.approx(1.0)


def test_power_product_uncertainty_propagation():
    result = propagate_power_product(
        values=[2.0, 3.0],
        uncertainties=[0.1, 0.3],
        powers=[1.0, 2.0],
        coefficient=4.0,
    )

    assert result.value == pytest.approx(72.0)
    expected_rel = np.sqrt((0.1 / 2.0) ** 2 + (2.0 * 0.3 / 3.0) ** 2)
    assert result.relative_uncertainty == pytest.approx(expected_rel)
    assert result.uncertainty == pytest.approx(72.0 * expected_rel)
