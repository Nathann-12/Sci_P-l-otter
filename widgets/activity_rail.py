# widgets/activity_rail.py
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ActivityRail(QWidget):
    """แถบกิจกรรมแนวตั้ง (activity bar) — ปุ่มไอคอน/ข้อความแบบ checkable

    มีปุ่มได้หลายปุ่ม แต่เลือก active ได้ทีละปุ่มเดียว เมื่อเปลี่ยนปุ่มที่ active
    (จากการคลิกหรือเรียก ``set_active``) จะส่งสัญญาณ ``activity_changed``
    """

    activity_changed = Signal(str)

    #: ขนาดไอคอนของปุ่มกิจกรรม (ดูพอดีกับปุ่มสูง ~56px)
    ICON_SIZE = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ActivityRail")

        self._order: List[str] = []
        self._buttons: Dict[str, QToolButton] = {}
        self._current: Optional[str] = None

        # กลุ่มปุ่มแบบ exclusive เพื่อให้เลือกได้ทีละปุ่ม
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(2, 4, 2, 4)
        self._layout.setSpacing(2)
        self._layout.setAlignment(Qt.AlignTop)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def add_activity(self, activity_id: str, label: str, icon=None) -> QToolButton:
        """เพิ่มกิจกรรมหนึ่งรายการลงในแถบ คืนค่าปุ่มที่สร้าง

        ถ้า ``activity_id`` ซ้ำกับของเดิม จะคืนปุ่มเดิมโดยไม่สร้างซ้ำ
        """
        if activity_id in self._buttons:
            return self._buttons[activity_id]

        button = QToolButton(self)
        button.setObjectName(f"ActivityButton_{activity_id}")
        button.setText(label)
        button.setCheckable(True)
        button.setToolTip(label)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        if icon is not None:
            button.setIcon(icon if isinstance(icon, QIcon) else QIcon(icon))

        button.clicked.connect(lambda _checked=False, aid=activity_id: self.set_active(aid))

        self._group.addButton(button)
        self._layout.addWidget(button)
        self._buttons[activity_id] = button
        self._order.append(activity_id)

        # ปุ่มแรกที่เพิ่มจะกลายเป็น active โดยอัตโนมัติ
        if self._current is None:
            self.set_active(activity_id)

        return button

    def set_active(self, activity_id: str) -> None:
        """ตั้งให้กิจกรรมที่ระบุเป็น active และส่งสัญญาณถ้ามีการเปลี่ยนแปลง"""
        if activity_id not in self._buttons:
            return

        button = self._buttons[activity_id]
        if not button.isChecked():
            button.setChecked(True)

        if activity_id != self._current:
            self._current = activity_id
            self.activity_changed.emit(activity_id)

    def current_activity(self) -> Optional[str]:
        """คืนค่า id ของกิจกรรมที่ active อยู่ (หรือ None ถ้ายังไม่มี)"""
        return self._current

    def activity_ids(self) -> List[str]:
        """คืนรายการ id ตามลำดับที่เพิ่มเข้ามา"""
        return list(self._order)

    def button_for(self, activity_id: str) -> Optional[QToolButton]:
        """คืนปุ่มของกิจกรรมที่ระบุ (หรือ None ถ้าไม่มี)"""
        return self._buttons.get(activity_id)
