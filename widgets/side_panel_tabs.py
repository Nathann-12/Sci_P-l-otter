from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QWidget,
)


class _VerticalSideTabBar(QTabBar):
    TAB_WIDTH = 24
    TAB_HEIGHT = 158

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_index = -1
        self.setMouseTracking(True)

    def tabSizeHint(self, index: int) -> QSize:
        return QSize(self.TAB_WIDTH, self.TAB_HEIGHT)

    def mouseMoveEvent(self, event) -> None:
        self._hover_index = self.tabAt(event.pos())
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_index = -1
        self.update()
        super().leaveEvent(event)

    @staticmethod
    def _mix(source: QColor, target: QColor, amount: float) -> QColor:
        amount = max(0.0, min(1.0, amount))
        return QColor(
            round(source.red() + (target.red() - source.red()) * amount),
            round(source.green() + (target.green() - source.green()) * amount),
            round(source.blue() + (target.blue() - source.blue()) * amount),
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        palette = self.palette()
        window = palette.color(QPalette.Window)
        surface = palette.color(QPalette.Button)
        text = palette.color(QPalette.WindowText)
        muted = palette.color(QPalette.PlaceholderText)
        accent = palette.color(QPalette.Highlight)
        border = self._mix(window, text, 0.16)
        painter.fillRect(self.rect(), window)

        for index in range(self.count()):
            rect = self.tabRect(index)
            if not rect.isValid() or not rect.intersects(event.rect()):
                continue

            selected = index == self.currentIndex()
            hovered = index == self._hover_index
            bg = (
                self._mix(surface, accent, 0.18)
                if selected
                else self._mix(surface, accent, 0.08) if hovered else surface
            )
            fg = text if selected else muted
            painter.fillRect(rect, bg)
            painter.setPen(border)
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())

            if selected:
                painter.fillRect(QRect(rect.left(), rect.top(), 2, rect.height()), accent)

            font = QFont(self.font())
            if font.pointSizeF() > 0:
                font.setPointSizeF(max(7.0, font.pointSizeF() * 0.85))
            font.setWeight(QFont.DemiBold if selected else QFont.Medium)
            painter.setFont(font)
            painter.setPen(fg)

            painter.save()
            painter.translate(rect.center())
            painter.rotate(-90)
            text_rect = QRect(
                -rect.height() // 2,
                -rect.width() // 2,
                rect.height(),
                rect.width(),
            )
            painter.drawText(text_rect, Qt.AlignCenter, self.tabText(index))
            painter.restore()


class SidePanelTabs(QWidget):
    """Collapsible vertical side tabs for project/log/assistant panels.

    The tab strip stays visible while the content pane can be collapsed, matching
    Origin-style parked side panels. Clicking a collapsed tab opens it; clicking
    the active open tab parks it back to the side strip.
    """

    COLLAPSED_WIDTH = _VerticalSideTabBar.TAB_WIDTH
    EXPANDED_WIDTH = 240

    panel_changed = Signal(int)
    panel_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanelTabs")

        self._titles: List[str] = []
        self._widgets: List[QWidget] = []
        self._title_to_index: Dict[str, int] = {}
        self._current_index = -1
        self._collapsed = True

        self.tab_bar = _VerticalSideTabBar(self)
        self.tab_bar.setObjectName("SidePanelTabBar")
        self.tab_bar.setShape(QTabBar.RoundedWest)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setMovable(False)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.tab_bar.tabBarClicked.connect(self._on_tab_clicked)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName("SidePanelStack")
        self.stack.setMinimumWidth(200)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tab_bar)
        layout.addWidget(self.stack, 1)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.collapse()

    def add_panel(self, title: str, widget: QWidget) -> int:
        if title in self._title_to_index:
            return self._title_to_index[title]

        index = self.stack.addWidget(widget)
        self.tab_bar.addTab(title)
        self.tab_bar.setTabToolTip(index, title)
        self._titles.append(title)
        self._widgets.append(widget)
        self._title_to_index[title] = index
        self._sync_tab_bar_min_height()

        if self._current_index < 0:
            self.set_current_index(index)

        self.show()
        return index

    def set_current_index(self, index: int) -> None:
        if index < 0 or index >= self.stack.count():
            return
        self._current_index = index
        self.tab_bar.setCurrentIndex(index)
        self.stack.setCurrentIndex(index)
        self.panel_changed.emit(index)

    def set_tab_text(self, index: int, title: str) -> None:
        if index < 0 or index >= len(self._titles):
            return
        old_title = self._titles[index]
        self._titles[index] = title
        self._title_to_index.pop(old_title, None)
        self._title_to_index[title] = index
        self.tab_bar.setTabText(index, title)
        self.tab_bar.setTabToolTip(index, title)

    def index_of_title(self, title: str) -> int:
        return self._title_to_index.get(title, -1)

    def widget(self, index: int) -> Optional[QWidget]:
        if index < 0 or index >= self.stack.count():
            return None
        return self.stack.widget(index)

    def count(self) -> int:
        return self.stack.count()

    def is_collapsed(self) -> bool:
        return self._collapsed

    def expand(self) -> None:
        if self.stack.count() == 0:
            return
        self._collapsed = False
        self.stack.show()
        self.setMinimumWidth(self.EXPANDED_WIDTH)
        self.setMaximumWidth(self.EXPANDED_WIDTH)
        self.panel_toggled.emit(False)

    def collapse(self) -> None:
        self._collapsed = True
        self.stack.hide()
        self.setMinimumWidth(self.COLLAPSED_WIDTH)
        self.setMaximumWidth(self.COLLAPSED_WIDTH)
        self.panel_toggled.emit(True)

    def toggle_current(self) -> None:
        if self._collapsed:
            self.expand()
        else:
            self.collapse()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.height() > self.tab_bar.minimumHeight():
            self.tab_bar.setFixedHeight(self.height())

    def _on_tab_clicked(self, index: int) -> None:
        if index < 0:
            return
        clicked_current = index == self._current_index
        self.set_current_index(index)
        if clicked_current and not self._collapsed:
            self.collapse()
        else:
            self.expand()

    def _sync_tab_bar_min_height(self) -> None:
        min_height = min(max(1, self.tab_bar.count()) * _VerticalSideTabBar.TAB_HEIGHT, 520)
        self.tab_bar.setMinimumHeight(min_height)
