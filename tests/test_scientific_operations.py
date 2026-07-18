from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.scientific_operations import (
    ScientificOperationError,
    execute_global_fit,
    execute_peak_analysis,
    execute_statistical_operation,
    global_fit_curves,
    global_fit_report,
    peak_fit_curves,
    recipe_executor,
    register_scientific_operations,
)


def test_welch_adapter_includes_effect_size_and_assumption_checks():
    frame = pd.DataFrame({
        "control": [1.0, 2.0, 3.0, 2.5, 1.8, 2.2],
        "treated": [3.0, 4.0, 5.0, 4.5, 3.8, 4.2],
    })
    report = execute_statistical_operation(frame, "independent_t_test", {
        "first": "control", "second": "treated", "equal_var": False,
    })
    assert report.loc[report.metric == "p_value", "value"].iloc[0] < 0.05
    assert (report.section == "Effect size").any()
    assert (report.section == "Assumption").any()


def test_one_way_adapter_supports_wide_and_long_groups():
    wide = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    wide_report = execute_statistical_operation(
        wide, "one_way_anova", {"group_columns": ["a", "b", "c"]}
    )
    assert "ANOVA term" in wide_report.section.values

    long = pd.DataFrame({"value": [1, 2, 4, 5], "group": ["a", "a", "b", "b"]})
    long_report = execute_statistical_operation(
        long, "kruskal_wallis_test", {"dependent": "value", "group": "group"}
    )
    assert (long_report.metric == "p_value").any()


def test_regression_adapter_reports_coefficients_and_diagnostics():
    x = np.linspace(0, 4, 20)
    frame = pd.DataFrame({"x": x, "z": x**2, "y": 1 + 2*x - .2*x**2})
    report = execute_statistical_operation(frame, "multiple_linear_regression", {
        "response": "y", "predictors": ["x", "z"]
    })
    assert {"Coefficient", "Model", "Diagnostic"}.issubset(set(report.section))
    assert "r_squared" in report.term.values


def test_global_fit_adapter_returns_summary_and_curves():
    x = np.linspace(-4, 4, 120)
    frame = pd.DataFrame({
        "x": x,
        "run1": 1 + 3*np.exp(-.5*((x-.3)/.8)**2),
        "run2": 2 + 5*np.exp(-.5*((x-.3)/.8)**2),
    })
    result = execute_global_fit(frame, {
        "x": "x", "ys": ["run1", "run2"], "model": "gaussian",
        "shared": ["center", "sigma"],
    })
    assert result.success
    assert result.parameters["center"] == pytest.approx(.3, abs=1e-4)
    assert set(global_fit_report(result).section) >= {"Parameter", "Overall fit", "Dataset fit"}
    assert set(global_fit_curves(result).dataset) == {"run1", "run2"}


def test_peak_adapter_returns_complete_fit_curves():
    x = np.linspace(0, 10, 300)
    y = .1*x + 2*np.exp(-.5*((x-4)/.35)**2)
    result = execute_peak_analysis(pd.DataFrame({"x": x, "y": y}), {
        "x": "x", "y": "y", "baseline": "linear", "model": "gaussian",
        "prominence": .5,
    })
    assert result.peak_count == 1
    curves = peak_fit_curves(result)
    assert {"observed", "baseline", "fitted", "residual"}.issubset(curves.columns)


def test_global_fit_report_records_convergence_status():
    x = np.linspace(-4, 4, 120)
    frame = pd.DataFrame({
        "x": x,
        "run1": 1 + 3*np.exp(-.5*((x-.3)/.8)**2),
        "run2": 2 + 5*np.exp(-.5*((x-.3)/.8)**2),
    })
    result = execute_global_fit(frame, {
        "x": "x", "ys": ["run1", "run2"], "model": "gaussian",
        "shared": ["center", "sigma"],
    })
    report = global_fit_report(result)
    convergence = report[report.section == "Convergence"]
    success = convergence[convergence.metric == "success"]["value"].iloc[0]
    assert bool(success) is True


def test_ci_curve_columns_carry_the_actual_confidence_level():
    x = np.linspace(-4, 4, 120)
    frame = pd.DataFrame({
        "x": x,
        "run1": 1 + 3*np.exp(-.5*((x-.3)/.8)**2),
        "run2": 2 + 5*np.exp(-.5*((x-.3)/.8)**2),
    })
    result = execute_global_fit(frame, {
        "x": "x", "ys": ["run1", "run2"], "model": "gaussian",
        "shared": ["center", "sigma"], "confidence": 0.90,
    })
    curves = global_fit_curves(result)
    # A 90% band must not be mislabelled as 95%.
    assert "ci_90_lower" in curves.columns and "ci_90_upper" in curves.columns
    assert "ci95_lower" not in curves.columns


def test_adapter_rejects_stale_column_mapping():
    with pytest.raises(ScientificOperationError, match="no longer exists"):
        execute_statistical_operation(pd.DataFrame({"x": [1, 2]}), "one_sample_t_test", {
            "sample": "deleted"
        })


def test_fit_recipe_executors_expose_report_and_curve_outputs():
    x = np.linspace(0, 8, 200)
    frame = pd.DataFrame({"x": x, "y": np.exp(-.5*((x-3)/.3)**2)})
    output = recipe_executor("peak_analysis")(
        {"data": frame},
        {"x": "x", "y": "y", "model": "gaussian", "baseline": "none", "prominence": .2},
        None,
    )
    assert set(output) == {"result", "curves"}
    assert not output["result"].empty and not output["curves"].empty


def test_recipe_registry_rejects_invalid_or_ambiguous_mappings_before_execution():
    from core.analysis_recipe import OperationRegistry, ParameterValidationError

    registry = OperationRegistry()
    register_scientific_operations(registry)
    with pytest.raises(ParameterValidationError, match="required"):
        registry.validate("global_fit", {"x": "x", "model": "gaussian"})
    with pytest.raises(ParameterValidationError, match="different"):
        registry.validate("paired_t_test", {"first": "a", "second": "a"})
    with pytest.raises(ParameterValidationError, match="group_columns"):
        registry.validate("one_way_anova", {})
