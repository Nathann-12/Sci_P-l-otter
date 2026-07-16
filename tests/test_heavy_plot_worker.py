from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from widgets.heavy_plot_worker import CancellationToken, HeavyPlotWorker


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_cancellation_token_is_cooperative():
    token = CancellationToken()
    assert token.cancelled is False
    token.cancel()
    assert token.cancelled is True
    with pytest.raises(RuntimeError, match="cancelled"):
        token.raise_if_cancelled()


def test_heavy_plot_worker_computes_off_gui_thread(qapp):
    gui_thread = threading.get_ident()
    seen = {}
    loop = QEventLoop()

    def prepare(frame, token):
        token.raise_if_cancelled()
        seen["worker_thread"] = threading.get_ident()
        return int(frame["value"].sum())

    worker = HeavyPlotWorker(prepare, pd.DataFrame({"value": [1, 2, 3]}))
    worker.signals.finished.connect(lambda value: (seen.update(result=value), loop.quit()))
    worker.signals.failed.connect(lambda error: (seen.update(error=error), loop.quit()))
    QTimer.singleShot(5_000, loop.quit)
    worker.start()
    loop.exec()

    assert seen.get("result") == 6
    assert "error" not in seen
    assert seen["worker_thread"] != gui_thread


def test_heavy_plot_worker_cancel_stops_preparation(qapp):
    events = []
    loop = QEventLoop()

    def prepare(_frame, token):
        for _ in range(2_000):
            token.raise_if_cancelled()
            time.sleep(0.001)
        return "finished"

    worker = HeavyPlotWorker(prepare, pd.DataFrame())
    worker.signals.finished.connect(lambda _value: (events.append("finished"), loop.quit()))
    worker.signals.cancelled.connect(lambda: (events.append("cancelled"), loop.quit()))
    QTimer.singleShot(20, worker.cancel)
    QTimer.singleShot(5_000, loop.quit)
    worker.start()
    loop.exec()

    assert events == ["cancelled"]
