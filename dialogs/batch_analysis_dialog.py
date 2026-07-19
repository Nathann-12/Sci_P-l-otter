"""Single-screen setup dialog for applying a saved recipe to many files."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)


DATA_FILTER = (
    "Data Files (*.csv *.tsv *.txt *.xlsx *.nc *.cdf *.json *.h5 *.hdf5 "
    "*.hdf *.mat *.xml);;All Files (*.*)"
)
REPORT_FILTER = (
    "Excel Workbook (*.xlsx);;PDF Report (*.pdf);;Word Report (*.docx);;"
    "PowerPoint (*.pptx);;HTML Report (*.html);;CSV Summary (*.csv);;JSON Manifest (*.json)"
)


class BatchAnalysisDialog(QDialog):
    def __init__(self, recipes: Iterable[Mapping], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Analysis")
        self.resize(700, 480)

        layout = QVBoxLayout(self)
        description = QLabel(
            "Apply one saved Analysis Recipe to every file. Each input is isolated: "
            "a bad file is reported without discarding successful results."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        self.recipe_combo = QComboBox()
        for recipe in recipes:
            self.recipe_combo.addItem(str(recipe.get("name", "Untitled Recipe")), recipe.get("id"))
        form.addRow("Recipe:", self.recipe_combo)
        layout.addLayout(form)

        layout.addWidget(QLabel("Input files (processed in this order):"))
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.file_list, 1)
        file_buttons = QHBoxLayout()
        add_button = QPushButton("Add files...")
        add_button.clicked.connect(self._browse_inputs)
        remove_button = QPushButton("Remove selected")
        remove_button.clicked.connect(self._remove_selected)
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.file_list.clear)
        for button in (add_button, remove_button, clear_button):
            file_buttons.addWidget(button)
        file_buttons.addStretch(1)
        layout.addLayout(file_buttons)

        report_row = QHBoxLayout()
        self.report_path = QLineEdit()
        self.report_path.setPlaceholderText("Summary report path (.xlsx recommended)")
        report_row.addWidget(self.report_path, 1)
        browse_report = QPushButton("Browse...")
        browse_report.clicked.connect(self._browse_report)
        report_row.addWidget(browse_report)
        form2 = QFormLayout()
        form2.addRow("Report:", report_row)
        layout.addLayout(form2)

        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet("color:#e29b52")
        layout.addWidget(self.validation_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Run Batch")
        self.buttons.accepted.connect(self._accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.file_list.model().rowsInserted.connect(self._refresh_validation)
        self.file_list.model().rowsRemoved.connect(self._refresh_validation)
        self.report_path.textChanged.connect(self._refresh_validation)
        self.recipe_combo.currentIndexChanged.connect(self._refresh_validation)
        self._refresh_validation()

    def add_files(self, paths: Iterable[str | Path]) -> None:
        existing = {self.file_list.item(i).text() for i in range(self.file_list.count())}
        for value in paths:
            path = str(Path(value))
            if path not in existing:
                self.file_list.addItem(path)
                existing.add(path)
        self._refresh_validation()

    def values(self) -> dict:
        return {
            "recipe_id": self.recipe_combo.currentData(),
            "files": [self.file_list.item(i).text() for i in range(self.file_list.count())],
            "report_path": self.report_path.text().strip(),
        }

    def _browse_inputs(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Data Files", "", DATA_FILTER)
        self.add_files(paths)

    def _remove_selected(self) -> None:
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self._refresh_validation()

    def _browse_report(self) -> None:
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Batch Report", "batch_analysis.xlsx", REPORT_FILTER
        )
        if not path:
            return
        suffixes = {"Excel Workbook (*.xlsx)": ".xlsx", "PDF Report (*.pdf)": ".pdf",
                    "Word Report (*.docx)": ".docx", "PowerPoint (*.pptx)": ".pptx",
                    "HTML Report (*.html)": ".html", "CSV Summary (*.csv)": ".csv",
                    "JSON Manifest (*.json)": ".json"}
        if not Path(path).suffix:
            path += suffixes.get(selected_filter, ".xlsx")
        self.report_path.setText(path)

    def _problem(self) -> str:
        if self.recipe_combo.count() == 0 or self.recipe_combo.currentData() is None:
            return "Create or import an Analysis Recipe first."
        if self.file_list.count() == 0:
            return "Add at least one input file."
        if not self.report_path.text().strip():
            return "Choose where to save the summary report."
        if Path(self.report_path.text().strip()).suffix.lower() not in {
            ".xlsx", ".pdf", ".docx", ".pptx", ".html", ".htm", ".csv", ".json",
        }:
            return "Report must use .xlsx, .pdf, .docx, .pptx, .html, .csv, or .json."
        return ""

    def _refresh_validation(self, *_args) -> None:
        problem = self._problem()
        self.validation_label.setText(problem or f"Ready to process {self.file_list.count()} file(s).")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not problem)

    def _accept_if_valid(self) -> None:
        self._refresh_validation()
        if not self._problem():
            self.accept()


__all__ = ["BatchAnalysisDialog", "DATA_FILTER", "REPORT_FILTER"]
