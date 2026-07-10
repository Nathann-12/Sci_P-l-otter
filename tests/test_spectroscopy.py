from __future__ import annotations

import numpy as np
import pytest

from analysis.spectroscopy import (
    baseline_correct,
    detect_spectrum_peaks,
    normalize_spectrum,
    raman_d_g_ratio,
    scherrer_crystallite_size,
    tauc_band_gap,
)


def test_baseline_correct_and_normalize_spectrum():
    x = np.linspace(0, 10, 101)
    baseline = 0.1 * x + 2.0
    peak = 5.0 * np.exp(-0.5 * ((x - 5.0) / 0.35) ** 2)
    result = baseline_correct(x, baseline + peak, degree=1, quantile=0.25)
    norm = normalize_spectrum(result["corrected"], mode="max")

    assert result["corrected"].max() == pytest.approx(5.0, rel=0.15)
    assert norm.max() == pytest.approx(1.0)


def test_detect_spectrum_peaks_reports_fwhm_and_area():
    x = np.linspace(0, 10, 1001)
    y = np.exp(-0.5 * ((x - 3.0) / 0.2) ** 2) + 0.7 * np.exp(-0.5 * ((x - 7.0) / 0.3) ** 2)

    peaks = detect_spectrum_peaks(x, y, threshold_rel=0.3, min_distance=100)

    assert len(peaks) == 2
    assert [p.x for p in peaks] == pytest.approx([3.0, 7.0], abs=0.02)
    assert peaks[0].fwhm == pytest.approx(2.355 * 0.2, rel=0.12)
    assert peaks[0].y > peaks[1].y
    assert peaks[1].area > peaks[0].area  # broader peaks can have larger area.


def test_raman_d_g_ratio_uses_configured_windows():
    x = np.linspace(1000, 1800, 1601)
    y = 2.0 * np.exp(-0.5 * ((x - 1350) / 18) ** 2) + 4.0 * np.exp(-0.5 * ((x - 1580) / 22) ** 2)

    result = raman_d_g_ratio(x, y)

    assert result["d_position"] == pytest.approx(1350, abs=1)
    assert result["g_position"] == pytest.approx(1580, abs=1)
    assert result["id_ig"] == pytest.approx(0.5, rel=0.03)


def test_tauc_band_gap_recovers_linear_intercept():
    energy = np.linspace(1.5, 3.2, 80)
    eg = 2.05
    absorbance = np.clip(energy - eg, 0, None) / energy

    result = tauc_band_gap(energy, absorbance, exponent=1.0, fit_fraction=0.45)

    assert result.band_gap_ev == pytest.approx(eg, abs=0.03)
    assert result.r_squared > 0.99


def test_scherrer_crystallite_size_returns_angstrom():
    size_a = scherrer_crystallite_size(two_theta_deg=26.5, fwhm_deg=0.2)

    assert size_a == pytest.approx(407.0, rel=0.04)
