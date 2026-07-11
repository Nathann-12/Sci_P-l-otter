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
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class _ModuleCard(QToolButton):
    """A selectable module card: icon + title + muted subtitle + pin dot.

    Kept a checkable QToolButton (so it still lives in the QButtonGroup) but the
    label content is real child widgets — that gives proper typographic
    hierarchy instead of cramming ``title\\nsubtitle`` into the button text.
    Child labels are transparent to the mouse so a click always hits the card.
    """

    def __init__(self, module_id: str, title: str, subtitle: str,
                 icon: Optional[QIcon], parent=None):
        super().__init__(parent)
        self.setObjectName("ModuleCard")
        self.setProperty("moduleId", module_id)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumHeight(52)

        row = QHBoxLayout(self)
        row.setContentsMargins(11, 8, 10, 8)
        row.setSpacing(11)

        self._icon_label = QLabel(self)
        self._icon_label.setObjectName("ModuleCardIcon")
        self._icon_label.setFixedSize(28, 28)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(self._icon_label, 0)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("ModuleCardTitle")
        self._title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._subtitle_label = QLabel(subtitle, self)
        self._subtitle_label.setObjectName("ModuleCardSubtitle")
        self._subtitle_label.setWordWrap(False)  # one clean line -> uniform cards
        self._subtitle_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        text_col.addWidget(self._title_label)
        text_col.addWidget(self._subtitle_label)
        row.addLayout(text_col, 1)

        self._pin_dot = QLabel("●", self)  # ● shown only when pinned
        self._pin_dot.setObjectName("ModuleCardPin")
        self._pin_dot.setFixedWidth(12)
        self._pin_dot.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self._pin_dot.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._pin_dot.setVisible(False)
        row.addWidget(self._pin_dot, 0)

        self.set_card_icon(icon)

    def set_card_icon(self, icon: Optional[QIcon]) -> None:
        if icon is not None and not icon.isNull():
            self._icon_label.setPixmap(icon.pixmap(20, 20))
        else:
            self._icon_label.clear()

    def set_meta(self, title: str, subtitle: str) -> None:
        self._title_label.setText(title)
        self._subtitle_label.setText(subtitle)

    def set_pinned(self, pinned: bool) -> None:
        self._pin_dot.setVisible(bool(pinned))


class ModulesPanel(QWidget):
    """Text-first gallery for specialty/domain modules.

    Styled to the app's single design system (accent #4F9CF9, surface #23272e,
    border #3a3f44, text #e6e6e6) so it reads as part of SciPlotter rather than
    a bolted-on panel.
    """

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

        # ---- header: eyebrow + title + close ----
        eyebrow = QLabel("SPECIALTY MODULES", self)
        eyebrow.setObjectName("ModulesEyebrow")
        root.addWidget(eyebrow)

        header = QWidget(self)
        header.setObjectName("ModulesHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        # short title (the eyebrow already says SPECIALTY MODULES) so it never
        # clips in a narrow splitter pane
        title = QLabel("Modules", self)
        title.setObjectName("ModulesTitle")
        title.setMinimumWidth(0)
        header_layout.addWidget(title, 1)

        self.close_button = QToolButton(self)
        self.close_button.setObjectName("ModulesCloseButton")
        self.close_button.setText("✕")  # ✕
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setToolTip("Close Modules Gallery")
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(self.close_button, 0, Qt.AlignTop)
        root.addWidget(header)

        intro = QLabel(
            "Domain-specific tools live here so the main toolbar stays focused "
            "on universal plotting and data work.",
            self,
        )
        intro.setObjectName("ModulesIntro")
        intro.setWordWrap(True)
        root.addWidget(intro)

        # ---- search + pin filter on one row ----
        controls = QWidget(self)
        controls.setObjectName("ModulesControls")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("ModulesSearch")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("Search modules…")
        self.search_edit.textChanged.connect(self._apply_filters)
        controls_layout.addWidget(self.search_edit, 1)

        self.pin_filter_button = QPushButton("Pinned", self)
        self.pin_filter_button.setObjectName("ModulesPinnedFilter")
        self.pin_filter_button.setCheckable(True)
        self.pin_filter_button.setCursor(Qt.PointingHandCursor)
        self.pin_filter_button.setToolTip("Show only pinned specialty modules")
        self.pin_filter_button.toggled.connect(self._set_pinned_filter)
        controls_layout.addWidget(self.pin_filter_button, 0)
        root.addWidget(controls)

        # ---- scrollable card list ----
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
        root.addWidget(scroll, 3)

        self._empty_label = QLabel("No modules match this filter.", self)
        self._empty_label.setObjectName("ModulesEmptyLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.hide()
        root.addWidget(self._empty_label)

        # ---- active-module section ----
        active_row = QWidget(self)
        active_row.setObjectName("ModulesActiveRow")
        active_layout = QHBoxLayout(active_row)
        active_layout.setContentsMargins(0, 6, 0, 0)
        active_layout.setSpacing(8)

        self._active_label = QLabel("Select a module", self)
        self._active_label.setObjectName("ModulesActiveLabel")
        active_layout.addWidget(self._active_label, 1)

        self.pin_current_button = QPushButton("Pin", self)
        self.pin_current_button.setObjectName("ModulesPinCurrent")
        self.pin_current_button.setCursor(Qt.PointingHandCursor)
        self.pin_current_button.setToolTip("Pin or unpin the selected module")
        self.pin_current_button.clicked.connect(self.toggle_current_pin)
        active_layout.addWidget(self.pin_current_button, 0)
        root.addWidget(active_row)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("ModulesStack")
        root.addWidget(self._stack, 5)

        self.setStyleSheet(self._build_qss())

    # ------------------------------------------------------------------ style
    @staticmethod
    def _build_qss() -> str:
        return """
            #ModulesPanel {
                background: #1e2126;
            }
            #ModulesEyebrow {
                color: #4F9CF9; font-size: 8pt; font-weight: 700;
                letter-spacing: 1.5px;
            }
            #ModulesTitle {
                color: #f0f3f7; font-size: 13.5pt; font-weight: 700;
            }
            #ModulesIntro {
                color: #8b95a3; font-size: 8.5pt;
            }
            #ModulesActiveLabel {
                color: #c7ced8; font-size: 9pt; font-weight: 600;
            }
            #ModulesEmptyLabel {
                color: #8b95a3; font-size: 9pt; padding: 18px 0;
            }
            #ModulesCloseButton {
                color: #9aa4b2; font-size: 11pt; font-weight: 700;
                border: 1px solid transparent; border-radius: 6px; background: transparent;
            }
            #ModulesCloseButton:hover {
                color: #f0f3f7; background: rgba(248,113,113,0.16);
                border-color: rgba(248,113,113,0.45);
            }
            #ModulesSearch {
                min-height: 30px; color: #e6e6e6;
                background: #23272e; border: 1px solid #3a3f44;
                border-radius: 8px; padding: 4px 10px;
                selection-background-color: #4F9CF9;
            }
            #ModulesSearch:focus {
                border-color: #4F9CF9; background: #262b33;
            }
            #ModulesPinnedFilter, #ModulesPinCurrent {
                min-height: 30px; padding: 4px 14px; font-weight: 600;
                color: #c7ced8; background: #23272e;
                border: 1px solid #3a3f44; border-radius: 8px;
            }
            #ModulesPinnedFilter:hover, #ModulesPinCurrent:hover {
                border-color: #4F9CF9; color: #f0f3f7;
            }
            #ModulesPinnedFilter:checked {
                color: #0f1620; background: #4F9CF9; border-color: #4F9CF9;
            }
            #ModulesCardScroll { background: transparent; }
            #ModulesCardPane { background: transparent; }
            #ModuleCard {
                text-align: left; background: #23272e;
                border: 1px solid #3a3f44; border-radius: 10px;
            }
            #ModuleCard:hover {
                background: #262c34; border-color: #4a5666;
            }
            #ModuleCard:checked {
                background: rgba(79,156,249,0.14); border-color: #4F9CF9;
            }
            #ModuleCardIcon {
                background: transparent; border: none;
            }
            #ModuleCardTitle {
                color: #eef2f7; font-size: 10.5pt; font-weight: 600;
                background: transparent; border: none;
            }
            #ModuleCardSubtitle {
                color: #8b95a3; font-size: 8.5pt;
                background: transparent; border: none;
            }
            #ModuleCard:checked #ModuleCardTitle { color: #ffffff; }
            #ModuleCardPin {
                color: #4F9CF9; font-size: 9pt; background: transparent; border: none;
            }
        """

    # ----------------------------------------------------------------- public
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
            card.set_meta(title, subtitle)
            if icon is not None:
                card.set_card_icon(icon)
        card.set_pinned(module_id in self._pinned)

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
            card.set_pinned(is_pinned)
        self._update_pin_button()
        self._apply_filters()
        if was_pinned != is_pinned:
            self.pin_changed.emit(module_id, is_pinned)

    def toggle_current_pin(self) -> None:
        if self._current is None:
            return
        self.set_module_pinned(self._current, self._current not in self._pinned)

    # ---------------------------------------------------------------- private
    def _set_pinned_filter(self, checked: bool) -> None:
        self._show_pinned_only = bool(checked)
        self._apply_filters()

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
            self.pin_current_button.setText("Pin")
            return
        pinned = self._current in self._pinned
        self.pin_current_button.setText("Unpin" if pinned else "Pin")
