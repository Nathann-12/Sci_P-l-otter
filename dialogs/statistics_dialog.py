"""Beginner-safe, single-screen setup for SciPlotter statistical analyses.

The dialog is intentionally a thin mapping layer over
``analysis.scientific_operations.execute_statistical_operation``.  Its
``values()`` method returns exactly ``{"operation": ..., "params": ...}`` and
never performs any numerical work.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from analysis.scientific_operations import STATISTICAL_OPERATIONS


OPERATION_LABELS = {
    "one_sample_t_test": "One-sample t-test",
    "independent_t_test": "Independent-samples t-test",
    "paired_t_test": "Paired-samples t-test",
    "one_way_anova": "One-way ANOVA",
    "two_way_anova": "Two-way ANOVA",
    "mann_whitney_test": "Mann-Whitney U test",
    "wilcoxon_signed_rank_test": "Wilcoxon signed-rank test",
    "kruskal_wallis_test": "Kruskal-Wallis test",
    "multiple_linear_regression": "Multiple linear regression",
    "adjust_p_values": "Adjust multiple p-values",
}


OPERATION_HELP = {
    "one_sample_t_test": (
        "Compare the mean of one numeric column with a reference value."
    ),
    "independent_t_test": (
        "Compare two independent numeric samples. Welch's unequal-variance "
        "test is the safer default."
    ),
    "paired_t_test": (
        "Compare matched measurements stored in two columns, such as before "
        "and after values from the same subjects."
    ),
    "one_way_anova": (
        "Compare the means of three or more groups. Use Wide data when each "
        "group has its own column, or Long data when one column stores values "
        "and another stores group labels."
    ),
    "two_way_anova": (
        "Test two categorical factors and, optionally, whether their effects "
        "interact. Data must be in long format. Use categorical columns with "
        "a modest number of levels—not measurements, timestamps, or row IDs."
    ),
    "mann_whitney_test": (
        "Compare two independent samples by ranks when a t-test is not suitable."
    ),
    "wilcoxon_signed_rank_test": (
        "Compare paired measurements by ranks when paired differences are not normal."
    ),
    "kruskal_wallis_test": (
        "Compare three or more independent groups by ranks. Wide and Long "
        "data layouts are supported."
    ),
    "multiple_linear_regression": (
        "Model one numeric response from one or more numeric predictors and "
        "produce coefficient and residual diagnostics."
    ),
    "adjust_p_values": (
        "Correct a numeric column of p-values for multiple comparisons while "
        "preserving the original row order."
    ),
}


_T_TEST_OPERATIONS = {
    "one_sample_t_test",
    "independent_t_test",
    "paired_t_test",
}
_DIRECTIONAL_OPERATIONS = {
    *_T_TEST_OPERATIONS,
    "mann_whitney_test",
    "wilcoxon_signed_rank_test",
}
_TWO_COLUMN_OPERATIONS = {
    "independent_t_test",
    "paired_t_test",
    "mann_whitney_test",
    "wilcoxon_signed_rank_test",
}
_GROUPED_OPERATIONS = {"one_way_anova", "kruskal_wallis_test"}


def _unique_strings(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = str(value)
        if name not in seen:
            output.append(name)
            seen.add(name)
    return output


class StatisticsDialog(QDialog):
    """Configure one operation from ``STATISTICAL_OPERATIONS``.

    Parameters
    ----------
    all_columns:
        Every column in the active Book; categorical factor selectors use this
        list.
    numeric_columns:
        Columns already identified as numeric; response/sample selectors are
        restricted to this list to prevent avoidable runtime errors.
    default_operation:
        Optional stable operation key from ``STATISTICAL_OPERATIONS``.
    """

    def __init__(
        self,
        all_columns: Iterable[str],
        numeric_columns: Iterable[str],
        default_operation: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.all_columns = _unique_strings(all_columns)
        allowed = set(self.all_columns)
        self.numeric_columns = [
            name for name in _unique_strings(numeric_columns) if name in allowed
        ]
        if default_operation is not None and default_operation not in STATISTICAL_OPERATIONS:
            raise ValueError(f"Unknown statistical operation: {default_operation}")

        self.setWindowTitle("Statistical Analysis")
        self.setModal(True)
        self.resize(640, 610)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        introduction = QLabel(
            "Choose an analysis, map the worksheet columns, then review the "
            "test options. SciPlotter will create a separate result Book and "
            "leave the source data unchanged."
        )
        introduction.setWordWrap(True)
        outer.addWidget(introduction)

        operation_box = QGroupBox("1. Choose an analysis")
        operation_layout = QFormLayout(operation_box)
        self.operation_combo = QComboBox()
        for operation in STATISTICAL_OPERATIONS:
            self.operation_combo.addItem(OPERATION_LABELS[operation], operation)
        operation_layout.addRow("Analysis:", self.operation_combo)
        self.operation_help = QLabel()
        self.operation_help.setWordWrap(True)
        self.operation_help.setStyleSheet("color:#aab0b6")
        operation_layout.addRow("", self.operation_help)
        outer.addWidget(operation_box)

        mapping_box = QGroupBox("2. Map worksheet columns")
        mapping_layout = QVBoxLayout(mapping_box)
        self.mapping_stack = QStackedWidget()
        mapping_layout.addWidget(self.mapping_stack)
        outer.addWidget(mapping_box, 1)

        self._pages: dict[str, QWidget] = {}
        self._build_one_sample_page()
        self._build_two_column_page()
        self._build_grouped_page()
        self._build_two_way_page()
        self._build_regression_page()
        self._build_adjustment_page()

        options_box = QGroupBox("3. Test options")
        self.options_form = QFormLayout(options_box)
        self.alpha_spin = self._percentage_spin(5.0)
        self.options_form.addRow("Significance level (alpha):", self.alpha_spin)
        self.confidence_spin = self._percentage_spin(95.0)
        self._confidence_label = QLabel("Confidence level:")
        self.options_form.addRow(self._confidence_label, self.confidence_spin)
        self.alternative_combo = QComboBox()
        self.alternative_combo.addItem("Two-sided: any difference", "two-sided")
        self.alternative_combo.addItem("Greater: first/sample is higher", "greater")
        self.alternative_combo.addItem("Less: first/sample is lower", "less")
        self._alternative_label = QLabel("Alternative hypothesis:")
        self.options_form.addRow(self._alternative_label, self.alternative_combo)
        outer.addWidget(options_box)

        self.validation_label = QLabel("")
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet("color:#e29b52")
        outer.addWidget(self.validation_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Run Analysis")
        self.buttons.accepted.connect(self._accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self._connect_signals()
        self._set_beginner_defaults()
        if default_operation is not None:
            self.operation_combo.setCurrentIndex(
                self.operation_combo.findData(default_operation)
            )
        self._operation_changed()

    # ------------------------------------------------------------------ pages
    @staticmethod
    def _percentage_spin(default: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.01, 99.99)
        spin.setDecimals(2)
        spin.setSingleStep(0.5)
        spin.setSuffix(" %")
        spin.setValue(default)
        return spin

    @staticmethod
    def _combo(columns: Iterable[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(list(columns))
        return combo

    @staticmethod
    def _multi_column_list(columns: Iterable[str], minimum_height: int = 95) -> QListWidget:
        widget = QListWidget()
        widget.addItems(list(columns))
        widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        widget.setMinimumHeight(minimum_height)
        return widget

    def _add_page(self, key: str, page: QWidget) -> None:
        self._pages[key] = page
        self.mapping_stack.addWidget(page)

    def _build_one_sample_page(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.sample_combo = self._combo(self.numeric_columns)
        form.addRow("Numeric sample:", self.sample_combo)
        self.popmean_spin = QDoubleSpinBox()
        self.popmean_spin.setRange(-1e15, 1e15)
        self.popmean_spin.setDecimals(8)
        self.popmean_spin.setValue(0.0)
        form.addRow("Reference mean:", self.popmean_spin)
        self._add_page("one_sample", page)

    def _build_two_column_page(self) -> None:
        page = QWidget()
        self.two_column_form = QFormLayout(page)
        self.first_combo = self._combo(self.numeric_columns)
        self.second_combo = self._combo(self.numeric_columns)
        self._first_label = QLabel("First numeric column:")
        self._second_label = QLabel("Second numeric column:")
        self.two_column_form.addRow(self._first_label, self.first_combo)
        self.two_column_form.addRow(self._second_label, self.second_combo)
        self.equal_var_check = QCheckBox(
            "Assume equal variances (pooled t-test); leave clear for Welch's test"
        )
        self._equal_var_label = QLabel("Variance model:")
        self.two_column_form.addRow(self._equal_var_label, self.equal_var_check)
        self._add_page("two_column", page)

    def _build_grouped_page(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.group_mode_combo = QComboBox()
        self.group_mode_combo.addItem("Wide: each group is a separate numeric column", "wide")
        self.group_mode_combo.addItem("Long: one value column plus one group-label column", "long")
        form.addRow("Data layout:", self.group_mode_combo)
        self.group_columns_list = self._multi_column_list(self.numeric_columns, 115)
        self._group_columns_label = QLabel("Group columns:")
        form.addRow(self._group_columns_label, self.group_columns_list)
        self.group_dependent_combo = self._combo(self.numeric_columns)
        self._group_dependent_label = QLabel("Numeric values:")
        form.addRow(self._group_dependent_label, self.group_dependent_combo)
        self.group_combo = self._combo(self.all_columns)
        self._group_label = QLabel("Group labels:")
        form.addRow(self._group_label, self.group_combo)
        self._add_page("grouped", page)

    def _build_two_way_page(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.two_way_dependent_combo = self._combo(self.numeric_columns)
        self.factor_a_combo = self._combo(self.all_columns)
        self.factor_b_combo = self._combo(self.all_columns)
        form.addRow("Numeric response:", self.two_way_dependent_combo)
        form.addRow("Factor A:", self.factor_a_combo)
        form.addRow("Factor B:", self.factor_b_combo)
        self.interaction_check = QCheckBox("Test whether Factor A changes the effect of Factor B")
        self.interaction_check.setChecked(False)
        form.addRow("Interaction:", self.interaction_check)
        self.two_way_safety_help = QLabel(
            "Interaction is off by default. Turn it on only when every Factor A × "
            "Factor B combination has data and repeated observations. Continuous "
            "or ID-like factors can create an unsafe model and will be rejected."
        )
        self.two_way_safety_help.setWordWrap(True)
        self.two_way_safety_help.setStyleSheet("color:#aab0b6")
        form.addRow("", self.two_way_safety_help)
        self.ss_type_combo = QComboBox()
        self.ss_type_combo.addItem("Type II (recommended unless interaction interpretation requires Type III)", 2)
        self.ss_type_combo.addItem("Type III (effect-coded full-model tests)", 3)
        form.addRow("Sum of squares:", self.ss_type_combo)
        self._add_page("two_way", page)

    def _build_regression_page(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.response_combo = self._combo(self.numeric_columns)
        form.addRow("Numeric response:", self.response_combo)
        self.predictors_list = self._multi_column_list(self.numeric_columns, 115)
        form.addRow("Numeric predictors:", self.predictors_list)
        self.add_intercept_check = QCheckBox("Estimate an intercept (recommended)")
        self.add_intercept_check.setChecked(True)
        form.addRow("Model:", self.add_intercept_check)
        self._add_page("regression", page)

    def _build_adjustment_page(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.p_column_combo = self._combo(self.numeric_columns)
        form.addRow("P-value column:", self.p_column_combo)
        self.correction_method_combo = QComboBox()
        self.correction_method_combo.addItem("Holm (family-wise error, recommended)", "holm")
        self.correction_method_combo.addItem("Bonferroni (conservative)", "bonferroni")
        self.correction_method_combo.addItem("Sidak", "sidak")
        self.correction_method_combo.addItem("Benjamini-Hochberg FDR", "fdr_bh")
        self.correction_method_combo.addItem("Benjamini-Yekutieli FDR", "fdr_by")
        self.correction_method_combo.addItem("No correction", "none")
        form.addRow("Correction method:", self.correction_method_combo)
        self._add_page("adjust", page)

    # --------------------------------------------------------------- behaviour
    def _connect_signals(self) -> None:
        self.operation_combo.currentIndexChanged.connect(self._operation_changed)
        self.group_mode_combo.currentIndexChanged.connect(self._group_mode_changed)
        combos = (
            self.sample_combo,
            self.first_combo,
            self.second_combo,
            self.group_dependent_combo,
            self.group_combo,
            self.two_way_dependent_combo,
            self.factor_a_combo,
            self.factor_b_combo,
            self.response_combo,
            self.p_column_combo,
            self.correction_method_combo,
            self.alternative_combo,
            self.ss_type_combo,
        )
        for combo in combos:
            combo.currentIndexChanged.connect(self._refresh_validation)
        self.group_columns_list.itemSelectionChanged.connect(self._refresh_validation)
        self.predictors_list.itemSelectionChanged.connect(self._refresh_validation)
        self.equal_var_check.toggled.connect(self._refresh_validation)
        self.interaction_check.toggled.connect(self._refresh_validation)
        self.add_intercept_check.toggled.connect(self._refresh_validation)
        self.alpha_spin.valueChanged.connect(self._refresh_validation)
        self.confidence_spin.valueChanged.connect(self._refresh_validation)

    @staticmethod
    def _set_combo_to_first_distinct(
        combo: QComboBox,
        excluded: set[str],
        preferred: Iterable[str] = (),
    ) -> None:
        for name in preferred:
            index = combo.findText(str(name))
            if index >= 0 and combo.itemText(index) not in excluded:
                combo.setCurrentIndex(index)
                return
        for index in range(combo.count()):
            if combo.itemText(index) not in excluded:
                combo.setCurrentIndex(index)
                return

    def _set_beginner_defaults(self) -> None:
        if self.second_combo.count() > 1:
            self.second_combo.setCurrentIndex(1)
        for index in range(min(2, self.group_columns_list.count())):
            self.group_columns_list.item(index).setSelected(True)

        dependent = self.group_dependent_combo.currentText()
        self._set_combo_to_first_distinct(self.group_combo, {dependent})

        two_way_dependent = self.two_way_dependent_combo.currentText()
        plausible_factors = [
            name for name in self.all_columns if name not in set(self.numeric_columns)
        ]
        self._set_combo_to_first_distinct(
            self.factor_a_combo,
            {two_way_dependent},
            plausible_factors,
        )
        self._set_combo_to_first_distinct(
            self.factor_b_combo,
            {two_way_dependent, self.factor_a_combo.currentText()},
            plausible_factors,
        )

        response = self.response_combo.currentText()
        for index in range(self.predictors_list.count()):
            item = self.predictors_list.item(index)
            item.setSelected(item.text() != response)

    def _operation(self) -> str:
        return str(self.operation_combo.currentData() or "")

    def _page_for_operation(self, operation: str) -> QWidget:
        if operation == "one_sample_t_test":
            return self._pages["one_sample"]
        if operation in _TWO_COLUMN_OPERATIONS:
            return self._pages["two_column"]
        if operation in _GROUPED_OPERATIONS:
            return self._pages["grouped"]
        if operation == "two_way_anova":
            return self._pages["two_way"]
        if operation == "multiple_linear_regression":
            return self._pages["regression"]
        return self._pages["adjust"]

    def _operation_changed(self, *_args) -> None:
        operation = self._operation()
        self.operation_help.setText(OPERATION_HELP.get(operation, ""))
        self.mapping_stack.setCurrentWidget(self._page_for_operation(operation))

        is_independent = operation == "independent_t_test"
        self._equal_var_label.setVisible(is_independent)
        self.equal_var_check.setVisible(is_independent)
        paired = operation in {"paired_t_test", "wilcoxon_signed_rank_test"}
        self._first_label.setText("First paired measurement:" if paired else "First numeric sample:")
        self._second_label.setText("Second paired measurement:" if paired else "Second numeric sample:")

        show_confidence = operation in _T_TEST_OPERATIONS or operation == "multiple_linear_regression"
        self._confidence_label.setVisible(show_confidence)
        self.confidence_spin.setVisible(show_confidence)
        show_alternative = operation in _DIRECTIONAL_OPERATIONS
        self._alternative_label.setVisible(show_alternative)
        self.alternative_combo.setVisible(show_alternative)
        self._group_mode_changed()
        self._refresh_validation()

    def _group_mode_changed(self, *_args) -> None:
        wide = self.group_mode_combo.currentData() == "wide"
        self._group_columns_label.setVisible(wide)
        self.group_columns_list.setVisible(wide)
        self._group_dependent_label.setVisible(not wide)
        self.group_dependent_combo.setVisible(not wide)
        self._group_label.setVisible(not wide)
        self.group_combo.setVisible(not wide)
        self._refresh_validation()

    @staticmethod
    def _selected_texts(widget: QListWidget) -> list[str]:
        return [item.text() for item in widget.selectedItems()]

    # ------------------------------------------------------------ validation
    def validation_error(self) -> str:
        """Return a user-facing problem, or an empty string when ready."""

        operation = self._operation()
        if operation not in STATISTICAL_OPERATIONS:
            return "Choose a statistical analysis."
        if not self.numeric_columns:
            return "This Book has no numeric columns available for statistical analysis."

        if operation == "one_sample_t_test":
            if not self.sample_combo.currentText():
                return "Select a numeric sample column."
        elif operation in _TWO_COLUMN_OPERATIONS:
            first, second = self.first_combo.currentText(), self.second_combo.currentText()
            if not first or not second:
                return "Select two numeric columns."
            if first == second:
                return "Choose two different numeric columns."
        elif operation in _GROUPED_OPERATIONS:
            if self.group_mode_combo.currentData() == "wide":
                if len(self._selected_texts(self.group_columns_list)) < 2:
                    return "Select at least two numeric group columns."
            else:
                dependent = self.group_dependent_combo.currentText()
                group = self.group_combo.currentText()
                if not dependent or not group:
                    return "Select both a numeric value column and a group-label column."
                if dependent == group:
                    return "The numeric value and group-label columns must be different."
        elif operation == "two_way_anova":
            values = {
                self.two_way_dependent_combo.currentText(),
                self.factor_a_combo.currentText(),
                self.factor_b_combo.currentText(),
            }
            if "" in values:
                return "Select a response column and two factor columns."
            if len(values) != 3:
                return "The response, Factor A, and Factor B must be different columns."
        elif operation == "multiple_linear_regression":
            response = self.response_combo.currentText()
            predictors = self._selected_texts(self.predictors_list)
            if not response:
                return "Select a numeric response column."
            if not predictors:
                return "Select at least one numeric predictor."
            if response in predictors:
                return "The response cannot also be selected as a predictor."
        elif operation == "adjust_p_values" and not self.p_column_combo.currentText():
            return "Select the numeric column containing p-values."
        return ""

    def _refresh_validation(self, *_args) -> None:
        problem = self.validation_error()
        if problem:
            self.validation_label.setText(problem)
        else:
            self.validation_label.setText(
                f"Ready to run {OPERATION_LABELS.get(self._operation(), 'analysis')}."
            )
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not problem)

    def _accept_if_valid(self) -> None:
        self._refresh_validation()
        if not self.validation_error():
            self.accept()

    # ------------------------------------------------------------------ read
    def values(self) -> dict:
        """Return the adapter-ready operation and parameters.

        Programmatic callers receive the same validation guarantee as users
        pressing Run Analysis.  This prevents invalid recipes from being saved
        by code that bypasses the dialog button.
        """

        problem = self.validation_error()
        if problem:
            raise ValueError(problem)
        operation = self._operation()
        params: dict = {
            "alpha": self.alpha_spin.value() / 100.0,
            "confidence_level": self.confidence_spin.value() / 100.0,
            "alternative": self.alternative_combo.currentData(),
        }
        if operation == "one_sample_t_test":
            params.update(
                sample=self.sample_combo.currentText(),
                popmean=float(self.popmean_spin.value()),
            )
        elif operation in _TWO_COLUMN_OPERATIONS:
            params.update(
                first=self.first_combo.currentText(),
                second=self.second_combo.currentText(),
            )
            if operation == "independent_t_test":
                params["equal_var"] = self.equal_var_check.isChecked()
        elif operation in _GROUPED_OPERATIONS:
            if self.group_mode_combo.currentData() == "wide":
                params["group_columns"] = self._selected_texts(self.group_columns_list)
            else:
                params.update(
                    dependent=self.group_dependent_combo.currentText(),
                    group=self.group_combo.currentText(),
                )
        elif operation == "two_way_anova":
            params.update(
                dependent=self.two_way_dependent_combo.currentText(),
                factor_a=self.factor_a_combo.currentText(),
                factor_b=self.factor_b_combo.currentText(),
                interaction=self.interaction_check.isChecked(),
                ss_type=int(self.ss_type_combo.currentData()),
            )
        elif operation == "multiple_linear_regression":
            params.update(
                response=self.response_combo.currentText(),
                predictors=self._selected_texts(self.predictors_list),
                add_intercept=self.add_intercept_check.isChecked(),
            )
        elif operation == "adjust_p_values":
            params.update(
                p_column=self.p_column_combo.currentText(),
                method=self.correction_method_combo.currentData(),
            )
        return {"operation": operation, "params": params}


__all__ = ["StatisticsDialog", "OPERATION_LABELS", "OPERATION_HELP"]
