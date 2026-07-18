"""AI tools for the dependency-aware Scientific Suite.

These wrap the same pure adapters the GUI, recipes and batch runner use
(`analysis.scientific_operations`), so the local assistant runs statistics,
global fitting and peak analysis through one code path — no dialogs, no
duplicated numerical mapping.  Every handler is defensive: it resolves columns
from explicit arguments first, returns a short string for the model to read,
and turns errors into text instead of raising.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Reuse the window/data helpers already defined for the core app tools.
from ai.app_tools import _active_df, _numeric_columns, _open_result, _resolve_column_name


_STAT_TESTS = (
    "one_sample_t_test",
    "independent_t_test",
    "paired_t_test",
    "one_way_anova",
    "mann_whitney_test",
    "wilcoxon_signed_rank_test",
    "kruskal_wallis_test",
    "multiple_linear_regression",
)


def _resolve(df, value, fallback=None):
    """Return an existing column name for *value* or a numeric fallback."""
    if value is not None:
        resolved = _resolve_column_name(df, value)
        if resolved is not None:
            return resolved
    return fallback


def _extract_p_value(report) -> float | None:
    """Find the primary p-value in any of the report table shapes."""
    try:
        import numpy as np

        if "p_value" in report.columns:
            values = report["p_value"].dropna()
            return float(values.min()) if not values.empty else None
        # Long form: a metric/term column paired with a value column.
        for key in ("metric", "term"):
            if key in report.columns and "value" in report.columns:
                hit = report.loc[report[key] == "p_value", "value"].dropna()
                if not hit.empty:
                    return float(hit.iloc[0])
    except Exception:
        logger.debug("could not extract p-value from report", exc_info=True)
    return None


def _stat_params(test: str, df, args: Dict[str, Any]) -> Dict[str, Any]:
    numeric = _numeric_columns(df)
    columns = args.get("columns") if isinstance(args.get("columns"), list) else None
    params: Dict[str, Any] = {}
    if args.get("alpha") is not None:
        params["alpha"] = float(args["alpha"])

    first = columns[0] if columns else None
    second = columns[1] if columns and len(columns) > 1 else None

    if test == "one_sample_t_test":
        params["sample"] = _resolve(df, args.get("sample") or first, numeric[0] if numeric else None)
        if args.get("popmean") is not None:
            params["popmean"] = float(args["popmean"])
    elif test in {"independent_t_test", "paired_t_test", "mann_whitney_test", "wilcoxon_signed_rank_test"}:
        params["first"] = _resolve(df, args.get("first") or first, numeric[0] if numeric else None)
        params["second"] = _resolve(df, args.get("second") or second, numeric[1] if len(numeric) > 1 else None)
        if args.get("equal_var") is not None:
            params["equal_var"] = bool(args["equal_var"])
    elif test in {"one_way_anova", "kruskal_wallis_test"}:
        groups = columns or args.get("group_columns")
        if isinstance(groups, list) and len(groups) >= 2:
            params["group_columns"] = [_resolve(df, g, g) for g in groups]
        else:
            params["dependent"] = _resolve(df, args.get("dependent"))
            params["group"] = _resolve(df, args.get("group"))
    elif test == "multiple_linear_regression":
        response = args.get("response") or first
        predictors = args.get("predictors")
        if not isinstance(predictors, list):
            predictors = [c for c in (columns or numeric) if c != response][:] or numeric[1:]
        params["response"] = _resolve(df, response, numeric[0] if numeric else None)
        params["predictors"] = [_resolve(df, p, p) for p in predictors]
    return params


def _tool_run_statistics(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data. Open a Book first."
    test = str(args.get("test", "one_sample_t_test")).strip()
    if test not in _STAT_TESTS:
        return f"Unknown test '{test}'. Choose one of: {', '.join(_STAT_TESTS)}."
    try:
        from analysis.scientific_operations import execute_statistical_operation

        params = _stat_params(test, df, args)
        report = execute_statistical_operation(df, test, params)
        _open_result(window, f"Stats_{test}", report)
        p = _extract_p_value(report)
        alpha = float(params.get("alpha", 0.05))
        if p is None:
            return f"Ran {test}; result table opened as a Book."
        verdict = "significant" if p < alpha else "not significant"
        return (
            f"{test}: p = {p:.4g} ({verdict} at alpha {alpha:g}). "
            "Full report opened as a Book."
        )
    except Exception as exc:
        logger.debug("run_statistics tool failed", exc_info=True)
        return f"Could not run {test}: {exc}"


def _tool_global_fit(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data. Open a Book first."
    numeric = _numeric_columns(df)
    if len(numeric) < 3:
        return "Global fit needs an X column and at least two Y datasets."
    x_col = _resolve(df, args.get("x_column"), numeric[0])
    ys = args.get("y_columns")
    if isinstance(ys, list) and ys:
        y_cols = [_resolve(df, y, y) for y in ys]
    else:
        y_cols = [c for c in numeric if c != x_col]
    try:
        from analysis.scientific_operations import (
            execute_global_fit,
            global_fit_curves,
            global_fit_report,
        )

        params: Dict[str, Any] = {
            "x": x_col,
            "ys": y_cols,
            "model": str(args.get("model", "gaussian")),
        }
        if isinstance(args.get("shared"), list):
            params["shared"] = list(args["shared"])
        if args.get("confidence") is not None:
            params["confidence"] = float(args["confidence"])
        result = execute_global_fit(df, params)
        _open_result(window, f"GlobalFit_{params['model']}", global_fit_report(result))
        _open_result(window, f"GlobalFit_{params['model']}_curves", global_fit_curves(result))
        shared = ", ".join(
            f"{k}={result.parameters[k]:.4g}"
            for k in list(result.parameters)[:4]
        )
        status = "converged" if result.success else "did NOT converge"
        return (
            f"Global fit ({params['model']}) across {len(y_cols)} datasets {status}. "
            f"Parameters: {shared}. Report + curves opened as Books."
        )
    except Exception as exc:
        logger.debug("global_fit tool failed", exc_info=True)
        return f"Could not run global fit: {exc}"


def _tool_analyze_peaks(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data. Open a Book first."
    numeric = _numeric_columns(df)
    if len(numeric) < 2:
        return "Peak analysis needs an X and a Y numeric column."
    x_col = _resolve(df, args.get("x_column"), numeric[0])
    y_col = _resolve(df, args.get("y_column"), next((c for c in numeric if c != x_col), None))
    if x_col is None or y_col is None or x_col == y_col:
        return "Need two different numeric columns (x_column and y_column)."
    try:
        from analysis.scientific_operations import execute_peak_analysis, peak_fit_curves

        params: Dict[str, Any] = {
            "x": x_col,
            "y": y_col,
            "model": str(args.get("model", "gaussian")),
            "baseline": str(args.get("baseline", "linear")),
        }
        if args.get("prominence") is not None:
            params["prominence"] = float(args["prominence"])
        if args.get("confidence") is not None:
            params["confidence"] = float(args["confidence"])
        result = execute_peak_analysis(df, params)
        _open_result(window, f"Peaks_{y_col}", result.to_frame())
        _open_result(window, f"Peaks_{y_col}_curves", peak_fit_curves(result))
        if result.peak_count == 0:
            return f"No peaks detected in '{y_col}'. Try a lower prominence."
        status = "converged" if result.success else "did NOT converge"
        return (
            f"Fitted {result.peak_count} peak(s) in '{y_col}' ({params['model']}, {status}), "
            f"R^2 = {result.metrics.r_squared:.4g}. Table + curves opened as Books."
        )
    except Exception as exc:
        logger.debug("analyze_peaks tool failed", exc_info=True)
        return f"Could not analyze peaks: {exc}"


def _tool_list_analysis_recipes(window, _args: Dict[str, Any]) -> str:
    getter = getattr(window, "analysis_recipe_summaries", None)
    if not callable(getter):
        return "Analysis recipes are unavailable in this context."
    try:
        summaries: List[Dict[str, Any]] = list(getter() or [])
    except Exception as exc:
        logger.debug("list_analysis_recipes tool failed", exc_info=True)
        return f"Could not list recipes: {exc}"
    if not summaries:
        return "No analysis recipes yet. Run Statistics, Global Fit or Peak Analyzer to create one."
    lines = [
        f"{row.get('name', '?')} [{row.get('status', '?')}, {row.get('mode', '?')}]"
        for row in summaries[:12]
    ]
    return f"{len(summaries)} analysis recipe(s): " + "; ".join(lines)


def register_scientific_tools(registry, window) -> None:
    """Register the Scientific Suite capabilities with the AI tool registry."""
    registry.add(
        "run_statistics",
        "Run a hypothesis test / ANOVA / regression on the active Book and open the "
        "full report as a result Book. 'test' selects the analysis; 'columns' names "
        "the data columns (resolved to numeric columns when omitted).",
        {
            "test": {
                "type": "string",
                "description": "which statistical test to run",
                "required": True,
                "enum": list(_STAT_TESTS),
            },
            "columns": {"type": "array", "description": "column names used by the test", "required": False},
            "popmean": {"type": "number", "description": "one-sample t-test reference mean", "required": False},
            "equal_var": {"type": "boolean", "description": "assume equal variance (pooled t-test)", "required": False},
            "dependent": {"type": "string", "description": "long-form value column", "required": False},
            "group": {"type": "string", "description": "long-form group column", "required": False},
            "response": {"type": "string", "description": "regression response column", "required": False},
            "predictors": {"type": "array", "description": "regression predictor columns", "required": False},
            "alpha": {"type": "number", "description": "significance level (default 0.05)", "required": False},
        },
        lambda args: _tool_run_statistics(window, args),
    )
    registry.add(
        "global_fit",
        "Fit one model to several Y datasets at once (shared/local parameters) and open "
        "the parameter report + fit curves as Books. Reports whether the optimiser "
        "converged.",
        {
            "x_column": {"type": "string", "description": "shared X column", "required": False},
            "y_columns": {"type": "array", "description": "two or more Y dataset columns", "required": False},
            "model": {"type": "string", "description": "model name, e.g. gaussian", "required": False},
            "shared": {"type": "array", "description": "parameter names shared across datasets", "required": False},
            "confidence": {"type": "number", "description": "confidence level for CIs (default 0.95)", "required": False},
        },
        lambda args: _tool_global_fit(window, args),
    )
    registry.add(
        "analyze_peaks",
        "Baseline-correct and fit peaks (Gaussian/Lorentzian/Voigt) on the active Book, "
        "opening the per-peak metrics and fit curves as Books. Reports peak count, R^2 "
        "and convergence.",
        {
            "x_column": {"type": "string", "description": "X column", "required": False},
            "y_column": {"type": "string", "description": "Y signal column", "required": False},
            "model": {"type": "string", "description": "gaussian | lorentzian | voigt", "required": False},
            "baseline": {"type": "string", "description": "none | constant | linear | als", "required": False},
            "prominence": {"type": "number", "description": "minimum peak prominence", "required": False},
            "confidence": {"type": "number", "description": "confidence level for CIs (default 0.95)", "required": False},
        },
        lambda args: _tool_analyze_peaks(window, args),
    )
    registry.add(
        "list_analysis_recipes",
        "List the saved Analysis Recipes (name, status, recalculation mode) so the "
        "assistant knows which reusable analyses already exist.",
        {},
        lambda args: _tool_list_analysis_recipes(window, args),
    )
