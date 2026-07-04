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


def compute_psd(y, fs: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """Power spectral density via periodogram. Returns ``(freqs, psd)``."""
    arr = _as_clean_array(y)
    if fs <= 0:
        raise ValueError("fs must be > 0")
    return _sig.periodogram(arr, fs=fs)


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
