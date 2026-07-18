"""Pure baseline, detection and simultaneous multi-peak analysis.

The fitting contract is intentionally batch-friendly and independent of Qt.
Peak ``amplitude`` is the fitted height above the baseline; ``height`` is the
absolute fitted Y value at the centre; ``area`` is the signed analytic area of
the peak component.  Input rows containing non-finite aligned values are
removed, then the retained rows are stably sorted by X.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import least_squares
from scipy.signal import find_peaks as scipy_find_peaks
from scipy.signal import peak_widths
from scipy.sparse.linalg import spsolve
from scipy.special import voigt_profile
from scipy.stats import t as student_t

from analysis.global_fitting import FitMetrics


ArrayLike = Sequence[float] | np.ndarray
CancelCheck = Callable[[], bool]
_EPS = np.finfo(float).eps
_ALS_BASELINES = frozenset({"als", "asls", "asymmetric_least_squares"})
_POSITIVE_PARAMETERS = frozenset({"sigma", "gamma", "tau"})


class PeakAnalysisError(ValueError):
    """Raised for invalid peak-analysis data or configuration."""


@dataclass(frozen=True)
class PeakMetric:
    peak: int
    detected_index: int
    model: str
    center: float
    height: float
    amplitude: float
    fwhm: float
    area: float
    center_ci95: tuple[float, float]
    height_ci95: tuple[float, float]
    amplitude_ci95: tuple[float, float]
    fwhm_ci95: tuple[float, float]
    area_ci95: tuple[float, float]
    parameters: dict[str, float]
    stderr: dict[str, float]
    ci95: dict[str, tuple[float, float]]


@dataclass(frozen=True)
class PeakAnalysisResult:
    model: str
    baseline_method: str
    direction: str
    success: bool
    message: str
    x: np.ndarray
    y: np.ndarray
    original_indices: np.ndarray
    detected_indices: np.ndarray
    baseline: np.ndarray
    corrected: np.ndarray
    peak_component: np.ndarray
    fitted: np.ndarray
    residuals: np.ndarray
    weighted_residuals: np.ndarray
    ci95_lower: np.ndarray | None
    ci95_upper: np.ndarray | None
    peaks: tuple[PeakMetric, ...]
    parameter_order: tuple[str, ...]
    parameters: dict[str, float]
    stderr: dict[str, float]
    ci95: dict[str, tuple[float, float]]
    covariance: np.ndarray
    correlation: np.ndarray
    metrics: FitMetrics
    nfev: int
    confidence_level: float = 0.95

    @property
    def peak_count(self) -> int:
        return len(self.peaks)

    @property
    def r2(self) -> float:
        return self.metrics.r_squared

    @property
    def rmse(self) -> float:
        return self.metrics.rmse

    @property
    def chi2_red(self) -> float:
        return self.metrics.reduced_chi_square

    @property
    def aic(self) -> float:
        return self.metrics.aic

    @property
    def bic(self) -> float:
        return self.metrics.bic

    @property
    def yfit(self) -> np.ndarray:
        return self.fitted

    @property
    def cov(self) -> np.ndarray:
        return self.covariance

    @property
    def summary(self) -> pd.DataFrame:
        return self.to_frame()

    def to_frame(self, dataset: str | None = None) -> pd.DataFrame:
        """Return one stable, batch-concatenable row per fitted peak."""

        rows: list[dict[str, object]] = []
        for peak in self.peaks:
            row: dict[str, object] = {
                "peak": peak.peak,
                "model": peak.model,
                "center": peak.center,
                "center_ci95_low": peak.center_ci95[0],
                "center_ci95_high": peak.center_ci95[1],
                "height": peak.height,
                "height_ci95_low": peak.height_ci95[0],
                "height_ci95_high": peak.height_ci95[1],
                "amplitude": peak.amplitude,
                "amplitude_ci95_low": peak.amplitude_ci95[0],
                "amplitude_ci95_high": peak.amplitude_ci95[1],
                "fwhm": peak.fwhm,
                "fwhm_ci95_low": peak.fwhm_ci95[0],
                "fwhm_ci95_high": peak.fwhm_ci95[1],
                "area": peak.area,
                "area_ci95_low": peak.area_ci95[0],
                "area_ci95_high": peak.area_ci95[1],
                "r_squared": self.metrics.r_squared,
                "rmse": self.metrics.rmse,
                "reduced_chi_square": self.metrics.reduced_chi_square,
                "success": self.success,
            }
            if dataset is not None:
                row["dataset"] = dataset
            rows.append(row)
        columns = list(_SUMMARY_COLUMNS)
        if dataset is not None:
            columns = ["dataset", *columns]
        return pd.DataFrame(rows, columns=columns)


@dataclass(frozen=True)
class PeakBatchResult:
    results: dict[str, PeakAnalysisResult]
    summary: pd.DataFrame
    errors: dict[str, str]


@dataclass(frozen=True)
class _PreparedPeakData:
    x: np.ndarray
    y: np.ndarray
    original_indices: np.ndarray
    scale: np.ndarray


_SUMMARY_COLUMNS = (
    "peak",
    "model",
    "center",
    "center_ci95_low",
    "center_ci95_high",
    "height",
    "height_ci95_low",
    "height_ci95_high",
    "amplitude",
    "amplitude_ci95_low",
    "amplitude_ci95_high",
    "fwhm",
    "fwhm_ci95_low",
    "fwhm_ci95_high",
    "area",
    "area_ci95_low",
    "area_ci95_high",
    "r_squared",
    "rmse",
    "reduced_chi_square",
    "success",
)


def gaussian_peak(x: ArrayLike, amplitude: float, center: float, sigma: float) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    width = max(abs(float(sigma)), np.finfo(float).tiny)
    return amplitude * np.exp(-0.5 * ((x_arr - center) / width) ** 2)


def lorentzian_peak(
    x: ArrayLike, amplitude: float, center: float, gamma: float
) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    width = max(abs(float(gamma)), np.finfo(float).tiny)
    return amplitude * width**2 / ((x_arr - center) ** 2 + width**2)


def voigt_peak(
    x: ArrayLike,
    amplitude: float,
    center: float,
    sigma: float,
    gamma: float,
) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    sigma_pos = max(abs(float(sigma)), np.finfo(float).tiny)
    gamma_pos = max(abs(float(gamma)), np.finfo(float).tiny)
    raw = voigt_profile(x_arr - center, sigma_pos, gamma_pos)
    at_center = float(voigt_profile(0.0, sigma_pos, gamma_pos))
    return amplitude * raw / max(at_center, np.finfo(float).tiny)


_PEAK_MODELS = {
    "gaussian": (gaussian_peak, ("amplitude", "center", "sigma")),
    "lorentzian": (lorentzian_peak, ("amplitude", "center", "gamma")),
    "voigt": (voigt_peak, ("amplitude", "center", "sigma", "gamma")),
}


def _normalise_peak_model(model: str):
    key = str(model).strip().lower().replace("-", "_").replace(" ", "_")
    if key == "gauss":
        key = "gaussian"
    if key == "lorentz":
        key = "lorentzian"
    try:
        function, names = _PEAK_MODELS[key]
    except KeyError as exc:
        raise PeakAnalysisError(f"Unknown peak model: {model!r}") from exc
    return key, function, names


def _baseline_key(method: str) -> str:
    return str(method).strip().lower().replace("-", "_").replace(" ", "_")


def _check_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is None:
        return
    if not callable(cancel_check):
        raise PeakAnalysisError("cancel_check must be callable")
    try:
        cancelled = bool(cancel_check())
    except PeakAnalysisError:
        raise
    except Exception as exc:
        raise PeakAnalysisError(f"cancel_check failed: {exc}") from exc
    if cancelled:
        raise PeakAnalysisError("Peak analysis cancelled")


def _validate_baseline_direction(baseline: str, direction: str) -> tuple[str, str]:
    baseline_key = _baseline_key(baseline)
    direction_key = str(direction).strip().lower()
    _detection_signal(np.zeros(1), direction_key)  # validates the spelling
    if baseline_key in _ALS_BASELINES and direction_key in {"both", "absolute"}:
        raise PeakAnalysisError(
            "ALS baseline cannot be used with direction='both'; analyze positive and "
            "negative peaks separately or choose Linear, Constant, or None baseline"
        )
    return baseline_key, direction_key


def _prepare_peak_data(
    x: ArrayLike,
    y: ArrayLike,
    *,
    sigma: ArrayLike | None = None,
    weights: ArrayLike | None = None,
) -> _PreparedPeakData:
    if sigma is not None and weights is not None:
        raise PeakAnalysisError("sigma and weights are mutually exclusive")
    try:
        x_arr = np.asarray(x, dtype=float).reshape(-1)
        y_arr = np.asarray(y, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise PeakAnalysisError("X and Y must be numeric") from exc
    if x_arr.size != y_arr.size:
        raise PeakAnalysisError("X and Y lengths differ")
    if x_arr.size == 0:
        raise PeakAnalysisError("Peak data is empty")
    original = np.arange(x_arr.size, dtype=int)
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    scale = np.ones(x_arr.size, dtype=float)
    auxiliary = sigma if sigma is not None else weights
    if auxiliary is not None:
        try:
            aux = np.asarray(auxiliary, dtype=float).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise PeakAnalysisError("uncertainty/weights must be numeric") from exc
        if aux.size != x_arr.size:
            raise PeakAnalysisError("uncertainty/weight length differs from X/Y")
        if np.any(mask & np.isfinite(aux) & (aux <= 0)):
            label = "sigma" if sigma is not None else "weights"
            raise PeakAnalysisError(f"{label} must contain positive values")
        mask &= np.isfinite(aux)
        scale = 1.0 / aux if sigma is not None else np.sqrt(aux)
    x_arr = x_arr[mask]
    y_arr = y_arr[mask]
    scale = scale[mask]
    original = original[mask]
    if x_arr.size < 7:
        raise PeakAnalysisError("At least 7 finite observations are required")
    if np.unique(x_arr).size < 3:
        raise PeakAnalysisError("X must contain at least three distinct values")
    order = np.argsort(x_arr, kind="mergesort")
    return _PreparedPeakData(
        x_arr[order], y_arr[order], original[order], scale[order]
    )


def _baseline_array(
    x: np.ndarray,
    y: np.ndarray,
    method: str,
    *,
    constant_quantile: float,
    als_lambda: float,
    als_p: float,
    als_iterations: int,
    cancel_check: CancelCheck | None = None,
) -> np.ndarray:
    key = _baseline_key(method)
    _check_cancelled(cancel_check)
    if key in {"none", "zero"}:
        return np.zeros_like(y)
    if key in {"constant", "const"}:
        if not 0.0 <= constant_quantile <= 1.0:
            raise PeakAnalysisError("constant_quantile must be between 0 and 1")
        return np.full_like(y, float(np.quantile(y, constant_quantile)))
    if key == "linear":
        edge_count = max(3, min(y.size // 5, max(3, y.size // 10)))
        edge_indices = np.r_[np.arange(edge_count), np.arange(y.size - edge_count, y.size)]
        try:
            slope, intercept = np.polyfit(x[edge_indices], y[edge_indices], 1)
        except (ValueError, np.linalg.LinAlgError) as exc:
            raise PeakAnalysisError(f"Linear baseline failed: {exc}") from exc
        return slope * x + intercept
    if key in _ALS_BASELINES:
        if als_lambda <= 0:
            raise PeakAnalysisError("als_lambda must be positive")
        if not 0.0 < als_p < 1.0:
            raise PeakAnalysisError("als_p must be between 0 and 1")
        if als_iterations < 1:
            raise PeakAnalysisError("als_iterations must be at least 1")
        n = y.size
        differences = sparse.diags(
            [np.ones(n), -2.0 * np.ones(n), np.ones(n)],
            [0, 1, 2],
            shape=(n - 2, n),
            format="csc",
        )
        penalty = float(als_lambda) * (differences.T @ differences)
        weights = np.ones(n, dtype=float)
        baseline = y.copy()
        for _ in range(int(als_iterations)):
            _check_cancelled(cancel_check)
            weight_matrix = sparse.spdiags(weights, 0, n, n, format="csc")
            try:
                baseline = np.asarray(
                    spsolve(weight_matrix + penalty, weights * y), dtype=float
                )
            except Exception as exc:
                raise PeakAnalysisError(f"ALS baseline failed: {exc}") from exc
            above = y > baseline
            below = y < baseline
            weights = als_p * above + (1.0 - als_p) * below + 0.5 * ~(above | below)
        if not np.all(np.isfinite(baseline)):
            raise PeakAnalysisError("ALS baseline produced non-finite values")
        return baseline
    raise PeakAnalysisError(f"Unknown baseline method: {method!r}")


def estimate_baseline(
    x: ArrayLike,
    y: ArrayLike,
    method: str = "linear",
    *,
    constant_quantile: float = 0.1,
    als_lambda: float = 1e5,
    als_p: float = 0.01,
    als_iterations: int = 10,
) -> np.ndarray:
    """Estimate a baseline after finite-row filtering and stable X sorting."""

    prepared = _prepare_peak_data(x, y)
    return _baseline_array(
        prepared.x,
        prepared.y,
        method,
        constant_quantile=constant_quantile,
        als_lambda=als_lambda,
        als_p=als_p,
        als_iterations=als_iterations,
    )


def _detection_signal(corrected: np.ndarray, direction: str) -> np.ndarray:
    key = str(direction).strip().lower()
    if key == "positive":
        return corrected
    if key == "negative":
        return -corrected
    if key in {"both", "absolute"}:
        return np.abs(corrected)
    raise PeakAnalysisError("direction must be 'positive', 'negative', or 'both'")


def _default_prominence(signal: np.ndarray) -> float:
    spread = float(np.ptp(signal))
    if spread <= 0:
        return np.finfo(float).eps
    differences = np.diff(signal)
    median = float(np.median(differences)) if differences.size else 0.0
    mad = float(np.median(np.abs(differences - median))) if differences.size else 0.0
    noise = 1.4826 * mad / np.sqrt(2.0)
    return max(3.0 * noise, 0.03 * spread, np.finfo(float).eps)


def _find_peak_indices(
    signal: np.ndarray,
    *,
    prominence: float | None,
    height: float | None,
    distance: int | None,
    width: float | None,
    max_peaks: int | None,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    if prominence is None:
        prominence = _default_prominence(signal)
    if prominence < 0:
        raise PeakAnalysisError("prominence must be non-negative")
    if distance is not None and int(distance) < 1:
        raise PeakAnalysisError("distance must be at least 1 sample")
    if width is not None and width <= 0:
        raise PeakAnalysisError("width must be positive")
    indices, properties = scipy_find_peaks(
        signal,
        prominence=float(prominence),
        height=height,
        distance=None if distance is None else int(distance),
        width=width,
    )
    if max_peaks is not None:
        if int(max_peaks) < 1:
            raise PeakAnalysisError("max_peaks must be positive or None")
        if indices.size > int(max_peaks):
            prominence_values = properties.get("prominences", signal[indices])
            strongest = np.argsort(prominence_values)[-int(max_peaks) :]
            indices = indices[strongest]
            properties = {
                key: np.asarray(value)[strongest]
                for key, value in properties.items()
                if np.asarray(value).shape[:1] == prominence_values.shape[:1]
            }
    order = np.argsort(indices)
    indices = np.asarray(indices[order], dtype=int)
    ordered_properties = {
        key: np.asarray(value)[order]
        for key, value in properties.items()
        if np.asarray(value).shape[:1] == order.shape[:1]
    }
    return indices, ordered_properties


def detect_peaks(
    x: ArrayLike,
    y: ArrayLike,
    *,
    baseline: str = "linear",
    direction: str = "positive",
    prominence: float | None = None,
    height: float | None = None,
    distance: int | None = None,
    width: float | None = None,
    max_peaks: int | None = 20,
    constant_quantile: float = 0.1,
    als_lambda: float = 1e5,
    als_p: float = 0.01,
    als_iterations: int = 10,
) -> np.ndarray:
    """Return detected indices in the finite, X-sorted representation."""

    _, direction_key = _validate_baseline_direction(baseline, direction)
    prepared = _prepare_peak_data(x, y)
    sign = -1.0 if direction_key == "negative" else 1.0
    baseline_y = sign * _baseline_array(
        prepared.x,
        sign * prepared.y,
        baseline,
        constant_quantile=constant_quantile,
        als_lambda=als_lambda,
        als_p=als_p,
        als_iterations=als_iterations,
    )
    corrected = prepared.y - baseline_y
    signal = _detection_signal(corrected, direction_key)
    indices, _ = _find_peak_indices(
        signal,
        prominence=prominence,
        height=height,
        distance=distance,
        width=width,
        max_peaks=max_peaks,
    )
    return indices


def _mapping_value(mapping, peak_index: int, parameter: str, default):
    if not mapping:
        return default
    key = f"peak{peak_index}.{parameter}"
    if key in mapping:
        return mapping[key]
    return mapping.get(parameter, default)


def _validate_mapping_keys(mapping, label: str, count: int, parameter_names: Sequence[str]):
    if not mapping:
        return
    valid = set(parameter_names)
    for peak_index in range(count):
        valid.update(f"peak{peak_index}.{name}" for name in parameter_names)
    unknown = sorted(str(key) for key in mapping if key not in valid)
    if unknown:
        raise PeakAnalysisError(f"Unknown {label} key(s): {', '.join(unknown)}")


def _initial_widths(x: np.ndarray, detection_signal: np.ndarray, indices: np.ndarray) -> np.ndarray:
    span = max(float(np.ptp(x)), np.finfo(float).eps)
    default = span / max(8.0, 3.0 * indices.size)
    if indices.size == 0:
        return np.empty(0, dtype=float)
    try:
        _, _, left_ips, right_ips = peak_widths(detection_signal, indices, rel_height=0.5)
        sample_axis = np.arange(x.size, dtype=float)
        left_x = np.interp(left_ips, sample_axis, x)
        right_x = np.interp(right_ips, sample_axis, x)
        widths = right_x - left_x
        widths = np.where(np.isfinite(widths) & (widths > 0), widths, default)
        return np.asarray(widths, dtype=float)
    except Exception:
        return np.full(indices.size, default, dtype=float)


def _parameter_setup(
    x: np.ndarray,
    corrected: np.ndarray,
    detection_signal: np.ndarray,
    indices: np.ndarray,
    model: str,
    parameter_names: Sequence[str],
    direction: str,
    initial: Mapping[str, float] | None,
    bounds: Mapping[str, tuple[float, float]] | None,
):
    _validate_mapping_keys(initial, "initial", indices.size, parameter_names)
    _validate_mapping_keys(bounds, "bounds", indices.size, parameter_names)
    fwhm_guesses = _initial_widths(x, detection_signal, indices)
    unique_x = np.unique(x)
    positive_steps = np.diff(unique_x)
    min_step = float(np.min(positive_steps[positive_steps > 0]))
    span = max(float(np.ptp(x)), min_step)
    centers = x[indices]
    center_lowers = np.r_[x.min(), (centers[:-1] + centers[1:]) / 2.0]
    center_uppers = np.r_[(centers[:-1] + centers[1:]) / 2.0, x.max()]
    names: list[str] = []
    p0: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    for peak_index, detected_index in enumerate(indices):
        amplitude = float(corrected[detected_index])
        if direction == "positive":
            amp_bounds = (0.0, np.inf)
        elif direction == "negative":
            amp_bounds = (-np.inf, 0.0)
        else:
            amp_bounds = (0.0, np.inf) if amplitude >= 0 else (-np.inf, 0.0)
        fwhm = max(float(fwhm_guesses[peak_index]), min_step)
        defaults = {
            "amplitude": amplitude,
            "center": float(x[detected_index]),
            "sigma": fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0))),
            "gamma": fwhm / 2.0,
        }
        default_bounds = {
            "amplitude": amp_bounds,
            "center": (float(center_lowers[peak_index]), float(center_uppers[peak_index])),
            "sigma": (max(min_step * 1e-3, np.finfo(float).tiny), span * 2.0),
            "gamma": (max(min_step * 1e-3, np.finfo(float).tiny), span * 2.0),
        }
        for parameter in parameter_names:
            key = f"peak{peak_index}.{parameter}"
            lo, hi = default_bounds[parameter]
            requested_bounds = _mapping_value(bounds, peak_index, parameter, None)
            if requested_bounds is not None:
                try:
                    requested_length = len(requested_bounds)
                except TypeError as exc:
                    raise PeakAnalysisError(
                        f"Bounds for {key} require two values"
                    ) from exc
                if requested_length != 2:
                    raise PeakAnalysisError(f"Bounds for {key} require two values")
                lo, hi = map(float, requested_bounds)
            if parameter in _POSITIVE_PARAMETERS:
                if lo < 0 or hi <= 0:
                    raise PeakAnalysisError(
                        f"Bounds for physical width {key} cannot be negative and must allow values above zero"
                    )
                if lo == 0:
                    lo = np.finfo(float).tiny
            if not lo < hi:
                raise PeakAnalysisError(f"Bounds for {key} must satisfy lower < upper")
            value = float(_mapping_value(initial, peak_index, parameter, defaults[parameter]))
            if not np.isfinite(value):
                raise PeakAnalysisError(f"Initial value for {key} must be finite")
            if parameter in _POSITIVE_PARAMETERS and value <= 0:
                raise PeakAnalysisError(
                    f"Initial value for physical width {key} must be positive"
                )
            if value <= lo and np.isfinite(lo):
                value = np.nextafter(lo, hi)
            if value >= hi and np.isfinite(hi):
                value = np.nextafter(hi, lo)
            if not lo < value < hi:
                raise PeakAnalysisError(f"Initial value for {key} lies outside bounds")
            names.append(key)
            p0.append(value)
            lower.append(lo)
            upper.append(hi)
    return (
        tuple(names),
        np.asarray(p0, dtype=float),
        np.asarray(lower, dtype=float),
        np.asarray(upper, dtype=float),
    )


def _component_sum(
    x: np.ndarray,
    theta: np.ndarray,
    function,
    parameter_names: Sequence[str],
) -> np.ndarray:
    count = len(parameter_names)
    result = np.zeros_like(x, dtype=float)
    for start in range(0, theta.size, count):
        result += function(x, *theta[start : start + count])
    if not np.all(np.isfinite(result)):
        raise PeakAnalysisError("Peak model produced non-finite values")
    return result


def _fit_metrics(
    y: np.ndarray,
    fitted: np.ndarray,
    weighted_residuals: np.ndarray,
    parameter_count: int,
) -> FitMetrics:
    n = int(y.size)
    k = int(parameter_count)
    dof = max(0, n - k)
    residual = y - fitted
    rss = float(np.dot(residual, residual))
    chi = float(np.dot(weighted_residuals, weighted_residuals))
    tss = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - rss / tss if tss > 0 else (1.0 if rss <= _EPS else np.nan)
    rmse = float(np.sqrt(rss / n))
    objective = max(chi, np.finfo(float).tiny)
    aic = float(n * np.log(objective / n) + 2.0 * k)
    bic = float(n * np.log(objective / n) + k * np.log(n))
    reduced = chi / dof if dof > 0 else np.nan
    return FitMetrics(n, k, dof, rss, chi, float(reduced), float(r2), rmse, aic, bic)


def _covariance(jacobian: np.ndarray, chi_square: float, dof: int, absolute_sigma: bool):
    if np.linalg.matrix_rank(jacobian) < jacobian.shape[1]:
        return np.full((jacobian.shape[1], jacobian.shape[1]), np.nan)
    try:
        covariance = np.linalg.pinv(jacobian.T @ jacobian, hermitian=True)
    except np.linalg.LinAlgError:
        return np.full((jacobian.shape[1], jacobian.shape[1]), np.nan)
    if not absolute_sigma:
        covariance *= chi_square / dof if dof > 0 else np.nan
    return np.asarray((covariance + covariance.T) / 2.0, dtype=float)


def _correlation(covariance: np.ndarray) -> np.ndarray:
    if covariance.size == 0:
        return covariance.copy()
    standard = np.sqrt(np.clip(np.diag(covariance), 0.0, np.inf))
    with np.errstate(divide="ignore", invalid="ignore"):
        result = covariance / np.outer(standard, standard)
    result[~np.isfinite(result)] = np.nan
    np.fill_diagonal(result, np.where(standard > 0, 1.0, np.nan))
    return result


def _numeric_gradient(function, theta: np.ndarray, lower: np.ndarray, upper: np.ndarray):
    base = np.asarray(function(theta), dtype=float)
    gradient = np.empty((base.size, theta.size), dtype=float)
    for index, value in enumerate(theta):
        step = np.sqrt(_EPS) * max(1.0, abs(float(value)))
        forward = min(value + step, upper[index])
        backward = max(value - step, lower[index])
        if forward > value and backward < value:
            plus, minus = theta.copy(), theta.copy()
            plus[index], minus[index] = forward, backward
            gradient[:, index] = (
                np.asarray(function(plus)).reshape(-1)
                - np.asarray(function(minus)).reshape(-1)
            ) / (forward - backward)
        elif forward > value:
            plus = theta.copy()
            plus[index] = forward
            gradient[:, index] = (
                np.asarray(function(plus)).reshape(-1) - base.reshape(-1)
            ) / (forward - value)
        elif backward < value:
            minus = theta.copy()
            minus[index] = backward
            gradient[:, index] = (
                base.reshape(-1) - np.asarray(function(minus)).reshape(-1)
            ) / (value - backward)
        else:
            gradient[:, index] = 0.0
    return gradient


def _voigt_fwhm(sigma: float, gamma: float) -> float:
    gaussian_width = 2.0 * np.sqrt(2.0 * np.log(2.0)) * abs(sigma)
    lorentz_width = 2.0 * abs(gamma)
    return float(
        0.5346 * lorentz_width
        + np.sqrt(0.2166 * lorentz_width**2 + gaussian_width**2)
    )


def _derived_peak_values(
    peak_index: int,
    theta: np.ndarray,
    model: str,
    parameter_names: Sequence[str],
    x: np.ndarray,
    baseline: np.ndarray,
) -> np.ndarray:
    count = len(parameter_names)
    params = {
        name: float(value)
        for name, value in zip(
            parameter_names, theta[peak_index * count : (peak_index + 1) * count]
        )
    }
    amplitude = params["amplitude"]
    center = params["center"]
    baseline_center = float(np.interp(center, x, baseline))
    height = baseline_center + amplitude
    if model == "gaussian":
        sigma = abs(params["sigma"])
        fwhm = 2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma
        area = amplitude * sigma * np.sqrt(2.0 * np.pi)
    elif model == "lorentzian":
        gamma = abs(params["gamma"])
        fwhm = 2.0 * gamma
        area = amplitude * np.pi * gamma
    else:
        sigma = abs(params["sigma"])
        gamma = abs(params["gamma"])
        fwhm = _voigt_fwhm(sigma, gamma)
        peak_density = float(voigt_profile(0.0, sigma, gamma))
        area = amplitude / max(peak_density, np.finfo(float).tiny)
    return np.asarray([center, height, amplitude, fwhm, area], dtype=float)


def _empty_result(
    prepared: _PreparedPeakData,
    model: str,
    baseline_method: str,
    direction: str,
    baseline: np.ndarray,
    baseline_parameter_count: int,
    confidence_level: float,
) -> PeakAnalysisResult:
    fitted = baseline.copy()
    residuals = prepared.y - fitted
    weighted = residuals * prepared.scale
    metrics = _fit_metrics(prepared.y, fitted, weighted, baseline_parameter_count)
    empty = np.empty(0, dtype=float)
    return PeakAnalysisResult(
        model,
        baseline_method,
        direction,
        True,
        "No peaks detected",
        prepared.x.copy(),
        prepared.y.copy(),
        prepared.original_indices.copy(),
        np.empty(0, dtype=int),
        baseline,
        prepared.y - baseline,
        np.zeros_like(prepared.y),
        fitted,
        residuals,
        weighted,
        None,
        None,
        (),
        (),
        {},
        {},
        {},
        np.empty((0, 0), dtype=float),
        np.empty((0, 0), dtype=float),
        metrics,
        0,
        float(confidence_level),
    )


def analyze_peaks(
    x: ArrayLike,
    y: ArrayLike,
    *,
    model: str = "gaussian",
    baseline: str = "linear",
    direction: str = "positive",
    peak_indices: Sequence[int] | None = None,
    prominence: float | None = None,
    height: float | None = None,
    distance: int | None = None,
    width: float | None = None,
    max_peaks: int | None = 20,
    initial: Mapping[str, float] | None = None,
    bounds: Mapping[str, tuple[float, float]] | None = None,
    sigma: ArrayLike | None = None,
    weights: ArrayLike | None = None,
    absolute_sigma: bool = False,
    confidence: float = 0.95,
    constant_quantile: float = 0.1,
    als_lambda: float = 1e5,
    als_p: float = 0.01,
    als_iterations: int = 10,
    max_nfev: int = 50_000,
    cancel_check: CancelCheck | None = None,
) -> PeakAnalysisResult:
    """Detect and simultaneously fit peaks on a fixed estimated baseline."""

    _check_cancelled(cancel_check)
    if not 0.0 < confidence < 1.0:
        raise PeakAnalysisError("confidence must be between 0 and 1")
    if max_nfev <= 0:
        raise PeakAnalysisError("max_nfev must be positive")
    model_key, function, parameter_names = _normalise_peak_model(model)
    baseline_key, direction_key = _validate_baseline_direction(baseline, direction)
    prepared = _prepare_peak_data(x, y, sigma=sigma, weights=weights)
    _check_cancelled(cancel_check)
    sign = -1.0 if direction_key == "negative" else 1.0
    baseline_y = sign * _baseline_array(
        prepared.x,
        sign * prepared.y,
        baseline,
        constant_quantile=constant_quantile,
        als_lambda=als_lambda,
        als_p=als_p,
        als_iterations=als_iterations,
        cancel_check=cancel_check,
    )
    corrected = prepared.y - baseline_y
    detection_signal = _detection_signal(corrected, direction_key)
    if peak_indices is None:
        indices, _ = _find_peak_indices(
            detection_signal,
            prominence=prominence,
            height=height,
            distance=distance,
            width=width,
            max_peaks=max_peaks,
        )
    else:
        indices = np.asarray(peak_indices, dtype=int).reshape(-1)
        if indices.size and (np.any(indices < 0) or np.any(indices >= prepared.x.size)):
            raise PeakAnalysisError("peak_indices refer outside the finite, sorted data")
        indices = np.unique(indices)
    _check_cancelled(cancel_check)
    baseline_parameter_count = 0 if baseline_key in {"none", "zero", *_ALS_BASELINES} else (1 if baseline_key in {"constant", "const"} else 2)
    if indices.size == 0:
        return _empty_result(
            prepared,
            model_key,
            baseline_key,
            direction_key,
            baseline_y,
            baseline_parameter_count,
            confidence,
        )
    max_fittable = (prepared.x.size - baseline_parameter_count - 1) // len(parameter_names)
    if indices.size > max_fittable:
        if peak_indices is not None:
            raise PeakAnalysisError("Too many requested peaks for the available observations")
        strengths = detection_signal[indices]
        indices = np.sort(indices[np.argsort(strengths)[-max_fittable:]])
    names, p0, lower, upper = _parameter_setup(
        prepared.x,
        corrected,
        detection_signal,
        indices,
        model_key,
        parameter_names,
        direction_key,
        initial,
        bounds,
    )
    _check_cancelled(cancel_check)

    def component(theta: np.ndarray) -> np.ndarray:
        return _component_sum(prepared.x, theta, function, parameter_names)

    def residual(theta: np.ndarray) -> np.ndarray:
        return (corrected - component(theta)) * prepared.scale

    def cancellation_callback(_intermediate_result) -> None:
        _check_cancelled(cancel_check)

    try:
        optimisation = least_squares(
            residual,
            p0,
            bounds=(lower, upper),
            method="trf",
            jac="2-point",
            x_scale="jac",
            loss="linear",
            max_nfev=int(max_nfev),
            callback=cancellation_callback if cancel_check is not None else None,
        )
    except PeakAnalysisError:
        raise
    except Exception as exc:
        raise PeakAnalysisError(f"Multi-peak fitting failed: {exc}") from exc
    _check_cancelled(cancel_check)
    theta = np.asarray(optimisation.x, dtype=float)
    peak_component = component(theta)
    fitted = baseline_y + peak_component
    residuals = prepared.y - fitted
    weighted = residuals * prepared.scale
    total_parameter_count = theta.size + baseline_parameter_count
    metrics = _fit_metrics(prepared.y, fitted, weighted, total_parameter_count)
    covariance = _covariance(
        np.asarray(optimisation.jac, dtype=float),
        metrics.chi_square,
        metrics.degrees_of_freedom,
        bool(absolute_sigma),
    )
    correlation = _correlation(covariance)
    alpha = 1.0 - confidence
    critical = float(student_t.ppf(1.0 - alpha / 2.0, max(1, metrics.degrees_of_freedom)))
    if not np.isfinite(critical):
        critical = 1.959963984540054
    diagonal = np.diag(covariance)
    errors = np.sqrt(np.where(diagonal >= 0, diagonal, np.nan))
    parameters = {name: float(value) for name, value in zip(names, theta)}
    stderr = {name: float(error) for name, error in zip(names, errors)}
    ci95 = {
        name: (
            float(value - critical * error),
            float(value + critical * error),
        )
        if np.isfinite(error)
        else (np.nan, np.nan)
        for name, value, error in zip(names, theta, errors)
    }
    lower_band = upper_band = None
    covariance_usable = covariance.size > 0 and np.all(np.isfinite(covariance))
    if covariance_usable:
        prediction_gradient = _numeric_gradient(component, theta, lower, upper)
        pred_variance = np.einsum(
            "ij,jk,ik->i", prediction_gradient, covariance, prediction_gradient, optimize=True
        )
        pred_standard = np.sqrt(np.clip(pred_variance, 0.0, np.inf))
        lower_band = fitted - critical * pred_standard
        upper_band = fitted + critical * pred_standard

    peak_metrics: list[PeakMetric] = []
    parameter_count = len(parameter_names)
    for peak_index, detected_index in enumerate(indices):
        derived = _derived_peak_values(
            peak_index, theta, model_key, parameter_names, prepared.x, baseline_y
        )
        if covariance_usable:
            metric_function = lambda values, i=peak_index: _derived_peak_values(
                i, values, model_key, parameter_names, prepared.x, baseline_y
            )
            derived_gradient = _numeric_gradient(metric_function, theta, lower, upper)
            derived_variance = np.einsum(
                "ij,jk,ik->i",
                derived_gradient,
                covariance,
                derived_gradient,
                optimize=True,
            )
            derived_error = np.sqrt(np.clip(derived_variance, 0.0, np.inf))
        else:
            derived_error = np.full(5, np.nan)
        derived_ci = [
            (float(value - critical * error), float(value + critical * error))
            if np.isfinite(error)
            else (np.nan, np.nan)
            for value, error in zip(derived, derived_error)
        ]
        start = peak_index * parameter_count
        stop = start + parameter_count
        local_names = names[start:stop]
        local_params = {
            parameter: float(value)
            for parameter, value in zip(parameter_names, theta[start:stop])
        }
        local_stderr = {
            parameter: stderr[name]
            for parameter, name in zip(parameter_names, local_names)
        }
        local_ci = {
            parameter: ci95[name]
            for parameter, name in zip(parameter_names, local_names)
        }
        peak_metrics.append(
            PeakMetric(
                peak_index + 1,
                int(detected_index),
                model_key,
                float(derived[0]),
                float(derived[1]),
                float(derived[2]),
                float(derived[3]),
                float(derived[4]),
                derived_ci[0],
                derived_ci[1],
                derived_ci[2],
                derived_ci[3],
                derived_ci[4],
                local_params,
                local_stderr,
                local_ci,
            )
        )
    return PeakAnalysisResult(
        model_key,
        baseline_key,
        direction_key,
        bool(optimisation.success),
        str(optimisation.message),
        prepared.x.copy(),
        prepared.y.copy(),
        prepared.original_indices.copy(),
        indices.copy(),
        baseline_y,
        corrected,
        peak_component,
        fitted,
        residuals,
        weighted,
        lower_band,
        upper_band,
        tuple(peak_metrics),
        names,
        parameters,
        stderr,
        ci95,
        covariance,
        correlation,
        metrics,
        int(optimisation.nfev),
        float(confidence),
    )


def fit_peaks(
    x: ArrayLike,
    y: ArrayLike,
    peak_indices: Sequence[int],
    **kwargs,
) -> PeakAnalysisResult:
    """Fit caller-specified peaks; a convenience wrapper around analyze_peaks."""

    return analyze_peaks(x, y, peak_indices=peak_indices, **kwargs)


def analyze_peaks_batch(
    frame: pd.DataFrame,
    x_column: str,
    y_columns: Sequence[str] | None = None,
    *,
    continue_on_error: bool = True,
    **kwargs,
) -> PeakBatchResult:
    """Analyze multiple Y columns and concatenate their peak summaries."""

    if not isinstance(frame, pd.DataFrame):
        raise PeakAnalysisError("frame must be a pandas DataFrame")
    if x_column not in frame.columns:
        raise PeakAnalysisError(f"Unknown X column: {x_column}")
    if y_columns is None:
        column_labels = [
            column
            for column in frame.select_dtypes(include=[np.number]).columns
            if column != x_column
        ]
    else:
        column_labels = list(y_columns)
    if not column_labels:
        raise PeakAnalysisError("At least one Y column is required")
    missing = [label for label in column_labels if label not in frame.columns]
    if missing:
        raise PeakAnalysisError(
            f"Unknown Y column(s): {', '.join(map(str, missing))}"
        )
    results: dict[str, PeakAnalysisResult] = {}
    errors: dict[str, str] = {}
    summaries: list[pd.DataFrame] = []
    x_values = frame[x_column].to_numpy()
    for label in column_labels:
        name = str(label)
        try:
            result = analyze_peaks(x_values, frame[label].to_numpy(), **kwargs)
        except Exception as exc:
            if not continue_on_error:
                raise
            errors[name] = str(exc)
            continue
        results[name] = result
        summaries.append(result.to_frame(dataset=name))
    if summaries:
        summary = pd.concat(summaries, ignore_index=True)
    else:
        summary = pd.DataFrame(columns=["dataset", *_SUMMARY_COLUMNS])
    if not summary.empty:
        summary.insert(1, "x_column", x_column)
    else:
        summary.insert(1, "x_column", pd.Series(dtype="object"))
    return PeakBatchResult(results, summary, errors)


__all__ = [
    "PeakAnalysisError",
    "PeakAnalysisResult",
    "PeakBatchResult",
    "PeakMetric",
    "analyze_peaks",
    "analyze_peaks_batch",
    "detect_peaks",
    "estimate_baseline",
    "fit_peaks",
    "gaussian_peak",
    "lorentzian_peak",
    "voigt_peak",
]
