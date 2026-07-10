# widgets/activity_rail.py
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QSizePolicy,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ActivityRail(QWidget):
    """Scalable module rail for specialty contexts.

    The rail is intentionally narrow, but it is not a throwaway toolbar. It has
    a small brand header, a section label, and a scrollable module list so future
    specialty modules can be added without redesigning the shell.
    """

    activity_changed = Signal(str)
    activity_toggled = Signal(str)

    ICON_SIZE = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ActivityRail")

        self._order: List[str] = []
        self._buttons: Dict[str, QToolButton] = {}
        self._current: Optional[str] = None

        # Non-exclusive group: Windows native styles can swallow clicks on an
        # already-checked exclusive button. We enforce single-selection manually
        # so re-clicking the active item can collapse/restore the context panel.
        self._group = QButtonGroup(self)
        self._group.setExclusive(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 8, 6, 8)
        root.setSpacing(8)

        self.brand = QLabel("SP", self)
        self.brand.setObjectName("ActivityRailBrand")
        self.brand.setAlignment(Qt.AlignCenter)
        root.addWidget(self.brand)

        self.section_label = QLabel("MODULES", self)
        self.section_label.setObjectName("ActivityRailSection")
        self.section_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.section_label)

        self.separator = QFrame(self)
        self.separator.setObjectName("ActivityRailSeparator")
        self.separator.setFrameShape(QFrame.HLine)
        root.addWidget(self.separator)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("ActivityRailScroll")
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._button_pane = QWidget(self.scroll)
        self._button_pane.setObjectName("ActivityRailButtonPane")
        self._layout = QVBoxLayout(self._button_pane)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self._button_pane)
        root.addWidget(self.scroll, 1)

        self.footer_separator = QFrame(self)
        self.footer_separator.setObjectName("ActivityRailFooterSeparator")
        self.footer_separator.setFrameShape(QFrame.HLine)
        root.addWidget(self.footer_separator)

        self.footer_hint = QLabel("+", self)
        self.footer_hint.setObjectName("ActivityRailFutureSlot")
        self.footer_hint.setAlignment(Qt.AlignCenter)
        self.footer_hint.setToolTip("Reserved space for future modules/plugins")
        root.addWidget(self.footer_hint)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def add_activity(self, activity_id: str, label: str, icon=None) -> QToolButton:
        """Add a context module button, returning the created/reused button."""
        if activity_id in self._buttons:
            return self._buttons[activity_id]

        button = QToolButton(self._button_pane)
        button.setObjectName(f"ActivityButton_{activity_id}")
        button.setProperty("activityId", activity_id)
        button.setText(label)
        button.setCheckable(True)
        button.setToolTip(f"{label}\nClick again to collapse/restore the context panel")
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        button.setCursor(Qt.PointingHandCursor)
        if icon is not None:
            button.setIcon(icon if isinstance(icon, QIcon) else QIcon(icon))

        button.clicked.connect(lambda _checked=False, aid=activity_id: self._on_button_clicked(aid))

        self._group.addButton(button)
        self._layout.addWidget(button)
        self._buttons[activity_id] = button
        self._order.append(activity_id)

        if self._current is None:
            self.set_active(activity_id)

        return button

    def _on_button_clicked(self, activity_id: str) -> None:
        if activity_id == self._current:
            button = self._buttons.get(activity_id)
            if button is not None:
                button.setChecked(True)
            self.activity_toggled.emit(activity_id)
            return
        self.set_active(activity_id)

    def set_active(self, activity_id: str) -> None:
        """Set the active module and emit activity_changed when it changes."""
        if activity_id not in self._buttons:
            return

        for aid, button in self._buttons.items():
            button.setChecked(aid == activity_id)

        if activity_id != self._current:
            self._current = activity_id
            self.activity_changed.emit(activity_id)

    def current_activity(self) -> Optional[str]:
        return self._current

    def activity_ids(self) -> List[str]:
        return list(self._order)

    def button_for(self, activity_id: str) -> Optional[QToolButton]:
        return self._buttons.get(activity_id)
