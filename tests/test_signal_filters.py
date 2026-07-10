"""Behavioral tests for analysis.signal_filters (ROADMAP section E)."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("scipy")

from analysis.signal_filters import (
    apply_window,
    autocorrelation,
    butterworth_filter,
    compute_ifft,
    compute_psd,
    compute_stft,
    convolve_signals,
    deconvolve_signals,
    estimate_snr,
    fwhm,
    gaussian_smooth,
    hilbert_transform,
    instantaneous_frequency,
    median_filter,
    noise_floor,
    peak_area,
    savitzky_golay,
    signal_envelope,
    welch_psd,
    zero_pad,
)


FS = 100.0  # Hz
T = np.arange(0, 10, 1 / FS)  # 10 s
LOW_TONE = np.sin(2 * np.pi * 2.0 * T)    # 2 Hz
HIGH_TONE = np.sin(2 * np.pi * 20.0 * T)  # 20 Hz


_trapezoid = getattr(np, "trapezoid", None) or np.trapz


def _band_power(y, fs, f_lo, f_hi):
    f, pxx = welch_psd(y, fs=fs)
    band = (f >= f_lo) & (f <= f_hi)
    return float(_trapezoid(pxx[band], f[band]))


# ---------- Butterworth family ----------

def test_lowpass_keeps_low_tone_kills_high_tone():
    mixed = LOW_TONE + HIGH_TONE
    out = butterworth_filter(mixed, FS, kind="lowpass", cutoff=5.0)
    assert _band_power(out, FS, 1, 3) > 0.5 * _band_power(LOW_TONE, FS, 1, 3)
    assert _band_power(out, FS, 15, 25) < 0.01 * _band_power(HIGH_TONE, FS, 15, 25)


def test_highpass_keeps_high_tone_kills_low_tone():
    mixed = LOW_TONE + HIGH_TONE
    out = butterworth_filter(mixed, FS, kind="highpass", cutoff=10.0)
    assert _band_power(out, FS, 15, 25) > 0.5 * _band_power(HIGH_TONE, FS, 15, 25)
    assert _band_power(out, FS, 1, 3) < 0.01 * _band_power(LOW_TONE, FS, 1, 3)


def test_bandpass_isolates_middle_tone():
    mid = np.sin(2 * np.pi * 10.0 * T)
    mixed = LOW_TONE + mid + HIGH_TONE
    out = butterworth_filter(mixed, FS, kind="bandpass", cutoff=(8.0, 12.0))
    assert _band_power(out, FS, 9, 11) > 0.5 * _band_power(mid, FS, 9, 11)
    assert _band_power(out, FS, 1, 3) < 0.01 * _band_power(LOW_TONE, FS, 1, 3)
    assert _band_power(out, FS, 18, 22) < 0.01 * _band_power(HIGH_TONE, FS, 18, 22)


def test_bandstop_removes_only_target_tone():
    mixed = LOW_TONE + HIGH_TONE
    out = butterworth_filter(mixed, FS, kind="bandstop", cutoff=(18.0, 22.0))
    assert _band_power(out, FS, 19, 21) < 0.01 * _band_power(HIGH_TONE, FS, 19, 21)
    assert _band_power(out, FS, 1, 3) > 0.5 * _band_power(LOW_TONE, FS, 1, 3)


def test_butterworth_validates_inputs():
    with pytest.raises(ValueError):
        butterworth_filter(LOW_TONE, FS, kind="nope", cutoff=5.0)
    with pytest.raises(ValueError):
        butterworth_filter(LOW_TONE, FS, kind="lowpass", cutoff=99.0)  # >= nyquist
    with pytest.raises(ValueError):
        butterworth_filter([1.0, np.nan], FS, kind="lowpass", cutoff=5.0)


# ---------- smoothers ----------

def test_savgol_preserves_polynomial_exactly():
    x = np.linspace(0, 1, 101)
    y = 3 * x**2 - 2 * x + 1  # polyorder 3 window fits a quadratic exactly
    out = savitzky_golay(y, window_length=11, polyorder=3)
    assert np.allclose(out, y, atol=1e-10)


def test_savgol_reduces_noise_variance():
    rng = np.random.default_rng(42)
    noisy = LOW_TONE + rng.normal(0, 0.5, LOW_TONE.size)
    out = savitzky_golay(noisy, window_length=31, polyorder=3)
    assert np.var(out - LOW_TONE) < 0.25 * np.var(noisy - LOW_TONE)


def test_median_filter_kills_isolated_spikes():
    y = np.ones(50)
    y[25] = 100.0
    out = median_filter(y, kernel_size=5)
    assert out[25] == pytest.approx(1.0)


def test_gaussian_smooth_reduces_noise():
    rng = np.random.default_rng(7)
    noisy = LOW_TONE + rng.normal(0, 0.5, LOW_TONE.size)
    out = gaussian_smooth(noisy, sigma=3.0)
    assert np.var(out - LOW_TONE) < 0.25 * np.var(noisy - LOW_TONE)


# ---------- windows / padding ----------

def test_windows_taper_endpoints():
    y = np.ones(64)
    for name in ("hann", "blackman"):
        w = apply_window(y, window=name)
        assert abs(w[0]) < 1e-6 and abs(w[-1]) < 1e-6
        assert w.max() == pytest.approx(1.0, abs=0.05)
    kaiser = apply_window(y, window="kaiser", beta=14.0)
    assert kaiser.size == 64 and kaiser.max() <= 1.0
    with pytest.raises(ValueError):
        apply_window(y, window="tukey")


def test_zero_pad_extends_with_zeros():
    y = np.array([1.0, 2.0, 3.0])
    out = zero_pad(y, 8)
    assert out.size == 8
    assert out[:3].tolist() == [1.0, 2.0, 3.0]
    assert np.all(out[3:] == 0)
    with pytest.raises(ValueError):
        zero_pad(y, 2)


# ---------- analytic signal / correlation / convolution ----------

def test_hilbert_transform_preserves_real_part_and_envelope():
    analytic = hilbert_transform(LOW_TONE)
    assert np.allclose(np.real(analytic), LOW_TONE, atol=1e-10)
    assert np.allclose(signal_envelope(LOW_TONE), 1.0, atol=1e-10)


def test_instantaneous_frequency_tracks_single_tone():
    inst = instantaneous_frequency(np.sin(2 * np.pi * 5.0 * T), fs=FS)
    assert np.nanmedian(inst) == pytest.approx(5.0, abs=0.05)


def test_autocorrelation_returns_one_sided_normalized_lags():
    lags, corr = autocorrelation([1.0, -1.0, 1.0, -1.0], max_lag=3)
    assert lags.tolist() == [0.0, 1.0, 2.0, 3.0]
    assert corr.tolist() == pytest.approx([1.0, -0.75, 0.5, -0.25])


def test_convolve_signals_modes_and_validation():
    assert convolve_signals([1, 2, 3], [1, 1], mode="full").tolist() == [1.0, 3.0, 5.0, 3.0]
    assert convolve_signals([1, 2, 3], [1, 1], mode="same").tolist() == [1.0, 3.0, 5.0]
    with pytest.raises(ValueError):
        convolve_signals([1, 2], [1], mode="circular")


def test_deconvolve_signals_roundtrips_linear_convolution():
    original = np.array([1.0, 2.0, -1.0, 0.5])
    kernel = np.array([1.0, 0.25])
    observed = convolve_signals(original, kernel, mode="full")
    quotient, remainder = deconvolve_signals(observed, kernel)
    assert quotient.tolist() == pytest.approx(original.tolist())
    assert np.max(np.abs(remainder)) < 1e-10
    with pytest.raises(ValueError):
        deconvolve_signals(observed, [0.0, 0.0])


def test_stft_identifies_dominant_tone_frequency():
    freqs, times, zxx = compute_stft(HIGH_TONE, fs=FS, nperseg=128, noverlap=64)
    assert times.size > 0
    dominant = freqs[np.argmax(np.mean(np.abs(zxx), axis=1))]
    assert dominant == pytest.approx(20.0, abs=1.0)


# ---------- spectra ----------

def test_psd_peaks_at_tone_frequency():
    f, pxx = compute_psd(LOW_TONE, fs=FS)
    assert f[np.argmax(pxx)] == pytest.approx(2.0, abs=0.2)


def test_welch_psd_peaks_at_tone_frequency():
    f, pxx = welch_psd(HIGH_TONE, fs=FS, nperseg=512)
    assert f[np.argmax(pxx)] == pytest.approx(20.0, abs=0.5)


def test_ifft_roundtrips_real_signal():
    spec = np.fft.fft(LOW_TONE)
    back = compute_ifft(spec)
    assert not np.iscomplexobj(back)
    assert np.allclose(back, LOW_TONE, atol=1e-9)


def test_snr_higher_for_clean_signal():
    rng = np.random.default_rng(3)
    clean = LOW_TONE
    noisy = LOW_TONE + rng.normal(0, 1.0, LOW_TONE.size)
    assert estimate_snr(clean, fs=FS) > estimate_snr(noisy, fs=FS)
    assert noise_floor(noisy, fs=FS) > noise_floor(clean, fs=FS)


# ---------- peak metrics ----------

def test_fwhm_of_gaussian_matches_theory():
    sigma = 2.0
    x = np.linspace(-15, 15, 3001)
    y = np.exp(-x**2 / (2 * sigma**2))
    expected = 2 * np.sqrt(2 * np.log(2)) * sigma  # ≈ 2.3548 σ
    assert fwhm(x, y) == pytest.approx(expected, rel=1e-3)


def test_fwhm_rejects_flat_signal():
    with pytest.raises(ValueError):
        fwhm([0, 1, 2], [5.0, 5.0, 5.0])


def test_peak_area_of_gaussian_matches_theory():
    sigma, amp = 1.5, 3.0
    x = np.linspace(-12, 12, 4001)
    y = amp * np.exp(-x**2 / (2 * sigma**2))
    expected = amp * sigma * np.sqrt(2 * np.pi)
    assert peak_area(x, y) == pytest.approx(expected, rel=1e-4)


def test_peak_area_respects_range():
    x = np.linspace(0, 10, 1001)
    y = np.ones_like(x)
    assert peak_area(x, y, x_min=2.0, x_max=5.0) == pytest.approx(3.0, rel=1e-6)


def test_peak_metrics_summary_gaussian():
    from analysis.signal_filters import peak_metrics_summary
    sigma = 2.0
    x = np.linspace(-15, 15, 3001)
    y = np.exp(-x**2 / (2 * sigma**2))
    s = peak_metrics_summary(x, y)
    assert s["points"] == 3001
    assert s["fwhm"] == pytest.approx(2 * np.sqrt(2 * np.log(2)) * sigma, rel=0.01)
    assert s["area"] == pytest.approx(sigma * np.sqrt(2 * np.pi), rel=0.01)
    assert s["peak_x"] == pytest.approx(0.0, abs=0.02)
    assert s["peak_height"] == pytest.approx(1.0, rel=0.01)


def test_peak_metrics_summary_monotonic_has_none_fwhm():
    from analysis.signal_filters import peak_metrics_summary
    x = np.linspace(0, 1, 50)
    s = peak_metrics_summary(x, x)  # ramp: FWHM undefined, area fine
    assert s["fwhm"] is None
    assert s["area"] == pytest.approx(0.5, rel=1e-3)


def test_signal_quality_summary_keys_and_snr():
    from analysis.signal_filters import signal_quality_summary
    fs = 100.0
    t = np.arange(0, 10, 1 / fs)
    s = signal_quality_summary(np.sin(2 * np.pi * 5 * t), fs=fs)
    assert set(s) == {"fs_hz", "snr_db", "noise_floor"}
    assert s["snr_db"] > 20
