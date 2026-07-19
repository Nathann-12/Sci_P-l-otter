"""Report workflow on a real MainWindow (headless) + AI generate_report tool."""
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


def _seed_session(win):
    df = pd.DataFrame({"t": np.linspace(0, 10, 40), "y": np.cos(np.linspace(0, 10, 40))})
    win._stage_insert("Signal", df, None)
    win.tabs.add_tab()
    tab = win.tabs.currentWidget()
    ax = tab.get_axes()
    ax.plot(df["t"], df["y"], label="y")
    ax.set_title("Signal")
    tab.draw()
    win._open_signal_result_book(
        "Result", pd.DataFrame({"metric": ["mean", "std"], "value": [0.0, 0.7]}))


def _menu(win, title):
    wanted = title.replace("&", "")
    for a in win.menuBar().actions():
        if a.menu() and a.menu().title().replace("&", "") == wanted:
            return a.menu()
    return None


def test_report_menu_exists_with_actions(window):
    menu = _menu(window, "Report")
    assert menu is not None
    texts = {a.text().replace("&", "") for a in menu.actions()}
    assert any("Generate Report" in t for t in texts)
    assert any("HTML" in t for t in texts) and any("PDF" in t for t in texts)


def test_collectors_pick_up_graphs_and_tables(window):
    _seed_session(window)
    graphs = window._report_graphs()
    tables = window._report_tables()
    assert len(graphs) == 1 and graphs[0][1][:4] == b"\x89PNG"
    names = [t[0] for t in tables]
    assert "Signal" in names and "Result" in names


def test_generate_report_core_builds_document(window):
    _seed_session(window)
    doc = window.generate_report_core(title="My Report", author="N")
    counts = doc.counts()
    assert counts["figures"] == 1 and counts["tables"] >= 2 and counts["text"] == 1
    # narrative mentions a dataset by name
    from core.report import TextSection

    text = next(s for s in doc.sections if isinstance(s, TextSection))
    assert "Signal" in text.body or "dataset" in text.body


def test_report_export_all_formats(window, tmp_path):
    _seed_session(window)
    doc = window.generate_report_core(title="Export Test")
    for ext, head in ((".html", b"<!doctype"), (".pdf", b"%PDF-"), (".md", b"# Export"),
                      (".docx", b"PK"), (".pptx", b"PK")):
        path = tmp_path / f"r{ext}"
        window.report_export(doc, str(path))
        assert path.read_bytes()[:8].lower().startswith(head[:8].lower())
    with pytest.raises(ValueError, match="Unsupported"):
        window.report_export(doc, str(tmp_path / "r.rtf"))


def test_ai_generate_report_office_formats(window, tmp_path):
    from ai.app_tools import build_app_registry

    _seed_session(window)
    registry = build_app_registry(window)
    for fmt, magic in (("docx", b"PK"), ("pptx", b"PK")):
        out_path = tmp_path / f"ai.{fmt}"
        out = registry.execute("generate_report", {
            "format": fmt, "path": str(out_path)})
        assert "Report saved" in out
        assert out_path.read_bytes()[:2] == magic


def test_ai_generate_report_tool(window, tmp_path):
    from ai.app_tools import build_app_registry

    _seed_session(window)
    registry = build_app_registry(window)
    out_path = tmp_path / "ai_report.html"
    out = registry.execute("generate_report", {
        "title": "AI Report", "format": "html", "path": str(out_path)})
    assert "Report saved" in out and "figure" in out
    assert out_path.exists() and out_path.read_text(encoding="utf-8").startswith("<!doctype")


def test_ai_generate_report_needs_content(window):
    from ai.app_tools import build_app_registry

    # a fresh window with an empty starting Book -> nothing to report
    registry = build_app_registry(window)
    out = registry.execute("generate_report", {"format": "html"})
    assert "Nothing to report" in out
