"""Layout editor widget + MainWindow layout workflow + AI arrange_layout."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _graphs(n=2):
    from matplotlib.figure import Figure
    import io

    out = []
    for k in range(n):
        fig = Figure(figsize=(3, 2), dpi=80)
        fig.add_subplot(111).plot([0, 1, 2], [k, k + 1, k])
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        out.append((f"Graph {k}", buf.getvalue()))
    return out


def _tables():
    return [("Calib", pd.DataFrame({"c": [1, 2, 5], "r": [3.4, 6.9, 17.1]}))]


def test_editor_prefill_and_build_model(qapp):
    from UI.layout_page import LayoutEditor, LayoutItem

    ed = LayoutEditor(_graphs(2), _tables(), ask_save_path=lambda *a: None,
                      default_title="Poster")
    ed.prefill()
    items = [it for it in ed.scene.items() if isinstance(it, LayoutItem)]
    kinds = sorted(i.kind for i in items)
    assert kinds == ["figure", "figure", "table", "text"]
    page = ed.build_page()
    assert len(page.items) == 4
    # figures are arranged to non-overlapping positions
    figs = [it for it in items if it.kind == "figure"]
    assert figs[0].pos() != figs[1].pos()


def test_editor_add_delete_and_page_size(qapp):
    from UI.layout_page import LayoutEditor, LayoutItem

    ed = LayoutEditor(_graphs(1), _tables())
    ed._add_figure(_graphs(1)[0][1])
    ed._add_table(_tables()[0][1])
    assert len([i for i in ed.scene.items() if isinstance(i, LayoutItem)]) == 2
    ed.scene.selectedItems()[0].setSelected(True)
    ed._delete_selected()
    assert len([i for i in ed.scene.items() if isinstance(i, LayoutItem)]) == 1
    ed._set_page("Slide 16:9")
    assert ed._page_w == 960.0


def test_layout_item_handle_and_to_model(qapp):
    from PySide6.QtCore import QPointF
    from UI.layout_page import LayoutItem
    from core import layout as L

    item = LayoutItem("text", 200, 40, text="hi", font_size=12)
    item.setPos(30, 40)
    assert item._on_handle(QPointF(195, 35)) is True   # bottom-right corner
    assert item._on_handle(QPointF(10, 10)) is False
    model = item.to_model()
    assert isinstance(model, L.TextItem)
    assert model.x == 30 and model.y == 40 and model.text == "hi"


@pytest.fixture()
def window(qapp):
    import main

    win = main.MainWindow()
    win.show()
    yield win
    try:
        win.close()
    except RuntimeError:
        pass


def _seed(win):
    for k in range(2):
        win.tabs.add_tab()
        ax = win.tabs.currentWidget().get_axes()
        ax.plot(np.linspace(0, 6, 30), np.sin(np.linspace(0, 6, 30) + k))
        win.tabs.currentWidget().draw()
    win._open_signal_result_book("Res", pd.DataFrame({"a": [1, 2], "b": [3, 4]}))


def test_layout_export_core_writes_pdf_and_png(window, tmp_path):
    _seed(window)
    pdf, n = window.layout_export_core(str(tmp_path / "l.pdf"), title="Deck")
    assert n == 3 and (tmp_path / "l.pdf").read_bytes()[:5] == b"%PDF-"
    png, _ = window.layout_export_core(str(tmp_path / "l.png"))
    assert (tmp_path / "l.png").read_bytes()[:4] == b"\x89PNG"
    with pytest.raises(ValueError, match="pdf/png"):
        window.layout_export_core(str(tmp_path / "l.txt"))


def test_ai_arrange_layout_tool(window, tmp_path):
    from ai.app_tools import build_app_registry

    _seed(window)
    registry = build_app_registry(window)
    out = registry.execute("arrange_layout", {
        "format": "pdf", "page": "A4 Landscape", "path": str(tmp_path / "poster.pdf")})
    assert "Arranged" in out and "3 item" in out
    assert (tmp_path / "poster.pdf").exists()


def test_report_menu_has_layout_action(window):
    texts = {a.text().replace("&", "") for a in window._report_menu.actions()}
    assert any("Layout Page" in t for t in texts)
