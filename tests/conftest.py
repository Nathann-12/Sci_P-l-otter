from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _cleanup_qt_widgets_after_test():
    """Keep Qt tests isolated so full-suite runtime does not degrade over time."""
    yield

    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except Exception:
        return

    app = QApplication.instance()
    if app is None:
        return

    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            continue

    try:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    except RuntimeError:
        return
