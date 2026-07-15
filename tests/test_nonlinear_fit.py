"""Behavioral coverage for the scientific nonlinear-fitting workflow."""
from __future__ import annotations

import numpy as np
import pytest

from processors import model_voigt, nonlinear_fit


LINEAR_CUSTOM = {
    "model_name": "custom",
    "init_params": {"a": 1.0, "b": 0.0},
    "custom_expr": "a*x+b",
    "custom_params": ["a", "b"],
}


def test_weighted_fit_accepts_absolute_uncertainty_or_inverse_variance():
    """Both public weight conventions must represent the same objective."""
    x = np.arange(6.0)
    y = 2.0 * x + 1.0
    y[-1] = 30.0  # low-confidence outlier
    uncertainty = np.array([0.1, 0.1, 0.1, 0.1, 0.1, 100.0])
    inverse_variance = 1.0 / uncertainty**2

    unweighted = nonlinear_fit(x, y, weighting="none", **LINEAR_CUSTOM)
    via_sigma = nonlinear_fit(
        x, y, sigma=uncertainty, weighting="sigma", **LINEAR_CUSTOM
    )
    via_weights = nonlinear_fit(
        x, y, sigma=inverse_variance, weighting="1/sigma^2", **LINEAR_CUSTOM
    )

    assert unweighted.success and via_sigma.success and via_weights.success
    assert unweighted.params["a"] > 4.0
    assert via_sigma.params["a"] == pytest.approx(2.0, abs=1e-4)
    assert via_sigma.params == pytest.approx(via_weights.params, rel=1e-8)
    assert via_sigma.chi2_red == pytest.approx(via_weights.chi2_red, rel=1e-8)


def test_weighted_fit_chi_square_stderr_and_confidence_band_are_consistent():
    x = np.linspace(0.0, 5.0, 12)
    y = 1.75 * x + 0.4 + np.array(
        [0.02, -0.03, 0.01, 0.04, -0.02, 0.0, 0.03, -0.01, 0.02, -0.04, 0.01, 0.0]
    )
    uncertainty = np.full(x.shape, 0.1)

    result = nonlinear_fit(
        x,
        y,
        sigma=uncertainty,
        weighting="sigma",
        calc_ci=True,
        **LINEAR_CUSTOM,
    )

    expected_chi2_red = np.sum(((y - result.yfit) / uncertainty) ** 2) / (x.size - 2)
    assert result.success
    assert result.chi2_red == pytest.approx(expected_chi2_red)
    assert all(np.isfinite(value) and value > 0 for value in result.stderr.values())
    assert result.ci95_lower is not None and result.ci95_upper is not None
    np.testing.assert_array_less(result.ci95_lower, result.ci95_upper)
    assert np.all(result.ci95_lower <= result.yfit)
    assert np.all(result.yfit <= result.ci95_upper)


def test_voigt_fit_respects_bounds_and_produces_confidence_interval():
    x = np.linspace(-5.0, 5.0, 151)
    y = model_voigt(x, 4.0, 0.3, 0.8, 0.45, 0.2)

    result = nonlinear_fit(
        x,
        y,
        "voigt",
        {"A": 3.8, "x0": 0.2, "sigma": 0.7, "gamma": 0.5, "C": 0.1},
        bounds={
            "A": (0.0, 10.0),
            "x0": (-1.0, 1.0),
            "sigma": (0.1, 2.0),
            "gamma": (0.1, 2.0),
            "C": (-1.0, 1.0),
        },
        calc_ci=True,
    )

    assert result.success
    assert result.r2 > 0.999999
    assert result.params == pytest.approx(
        {"A": 4.0, "x0": 0.3, "sigma": 0.8, "gamma": 0.45, "C": 0.2},
        rel=1e-5,
        abs=1e-7,
    )
    assert result.ci95_lower is not None and result.ci95_lower.shape == x.shape
    assert result.ci95_upper is not None and result.ci95_upper.shape == x.shape


def test_unweighted_mode_ignores_an_auxiliary_column_and_invalid_modes_fail_fast():
    x = np.arange(5.0)
    y = 3.0 * x - 2.0

    # The extra column is deliberately the wrong length. It is irrelevant when
    # weighting is None and must neither reject nor filter valid X/Y samples.
    result = nonlinear_fit(
        x, y, sigma=np.array([np.nan]), weighting="none", **LINEAR_CUSTOM
    )
    assert result.success
    assert result.params == pytest.approx({"a": 3.0, "b": -2.0})

    with pytest.raises(ValueError, match="uncertainty/weight"):
        nonlinear_fit(x, y, weighting="sigma", **LINEAR_CUSTOM)
    with pytest.raises(ValueError, match="weighting"):
        nonlinear_fit(x, y, weighting="mystery", **LINEAR_CUSTOM)
