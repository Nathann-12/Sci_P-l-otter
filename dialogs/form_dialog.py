# dialogs/form_dialog.py
"""A single consolidated form dialog to replace chains of QInputDialog popups.

Instead of firing 3-4 modal prompts in a row (kind → fs → cutoff low → cutoff
high), an operation describes all its inputs once and gets one clean dialog
with OK/Cancel. Fields can be shown conditionally on another field's value
(e.g. the high-cutoff only appears for band filters).

Usage::

    fields = [
        {"name": "method", "label": "วิธี", "kind": "choice",
         "options": ["mean", "median", "value"], "default": "mean"},
        {"name": "value", "label": "ค่า", "kind": "float", "default": 0.0,
         "show_if": ("method", "value")},
    ]
    result = run_form(parent, "เติมค่าที่หาย", fields, description="...")
    if result is None:   # cancelled
        return
    method = result["method"]
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

_BIG = 1e12


class FormDialog(QDialog):
    """Build a form from a field spec; :meth:`values` returns the entered dict."""

    def __init__(self, title: str, fields: Sequence[Dict[str, Any]],
                 description: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._specs = [dict(f) for f in fields]
        self._widgets: Dict[str, QWidget] = {}
        self._rows: Dict[str, tuple] = {}  # name -> (label_widget, field_widget)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(10)

        if description:
            lbl = QLabel(description)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: #aab0b6;")
            outer.addWidget(lbl)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setSpacing(8)
        outer.addLayout(form)

        for spec in self._specs:
            w = self._make_widget(spec)
            self._widgets[spec["name"]] = w
            label = QLabel(spec.get("label", spec["name"]))
            form.addRow(label, w)
            self._rows[spec["name"]] = (label, w)

        # live conditional visibility
        for spec in self._specs:
            ctrl = spec.get("show_if")
            if ctrl:
                ctrl_name = ctrl[0]
                ctrl_w = self._widgets.get(ctrl_name)
                if isinstance(ctrl_w, QComboBox):
                    ctrl_w.currentTextChanged.connect(self._refresh_visibility)
                elif isinstance(ctrl_w, QCheckBox):
                    ctrl_w.toggled.connect(self._refresh_visibility)
        self._refresh_visibility()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.setMinimumWidth(340)

    # ------------------------------------------------------------------ build
    def _make_widget(self, spec: Dict[str, Any]) -> QWidget:
        kind = spec.get("kind", "text")
        default = spec.get("default")
        if kind == "choice":
            w = QComboBox()
            options = [str(o) for o in spec.get("options", [])]
            w.addItems(options)
            if default is not None and str(default) in options:
                w.setCurrentText(str(default))
            return w
        if kind == "multi_choice":
            w = QListWidget()
            w.setSelectionMode(QAbstractItemView.ExtendedSelection)
            w.addItems([str(o) for o in spec.get("options", [])])
            defaults = default if isinstance(default, (list, tuple, set)) else [default]
            wanted = {str(value) for value in defaults if value is not None}
            for index in range(w.count()):
                item = w.item(index)
                item.setSelected(item.text() in wanted)
            w.setMinimumHeight(int(spec.get("height", 110)))
            tooltip = spec.get("help") or spec.get("placeholder")
            if tooltip:
                w.setToolTip(str(tooltip))
            return w
        if kind == "int":
            w = QSpinBox()
            w.setRange(int(spec.get("min", -1_000_000_000)),
                       int(spec.get("max", 1_000_000_000)))
            w.setSingleStep(int(spec.get("step", 1)))
            if default is not None:
                w.setValue(int(default))
            return w
        if kind == "float":
            w = QDoubleSpinBox()
            w.setDecimals(int(spec.get("decimals", 4)))
            w.setRange(float(spec.get("min", -_BIG)), float(spec.get("max", _BIG)))
            w.setSingleStep(float(spec.get("step", 1.0)))
            if default is not None:
                w.setValue(float(default))
            return w
        if kind == "bool":
            w = QCheckBox(spec.get("checkbox_text", ""))
            w.setChecked(bool(default))
            return w
        w = QLineEdit()
        if default is not None:
            w.setText(str(default))
        return w

    def _refresh_visibility(self, *_):
        for spec in self._specs:
            ctrl = spec.get("show_if")
            if not ctrl:
                continue
            ctrl_name, wanted = ctrl[0], ctrl[1]
            wanted_set = set(wanted) if isinstance(wanted, (list, tuple, set)) else {wanted}
            cur = self._current_value(ctrl_name)
            visible = str(cur) in {str(x) for x in wanted_set}
            label, field = self._rows[spec["name"]]
            label.setVisible(visible)
            field.setVisible(visible)

    # ------------------------------------------------------------------ read
    def _current_value(self, name: str) -> Any:
        w = self._widgets.get(name)
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, QSpinBox):
            return w.value()
        if isinstance(w, QDoubleSpinBox):
            return w.value()
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QListWidget):
            return [item.text() for item in w.selectedItems()]
        if isinstance(w, QLineEdit):
            return w.text()
        return None

    def values(self) -> Dict[str, Any]:
        """Entered values keyed by field name (hidden fields still return their
        current value, so callers can ignore them)."""
        return {name: self._current_value(name) for name in self._widgets}


def run_form(parent, title: str, fields: Sequence[Dict[str, Any]],
             description: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Show the form modally; return the values dict, or None if cancelled."""
    dlg = FormDialog(title, fields, description=description, parent=parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()
