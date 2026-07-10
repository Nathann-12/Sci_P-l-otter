from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class _ModuleCard(QToolButton):
    def __init__(self, module_id: str, title: str, subtitle: str, icon: Optional[QIcon], parent=None):
        super().__init__(parent)
        self.setObjectName(f"ModuleCard_{module_id}")
        self.setProperty("moduleId", module_id)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setText(f"{title}\n{subtitle}")
        if icon is not None:
            self.setIcon(icon)
        self.setMinimumHeight(58)
        self.setMaximumHeight(72)


class ModulesPanel(QWidget):
    """Text-first gallery for specialty/domain modules."""

    module_selected = Signal(str)
    pin_changed = Signal(str, bool)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModulesPanel")
        self._cards: Dict[str, _ModuleCard] = {}
        self._meta: Dict[str, dict[str, str]] = {}
        self._pinned: set[str] = set()
        self._widgets: Dict[str, QWidget] = {}
        self._current: Optional[str] = None
        self._show_pinned_only = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        eyebrow = QLabel("SPECIALTY MODULES", self)
        eyebrow.setObjectName("ModulesEyebrow")
        root.addWidget(eyebrow)

        header = QWidget(self)
        header.setObjectName("ModulesHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title = QLabel("Modules Gallery", self)
        title.setObjectName("ModulesTitle")
        header_layout.addWidget(title, 1)

        self.close_button = QPushButton("Close", self)
        self.close_button.setObjectName("ModulesCloseButton")
        self.close_button.setToolTip("Close Modules Gallery")
        self.close_button.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(self.close_button)
        root.addWidget(header)

        intro = QLabel(
            "Domain-specific tools stay here so the main toolbar remains focused on universal plotting and data work.",
            self,
        )
        intro.setObjectName("ModulesIntro")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("ModulesSearch")
        self.search_edit.setPlaceholderText("Search modules, methods, or domains...")
        self.search_edit.textChanged.connect(self._apply_filters)
        root.addWidget(self.search_edit)

        self.pin_filter_button = QPushButton("Pinned", self)
        self.pin_filter_button.setObjectName("ModulesPinnedFilter")
        self.pin_filter_button.setCheckable(True)
        self.pin_filter_button.setToolTip("Show only pinned specialty modules")
        self.pin_filter_button.toggled.connect(self._set_pinned_filter)

        self.pin_current_button = QPushButton("Pin Current", self)
        self.pin_current_button.setObjectName("ModulesPinCurrent")
        self.pin_current_button.setToolTip("Pin or unpin the selected module")
        self.pin_current_button.clicked.connect(self.toggle_current_pin)

        actions_row = QWidget(self)
        actions_row.setObjectName("ModulesActionsRow")
        actions_layout = QVBoxLayout(actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)
        actions_layout.addWidget(self.pin_filter_button)
        actions_layout.addWidget(self.pin_current_button)
        root.addWidget(actions_row)

        self._card_group = QButtonGroup(self)
        self._card_group.setExclusive(True)

        self._card_pane = QWidget(self)
        self._card_pane.setObjectName("ModulesCardPane")
        self._card_layout = QVBoxLayout(self._card_pane)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(8)
        self._card_layout.setAlignment(Qt.AlignTop)

        scroll = QScrollArea(self)
        scroll.setObjectName("ModulesCardScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self._card_pane)
        root.addWidget(scroll, 0)

        divider = QFrame(self)
        divider.setObjectName("ModulesDivider")
        divider.setFrameShape(QFrame.HLine)
        root.addWidget(divider)

        self._active_label = QLabel("Select a module", self)
        self._active_label.setObjectName("ModulesActiveLabel")
        root.addWidget(self._active_label)

        self._empty_label = QLabel("No modules match this filter.", self)
        self._empty_label.setObjectName("ModulesEmptyLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.hide()
        root.addWidget(self._empty_label)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("ModulesStack")
        root.addWidget(self._stack, 1)

        self.setStyleSheet(
            """
            #ModulesPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #111820, stop:0.52 #151b24, stop:1 #0e141b);
            }
            #ModulesEyebrow {
                color: #7dd3fc; font-size: 8pt; font-weight: 700; letter-spacing: 1.4px;
            }
            #ModulesTitle {
                color: #f8fafc; font-size: 15pt; font-weight: 700;
            }
            #ModulesIntro, #ModulesActiveLabel, #ModulesEmptyLabel {
                color: #aab5c2; font-size: 9pt;
            }
            #ModulesSearch {
                min-height: 30px;
                color: #e5eef8;
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                padding: 4px 9px;
                selection-background-color: rgba(45,212,191,0.45);
            }
            #ModulesSearch:focus {
                border-color: rgba(125,211,252,0.70);
                background: rgba(255,255,255,0.095);
            }
            #ModulesPinnedFilter, #ModulesPinCurrent, #ModulesCloseButton {
                min-height: 28px;
                border-radius: 9px;
                padding: 4px 8px;
                color: #dbeafe;
                background: rgba(148,163,184,0.12);
                border: 1px solid rgba(148,163,184,0.24);
            }
            #ModulesPinnedFilter:checked {
                color: #0f172a;
                background: #7dd3fc;
                border-color: #7dd3fc;
            }
            #ModulesCloseButton {
                color: #fee2e2;
                background: rgba(248,113,113,0.12);
                border-color: rgba(248,113,113,0.26);
            }
            #ModulesCloseButton:hover {
                background: rgba(248,113,113,0.22);
                border-color: rgba(248,113,113,0.55);
            }
            #ModulesPinCurrent:hover, #ModulesPinnedFilter:hover {
                border-color: rgba(125,211,252,0.60);
            }
            #ModulesDivider {
                color: rgba(255,255,255,0.10);
                background: rgba(255,255,255,0.10);
                max-height: 1px;
            }
            #ModulesCardScroll {
                background: transparent;
            }
            #ModulesPanel QToolButton {
                text-align: left;
                color: #e5eef8;
                background: rgba(255,255,255,0.055);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                padding: 8px 10px;
            }
            #ModulesPanel QToolButton:hover {
                background: rgba(125,211,252,0.13);
                border-color: rgba(125,211,252,0.45);
            }
            #ModulesPanel QToolButton:checked {
                background: rgba(45,212,191,0.16);
                border-color: rgba(45,212,191,0.65);
            }
            """
        )

    def add_module(
        self,
        module_id: str,
        title: str,
        subtitle: str,
        widget: QWidget,
        icon: Optional[QIcon] = None,
        search_terms: Optional[list[str]] = None,
    ) -> None:
        extra_terms = " ".join(search_terms or [])
        self._meta[module_id] = {
            "title": title,
            "subtitle": subtitle,
            "search": f"{module_id} {title} {subtitle} {extra_terms}".lower(),
        }
        if module_id in self._widgets:
            old = self._widgets[module_id]
            index = self._stack.indexOf(old)
            if index != -1:
                self._stack.removeWidget(old)
                old.setParent(None)
        self._widgets[module_id] = widget
        self._stack.addWidget(widget)

        card = self._cards.get(module_id)
        if card is None:
            card = _ModuleCard(module_id, title, subtitle, icon, self._card_pane)
            card.clicked.connect(lambda _checked=False, mid=module_id: self.show_module(mid))
            self._card_group.addButton(card)
            self._cards[module_id] = card
            self._card_layout.addWidget(card)
        else:
            card.setText(self._card_text(module_id))
            if icon is not None:
                card.setIcon(icon)

        if self._current is None:
            self.show_module(module_id)
        self._apply_filters()

    def show_module(self, module_id: str) -> None:
        widget = self._widgets.get(module_id)
        card = self._cards.get(module_id)
        if widget is None or card is None:
            return
        self._stack.setCurrentWidget(widget)
        card.setChecked(True)
        self._current = module_id
        self._active_label.setText(self._meta.get(module_id, {}).get("title", module_id))
        self._update_pin_button()
        self.module_selected.emit(module_id)

    def module_ids(self) -> list[str]:
        return list(self._widgets)

    def visible_module_ids(self) -> list[str]:
        return [module_id for module_id, card in self._cards.items() if not card.isHidden()]

    def current_module_id(self) -> Optional[str]:
        return self._current

    def module_widget(self, module_id: str) -> Optional[QWidget]:
        return self._widgets.get(module_id)

    def pinned_module_ids(self) -> list[str]:
        return [module_id for module_id in self._widgets if module_id in self._pinned]

    def set_search_text(self, text: str) -> None:
        self.search_edit.setText(text)

    def set_module_pinned(self, module_id: str, pinned: bool) -> None:
        if module_id not in self._widgets:
            return
        was_pinned = module_id in self._pinned
        if pinned:
            self._pinned.add(module_id)
        else:
            self._pinned.discard(module_id)
        is_pinned = module_id in self._pinned
        card = self._cards.get(module_id)
        if card is not None:
            card.setText(self._card_text(module_id))
        self._update_pin_button()
        self._apply_filters()
        if was_pinned != is_pinned:
            self.pin_changed.emit(module_id, is_pinned)

    def toggle_current_pin(self) -> None:
        if self._current is None:
            return
        self.set_module_pinned(self._current, self._current not in self._pinned)

    def _set_pinned_filter(self, checked: bool) -> None:
        self._show_pinned_only = bool(checked)
        self._apply_filters()

    def _card_text(self, module_id: str) -> str:
        meta = self._meta.get(module_id, {})
        title = meta.get("title", module_id)
        subtitle = meta.get("subtitle", "")
        prefix = "* " if module_id in self._pinned else ""
        return f"{prefix}{title}\n{subtitle}"

    def _matches_filter(self, module_id: str, query: str) -> bool:
        if self._show_pinned_only and module_id not in self._pinned:
            return False
        if not query:
            return True
        return query in self._meta.get(module_id, {}).get("search", "")

    def _apply_filters(self) -> None:
        query = self.search_edit.text().strip().lower()
        visible: list[str] = []
        for module_id, card in self._cards.items():
            matched = self._matches_filter(module_id, query)
            card.setVisible(matched)
            if matched:
                visible.append(module_id)

        has_visible = bool(visible)
        self._empty_label.setVisible(not has_visible)
        self._stack.setVisible(has_visible)
        self.pin_current_button.setEnabled(has_visible and self._current in self._widgets)
        if has_visible and self._current not in visible:
            self.show_module(visible[0])
        self._update_pin_button()

    def _update_pin_button(self) -> None:
        if self._current is None:
            self.pin_current_button.setText("Pin Current")
            return
        pinned = self._current in self._pinned
        self.pin_current_button.setText("Unpin Current" if pinned else "Pin Current")
