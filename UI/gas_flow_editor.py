"""Polished LabVIEW-inspired visual flow editor for Gas Live acquisition."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QLocale, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from analysis.gas_flow import (
    DEFAULT_FLOW_WIRING,
    GasFlowConfig,
    GasSensorChannelConfig,
    validate_flow_wiring,
)


class _FlowEdge(QGraphicsPathItem):
    def __init__(
        self,
        source: "_FlowNode",
        target: "_FlowNode",
        on_delete: Callable[["_FlowEdge"], None],
    ) -> None:
        super().__init__()
        self.source = source
        self.target = target
        self._on_delete = on_delete
        self.setZValue(-2)
        source.edges.append(self)
        target.edges.append(self)
        self.update_path()

    def update_path(self) -> None:
        start = self.source.mapToScene(self.source.output_port())
        end = self.target.mapToScene(self.target.input_port())
        distance = max(70.0, abs(end.x() - start.x()) * 0.48)
        path = QPainterPath(start)
        path.cubicTo(
            QPointF(start.x() + distance, start.y()),
            QPointF(end.x() - distance, end.y()),
            end,
        )
        self.setPath(path)
        active = self.source.enabled and self.target.enabled
        color = QColor("#4F9CF9" if active else "#586273")
        pen = QPen(color, 3.0 if active else 2.0)
        pen.setCapStyle(Qt.RoundCap)
        if not active:
            pen.setStyle(Qt.DashLine)
        self.setPen(pen)

    def mouseDoubleClickEvent(self, event) -> None:
        self._on_delete(self)
        event.accept()


class _FlowNode(QGraphicsObject):
    WIDTH = 210.0
    HEIGHT = 112.0

    def __init__(
        self,
        key: str,
        title: str,
        subtitle: str,
        accent: str,
        on_selected: Callable[[str], None],
        on_wire_start: Callable[["_FlowNode", QPointF], None],
        on_wire_move: Callable[[QPointF], None],
        on_wire_finish: Callable[["_FlowNode", QPointF], None],
        *,
        enabled: bool = True,
    ) -> None:
        super().__init__()
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.accent = QColor(accent)
        self.enabled = bool(enabled)
        self.edges: list[_FlowEdge] = []
        self._on_selected = on_selected
        self._on_wire_start = on_wire_start
        self._on_wire_move = on_wire_move
        self._on_wire_finish = on_wire_finish
        self._drawing_wire = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.setCursor(Qt.OpenHandCursor)

    def boundingRect(self) -> QRectF:
        return QRectF(-5.0, -5.0, self.WIDTH + 10.0, self.HEIGHT + 10.0)

    def input_port(self) -> QPointF:
        return QPointF(0.0, self.HEIGHT / 2.0)

    def output_port(self) -> QPointF:
        return QPointF(self.WIDTH, self.HEIGHT / 2.0)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.setOpacity(1.0 if enabled else 0.62)
        self.update()
        for edge in self.edges:
            edge.update_path()

    def set_text(self, title: str, subtitle: str) -> None:
        self.title = str(title)
        self.subtitle = str(subtitle)
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_path()
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        if self.key != "graph" and self._near(event.pos(), self.output_port(), 14.0):
            self._drawing_wire = True
            self._on_wire_start(self, event.scenePos())
            event.accept()
            return
        self._on_selected(self.key)
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drawing_wire:
            self._on_wire_move(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drawing_wire:
            self._drawing_wire = False
            self._on_wire_finish(self, event.scenePos())
            event.accept()
            return
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    @staticmethod
    def _near(first: QPointF, second: QPointF, radius: float) -> bool:
        delta = first - second
        return delta.x() * delta.x() + delta.y() * delta.y() <= radius * radius

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.0, 0.0, self.WIDTH, self.HEIGHT)
        shadow = rect.translated(0.0, 4.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 75))
        painter.drawRoundedRect(shadow, 13.0, 13.0)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#2b3038"))
        gradient.setColorAt(1.0, QColor("#20242b"))
        border = self.accent.lighter(120) if self.isSelected() else QColor("#414a57")
        painter.setPen(QPen(border, 2.2 if self.isSelected() else 1.2))
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 13.0, 13.0)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.accent)
        painter.drawRoundedRect(QRectF(0.0, 0.0, 6.0, self.HEIGHT), 3.0, 3.0)
        painter.drawEllipse(QPointF(27.0, 29.0), 11.0, 11.0)
        painter.setPen(QPen(QColor("#ffffff"), 2.0))
        painter.drawLine(QPointF(22.0, 29.0), QPointF(32.0, 29.0))

        painter.setPen(QColor("#f2f5f8"))
        title_font = QFont(painter.font())
        title_font.setPointSizeF(10.0)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(48.0, 13.0, 148.0, 27.0), Qt.AlignVCenter, self.title)

        painter.setPen(QColor("#9ba6b5"))
        subtitle_font = QFont(painter.font())
        subtitle_font.setPointSizeF(8.1)
        subtitle_font.setBold(False)
        painter.setFont(subtitle_font)
        painter.drawText(
            QRectF(18.0, 49.0, 175.0, 42.0),
            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            self.subtitle,
        )

        status_color = QColor("#41d19a" if self.enabled else "#6f7886")
        painter.setPen(Qt.NoPen)
        painter.setBrush(status_color)
        painter.drawEllipse(QPointF(190.0, 96.0), 4.0, 4.0)

        painter.setBrush(QColor("#14181e"))
        painter.setPen(QPen(self.accent, 2.2))
        if self.key != "source":
            painter.drawEllipse(self.input_port(), 6.0, 6.0)
        if self.key != "graph":
            painter.drawEllipse(self.output_port(), 6.0, 6.0)


class _FlowView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.setObjectName("GasFlowCanvas")
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setFrameShape(QFrame.NoFrame)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor("#171a1f"))
        minor = 24
        major = minor * 4
        left = int(rect.left()) - int(rect.left()) % minor
        top = int(rect.top()) - int(rect.top()) % minor
        painter.setPen(QPen(QColor("#22272f"), 1.0))
        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += minor
        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += minor
        left_major = int(rect.left()) - int(rect.left()) % major
        top_major = int(rect.top()) - int(rect.top()) % major
        painter.setPen(QPen(QColor("#2b323c"), 1.0))
        x = left_major
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += major
        y = top_major
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += major

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        current = self.transform().m11()
        if 0.45 <= current * factor <= 2.2:
            self.scale(factor, factor)

    def fit_flow(self) -> None:
        bounds = self.scene().itemsBoundingRect().adjusted(-60, -60, 60, 60)
        if not bounds.isEmpty():
            self.fitInView(bounds, Qt.KeepAspectRatio)


class GasFlowDesigner(QDialog):
    config_changed = Signal(object)
    wiring_changed = Signal(object)

    PRESETS = {
        "Raw voltage": GasFlowConfig(),
        "Voltage → resistance": GasFlowConfig(voltage_to_resistance=True),
        "Resistance + smoothing": GasFlowConfig(
            voltage_to_resistance=True,
            smoothing=True,
            smoothing_field="resistance_ohm",
            smoothing_window=5,
        ),
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GasFlowDesigner")
        self.setWindowTitle("Visual Acquisition Flow — Gas Sensor")
        self.resize(1180, 680)
        self.setMinimumSize(900, 540)
        self.setModal(False)
        self.setFont(QFont("Segoe UI", 9))
        self._updating = False
        self._fields: list[str] = []
        self._sensor_channels: list[GasSensorChannelConfig] = []
        self._selected_node = ""
        self._wire_source: _FlowNode | None = None
        self._preview_wire: QGraphicsPathItem | None = None
        self._wiring_is_valid = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        splitter = QSplitter(Qt.Horizontal, self)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 1500, 460)
        self.view = _FlowView(self.scene, splitter)
        splitter.addWidget(self.view)
        self.inspector = self._build_inspector(splitter)
        splitter.addWidget(self.inspector)
        splitter.setSizes([820, 360])
        splitter.setStretchFactor(0, 1)
        splitter.setCollapsible(1, False)
        root.addWidget(splitter, 1)

        self._create_flow_items()
        self._connect_controls()
        self.set_config(GasFlowConfig())
        self.reset_layout()

        self.setStyleSheet(
            """
            #GasFlowDesigner { background: #171a1f; color: #e8edf3; }
            #FlowHeader { background: #20242b; border-bottom: 1px solid #343b46; }
            #FlowEyebrow { color: #4F9CF9; font-size: 8pt; font-weight: 700; }
            #FlowTitle { color: #f4f7fa; font-size: 15pt; font-weight: 700; }
            #FlowSubtitle { color: #8f9baa; font-size: 9pt; }
            #FlowStatus {
                color: #aab4c2; background: #2a3038; border: 1px solid #414a57;
                border-radius: 11px; padding: 4px 10px; font-weight: 700;
            }
            #FlowInspector, #FlowInspector QWidget {
                background: #20242b; color: #e8edf3;
            }
            #FlowInspector { border-left: 1px solid #343b46; }
            #InspectorTitle { color: #f0f4f8; font-size: 12pt; font-weight: 700; }
            #InspectorHint { color: #8f9baa; font-size: 8.5pt; }
            #InspectorSection { color: #4F9CF9; font-weight: 700; padding-top: 8px; }
            #GasFlowDesigner QComboBox, #GasFlowDesigner QDoubleSpinBox,
            #GasFlowDesigner QSpinBox, #GasFlowDesigner QLineEdit,
            #GasFlowDesigner QListWidget {
                min-height: 28px; color: #e7ecf2; background: #2a3038;
                border: 1px solid #414a57; border-radius: 7px; padding: 2px 7px;
            }
            #GasFlowDesigner QComboBox:focus, #GasFlowDesigner QDoubleSpinBox:focus,
            #GasFlowDesigner QSpinBox:focus, #GasFlowDesigner QLineEdit:focus,
            #GasFlowDesigner QListWidget:focus { border-color: #4F9CF9; }
            #GasFlowDesigner QPushButton {
                min-height: 29px; color: #e7ecf2; background: #2a3038;
                border: 1px solid #414a57; border-radius: 7px; padding: 3px 11px;
            }
            #GasFlowDesigner QPushButton:hover { border-color: #4F9CF9; }
            #GasFlowDesigner QCheckBox { color: #e1e7ee; spacing: 8px; }
            """
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.view.fit_flow)

    def _build_header(self) -> QWidget:
        header = QWidget(self)
        header.setObjectName("FlowHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 13, 18, 13)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        eyebrow = QLabel("GAS SENSOR  /  VISUAL PROGRAMMING", header)
        eyebrow.setObjectName("FlowEyebrow")
        title = QLabel("Visual Acquisition Flow", header)
        title.setObjectName("FlowTitle")
        subtitle = QLabel("Drag nodes to organize the pipeline; enabled processors run on every sample.", header)
        subtitle.setObjectName("FlowSubtitle")
        titles.addWidget(eyebrow)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles, 1)
        self.status_label = QLabel("●  READY", header)
        self.status_label.setObjectName("FlowStatus")
        layout.addWidget(self.status_label)
        self.fit_button = QPushButton("Fit flow", header)
        self.reset_button = QPushButton("Reset layout", header)
        layout.addWidget(self.fit_button)
        layout.addWidget(self.reset_button)
        return header

    def _build_inspector(self, parent) -> QWidget:
        scroll = QScrollArea(parent)
        scroll.setObjectName("FlowInspector")
        scroll.setMinimumWidth(340)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(17, 17, 17, 17)
        layout.setSpacing(9)
        title = QLabel("Flow inspector", body)
        title.setObjectName("InspectorTitle")
        layout.addWidget(title)
        self.selection_label = QLabel("Pipeline settings", body)
        self.selection_label.setObjectName("InspectorHint")
        self.selection_label.setWordWrap(True)
        layout.addWidget(self.selection_label)

        preset_label = QLabel("PRESET", body)
        preset_label.setObjectName("InspectorSection")
        layout.addWidget(preset_label)
        self.preset_combo = QComboBox(body)
        self.preset_combo.addItems(["Custom", *self.PRESETS])
        layout.addWidget(self.preset_combo)

        palette_label = QLabel("NODE PALETTE", body)
        palette_label.setObjectName("InspectorSection")
        layout.addWidget(palette_label)
        palette_row = QHBoxLayout()
        self.add_divider_button = QPushButton("+ Divider", body)
        self.add_smooth_button = QPushButton("+ Average", body)
        palette_row.addWidget(self.add_divider_button)
        palette_row.addWidget(self.add_smooth_button)
        layout.addLayout(palette_row)
        self.remove_node_button = QPushButton("Remove selected processor", body)
        layout.addWidget(self.remove_node_button)

        divider_label = QLabel("VOLTAGE DIVIDER", body)
        divider_label.setObjectName("InspectorSection")
        layout.addWidget(divider_label)
        self.divider_enabled = QCheckBox("Enable voltage → resistance", body)
        layout.addWidget(self.divider_enabled)
        divider_form = QFormLayout()
        self.voltage_field_combo = QComboBox(body)
        self.voltage_field_combo.setEditable(True)
        self.voltage_field_combo.setPlaceholderText("Auto-detect voltage")
        divider_form.addRow("Voltage field", self.voltage_field_combo)
        self.supply_spin = QDoubleSpinBox(body)
        self.supply_spin.setRange(0.001, 1000.0)
        self.supply_spin.setDecimals(4)
        self.supply_spin.setValue(5.0)
        self.supply_spin.setSuffix(" V")
        self.supply_spin.setLocale(QLocale.c())
        divider_form.addRow("Supply", self.supply_spin)
        self.reference_spin = QDoubleSpinBox(body)
        self.reference_spin.setRange(0.001, 1e12)
        self.reference_spin.setDecimals(3)
        self.reference_spin.setValue(10_000.0)
        self.reference_spin.setSuffix(" Ω")
        self.reference_spin.setLocale(QLocale.c())
        divider_form.addRow("Reference R", self.reference_spin)
        self.topology_combo = QComboBox(body)
        self.topology_combo.addItem("Sensor high-side", "sensor_high")
        self.topology_combo.addItem("Sensor low-side", "sensor_low")
        divider_form.addRow("Topology", self.topology_combo)
        layout.addLayout(divider_form)

        smooth_label = QLabel("MOVING AVERAGE", body)
        smooth_label.setObjectName("InspectorSection")
        layout.addWidget(smooth_label)
        self.smoothing_enabled = QCheckBox("Enable smoothing", body)
        layout.addWidget(self.smoothing_enabled)
        smooth_form = QFormLayout()
        self.smoothing_field_combo = QComboBox(body)
        self.smoothing_field_combo.setEditable(True)
        self.smoothing_field_combo.setPlaceholderText("resistance_ohm")
        smooth_form.addRow("Input field", self.smoothing_field_combo)
        self.window_spin = QSpinBox(body)
        self.window_spin.setRange(1, 10_000)
        self.window_spin.setValue(5)
        self.window_spin.setSuffix(" samples")
        self.window_spin.setLocale(QLocale.c())
        smooth_form.addRow("Window", self.window_spin)
        layout.addLayout(smooth_form)

        sensors_label = QLabel("SENSOR CHANNELS", body)
        sensors_label.setObjectName("InspectorSection")
        layout.addWidget(sensors_label)
        sensors_hint = QLabel(
            "Name and process each physical channel independently. Raw fields are always kept.",
            body,
        )
        sensors_hint.setObjectName("InspectorHint")
        sensors_hint.setWordWrap(True)
        layout.addWidget(sensors_hint)
        self.sensor_list = QListWidget(body)
        self.sensor_list.setMaximumHeight(92)
        layout.addWidget(self.sensor_list)
        sensor_form = QFormLayout()
        self.sensor_source_combo = QComboBox(body)
        self.sensor_source_combo.setEditable(True)
        self.sensor_source_combo.setPlaceholderText("e.g. ai0_voltage_v")
        sensor_form.addRow("Source field", self.sensor_source_combo)
        self.sensor_alias_edit = QLineEdit(body)
        self.sensor_alias_edit.setPlaceholderText("e.g. MQ-2 chamber A")
        sensor_form.addRow("Display name", self.sensor_alias_edit)
        self.sensor_divider_check = QCheckBox("Voltage → resistance", body)
        sensor_form.addRow(self.sensor_divider_check)
        self.sensor_supply_spin = QDoubleSpinBox(body)
        self.sensor_supply_spin.setRange(0.001, 1000.0)
        self.sensor_supply_spin.setDecimals(4)
        self.sensor_supply_spin.setValue(5.0)
        self.sensor_supply_spin.setSuffix(" V")
        self.sensor_supply_spin.setLocale(QLocale.c())
        sensor_form.addRow("Supply", self.sensor_supply_spin)
        self.sensor_reference_spin = QDoubleSpinBox(body)
        self.sensor_reference_spin.setRange(0.001, 1e12)
        self.sensor_reference_spin.setDecimals(3)
        self.sensor_reference_spin.setValue(10_000.0)
        self.sensor_reference_spin.setSuffix(" Ω")
        self.sensor_reference_spin.setLocale(QLocale.c())
        sensor_form.addRow("Reference R", self.sensor_reference_spin)
        self.sensor_topology_combo = QComboBox(body)
        self.sensor_topology_combo.addItem("Sensor high-side", "sensor_high")
        self.sensor_topology_combo.addItem("Sensor low-side", "sensor_low")
        sensor_form.addRow("Topology", self.sensor_topology_combo)
        self.sensor_smoothing_check = QCheckBox("Moving average", body)
        sensor_form.addRow(self.sensor_smoothing_check)
        self.sensor_window_spin = QSpinBox(body)
        self.sensor_window_spin.setRange(1, 10_000)
        self.sensor_window_spin.setValue(5)
        self.sensor_window_spin.setSuffix(" samples")
        sensor_form.addRow("Window", self.sensor_window_spin)
        layout.addLayout(sensor_form)
        sensor_buttons = QHBoxLayout()
        self.sensor_save_button = QPushButton("Add / update", body)
        self.sensor_remove_button = QPushButton("Remove", body)
        sensor_buttons.addWidget(self.sensor_save_button)
        sensor_buttons.addWidget(self.sensor_remove_button)
        layout.addLayout(sensor_buttons)

        wiring_label = QLabel("WIRING", body)
        wiring_label.setObjectName("InspectorSection")
        layout.addWidget(wiring_label)
        wiring_hint = QLabel(
            "Drag from a node's right port to another node's left port. "
            "A new wire replaces the target input; double-click a wire to remove it.",
            body,
        )
        wiring_hint.setObjectName("InspectorHint")
        wiring_hint.setWordWrap(True)
        layout.addWidget(wiring_hint)
        wiring_row = QHBoxLayout()
        self.auto_wire_button = QPushButton("Auto wire", body)
        self.clear_wires_button = QPushButton("Clear wires", body)
        wiring_row.addWidget(self.auto_wire_button)
        wiring_row.addWidget(self.clear_wires_button)
        layout.addLayout(wiring_row)
        self.wiring_status_label = QLabel("Wiring valid", body)
        self.wiring_status_label.setObjectName("InspectorHint")
        self.wiring_status_label.setWordWrap(True)
        layout.addWidget(self.wiring_status_label)

        note = QLabel(
            "Configuration is locked while acquisition is running so the Live Book schema stays stable.",
            body,
        )
        note.setObjectName("InspectorHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        self.settings_body = body
        scroll.setWidget(body)
        return scroll

    def _create_flow_items(self) -> None:
        definitions = (
            ("source", "Acquisition Input", "Serial or NI-DAQmx samples", "#4F9CF9", True),
            ("divider", "Voltage Divider", "Convert voltage into sensor resistance", "#a879ff", False),
            ("smooth", "Moving Average", "Reduce short-term measurement noise", "#ffad57", False),
            ("book", "Live Book", "Store every sample and event", "#41d19a", True),
            ("graph", "Rolling Graph", "Render the latest 2,000 points", "#42c6d9", True),
        )
        self.nodes: dict[str, _FlowNode] = {}
        for key, title, subtitle, accent, enabled in definitions:
            node = _FlowNode(
                key,
                title,
                subtitle,
                accent,
                self._node_selected,
                self._wire_start,
                self._wire_move,
                self._wire_finish,
                enabled=enabled,
            )
            self.nodes[key] = node
            self.scene.addItem(node)
        self.edges: list[_FlowEdge] = []
        self.set_wiring(DEFAULT_FLOW_WIRING, emit=False)

    def _create_edge(self, source: str, target: str) -> _FlowEdge:
        edge = _FlowEdge(self.nodes[source], self.nodes[target], self._delete_edge)
        self.edges.append(edge)
        self.scene.addItem(edge)
        return edge

    def _delete_edge(self, edge: _FlowEdge) -> None:
        if edge not in self.edges:
            return
        self.edges.remove(edge)
        if edge in edge.source.edges:
            edge.source.edges.remove(edge)
        if edge in edge.target.edges:
            edge.target.edges.remove(edge)
        self.scene.removeItem(edge)
        self._validate_visible_wiring(emit=True)

    def wiring(self) -> tuple[tuple[str, str], ...]:
        return tuple((edge.source.key, edge.target.key) for edge in self.edges)

    def set_wiring(self, edges, *, emit: bool = False) -> None:
        normalized = tuple((str(source), str(target)) for source, target in edges)
        if emit:
            validate_flow_wiring(normalized)
        for edge in list(self.edges):
            self._delete_edge_silent(edge)
        for source, target in normalized:
            self._create_edge(source, target)
        self._validate_visible_wiring(emit=emit)

    def _delete_edge_silent(self, edge: _FlowEdge) -> None:
        if edge in self.edges:
            self.edges.remove(edge)
        if edge in edge.source.edges:
            edge.source.edges.remove(edge)
        if edge in edge.target.edges:
            edge.target.edges.remove(edge)
        self.scene.removeItem(edge)

    def wiring_valid(self) -> bool:
        return self._wiring_is_valid

    def _validate_visible_wiring(self, *, emit: bool) -> bool:
        try:
            normalized = validate_flow_wiring(self.wiring())
        except ValueError as exc:
            self._wiring_is_valid = False
            self.wiring_status_label.setText(f"Invalid wiring: {exc}")
            self.wiring_status_label.setStyleSheet("color: #ff8f8f;")
            self.status_label.setText("●  INVALID")
            return False
        self._wiring_is_valid = True
        self.wiring_status_label.setText("Wiring valid · ready to acquire")
        self.wiring_status_label.setStyleSheet("color: #8ef0c5;")
        if not self.settings_body.isEnabled():
            self.status_label.setText("●  RUNNING")
        else:
            self.status_label.setText("●  READY")
        if emit:
            self.wiring_changed.emit(normalized)
        return True

    def _wire_start(self, source: _FlowNode, position: QPointF) -> None:
        self._wire_source = source
        preview = QGraphicsPathItem()
        preview.setZValue(-1)
        pen = QPen(QColor("#8fc4ff"), 2.2, Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        preview.setPen(pen)
        self.scene.addItem(preview)
        self._preview_wire = preview
        self._wire_move(position)

    def _wire_move(self, position: QPointF) -> None:
        if self._wire_source is None or self._preview_wire is None:
            return
        start = self._wire_source.mapToScene(self._wire_source.output_port())
        distance = max(60.0, abs(position.x() - start.x()) * 0.5)
        path = QPainterPath(start)
        path.cubicTo(
            QPointF(start.x() + distance, start.y()),
            QPointF(position.x() - distance, position.y()),
            position,
        )
        self._preview_wire.setPath(path)

    def _wire_finish(self, source: _FlowNode, position: QPointF) -> None:
        if self._preview_wire is not None:
            self.scene.removeItem(self._preview_wire)
        self._preview_wire = None
        self._wire_source = None
        target = self._target_input_at(position)
        if target is None or target is source:
            return
        candidate = [
            edge for edge in self.wiring() if edge[1] != target.key
        ]
        candidate.append((source.key, target.key))
        try:
            validate_flow_wiring(candidate)
        except ValueError as exc:
            self.wiring_status_label.setText(f"Wire rejected: {exc}")
            self.wiring_status_label.setStyleSheet("color: #ffb36b;")
            return
        self.set_wiring(candidate, emit=True)

    def _target_input_at(self, position: QPointF) -> _FlowNode | None:
        for item in self.scene.items(position):
            if not isinstance(item, _FlowNode) or item.key == "source":
                continue
            port = item.mapToScene(item.input_port())
            delta = port - position
            if delta.x() * delta.x() + delta.y() * delta.y() <= 18.0 * 18.0:
                return item
        return None

    def auto_wire(self) -> None:
        config = self.config()
        keys = ["source"]
        if config.voltage_to_resistance or any(
            channel.voltage_to_resistance for channel in config.sensor_channels
        ):
            keys.append("divider")
        if config.smoothing or any(channel.smoothing for channel in config.sensor_channels):
            keys.append("smooth")
        keys.extend(("book", "graph"))
        self.set_wiring(tuple(zip(keys, keys[1:])), emit=True)

    def clear_wires(self) -> None:
        self.set_wiring((), emit=False)

    def _palette_add(self, key: str) -> None:
        if key == "divider":
            self.divider_enabled.setChecked(True)
        elif key == "smooth":
            self.smoothing_enabled.setChecked(True)
        self.nodes[key].setSelected(True)
        self._node_selected(key)
        self.auto_wire()

    def _palette_remove_selected(self) -> None:
        if self._selected_node == "divider":
            self.divider_enabled.setChecked(False)
        elif self._selected_node == "smooth":
            self.smoothing_enabled.setChecked(False)
        else:
            self.selection_label.setText("Select Voltage Divider or Moving Average to remove it.")
            return
        self.auto_wire()

    def _connect_controls(self) -> None:
        self.fit_button.clicked.connect(self.view.fit_flow)
        self.reset_button.clicked.connect(self.reset_layout)
        self.add_divider_button.clicked.connect(lambda: self._palette_add("divider"))
        self.add_smooth_button.clicked.connect(lambda: self._palette_add("smooth"))
        self.remove_node_button.clicked.connect(self._palette_remove_selected)
        self.auto_wire_button.clicked.connect(self.auto_wire)
        self.clear_wires_button.clicked.connect(self.clear_wires)
        self.sensor_save_button.clicked.connect(self._save_sensor_channel)
        self.sensor_remove_button.clicked.connect(self._remove_sensor_channel)
        self.sensor_list.currentRowChanged.connect(self._sensor_channel_selected)
        self.preset_combo.currentTextChanged.connect(self._preset_selected)
        for signal in (
            self.divider_enabled.toggled,
            self.voltage_field_combo.currentTextChanged,
            self.supply_spin.valueChanged,
            self.reference_spin.valueChanged,
            self.topology_combo.currentIndexChanged,
            self.smoothing_enabled.toggled,
            self.smoothing_field_combo.currentTextChanged,
            self.window_spin.valueChanged,
        ):
            signal.connect(self._controls_changed)

    def _node_selected(self, key: str) -> None:
        self._selected_node = key
        labels = {
            "source": "Input node follows the source selected in Gas Sensor Live.",
            "divider": "Voltage divider converts one voltage field to resistance_ohm.",
            "smooth": "Moving average adds a new derived signal column.",
            "book": "Live Book stores every raw and derived sample.",
            "graph": "Signal selector controls the rolling graph output.",
        }
        self.selection_label.setText(labels.get(key, "Pipeline settings"))

    def _preset_selected(self, name: str) -> None:
        if self._updating or name not in self.PRESETS:
            return
        current = self.config()
        preset = self.PRESETS[name]
        config = GasFlowConfig(
            voltage_to_resistance=preset.voltage_to_resistance,
            voltage_field=current.voltage_field,
            supply_voltage_v=current.supply_voltage_v,
            reference_resistance_ohm=current.reference_resistance_ohm,
            divider_topology=current.divider_topology,
            smoothing=preset.smoothing,
            smoothing_field=current.smoothing_field or preset.smoothing_field,
            smoothing_window=current.smoothing_window,
            sensor_channels=current.sensor_channels,
        )
        self.set_config(config)
        self.config_changed.emit(config)

    def _controls_changed(self, *_args) -> None:
        if self._updating:
            return
        blocked = self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText("Custom")
        self.preset_combo.blockSignals(blocked)
        config = self.config()
        self._sync_nodes(config)
        self.config_changed.emit(config)

    def config(self) -> GasFlowConfig:
        return GasFlowConfig(
            voltage_to_resistance=self.divider_enabled.isChecked(),
            voltage_field=self.voltage_field_combo.currentText().strip(),
            supply_voltage_v=self.supply_spin.value(),
            reference_resistance_ohm=self.reference_spin.value(),
            divider_topology=str(self.topology_combo.currentData() or "sensor_high"),
            smoothing=self.smoothing_enabled.isChecked(),
            smoothing_field=self.smoothing_field_combo.currentText().strip(),
            smoothing_window=self.window_spin.value(),
            sensor_channels=tuple(self._sensor_channels),
        ).validated()

    def set_config(self, config: GasFlowConfig) -> None:
        config = config.validated()
        self._updating = True
        try:
            self.divider_enabled.setChecked(config.voltage_to_resistance)
            self.voltage_field_combo.setEditText(config.voltage_field)
            self.supply_spin.setValue(config.supply_voltage_v)
            self.reference_spin.setValue(config.reference_resistance_ohm)
            topology = self.topology_combo.findData(config.divider_topology)
            if topology >= 0:
                self.topology_combo.setCurrentIndex(topology)
            self.smoothing_enabled.setChecked(config.smoothing)
            self.smoothing_field_combo.setEditText(config.smoothing_field)
            self.window_spin.setValue(config.smoothing_window)
            self._sensor_channels = list(config.sensor_channels)
            self._refresh_sensor_list()
            if config.voltage_to_resistance and config.smoothing:
                preset = "Resistance + smoothing"
            elif config.voltage_to_resistance:
                preset = "Voltage → resistance"
            elif not config.smoothing:
                preset = "Raw voltage"
            else:
                preset = "Custom"
            self.preset_combo.setCurrentText(preset)
        finally:
            self._updating = False
        self._sync_nodes(config)

    def _sync_nodes(self, config: GasFlowConfig) -> None:
        self.nodes["divider"].set_enabled(
            config.voltage_to_resistance
            or any(channel.voltage_to_resistance for channel in config.sensor_channels)
        )
        self.nodes["smooth"].set_enabled(
            config.smoothing or any(channel.smoothing for channel in config.sensor_channels)
        )
        topology = "high-side" if config.divider_topology == "sensor_high" else "low-side"
        self.nodes["divider"].set_text(
            "Voltage Divider",
            f"{config.reference_resistance_ohm:g} Ω reference · {topology}",
        )
        self.nodes["smooth"].set_text(
            "Moving Average", f"Window: {config.smoothing_window} samples"
        )

    def _refresh_sensor_list(self) -> None:
        current = self.sensor_list.currentRow()
        blocked = self.sensor_list.blockSignals(True)
        self.sensor_list.clear()
        for channel in self._sensor_channels:
            processors = []
            if channel.voltage_to_resistance:
                processors.append("R")
            if channel.smoothing:
                processors.append(f"MA{channel.smoothing_window}")
            suffix = f"  ·  {' + '.join(processors)}" if processors else ""
            self.sensor_list.addItem(
                f"{channel.alias}  ←  {channel.source_field}{suffix}"
            )
        if self._sensor_channels:
            row = min(max(current, 0), len(self._sensor_channels) - 1)
            self.sensor_list.setCurrentRow(row)
        self.sensor_list.blockSignals(blocked)
        if self._sensor_channels:
            self._sensor_channel_selected(row)

    def _sensor_channel_selected(self, row: int) -> None:
        if not 0 <= row < len(self._sensor_channels):
            return
        channel = self._sensor_channels[row]
        self._updating = True
        try:
            self.sensor_source_combo.setEditText(channel.source_field)
            self.sensor_alias_edit.setText(channel.alias)
            self.sensor_divider_check.setChecked(channel.voltage_to_resistance)
            self.sensor_supply_spin.setValue(channel.supply_voltage_v)
            self.sensor_reference_spin.setValue(channel.reference_resistance_ohm)
            index = self.sensor_topology_combo.findData(channel.divider_topology)
            if index >= 0:
                self.sensor_topology_combo.setCurrentIndex(index)
            self.sensor_smoothing_check.setChecked(channel.smoothing)
            self.sensor_window_spin.setValue(channel.smoothing_window)
        finally:
            self._updating = False

    def _save_sensor_channel(self) -> None:
        source = self.sensor_source_combo.currentText().strip()
        alias = self.sensor_alias_edit.text().strip()
        if not alias and source:
            alias = source.rsplit("/", 1)[-1].replace("_voltage_v", "")
        try:
            channel = GasSensorChannelConfig(
                source_field=source,
                alias=alias,
                voltage_to_resistance=self.sensor_divider_check.isChecked(),
                supply_voltage_v=self.sensor_supply_spin.value(),
                reference_resistance_ohm=self.sensor_reference_spin.value(),
                divider_topology=str(
                    self.sensor_topology_combo.currentData() or "sensor_high"
                ),
                smoothing=self.sensor_smoothing_check.isChecked(),
                smoothing_window=self.sensor_window_spin.value(),
            ).validated()
            row = self.sensor_list.currentRow()
            if not 0 <= row < len(self._sensor_channels):
                row = next(
                    (
                        index for index, existing in enumerate(self._sensor_channels)
                        if existing.source_field.casefold() == source.casefold()
                    ),
                    -1,
                )
            updated = list(self._sensor_channels)
            if row >= 0:
                updated[row] = channel
            else:
                updated.append(channel)
                row = len(updated) - 1
            GasFlowConfig(sensor_channels=tuple(updated)).validated()
        except (TypeError, ValueError) as exc:
            self.selection_label.setText(str(exc))
            return
        self._sensor_channels = updated
        self._refresh_sensor_list()
        self.sensor_list.setCurrentRow(row)
        config = self.config()
        self._sync_nodes(config)
        self.auto_wire()
        self.config_changed.emit(config)

    def _remove_sensor_channel(self) -> None:
        row = self.sensor_list.currentRow()
        if not 0 <= row < len(self._sensor_channels):
            return
        self._sensor_channels.pop(row)
        self._refresh_sensor_list()
        config = self.config()
        self._sync_nodes(config)
        self.auto_wire()
        self.config_changed.emit(config)

    def set_available_fields(self, fields: list[str]) -> None:
        self._fields = [str(field) for field in fields]
        self._replace_combo_items(self.voltage_field_combo, self._fields)
        self._replace_combo_items(self.sensor_source_combo, self._fields)
        smoothing_fields = list(self._fields)
        if "resistance_ohm" not in smoothing_fields:
            smoothing_fields.append("resistance_ohm")
        self._replace_combo_items(self.smoothing_field_combo, smoothing_fields)

    @staticmethod
    def _replace_combo_items(combo: QComboBox, values: list[str]) -> None:
        current = combo.currentText()
        blocked = combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        combo.setEditText(current)
        combo.blockSignals(blocked)

    def set_source(self, transport: str, detail: str = "") -> None:
        if str(transport) == "ni_daq":
            title = "NI-DAQmx Input"
            subtitle = detail or "Hardware-timed analog voltage"
        else:
            title = "Serial Input"
            subtitle = detail or "JSON Lines / CSV records"
        self.nodes["source"].set_text(title, subtitle)

    def set_running(self, running: bool) -> None:
        self.settings_body.setEnabled(not running)
        self.status_label.setText("●  RUNNING" if running else "●  READY")
        self.status_label.setStyleSheet(
            "color: #8ef0c5; border-color: #2c8f6b; background: rgba(65,209,154,0.12);"
            if running else ""
        )

    def reset_layout(self) -> None:
        positions = {
            "source": QPointF(60, 170),
            "divider": QPointF(330, 70),
            "smooth": QPointF(600, 250),
            "book": QPointF(870, 70),
            "graph": QPointF(1140, 250),
        }
        for key, position in positions.items():
            self.nodes[key].setPos(position)
        for edge in self.edges:
            edge.update_path()
        self.view.fit_flow()
