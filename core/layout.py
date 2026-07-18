"""Free-form layout page: place figures, tables and text anywhere on a page.

Pure data model + renderers (reportlab PDF, matplotlib PNG). The interactive
QGraphicsView editor in ``UI/layout_page.py`` edits this model and calls these
renderers on export, so what you arrange is exactly what ships — and export is
unit-testable with no Qt.

Coordinates are in POINTS (1/72"), origin top-left, y increasing downward
(screen convention). Renderers flip to their native systems.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

# page presets in points (w, h)
PAGE_SIZES = {
    "A4 Portrait": (595.0, 842.0),
    "A4 Landscape": (842.0, 595.0),
    "Letter Portrait": (612.0, 792.0),
    "Letter Landscape": (792.0, 612.0),
    "Slide 16:9": (960.0, 540.0),
    "Square": (600.0, 600.0),
}


@dataclass
class FigureItem:
    x: float
    y: float
    w: float
    h: float
    png: bytes = b""
    kind: str = "figure"


@dataclass
class TableItem:
    x: float
    y: float
    w: float
    h: float
    frame: Optional[pd.DataFrame] = None
    max_rows: int = 12
    font_size: float = 7.0
    kind: str = "table"


@dataclass
class TextItem:
    x: float
    y: float
    w: float
    h: float
    text: str = ""
    font_size: float = 14.0
    bold: bool = False
    color: str = "#1a2230"
    kind: str = "text"


@dataclass
class LayoutPage:
    page: str = "A4 Portrait"
    background: str = "#ffffff"
    items: List[object] = field(default_factory=list)

    @property
    def size(self):
        return PAGE_SIZES.get(self.page, PAGE_SIZES["A4 Portrait"])

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    def add(self, item) -> "LayoutPage":
        self.items.append(item)
        return self


def _fmt(value) -> str:
    if isinstance(value, float):
        if value != value:
            return "—"
        if value == 0 or (1e-4 <= abs(value) < 1e6):
            return f"{value:.4g}"
        return f"{value:.3e}"
    return str(value)


# ------------------------------------------------------------- auto arrangement
def auto_grid(page: LayoutPage, items, *, margin=40.0, gap=18.0,
              title: str = "") -> LayoutPage:
    """Place *items* (FigureItem/TableItem/TextItem, sizes ignored) in a tidy
    grid that fills the page. Figures/tables share a near-square grid."""
    W, H = page.width, page.height
    top = margin
    if title:
        page.add(TextItem(margin, margin, W - 2 * margin, 26, title,
                          font_size=18, bold=True))
        top = margin + 34
    n = len(items)
    if n == 0:
        return page
    cols = 1 if n == 1 else (2 if n <= 6 else 3)
    rows = int(np.ceil(n / cols))
    cell_w = (W - 2 * margin - (cols - 1) * gap) / cols
    cell_h = (H - top - margin - (rows - 1) * gap) / rows
    for i, item in enumerate(items):
        r, c = divmod(i, cols)
        item.x = margin + c * (cell_w + gap)
        item.y = top + r * (cell_h + gap)
        item.w = cell_w
        item.h = cell_h
        page.add(item)
    return page


# --------------------------------------------------------------------- PDF
def render_pdf(page: LayoutPage, path: str) -> str:
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.platypus import Table, TableStyle

    W, H = page.width, page.height
    c = pdfcanvas.Canvas(str(path), pagesize=(W, H))
    c.setFillColor(colors.HexColor(page.background))
    c.rect(0, 0, W, H, fill=1, stroke=0)

    for it in page.items:
        px, py = it.x, H - it.y - it.h  # flip to reportlab bottom-left origin
        if isinstance(it, FigureItem) and it.png:
            try:
                c.drawImage(ImageReader(io.BytesIO(it.png)), px, py, width=it.w,
                            height=it.h, preserveAspectRatio=True, anchor="c", mask="auto")
            except Exception:
                pass
        elif isinstance(it, TextItem):
            c.setFillColor(colors.HexColor(it.color))
            font = "Helvetica-Bold" if it.bold else "Helvetica"
            c.setFont(font, it.font_size)
            line_h = it.font_size * 1.3
            yy = H - it.y - it.font_size
            for line in str(it.text).split("\n"):
                c.drawString(it.x, yy, line)
                yy -= line_h
        elif isinstance(it, TableItem) and it.frame is not None:
            data = _table_data(it.frame, it.max_rows)
            ncol = max(1, len(data[0]))
            t = Table(data, colWidths=[it.w / ncol] * ncol)
            t.setStyle(_pdf_table_style(it.font_size))
            t.wrapOn(c, it.w, it.h)
            t.drawOn(c, it.x, H - it.y - t._height)
    c.showPage()
    c.save()
    return str(path)


def _table_data(frame: pd.DataFrame, max_rows: int):
    shown = frame.head(max_rows)
    data = [[str(col) for col in shown.columns]]
    data += [[_fmt(v) for v in row] for _, row in shown.iterrows()]
    return data


def _pdf_table_style(font_size):
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle

    return TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fb")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#c4cede")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#e2e7ee")),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])


# --------------------------------------------------------------------- PNG
def render_png(page: LayoutPage, path: str, *, scale: float = 2.0) -> str:
    from matplotlib.figure import Figure

    W, H = page.width, page.height
    fig = Figure(figsize=(W / 72.0, H / 72.0), dpi=72 * scale)
    fig.patch.set_facecolor(page.background)

    def norm(it):  # model (top-left, y-down) -> figure fraction (bottom-left, y-up)
        return [it.x / W, 1 - (it.y + it.h) / H, it.w / W, it.h / H]

    for it in page.items:
        rect = norm(it)
        if isinstance(it, FigureItem) and it.png:
            import matplotlib.image as mpimg

            ax = fig.add_axes(rect)
            ax.imshow(mpimg.imread(io.BytesIO(it.png)))
            ax.axis("off")
        elif isinstance(it, TextItem):
            fig.text(it.x / W, 1 - it.y / H, str(it.text), va="top", ha="left",
                     fontsize=it.font_size * scale / 2.0,
                     fontweight="bold" if it.bold else "normal", color=it.color,
                     wrap=True)
        elif isinstance(it, TableItem) and it.frame is not None:
            ax = fig.add_axes(rect)
            ax.axis("off")
            data = _table_data(it.frame, it.max_rows)
            table = ax.table(cellText=data[1:], colLabels=data[0], loc="upper left",
                             cellLoc="left", bbox=[0, 0, 1, 1])
            table.auto_set_font_size(False)
            table.set_fontsize(it.font_size * scale / 2.0)
            for (r, _c), cell in table.get_celld().items():
                cell.set_edgecolor("#e2e7ee")
                if r == 0:
                    cell.set_facecolor("#f6f8fb")
                    cell.set_text_props(fontweight="bold")
    fig.savefig(str(path), dpi=72 * scale, facecolor=page.background)
    return str(path)
