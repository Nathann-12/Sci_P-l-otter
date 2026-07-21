"""Report Builder — pick title/author/template and what to include, then
preview or export. Deliberately small: sensible defaults, everything on."""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from core.report import TEMPLATES


class ReportBuilderDialog(QDialog):
    def __init__(self, table_names: List[str], graph_names: List[str],
                 *, default_title="SciPlotter Report", default_author="",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Report")
        self.setMinimumWidth(460)
        self._action = "preview"

        outer = QVBoxLayout(self)
        form = QFormLayout()
        self.ed_title = QLineEdit(default_title)
        self.ed_subtitle = QLineEdit()
        self.ed_author = QLineEdit(default_author)
        self.cb_template = QComboBox()
        self.cb_template.addItems(list(TEMPLATES))
        form.addRow("Title", self.ed_title)
        form.addRow("Subtitle", self.ed_subtitle)
        form.addRow("Author", self.ed_author)
        form.addRow("Template", self.cb_template)
        outer.addLayout(form)

        gb = QGroupBox("Include")
        gv = QVBoxLayout(gb)
        self.chk_narrative = QCheckBox("Auto summary (data-driven narrative)")
        self.chk_narrative.setChecked(True)
        self.chk_graphs = QCheckBox(f"All figures ({len(graph_names)})")
        self.chk_graphs.setChecked(True)
        self.chk_tables = QCheckBox("Selected tables")
        self.chk_tables.setChecked(True)
        gv.addWidget(self.chk_narrative)
        gv.addWidget(self.chk_graphs)
        gv.addWidget(self.chk_tables)
        gv.addWidget(QLabel("Tables:"))
        self.lst_tables = QListWidget()
        for name in table_names:
            item = QListWidgetItem(name)
            item.setCheckState(Qt.Checked)
            self.lst_tables.addItem(item)
        self.lst_tables.setMaximumHeight(150)
        gv.addWidget(self.lst_tables)
        outer.addWidget(gb)

        buttons = QDialogButtonBox()
        btn_preview = buttons.addButton("Preview", QDialogButtonBox.AcceptRole)
        btn_export = buttons.addButton("Export…", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        btn_preview.clicked.connect(lambda: self._finish("preview"))
        btn_export.clicked.connect(lambda: self._finish("export"))
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _finish(self, action: str) -> None:
        self._action = action
        self.accept()

    def values(self) -> dict:
        table_names = [
            self.lst_tables.item(i).text()
            for i in range(self.lst_tables.count())
            if self.lst_tables.item(i).checkState() == Qt.Checked
        ]
        return {
            "title": self.ed_title.text().strip() or "SciPlotter Report",
            "subtitle": self.ed_subtitle.text().strip(),
            "author": self.ed_author.text().strip(),
            "template": self.cb_template.currentText(),
            "include_narrative": self.chk_narrative.isChecked(),
            "include_graphs": self.chk_graphs.isChecked(),
            "include_tables": self.chk_tables.isChecked(),
            "table_names": table_names,
            "action": self._action,
        }
