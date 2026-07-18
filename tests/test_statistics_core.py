from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import analysis.statistics as statistics_module
from analysis.statistics import (
    kruskal_wallis_test,
    levene_test,
    mann_whitney_test,
    multiple_linear_regression,
    multiple_testing_correction,
    one_sample_t_test,
    one_way_anova,
    paired_t_test,
    pooled_t_test,
    shapiro_wilk_test,
    two_way_anova,
    welch_t_test,
    wilcoxon_signed_rank_test,
)


def _effects(result):
    return {effect.name: effect.value for effect in result.effect_sizes}


def _terms(result):
    return {term.term: term for term in result.terms}


def test_result_contract_is_strict_json_safe():
    result = one_sample_t_test([4.0, 4.0, 4.0], popmean=3.0)

    payload = result.to_dict()
    assert payload["method"] == "One-sample t-test"
    assert payload["reject_null"] is True
    assert payload["confidence_interval"]["level"] == 0.95
    # Infinite standardized effects are intentionally represented as JSON null.
    assert payload["effect_sizes"][0]["value"] is None
    assert json.loads(result.to_json(indent=None)) == payload


def test_degenerate_t_and_assumption_inputs_have_defined_results():
    on_null = one_sample_t_test([4.0, 4.0, 4.0], popmean=4.0)
    assert (on_null.statistic, on_null.p_value) == (0.0, 1.0)
    assert shapiro_wilk_test([2.0, 2.0, 2.0]).p_value == 1.0
    assert levene_test([1.0, 1.0], [5.0, 5.0]).p_value == 1.0


def test_nan_policy_propagates_without_trying_to_compute_partial_sample():
    result = one_sample_t_test([1.0, np.nan], nan_policy="propagate")

    assert np.isnan(result.statistic)
    assert np.isnan(result.p_value)
    assert result.reject_null is False
    assert result.to_dict()["p_value"] is None


def test_one_sample_t_matches_scipy_and_reports_ci_and_effects():
    sample = np.array([8.1, 7.7, 8.4, 8.0, 7.9, 8.3])
    expected = stats.ttest_1samp(sample, 7.5)

    result = one_sample_t_test(sample, 7.5)

    assert result.statistic == pytest.approx(expected.statistic)
    assert result.p_value == pytest.approx(expected.pvalue)
    assert result.degrees_of_freedom == 5
    assert result.confidence_interval.lower < result.estimate < result.confidence_interval.upper
    assert set(_effects(result)) == {"cohen_d", "hedges_g"}


def test_one_sided_t_test_has_directional_p_and_unbounded_ci():
    sample = [3.0, 4.0, 5.0, 6.0, 7.0]
    two_sided = one_sample_t_test(sample, 2.0)
    greater = one_sample_t_test(sample, 2.0, alternative="greater")

    assert greater.p_value == pytest.approx(two_sided.p_value / 2.0)
    assert greater.confidence_interval.upper is None
    assert greater.confidence_interval.lower < greater.estimate


def test_welch_and_pooled_tests_match_scipy_and_expose_distinct_df():
    first = np.array([1.0, 2.0, 3.0, 4.0, 12.0])
    second = np.array([0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5])

    welch = welch_t_test(first, second)
    pooled = pooled_t_test(first, second)

    expected_welch = stats.ttest_ind(first, second, equal_var=False)
    expected_pooled = stats.ttest_ind(first, second, equal_var=True)
    assert welch.statistic == pytest.approx(expected_welch.statistic)
    assert welch.p_value == pytest.approx(expected_welch.pvalue)
    assert pooled.statistic == pytest.approx(expected_pooled.statistic)
    assert pooled.p_value == pytest.approx(expected_pooled.pvalue)
    assert pooled.degrees_of_freedom == len(first) + len(second) - 2
    assert welch.degrees_of_freedom != pooled.degrees_of_freedom
    assert _effects(welch)["cohen_d"] == pytest.approx(_effects(pooled)["cohen_d"])


def test_paired_t_omits_missing_pairs_jointly():
    first = [10.0, 12.0, np.nan, 15.0, 18.0]
    second = [9.0, 11.0, 13.0, np.nan, 15.0]
    expected = stats.ttest_rel([10.0, 12.0, 18.0], [9.0, 11.0, 15.0])

    result = paired_t_test(first, second, nan_policy="omit")

    assert result.sample_sizes == {"pairs": 3}
    assert result.statistic == pytest.approx(expected.statistic)
    assert result.p_value == pytest.approx(expected.pvalue)
    assert result.estimate == pytest.approx(5.0 / 3.0)


def test_one_way_anova_matches_scipy_and_partitions_sum_of_squares():
    groups = {
        "control": [4.0, 5.0, 6.0, 5.0],
        "low": [7.0, 8.0, 7.5, 8.5],
        "high": [10.0, 11.0, 10.5, 12.0],
    }
    expected = stats.f_oneway(*groups.values())

    result = one_way_anova(groups)
    terms = _terms(result)

    assert terms["group"].f_statistic == pytest.approx(expected.statistic)
    assert terms["group"].p_value == pytest.approx(expected.pvalue)
    assert terms["group"].eta_squared > 0.8
    assert result.total_sum_squares == pytest.approx(
        terms["group"].sum_squares + terms["Residual"].sum_squares
    )


def test_two_way_anova_detects_main_effects_and_interaction():
    rows = []
    # Balanced 2x2 design with three replicates and a deliberately strong
    # non-additive effect in A2/B2.
    cell_means = {
        ("A1", "B1"): 1.0,
        ("A1", "B2"): 3.0,
        ("A2", "B1"): 5.0,
        ("A2", "B2"): 12.0,
    }
    for (a, b), mean in cell_means.items():
        for noise in (-0.2, 0.0, 0.2):
            rows.append({"response": mean + noise, "A": a, "B": b})
    frame = pd.DataFrame(rows)

    result = two_way_anova(frame, "response", "A", "B", ss_type=2)
    terms = _terms(result)

    assert set(terms) == {"A", "B", "A:B", "Residual"}
    assert all(terms[name].reject_null for name in ("A", "B", "A:B"))
    assert terms["A:B"].f_statistic > 100
    assert result.residual_degrees_of_freedom == 8
    assert result.factor_levels == {"A": ("A1", "A2"), "B": ("B1", "B2")}


def test_two_way_anova_rejects_rank_deficient_missing_cell_design():
    frame = pd.DataFrame(
        {
            "y": [1.0, 1.2, 2.0, 2.2, 3.0, 3.2],
            "A": ["a1", "a1", "a1", "a1", "a2", "a2"],
            "B": ["b1", "b1", "b2", "b2", "b1", "b1"],
        }
    )

    with pytest.raises(ValueError, match="rank deficient"):
        two_way_anova(frame, "y", "A", "B")


def test_two_way_anova_rejects_high_cardinality_before_matrix_allocation(monkeypatch):
    observations = 300
    frame = pd.DataFrame({
        "y": np.arange(observations, dtype=float),
        "subject_id": [f"S{index}" for index in range(observations)],
        "condition": np.where(np.arange(observations) % 2, "treated", "control"),
    })

    def allocation_must_not_start(*_args, **_kwargs):
        raise AssertionError("effect coding was reached before cardinality preflight")

    monkeypatch.setattr(statistics_module, "_effect_coding", allocation_must_not_start)
    with pytest.raises(ValueError, match="cardinality is too high.*safe maximum"):
        two_way_anova(frame, "y", "subject_id", "condition", interaction=True)


def test_two_way_anova_rejects_oversized_interaction_before_matrix_allocation(monkeypatch):
    observations = 100
    frame = pd.DataFrame({
        "y": np.arange(observations, dtype=float),
        "A": [f"A{index}" for index in range(observations)],
        "B": [f"B{index}" for index in range(observations)],
    })

    def allocation_must_not_start(*_args, **_kwargs):
        raise AssertionError("effect coding was reached before design-size preflight")

    monkeypatch.setattr(statistics_module, "_effect_coding", allocation_must_not_start)
    with pytest.raises(ValueError, match="design is too large to allocate safely"):
        two_way_anova(frame, "y", "A", "B", interaction=True)


def test_nonparametric_tests_match_scipy_and_report_effects():
    first = [7, 8, 9, 10, 11]
    second = [1, 2, 3, 4, 5]
    mann = mann_whitney_test(first, second, method="exact")
    expected_mann = stats.mannwhitneyu(first, second, method="exact")
    assert mann.statistic == expected_mann.statistic
    assert mann.p_value == expected_mann.pvalue
    assert _effects(mann)["rank_biserial_correlation"] == pytest.approx(1.0)
    assert mann.effect_sizes[0].interpretation == "large"

    kruskal = kruskal_wallis_test(first, second, [3, 4, 5, 6, 7])
    expected_kruskal = stats.kruskal(first, second, [3, 4, 5, 6, 7])
    assert kruskal.statistic == pytest.approx(expected_kruskal.statistic)
    assert kruskal.p_value == pytest.approx(expected_kruskal.pvalue)
    assert 0 <= _effects(kruskal)["epsilon_squared"] <= 1


def test_wilcoxon_handles_all_zero_differences_without_scipy_failure():
    result = wilcoxon_signed_rank_test([1, 2, 3], [1, 2, 3])

    assert result.statistic == 0
    assert result.p_value == 1
    assert result.reject_null is False
    assert _effects(result)["matched_pairs_rank_biserial"] == 0
    assert result.notes


def test_rank_biserial_effects_use_correlation_interpretation_thresholds():
    mann = mann_whitney_test([4, 5, 6, 7, 8], [1, 2, 3, 4, 9])
    wilcoxon = wilcoxon_signed_rank_test([-3, 1, 2, 4, 5], [0, 0, 0, 0, 0])

    assert _effects(mann)["rank_biserial_correlation"] == pytest.approx(0.56)
    assert mann.effect_sizes[0].interpretation == "large"
    assert _effects(wilcoxon)["matched_pairs_rank_biserial"] == pytest.approx(0.6)
    assert wilcoxon.effect_sizes[0].interpretation == "large"


def test_assumption_tests_match_scipy():
    sample = np.array([-1.2, -0.7, -0.1, 0.0, 0.2, 0.8, 1.1])
    shapiro = shapiro_wilk_test(sample)
    expected_shapiro = stats.shapiro(sample)
    assert shapiro.statistic == pytest.approx(expected_shapiro.statistic)
    assert shapiro.p_value == pytest.approx(expected_shapiro.pvalue)

    groups = ([1, 2, 3, 4], [2, 3, 4, 5], [10, 20, 30, 40])
    levene = levene_test(*groups, center="median")
    expected_levene = stats.levene(*groups, center="median")
    assert levene.statistic == pytest.approx(expected_levene.statistic)
    assert levene.p_value == pytest.approx(expected_levene.pvalue)


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("bonferroni", [0.03, 0.12, 0.09]),
        ("holm", [0.03, 0.06, 0.06]),
        ("fdr_bh", [0.03, 0.04, 0.04]),
    ],
)
def test_multiple_testing_corrections(method, expected):
    result = multiple_testing_correction([0.01, 0.04, 0.03], method=method)

    assert result.adjusted_p_values == pytest.approx(expected)
    assert result.reject_null == tuple(value <= 0.05 for value in expected)


def test_multiple_testing_omits_missing_without_inflating_family_size():
    result = multiple_testing_correction(
        [0.01, np.nan, 0.04], method="bonferroni", nan_policy="omit"
    )

    assert result.tested_count == 2
    assert result.adjusted_p_values == (0.02, None, 0.08)
    assert result.original_p_values == (0.01, None, 0.04)


def test_multiple_linear_regression_recovers_coefficients_and_diagnostics():
    rng = np.random.default_rng(42)
    x1 = np.linspace(-2.0, 2.0, 80)
    x2 = rng.normal(size=80)
    noise = rng.normal(scale=0.08, size=80)
    y = 1.5 + 2.25 * x1 - 0.75 * x2 + noise
    predictors = pd.DataFrame({"temperature": x1, "pressure": x2})

    result = multiple_linear_regression(predictors, y)
    coefficients = {item.term: item for item in result.coefficients}

    assert coefficients["Intercept"].estimate == pytest.approx(1.5, abs=0.03)
    assert coefficients["temperature"].estimate == pytest.approx(2.25, abs=0.03)
    assert coefficients["pressure"].estimate == pytest.approx(-0.75, abs=0.03)
    assert result.r_squared > 0.99
    assert result.f_p_value < 1e-20
    assert len(result.fitted_values) == 80
    assert len(result.cooks_distance) == 80
    assert sum(result.leverage) == pytest.approx(result.rank)
    assert set(result.diagnostics.variance_inflation_factors) == {
        "temperature",
        "pressure",
    }
    assert result.diagnostics.breusch_pagan_p_value is not None
    json.loads(result.to_json(indent=None))


def test_regression_alpha_controls_model_and_coefficient_decisions():
    predictors = pd.DataFrame({"x": np.arange(10, dtype=float)})
    response = [0, 1, 0, 1, 0, 1, 1, 1, 1, 2]

    at_five_percent = multiple_linear_regression(predictors, response, alpha=0.05)
    at_one_percent = multiple_linear_regression(predictors, response, alpha=0.01)
    slope_at_five = next(item for item in at_five_percent.coefficients if item.term == "x")
    slope_at_one = next(item for item in at_one_percent.coefficients if item.term == "x")

    assert at_five_percent.alpha == 0.05
    assert at_one_percent.alpha == 0.01
    assert at_five_percent.f_p_value == pytest.approx(0.02529324958545547)
    assert at_five_percent.reject_null is True
    assert at_one_percent.reject_null is False
    assert slope_at_five.reject_null is True
    assert slope_at_one.reject_null is False
    payload = at_five_percent.to_dict()
    assert payload["alpha"] == 0.05
    assert payload["reject_null"] is True
    assert next(item for item in payload["coefficients"] if item["term"] == "x")[
        "reject_null"
    ] is True


def test_regression_omits_rows_jointly_and_rejects_singular_design():
    predictors = pd.DataFrame(
        {"x1": [0.0, 1.0, 2.0, np.nan, 4.0], "x2": [1.0, 0.0, 1.0, 2.0, 3.0]}
    )
    response = [1.0, 2.0, 4.0, 8.0, 9.0]
    result = multiple_linear_regression(predictors, response, nan_policy="omit")
    assert result.n_observations == 4
    assert "Omitted 1 incomplete row(s)." in result.notes

    collinear = pd.DataFrame({"x": np.arange(8.0), "twice_x": np.arange(8.0) * 2})
    with pytest.raises(ValueError, match="rank deficient"):
        multiple_linear_regression(collinear, np.arange(8.0) + 1)


def test_validation_rejects_bad_alternatives_nan_and_small_samples():
    with pytest.raises(ValueError, match="alternative"):
        one_sample_t_test([1, 2, 3], alternative="up")
    with pytest.raises(ValueError, match="NaN"):
        paired_t_test([1.0, np.nan], [1.0, 2.0], nan_policy="raise")
    with pytest.raises(ValueError, match="at least 2"):
        one_sample_t_test([1.0])
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        multiple_testing_correction([0.1, 1.2])
