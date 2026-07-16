"""Cancelable background computation for heavy gallery plots.

Only NumPy/Pandas/SciPy preparation runs in the worker.  Every Matplotlib call
is deliberately left to the GUI thread.
"""

from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class CancelledError(RuntimeError):
    pass


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError("plot preparation cancelled")


class HeavyPlotSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class HeavyPlotWorker(QRunnable):
    def __init__(self, prepare, dataframe):
        super().__init__()
        self.prepare = prepare
        self.dataframe = dataframe
        self.token = CancellationToken()
        self.signals = HeavyPlotSignals()

    def cancel(self) -> None:
        self.token.cancel()

    def run(self) -> None:
        try:
            self.token.raise_if_cancelled()
            result = self.prepare(self.dataframe, self.token)
            self.token.raise_if_cancelled()
        except CancelledError:
            self.signals.cancelled.emit()
        except Exception:
            self.signals.failed.emit(traceback.format_exc(limit=8))
        else:
            self.signals.finished.emit(result)

    def start(self, pool: QThreadPool | None = None) -> None:
        (pool or QThreadPool.globalInstance()).start(self)
