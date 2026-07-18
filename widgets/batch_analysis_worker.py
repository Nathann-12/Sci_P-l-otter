"""Qt bridge for running the pure batch pipeline away from the GUI thread."""
from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from analysis.batch import run_batch_analysis


class BatchWorkerSignals(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)


class BatchAnalysisWorker(QRunnable):
    """Cancelable worker; loaders/analyzers must not touch Qt widgets."""

    def __init__(self, sources, *, loader, analyzer, recipe_name, recipe_version=1):
        super().__init__()
        self.sources = list(sources)
        self.loader = loader
        self.analyzer = analyzer
        self.recipe_name = recipe_name
        self.recipe_version = int(recipe_version)
        self.signals = BatchWorkerSignals()
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _progress(self, done, total, item) -> None:
        source = "" if item is None else item.source
        self.signals.progress.emit(int(done), int(total), source)

    def run(self) -> None:
        try:
            result = run_batch_analysis(
                self.sources,
                loader=self.loader,
                analyzer=self.analyzer,
                recipe_name=self.recipe_name,
                recipe_version=self.recipe_version,
                is_cancelled=self._cancel_event.is_set,
                progress=self._progress,
            )
        except Exception:
            self.signals.failed.emit(traceback.format_exc(limit=12))
        else:
            self.signals.finished.emit(result)

    def start(self, pool: QThreadPool | None = None) -> None:
        (pool or QThreadPool.globalInstance()).start(self)


__all__ = ["BatchAnalysisWorker", "BatchWorkerSignals"]
