"""Pure statistical routines and JSON-safe result contracts.

The functions in this module deliberately have no Qt dependency.  They accept
array-like inputs, validate them consistently, and return immutable dataclasses
rather than display strings.  This keeps the numerical layer usable from the
desktop UI, the offline assistant, generated reports, and headless tests.

Missing-value handling is explicit through ``nan_policy``:

``"omit"``
    Drop non-finite observations (jointly for paired/multivariate inputs).
``"raise"``
    Reject inputs containing NaN or infinity.
``"propagate"``
    Return a result whose numerical test fields are NaN.  Regression is the
    sole exception because propagating a missing design matrix cannot produce
    meaningful diagnostics; callers must choose ``omit`` or ``raise`` there.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
import json
import math
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats


__all__ = [
    "ConfidenceInterval",
    "EffectSize",
    "HypothesisTestResult",
    "AnovaTerm",
    "AnovaResult",
    "MultipleTestingResult",
    "RegressionCoefficient",
    "RegressionDiagnostics",
    "RegressionResult",
    "one_sample_t_test",
    "independent_t_test",
    "welch_t_test",
    "pooled_t_test",
    "paired_t_test",
    "one_way_anova",
    "two_way_anova",
    "mann_whitney_test",
    "wilcoxon_signed_rank_test",
    "kruskal_wallis_test",
    "shapiro_wilk_test",
    "levene_test",
    "multiple_testing_correction",
    "multiple_linear_regression",
]


# ---------------------------------------------------------------------------
# JSON-safe public result contracts


def _json_safe(value: Any) -> Any:
    """Recursively convert scientific Python values to strict JSON values.

    JSON has no portable representation for NaN or infinity.  Those values are
    emitted as ``None`` while remaining available as floats on the dataclass
    itself.  Mapping keys are stringified to keep ``json.dumps(...,
    allow_nan=False)`` valid.
    """

    if is_dataclass(value):
        return {field.name: _json_safe(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    # bool is a subclass of int in Python, so it must be handled first.
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return value.isoformat()
    return value


class JsonSafeResult:
    """Mixin shared by every public result dataclass."""

    def to_dict(self) -> Dict[str, Any]:
        return _json_safe(self)

    def to_json(self, *, indent: Optional[int] = 2) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, allow_nan=False, indent=indent
        )


@dataclass(frozen=True)
class ConfidenceInterval(JsonSafeResult):
    lower: Optional[float]
    upper: Optional[float]
    level: float


@dataclass(frozen=True)
class EffectSize(JsonSafeResult):
    name: str
    value: float
    interpretation: Optional[str] = None


@dataclass(frozen=True)
class HypothesisTestResult(JsonSafeResult):
    method: str
    statistic: float
    p_value: float
    alpha: float
    reject_null: bool
    alternative: str
    degrees_of_freedom: Optional[float | Tuple[float, ...]] = None
    estimate: Optional[float] = None
    standard_error: Optional[float] = None
    confidence_interval: Optional[ConfidenceInterval] = None
    effect_sizes: Tuple[EffectSize, ...] = ()
    sample_sizes: Mapping[str, int] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AnovaTerm(JsonSafeResult):
    term: str
    sum_squares: float
    degrees_of_freedom: float
    mean_square: float
    f_statistic: Optional[float]
    p_value: Optional[float]
    reject_null: Optional[bool]
    eta_squared: Optional[float] = None
    partial_eta_squared: Optional[float] = None
    omega_squared: Optional[float] = None


@dataclass(frozen=True)
class AnovaResult(JsonSafeResult):
    method: str
    terms: Tuple[AnovaTerm, ...]
    alpha: float
    total_sum_squares: float
    total_degrees_of_freedom: float
    residual_sum_squares: float
    residual_degrees_of_freedom: float
    sample_size: int
    factor_levels: Mapping[str, Tuple[str, ...]]
    ss_type: Optional[int] = None
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MultipleTestingResult(JsonSafeResult):
    method: str
    alpha: float
    original_p_values: Tuple[Optional[float], ...]
    adjusted_p_values: Tuple[Optional[float], ...]
    reject_null: Tuple[bool, ...]
    tested_count: int


@dataclass(frozen=True)
class RegressionCoefficient(JsonSafeResult):
    term: str
    estimate: float
    standard_error: float
    t_statistic: float
    p_value: float
    confidence_interval: ConfidenceInterval
    reject_null: bool = False


@dataclass(frozen=True)
class RegressionDiagnostics(JsonSafeResult):
    durbin_watson: float
    condition_number: float
    variance_inflation_factors: Mapping[str, float]
    shapiro_w: Optional[float]
    shapiro_p_value: Optional[float]
    breusch_pagan_lm: Optional[float]
    breusch_pagan_p_value: Optional[float]
    maximum_leverage: float
    maximum_cooks_distance: float


@dataclass(frozen=True)
class RegressionResult(JsonSafeResult):
    method: str
    coefficients: Tuple[RegressionCoefficient, ...]
    n_observations: int
    predictor_names: Tuple[str, ...]
    add_intercept: bool
    rank: int
    degrees_of_freedom_model: int
    degrees_of_freedom_residual: int
    r_squared: float
    adjusted_r_squared: float
    f_statistic: float
    f_p_value: float
    rmse: float
    residual_standard_error: float
    sum_squared_errors: float
    regression_sum_squares: float
    total_sum_squares: float
    log_likelihood: float
    aic: float
    bic: float
    covariance_matrix: Tuple[Tuple[float, ...], ...]
    fitted_values: Tuple[float, ...]
    residuals: Tuple[float, ...]
    leverage: Tuple[float, ...]
    standardized_residuals: Tuple[float, ...]
    cooks_distance: Tuple[float, ...]
    diagnostics: RegressionDiagnostics
    confidence_level: float
    notes: Tuple[str, ...] = ()
    # Kept at the end with defaults so older positional construction remains
    # valid while new callers can audit the decision threshold and model test.
    alpha: float = 0.05
    reject_null: bool = False


# ---------------------------------------------------------------------------
# Validation and numerical helpers


_ALTERNATIVES = {"two-sided", "less", "greater"}
_NAN_POLICIES = {"omit", "raise", "propagate"}


def _validate_probability(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not 0.0 < number < 1.0:
        raise ValueError(f"{name} must be between 0 and 1 (exclusive)")
    return number


def _validate_common(
    alternative: str, alpha: float, confidence_level: float, nan_policy: str
) -> tuple[str, float, float, str]:
    alt = str(alternative).strip().lower()
    if alt not in _ALTERNATIVES:
        raise ValueError(f"alternative must be one of {sorted(_ALTERNATIVES)}")
    policy = str(nan_policy).strip().lower()
    if policy not in _NAN_POLICIES:
        raise ValueError(f"nan_policy must be one of {sorted(_NAN_POLICIES)}")
    return (
        alt,
        _validate_probability(alpha, "alpha"),
        _validate_probability(confidence_level, "confidence_level"),
        policy,
    )


def _as_numeric_1d(values: Sequence[float], name: str) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain only numeric values") from exc
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array


def _clean_1d(
    values: Sequence[float],
    name: str,
    *,
    nan_policy: str,
    minimum_size: int,
) -> tuple[np.ndarray, bool]:
    array = _as_numeric_1d(values, name)
    finite = np.isfinite(array)
    had_missing = not bool(finite.all())
    if had_missing:
        if nan_policy == "raise":
            raise ValueError(f"{name} contains NaN or infinity")
        if nan_policy == "omit":
            array = array[finite]
    effective_size = int(np.count_nonzero(np.isfinite(array)))
    validation_size = int(array.size) if had_missing and nan_policy == "propagate" else effective_size
    if validation_size < minimum_size:
        raise ValueError(
            f"{name} needs at least {minimum_size} finite observation(s); "
            f"got {effective_size}"
        )
    return array, had_missing


def _clean_paired(
    first: Sequence[float],
    second: Sequence[float],
    *,
    first_name: str,
    second_name: str,
    nan_policy: str,
    minimum_size: int,
) -> tuple[np.ndarray, np.ndarray, bool]:
    a = _as_numeric_1d(first, first_name)
    b = _as_numeric_1d(second, second_name)
    if a.size != b.size:
        raise ValueError(
            f"paired inputs must have the same length; got {a.size} and {b.size}"
        )
    finite = np.isfinite(a) & np.isfinite(b)
    had_missing = not bool(finite.all())
    if had_missing:
        if nan_policy == "raise":
            raise ValueError("paired inputs contain NaN or infinity")
        if nan_policy == "omit":
            a, b = a[finite], b[finite]
    effective_size = int(np.count_nonzero(np.isfinite(a) & np.isfinite(b)))
    validation_size = int(a.size) if had_missing and nan_policy == "propagate" else effective_size
    if validation_size < minimum_size:
        raise ValueError(
            f"paired inputs need at least {minimum_size} complete pair(s); "
            f"got {effective_size}"
        )
    return a, b, had_missing


def _float(value: Any) -> float:
    return float(np.asarray(value).item())


def _reject(p_value: float, alpha: float) -> bool:
    return bool(math.isfinite(p_value) and p_value <= alpha)


def _interpret_standardized(value: float) -> Optional[str]:
    if not math.isfinite(value):
        return None
    magnitude = abs(value)
    if magnitude < 0.2:
        return "negligible"
    if magnitude < 0.5:
        return "small"
    if magnitude < 0.8:
        return "medium"
    return "large"


def _interpret_correlation(value: float) -> Optional[str]:
    """Interpret a correlation-like effect without reusing Cohen-d cutoffs."""

    if not math.isfinite(value):
        return None
    magnitude = abs(value)
    if magnitude < 0.1:
        return "negligible"
    if magnitude < 0.3:
        return "small"
    if magnitude < 0.5:
        return "medium"
    return "large"


def _interpret_variance_effect(value: float) -> Optional[str]:
    if not math.isfinite(value):
        return None
    magnitude = max(0.0, value)
    if magnitude < 0.01:
        return "negligible"
    if magnitude < 0.06:
        return "small"
    if magnitude < 0.14:
        return "medium"
    return "large"


def _hedges_correction(degrees_of_freedom: float) -> float:
    if not math.isfinite(degrees_of_freedom) or degrees_of_freedom <= 1:
        return float("nan")
    # Accurate enough for routine samples and stable at small df.
    return 1.0 - 3.0 / (4.0 * degrees_of_freedom - 1.0)


def _standardized_difference(numerator: float, denominator: float) -> float:
    if denominator > 0 and math.isfinite(denominator):
        return numerator / denominator
    if numerator == 0:
        return 0.0
    return math.copysign(float("inf"), numerator)


def _mean_confidence_interval(
    estimate: float,
    standard_error: float,
    degrees_of_freedom: float,
    *,
    alternative: str,
    confidence_level: float,
) -> ConfidenceInterval:
    if not all(
        math.isfinite(value)
        for value in (estimate, standard_error, degrees_of_freedom)
    ) or degrees_of_freedom <= 0:
        return ConfidenceInterval(float("nan"), float("nan"), confidence_level)
    if alternative == "two-sided":
        critical = float(stats.t.ppf((1.0 + confidence_level) / 2.0, degrees_of_freedom))
        margin = critical * standard_error
        return ConfidenceInterval(estimate - margin, estimate + margin, confidence_level)
    critical = float(stats.t.ppf(confidence_level, degrees_of_freedom))
    margin = critical * standard_error
    if alternative == "greater":
        return ConfidenceInterval(estimate - margin, None, confidence_level)
    return ConfidenceInterval(None, estimate + margin, confidence_level)


def _t_statistic_and_p_value(
    estimate_difference: float,
    standard_error: float,
    degrees_of_freedom: float,
    alternative: str,
) -> tuple[float, float]:
    """Stable t statistic/tail probability, including zero-variance data."""

    if standard_error > 0 and math.isfinite(standard_error):
        statistic = estimate_difference / standard_error
    elif estimate_difference == 0:
        # scipy returns NaN for 0/0.  For a completely degenerate sample that
        # is exactly on the null value, 0 and p=1 are the useful scientific
        # contract and avoid an avoidable precision-loss warning.
        return 0.0, 1.0
    else:
        statistic = math.copysign(float("inf"), estimate_difference)
    if alternative == "two-sided":
        p_value = 2.0 * float(stats.t.sf(abs(statistic), degrees_of_freedom))
    elif alternative == "greater":
        p_value = float(stats.t.sf(statistic, degrees_of_freedom))
    else:
        p_value = float(stats.t.cdf(statistic, degrees_of_freedom))
    return float(statistic), float(np.clip(p_value, 0.0, 1.0))


def _propagated_test(
    method: str,
    *,
    alpha: float,
    alternative: str,
    sample_sizes: Mapping[str, int],
    notes: tuple[str, ...] = ("NaN propagated from the input.",),
) -> HypothesisTestResult:
    return HypothesisTestResult(
        method=method,
        statistic=float("nan"),
        p_value=float("nan"),
        alpha=alpha,
        reject_null=False,
        alternative=alternative,
        sample_sizes=sample_sizes,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Parametric tests


def one_sample_t_test(
    sample: Sequence[float],
    popmean: float = 0.0,
    *,
    alternative: str = "two-sided",
    alpha: float = 0.05,
    confidence_level: float = 0.95,
    nan_policy: str = "omit",
) -> HypothesisTestResult:
    """One-sample Student t-test with Cohen's *d* and Hedges' *g*."""

    alternative, alpha, confidence_level, nan_policy = _validate_common(
        alternative, alpha, confidence_level, nan_policy
    )
    null_mean = float(popmean)
    if not math.isfinite(null_mean):
        raise ValueError("popmean must be finite")
    values, missing = _clean_1d(
        sample, "sample", nan_policy=nan_policy, minimum_size=2
    )
    if missing and nan_policy == "propagate":
        return _propagated_test(
            "One-sample t-test",
            alpha=alpha,
            alternative=alternative,
            sample_sizes={"sample": int(values.size)},
        )

    n = int(values.size)
    estimate = float(np.mean(values))
    standard_deviation = float(np.std(values, ddof=1))
    standard_error = standard_deviation / math.sqrt(n)
    degrees_of_freedom = float(n - 1)
    difference = estimate - null_mean
    statistic, p_value = _t_statistic_and_p_value(
        difference, standard_error, degrees_of_freedom, alternative
    )
    cohen_d = _standardized_difference(difference, standard_deviation)
    hedges_g = cohen_d * _hedges_correction(degrees_of_freedom)
    ci = _mean_confidence_interval(
        estimate,
        standard_error,
        degrees_of_freedom,
        alternative=alternative,
        confidence_level=confidence_level,
    )
    return HypothesisTestResult(
        method="One-sample t-test",
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        reject_null=_reject(p_value, alpha),
        alternative=alternative,
        degrees_of_freedom=degrees_of_freedom,
        estimate=estimate,
        standard_error=standard_error,
        confidence_interval=ci,
        effect_sizes=(
            EffectSize("cohen_d", cohen_d, _interpret_standardized(cohen_d)),
            EffectSize("hedges_g", hedges_g, _interpret_standardized(hedges_g)),
        ),
        sample_sizes={"sample": n},
        metadata={
            "null_mean": null_mean,
            "sample_mean": estimate,
            "sample_standard_deviation": standard_deviation,
            "mean_difference": difference,
        },
    )


def independent_t_test(
    first: Sequence[float],
    second: Sequence[float],
    *,
    equal_var: bool = False,
    alternative: str = "two-sided",
    alpha: float = 0.05,
    confidence_level: float = 0.95,
    nan_policy: str = "omit",
) -> HypothesisTestResult:
    """Independent-samples t-test.

    ``equal_var=False`` (the default) performs Welch's test.  ``True`` uses the
    classical pooled-variance test.  The estimate and confidence interval are
    for ``mean(first) - mean(second)``.
    """

    alternative, alpha, confidence_level, nan_policy = _validate_common(
        alternative, alpha, confidence_level, nan_policy
    )
    a, missing_a = _clean_1d(
        first, "first", nan_policy=nan_policy, minimum_size=2
    )
    b, missing_b = _clean_1d(
        second, "second", nan_policy=nan_policy, minimum_size=2
    )
    method = "Pooled independent-samples t-test" if equal_var else "Welch independent-samples t-test"
    if (missing_a or missing_b) and nan_policy == "propagate":
        return _propagated_test(
            method,
            alpha=alpha,
            alternative=alternative,
            sample_sizes={"first": int(a.size), "second": int(b.size)},
        )

    n1, n2 = int(a.size), int(b.size)
    mean1, mean2 = float(np.mean(a)), float(np.mean(b))
    variance1, variance2 = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    estimate = mean1 - mean2
    pooled_variance = (
        ((n1 - 1) * variance1 + (n2 - 1) * variance2) / (n1 + n2 - 2)
    )
    pooled_sd = math.sqrt(max(0.0, pooled_variance))

    if equal_var:
        degrees_of_freedom = float(n1 + n2 - 2)
        standard_error = math.sqrt(pooled_variance * (1.0 / n1 + 1.0 / n2))
    else:
        first_component = variance1 / n1
        second_component = variance2 / n2
        standard_error = math.sqrt(first_component + second_component)
        denominator = (
            first_component**2 / (n1 - 1)
            + second_component**2 / (n2 - 1)
        )
        degrees_of_freedom = (
            (first_component + second_component) ** 2 / denominator
            if denominator > 0
            else float(n1 + n2 - 2)
        )

    statistic, p_value = _t_statistic_and_p_value(
        estimate, standard_error, degrees_of_freedom, alternative
    )
    cohen_d = _standardized_difference(estimate, pooled_sd)
    hedges_g = cohen_d * _hedges_correction(float(n1 + n2 - 2))
    ci = _mean_confidence_interval(
        estimate,
        standard_error,
        degrees_of_freedom,
        alternative=alternative,
        confidence_level=confidence_level,
    )
    return HypothesisTestResult(
        method=method,
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        reject_null=_reject(p_value, alpha),
        alternative=alternative,
        degrees_of_freedom=degrees_of_freedom,
        estimate=estimate,
        standard_error=standard_error,
        confidence_interval=ci,
        effect_sizes=(
            EffectSize("cohen_d", cohen_d, _interpret_standardized(cohen_d)),
            EffectSize("hedges_g", hedges_g, _interpret_standardized(hedges_g)),
        ),
        sample_sizes={"first": n1, "second": n2},
        metadata={
            "equal_var": bool(equal_var),
            "first_mean": mean1,
            "second_mean": mean2,
            "first_standard_deviation": math.sqrt(max(0.0, variance1)),
            "second_standard_deviation": math.sqrt(max(0.0, variance2)),
            "pooled_standard_deviation": pooled_sd,
            "mean_difference": estimate,
        },
    )


def welch_t_test(
    first: Sequence[float], second: Sequence[float], **kwargs: Any
) -> HypothesisTestResult:
    """Convenience wrapper for :func:`independent_t_test` (Welch variance)."""

    kwargs.pop("equal_var", None)
    return independent_t_test(first, second, equal_var=False, **kwargs)


def pooled_t_test(
    first: Sequence[float], second: Sequence[float], **kwargs: Any
) -> HypothesisTestResult:
    """Convenience wrapper for the pooled independent-samples t-test."""

    kwargs.pop("equal_var", None)
    return independent_t_test(first, second, equal_var=True, **kwargs)


def paired_t_test(
    first: Sequence[float],
    second: Sequence[float],
    *,
    alternative: str = "two-sided",
    alpha: float = 0.05,
    confidence_level: float = 0.95,
    nan_policy: str = "omit",
) -> HypothesisTestResult:
    """Paired-samples t-test with pairwise missing-value omission."""

    alternative, alpha, confidence_level, nan_policy = _validate_common(
        alternative, alpha, confidence_level, nan_policy
    )
    a, b, missing = _clean_paired(
        first,
        second,
        first_name="first",
        second_name="second",
        nan_policy=nan_policy,
        minimum_size=2,
    )
    if missing and nan_policy == "propagate":
        return _propagated_test(
            "Paired-samples t-test",
            alpha=alpha,
            alternative=alternative,
            sample_sizes={"pairs": int(a.size)},
        )

    differences = a - b
    n = int(differences.size)
    estimate = float(np.mean(differences))
    difference_sd = float(np.std(differences, ddof=1))
    standard_error = difference_sd / math.sqrt(n)
    degrees_of_freedom = float(n - 1)
    statistic, p_value = _t_statistic_and_p_value(
        estimate, standard_error, degrees_of_freedom, alternative
    )
    cohen_dz = _standardized_difference(estimate, difference_sd)
    hedges_gz = cohen_dz * _hedges_correction(degrees_of_freedom)
    ci = _mean_confidence_interval(
        estimate,
        standard_error,
        degrees_of_freedom,
        alternative=alternative,
        confidence_level=confidence_level,
    )
    return HypothesisTestResult(
        method="Paired-samples t-test",
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        reject_null=_reject(p_value, alpha),
        alternative=alternative,
        degrees_of_freedom=degrees_of_freedom,
        estimate=estimate,
        standard_error=standard_error,
        confidence_interval=ci,
        effect_sizes=(
            EffectSize("cohen_dz", cohen_dz, _interpret_standardized(cohen_dz)),
            EffectSize("hedges_gz", hedges_gz, _interpret_standardized(hedges_gz)),
        ),
        sample_sizes={"pairs": n},
        metadata={
            "first_mean": float(np.mean(a)),
            "second_mean": float(np.mean(b)),
            "mean_difference": estimate,
            "difference_standard_deviation": difference_sd,
        },
    )


# ---------------------------------------------------------------------------
# ANOVA


def _prepare_groups(
    groups: tuple[Any, ...],
    *,
    group_names: Optional[Sequence[str]],
    nan_policy: str,
    minimum_size: int,
) -> tuple[list[np.ndarray], list[str], bool]:
    if len(groups) == 1 and isinstance(groups[0], Mapping):
        items = list(groups[0].items())
        raw_groups = [values for _, values in items]
        names = [str(name) for name, _ in items]
        if group_names is not None:
            raise ValueError("group_names cannot be used when groups are a mapping")
    else:
        raw_groups = list(groups)
        names = (
            [str(name) for name in group_names]
            if group_names is not None
            else [f"group_{index + 1}" for index in range(len(raw_groups))]
        )
    if len(raw_groups) < 2:
        raise ValueError("at least two groups are required")
    if len(names) != len(raw_groups):
        raise ValueError("group_names must match the number of groups")
    if len(set(names)) != len(names):
        raise ValueError("group names must be unique")
    cleaned: list[np.ndarray] = []
    had_missing = False
    for name, values in zip(names, raw_groups):
        array, missing = _clean_1d(
            values,
            name,
            nan_policy=nan_policy,
            minimum_size=minimum_size,
        )
        cleaned.append(array)
        had_missing = had_missing or missing
    return cleaned, names, had_missing


def _anova_f(statistic_numerator: float, mean_square_error: float) -> float:
    if mean_square_error > 0:
        return statistic_numerator / mean_square_error
    if statistic_numerator == 0:
        return 0.0
    return float("inf")


def one_way_anova(
    *groups: Sequence[float] | Mapping[str, Sequence[float]],
    group_names: Optional[Sequence[str]] = None,
    alpha: float = 0.05,
    nan_policy: str = "omit",
) -> AnovaResult:
    """Classical one-way between-groups ANOVA with eta/omega effect sizes."""

    alpha = _validate_probability(alpha, "alpha")
    policy = str(nan_policy).strip().lower()
    if policy not in _NAN_POLICIES:
        raise ValueError(f"nan_policy must be one of {sorted(_NAN_POLICIES)}")
    arrays, names, missing = _prepare_groups(
        groups, group_names=group_names, nan_policy=policy, minimum_size=2
    )
    sample_size = int(sum(array.size for array in arrays))
    factor_levels = {"group": tuple(names)}
    if missing and policy == "propagate":
        nan_term = AnovaTerm(
            "group", float("nan"), float(len(arrays) - 1), float("nan"),
            float("nan"), float("nan"), False,
        )
        residual = AnovaTerm(
            "Residual", float("nan"), float(sample_size - len(arrays)),
            float("nan"), None, None, None,
        )
        return AnovaResult(
            "One-way ANOVA", (nan_term, residual), alpha, float("nan"),
            float(sample_size - 1), float("nan"),
            float(sample_size - len(arrays)), sample_size, factor_levels,
            notes=("NaN propagated from the input.",),
        )

    all_values = np.concatenate(arrays)
    grand_mean = float(np.mean(all_values))
    ss_between = float(
        sum(array.size * (float(np.mean(array)) - grand_mean) ** 2 for array in arrays)
    )
    ss_within = float(
        sum(np.sum((array - float(np.mean(array))) ** 2) for array in arrays)
    )
    total_ss = float(np.sum((all_values - grand_mean) ** 2))
    df_between = float(len(arrays) - 1)
    df_within = float(sample_size - len(arrays))
    if df_within <= 0:
        raise ValueError("one-way ANOVA needs positive residual degrees of freedom")
    ms_between = ss_between / df_between
    ms_within = ss_within / df_within
    f_statistic = _anova_f(ms_between, ms_within)
    p_value = float(stats.f.sf(f_statistic, df_between, df_within))
    eta_squared = ss_between / total_ss if total_ss > 0 else 0.0
    omega_denominator = total_ss + ms_within
    omega_squared = (
        max(0.0, (ss_between - df_between * ms_within) / omega_denominator)
        if omega_denominator > 0
        else 0.0
    )
    group_term = AnovaTerm(
        term="group",
        sum_squares=ss_between,
        degrees_of_freedom=df_between,
        mean_square=ms_between,
        f_statistic=f_statistic,
        p_value=p_value,
        reject_null=_reject(p_value, alpha),
        eta_squared=eta_squared,
        partial_eta_squared=eta_squared,
        omega_squared=omega_squared,
    )
    residual_term = AnovaTerm(
        term="Residual",
        sum_squares=ss_within,
        degrees_of_freedom=df_within,
        mean_square=ms_within,
        f_statistic=None,
        p_value=None,
        reject_null=None,
    )
    return AnovaResult(
        method="One-way ANOVA",
        terms=(group_term, residual_term),
        alpha=alpha,
        total_sum_squares=total_ss,
        total_degrees_of_freedom=float(sample_size - 1),
        residual_sum_squares=ss_within,
        residual_degrees_of_freedom=df_within,
        sample_size=sample_size,
        factor_levels=factor_levels,
    )


def _effect_coding(values: pd.Series, factor_name: str) -> tuple[np.ndarray, list[str], tuple[str, ...]]:
    raw_levels = list(pd.unique(values))
    raw_levels.sort(key=lambda value: str(value))
    if len(raw_levels) < 2:
        raise ValueError(f"{factor_name} must contain at least two levels")
    levels = tuple(str(level) for level in raw_levels)
    reference = raw_levels[-1]
    matrix = np.zeros((len(values), len(raw_levels) - 1), dtype=float)
    raw_array = values.to_numpy()
    for column, level in enumerate(raw_levels[:-1]):
        matrix[raw_array == level, column] = 1.0
        matrix[raw_array == reference, column] = -1.0
    names = [f"{factor_name}[{level}]" for level in levels[:-1]]
    return matrix, names, levels


def _least_squares_sse(design: np.ndarray, response: np.ndarray) -> tuple[float, int]:
    coefficients, _, rank, _ = np.linalg.lstsq(design, response, rcond=None)
    residual = response - design @ coefficients
    return float(residual @ residual), int(rank)


_TWO_WAY_MAX_FACTOR_LEVELS = 256
_TWO_WAY_MAX_DESIGN_COLUMNS = 8_192
_TWO_WAY_MAX_DESIGN_ELEMENTS = 4_000_000


def _preflight_two_way_design(
    frame: pd.DataFrame,
    factor_a: str,
    factor_b: str,
    *,
    interaction: bool,
) -> None:
    """Reject unsafe or non-estimable designs before allocating dummy matrices."""

    observations = int(len(frame))
    levels_a = int(frame[factor_a].nunique(dropna=False))
    levels_b = int(frame[factor_b].nunique(dropna=False))
    if levels_a < 2:
        raise ValueError(f"{factor_a} must contain at least two levels")
    if levels_b < 2:
        raise ValueError(f"{factor_b} must contain at least two levels")
    if levels_a > _TWO_WAY_MAX_FACTOR_LEVELS or levels_b > _TWO_WAY_MAX_FACTOR_LEVELS:
        raise ValueError(
            "two-way ANOVA factor cardinality is too high before model allocation "
            f"({factor_a}={levels_a}, {factor_b}={levels_b}; safe maximum is "
            f"{_TWO_WAY_MAX_FACTOR_LEVELS} levels per factor). Use categorical "
            "factors, remove identifier/continuous columns, or combine sparse levels."
        )

    columns_a = levels_a - 1
    columns_b = levels_b - 1
    interaction_columns = columns_a * columns_b if interaction else 0
    design_columns = 1 + columns_a + columns_b + interaction_columns
    design_elements = observations * design_columns
    if (
        design_columns > _TWO_WAY_MAX_DESIGN_COLUMNS
        or design_elements > _TWO_WAY_MAX_DESIGN_ELEMENTS
    ):
        estimated_mib = design_elements * np.dtype(float).itemsize / (1024.0**2)
        raise ValueError(
            "two-way ANOVA design is too large to allocate safely "
            f"({observations} observations x {design_columns} model columns, "
            f"about {estimated_mib:.1f} MiB per dense matrix; safe limits are "
            f"{_TWO_WAY_MAX_DESIGN_COLUMNS} columns and "
            f"{_TWO_WAY_MAX_DESIGN_ELEMENTS:,} elements). Disable the interaction, "
            "reduce factor levels, or aggregate the data."
        )

    if interaction:
        expected_cells = levels_a * levels_b
        observed_cells = int(frame[[factor_a, factor_b]].drop_duplicates().shape[0])
        if observed_cells != expected_cells:
            raise ValueError(
                "two-way ANOVA design is rank deficient: an interaction requires "
                f"every {factor_a} x {factor_b} cell; observed {observed_cells} of "
                f"{expected_cells}."
            )
        # With all cells present, the full interaction model has one parameter
        # per cell. At least one additional observation is needed for residual
        # variance; catch the unreplicated design before building any matrices.
        if observations <= design_columns:
            raise ValueError(
                "two-way ANOVA needs replication to estimate residual variance; "
                "the interaction model has no residual degrees of freedom."
            )


def two_way_anova(
    data: pd.DataFrame,
    dependent: str,
    factor_a: str,
    factor_b: str,
    *,
    interaction: bool = True,
    ss_type: int = 2,
    alpha: float = 0.05,
    nan_policy: str = "omit",
) -> AnovaResult:
    """Two-way fixed-effects ANOVA using effect-coded OLS models.

    ``ss_type=2`` tests each main effect after the other main effect and tests
    the interaction after both.  ``ss_type=3`` compares the full model with a
    model omitting each individual effect.  Effect coding makes Type-III main
    effects meaningful and invariant to the chosen reference level.

    Empty cells/confounded designs are rejected instead of returning unstable
    or reference-level-dependent results.
    """

    if not isinstance(data, pd.DataFrame):
        raise ValueError("data must be a pandas DataFrame")
    if ss_type not in (2, 3):
        raise ValueError("ss_type must be 2 or 3")
    if len({dependent, factor_a, factor_b}) != 3:
        raise ValueError("dependent, factor_a, and factor_b must be distinct columns")
    missing_columns = [name for name in (dependent, factor_a, factor_b) if name not in data.columns]
    if missing_columns:
        raise ValueError(f"column(s) not found: {', '.join(missing_columns)}")
    alpha = _validate_probability(alpha, "alpha")
    policy = str(nan_policy).strip().lower()
    if policy not in _NAN_POLICIES:
        raise ValueError(f"nan_policy must be one of {sorted(_NAN_POLICIES)}")

    frame = data[[dependent, factor_a, factor_b]].copy()
    try:
        response = pd.to_numeric(frame[dependent], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{dependent} must be numeric") from exc
    complete = (
        np.isfinite(response)
        & frame[factor_a].notna().to_numpy()
        & frame[factor_b].notna().to_numpy()
    )
    had_missing = not bool(complete.all())
    if had_missing and policy == "raise":
        raise ValueError("ANOVA data contain missing or non-finite values")
    if had_missing and policy == "propagate":
        raise ValueError("two_way_anova cannot propagate a missing design; use omit or raise")
    if policy == "omit":
        frame = frame.loc[complete].reset_index(drop=True)
        response = response[complete]
    if len(frame) < 4:
        raise ValueError("two-way ANOVA needs at least four complete observations")

    _preflight_two_way_design(
        frame,
        factor_a,
        factor_b,
        interaction=bool(interaction),
    )
    a_matrix, _, a_levels = _effect_coding(frame[factor_a], factor_a)
    b_matrix, _, b_levels = _effect_coding(frame[factor_b], factor_b)
    intercept_matrix = np.ones((len(frame), 1), dtype=float)
    interaction_matrix = np.column_stack(
        [a_matrix[:, i] * b_matrix[:, j] for i in range(a_matrix.shape[1]) for j in range(b_matrix.shape[1])]
    )

    pieces: Dict[str, np.ndarray] = {
        "Intercept": intercept_matrix,
        factor_a: a_matrix,
        factor_b: b_matrix,
    }
    interaction_name = f"{factor_a}:{factor_b}"
    if interaction:
        pieces[interaction_name] = interaction_matrix

    def design(term_names: Sequence[str]) -> np.ndarray:
        return np.column_stack([pieces[name] for name in term_names])

    full_terms = ["Intercept", factor_a, factor_b]
    if interaction:
        full_terms.append(interaction_name)
    full_design = design(full_terms)
    full_sse, full_rank = _least_squares_sse(full_design, response)
    if full_rank < full_design.shape[1]:
        raise ValueError(
            "two-way ANOVA design is rank deficient; check for empty cells, "
            "confounded factors, or unused levels"
        )
    residual_df = float(len(frame) - full_rank)
    if residual_df <= 0:
        raise ValueError("two-way ANOVA needs replication to estimate residual variance")
    residual_ms = full_sse / residual_df
    centered = response - float(np.mean(response))
    total_ss = float(centered @ centered)

    term_specs: list[tuple[str, float, float]] = []
    if ss_type == 2:
        # Main effects are tested in the additive hierarchy.  The full-model
        # residual remains the denominator when an interaction is requested.
        for term, other in ((factor_a, factor_b), (factor_b, factor_a)):
            reduced_terms = ["Intercept", other]
            augmented_terms = ["Intercept", factor_a, factor_b]
            reduced_sse, reduced_rank = _least_squares_sse(design(reduced_terms), response)
            augmented_sse, augmented_rank = _least_squares_sse(design(augmented_terms), response)
            term_specs.append(
                (term, max(0.0, reduced_sse - augmented_sse), float(augmented_rank - reduced_rank))
            )
        if interaction:
            additive_sse, additive_rank = _least_squares_sse(
                design(["Intercept", factor_a, factor_b]), response
            )
            term_specs.append(
                (interaction_name, max(0.0, additive_sse - full_sse), float(full_rank - additive_rank))
            )
    else:
        for term in full_terms[1:]:
            reduced_terms = [name for name in full_terms if name != term]
            reduced_sse, reduced_rank = _least_squares_sse(design(reduced_terms), response)
            term_specs.append(
                (term, max(0.0, reduced_sse - full_sse), float(full_rank - reduced_rank))
            )

    anova_terms: list[AnovaTerm] = []
    for term, sum_squares, term_df in term_specs:
        if term_df <= 0:
            raise ValueError(f"term {term!r} is not estimable")
        mean_square = sum_squares / term_df
        f_statistic = _anova_f(mean_square, residual_ms)
        p_value = float(stats.f.sf(f_statistic, term_df, residual_df))
        eta_squared = sum_squares / total_ss if total_ss > 0 else 0.0
        partial_denominator = sum_squares + full_sse
        partial_eta = sum_squares / partial_denominator if partial_denominator > 0 else 0.0
        anova_terms.append(
            AnovaTerm(
                term=term,
                sum_squares=sum_squares,
                degrees_of_freedom=term_df,
                mean_square=mean_square,
                f_statistic=f_statistic,
                p_value=p_value,
                reject_null=_reject(p_value, alpha),
                eta_squared=eta_squared,
                partial_eta_squared=partial_eta,
            )
        )
    anova_terms.append(
        AnovaTerm(
            term="Residual",
            sum_squares=full_sse,
            degrees_of_freedom=residual_df,
            mean_square=residual_ms,
            f_statistic=None,
            p_value=None,
            reject_null=None,
        )
    )
    return AnovaResult(
        method="Two-way ANOVA",
        terms=tuple(anova_terms),
        alpha=alpha,
        total_sum_squares=total_ss,
        total_degrees_of_freedom=float(len(frame) - 1),
        residual_sum_squares=full_sse,
        residual_degrees_of_freedom=residual_df,
        sample_size=int(len(frame)),
        factor_levels={factor_a: a_levels, factor_b: b_levels},
        ss_type=ss_type,
        notes=("Effect-coded fixed-effects OLS model.",),
    )


# ---------------------------------------------------------------------------
# Non-parametric and assumption tests


def mann_whitney_test(
    first: Sequence[float],
    second: Sequence[float],
    *,
    alternative: str = "two-sided",
    method: str = "auto",
    use_continuity: bool = True,
    alpha: float = 0.05,
    nan_policy: str = "omit",
) -> HypothesisTestResult:
    """Mann-Whitney U test with rank-biserial effect size."""

    alternative, alpha, _, nan_policy = _validate_common(
        alternative, alpha, 0.95, nan_policy
    )
    a, missing_a = _clean_1d(first, "first", nan_policy=nan_policy, minimum_size=1)
    b, missing_b = _clean_1d(second, "second", nan_policy=nan_policy, minimum_size=1)
    if (missing_a or missing_b) and nan_policy == "propagate":
        return _propagated_test(
            "Mann-Whitney U test",
            alpha=alpha,
            alternative=alternative,
            sample_sizes={"first": int(a.size), "second": int(b.size)},
        )
    scipy_result = stats.mannwhitneyu(
        a,
        b,
        alternative=alternative,
        method=method,
        use_continuity=bool(use_continuity),
    )
    statistic, p_value = _float(scipy_result.statistic), _float(scipy_result.pvalue)
    rank_biserial = 2.0 * statistic / (a.size * b.size) - 1.0
    return HypothesisTestResult(
        method="Mann-Whitney U test",
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        reject_null=_reject(p_value, alpha),
        alternative=alternative,
        estimate=float(np.median(a) - np.median(b)),
        effect_sizes=(
            EffectSize(
                "rank_biserial_correlation",
                rank_biserial,
                _interpret_correlation(rank_biserial),
            ),
        ),
        sample_sizes={"first": int(a.size), "second": int(b.size)},
        metadata={
            "first_median": float(np.median(a)),
            "second_median": float(np.median(b)),
            "median_difference": float(np.median(a) - np.median(b)),
            "scipy_method": method,
            "use_continuity": bool(use_continuity),
        },
    )


def wilcoxon_signed_rank_test(
    first: Sequence[float],
    second: Optional[Sequence[float]] = None,
    *,
    alternative: str = "two-sided",
    zero_method: str = "wilcox",
    correction: bool = False,
    method: str = "auto",
    alpha: float = 0.05,
    nan_policy: str = "omit",
) -> HypothesisTestResult:
    """Wilcoxon signed-rank test for paired data or differences vs zero."""

    alternative, alpha, _, nan_policy = _validate_common(
        alternative, alpha, 0.95, nan_policy
    )
    if zero_method not in {"wilcox", "pratt", "zsplit"}:
        raise ValueError("zero_method must be 'wilcox', 'pratt', or 'zsplit'")
    if second is None:
        differences, missing = _clean_1d(
            first, "differences", nan_policy=nan_policy, minimum_size=1
        )
    else:
        a, b, missing = _clean_paired(
            first,
            second,
            first_name="first",
            second_name="second",
            nan_policy=nan_policy,
            minimum_size=1,
        )
        differences = a - b
    if missing and nan_policy == "propagate":
        return _propagated_test(
            "Wilcoxon signed-rank test",
            alpha=alpha,
            alternative=alternative,
            sample_sizes={"pairs": int(differences.size)},
        )

    nonzero = differences[differences != 0]
    if nonzero.size == 0:
        statistic, p_value, rank_biserial = 0.0, 1.0, 0.0
        notes = ("All paired differences are zero.",)
    else:
        scipy_result = stats.wilcoxon(
            differences,
            alternative=alternative,
            zero_method=zero_method,
            correction=bool(correction),
            method=method,
        )
        statistic, p_value = _float(scipy_result.statistic), _float(scipy_result.pvalue)
        ranks = stats.rankdata(np.abs(nonzero), method="average")
        positive = float(np.sum(ranks[nonzero > 0]))
        negative = float(np.sum(ranks[nonzero < 0]))
        rank_biserial = (positive - negative) / (positive + negative)
        notes = ()
    return HypothesisTestResult(
        method="Wilcoxon signed-rank test",
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        reject_null=_reject(p_value, alpha),
        alternative=alternative,
        estimate=float(np.median(differences)),
        effect_sizes=(
            EffectSize(
                "matched_pairs_rank_biserial",
                rank_biserial,
                _interpret_correlation(rank_biserial),
            ),
        ),
        sample_sizes={"pairs": int(differences.size), "nonzero_pairs": int(nonzero.size)},
        metadata={
            "median_difference": float(np.median(differences)),
            "zero_method": zero_method,
            "scipy_method": method,
            "continuity_correction": bool(correction),
        },
        notes=notes,
    )


def kruskal_wallis_test(
    *groups: Sequence[float] | Mapping[str, Sequence[float]],
    group_names: Optional[Sequence[str]] = None,
    alpha: float = 0.05,
    nan_policy: str = "omit",
) -> HypothesisTestResult:
    """Kruskal-Wallis H test with epsilon-squared effect size."""

    alpha = _validate_probability(alpha, "alpha")
    policy = str(nan_policy).strip().lower()
    if policy not in _NAN_POLICIES:
        raise ValueError(f"nan_policy must be one of {sorted(_NAN_POLICIES)}")
    arrays, names, missing = _prepare_groups(
        groups, group_names=group_names, nan_policy=policy, minimum_size=1
    )
    sizes = {name: int(array.size) for name, array in zip(names, arrays)}
    if missing and policy == "propagate":
        return _propagated_test(
            "Kruskal-Wallis H test",
            alpha=alpha,
            alternative="group-differences",
            sample_sizes=sizes,
        )
    all_values = np.concatenate(arrays)
    if np.ptp(all_values) == 0:
        statistic, p_value = 0.0, 1.0
        notes = ("All observations are identical.",)
    else:
        result = stats.kruskal(*arrays, nan_policy="raise")
        statistic, p_value = _float(result.statistic), _float(result.pvalue)
        notes = ()
    total = int(all_values.size)
    count_groups = len(arrays)
    epsilon_squared = max(
        0.0,
        (statistic - count_groups + 1.0) / (total - count_groups),
    ) if total > count_groups else float("nan")
    return HypothesisTestResult(
        method="Kruskal-Wallis H test",
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        reject_null=_reject(p_value, alpha),
        alternative="group-differences",
        degrees_of_freedom=float(count_groups - 1),
        effect_sizes=(
            EffectSize(
                "epsilon_squared",
                epsilon_squared,
                _interpret_variance_effect(epsilon_squared),
            ),
        ),
        sample_sizes=sizes,
        metadata={
            "group_medians": {
                name: float(np.median(array)) for name, array in zip(names, arrays)
            }
        },
        notes=notes,
    )


def shapiro_wilk_test(
    sample: Sequence[float],
    *,
    alpha: float = 0.05,
    nan_policy: str = "omit",
) -> HypothesisTestResult:
    """Shapiro-Wilk normality test (null hypothesis: normal distribution)."""

    alpha = _validate_probability(alpha, "alpha")
    policy = str(nan_policy).strip().lower()
    if policy not in _NAN_POLICIES:
        raise ValueError(f"nan_policy must be one of {sorted(_NAN_POLICIES)}")
    values, missing = _clean_1d(
        sample, "sample", nan_policy=policy, minimum_size=3
    )
    if missing and policy == "propagate":
        return _propagated_test(
            "Shapiro-Wilk normality test",
            alpha=alpha,
            alternative="non-normal",
            sample_sizes={"sample": int(values.size)},
        )
    if np.ptp(values) == 0:
        statistic, p_value = 1.0, 1.0
        notes = ("All observations are identical; normality is not identifiable.",)
    else:
        result = stats.shapiro(values)
        statistic, p_value = _float(result.statistic), _float(result.pvalue)
        notes = (
            ("For samples above 5,000, SciPy notes that the W statistic is accurate "
             "but the p-value may be approximate."),
        ) if values.size > 5_000 else ()
    return HypothesisTestResult(
        method="Shapiro-Wilk normality test",
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        reject_null=_reject(p_value, alpha),
        alternative="non-normal",
        sample_sizes={"sample": int(values.size)},
        metadata={"null_hypothesis": "sample is normally distributed"},
        notes=notes,
    )


def levene_test(
    *groups: Sequence[float] | Mapping[str, Sequence[float]],
    group_names: Optional[Sequence[str]] = None,
    center: str = "median",
    proportiontocut: float = 0.05,
    alpha: float = 0.05,
    nan_policy: str = "omit",
) -> HypothesisTestResult:
    """Levene/Brown-Forsythe homogeneity-of-variance test."""

    center = str(center).strip().lower()
    if center not in {"mean", "median", "trimmed"}:
        raise ValueError("center must be 'mean', 'median', or 'trimmed'")
    if not 0.0 <= float(proportiontocut) < 0.5:
        raise ValueError("proportiontocut must be in [0, 0.5)")
    alpha = _validate_probability(alpha, "alpha")
    policy = str(nan_policy).strip().lower()
    if policy not in _NAN_POLICIES:
        raise ValueError(f"nan_policy must be one of {sorted(_NAN_POLICIES)}")
    arrays, names, missing = _prepare_groups(
        groups, group_names=group_names, nan_policy=policy, minimum_size=2
    )
    sizes = {name: int(array.size) for name, array in zip(names, arrays)}
    if missing and policy == "propagate":
        return _propagated_test(
            "Levene homogeneity-of-variance test",
            alpha=alpha,
            alternative="unequal-variance",
            sample_sizes=sizes,
        )
    if all(float(np.ptp(array)) == 0.0 for array in arrays):
        statistic, p_value = 0.0, 1.0
        notes = ("Every group has zero within-group variance.",)
    else:
        result = stats.levene(
            *arrays,
            center=center,
            proportiontocut=float(proportiontocut),
        )
        statistic, p_value = _float(result.statistic), _float(result.pvalue)
        notes = ()
    return HypothesisTestResult(
        method="Levene homogeneity-of-variance test",
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        reject_null=_reject(p_value, alpha),
        alternative="unequal-variance",
        degrees_of_freedom=(float(len(arrays) - 1), float(sum(map(len, arrays)) - len(arrays))),
        sample_sizes=sizes,
        metadata={
            "center": center,
            "proportion_to_cut": float(proportiontocut),
            "null_hypothesis": "group variances are equal",
        },
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Multiple testing


_CORRECTION_METHODS = {
    "none",
    "bonferroni",
    "sidak",
    "holm",
    "fdr_bh",
    "fdr_by",
}


def multiple_testing_correction(
    p_values: Sequence[float],
    *,
    method: str = "holm",
    alpha: float = 0.05,
    nan_policy: str = "omit",
) -> MultipleTestingResult:
    """Adjust a family of p-values while preserving the original order.

    Supported methods are Bonferroni, Sidak, Holm step-down, Benjamini-Hochberg
    FDR, and Benjamini-Yekutieli FDR.  With ``nan_policy='omit'``, missing
    p-values are excluded from the family size and represented as ``None`` in
    the result contract.
    """

    method_key = str(method).strip().lower().replace("-", "_")
    aliases = {
        "bh": "fdr_bh",
        "benjamini_hochberg": "fdr_bh",
        "by": "fdr_by",
        "benjamini_yekutieli": "fdr_by",
    }
    method_key = aliases.get(method_key, method_key)
    if method_key not in _CORRECTION_METHODS:
        raise ValueError(f"method must be one of {sorted(_CORRECTION_METHODS)}")
    alpha = _validate_probability(alpha, "alpha")
    policy = str(nan_policy).strip().lower()
    if policy not in _NAN_POLICIES:
        raise ValueError(f"nan_policy must be one of {sorted(_NAN_POLICIES)}")
    raw = _as_numeric_1d(p_values, "p_values")
    if raw.size == 0:
        raise ValueError("p_values must not be empty")
    finite = np.isfinite(raw)
    if not finite.all():
        if policy == "raise":
            raise ValueError("p_values contain NaN or infinity")
        if policy == "propagate":
            originals = tuple(float(value) if math.isfinite(value) else None for value in raw)
            return MultipleTestingResult(
                method_key,
                alpha,
                originals,
                tuple(None for _ in raw),
                tuple(False for _ in raw),
                0,
            )
    tested = raw[finite]
    if np.any((tested < 0.0) | (tested > 1.0)):
        raise ValueError("every finite p-value must lie in [0, 1]")
    count = int(tested.size)
    if count == 0:
        raise ValueError("no finite p-values remain after omission")

    if method_key == "none":
        adjusted = tested.copy()
    elif method_key == "bonferroni":
        adjusted = np.minimum(1.0, tested * count)
    elif method_key == "sidak":
        with np.errstate(divide="ignore", invalid="ignore"):
            adjusted = -np.expm1(count * np.log1p(-tested))
        adjusted = np.clip(adjusted, 0.0, 1.0)
    else:
        order = np.argsort(tested, kind="mergesort")
        sorted_p = tested[order]
        if method_key == "holm":
            scaled = (count - np.arange(count)) * sorted_p
            sorted_adjusted = np.maximum.accumulate(scaled)
        else:
            harmonic = (
                float(np.sum(1.0 / np.arange(1, count + 1)))
                if method_key == "fdr_by"
                else 1.0
            )
            scaled = sorted_p * count * harmonic / np.arange(1, count + 1)
            sorted_adjusted = np.minimum.accumulate(scaled[::-1])[::-1]
        sorted_adjusted = np.clip(sorted_adjusted, 0.0, 1.0)
        adjusted = np.empty_like(sorted_adjusted)
        adjusted[order] = sorted_adjusted

    original_contract: list[Optional[float]] = []
    adjusted_contract: list[Optional[float]] = []
    decisions: list[bool] = []
    tested_index = 0
    for is_finite, original in zip(finite, raw):
        if not is_finite:
            original_contract.append(None)
            adjusted_contract.append(None)
            decisions.append(False)
            continue
        adj = float(adjusted[tested_index])
        original_contract.append(float(original))
        adjusted_contract.append(adj)
        decisions.append(bool(adj <= alpha))
        tested_index += 1
    return MultipleTestingResult(
        method=method_key,
        alpha=alpha,
        original_p_values=tuple(original_contract),
        adjusted_p_values=tuple(adjusted_contract),
        reject_null=tuple(decisions),
        tested_count=count,
    )


# ---------------------------------------------------------------------------
# Multiple linear regression


def _coerce_regression_inputs(
    predictors: pd.DataFrame | Sequence[Sequence[float]] | np.ndarray,
    response: pd.Series | Sequence[float] | np.ndarray,
    *,
    predictor_names: Optional[Sequence[str]],
    nan_policy: str,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...], int]:
    if isinstance(predictors, pd.DataFrame):
        if predictors.columns.duplicated().any():
            raise ValueError("predictor column names must be unique")
        names = tuple(str(column) for column in predictors.columns)
        try:
            matrix = predictors.apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("all predictors must be numeric") from exc
        if predictor_names is not None:
            supplied = tuple(str(name) for name in predictor_names)
            if supplied != names:
                raise ValueError("predictor_names must match DataFrame columns exactly")
    else:
        try:
            matrix = np.asarray(predictors, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("all predictors must be numeric") from exc
        if matrix.ndim == 1:
            matrix = matrix.reshape(-1, 1)
        if matrix.ndim != 2:
            raise ValueError("predictors must be a two-dimensional matrix")
        names = (
            tuple(str(name) for name in predictor_names)
            if predictor_names is not None
            else tuple(f"x{index + 1}" for index in range(matrix.shape[1]))
        )
    if matrix.shape[1] == 0:
        raise ValueError("at least one predictor is required")
    if len(names) != matrix.shape[1]:
        raise ValueError("predictor_names must match the number of predictor columns")
    if len(set(names)) != len(names):
        raise ValueError("predictor_names must be unique")
    y = _as_numeric_1d(response, "response")
    if y.size != matrix.shape[0]:
        raise ValueError(
            f"predictors and response must have the same row count; got {matrix.shape[0]} and {y.size}"
        )
    finite_rows = np.isfinite(y) & np.isfinite(matrix).all(axis=1)
    omitted = int(np.count_nonzero(~finite_rows))
    if omitted:
        if nan_policy == "raise":
            raise ValueError("regression inputs contain NaN or infinity")
        if nan_policy == "propagate":
            raise ValueError("regression cannot propagate a missing design; use omit or raise")
        matrix, y = matrix[finite_rows], y[finite_rows]
    return matrix, y, names, omitted


def _variance_inflation_factors(
    predictors: np.ndarray, names: tuple[str, ...]
) -> Dict[str, float]:
    count = predictors.shape[1]
    if count == 1:
        return {names[0]: 1.0}
    output: Dict[str, float] = {}
    for index, name in enumerate(names):
        target = predictors[:, index]
        others = np.delete(predictors, index, axis=1)
        auxiliary = np.column_stack([np.ones(len(target)), others])
        coefficients, _, _, _ = np.linalg.lstsq(auxiliary, target, rcond=None)
        residual = target - auxiliary @ coefficients
        sse = float(residual @ residual)
        centered = target - float(np.mean(target))
        sst = float(centered @ centered)
        if sst <= 0:
            vif = float("inf")
        else:
            r_squared = max(0.0, min(1.0, 1.0 - sse / sst))
            vif = 1.0 / (1.0 - r_squared) if r_squared < 1.0 else float("inf")
        output[name] = float(vif)
    return output


def _breusch_pagan(
    residuals: np.ndarray, predictors: np.ndarray
) -> tuple[Optional[float], Optional[float]]:
    if predictors.shape[1] == 0 or len(residuals) <= predictors.shape[1] + 1:
        return None, None
    squared = residuals**2
    design = np.column_stack([np.ones(len(residuals)), predictors])
    coefficients, _, rank, _ = np.linalg.lstsq(design, squared, rcond=None)
    if rank < design.shape[1]:
        return None, None
    fitted = design @ coefficients
    centered = squared - float(np.mean(squared))
    total = float(centered @ centered)
    if total <= 0:
        return 0.0, 1.0
    error = squared - fitted
    r_squared = max(0.0, min(1.0, 1.0 - float(error @ error) / total))
    statistic = float(len(residuals) * r_squared)
    p_value = float(stats.chi2.sf(statistic, predictors.shape[1]))
    return statistic, p_value


def multiple_linear_regression(
    predictors: pd.DataFrame | Sequence[Sequence[float]] | np.ndarray,
    response: pd.Series | Sequence[float] | np.ndarray,
    *,
    predictor_names: Optional[Sequence[str]] = None,
    add_intercept: bool = True,
    alpha: float = 0.05,
    confidence_level: float = 0.95,
    nan_policy: str = "omit",
) -> RegressionResult:
    """Ordinary least-squares regression with inferential diagnostics.

    The result includes coefficient tests/CIs, ANOVA-style model F test,
    information criteria, VIF, Durbin-Watson, residual Shapiro-Wilk,
    Breusch-Pagan, leverage, standardized residuals, and Cook's distance.
    Rank-deficient designs are rejected because coefficient-level inference is
    not identifiable in that case.
    """

    alpha = _validate_probability(alpha, "alpha")
    confidence_level = _validate_probability(confidence_level, "confidence_level")
    policy = str(nan_policy).strip().lower()
    if policy not in _NAN_POLICIES:
        raise ValueError(f"nan_policy must be one of {sorted(_NAN_POLICIES)}")
    raw_predictors, y, names, omitted = _coerce_regression_inputs(
        predictors,
        response,
        predictor_names=predictor_names,
        nan_policy=policy,
    )
    n_observations, predictor_count = raw_predictors.shape
    if n_observations < 3:
        raise ValueError("regression needs at least three complete observations")
    if np.any(np.ptp(raw_predictors, axis=0) == 0):
        constant_names = [
            names[index] for index in np.where(np.ptp(raw_predictors, axis=0) == 0)[0]
        ]
        raise ValueError(f"constant predictor(s) are not identifiable: {', '.join(constant_names)}")
    if np.ptp(y) == 0:
        raise ValueError("response must have non-zero variance")

    design = (
        np.column_stack([np.ones(n_observations), raw_predictors])
        if add_intercept
        else raw_predictors.copy()
    )
    coefficient_names = (("Intercept",) + names) if add_intercept else names
    coefficients, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    rank = int(rank)
    if rank < design.shape[1]:
        raise ValueError(
            "regression design is rank deficient; remove duplicate or perfectly "
            "collinear predictors"
        )
    residual_df = int(n_observations - rank)
    if residual_df <= 0:
        raise ValueError(
            "regression needs more complete observations than fitted coefficients"
        )

    fitted = design @ coefficients
    residuals = y - fitted
    sse = float(residuals @ residuals)
    if add_intercept:
        centered = y - float(np.mean(y))
        total_df = n_observations - 1
    else:
        centered = y
        total_df = n_observations
    total_ss = float(centered @ centered)
    regression_ss = max(0.0, total_ss - sse)
    model_df = int(rank - 1 if add_intercept else rank)
    mse = sse / residual_df
    residual_standard_error = math.sqrt(max(0.0, mse))
    rmse = math.sqrt(max(0.0, sse / n_observations))
    r_squared = 1.0 - sse / total_ss
    adjusted_r_squared = 1.0 - (1.0 - r_squared) * total_df / residual_df
    if model_df > 0:
        f_statistic = _anova_f(regression_ss / model_df, mse)
        f_p_value = float(stats.f.sf(f_statistic, model_df, residual_df))
    else:
        f_statistic, f_p_value = float("nan"), float("nan")

    xtx_inverse = np.linalg.inv(design.T @ design)
    covariance = mse * xtx_inverse
    standard_errors = np.sqrt(np.maximum(0.0, np.diag(covariance)))
    with np.errstate(divide="ignore", invalid="ignore"):
        t_values = coefficients / standard_errors
    p_values = 2.0 * stats.t.sf(np.abs(t_values), residual_df)
    critical = float(stats.t.ppf((1.0 + confidence_level) / 2.0, residual_df))
    coefficient_results = tuple(
        RegressionCoefficient(
            term=name,
            estimate=float(estimate),
            standard_error=float(se),
            t_statistic=float(t_value),
            p_value=float(p_value),
            confidence_interval=ConfidenceInterval(
                float(estimate - critical * se),
                float(estimate + critical * se),
                confidence_level,
            ),
            reject_null=_reject(float(p_value), alpha),
        )
        for name, estimate, se, t_value, p_value in zip(
            coefficient_names, coefficients, standard_errors, t_values, p_values
        )
    )

    # Influence diagnostics.
    leverage = np.einsum("ij,jk,ik->i", design, xtx_inverse, design, optimize=True)
    leverage = np.clip(leverage, 0.0, 1.0)
    denominator = np.sqrt(np.maximum(np.finfo(float).tiny, mse * (1.0 - leverage)))
    if mse == 0:
        standardized_residuals = np.zeros_like(residuals)
    else:
        standardized_residuals = residuals / denominator
    cook_denominator = np.maximum(np.finfo(float).tiny, 1.0 - leverage)
    cooks_distance = (
        standardized_residuals**2 * leverage / (rank * cook_denominator)
    )
    durbin_denominator = float(residuals @ residuals)
    durbin_watson = (
        float(np.sum(np.diff(residuals) ** 2) / durbin_denominator)
        if durbin_denominator > 0
        else 0.0
    )

    # A scale-aware condition number is more useful than one dominated solely
    # by heterogeneous measurement units.  Keep the intercept unchanged.
    centered_predictors = raw_predictors - np.mean(raw_predictors, axis=0)
    scales = np.std(centered_predictors, axis=0, ddof=1)
    standardized_predictors = centered_predictors / scales
    condition_design = (
        np.column_stack([np.ones(n_observations), standardized_predictors])
        if add_intercept
        else standardized_predictors
    )
    condition_number = float(np.linalg.cond(condition_design))
    vifs = _variance_inflation_factors(raw_predictors, names)

    shapiro_w: Optional[float]
    shapiro_p: Optional[float]
    if n_observations >= 3 and np.ptp(residuals) > 0:
        shapiro_result = stats.shapiro(residuals)
        shapiro_w = _float(shapiro_result.statistic)
        shapiro_p = _float(shapiro_result.pvalue)
    else:
        shapiro_w = shapiro_p = None
    bp_lm, bp_p = _breusch_pagan(residuals, raw_predictors)

    sigma2_mle = max(sse / n_observations, np.finfo(float).tiny)
    log_likelihood = float(
        -0.5 * n_observations * (math.log(2.0 * math.pi) + 1.0 + math.log(sigma2_mle))
    )
    parameter_count = rank + 1  # fitted coefficients plus residual variance
    aic = float(-2.0 * log_likelihood + 2.0 * parameter_count)
    bic = float(-2.0 * log_likelihood + math.log(n_observations) * parameter_count)
    notes: list[str] = []
    if omitted:
        notes.append(f"Omitted {omitted} incomplete row(s).")
    if n_observations > 5_000:
        notes.append("Residual Shapiro-Wilk p-value may be approximate above 5,000 rows.")
    diagnostics = RegressionDiagnostics(
        durbin_watson=durbin_watson,
        condition_number=condition_number,
        variance_inflation_factors=vifs,
        shapiro_w=shapiro_w,
        shapiro_p_value=shapiro_p,
        breusch_pagan_lm=bp_lm,
        breusch_pagan_p_value=bp_p,
        maximum_leverage=float(np.max(leverage)),
        maximum_cooks_distance=float(np.max(cooks_distance)),
    )
    return RegressionResult(
        method="Ordinary least squares multiple linear regression",
        coefficients=coefficient_results,
        n_observations=int(n_observations),
        predictor_names=names,
        add_intercept=bool(add_intercept),
        rank=rank,
        degrees_of_freedom_model=model_df,
        degrees_of_freedom_residual=residual_df,
        r_squared=float(r_squared),
        adjusted_r_squared=float(adjusted_r_squared),
        f_statistic=float(f_statistic),
        f_p_value=float(f_p_value),
        rmse=float(rmse),
        residual_standard_error=float(residual_standard_error),
        sum_squared_errors=sse,
        regression_sum_squares=regression_ss,
        total_sum_squares=total_ss,
        log_likelihood=log_likelihood,
        aic=aic,
        bic=bic,
        covariance_matrix=tuple(tuple(float(value) for value in row) for row in covariance),
        fitted_values=tuple(float(value) for value in fitted),
        residuals=tuple(float(value) for value in residuals),
        leverage=tuple(float(value) for value in leverage),
        standardized_residuals=tuple(float(value) for value in standardized_residuals),
        cooks_distance=tuple(float(value) for value in cooks_distance),
        diagnostics=diagnostics,
        confidence_level=confidence_level,
        notes=tuple(notes),
        alpha=alpha,
        reject_null=_reject(float(f_p_value), alpha),
    )
