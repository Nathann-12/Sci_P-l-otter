"""Behavioral tests for baseline, detection, simultaneous peak fit and batch output."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.peak_analysis import (
    PeakAnalysisError,
    analyze_peaks,
    analyze_peaks_batch,
    detect_peaks,
    estimate_baseline,
    gaussian_peak,
    lorentzian_peak,
    voigt_peak,
)


def test_two_gaussian_peaks_fit_simultaneously_over_a_linear_baseline():
    x = np.linspace(0.0, 10.0, 401)
    baseline = 0.1 * x + 0.5
    y = (
        baseline
        + gaussian_peak(x, 3.0, 3.0, 0.35)
        + gaussian_peak(x, 2.0, 7.0, 0.55)
        + 0.002 * np.sin(np.arange(x.size) * 0.51)
    )

    result = analyze_peaks(
        x,
        y,
        model="gaussian",
        baseline="linear",
        prominence=0.25,
        distance=80,
    )

    assert result.success
    assert result.peak_count == 2
    assert [peak.center for peak in result.peaks] == pytest.approx([3.0, 7.0], abs=2e-3)
    assert [peak.amplitude for peak in result.peaks] == pytest.approx([3.0, 2.0], abs=3e-3)
    assert [peak.fwhm for peak in result.peaks] == pytest.approx(
        [2.0 * np.sqrt(2.0 * np.log(2.0)) * 0.35, 2.0 * np.sqrt(2.0 * np.log(2.0)) * 0.55],
        rel=3e-3,
    )
    assert [peak.area for peak in result.peaks] == pytest.approx(
        [3.0 * 0.35 * np.sqrt(2.0 * np.pi), 2.0 * 0.55 * np.sqrt(2.0 * np.pi)],
        rel=3e-3,
    )
    assert result.metrics.r_squared > 0.99999
    assert result.covariance.shape == (6, 6)
    assert result.fitted.shape == x.shape
    assert result.baseline.shape == x.shape
    assert result.residuals.shape == x.shape
    assert result.ci95_lower is not None and result.ci95_lower.shape == x.shape
    assert result.ci95_upper is not None and result.ci95_upper.shape == x.shape
    assert np.all(result.ci95_lower <= result.fitted)
    assert np.all(result.fitted <= result.ci95_upper)

    summary = result.summary
    assert list(summary["peak"]) == [1, 2]
    assert {"center", "height", "amplitude", "fwhm", "area", "rmse"}.issubset(summary)
    assert summary["success"].all()
    for peak in result.peaks:
        assert peak.center_ci95[0] <= peak.center <= peak.center_ci95[1]
        assert peak.area_ci95[0] <= peak.area <= peak.area_ci95[1]


@pytest.mark.parametrize(
    ("model", "function", "parameters", "expected_fwhm"),
    [
        (
            "gaussian",
            gaussian_peak,
            {"amplitude": 3.0, "center": 0.2, "sigma": 0.6},
            2.0 * np.sqrt(2.0 * np.log(2.0)) * 0.6,
        ),
        (
            "lorentzian",
            lorentzian_peak,
            {"amplitude": 3.0, "center": 0.2, "gamma": 0.6},
            1.2,
        ),
        (
            "voigt",
            voigt_peak,
            {"amplitude": 3.0, "center": 0.2, "sigma": 0.5, "gamma": 0.25},
            0.5346 * 0.5
            + np.sqrt(0.2166 * 0.5**2 + (2.0 * np.sqrt(2.0 * np.log(2.0)) * 0.5) ** 2),
        ),
    ],
)
def test_supported_peak_profiles_recover_parameters_and_analytic_width(
    model, function, parameters, expected_fwhm
):
    x = np.linspace(-10.0, 10.0, 801)
    y = function(x, **parameters)
    peak_index = int(np.argmin(np.abs(x - parameters["center"])))

    result = analyze_peaks(
        x,
        y,
        model=model,
        baseline="none",
        peak_indices=[peak_index],
        bounds={"center": (-1.0, 1.0)},
    )

    assert result.success
    assert result.metrics.r_squared > 0.999999999
    assert result.peaks[0].parameters == pytest.approx(parameters, rel=2e-6, abs=1e-8)
    assert result.peaks[0].fwhm == pytest.approx(expected_fwhm, rel=2e-6)
    assert result.peaks[0].height == pytest.approx(parameters["amplitude"], rel=2e-6)


def test_negative_peak_direction_weights_nan_filtering_and_sorted_x():
    x = np.linspace(-5.0, 5.0, 301)
    y = 1.2 - gaussian_peak(x, 2.4, -0.35, 0.45)
    y[15] = np.nan
    weights = np.ones_like(x)
    weights[15] = np.nan
    shuffled = np.arange(x.size)[::-1]

    result = analyze_peaks(
        x[shuffled],
        y[shuffled],
        model="gaussian",
        baseline="constant",
        direction="negative",
        prominence=0.3,
        weights=weights[shuffled],
    )

    assert result.success
    assert result.peak_count == 1
    assert result.peaks[0].center == pytest.approx(-0.35, abs=2e-3)
    assert result.peaks[0].amplitude == pytest.approx(-2.4, abs=3e-3)
    assert np.all(np.diff(result.x) >= 0)
    assert result.x.size == x.size - 1
    assert np.all(np.isfinite(result.weighted_residuals))


def test_detection_baselines_empty_result_and_input_validation():
    x = np.linspace(0.0, 20.0, 300)
    true_baseline = 0.03 * x + 0.4 + 0.001 * (x - 10.0) ** 2
    y = true_baseline + gaussian_peak(x, 2.0, 9.0, 0.5)

    detected = detect_peaks(x, y, baseline="als", prominence=0.3, als_lambda=2e5)
    assert detected.size == 1
    assert x[detected[0]] == pytest.approx(9.0, abs=0.08)
    als = estimate_baseline(x, y, "als", als_lambda=2e5)
    assert als.shape == x.shape
    assert np.all(np.isfinite(als))
    assert np.median(np.abs(als - true_baseline)) < 0.12

    no_peak = analyze_peaks(x, true_baseline, baseline="linear", prominence=10.0)
    assert no_peak.success
    assert no_peak.message == "No peaks detected"
    assert no_peak.peak_count == 0
    assert no_peak.summary.empty
    assert np.allclose(no_peak.fitted, no_peak.baseline)

    with pytest.raises(PeakAnalysisError, match="At least 7"):
        analyze_peaks([0, 1, 2, 3, np.nan, np.nan], [1, 2, 3, 4, 5, 6])
    with pytest.raises(PeakAnalysisError, match="positive"):
        analyze_peaks(x, y, weights=np.r_[np.ones(x.size - 1), 0.0])
    with pytest.raises(PeakAnalysisError, match="outside"):
        analyze_peaks(x, y, peak_indices=[999])
    with pytest.raises(PeakAnalysisError, match="Unknown baseline"):
        analyze_peaks(x, y, baseline="magic")
    # A physical width (sigma/gamma/tau) must never be allowed to go negative.
    with pytest.raises(PeakAnalysisError, match="negative"):
        analyze_peaks(x, y, peak_indices=[125], bounds={"peak0.sigma": (-1.0, 2.0)})
    with pytest.raises(PeakAnalysisError, match="width must be positive"):
        analyze_peaks(x, y, width=-3.0)


def test_batch_summary_is_stable_and_can_continue_after_one_bad_column():
    x = np.linspace(-5.0, 5.0, 251)
    frame = pd.DataFrame(
        {
            "time": x,
            "sensor_a": gaussian_peak(x, 2.0, -1.0, 0.4),
            "sensor_b": lorentzian_peak(x, 3.0, 1.5, 0.5),
            "bad": ["not numeric"] * x.size,
        }
    )

    # A common Gaussian model is intentional here: the batch contract concerns
    # robust traversal and summaries, not model selection per column.
    batch = analyze_peaks_batch(
        frame,
        "time",
        ["sensor_a", "sensor_b", "bad"],
        baseline="none",
        prominence=0.2,
        continue_on_error=True,
    )

    assert set(batch.results) == {"sensor_a", "sensor_b"}
    assert set(batch.errors) == {"bad"}
    assert list(batch.summary["dataset"]) == ["sensor_a", "sensor_b"]
    assert batch.summary["x_column"].eq("time").all()
    assert batch.summary["center"].to_numpy() == pytest.approx([-1.0, 1.5], abs=0.03)

    with pytest.raises(Exception):
        analyze_peaks_batch(
            frame,
            "time",
            ["bad"],
            baseline="none",
            continue_on_error=False,
        )
