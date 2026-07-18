"""Pure simultaneous/global nonlinear fitting for scientific datasets.

The module deliberately has no Qt dependency.  A *global* fit optimises all
datasets in one residual vector while allowing any model parameter to be shared
between datasets or estimated independently for each dataset.

Custom callables use the positional contract ``f(x, *parameters)``; the order
is supplied with ``parameter_names``.  Built-in peak amplitudes are heights
above ``offset`` and all width parameters are constrained positive by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np
from scipy.optimize import least_squares
from scipy.special import voigt_profile
from scipy.stats import t as student_t


ArrayLike = Sequence[float] | np.ndarray
ModelCallable = Callable[..., np.ndarray]
CancelCheck = Callable[[], bool]
_EPS = np.finfo(float).eps
_POSITIVE_PARAMETERS = frozenset({"sigma", "gamma", "tau"})


class GlobalFitError(ValueError):
    """Raised when a global-fit request is scientifically invalid."""


@dataclass(frozen=True)
class GlobalFitDataset:
    """One dataset supplied to :func:`global_fit`.

    ``sigma`` contains absolute standard uncertainties. ``weights`` contains
    direct least-squares weights (normally inverse variances).  They are
    mutually exclusive.  Non-finite rows are removed as aligned rows and the
    remaining observations are sorted by X before fitting.
    """

    x: ArrayLike
    y: ArrayLike
    name: str = ""
    sigma: ArrayLike | None = None
    weights: ArrayLike | None = None


# Short public spelling for callers constructing many datasets.
FitDataset = GlobalFitDataset


@dataclass(frozen=True)
class FitMetrics:
    n_observations: int
    n_parameters: int
    degrees_of_freedom: int
    rss: float
    chi_square: float
    reduced_chi_square: float
    r_squared: float
    rmse: float
    aic: float
    bic: float


@dataclass(frozen=True)
class DatasetFitResult:
    name: str
    x: np.ndarray
    y: np.ndarray
    original_indices: np.ndarray
    parameters: dict[str, float]
    fitted: np.ndarray
    residuals: np.ndarray
    weighted_residuals: np.ndarray
    ci95_lower: np.ndarray | None
    ci95_upper: np.ndarray | None
    metrics: FitMetrics

    @property
    def r2(self) -> float:
        return self.metrics.r_squared

    @property
    def rmse(self) -> float:
        return self.metrics.rmse

    @property
    def yfit(self) -> np.ndarray:
        return self.fitted


@dataclass(frozen=True)
class GlobalFitResult:
    model: str
    success: bool
    message: str
    parameter_order: tuple[str, ...]
    parameters: dict[str, float]
    stderr: dict[str, float]
    ci95: dict[str, tuple[float, float]]
    covariance: np.ndarray
    correlation: np.ndarray
    datasets: tuple[DatasetFitResult, ...]
    metrics: FitMetrics
    nfev: int
    cost: float
    confidence_level: float = 0.95

    @property
    def params(self) -> dict[str, float]:
        """Compatibility alias used by the existing fitting code."""

        return self.parameters

    @property
    def r2(self) -> float:
        return self.metrics.r_squared

    @property
    def rmse(self) -> float:
        return self.metrics.rmse

    @property
    def reduced_chi_square(self) -> float:
        return self.metrics.reduced_chi_square

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
    def cov(self) -> np.ndarray:
        return self.covariance

    @property
    def residuals(self) -> np.ndarray:
        return np.concatenate([dataset.residuals for dataset in self.datasets])

    @property
    def shared_parameters(self) -> dict[str, float]:
        return {key: value for key, value in self.parameters.items() if "." not in key}

    @property
    def dataset_parameters(self) -> dict[str, dict[str, float]]:
        return {dataset.name: dict(dataset.parameters) for dataset in self.datasets}


@dataclass(frozen=True)
class _ModelSpec:
    name: str
    function: ModelCallable
    parameter_names: tuple[str, ...]


@dataclass(frozen=True)
class _PreparedDataset:
    name: str
    x: np.ndarray
    y: np.ndarray
    original_indices: np.ndarray
    scale: np.ndarray


@dataclass(frozen=True)
class _ParameterSlot:
    key: str
    parameter: str
    dataset_name: str | None
    initial: float
    lower: float
    upper: float
    fixed: float | None


def gaussian_model(
    x: ArrayLike,
    amplitude: float,
    center: float,
    sigma: float,
    offset: float,
) -> np.ndarray:
    """Gaussian whose ``amplitude`` is peak height above ``offset``."""

    x_arr = np.asarray(x, dtype=float)
    width = max(abs(float(sigma)), np.finfo(float).tiny)
    return offset + amplitude * np.exp(-0.5 * ((x_arr - center) / width) ** 2)


def lorentzian_model(
    x: ArrayLike,
    amplitude: float,
    center: float,
    gamma: float,
    offset: float,
) -> np.ndarray:
    """Lorentzian whose ``gamma`` is half width at half maximum."""

    x_arr = np.asarray(x, dtype=float)
    width = max(abs(float(gamma)), np.finfo(float).tiny)
    return offset + amplitude * width**2 / ((x_arr - center) ** 2 + width**2)


def voigt_model(
    x: ArrayLike,
    amplitude: float,
    center: float,
    sigma: float,
    gamma: float,
    offset: float,
) -> np.ndarray:
    """Exact Voigt profile normalised so ``amplitude`` is peak height."""

    x_arr = np.asarray(x, dtype=float)
    sigma_pos = max(abs(float(sigma)), np.finfo(float).tiny)
    gamma_pos = max(abs(float(gamma)), np.finfo(float).tiny)
    raw = voigt_profile(x_arr - center, sigma_pos, gamma_pos)
    at_center = float(voigt_profile(0.0, sigma_pos, gamma_pos))
    return offset + amplitude * raw / max(at_center, np.finfo(float).tiny)


def exponential_model(
    x: ArrayLike,
    amplitude: float,
    rate: float,
    offset: float,
) -> np.ndarray:
    """General exponential ``offset + amplitude * exp(rate * x)``."""

    x_arr = np.asarray(x, dtype=float)
    return offset + amplitude * np.exp(np.clip(rate * x_arr, -700.0, 700.0))


def exponential_decay_model(
    x: ArrayLike,
    amplitude: float,
    tau: float,
    offset: float,
) -> np.ndarray:
    """Exponential decay ``offset + amplitude * exp(-x/tau)``."""

    x_arr = np.asarray(x, dtype=float)
    tau_pos = max(abs(float(tau)), np.finfo(float).tiny)
    return offset + amplitude * np.exp(np.clip(-x_arr / tau_pos, -700.0, 700.0))


_MODELS: dict[str, _ModelSpec] = {
    "gaussian": _ModelSpec(
        "gaussian", gaussian_model, ("amplitude", "center", "sigma", "offset")
    ),
    "lorentzian": _ModelSpec(
        "lorentzian",
        lorentzian_model,
        ("amplitude", "center", "gamma", "offset"),
    ),
    "voigt": _ModelSpec(
        "voigt",
        voigt_model,
        ("amplitude", "center", "sigma", "gamma", "offset"),
    ),
    "exponential": _ModelSpec(
        "exponential", exponential_model, ("amplitude", "rate", "offset")
    ),
    "exp": _ModelSpec(
        "exponential", exponential_model, ("amplitude", "rate", "offset")
    ),
    "exponential_decay": _ModelSpec(
        "exponential_decay",
        exponential_decay_model,
        ("amplitude", "tau", "offset"),
    ),
    "exp_decay": _ModelSpec(
        "exponential_decay",
        exponential_decay_model,
        ("amplitude", "tau", "offset"),
    ),
}


def list_global_models() -> tuple[str, ...]:
    """Return canonical names of the built-in global-fit models."""

    return ("gaussian", "lorentzian", "voigt", "exponential", "exponential_decay")


def _normalise_model(
    model: str | ModelCallable,
    parameter_names: Sequence[str] | None,
) -> _ModelSpec:
    if isinstance(model, str):
        key = model.strip().lower().replace("-", "_").replace(" ", "_")
        try:
            return _MODELS[key]
        except KeyError as exc:
            raise GlobalFitError(f"Unknown global-fit model: {model!r}") from exc
    if not callable(model):
        raise GlobalFitError("model must be a built-in name or callable")
    names = tuple(str(name).strip() for name in (parameter_names or ()))
    if not names or any(not name for name in names):
        raise GlobalFitError("parameter_names are required for a custom callable")
    if len(set(names)) != len(names):
        raise GlobalFitError("parameter_names must be unique")
    return _ModelSpec(getattr(model, "__name__", "custom"), model, names)


def _coerce_dataset(value, index: int) -> GlobalFitDataset:
    if isinstance(value, GlobalFitDataset):
        dataset = value
    elif isinstance(value, Mapping):
        try:
            dataset = GlobalFitDataset(
                x=value["x"],
                y=value["y"],
                name=str(value.get("name", "")),
                sigma=value.get("sigma"),
                weights=value.get("weights"),
            )
        except KeyError as exc:
            raise GlobalFitError("Each dataset mapping requires x and y") from exc
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        dataset = GlobalFitDataset(value[0], value[1])
    elif isinstance(value, (tuple, list)) and len(value) == 3 and isinstance(value[0], str):
        dataset = GlobalFitDataset(value[1], value[2], name=value[0])
    else:
        raise GlobalFitError(
            "Datasets must be GlobalFitDataset, {x, y} mappings, or (x, y) pairs"
        )
    name = dataset.name.strip() or f"dataset_{index + 1}"
    return GlobalFitDataset(dataset.x, dataset.y, name, dataset.sigma, dataset.weights)


def _prepare_dataset(dataset: GlobalFitDataset) -> _PreparedDataset:
    if dataset.sigma is not None and dataset.weights is not None:
        raise GlobalFitError(f"{dataset.name}: sigma and weights are mutually exclusive")
    try:
        x = np.asarray(dataset.x, dtype=float).reshape(-1)
        y = np.asarray(dataset.y, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise GlobalFitError(f"{dataset.name}: X and Y must be numeric") from exc
    if x.size != y.size:
        raise GlobalFitError(f"{dataset.name}: X and Y lengths differ")
    if x.size == 0:
        raise GlobalFitError(f"{dataset.name}: dataset is empty")
    original = np.arange(x.size, dtype=int)
    mask = np.isfinite(x) & np.isfinite(y)
    scale = np.ones(x.size, dtype=float)
    auxiliary = dataset.sigma if dataset.sigma is not None else dataset.weights
    if auxiliary is not None:
        try:
            aux = np.asarray(auxiliary, dtype=float).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise GlobalFitError(
                f"{dataset.name}: uncertainty/weights must be numeric"
            ) from exc
        if aux.size != x.size:
            raise GlobalFitError(f"{dataset.name}: uncertainty/weight length differs")
        invalid_positive = mask & np.isfinite(aux) & (aux <= 0)
        if np.any(invalid_positive):
            label = "sigma" if dataset.sigma is not None else "weights"
            raise GlobalFitError(f"{dataset.name}: {label} must be positive")
        mask &= np.isfinite(aux)
        if dataset.sigma is not None:
            scale = 1.0 / aux
        else:
            scale = np.sqrt(aux)
    x = x[mask]
    y = y[mask]
    scale = scale[mask]
    original = original[mask]
    if x.size < 3:
        raise GlobalFitError(f"{dataset.name}: at least 3 finite observations are required")
    if np.unique(x).size < 2:
        raise GlobalFitError(f"{dataset.name}: X must contain at least two distinct values")
    order = np.argsort(x, kind="mergesort")
    return _PreparedDataset(
        dataset.name,
        x[order],
        y[order],
        original[order],
        scale[order],
    )


def _guess_parameters(spec: _ModelSpec, dataset: _PreparedDataset) -> dict[str, float]:
    x, y = dataset.x, dataset.y
    span = max(float(np.ptp(x)), np.finfo(float).eps)
    # Edge samples are a better peak baseline than a low quantile: a quantile
    # systematically mistakes a negative peak for the offset and starts the
    # optimiser on a spurious positive peak elsewhere in the domain.
    edge_count = max(2, min(y.size // 4, y.size // 10))
    baseline = float(np.median(np.r_[y[:edge_count], y[-edge_count:]]))
    deviation = y - baseline
    peak_index = int(np.argmax(np.abs(deviation)))
    amplitude = float(deviation[peak_index])
    guesses = {name: 1.0 for name in spec.parameter_names}
    guesses.update(
        amplitude=amplitude if amplitude != 0 else 1.0,
        center=float(x[peak_index]),
        sigma=span / 6.0,
        gamma=span / 6.0,
        offset=baseline,
        rate=-1.0 / span,
        tau=span / 3.0,
    )
    return {name: float(guesses[name]) for name in spec.parameter_names}


def _qualified(dataset_name: str, parameter: str) -> str:
    return f"{dataset_name}.{parameter}"


def _mapping_value(
    mapping: Mapping[str, object] | None,
    dataset_name: str | None,
    parameter: str,
    default,
):
    if not mapping:
        return default
    if dataset_name is not None:
        key = _qualified(dataset_name, parameter)
        if key in mapping:
            return mapping[key]
    return mapping.get(parameter, default)


def _default_bounds(
    parameter: str,
    datasets: Sequence[_PreparedDataset],
    dataset_name: str | None,
) -> tuple[float, float]:
    relevant = (
        datasets
        if dataset_name is None
        else [dataset for dataset in datasets if dataset.name == dataset_name]
    )
    x_min = min(float(dataset.x.min()) for dataset in relevant)
    x_max = max(float(dataset.x.max()) for dataset in relevant)
    span = max(x_max - x_min, np.finfo(float).eps)
    if parameter == "center":
        return x_min, x_max
    if parameter in _POSITIVE_PARAMETERS:
        return max(span * 1e-12, np.finfo(float).tiny), np.inf
    return -np.inf, np.inf


def _validate_configuration_keys(
    mapping: Mapping[str, object] | None,
    label: str,
    spec: _ModelSpec,
    datasets: Sequence[_PreparedDataset],
    shared: set[str],
) -> None:
    if not mapping:
        return
    valid = set(spec.parameter_names)
    for dataset in datasets:
        valid.update(
            _qualified(dataset.name, parameter)
            for parameter in spec.parameter_names
            if parameter not in shared
        )
    unknown = sorted(str(key) for key in mapping if key not in valid)
    if unknown:
        raise GlobalFitError(f"Unknown {label} parameter key(s): {', '.join(unknown)}")


def _safe_initial(value: float, lower: float, upper: float, key: str) -> float:
    if not np.isfinite(value):
        raise GlobalFitError(f"Initial value for {key} must be finite")
    if not lower < upper:
        raise GlobalFitError(f"Bounds for {key} must satisfy lower < upper")
    if value <= lower:
        if np.isfinite(lower):
            value = np.nextafter(lower, upper)
    if value >= upper:
        if np.isfinite(upper):
            value = np.nextafter(upper, lower)
    if not lower < value < upper:
        raise GlobalFitError(f"Initial value for {key} is outside its bounds")
    return float(value)


def _check_cancelled(cancel_check: CancelCheck | None, operation: str) -> None:
    """Raise the public domain error when a caller requests cancellation."""

    if cancel_check is None:
        return
    if not callable(cancel_check):
        raise GlobalFitError("cancel_check must be callable")
    try:
        cancelled = bool(cancel_check())
    except GlobalFitError:
        raise
    except Exception as exc:
        raise GlobalFitError(f"cancel_check failed: {exc}") from exc
    if cancelled:
        raise GlobalFitError(f"{operation} cancelled")


def _positive_parameter_bounds(
    parameter: str,
    key: str,
    lower: float,
    upper: float,
) -> tuple[float, float]:
    """Validate physical-width bounds and make an allowed zero bound strict."""

    if parameter not in _POSITIVE_PARAMETERS:
        return lower, upper
    if lower < 0 or upper <= 0:
        raise GlobalFitError(
            f"Bounds for physical width {key} cannot be negative and must allow values above zero"
        )
    # A user-facing lower bound of zero is meaningful, but a fitted width of
    # exactly zero is singular.  Use the smallest positive floating value as
    # the numerical bound while preserving the requested domain.
    if lower == 0:
        lower = np.finfo(float).tiny
    return lower, upper


def _build_slots(
    spec: _ModelSpec,
    datasets: Sequence[_PreparedDataset],
    shared: set[str],
    initial: Mapping[str, float] | None,
    fixed: Mapping[str, float] | None,
    bounds: Mapping[str, tuple[float, float]] | None,
) -> tuple[_ParameterSlot, ...]:
    for mapping, label in ((initial, "initial"), (fixed, "fixed"), (bounds, "bounds")):
        _validate_configuration_keys(mapping, label, spec, datasets, shared)
    guesses = {dataset.name: _guess_parameters(spec, dataset) for dataset in datasets}
    slots: list[_ParameterSlot] = []
    for parameter in spec.parameter_names:
        targets: list[str | None] = [None] if parameter in shared else [d.name for d in datasets]
        for dataset_name in targets:
            key = parameter if dataset_name is None else _qualified(dataset_name, parameter)
            if dataset_name is None:
                default = float(np.median([g[parameter] for g in guesses.values()]))
            else:
                default = guesses[dataset_name][parameter]
            guess = float(_mapping_value(initial, dataset_name, parameter, default))
            lower, upper = _default_bounds(parameter, datasets, dataset_name)
            requested_bounds = _mapping_value(bounds, dataset_name, parameter, None)
            if requested_bounds is not None:
                try:
                    requested_length = len(requested_bounds)
                except TypeError as exc:
                    raise GlobalFitError(
                        f"Bounds for {key} must be a (lower, upper) pair"
                    ) from exc
                if requested_length != 2:
                    raise GlobalFitError(f"Bounds for {key} must be a (lower, upper) pair")
                lower, upper = map(float, requested_bounds)
            lower, upper = _positive_parameter_bounds(
                parameter, key, float(lower), float(upper)
            )
            fixed_value_raw = _mapping_value(fixed, dataset_name, parameter, None)
            fixed_value = None if fixed_value_raw is None else float(fixed_value_raw)
            if fixed_value is not None:
                if parameter in _POSITIVE_PARAMETERS and fixed_value <= 0:
                    raise GlobalFitError(
                        f"Fixed value for physical width {key} must be positive"
                    )
                if not np.isfinite(fixed_value) or not lower <= fixed_value <= upper:
                    raise GlobalFitError(f"Fixed value for {key} is invalid or outside bounds")
                guess = fixed_value
            else:
                if parameter in _POSITIVE_PARAMETERS and guess <= 0:
                    raise GlobalFitError(
                        f"Initial value for physical width {key} must be positive"
                    )
                guess = _safe_initial(guess, lower, upper, key)
            slots.append(
                _ParameterSlot(
                    key, parameter, dataset_name, guess, float(lower), float(upper), fixed_value
                )
            )
    return tuple(slots)


def _evaluate_model(spec: _ModelSpec, x: np.ndarray, parameters: Mapping[str, float]) -> np.ndarray:
    values = [parameters[name] for name in spec.parameter_names]
    try:
        result = np.asarray(spec.function(x, *values), dtype=float)
    except Exception as exc:
        raise GlobalFitError(f"Model evaluation failed: {exc}") from exc
    if result.shape == ():
        result = np.full(x.shape, float(result), dtype=float)
    if result.shape != x.shape:
        raise GlobalFitError(
            f"Model returned shape {result.shape}; expected the same shape as X ({x.shape})"
        )
    if not np.all(np.isfinite(result)):
        raise GlobalFitError("Model produced non-finite values")
    return result


def _parameter_values(
    theta: np.ndarray,
    free_slots: Sequence[_ParameterSlot],
    slots: Sequence[_ParameterSlot],
) -> dict[str, float]:
    free = {slot.key: float(value) for slot, value in zip(free_slots, theta)}
    return {
        slot.key: (float(slot.fixed) if slot.fixed is not None else free[slot.key])
        for slot in slots
    }


def _dataset_parameters(
    dataset: _PreparedDataset,
    spec: _ModelSpec,
    shared: set[str],
    values: Mapping[str, float],
) -> dict[str, float]:
    return {
        parameter: values[
            parameter if parameter in shared else _qualified(dataset.name, parameter)
        ]
        for parameter in spec.parameter_names
    }


def _metrics(
    y: np.ndarray,
    fitted: np.ndarray,
    weighted_residuals: np.ndarray,
    n_parameters: int,
) -> FitMetrics:
    residuals = y - fitted
    n = int(y.size)
    k = int(n_parameters)
    dof = max(0, n - k)
    rss = float(np.dot(residuals, residuals))
    chi_square = float(np.dot(weighted_residuals, weighted_residuals))
    tss = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - rss / tss if tss > 0 else (1.0 if rss <= _EPS else np.nan)
    rmse = float(np.sqrt(rss / n))
    objective = max(chi_square, np.finfo(float).tiny)
    aic = float(n * np.log(objective / n) + 2.0 * k)
    bic = float(n * np.log(objective / n) + k * np.log(n))
    reduced = chi_square / dof if dof > 0 else np.nan
    return FitMetrics(n, k, dof, rss, chi_square, float(reduced), float(r2), rmse, aic, bic)


def _covariance_from_jacobian(
    jacobian: np.ndarray,
    chi_square: float,
    dof: int,
    absolute_sigma: bool,
) -> np.ndarray:
    n_params = jacobian.shape[1]
    if n_params == 0:
        return np.empty((0, 0), dtype=float)
    if np.linalg.matrix_rank(jacobian) < n_params:
        # A pseudo-inverse can otherwise manufacture deceptively tiny errors
        # for parameters that the data do not identify.
        return np.full((n_params, n_params), np.nan, dtype=float)
    try:
        covariance = np.linalg.pinv(jacobian.T @ jacobian, hermitian=True)
    except np.linalg.LinAlgError:
        return np.full((n_params, n_params), np.nan, dtype=float)
    if not absolute_sigma:
        covariance *= chi_square / dof if dof > 0 else np.nan
    covariance = (covariance + covariance.T) / 2.0
    return np.asarray(covariance, dtype=float)


def _correlation(covariance: np.ndarray) -> np.ndarray:
    if covariance.size == 0:
        return covariance.copy()
    standard = np.sqrt(np.clip(np.diag(covariance), 0.0, np.inf))
    denom = np.outer(standard, standard)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = covariance / denom
    corr[~np.isfinite(corr)] = np.nan
    np.fill_diagonal(corr, np.where(standard > 0, 1.0, np.nan))
    return corr


def _prediction_gradient(
    theta: np.ndarray,
    dataset: _PreparedDataset,
    predict: Callable[[np.ndarray, _PreparedDataset], np.ndarray],
    lower: np.ndarray,
    upper: np.ndarray,
) -> np.ndarray:
    base = predict(theta, dataset)
    gradient = np.empty((dataset.x.size, theta.size), dtype=float)
    for index, value in enumerate(theta):
        step = np.sqrt(_EPS) * max(1.0, abs(float(value)))
        forward = min(float(value) + step, float(upper[index]))
        backward = max(float(value) - step, float(lower[index]))
        if forward > value and backward < value:
            plus = theta.copy()
            minus = theta.copy()
            plus[index] = forward
            minus[index] = backward
            gradient[:, index] = (predict(plus, dataset) - predict(minus, dataset)) / (
                forward - backward
            )
        elif forward > value:
            plus = theta.copy()
            plus[index] = forward
            gradient[:, index] = (predict(plus, dataset) - base) / (forward - value)
        elif backward < value:
            minus = theta.copy()
            minus[index] = backward
            gradient[:, index] = (base - predict(minus, dataset)) / (value - backward)
        else:
            gradient[:, index] = 0.0
    return gradient


def global_fit(
    datasets: Sequence[GlobalFitDataset | Mapping[str, object] | tuple],
    model: str | ModelCallable,
    *,
    parameter_names: Sequence[str] | None = None,
    shared: Sequence[str] = (),
    initial: Mapping[str, float] | None = None,
    fixed: Mapping[str, float] | None = None,
    bounds: Mapping[str, tuple[float, float]] | None = None,
    absolute_sigma: bool = False,
    confidence: float = 0.95,
    loss: str = "linear",
    max_nfev: int = 50_000,
    cancel_check: CancelCheck | None = None,
) -> GlobalFitResult:
    """Fit multiple datasets simultaneously.

    Parameters not listed in ``shared`` receive one value per dataset. Mapping
    keys such as ``"run_1.amplitude"`` override an unqualified default such as
    ``"amplitude"``.  This convention applies to ``initial``, ``fixed`` and
    ``bounds``.  The returned covariance is ordered by ``parameter_order`` and
    contains free parameters only; fixed parameters have zero standard error
    and a zero-width confidence interval.
    """

    _check_cancelled(cancel_check, "Global fitting")
    if not datasets:
        raise GlobalFitError("At least one dataset is required")
    if not 0.0 < confidence < 1.0:
        raise GlobalFitError("confidence must be between 0 and 1")
    if max_nfev <= 0:
        raise GlobalFitError("max_nfev must be positive")
    spec = _normalise_model(model, parameter_names)
    prepared = tuple(
        _prepare_dataset(_coerce_dataset(dataset, index))
        for index, dataset in enumerate(datasets)
    )
    _check_cancelled(cancel_check, "Global fitting")
    names = [dataset.name for dataset in prepared]
    if len(set(names)) != len(names):
        raise GlobalFitError("Dataset names must be unique")
    shared_set = {str(name) for name in shared}
    unknown_shared = sorted(shared_set.difference(spec.parameter_names))
    if unknown_shared:
        raise GlobalFitError(f"Unknown shared parameter(s): {', '.join(unknown_shared)}")
    slots = _build_slots(spec, prepared, shared_set, initial, fixed, bounds)
    _check_cancelled(cancel_check, "Global fitting")
    free_slots = tuple(slot for slot in slots if slot.fixed is None)
    n_observations = sum(dataset.x.size for dataset in prepared)
    if n_observations <= len(free_slots):
        raise GlobalFitError(
            "Too few finite observations for the number of free global parameters"
        )
    theta0 = np.asarray([slot.initial for slot in free_slots], dtype=float)
    lower = np.asarray([slot.lower for slot in free_slots], dtype=float)
    upper = np.asarray([slot.upper for slot in free_slots], dtype=float)

    def predict(theta: np.ndarray, dataset: _PreparedDataset) -> np.ndarray:
        values = _parameter_values(theta, free_slots, slots)
        params = _dataset_parameters(dataset, spec, shared_set, values)
        return _evaluate_model(spec, dataset.x, params)

    def residual_vector(theta: np.ndarray) -> np.ndarray:
        return np.concatenate(
            [(dataset.y - predict(theta, dataset)) * dataset.scale for dataset in prepared]
        )

    if free_slots:
        def cancellation_callback(_intermediate_result) -> None:
            _check_cancelled(cancel_check, "Global fitting")

        try:
            optimisation = least_squares(
                residual_vector,
                theta0,
                bounds=(lower, upper),
                method="trf",
                jac="2-point",
                x_scale="jac",
                loss=loss,
                max_nfev=int(max_nfev),
                callback=cancellation_callback if cancel_check is not None else None,
            )
        except GlobalFitError:
            raise
        except Exception as exc:
            raise GlobalFitError(f"Global fitting failed: {exc}") from exc
        theta = np.asarray(optimisation.x, dtype=float)
        success = bool(optimisation.success)
        message = str(optimisation.message)
        nfev = int(optimisation.nfev)
        jacobian = np.asarray(optimisation.jac, dtype=float)
        cost = float(optimisation.cost)
    else:
        theta = np.empty(0, dtype=float)
        success = True
        message = "All parameters were fixed; model evaluated without optimisation"
        nfev = 0
        jacobian = np.empty((n_observations, 0), dtype=float)
        residual = residual_vector(theta)
        cost = float(np.dot(residual, residual) / 2.0)

    _check_cancelled(cancel_check, "Global fitting")
    values = _parameter_values(theta, free_slots, slots)
    all_y = np.concatenate([dataset.y for dataset in prepared])
    all_fitted = np.concatenate([predict(theta, dataset) for dataset in prepared])
    all_weighted = residual_vector(theta)
    overall_metrics = _metrics(all_y, all_fitted, all_weighted, len(free_slots))
    covariance = _covariance_from_jacobian(
        jacobian,
        overall_metrics.chi_square,
        overall_metrics.degrees_of_freedom,
        bool(absolute_sigma),
    )
    correlation = _correlation(covariance)
    alpha = 1.0 - confidence
    critical = float(
        student_t.ppf(1.0 - alpha / 2.0, max(1, overall_metrics.degrees_of_freedom))
    )
    if not np.isfinite(critical):
        critical = 1.959963984540054
    stderr: dict[str, float] = {}
    ci95: dict[str, tuple[float, float]] = {}
    free_index = {slot.key: index for index, slot in enumerate(free_slots)}
    for slot in slots:
        value = values[slot.key]
        if slot.fixed is not None:
            error = 0.0
        else:
            variance = covariance[free_index[slot.key], free_index[slot.key]]
            error = float(np.sqrt(variance)) if np.isfinite(variance) and variance >= 0 else np.nan
        stderr[slot.key] = error
        delta = critical * error
        ci95[slot.key] = (
            (float(value - delta), float(value + delta))
            if np.isfinite(delta)
            else (np.nan, np.nan)
        )

    dataset_results: list[DatasetFitResult] = []
    covariance_usable = covariance.size > 0 and np.all(np.isfinite(covariance))
    for dataset in prepared:
        fitted = predict(theta, dataset)
        residuals = dataset.y - fitted
        weighted = residuals * dataset.scale
        relevant_keys = {
            parameter if parameter in shared_set else _qualified(dataset.name, parameter)
            for parameter in spec.parameter_names
        }
        effective_free = sum(slot.key in relevant_keys for slot in free_slots)
        metrics = _metrics(dataset.y, fitted, weighted, effective_free)
        lower_band = upper_band = None
        if covariance_usable:
            gradient = _prediction_gradient(theta, dataset, predict, lower, upper)
            variance = np.einsum(
                "ij,jk,ik->i", gradient, covariance, gradient, optimize=True
            )
            standard = np.sqrt(np.clip(variance, 0.0, np.inf))
            lower_band = fitted - critical * standard
            upper_band = fitted + critical * standard
        params = _dataset_parameters(dataset, spec, shared_set, values)
        dataset_results.append(
            DatasetFitResult(
                dataset.name,
                dataset.x.copy(),
                dataset.y.copy(),
                dataset.original_indices.copy(),
                params,
                fitted,
                residuals,
                weighted,
                lower_band,
                upper_band,
                metrics,
            )
        )
    return GlobalFitResult(
        spec.name,
        success,
        message,
        tuple(slot.key for slot in free_slots),
        values,
        stderr,
        ci95,
        covariance,
        correlation,
        tuple(dataset_results),
        overall_metrics,
        nfev,
        cost,
        float(confidence),
    )


# Equally readable alias for callers that prefer verb-first naming.
fit_global = global_fit


__all__ = [
    "DatasetFitResult",
    "FitDataset",
    "FitMetrics",
    "GlobalFitDataset",
    "GlobalFitError",
    "GlobalFitResult",
    "exponential_decay_model",
    "exponential_model",
    "fit_global",
    "gaussian_model",
    "global_fit",
    "list_global_models",
    "lorentzian_model",
    "voigt_model",
]
