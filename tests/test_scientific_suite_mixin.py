from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from main_window_scientific_suite_mixin import MainWindowScientificSuiteMixin


class _Table(QObject):
    itemChanged = Signal(object)


class _Book(QObject):
    def __init__(self, name, frame):
        super().__init__()
        self.dataset_name = name
        self.table = _Table(self)
        self._frame = frame.copy()

    def dataframe(self):
        return self._frame.copy()

    def set_dataframe(self, frame):
        self._frame = frame.copy()


class _Mdi:
    def __init__(self, book):
        self._books = {book.dataset_name: (book, object())}

    def book_widget(self, name):
        entry = self._books.get(name)
        return entry[0] if entry else None


class _Stub(MainWindowScientificSuiteMixin):
    def __init__(self, frame):
        self.workbook = _Book("Book1", frame)
        self.mdi = _Mdi(self.workbook)
        self.tabs = None
        self._df = frame.copy()
        self._datasets = {"Book1": {"df": frame.copy(), "path": None}}
        self.messages = []
        self.errors = []
        self.history = []
        self.init_scientific_suite()

    def _active_book_label(self):
        return self.workbook.dataset_name

    def _open_signal_result_book(self, name, frame):
        base = name
        counter = 2
        while name in self._datasets:
            name = f"{base} {counter}"
            counter += 1
        self._datasets[name] = {"df": frame.copy(), "path": None}
        return name

    def notify(self, message, *args, **kwargs):
        self.messages.append(message)

    def inform(self, title, message):
        self.messages.append(f"{title}: {message}")

    def error_box(self, title, message):
        self.errors.append(f"{title}: {message}")

    def _record_op(self, operation, **params):
        self.history.append((operation, params))

    def _refresh_project_explorer(self):
        pass


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_new_analysis_creates_recipe_result_and_provenance(qapp):
    frame = pd.DataFrame({"sample": [1.0, 2.0, 3.0, 4.0, 5.0]})
    window = _Stub(frame)
    binding = window._create_and_run_recipe(
        "One-sample t-test", "one_sample_t_test",
        {"sample": "sample", "popmean": 0.0}, "Book1", frame,
    )
    assert binding is not None
    assert binding.status == "Clean"
    assert binding.mode == "Auto"
    assert binding.result_book in window._datasets
    report = window._datasets[binding.result_book]["df"]
    assert "p_value" in report.metric.values
    provenance = window._datasets[binding.result_book]["analysis_provenance"]
    assert provenance["recipe_id"] == binding.recipe_id
    assert provenance["source_checksum"].startswith("sha256:")
    assert binding.recipe.provenance[-1].success is True


def test_global_fit_recipe_publishes_summary_and_curve_books(qapp):
    x = np.linspace(-3, 3, 100)
    frame = pd.DataFrame({
        "x": x,
        "one": 1 + 2*np.exp(-.5*((x-.2)/.7)**2),
        "two": 2 + 4*np.exp(-.5*((x-.2)/.7)**2),
    })
    window = _Stub(frame)
    binding = window._create_and_run_recipe(
        "Global Fit", "global_fit",
        {"x": "x", "ys": ["one", "two"], "model": "gaussian",
         "shared": ["center", "sigma"], "confidence": .95, "loss": "linear"},
        "Book1", frame,
    )
    assert binding is not None
    assert binding.result_book and binding.curves_book
    assert set(window._datasets[binding.curves_book]["df"].dataset) == {"one", "two"}


def test_recipe_project_round_trip_restores_bindings(qapp):
    frame = pd.DataFrame({"sample": [1.0, 2.0, 3.0, 4.0]})
    first = _Stub(frame)
    binding = first._create_and_run_recipe(
        "One-sample t-test", "one_sample_t_test",
        {"sample": "sample", "popmean": 0.0}, "Book1", frame,
    )
    payload = first.serialize_analysis_recipes()

    restored = _Stub(frame)
    restored.restore_analysis_recipes(payload)
    assert list(restored._scientific_recipes) == [binding.recipe_id]
    copy = restored._scientific_recipes[binding.recipe_id]
    assert copy.recipe.to_dict() == binding.recipe.to_dict()
    assert copy.source_book == "Book1"


def test_source_edit_marks_manual_recipe_dirty_without_recomputing(qapp):
    frame = pd.DataFrame({"sample": [1.0, 2.0, 3.0, 4.0]})
    window = _Stub(frame)
    binding = window._create_and_run_recipe(
        "One-sample t-test", "one_sample_t_test",
        {"sample": "sample"}, "Book1", frame,
    )
    window._set_recipe_mode(binding.recipe_id, "Manual")
    result_before = window._datasets[binding.result_book]["df"].copy()
    window.workbook._frame.loc[0, "sample"] = 99.0
    window._analysis_source_edited(window.workbook)
    assert binding.status == "Dirty"
    assert window._datasets[binding.result_book]["analysis_provenance"]["stale"] is True
    pd.testing.assert_frame_equal(window._datasets[binding.result_book]["df"], result_before)


def test_output_warning_flags_non_converged_fits(qapp):
    warn = MainWindowScientificSuiteMixin._output_warning
    # Peak analyzer report: one boolean success per peak.
    clean_peak = pd.DataFrame({"peak": [1], "center": [4.0], "success": [True]})
    failed_peak = pd.DataFrame({"peak": [1], "center": [4.0], "success": [False]})
    assert warn({"result": clean_peak}) == ""
    assert "did not converge" in warn({"result": failed_peak})

    # Global fit report: a Convergence section carries success + message.
    failed_global = pd.DataFrame([
        {"section": "Convergence", "metric": "success", "value": False, "detail": np.nan},
        {"section": "Convergence", "metric": "message", "value": np.nan,
         "detail": "The maximum number of function evaluations is exceeded."},
        {"section": "Parameter", "metric": "center", "value": 0.3, "detail": np.nan},
    ])
    message = warn({"result": failed_global})
    assert "Global fit did not converge" in message
    assert "maximum number" in message


def test_committed_fit_is_marked_warning_when_optimiser_fails(qapp, monkeypatch):
    frame = pd.DataFrame({"sample": [1.0, 2.0, 3.0, 4.0, 5.0]})
    window = _Stub(frame)
    binding = window._create_and_run_recipe(
        "One-sample t-test", "one_sample_t_test",
        {"sample": "sample", "popmean": 0.0}, "Book1", frame,
    )
    # Simulate a re-run whose report says the optimiser stopped early.
    from main_window_scientific_suite_mixin import _RecipeComputation
    failed_report = pd.DataFrame({"peak": [1], "center": [4.0], "success": [False]})
    computation = _RecipeComputation(
        binding.engine, {"result": failed_report}, "sha256:deadbeef"
    )
    window._commit_recipe_computation(binding, computation)
    assert binding.status == "Warning"
    assert "did not converge" in binding.error


def test_failed_recalculation_keeps_last_good_result_metadata(qapp):
    frame = pd.DataFrame({"sample": [1.0, 2.0, 3.0, 4.0]})
    window = _Stub(frame)
    binding = window._create_and_run_recipe(
        "One-sample t-test", "one_sample_t_test",
        {"sample": "sample"}, "Book1", frame,
    )
    original = window._datasets[binding.result_book]["df"].copy()
    window._recipe_recalculation_failed(binding.recipe_id, "Traceback\nValueError: bad mapping")
    assert "last good result kept" in binding.status
    assert binding.error == "ValueError: bad mapping"
    pd.testing.assert_frame_equal(window._datasets[binding.result_book]["df"], original)


def test_prepare_persistence_snapshots_visible_recipe_source(qapp):
    frame = pd.DataFrame({"sample": [1.0, 2.0, 3.0, 4.0]})
    window = _Stub(frame)
    binding = window._create_and_run_recipe(
        "One-sample t-test", "one_sample_t_test", {"sample": "sample"},
        "Book1", frame,
    )
    window.workbook._frame.loc[0, "sample"] = 42.0
    window.prepare_analysis_recipe_persistence()
    assert window._datasets["Book1"]["df"].loc[0, "sample"] == 42.0
