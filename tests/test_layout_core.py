"""Pure layout page model + PDF/PNG renderers + auto-grid."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from core import layout as L


def _png():
    fig = Figure(figsize=(3, 2), dpi=80)
    fig.add_subplot(111).plot([0, 1, 2], [0, 1, 4])
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


def test_page_sizes_and_defaults():
    page = L.LayoutPage(page="A4 Landscape")
    assert page.width == 842.0 and page.height == 595.0
    assert L.LayoutPage().page == "A4 Portrait"


def test_auto_grid_places_items_inside_the_page_without_overlap_columns():
    page = L.LayoutPage(page="A4 Portrait")
    items = [L.FigureItem(0, 0, 0, 0, _png()) for _ in range(4)]
    L.auto_grid(page, items, title="Deck")
    figs = [it for it in page.items if isinstance(it, L.FigureItem)]
    assert len(figs) == 4
    # two columns for 4 items; first row shares a y, columns differ in x
    assert figs[0].y == figs[1].y and figs[0].x < figs[1].x
    for f in figs:
        assert 0 <= f.x and f.x + f.w <= page.width + 1
        assert f.y + f.h <= page.height + 1
    # a title text was added first
    assert isinstance(page.items[0], L.TextItem) and page.items[0].bold


def test_single_item_uses_one_column():
    page = L.LayoutPage()
    L.auto_grid(page, [L.FigureItem(0, 0, 0, 0, _png())], title="")
    fig = page.items[0]
    assert fig.w > page.width * 0.7   # spans most of the width


def test_render_pdf_and_png(tmp_path):
    page = L.LayoutPage(page="A4 Portrait")
    page.add(L.TextItem(40, 30, 500, 30, "Title", font_size=20, bold=True))
    page.add(L.FigureItem(40, 80, 250, 180, _png()))
    page.add(L.TableItem(40, 280, 250, 120,
                         pd.DataFrame({"x": [1, 2, 3], "y": [1.1, 2.2, 3.3]})))
    pdf = tmp_path / "layout.pdf"
    L.render_pdf(page, str(pdf))
    assert pdf.read_bytes()[:5] == b"%PDF-"
    png = tmp_path / "layout.png"
    L.render_png(page, str(png))
    assert png.read_bytes()[:4] == b"\x89PNG"


def test_render_handles_empty_page(tmp_path):
    page = L.LayoutPage()
    L.render_pdf(page, str(tmp_path / "e.pdf"))
    L.render_png(page, str(tmp_path / "e.png"))
    assert (tmp_path / "e.pdf").exists() and (tmp_path / "e.png").exists()
