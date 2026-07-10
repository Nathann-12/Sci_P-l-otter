"""Signal-processing primitives (ROADMAP section E).

Pure numpy/scipy functions, no Qt. All take 1-D array-likes; NaN values are
rejected with a clear error (clean the data first — see analysis.cleaning).
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple, Union

import numpy as np
from scipy import signal as _sig
from scipy.ndimage import gaussian_filter1d as _gaussian_filter1d


BUTTER_KINDS = ("lowpass", "highpass", "bandpass", "bandstop")
WINDOW_KINDS = ("hann", "hamming", "blackman", "kaiser")
CONVOLUTION_MODES = ("full", "same", "valid")

# numpy 2.0 renamed trapz -> trapezoid
_trapezoid = getattr(np, "trapezoid", None) or np.trapz


def _as_clean_array(y, name: str = "y") -> np.ndarray:
    arr = np.asarray(y, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError(f"{name} is empty")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains NaN/inf — clean the data first")
    return arr


def butterworth_filter(
    y,
    fs: float,
    kind: str = "lowpass",
    cutoff: Union[float, Sequence[float]] = 1.0,
    order: int = 4,
) -> np.ndarray:
    """Zero-phase Butterworth filter (filtfilt).

    ``kind``: one of BUTTER_KINDS. ``cutoff`` is a scalar (low/high-pass) or a
    (low, high) pair (band-pass/stop), in the same units as ``fs`` (Hz).
    """
    arr = _as_clean_array(y)
    if kind not in BUTTER_KINDS:
        raise ValueError(f"unknown filter kind: {kind!r} (use one of {BUTTER_KINDS})")
    if fs <= 0:
        raise ValueError("fs must be > 0")
    nyq = fs / 2.0
    if kind in ("bandpass", "bandstop"):
        lo, hi = (float(c) for c in cutoff)
        if not (0 < lo < hi < nyq):
            raise ValueError(f"band cutoffs must satisfy 0 < low < high < fs/2 (= {nyq})")
        wn = (lo / nyq, hi / nyq)
    else:
        c = float(cutoff if np.isscalar(cutoff) else cutoff[0])
        if not (0 < c < nyq):
            raise ValueError(f"cutoff must satisfy 0 < cutoff < fs/2 (= {nyq})")
        wn = c / nyq
    b, a = _sig.butter(order, wn, btype=kind)
    # filtfilt needs > 3*max(len(a),len(b)) samples; guard short signals
    padlen = min(3 * max(len(a), len(b)), arr.size - 1)
    return _sig.filtfilt(b, a, arr, padlen=padlen)


def savitzky_golay(y, window_length: int = 11, polyorder: int = 3) -> np.ndarray:
    """Savitzky-Golay smoothing; window is clamped to the signal and made odd."""
    arr = _as_clean_array(y)
    wl = int(window_length)
    if wl % 2 == 0:
        wl += 1
    wl = min(wl, arr.size if arr.size % 2 == 1 else arr.size - 1)
    if wl < 3:
        raise ValueError("signal too short for Savitzky-Golay")
    po = min(int(polyorder), wl - 1)
    return _sig.savgol_filter(arr, wl, po)


def median_filter(y, kernel_size: int = 5) -> np.ndarray:
    """Median filter (spike killer); kernel is forced odd and clamped."""
    arr = _as_clean_array(y)
    k = int(kernel_size)
    if k % 2 == 0:
        k += 1
    k = min(k, arr.size if arr.size % 2 == 1 else arr.size - 1)
    if k < 1:
        raise ValueError("signal too short for a median filter")
    return _sig.medfilt(arr, kernel_size=k)


def gaussian_smooth(y, sigma: float = 2.0) -> np.ndarray:
    """Gaussian smoothing with standard deviation ``sigma`` (in samples)."""
    arr = _as_clean_array(y)
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    return _gaussian_filter1d(arr, sigma=float(sigma))


def apply_window(y, window: str = "hann", beta: float = 14.0) -> np.ndarray:
    """Multiply the signal by a taper window (hann/hamming/blackman/kaiser)."""
    arr = _as_clean_array(y)
    if window not in WINDOW_KINDS:
        raise ValueError(f"unknown window: {window!r} (use one of {WINDOW_KINDS})")
    n = arr.size
    if window == "hann":
        w = np.hanning(n)
    elif window == "hamming":
        w = np.hamming(n)
    elif window == "blackman":
        w = np.blackman(n)
    else:
        w = np.kaiser(n, float(beta))
    return arr * w


def zero_pad(y, target_length: int) -> np.ndarray:
    """Append zeros up to ``target_length`` (e.g. next power of two for FFT)."""
    arr = _as_clean_array(y)
    n = int(target_length)
    if n < arr.size:
        raise ValueError(f"target_length {n} is shorter than the signal ({arr.size})")
    return np.concatenate([arr, np.zeros(n - arr.size)])


def hilbert_transform(y) -> np.ndarray:
    """Analytic signal via the Hilbert transform."""
    arr = _as_clean_array(y)
    if arr.size < 2:
        raise ValueError("need at least 2 samples for a Hilbert transform")
    return _sig.hilbert(arr)


def signal_envelope(y) -> np.ndarray:
    """Amplitude envelope derived from the Hilbert analytic signal."""
    return np.abs(hilbert_transform(y))


def instantaneous_frequency(y, fs: float = 1.0) -> np.ndarray:
    """Instantaneous frequency in Hz from Hilbert phase; first sample is NaN."""
    arr = _as_clean_array(y)
    if fs <= 0:
        raise ValueError("fs must be > 0")
    analytic = hilbert_transform(arr)
    phase = np.unwrap(np.angle(analytic))
    freq = np.empty(arr.size, dtype=float)
    freq[0] = np.nan
    freq[1:] = np.diff(phase) * float(fs) / (2.0 * np.pi)
    return freq


def autocorrelation(
    y,
    max_lag: Optional[int] = None,
    *,
    normalize: bool = True,
    demean: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    """One-sided auto-correlation. Returns ``(lags, corr)`` for lag >= 0."""
    arr = _as_clean_array(y)
    if demean:
        arr = arr - float(np.mean(arr))
    corr = np.correlate(arr, arr, mode="full")[arr.size - 1:]
    if normalize:
        denom = float(corr[0])
        if denom > 0:
            corr = corr / denom
    if max_lag is not None:
        lag = int(max_lag)
        if lag < 0:
            raise ValueError("max_lag must be >= 0")
        corr = corr[: min(lag, arr.size - 1) + 1]
    return np.arange(corr.size, dtype=float), corr


def convolve_signals(a, b, mode: str = "full") -> np.ndarray:
    """Linear convolution of two 1-D signals."""
    if mode not in CONVOLUTION_MODES:
        raise ValueError(f"unknown convolution mode: {mode!r} (use one of {CONVOLUTION_MODES})")
    left = _as_clean_array(a, name="a")
    right = _as_clean_array(b, name="b")
    return np.convolve(left, right, mode=mode)


def deconvolve_signals(observed, kernel, *, trim_leading_zeros: bool = True) -> Tuple[np.ndarray, np.ndarray]:
    """Polynomial/linear deconvolution. Returns ``(quotient, remainder)``."""
    obs = _as_clean_array(observed, name="observed")
    ker = _as_clean_array(kernel, name="kernel")
    non_zero = np.flatnonzero(np.abs(ker) > 1e-12)
    if non_zero.size == 0:
        raise ValueError("kernel must not be all zeros")
    if trim_leading_zeros and non_zero[0] > 0:
        ker = ker[int(non_zero[0]):]
    if obs.size < ker.size:
        raise ValueError("observed signal must be at least as long as the kernel")
    return _sig.deconvolve(obs, ker)


def compute_stft(
    y,
    fs: float = 1.0,
    *,
    window: str = "hann",
    nperseg: int = 256,
    noverlap: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Short-time Fourier transform. Returns ``(freqs, times, complex_matrix)``."""
    arr = _as_clean_array(y)
    if arr.size < 2:
        raise ValueError("need at least 2 samples for STFT")
    if fs <= 0:
        raise ValueError("fs must be > 0")
    nperseg = max(2, min(int(nperseg), arr.size))
    if noverlap is None:
        noverlap = nperseg // 2
    noverlap = int(noverlap)
    if not (0 <= noverlap < nperseg):
        raise ValueError("noverlap must satisfy 0 <= noverlap < nperseg")
    return _sig.stft(arr, fs=float(fs), window=window, nperseg=nperseg, noverlap=noverlap)


def compute_psd(y, fs: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """Power spectral density via periodogram. Returns ``(freqs, psd)``."""
    arr = _as_clean_array(y)
    if fs <= 0:
        raise ValueError("fs must be > 0")
    return _sig.periodogram(arr, fs=fs)


def harmonic_analysis(
    y,
    fs: float = 1.0,
    *,
    top_n: int = 8,
    window: str = "hann",
    fundamental_hz: Optional[float] = None,
) -> dict:
    """Return the strongest harmonic components of a 1-D signal.

    The output is a plain dict of numpy arrays so the function stays Qt-free
    and callers can decide whether to show it as a result Book, export table,
    or plot annotation.
    """
    arr = _as_clean_array(y)
    if arr.size < 2:
        raise ValueError("need at least 2 samples for harmonic analysis")
    if fs <= 0:
        raise ValueError("fs must be > 0")
    n_keep = max(1, int(top_n))
    centered = arr - float(np.mean(arr))
    if window not in ("none",) + WINDOW_KINDS:
        raise ValueError(f"unknown window: {window!r} (use 'none' or one of {WINDOW_KINDS})")
    if window == "hann":
        centered = centered * np.hanning(centered.size)
    elif window == "hamming":
        centered = centered * np.hamming(centered.size)
    elif window == "blackman":
        centered = centered * np.blackman(centered.size)
    elif window == "kaiser":
        centered = centered * np.kaiser(centered.size, 14.0)

    spectrum = np.fft.rfft(centered)
    freqs = np.fft.rfftfreq(centered.size, d=1.0 / float(fs))
    amplitude = (2.0 / centered.size) * np.abs(spectrum)
    if amplitude.size:
        amplitude[0] = amplitude[0] / 2.0
    power = amplitude ** 2
    candidates = np.arange(1, freqs.size)
    if candidates.size == 0:
        raise ValueError("signal has no positive-frequency bins")
    try:
        peaks, _ = _sig.find_peaks(amplitude[candidates])
        candidates = candidates[peaks] if peaks.size else candidates
    except Exception:
        pass
    order = candidates[np.argsort(amplitude[candidates])[::-1]]
    order = order[: min(n_keep, order.size)]
    if order.size == 0:
        raise ValueError("no harmonic peaks found")
    base = float(fundamental_hz) if fundamental_hz and fundamental_hz > 0 else float(freqs[order[0]])
    if base <= 0:
        base = float(freqs[order[0]])
    ranked = np.arange(1, order.size + 1, dtype=int)
    return {
        "rank": ranked,
        "frequency_Hz": freqs[order],
        "amplitude": amplitude[order],
        "power": power[order],
        "period_s": np.where(freqs[order] > 0, 1.0 / freqs[order], np.nan),
        "harmonic_order": freqs[order] / base if base > 0 else np.full(order.size, np.nan),
    }


def welch_psd(y, fs: float = 1.0, nperseg: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Welch-averaged PSD (smoother than a raw periodogram)."""
    arr = _as_clean_array(y)
    if fs <= 0:
        raise ValueError("fs must be > 0")
    if nperseg is None:
        nperseg = min(256, arr.size)
    nperseg = max(2, min(int(nperseg), arr.size))
    return _sig.welch(arr, fs=fs, nperseg=nperseg)


def compute_ifft(spectrum) -> np.ndarray:
    """Inverse FFT. Returns the real part when the imaginary residue is
    negligible (spectrum of a real signal), else the complex result."""
    spec = np.asarray(spectrum)
    if spec.size == 0:
        raise ValueError("spectrum is empty")
    out = np.fft.ifft(spec)
    if np.max(np.abs(out.imag)) < 1e-9 * max(1.0, float(np.max(np.abs(out.real)))):
        return out.real
    return out


def noise_floor(y, fs: float = 1.0) -> float:
    """Median Welch-PSD level — a robust estimate of the broadband noise floor."""
    _, pxx = welch_psd(y, fs=fs)
    return float(np.median(pxx))


def estimate_snr(y, fs: float = 1.0) -> float:
    """Crude SNR in dB: dominant PSD peak over the median noise floor."""
    _, pxx = welch_psd(y, fs=fs)
    floor = np.median(pxx)
    if floor <= 0:
        raise ValueError("cannot estimate SNR: zero noise floor")
    return float(10.0 * np.log10(np.max(pxx) / floor))


def fwhm(x, y) -> float:
    """Full width at half maximum of the dominant peak (linear interpolation
    at the half-level crossings; baseline = signal minimum)."""
    xa = np.asarray(x, dtype=float).ravel()
    ya = _as_clean_array(y)
    if xa.size != ya.size:
        raise ValueError("x and y must be the same length")
    if not np.all(np.isfinite(xa)):
        raise ValueError("x contains NaN/inf")
    i_peak = int(np.argmax(ya))
    y_min, y_max = float(np.min(ya)), float(np.max(ya))
    if y_max <= y_min:
        raise ValueError("signal is flat — no peak to measure")
    half = y_min + (y_max - y_min) / 2.0

    def _cross(i_from: int, step: int) -> float:
        i = i_peak
        while 0 <= i + step < ya.size and ya[i + step] >= half:
            i += step
        j = i + step
        if j < 0 or j >= ya.size:
            raise ValueError("peak does not fall below half maximum inside the data")
        # linear interpolation between (x[i], y[i]) and (x[j], y[j])
        frac = (half - ya[i]) / (ya[j] - ya[i])
        return float(xa[i] + frac * (xa[j] - xa[i]))

    left = _cross(i_peak, -1)
    right = _cross(i_peak, +1)
    return abs(right - left)


def peak_area(x, y, x_min: Optional[float] = None, x_max: Optional[float] = None) -> float:
    """Trapezoidal area under ``y(x)``, optionally restricted to [x_min, x_max]."""
    xa = np.asarray(x, dtype=float).ravel()
    ya = _as_clean_array(y)
    if xa.size != ya.size:
        raise ValueError("x and y must be the same length")
    mask = np.isfinite(xa)
    if x_min is not None:
        mask &= xa >= x_min
    if x_max is not None:
        mask &= xa <= x_max
    if mask.sum() < 2:
        raise ValueError("need at least 2 points in the integration range")
    order = np.argsort(xa[mask])
    return float(_trapezoid(ya[mask][order], xa[mask][order]))


def peak_metrics_summary(x, y) -> dict:
    """One-row summary of the main peak: area, FWHM, position and height.

    ``fwhm`` is None when the half-maximum width cannot be determined (e.g.
    monotonic data) instead of raising, so table builders can keep going.
    """
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    mask = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[mask], ya[mask]
    if xa.size < 2:
        raise ValueError("need at least 2 finite points")
    idx = int(np.argmax(ya))
    out = {
        "points": int(xa.size),
        "area": float(peak_area(xa, ya)),
        "peak_x": float(xa[idx]),
        "peak_height": float(ya[idx]),
    }
    try:
        out["fwhm"] = float(fwhm(xa, ya))
    except ValueError:
        out["fwhm"] = None
    return out


def signal_quality_summary(y, fs: float = 1.0) -> dict:
    """SNR + noise floor of a signal in one dict (for result sheets)."""
    return {
        "fs_hz": float(fs),
        "snr_db": float(estimate_snr(y, fs=fs)),
        "noise_floor": float(noise_floor(y, fs=fs)),
    }
