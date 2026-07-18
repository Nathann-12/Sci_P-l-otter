"""Stable DataFrame-facing operations for UI, recipes, batch, and local AI.

Numerical modules return rich immutable result objects.  This adapter keeps
column mapping and report-table formatting in one place, preventing the GUI
and batch runner from implementing subtly different statistics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Mapping, Sequence
import warnings

import numpy as np
import pandas as pd

from analysis.global_fitting import GlobalFitDataset, global_fit
from analysis.peak_analysis import analyze_peaks
from analysis.statistics import (
    independent_t_test,
    kruskal_wallis_test,
    levene_test,
    mann_whitney_test,
    multiple_linear_regression,
    multiple_testing_correction,
    one_sample_t_test,
    one_way_anova,
    paired_t_test,
    shapiro_wilk_test,
    two_way_anova,
    wilcoxon_signed_rank_test,
)


class ScientificOperationError(ValueError):
    pass


@dataclass(frozen=True)
class _AssumptionResult:
    method: str
    statistic: float
    p_value: float
    reject_null: bool


STATISTICAL_OPERATIONS = (
    "one_sample_t_test",
    "independent_t_test",
    "paired_t_test",
    "one_way_anova",
    "two_way_anova",
    "mann_whitney_test",
    "wilcoxon_signed_rank_test",
    "kruskal_wallis_test",
    "multiple_linear_regression",
    "adjust_p_values",
)


def execute_statistical_operation(
    dataframe: pd.DataFrame,
    operation: str,
    params: Mapping[str, Any],
) -> pd.DataFrame:
    """Execute one named statistical analysis and return a report table."""

    frame = _require_frame(dataframe)
    op = str(operation).strip().lower()
    alpha = float(params.get("alpha", 0.05))
    confidence = float(params.get("confidence_level", 1.0 - alpha))
    alternative = str(params.get("alternative", "two-sided"))

    if op == "one_sample_t_test":
        column = _column(frame, params, "sample")
        sample = _numeric(frame, column)
        result = one_sample_t_test(
            sample,
            popmean=float(params.get("popmean", 0.0)),
            alternative=alternative,
            alpha=alpha,
            confidence_level=confidence,
        )
        assumptions = [_safe_assumption("Shapiro-Wilk", shapiro_wilk_test, sample, alpha=alpha)]
        return hypothesis_report(result, assumptions=assumptions)

    if op in {"independent_t_test", "mann_whitney_test"}:
        first_name = _column(frame, params, "first")
        second_name = _column(frame, params, "second")
        _distinct(first_name, second_name)
        first, second = _numeric(frame, first_name), _numeric(frame, second_name)
        if op == "independent_t_test":
            result = independent_t_test(
                first, second,
                equal_var=bool(params.get("equal_var", False)),
                alternative=alternative,
                alpha=alpha,
                confidence_level=confidence,
            )
        else:
            result = mann_whitney_test(
                first, second, alternative=alternative, alpha=alpha,
            )
        assumptions = [
            _safe_assumption(f"Shapiro-Wilk: {first_name}", shapiro_wilk_test, first, alpha=alpha),
            _safe_assumption(f"Shapiro-Wilk: {second_name}", shapiro_wilk_test, second, alpha=alpha),
            _safe_assumption("Levene equal variance", levene_test, first, second, alpha=alpha,
                             group_names=[first_name, second_name]),
        ]
        return hypothesis_report(result, assumptions=assumptions)

    if op in {"paired_t_test", "wilcoxon_signed_rank_test"}:
        first_name = _column(frame, params, "first")
        second_name = _column(frame, params, "second")
        _distinct(first_name, second_name)
        paired = frame[[first_name, second_name]].apply(pd.to_numeric, errors="coerce").dropna()
        if paired.empty:
            raise ScientificOperationError("No complete numeric pairs remain after removing missing values.")
        first, second = paired[first_name].to_numpy(), paired[second_name].to_numpy()
        if op == "paired_t_test":
            result = paired_t_test(
                first, second, alternative=alternative, alpha=alpha,
                confidence_level=confidence,
            )
        else:
            result = wilcoxon_signed_rank_test(
                first, second, alternative=alternative, alpha=alpha,
            )
        assumptions = [
            _safe_assumption("Shapiro-Wilk: paired differences", shapiro_wilk_test,
                             first - second, alpha=alpha),
        ]
        return hypothesis_report(result, assumptions=assumptions)

    if op in {"one_way_anova", "kruskal_wallis_test"}:
        groups, names = _groups(frame, params)
        result = (
            one_way_anova(*groups, group_names=names, alpha=alpha)
            if op == "one_way_anova"
            else kruskal_wallis_test(*groups, group_names=names, alpha=alpha)
        )
        assumptions = [
            _safe_assumption(f"Shapiro-Wilk: {name}", shapiro_wilk_test, group, alpha=alpha)
            for name, group in zip(names, groups)
        ]
        assumptions.append(
            _safe_assumption("Levene equal variance", levene_test, *groups,
                             group_names=names, alpha=alpha)
        )
        if op == "one_way_anova":
            return anova_report(result, assumptions=assumptions)
        return hypothesis_report(result, assumptions=assumptions)

    if op == "two_way_anova":
        dependent = _column(frame, params, "dependent")
        factor_a = _column(frame, params, "factor_a")
        factor_b = _column(frame, params, "factor_b")
        if len({dependent, factor_a, factor_b}) != 3:
            raise ScientificOperationError("Dependent, Factor A, and Factor B must be different columns.")
        result = two_way_anova(
            frame,
            dependent,
            factor_a,
            factor_b,
            interaction=bool(params.get("interaction", True)),
            ss_type=int(params.get("ss_type", 2)),
            alpha=alpha,
        )
        return anova_report(result)

    if op == "multiple_linear_regression":
        response = _column(frame, params, "response")
        predictors = _columns(frame, params, "predictors", minimum=1)
        if response in predictors:
            raise ScientificOperationError("The response cannot also be a predictor.")
        result = multiple_linear_regression(
            frame[predictors],
            frame[response],
            predictor_names=predictors,
            add_intercept=bool(params.get("add_intercept", True)),
            alpha=alpha,
            confidence_level=confidence,
        )
        return regression_report(result)

    if op == "adjust_p_values":
        p_column = _column(frame, params, "p_column")
        original = pd.to_numeric(frame[p_column], errors="coerce").to_numpy()
        result = multiple_testing_correction(
            original, method=str(params.get("method", "holm")), alpha=alpha,
        )
        return pd.DataFrame({
            "original_p_value": result.original_p_values,
            "adjusted_p_value": result.adjusted_p_values,
            "reject_null": result.reject_null,
            "method": result.method,
            "alpha": result.alpha,
        })

    raise ScientificOperationError(f"Unknown statistical operation: {operation}")


def execute_global_fit(dataframe: pd.DataFrame, params: Mapping[str, Any]):
    frame = _require_frame(dataframe)
    x_column = _column(frame, params, "x")
    y_columns = _columns(frame, params, "ys", minimum=2)
    if x_column in y_columns:
        raise ScientificOperationError("The X column cannot also be a Y dataset.")
    sigma_column = params.get("sigma")
    sigma = _numeric(frame, str(sigma_column), keep_nan=True) if sigma_column else None
    datasets = [
        GlobalFitDataset(
            _numeric(frame, x_column, keep_nan=True),
            _numeric(frame, name, keep_nan=True),
            name=name,
            sigma=sigma,
        )
        for name in y_columns
    ]
    return global_fit(
        datasets,
        str(params.get("model", "gaussian")),
        shared=list(params.get("shared") or []),
        initial=params.get("initial"),
        fixed=params.get("fixed"),
        bounds=params.get("bounds"),
        absolute_sigma=bool(params.get("absolute_sigma", False)),
        confidence=float(params.get("confidence", 0.95)),
        loss=str(params.get("loss", "linear")),
        max_nfev=int(params.get("max_nfev", 50_000)),
    )


def execute_peak_analysis(dataframe: pd.DataFrame, params: Mapping[str, Any]):
    frame = _require_frame(dataframe)
    x_column = _column(frame, params, "x")
    y_column = _column(frame, params, "y")
    _distinct(x_column, y_column)
    sigma_column = params.get("sigma")
    kwargs = {
        "model": str(params.get("model", "gaussian")),
        "baseline": str(params.get("baseline", "linear")),
        "direction": str(params.get("direction", "positive")),
        "prominence": params.get("prominence"),
        "height": params.get("height"),
        "distance": params.get("distance"),
        "width": params.get("width"),
        "max_peaks": int(params.get("max_peaks", 20)),
        "initial": params.get("initial"),
        "bounds": params.get("bounds"),
        "absolute_sigma": bool(params.get("absolute_sigma", False)),
        "confidence": float(params.get("confidence", 0.95)),
        "max_nfev": int(params.get("max_nfev", 50_000)),
        "constant_quantile": float(params.get("constant_quantile", 0.1)),
        "als_lambda": float(params.get("als_lambda", 1e5)),
        "als_p": float(params.get("als_p", 0.01)),
        "als_iterations": int(params.get("als_iterations", 10)),
    }
    if sigma_column:
        kwargs["sigma"] = _numeric(frame, str(sigma_column), keep_nan=True)
    return analyze_peaks(
        _numeric(frame, x_column, keep_nan=True),
        _numeric(frame, y_column, keep_nan=True),
        **kwargs,
    )


def hypothesis_report(result, *, assumptions: Sequence[Any] = ()) -> pd.DataFrame:
    rows = [
        _row("Test", "method", result.method),
        _row("Test", "statistic", result.statistic),
        _row("Test", "p_value", result.p_value),
        _row("Test", "alpha", result.alpha),
        _row("Test", "reject_null", result.reject_null),
        _row("Test", "alternative", result.alternative),
        _row("Estimate", "estimate", result.estimate),
        _row("Estimate", "standard_error", result.standard_error),
    ]
    if result.degrees_of_freedom is not None:
        rows.append(_row("Test", "degrees_of_freedom", result.degrees_of_freedom))
    ci = result.confidence_interval
    if ci is not None:
        rows.extend([
            _row("Confidence interval", "level", ci.level),
            _row("Confidence interval", "lower", ci.lower),
            _row("Confidence interval", "upper", ci.upper),
        ])
    for effect in result.effect_sizes:
        rows.append(_row("Effect size", effect.name, effect.value, effect.interpretation))
    for name, size in result.sample_sizes.items():
        rows.append(_row("Sample size", str(name), size))
    rows.extend(_assumption_rows(assumptions))
    for note in result.notes:
        rows.append(_row("Note", "note", note))
    return pd.DataFrame(rows, columns=("section", "metric", "value", "detail"))


def anova_report(result, *, assumptions: Sequence[Any] = ()) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for term in result.terms:
        rows.append({
            "section": "ANOVA term",
            "term": term.term,
            "sum_squares": term.sum_squares,
            "df": term.degrees_of_freedom,
            "mean_square": term.mean_square,
            "statistic": term.f_statistic,
            "p_value": term.p_value,
            "reject_null": term.reject_null,
            "eta_squared": term.eta_squared,
            "partial_eta_squared": term.partial_eta_squared,
            "omega_squared": term.omega_squared,
            "detail": "",
        })
    for item in assumptions:
        if isinstance(item, Exception):
            rows.append({"section": "Assumption", "term": type(item).__name__, "detail": str(item)})
        else:
            rows.append({
                "section": "Assumption", "term": item.method,
                "statistic": item.statistic, "p_value": item.p_value,
                "reject_null": item.reject_null,
                "detail": "Assumption may be violated" if item.reject_null else "No evidence of violation",
            })
    return pd.DataFrame(rows).reindex(columns=(
        "section", "term", "sum_squares", "df", "mean_square", "statistic",
        "p_value", "reject_null", "eta_squared", "partial_eta_squared",
        "omega_squared", "detail",
    ))


def regression_report(result) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for coefficient in result.coefficients:
        rows.append({
            "section": "Coefficient", "term": coefficient.term,
            "estimate": coefficient.estimate, "standard_error": coefficient.standard_error,
            "statistic": coefficient.t_statistic, "p_value": coefficient.p_value,
            "ci_lower": coefficient.confidence_interval.lower,
            "ci_upper": coefficient.confidence_interval.upper,
            "value": np.nan,
        })
    metrics = {
        "n_observations": result.n_observations,
        "r_squared": result.r_squared,
        "adjusted_r_squared": result.adjusted_r_squared,
        "f_statistic": result.f_statistic,
        "f_p_value": result.f_p_value,
        "rmse": result.rmse,
        "aic": result.aic,
        "bic": result.bic,
    }
    diagnostics = asdict(result.diagnostics) if is_dataclass(result.diagnostics) else {}
    for name, value in {**metrics, **diagnostics}.items():
        if isinstance(value, Mapping):
            for sub_name, sub_value in value.items():
                rows.append({"section": "Diagnostic", "term": f"{name}.{sub_name}", "value": sub_value})
        else:
            rows.append({"section": "Model" if name in metrics else "Diagnostic", "term": name, "value": value})
    return pd.DataFrame(rows).reindex(columns=(
        "section", "term", "estimate", "standard_error", "statistic", "p_value",
        "ci_lower", "ci_upper", "value",
    ))


def global_fit_report(result) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    # Convergence status first, so a non-converged optimiser is never silently
    # reported as a valid fit (the report is what UI/batch/AI persist and read).
    rows.append({
        "section": "Convergence", "dataset": "All", "metric": "success",
        "value": bool(result.success),
    })
    rows.append({
        "section": "Convergence", "dataset": "All", "metric": "message",
        "detail": str(result.message),
    })
    rows.append({
        "section": "Convergence", "dataset": "All", "metric": "confidence_level",
        "value": float(result.confidence_level),
    })
    for name, value in result.parameters.items():
        interval = result.ci95.get(name, (np.nan, np.nan))
        rows.append({
            "section": "Parameter", "dataset": "Global" if "." not in name else name.split(".", 1)[0],
            "metric": name, "value": value, "standard_error": result.stderr.get(name),
            "ci_lower": interval[0], "ci_upper": interval[1],
        })
    for name, value in asdict(result.metrics).items():
        rows.append({"section": "Overall fit", "dataset": "All", "metric": name, "value": value})
    for dataset in result.datasets:
        for name, value in asdict(dataset.metrics).items():
            rows.append({"section": "Dataset fit", "dataset": dataset.name, "metric": name, "value": value})
    return pd.DataFrame(rows).reindex(columns=(
        "section", "dataset", "metric", "value", "standard_error",
        "ci_lower", "ci_upper", "detail",
    ))


def global_fit_curves(result) -> pd.DataFrame:
    # Column names carry the real confidence level so a 90%/99% band is never
    # mislabelled as 95% (the dataclass fields are named ci95_* for historical
    # reasons but hold whatever level the fit was run at).
    tag = _ci_column_tag(getattr(result, "confidence_level", 0.95))
    frames = []
    for dataset in result.datasets:
        frames.append(pd.DataFrame({
            "dataset": dataset.name,
            "x": dataset.x,
            "observed": dataset.y,
            "fitted": dataset.fitted,
            "residual": dataset.residuals,
            f"ci_{tag}_lower": dataset.ci95_lower if dataset.ci95_lower is not None else np.nan,
            f"ci_{tag}_upper": dataset.ci95_upper if dataset.ci95_upper is not None else np.nan,
        }))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def peak_fit_curves(result) -> pd.DataFrame:
    tag = _ci_column_tag(getattr(result, "confidence_level", 0.95))
    return pd.DataFrame({
        "x": result.x,
        "observed": result.y,
        "baseline": result.baseline,
        "baseline_corrected": result.corrected,
        "peak_component": result.peak_component,
        "fitted": result.fitted,
        "residual": result.residuals,
        f"ci_{tag}_lower": result.ci95_lower if result.ci95_lower is not None else np.nan,
        f"ci_{tag}_upper": result.ci95_upper if result.ci95_upper is not None else np.nan,
    })


def _ci_column_tag(confidence: float) -> str:
    """Return a compact percentage tag (e.g. ``95``, ``97p5``) for CI columns."""
    percent = float(confidence) * 100.0
    if abs(percent - round(percent)) < 1e-9:
        return str(int(round(percent)))
    return f"{percent:.1f}".replace(".", "p")


def recipe_executor(operation: str):
    """Create an executor with the recipe engine's stable three-argument ABI."""
    def execute(inputs, params, _context=None):
        frame = _input_dataframe(inputs)
        if operation in STATISTICAL_OPERATIONS:
            return execute_statistical_operation(frame, operation, params)
        if operation == "global_fit":
            result = execute_global_fit(frame, params)
            return {
                "result": global_fit_report(result),
                "curves": global_fit_curves(result),
            }
        if operation == "peak_analysis":
            result = execute_peak_analysis(frame, params)
            return {
                "result": result.to_frame(),
                "curves": peak_fit_curves(result),
            }
        raise ScientificOperationError(f"Unknown recipe operation: {operation}")
    execute.__name__ = f"execute_{operation}"
    return execute


def register_scientific_operations(registry) -> None:
    """Register all sale-facing scientific operations with a recipe registry."""
    operations = [*STATISTICAL_OPERATIONS, "global_fit", "peak_analysis"]
    for operation in operations:
        registry.register(
            operation,
            recipe_executor(operation),
            schema=_operation_schema(operation),
            validator=lambda parameters, op=operation: _operation_validator(op, parameters),
            version="1",
        )


def _operation_schema(operation: str) -> dict[str, Any]:
    text = {"type": "string", "minLength": 1}
    number = {"type": "number"}
    optional_number = {"type": ["number", "null"]}
    properties: dict[str, Any] = {
        "alpha": {"type": "number", "exclusiveMinimum": 0.0, "exclusiveMaximum": 1.0},
        "confidence_level": {"type": "number", "exclusiveMinimum": 0.0, "exclusiveMaximum": 1.0},
        "confidence": {"type": "number", "exclusiveMinimum": 0.0, "exclusiveMaximum": 1.0},
        "alternative": {"type": "string", "enum": ["two-sided", "less", "greater"]},
    }
    required: list[str] = []
    if operation == "one_sample_t_test":
        properties.update(sample=text, popmean=number)
        required = ["sample"]
    elif operation in {
        "independent_t_test", "paired_t_test", "mann_whitney_test",
        "wilcoxon_signed_rank_test",
    }:
        properties.update(first=text, second=text, equal_var={"type": "boolean"})
        required = ["first", "second"]
    elif operation in {"one_way_anova", "kruskal_wallis_test"}:
        properties.update(
            group_columns={"type": "array", "items": text, "minItems": 2},
            dependent=text,
            group=text,
        )
    elif operation == "two_way_anova":
        properties.update(
            dependent=text, factor_a=text, factor_b=text,
            interaction={"type": "boolean"}, ss_type={"type": "integer", "enum": [2, 3]},
        )
        required = ["dependent", "factor_a", "factor_b"]
    elif operation == "multiple_linear_regression":
        properties.update(
            response=text,
            predictors={"type": "array", "items": text, "minItems": 1},
            add_intercept={"type": "boolean"},
        )
        required = ["response", "predictors"]
    elif operation == "adjust_p_values":
        properties.update(
            p_column=text,
            method={"type": "string", "enum": ["holm", "bonferroni", "sidak", "fdr_bh", "fdr_by", "none"]},
        )
        required = ["p_column"]
    elif operation == "global_fit":
        properties.update(
            x=text,
            ys={"type": "array", "items": text, "minItems": 2},
            sigma={"type": ["string", "null"]},
            model={"type": "string", "enum": [
                "gaussian", "lorentzian", "voigt", "exponential", "exponential_decay",
            ]},
            shared={"type": "array", "items": text},
            loss={"type": "string", "enum": ["linear", "soft_l1", "huber", "cauchy", "arctan"]},
            absolute_sigma={"type": "boolean"},
        )
        required = ["x", "ys", "model"]
    elif operation == "peak_analysis":
        properties.update(
            x=text, y=text, sigma={"type": ["string", "null"]},
            model={"type": "string", "enum": ["gaussian", "lorentzian", "voigt"]},
            baseline={"type": "string", "enum": ["none", "constant", "linear", "als"]},
            direction={"type": "string", "enum": ["positive", "negative", "both"]},
            prominence=optional_number, height=optional_number, distance=optional_number,
            width=optional_number, max_peaks={"type": "integer", "minimum": 1},
            absolute_sigma={"type": "boolean"},
            constant_quantile={"type": "number", "minimum": 0.0, "maximum": 1.0},
            als_lambda={"type": "number", "exclusiveMinimum": 0.0},
            als_p={"type": "number", "exclusiveMinimum": 0.0, "exclusiveMaximum": 1.0},
            als_iterations={"type": "integer", "minimum": 1},
        )
        required = ["x", "y", "model", "baseline"]
    return {
        "type": "object", "required": required,
        "properties": properties, "additionalProperties": True,
    }


def _operation_validator(operation: str, parameters: Mapping[str, Any]):
    if operation in {"one_way_anova", "kruskal_wallis_test"}:
        wide = parameters.get("group_columns")
        long = parameters.get("dependent") and parameters.get("group")
        if not ((isinstance(wide, list) and len(wide) >= 2) or long):
            return "Use either two or more group_columns, or dependent + group long-format mappings."
    pairs = {
        "independent_t_test": ("first", "second"),
        "paired_t_test": ("first", "second"),
        "mann_whitney_test": ("first", "second"),
        "wilcoxon_signed_rank_test": ("first", "second"),
        "peak_analysis": ("x", "y"),
    }
    if operation in pairs:
        first, second = (parameters.get(key) for key in pairs[operation])
        if first == second:
            return "Mapped columns must be different."
    if operation == "global_fit" and parameters.get("x") in (parameters.get("ys") or []):
        return "The X column cannot also be a Y dataset."
    if operation == "two_way_anova":
        values = [parameters.get("dependent"), parameters.get("factor_a"), parameters.get("factor_b")]
        if len(set(values)) != 3:
            return "Dependent, Factor A, and Factor B must be different columns."
    if operation == "multiple_linear_regression" and parameters.get("response") in (
        parameters.get("predictors") or []
    ):
        return "The response cannot also be a predictor."
    return None


def _input_dataframe(inputs) -> pd.DataFrame:
    if isinstance(inputs, pd.DataFrame):
        return inputs
    if isinstance(inputs, Mapping):
        for key in ("data", "source", "result"):
            value = inputs.get(key)
            if isinstance(value, pd.DataFrame):
                return value
        for value in inputs.values():
            if isinstance(value, pd.DataFrame):
                return value
    if isinstance(inputs, Sequence) and not isinstance(inputs, (str, bytes)):
        for value in inputs:
            if isinstance(value, pd.DataFrame):
                return value
    raise ScientificOperationError("The operation requires one DataFrame input.")


def _require_frame(value) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame) or value.empty:
        raise ScientificOperationError("Select a non-empty data Book first.")
    return value


def _column(frame: pd.DataFrame, params: Mapping[str, Any], key: str) -> str:
    name = str(params.get(key, ""))
    if not name or name not in frame.columns:
        raise ScientificOperationError(f"Column mapping '{key}' is missing or no longer exists: {name!r}")
    return name


def _columns(frame: pd.DataFrame, params: Mapping[str, Any], key: str, *, minimum: int) -> list[str]:
    raw = params.get(key) or []
    names = [str(raw)] if isinstance(raw, str) else [str(value) for value in raw]
    if len(names) < minimum:
        raise ScientificOperationError(f"Select at least {minimum} column(s) for '{key}'.")
    missing = [name for name in names if name not in frame.columns]
    if missing:
        raise ScientificOperationError(f"Mapped columns no longer exist: {', '.join(missing)}")
    if len(set(names)) != len(names):
        raise ScientificOperationError(f"Column mapping '{key}' contains duplicates.")
    return names


def _numeric(frame: pd.DataFrame, name: str, *, keep_nan: bool = False) -> np.ndarray:
    if name not in frame.columns:
        raise ScientificOperationError(f"Column no longer exists: {name}")
    values = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float)
    return values if keep_nan else values[np.isfinite(values)]


def _distinct(first: str, second: str) -> None:
    if first == second:
        raise ScientificOperationError("Choose two different columns.")


def _groups(frame: pd.DataFrame, params: Mapping[str, Any]) -> tuple[list[np.ndarray], list[str]]:
    columns = params.get("group_columns")
    if columns:
        names = _columns(frame, params, "group_columns", minimum=2)
        return [_numeric(frame, name) for name in names], names
    dependent = _column(frame, params, "dependent")
    grouping = _column(frame, params, "group")
    _distinct(dependent, grouping)
    compact = pd.DataFrame({
        "value": pd.to_numeric(frame[dependent], errors="coerce"),
        "group": frame[grouping],
    }).dropna()
    grouped = list(compact.groupby("group", sort=False, observed=True))
    if len(grouped) < 2:
        raise ScientificOperationError("The grouping column must contain at least two non-empty groups.")
    names = [str(name) for name, _ in grouped]
    return [part["value"].to_numpy(dtype=float) for _, part in grouped], names


def _safe_assumption(label, function, *args, **kwargs):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            result = function(*args, **kwargs)
        if not np.isfinite(float(result.statistic)) or not np.isfinite(float(result.p_value)):
            raise ValueError("test is undefined for constant or degenerate samples")
        return _AssumptionResult(
            method=label,
            statistic=float(result.statistic),
            p_value=float(result.p_value),
            reject_null=bool(result.reject_null),
        )
    except Exception as exc:
        return ScientificOperationError(f"{label}: {exc}")


def _assumption_rows(results: Sequence[Any]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        if isinstance(result, Exception):
            rows.append(_row("Assumption", type(result).__name__, np.nan, str(result)))
        else:
            detail = "Assumption may be violated" if result.reject_null else "No evidence of violation"
            rows.extend([
                _row("Assumption", f"{result.method}.statistic", result.statistic, detail),
                _row("Assumption", f"{result.method}.p_value", result.p_value, detail),
            ])
    return rows


def _row(section, metric, value, detail="") -> dict[str, Any]:
    return {"section": section, "metric": metric, "value": value, "detail": detail}


__all__ = [
    "STATISTICAL_OPERATIONS",
    "ScientificOperationError",
    "anova_report",
    "execute_global_fit",
    "execute_peak_analysis",
    "execute_statistical_operation",
    "global_fit_curves",
    "global_fit_report",
    "hypothesis_report",
    "peak_fit_curves",
    "recipe_executor",
    "register_scientific_operations",
    "regression_report",
]
