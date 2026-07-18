from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture()
def window(qapp):
    import main

    value = main.MainWindow()
    value.show()
    yield value
    try:
        value.close()
    except RuntimeError:
        pass


def _menu(window, title):
    wanted = title.replace("&", "")
    stack = [action.menu() for action in window.menuBar().actions() if action.menu()]
    while stack:
        menu = stack.pop()
        if menu.title().replace("&", "") == wanted:
            return menu
        stack.extend(action.menu() for action in menu.actions() if action.menu())
    return None


def test_scientific_suite_actions_are_discoverable_in_analysis_menu(window):
    assert _menu(window, "Statistics") is not None
    assert _menu(window, "Hypothesis Tests") is not None
    assert _menu(window, "ANOVA") is not None
    assert _menu(window, "Nonparametric Tests") is not None
    assert _menu(window, "Analysis Recipes") is not None

    texts = {
        action.text().replace("&", "")
        for menu_name in ("Statistics", "Fitting", "Peaks and Baseline", "Analysis Recipes")
        for action in _menu(window, menu_name).actions()
    }
    assert "Multiple Linear Regression..." in texts
    assert "Global Fit (Shared Parameters)..." in texts
    assert "Peak Analyzer (Baseline + Multi-Peak Fit)..." in texts
    assert "Batch Analysis..." in texts


def test_scientific_operation_registry_is_initialized(window):
    names = set(window._scientific_registry.names())
    assert {
        "one_sample_t_test", "two_way_anova", "multiple_linear_regression",
        "global_fit", "peak_analysis",
    }.issubset(names)


def test_real_main_window_creates_audited_result_book(window):
    frame = pd.DataFrame({"sample": [2.0, 2.5, 3.0, 3.5, 4.0]})
    window._stage_insert("Scientific Source", frame, None)
    binding = window._create_and_run_recipe(
        "One-sample t-test", "one_sample_t_test",
        {"sample": "sample", "popmean": 0.0}, "Scientific Source", frame,
    )
    assert binding is not None
    assert binding.result_book in window._datasets
    metadata = window._datasets[binding.result_book]["analysis_provenance"]
    assert metadata["recipe_id"] == binding.recipe_id
    assert metadata["status"] == "Clean"
    assert any(row["id"] == binding.recipe_id for row in window.analysis_recipe_summaries())
