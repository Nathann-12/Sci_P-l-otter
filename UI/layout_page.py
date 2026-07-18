"""Interactive layout page editor — drag, resize and snap figures, tables and
text on a page, then export to PDF / PNG.

Edits a live scene of :class:`LayoutItem`s; on export it serialises the scene
back to a :class:`core.layout.LayoutPage` and calls the pure renderers, so the
exported file matches the canvas exactly.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import pandas as pd
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import layout as L

logger = logging.getLogger(__name__)

_GRID = 10
_ACCENT = QColor("#2f7fe0")


class LayoutItem(QGraphicsItem):
    """A movable, resizable page object (figure / table / text)."""

    HANDLE = 14.0

    def __init__(self, kind: str, w: float, h: float, *, pixmap=None,
                 text="", font_size=14.0, bold=False, frame=None):
        super().__init__()
        self.kind = kind
        self._rect = QRectF(0, 0, w, h)
        self._pixmap: Optional[QPixmap] = pixmap
        self.text = text
        self.font_size = font_size
        self.bold = bold
        self.frame = frame
        self._resizing = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

    # geometry ---------------------------------------------------------------
    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-1, -1, 1, 1)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self._rect
        if self.kind == "figure" and self._pixmap is not None:
            painter.drawPixmap(r.toRect(), self._pixmap)
        elif self.kind == "table" and self._pixmap is not None:
            painter.drawPixmap(r.toRect(), self._pixmap)
        elif self.kind == "text":
            painter.setPen(QPen(QColor("#1a2230")))
            font = QFont("Segoe UI", int(self.font_size))
            font.setBold(self.bold)
            painter.setFont(font)
            painter.drawText(r.adjusted(2, 2, -2, -2),
                             Qt.AlignLeft | Qt.TextWordWrap, self.text)
        # frame + selection
        if self.isSelected():
            painter.setPen(QPen(_ACCENT, 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r)
            painter.setBrush(QBrush(_ACCENT))
            painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(r.right() - self.HANDLE, r.bottom() - self.HANDLE,
                                    self.HANDLE, self.HANDLE))
        else:
            painter.setPen(QPen(QColor("#c4cede"), 0.6))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r)

    # interaction ------------------------------------------------------------
    def _on_handle(self, pos: QPointF) -> bool:
        return (pos.x() >= self._rect.right() - self.HANDLE
                and pos.y() >= self._rect.bottom() - self.HANDLE)

    def mousePressEvent(self, event):
        if self._on_handle(event.pos()):
            self._resizing = True
            self.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            self.prepareGeometryChange()
            self._rect.setRight(max(40.0, event.pos().x()))
            self._rect.setBottom(max(30.0, event.pos().y()))
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self.prepareGeometryChange()
            self._rect.setWidth(round(self._rect.width() / _GRID) * _GRID)
            self._rect.setHeight(round(self._rect.height() / _GRID) * _GRID)
            self.update()
            event.accept()
            return
        # snap position to grid
        p = self.pos()
        self.setPos(round(p.x() / _GRID) * _GRID, round(p.y() / _GRID) * _GRID)
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        self.setCursor(Qt.SizeFDiagCursor if self._on_handle(event.pos())
                       else Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def to_model(self):
        x, y = self.pos().x(), self.pos().y()
        w, h = self._rect.width(), self._rect.height()
        if self.kind == "figure":
            return L.FigureItem(x, y, w, h, self._figure_png or b"")
        if self.kind == "table":
            return L.TableItem(x, y, w, h, self.frame)
        return L.TextItem(x, y, w, h, self.text, self.font_size, self.bold)

    _figure_png: bytes = b""


class LayoutEditor(QDialog):
    """The layout page dialog."""

    def __init__(self, graphs, tables, *, parent=None,
                 ask_save_path=None, default_title=""):
        super().__init__(parent)
        self.setWindowTitle("Layout Page")
        self.resize(920, 760)
        self._graphs = list(graphs)   # [(title, png_bytes)]
        self._tables = list(tables)   # [(name, frame)]
        self._ask_save_path = ask_save_path

        outer = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.cb_page = QComboBox()
        self.cb_page.addItems(list(L.PAGE_SIZES.keys()))
        self.cb_page.currentTextChanged.connect(self._set_page)
        bar.addWidget(self.cb_page)
        bar.addWidget(self._menu_button("Add Figure", self._figure_menu))
        bar.addWidget(self._menu_button("Add Table", self._table_menu))
        bar.addWidget(self._button("Add Text", self._add_text))
        bar.addWidget(self._button("Auto Arrange", self._auto_arrange))
        bar.addWidget(self._button("Delete", self._delete_selected))
        bar.addStretch(1)
        bar.addWidget(self._button("Export PDF…", lambda: self._export("pdf")))
        bar.addWidget(self._button("Export PNG…", lambda: self._export("png")))
        outer.addLayout(bar)

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setBackgroundBrush(QBrush(QColor("#e9edf3")))
        outer.addWidget(self.view)

        self._page_name = "A4 Portrait"
        self._page_rect_item = None
        self._set_page("A4 Portrait")
        if default_title:
            self._add_text_item(default_title, font_size=20, bold=True,
                                x=40, y=28, w=self._page_w - 80, h=32)

    # scaffolding ------------------------------------------------------------
    def _button(self, text, slot):
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    def _menu_button(self, text, builder):
        b = QToolButton()
        b.setText(text)
        b.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(b)
        menu.aboutToShow.connect(lambda m=menu, f=builder: f(m))
        b.setMenu(menu)
        return b

    def _set_page(self, name):
        self._page_name = name
        w, h = L.PAGE_SIZES[name]
        self._page_w, self._page_h = w, h
        self.scene.setSceneRect(-30, -30, w + 60, h + 60)
        if self._page_rect_item is not None:
            self.scene.removeItem(self._page_rect_item)
        self._page_rect_item = self.scene.addRect(
            0, 0, w, h, QPen(QColor("#c4cede")), QBrush(QColor("#ffffff")))
        self._page_rect_item.setZValue(-100)

    # add items --------------------------------------------------------------
    def _figure_menu(self, menu: QMenu):
        menu.clear()
        if not self._graphs:
            menu.addAction("(no open graphs)").setEnabled(False)
        for i, (title, png) in enumerate(self._graphs):
            menu.addAction(title, lambda p=png, t=title: self._add_figure(p, t))

    def _table_menu(self, menu: QMenu):
        menu.clear()
        if not self._tables:
            menu.addAction("(no tables)").setEnabled(False)
        for name, frame in self._tables:
            menu.addAction(name, lambda f=frame: self._add_table(f))

    def _add_item(self, item, x=60, y=60, w=260, h=190):
        item.setPos(x, y)
        item.setZValue(len(self.scene.items()))
        self.scene.addItem(item)
        self.scene.clearSelection()
        item.setSelected(True)
        return item

    def _add_figure(self, png: bytes, title=""):
        pm = QPixmap()
        pm.loadFromData(png, "PNG")
        item = LayoutItem("figure", 260, 190, pixmap=pm)
        item._figure_png = png
        self._add_item(item)

    def _add_table(self, frame: pd.DataFrame):
        item = LayoutItem("table", 260, 150, pixmap=_table_pixmap(frame), frame=frame)
        self._add_item(item, w=260, h=150)

    def _add_text(self):
        text, ok = QInputDialog.getText(self, "Add Text", "Text:")
        if ok and text.strip():
            self._add_text_item(text.strip())

    def _add_text_item(self, text, *, font_size=14, bold=False, x=60, y=60, w=300, h=40):
        item = LayoutItem("text", w, h, text=text, font_size=font_size, bold=bold)
        self._add_item(item, x=x, y=y, w=w, h=h)

    def prefill(self):
        """Drop every open figure and table onto the page, tidily arranged."""
        for _title, png in self._graphs:
            self._add_figure(png)
        for _name, frame in self._tables:
            self._add_table(frame)
        self._auto_arrange()

    def _delete_selected(self):
        for item in self.scene.selectedItems():
            self.scene.removeItem(item)

    def _auto_arrange(self):
        movable = [it for it in self.scene.items() if isinstance(it, LayoutItem)
                   and it.kind != "text"]
        page = L.LayoutPage(page=self._page_name)
        blanks = []
        for it in movable:
            blanks.append(it.to_model())
        for it in movable:
            self.scene.removeItem(it)
        L.auto_grid(page, blanks, title="")
        for m in page.items:
            self._place_model(m)

    def _place_model(self, m):
        if isinstance(m, L.FigureItem):
            self._add_figure(m.png)
        elif isinstance(m, L.TableItem):
            self._add_table(m.frame)
        else:
            self._add_text_item(m.text, font_size=m.font_size, bold=m.bold)
        item = self.scene.selectedItems()[0]
        item.setPos(m.x, m.y)
        item.prepareGeometryChange()
        item._rect = QRectF(0, 0, m.w, m.h)
        if item.kind == "table" and item.frame is not None:
            item._pixmap = _table_pixmap(item.frame)
        item.update()

    # export -----------------------------------------------------------------
    def build_page(self) -> L.LayoutPage:
        page = L.LayoutPage(page=self._page_name)
        items = [it for it in self.scene.items() if isinstance(it, LayoutItem)]
        for it in sorted(items, key=lambda i: i.zValue()):
            page.add(it.to_model())
        return page

    def _export(self, fmt: str):
        page = self.build_page()
        if not page.items:
            return
        path = None
        if callable(self._ask_save_path):
            path = self._ask_save_path(
                f"Export Layout as {fmt.upper()}", f"layout.{fmt}",
                f"{fmt.upper()} (*.{fmt})")
        if not path:
            return
        try:
            if fmt == "pdf":
                L.render_pdf(page, path)
            else:
                L.render_png(page, path)
            self._saved_path = path
        except Exception:
            logger.debug("layout export failed", exc_info=True)


def _table_pixmap(frame: pd.DataFrame, max_rows: int = 12) -> QPixmap:
    """Render a dataframe to a QPixmap via the pure PNG table renderer."""
    from matplotlib.figure import Figure

    shown = frame.head(max_rows)
    fig = Figure(figsize=(3.2, min(3.2, 0.3 + 0.22 * (len(shown) + 1))), dpi=110)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    data = [[str(c) for c in shown.columns]]
    data += [[L._fmt(v) for v in row] for _, row in shown.iterrows()]
    table = ax.table(cellText=data[1:], colLabels=data[0], loc="upper left",
                     cellLoc="left", bbox=[0, 0, 1, 1])
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    for (r, _c), cell in table.get_celld().items():
        cell.set_edgecolor("#e2e7ee")
        if r == 0:
            cell.set_facecolor("#f6f8fb")
            cell.set_text_props(fontweight="bold")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    pm = QPixmap()
    pm.loadFromData(buf.getvalue(), "PNG")
    return pm
