from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _stable_matplotlib_backend():
    """Pin one clean Matplotlib backend for the whole session.

    Many test modules call ``matplotlib.use("Agg")`` at import time while the app
    forces ``Qt5Agg``, so full-suite collection leaves the backend in an
    inconsistent, non-force state. Re-forcing it once, after collection but
    before the first test, gives every test a clean, predictable backend
    (headless Agg) instead of whatever the import order happened to settle on.
    """
    import matplotlib

    matplotlib.use("Agg", force=True)
    yield


@pytest.fixture(scope="session", autouse=True)
def _keep_qapplication_alive():
    """Use one QApplication for the suite; Qt cannot safely recreate it."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _cleanup_qt_widgets_after_test():
    """Keep Qt tests isolated so full-suite runtime does not degrade over time."""
    yield

    # Close pyplot-managed figures first so leaked figures do not pile up in
    # matplotlib's Gcf across the run (keeps memory and per-test time bounded,
    # and avoids touching a canvas whose embedding QWidget is deleted below).
    try:
        import matplotlib.pyplot as plt

        plt.close("all")
    except Exception:
        pass

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

    # Drop Python-side wrappers of the just-deleted C++ objects before the next
    # test starts, so their teardown cannot race with new widget creation.
    import gc

    gc.collect()
