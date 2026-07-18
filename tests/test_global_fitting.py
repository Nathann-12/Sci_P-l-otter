"""Behavioral tests for the pure simultaneous/global-fitting core."""
from __future__ import annotations

import numpy as np
import pytest

from analysis.global_fitting import (
    GlobalFitDataset,
    GlobalFitError,
    exponential_decay_model,
    gaussian_model,
    global_fit,
    voigt_model,
)


def test_global_gaussian_shares_shape_and_keeps_dataset_specific_scale_and_offset():
    x = np.linspace(-4.0, 4.0, 161)
    noise = 0.004 * np.sin(np.arange(x.size) * 0.37)
    y_a = gaussian_model(x, 3.0, 0.4, 0.8, 0.2) + noise
    y_b = gaussian_model(x, 5.0, 0.4, 0.8, -0.1) - noise

    # Exercise aligned NaN removal and stable X sorting on both datasets.
    y_a[9] = np.nan
    sigma_a = np.full(x.shape, 0.02)
    sigma_a[9] = np.nan
    datasets = [
        GlobalFitDataset(x[::-1], y_a[::-1], "sample_a", sigma=sigma_a[::-1]),
        GlobalFitDataset(x, y_b, "sample_b", sigma=np.full(x.shape, 0.02)),
    ]
    result = global_fit(
        datasets,
        "gaussian",
        shared=("center", "sigma"),
        absolute_sigma=True,
    )

    assert result.success
    assert result.parameters["center"] == pytest.approx(0.4, abs=3e-3)
    assert result.parameters["sigma"] == pytest.approx(0.8, abs=3e-3)
    assert result.parameters["sample_a.amplitude"] == pytest.approx(3.0, abs=3e-3)
    assert result.parameters["sample_b.amplitude"] == pytest.approx(5.0, abs=3e-3)
    assert result.parameters["sample_a.offset"] == pytest.approx(0.2, abs=1e-3)
    assert result.parameters["sample_b.offset"] == pytest.approx(-0.1, abs=1e-3)
    assert result.metrics.r_squared > 0.99998
    assert result.metrics.degrees_of_freedom == (x.size - 1) + x.size - 6
    assert result.covariance.shape == (6, 6)
    assert result.correlation.shape == result.covariance.shape
    assert np.all(np.isfinite(np.diag(result.covariance)))
    assert all(np.isfinite(interval).all() for interval in result.ci95.values())

    first = result.datasets[0]
    assert np.all(np.diff(first.x) >= 0)
    assert first.x.size == x.size - 1
    assert first.fitted.shape == first.x.shape
    assert first.residuals.shape == first.x.shape
    assert first.ci95_lower is not None and first.ci95_lower.shape == first.x.shape
    assert first.ci95_upper is not None and first.ci95_upper.shape == first.x.shape
    assert np.all(first.ci95_lower <= first.fitted)
    assert np.all(first.fitted <= first.ci95_upper)


def test_custom_callable_supports_shared_and_dataset_specific_parameters_with_weights():
    def affine(x, slope, intercept):
        return slope * x + intercept

    x = np.arange(8.0)
    y_a = 2.25 * x + 1.0
    y_b = 2.25 * x - 3.0
    y_b[-1] += 50.0
    weights_b = np.ones_like(x)
    weights_b[-1] = 1e-10

    result = global_fit(
        [
            GlobalFitDataset(x, y_a, "a"),
            GlobalFitDataset(x, y_b, "b", weights=weights_b),
        ],
        affine,
        parameter_names=("slope", "intercept"),
        shared=("slope",),
        initial={"slope": 1.0, "intercept": 0.0, "b.intercept": -2.0},
    )

    assert result.success
    assert result.parameter_order == ("slope", "a.intercept", "b.intercept")
    assert result.parameters["slope"] == pytest.approx(2.25, abs=2e-5)
    assert result.parameters["a.intercept"] == pytest.approx(1.0, abs=3e-5)
    assert result.parameters["b.intercept"] == pytest.approx(-3.0, abs=3e-5)
    assert result.datasets[1].weighted_residuals[-1] == pytest.approx(5e-4, rel=2e-3)


def test_fixed_shared_parameter_bounds_and_all_major_metrics_are_reported():
    x = np.linspace(0.0, 8.0, 101)
    y_a = exponential_decay_model(x, 4.0, 2.0, 0.3)
    y_b = exponential_decay_model(x, 2.0, 2.0, -0.2)

    result = global_fit(
        [(x, y_a), (x, y_b)],
        "exponential_decay",
        shared=("tau",),
        fixed={"tau": 2.0},
        bounds={"amplitude": (0.0, 10.0), "offset": (-1.0, 1.0)},
    )

    assert result.success
    assert "tau" not in result.parameter_order
    assert result.parameters["tau"] == 2.0
    assert result.stderr["tau"] == 0.0
    assert result.ci95["tau"] == (2.0, 2.0)
    assert result.parameters["dataset_1.amplitude"] == pytest.approx(4.0, rel=1e-8)
    assert result.parameters["dataset_2.amplitude"] == pytest.approx(2.0, rel=1e-8)
    assert result.metrics.r_squared > 0.999999999
    assert result.metrics.rmse < 1e-9
    assert np.isfinite(result.metrics.aic)
    assert np.isfinite(result.metrics.bic)
    assert np.isfinite(result.metrics.reduced_chi_square)


def test_voigt_builtin_and_configuration_validation():
    x = np.linspace(-5.0, 5.0, 201)
    y = voigt_model(x, 3.5, 0.2, 0.7, 0.35, 0.1)
    result = global_fit(
        [GlobalFitDataset(x, y, "v")],
        "voigt",
        initial={
            "amplitude": 3.0,
            "center": 0.0,
            "sigma": 0.6,
            "gamma": 0.4,
            "offset": 0.0,
        },
    )
    assert result.success
    assert result.datasets[0].parameters == pytest.approx(
        {"amplitude": 3.5, "center": 0.2, "sigma": 0.7, "gamma": 0.35, "offset": 0.1},
        rel=2e-6,
        abs=1e-8,
    )

    with pytest.raises(GlobalFitError, match="unique"):
        global_fit(
            [GlobalFitDataset(x, y, "same"), GlobalFitDataset(x, y, "same")],
            "gaussian",
        )
    with pytest.raises(GlobalFitError, match="at least 3"):
        global_fit([([0.0, 1.0, np.nan], [1.0, 2.0, 3.0])], "gaussian")
    with pytest.raises(GlobalFitError, match="positive"):
        global_fit(
            [GlobalFitDataset(x, y, "bad", weights=np.r_[np.ones(x.size - 1), 0.0])],
            "gaussian",
        )
    with pytest.raises(GlobalFitError, match="Unknown shared"):
        global_fit([(x, y)], "gaussian", shared=("imaginary",))
    with pytest.raises(GlobalFitError, match="parameter_names"):
        global_fit([(x, y)], lambda values, a: a * values)
