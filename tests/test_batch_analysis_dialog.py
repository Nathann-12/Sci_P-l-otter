from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from dialogs.batch_analysis_dialog import BatchAnalysisDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_batch_dialog_requires_recipe_files_and_report(qapp, tmp_path):
    dialog = BatchAnalysisDialog([{"id": "r1", "name": "Peak recipe"}])
    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    assert not ok.isEnabled()
    source = tmp_path / "data.csv"
    source.write_text("x,y\n1,2\n", encoding="utf-8")
    dialog.add_files([source, source])
    assert dialog.file_list.count() == 1
    dialog.report_path.setText(str(tmp_path / "report.xlsx"))
    assert ok.isEnabled()
    assert dialog.values() == {
        "recipe_id": "r1", "files": [str(source)],
        "report_path": str(tmp_path / "report.xlsx"),
    }


def test_batch_dialog_without_recipes_explains_blocker(qapp):
    dialog = BatchAnalysisDialog([])
    assert "Create or import" in dialog.validation_label.text()
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
