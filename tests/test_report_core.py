"""Pure report model + HTML/Markdown/PDF renderers."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from core import report as R


def _png():
    fig = Figure(figsize=(4, 2.5), dpi=90)
    ax = fig.add_subplot(111)
    ax.plot(np.linspace(0, 6, 40), np.sin(np.linspace(0, 6, 40)))
    ax.set_title("Demo")
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


def _doc():
    doc = R.ReportDocument(title="Study", subtitle="sub", author="Lab")
    doc.add_kpis([("R2", 0.998), ("n", 40)])
    doc.add_text("Summary", "First paragraph.\n\nSecond paragraph.")
    doc.add_figure("Response", _png(), "Fig 1.")
    doc.add_table("Calibration",
                  pd.DataFrame({"x": [1, 2, 3], "y": [1.1, 2.2, 3.3]}), "Table 1.")
    return doc


def test_document_counts_and_defaults():
    doc = _doc()
    assert doc.counts() == {"figures": 1, "tables": 1, "text": 1}
    assert doc.date  # auto-filled to today


def test_html_is_self_contained_and_escaped():
    doc = R.ReportDocument(title="A & B <x>")
    doc.add_text("H", "value < 5 & okay")
    doc.add_figure("F", _png())
    html = R.render_html(doc)
    # no external resource references — everything inline
    assert "http://" not in html and "https://" not in html
    assert "data:image/png;base64," in html
    # HTML-escaped user text, never raw angle brackets from content
    assert "A &amp; B &lt;x&gt;" in html
    assert "value &lt; 5 &amp; okay" in html


def test_html_renders_table_and_truncates():
    frame = pd.DataFrame({"v": range(100)})
    doc = R.ReportDocument().add_table("Big", frame, max_rows=10)
    html = R.render_html(doc)
    assert "90 more rows" in html and "100 total" in html
    assert html.count("<td>") == 10


def test_markdown_writes_figures_and_tables(tmp_path):
    md = R.render_markdown(_doc(), image_dir=tmp_path)
    assert "# Study" in md
    assert "| x | y |" in md
    assert (tmp_path / "figure_1.png").exists()
    assert "![Fig 1.](figure_1.png)" in md


def test_pdf_renders_a_valid_file(tmp_path):
    path = tmp_path / "r.pdf"
    R.render_pdf(_doc(), str(path))
    data = path.read_bytes()
    assert data[:5] == b"%PDF-" and len(data) > 1000


def test_number_formatting():
    assert R._fmt(0.0000123) == "1.2300e-05"
    assert R._fmt(3.14159) == "3.142"
    assert R._fmt(float("nan")) == "—"
    assert R._fmt("text") == "text"
