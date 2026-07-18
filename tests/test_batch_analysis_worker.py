from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from widgets.batch_analysis_worker import BatchAnalysisWorker


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_worker_emits_progress_and_result(qapp, tmp_path):
    files = []
    for index in range(2):
        path = tmp_path / f"{index}.csv"
        pd.DataFrame({"y": [index, index + 1]}).to_csv(path, index=False)
        files.append(path)

    worker = BatchAnalysisWorker(
        files,
        loader=pd.read_csv,
        analyzer=lambda frame, context: {"mean": frame.y.mean()},
        recipe_name="Mean",
    )
    progress = []
    result = []
    failure = []
    loop = QEventLoop()
    worker.signals.progress.connect(lambda done, total, source: progress.append((done, total)))
    worker.signals.finished.connect(lambda value: (result.append(value), loop.quit()))
    worker.signals.failed.connect(lambda message: (failure.append(message), loop.quit()))
    worker.start()
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert failure == []
    assert result and result[0].success_count == 2
    assert progress[0] == (0, 2)
    assert progress[-1] == (2, 2)
