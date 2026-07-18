from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from dialogs.recipe_manager_dialog import RecipeManagerDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _recipes():
    return [{
        "id": "r-1", "name": "Welch comparison", "mode": "Auto", "status": "Clean",
        "source": "Book1", "result": "Welch comparison Result", "last_run": "Today",
        "operation": "independent_t_test", "source_checksum": "sha256:abc",
    }]


def test_recipe_manager_selects_and_emits_commands(qapp):
    dialog = RecipeManagerDialog(_recipes())
    assert dialog.selected_recipe_id() == "r-1"
    assert dialog.table.item(0, 0).text() == "Welch comparison"
    assert "sha256:abc" in dialog.detail.text()

    calls = []
    dialog.run_requested.connect(lambda recipe_id: calls.append(("run", recipe_id)))
    dialog.mode_requested.connect(lambda recipe_id, mode: calls.append((mode, recipe_id)))
    dialog._emit_run()
    dialog.mode_combo.setCurrentText("Frozen")
    dialog._emit_mode()
    assert calls == [("run", "r-1"), ("Frozen", "r-1")]


def test_empty_recipe_manager_disables_controls(qapp):
    dialog = RecipeManagerDialog([])
    assert dialog.selected_recipe_id() == ""
    assert not dialog.run_button.isEnabled()
    assert "No analysis recipes" in dialog.detail.text()
