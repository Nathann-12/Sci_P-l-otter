from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from analysis.scientific_operations import STATISTICAL_OPERATIONS
from dialogs.statistics_dialog import OPERATION_LABELS, StatisticsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _select_operation(dialog: StatisticsDialog, operation: str) -> None:
    index = dialog.operation_combo.findData(operation)
    assert index >= 0
    dialog.operation_combo.setCurrentIndex(index)


def _select_only(widget, names):
    wanted = set(names)
    widget.clearSelection()
    for index in range(widget.count()):
        item = widget.item(index)
        item.setSelected(item.text() in wanted)


def test_operation_catalog_matches_adapter_exactly_and_honors_default(qapp):
    dialog = StatisticsDialog(
        ["value", "group", "second"],
        ["value", "second"],
        default_operation="kruskal_wallis_test",
    )

    keys = tuple(dialog.operation_combo.itemData(i) for i in range(dialog.operation_combo.count()))
    assert keys == STATISTICAL_OPERATIONS
    assert set(OPERATION_LABELS) == set(STATISTICAL_OPERATIONS)
    assert dialog.operation_combo.currentData() == "kruskal_wallis_test"
    with pytest.raises(ValueError, match="Unknown statistical operation"):
        StatisticsDialog(["x"], ["x"], default_operation="not_real")


def test_one_sample_mapping_uses_adapter_names_and_common_options(qapp):
    dialog = StatisticsDialog(["signal", "label"], ["signal"])
    dialog.popmean_spin.setValue(2.5)
    dialog.alpha_spin.setValue(1.0)
    dialog.confidence_spin.setValue(99.0)
    dialog.alternative_combo.setCurrentIndex(dialog.alternative_combo.findData("greater"))

    values = dialog.values()

    assert values == {
        "operation": "one_sample_t_test",
        "params": {
            "alpha": 0.01,
            "confidence_level": 0.99,
            "alternative": "greater",
            "sample": "signal",
            "popmean": 2.5,
        },
    }
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_two_column_operations_require_distinct_columns_and_only_independent_has_variance_flag(qapp):
    dialog = StatisticsDialog(["before", "after", "batch"], ["before", "after"])
    _select_operation(dialog, "independent_t_test")
    dialog.equal_var_check.setChecked(True)
    independent = dialog.values()
    assert independent["params"]["first"] == "before"
    assert independent["params"]["second"] == "after"
    assert independent["params"]["equal_var"] is True
    assert dialog.equal_var_check.isVisibleTo(dialog)

    _select_operation(dialog, "paired_t_test")
    paired = dialog.values()
    assert "equal_var" not in paired["params"]
    assert not dialog.equal_var_check.isVisibleTo(dialog)

    dialog.second_combo.setCurrentText(dialog.first_combo.currentText())
    assert "different" in dialog.validation_error().lower()
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    with pytest.raises(ValueError, match="different"):
        dialog.values()


def test_wide_and_long_group_mapping_are_mutually_exclusive(qapp):
    dialog = StatisticsDialog(
        ["control", "treatment", "response", "condition"],
        ["control", "treatment", "response"],
        default_operation="one_way_anova",
    )
    _select_only(dialog.group_columns_list, ["control", "treatment"])
    wide = dialog.values()
    assert wide["params"]["group_columns"] == ["control", "treatment"]
    assert "dependent" not in wide["params"]
    assert "group" not in wide["params"]

    _select_only(dialog.group_columns_list, ["control"])
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    with pytest.raises(ValueError, match="at least two"):
        dialog.values()

    dialog.group_mode_combo.setCurrentIndex(dialog.group_mode_combo.findData("long"))
    dialog.group_dependent_combo.setCurrentText("response")
    dialog.group_combo.setCurrentText("condition")
    long_values = dialog.values()
    assert long_values["params"]["dependent"] == "response"
    assert long_values["params"]["group"] == "condition"
    assert "group_columns" not in long_values["params"]
    assert dialog.group_dependent_combo.isVisibleTo(dialog)
    assert not dialog.group_columns_list.isVisibleTo(dialog)


def test_kruskal_uses_the_same_group_layout_contract(qapp):
    dialog = StatisticsDialog(
        ["value", "category", "g1", "g2"],
        ["value", "g1", "g2"],
        default_operation="kruskal_wallis_test",
    )
    _select_only(dialog.group_columns_list, ["g1", "g2"])
    values = dialog.values()
    assert values["operation"] == "kruskal_wallis_test"
    assert values["params"]["group_columns"] == ["g1", "g2"]


def test_two_way_anova_maps_long_format_and_requires_three_distinct_columns(qapp):
    dialog = StatisticsDialog(
        ["response", "factor A", "factor B", "other"],
        ["response", "other"],
        default_operation="two_way_anova",
    )
    dialog.two_way_dependent_combo.setCurrentText("response")
    dialog.factor_a_combo.setCurrentText("factor A")
    dialog.factor_b_combo.setCurrentText("factor B")
    dialog.interaction_check.setChecked(False)
    dialog.ss_type_combo.setCurrentIndex(dialog.ss_type_combo.findData(3))

    values = dialog.values()

    assert values["params"] | {} == {
        "alpha": 0.05,
        "confidence_level": 0.95,
        "alternative": "two-sided",
        "dependent": "response",
        "factor_a": "factor A",
        "factor_b": "factor B",
        "interaction": False,
        "ss_type": 3,
    }
    dialog.factor_b_combo.setCurrentText("factor A")
    assert "must be different" in dialog.validation_error()


def test_two_way_anova_defaults_to_safer_categorical_factors_without_interaction(qapp):
    dialog = StatisticsDialog(
        ["outcome", "continuous_measure", "treatment", "site"],
        ["outcome", "continuous_measure"],
        default_operation="two_way_anova",
    )

    assert dialog.two_way_dependent_combo.currentText() == "outcome"
    assert dialog.factor_a_combo.currentText() == "treatment"
    assert dialog.factor_b_combo.currentText() == "site"
    assert dialog.interaction_check.isChecked() is False
    safety_text = dialog.two_way_safety_help.text().lower()
    assert "every factor a" in safety_text
    assert "continuous" in safety_text
    assert dialog.values()["params"]["interaction"] is False


def test_regression_requires_predictor_and_excludes_response(qapp):
    dialog = StatisticsDialog(
        ["outcome", "x1", "x2", "category"],
        ["outcome", "x1", "x2"],
        default_operation="multiple_linear_regression",
    )
    _select_only(dialog.predictors_list, ["x1", "x2"])
    values = dialog.values()
    assert values["params"]["response"] == "outcome"
    assert values["params"]["predictors"] == ["x1", "x2"]
    assert values["params"]["add_intercept"] is True

    _select_only(dialog.predictors_list, [])
    assert "at least one" in dialog.validation_error()
    _select_only(dialog.predictors_list, ["outcome"])
    assert "cannot also" in dialog.validation_error()


def test_adjust_p_values_maps_column_and_correction_method(qapp):
    dialog = StatisticsDialog(
        ["p", "effect", "label"],
        ["p", "effect"],
        default_operation="adjust_p_values",
    )
    dialog.p_column_combo.setCurrentText("p")
    dialog.correction_method_combo.setCurrentIndex(
        dialog.correction_method_combo.findData("fdr_bh")
    )

    values = dialog.values()

    assert values["operation"] == "adjust_p_values"
    assert values["params"]["p_column"] == "p"
    assert values["params"]["method"] == "fdr_bh"
    assert not dialog.alternative_combo.isVisibleTo(dialog)
    assert not dialog.confidence_spin.isVisibleTo(dialog)


def test_no_numeric_columns_disables_run_with_clear_message(qapp):
    dialog = StatisticsDialog(["sample id", "group"], [])

    assert "no numeric columns" in dialog.validation_error().lower()
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    with pytest.raises(ValueError, match="no numeric columns"):
        dialog.values()
