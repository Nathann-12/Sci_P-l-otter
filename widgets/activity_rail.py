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
    (จากการคลิกหรือเรียก ``set_active``) จะส่งสัญญาณ ``activity_changed``;
    คลิกปุ่มที่ active อยู่ซ้ำ → ``activity_toggled`` (ให้ shell ใช้ยุบ/กางแผง)
    """

    activity_changed = Signal(str)
    activity_toggled = Signal(str)

    #: ขนาดไอคอนของปุ่มกิจกรรม (ดูพอดีกับปุ่มสูง ~56px)
    ICON_SIZE = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ActivityRail")

        self._order: List[str] = []
        self._buttons: Dict[str, QToolButton] = {}
        self._current: Optional[str] = None

        # กลุ่มปุ่มแบบ NON-exclusive แล้วบังคับ single-selection เองใน set_active
        # เหตุผล: exclusive group บน Windows native จะ "กลืน" สัญญาณ clicked ของ
        # ปุ่มที่ checked อยู่ ทำให้ re-click ตัว active ไม่เกิด event → พับแผงไม่ได้.
        # ปุ่มแบบไม่ exclusive จะ emit clicked ทุกครั้งที่คลิกจริง ทุกแพลตฟอร์ม
        self._group = QButtonGroup(self)
        self._group.setExclusive(False)

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
        button.setToolTip(f"{label} • คลิกซ้ำเพื่อพับ/กางแผง")
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        if icon is not None:
            button.setIcon(icon if isinstance(icon, QIcon) else QIcon(icon))

        button.clicked.connect(lambda _checked=False, aid=activity_id: self._on_button_clicked(aid))

        self._group.addButton(button)
        self._layout.addWidget(button)
        self._buttons[activity_id] = button
        self._order.append(activity_id)

        # ปุ่มแรกที่เพิ่มจะกลายเป็น active โดยอัตโนมัติ
        if self._current is None:
            self.set_active(activity_id)

        return button

    def _on_button_clicked(self, activity_id: str) -> None:
        """คลิกกิจกรรมใหม่ = สลับ; คลิกตัวที่ active อยู่ซ้ำ = toggle แผง

        กลุ่มปุ่มไม่ exclusive → การคลิกจริงจะ toggle สถานะปุ่มก่อนถึงตรงนี้เสมอ
        เราจึงบังคับสถานะให้ถูกต้องเองที่นี่ (ตัว active ต้อง checked เสมอ)
        """
        if activity_id == self._current:
            # non-exclusive ทำให้คลิกแล้วปุ่มถูก uncheck — ดันกลับให้ active คง highlight
            button = self._buttons.get(activity_id)
            if button is not None:
                button.setChecked(True)
            self.activity_toggled.emit(activity_id)
            return
        self.set_active(activity_id)

    def set_active(self, activity_id: str) -> None:
        """ตั้งให้กิจกรรมที่ระบุเป็น active และส่งสัญญาณถ้ามีการเปลี่ยนแปลง"""
        if activity_id not in self._buttons:
            return

        # บังคับ single-selection เอง: เฉพาะตัว active ที่ checked
        for aid, btn in self._buttons.items():
            btn.setChecked(aid == activity_id)

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
