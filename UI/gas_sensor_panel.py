"""Gas Sensor module panel: live Serial/NI-DAQ acquisition and analysis."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class GasSensorPanel(QWidget):
    analyze_requested = Signal()
    cycles_requested = Signal()
    calibration_requested = Signal()
    dilution_requested = Signal()
    connect_requested = Signal(str, int)
    daq_connect_requested = Signal(str, str, float, float, float, str)
    disconnect_requested = Signal()
    refresh_ports_requested = Signal()
    daq_refresh_requested = Signal()
    daq_device_changed = Signal(str)
    transport_changed = Signal(str)
    signal_changed = Signal(str)
    signal_selection_changed = Signal(object)
    marker_requested = Signal(str)
    flow_designer_requested = Signal()

    BAUD_RATES = (9600, 19200, 38400, 57600, 115200, 230400)
    VOLTAGE_RANGES = (
        ("0 to 5 V", 0.0, 5.0),
        ("0 to 10 V", 0.0, 10.0),
        ("-5 to 5 V", -5.0, 5.0),
        ("-10 to 10 V", -10.0, 10.0),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GasSensorPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Gas Sensor", self)
        title.setObjectName("GasSensorTitle")
        layout.addWidget(title)

        self.tabs = QTabWidget(self)
        self.live_tab = self._build_live_tab()
        self.flow_tab = self._build_flow_tab()
        self.analysis_tab = self._build_analysis_tab()
        self.tabs.addTab(self.live_tab, "Live")
        self.tabs.addTab(self.flow_tab, "Flow")
        self.tabs.addTab(self.analysis_tab, "Analysis")
        layout.addWidget(self.tabs, 1)

        self.setStyleSheet(
            """
            #GasSensorTitle { font-size: 13pt; font-weight: 600; color: #e6e6e6; }
            #GasSensorPanel QLabel { color: #aab0b6; }
            #GasSensorPanel QPushButton {
                padding: 5px 8px; border-radius: 6px;
                background: #262b33; border: 1px solid rgba(255,255,255,0.08);
                color: #e6e6e6;
            }
            #GasSensorPanel QPushButton:hover { border-color: #4F9CF9; }
            """
        )

    def _build_live_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(8)

        connection = QGroupBox("Acquisition connection", tab)
        form = QFormLayout(connection)
        self.transport_combo = QComboBox(connection)
        self.transport_combo.addItem("Serial (ESP32 JSON/CSV)", "serial")
        self.transport_combo.addItem("NI-DAQmx (analog input)", "ni_daq")
        form.addRow("Source", self.transport_combo)

        self.connection_stack = QStackedWidget(connection)
        self.serial_page = self._build_serial_page()
        self.daq_page = self._build_daq_page()
        self.connection_stack.addWidget(self.serial_page)
        self.connection_stack.addWidget(self.daq_page)
        form.addRow(self.connection_stack)

        buttons = QWidget(connection)
        button_layout = QHBoxLayout(buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.connect_button = QPushButton("Connect", connection)
        self.disconnect_button = QPushButton("Disconnect", connection)
        self.disconnect_button.setEnabled(False)
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.disconnect_button)
        form.addRow(buttons)
        self.connection_status = QLabel("Disconnected", connection)
        self.connection_status.setWordWrap(True)
        form.addRow("Status", self.connection_status)
        layout.addWidget(connection)

        monitor = QGroupBox("Live monitor", tab)
        monitor_layout = QVBoxLayout(monitor)
        signal_form = QFormLayout()
        self.signal_combo = QComboBox(monitor)
        self.signal_combo.hide()  # compatibility proxy for single-signal callers
        self.signal_list = QListWidget(monitor)
        self.signal_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.signal_list.setMaximumHeight(92)
        self.signal_list.setToolTip("Ctrl-click to plot up to 8 sensor signals")
        signal_form.addRow("Plot signals", self.signal_list)
        self.stats_label = QLabel("0 samples · 0 Hz · 0 errors", monitor)
        signal_form.addRow("Acquisition", self.stats_label)
        monitor_layout.addLayout(signal_form)
        values = QGridLayout()
        self.value_labels: dict[str, QLabel] = {}
        for index, name in enumerate(("Resistance", "Voltage", "Temperature", "Humidity")):
            values.addWidget(QLabel(name, monitor), index // 2 * 2, index % 2)
            label = QLabel("—", monitor)
            label.setObjectName(f"GasLive{name}Value")
            values.addWidget(label, index // 2 * 2 + 1, index % 2)
            self.value_labels[name.lower()] = label
        monitor_layout.addLayout(values)
        marker_row = QHBoxLayout()
        self.gas_on_button = QPushButton("Gas ON marker", monitor)
        self.gas_off_button = QPushButton("Gas OFF marker", monitor)
        self.gas_on_button.setEnabled(False)
        self.gas_off_button.setEnabled(False)
        marker_row.addWidget(self.gas_on_button)
        marker_row.addWidget(self.gas_off_button)
        monitor_layout.addLayout(marker_row)
        layout.addWidget(monitor)

        raw_box = QGroupBox("Raw input (last 200 records)", tab)
        raw_layout = QVBoxLayout(raw_box)
        self.raw_monitor = QTextEdit(raw_box)
        self.raw_monitor.setReadOnly(True)
        self.raw_monitor.document().setMaximumBlockCount(200)
        self.raw_monitor.setMaximumHeight(150)
        raw_layout.addWidget(self.raw_monitor)
        layout.addWidget(raw_box)
        layout.addStretch(1)

        self.transport_combo.currentIndexChanged.connect(self._transport_selected)
        self.connect_button.clicked.connect(self._emit_connect)
        self.disconnect_button.clicked.connect(self.disconnect_requested.emit)
        self.signal_combo.currentTextChanged.connect(self.signal_changed.emit)
        self.signal_list.itemSelectionChanged.connect(self._signal_selection_updated)
        self.gas_on_button.clicked.connect(lambda: self.marker_requested.emit("on"))
        self.gas_off_button.clicked.connect(lambda: self.marker_requested.emit("off"))
        return tab

    def _build_serial_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.port_combo = QComboBox(page)
        self.port_combo.setMinimumContentsLength(12)
        port_row = QWidget(page)
        port_layout = QHBoxLayout(port_row)
        port_layout.setContentsMargins(0, 0, 0, 0)
        port_layout.addWidget(self.port_combo, 1)
        self.refresh_button = QPushButton("Refresh", page)
        port_layout.addWidget(self.refresh_button)
        form.addRow("Port", port_row)
        self.baud_combo = QComboBox(page)
        for baud in self.BAUD_RATES:
            self.baud_combo.addItem(str(baud), baud)
        self.baud_combo.setCurrentIndex(self.baud_combo.findData(115200))
        form.addRow("Baud", self.baud_combo)
        self.refresh_button.clicked.connect(self.refresh_ports_requested.emit)
        return page

    def _build_daq_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.daq_device_combo = QComboBox(page)
        device_row = QWidget(page)
        device_layout = QHBoxLayout(device_row)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.addWidget(self.daq_device_combo, 1)
        self.daq_refresh_button = QPushButton("Refresh", page)
        device_layout.addWidget(self.daq_refresh_button)
        form.addRow("Device", device_row)
        self.daq_channel_combo = QComboBox(page)
        self.daq_channel_combo.setEditable(True)
        self.daq_channel_combo.hide()  # compatibility proxy for older callers/tests
        self.daq_channel_list = QListWidget(page)
        self.daq_channel_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.daq_channel_list.setMaximumHeight(86)
        self.daq_channel_list.setToolTip("Select one or more analog-input channels")
        form.addRow("AI channels", self.daq_channel_list)
        self.daq_rate_spin = QDoubleSpinBox(page)
        self.daq_rate_spin.setRange(1.0, 20.0)
        self.daq_rate_spin.setDecimals(1)
        self.daq_rate_spin.setSingleStep(1.0)
        self.daq_rate_spin.setValue(10.0)
        self.daq_rate_spin.setSuffix(" Hz")
        form.addRow("Sample rate", self.daq_rate_spin)
        self.daq_range_combo = QComboBox(page)
        for label, lower, upper in self.VOLTAGE_RANGES:
            self.daq_range_combo.addItem(label, (lower, upper))
        form.addRow("Voltage range", self.daq_range_combo)
        self.daq_terminal_combo = QComboBox(page)
        self.daq_terminal_combo.addItem("RSE (AI to AI GND)", "RSE")
        self.daq_terminal_combo.addItem("Differential", "DIFFERENTIAL")
        self.daq_terminal_combo.addItem("NRSE", "NRSE")
        form.addRow("Terminal mode", self.daq_terminal_combo)
        hint = QLabel("Requires NI-DAQmx driver and the Python nidaqmx package.", page)
        hint.setWordWrap(True)
        form.addRow(hint)
        self.daq_refresh_button.clicked.connect(self.daq_refresh_requested.emit)
        self.daq_device_combo.currentIndexChanged.connect(self._daq_device_selected)
        return page

    def _build_analysis_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 8, 4, 4)
        hint = QLabel("Use the active Book or a completed live session", tab)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.btn_analyze = QPushButton("Response (t90)…", tab)
        self.btn_analyze.setToolTip("Response % / sensitivity / response & recovery time (t90)")
        self.btn_cycles = QPushButton("Detect Gas Cycles…", tab)
        self.btn_calibration = QPushButton("Calibration + LOD…", tab)
        self.btn_dilution = QPushButton("Gas Dilution (ppm)…", tab)
        for button in (
            self.btn_analyze, self.btn_cycles, self.btn_calibration, self.btn_dilution
        ):
            button.setMinimumHeight(34)
            layout.addWidget(button)
        layout.addStretch(1)
        self.btn_analyze.clicked.connect(self.analyze_requested.emit)
        self.btn_cycles.clicked.connect(self.cycles_requested.emit)
        self.btn_calibration.clicked.connect(self.calibration_requested.emit)
        self.btn_dilution.clicked.connect(self.dilution_requested.emit)
        return tab

    def _build_flow_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(10)
        title = QLabel("Visual Acquisition Flow", tab)
        title.setStyleSheet("font-size: 11pt; font-weight: 700; color: #eef3f8;")
        layout.addWidget(title)
        hint = QLabel(
            "Build a LabVIEW-inspired sample pipeline before connecting the device.", tab
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        pipeline = QFrame(tab)
        pipeline.setStyleSheet(
            "QFrame { background: #20252c; border: 1px solid #3a424d; border-radius: 10px; }"
            "QLabel { border: none; background: transparent; color: #dce4ed; font-weight: 600; }"
        )
        pipeline_layout = QVBoxLayout(pipeline)
        pipeline_layout.setContentsMargins(12, 10, 12, 10)
        pipeline_layout.setSpacing(4)
        pipeline_layout.addWidget(QLabel("INPUT  →  PROCESS  →  BOOK  →  GRAPH", pipeline))
        self.flow_summary_label = QLabel("Raw samples · processors disabled", pipeline)
        self.flow_summary_label.setWordWrap(True)
        self.flow_summary_label.setStyleSheet("color: #8f9baa; font-weight: 400;")
        pipeline_layout.addWidget(self.flow_summary_label)
        layout.addWidget(pipeline)

        self.open_flow_button = QPushButton("Open Visual Flow Designer", tab)
        self.open_flow_button.setMinimumHeight(38)
        self.open_flow_button.setStyleSheet(
            "background: #316fb8; border-color: #4F9CF9; color: white; font-weight: 700;"
        )
        self.open_flow_button.clicked.connect(self.flow_designer_requested.emit)
        layout.addWidget(self.open_flow_button)
        note = QLabel(
            "Flow settings lock during acquisition to keep the Live Book schema stable.", tab
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return tab

    def _transport_selected(self) -> None:
        transport = str(self.transport_combo.currentData() or "serial")
        self.connection_stack.setCurrentIndex(1 if transport == "ni_daq" else 0)
        self.transport_changed.emit(transport)

    def _daq_device_selected(self) -> None:
        self.daq_device_changed.emit(
            str(self.daq_device_combo.currentData() or self.daq_device_combo.currentText())
        )

    def _emit_connect(self) -> None:
        if self.current_transport() == "ni_daq":
            voltage_range = self.daq_range_combo.currentData() or (0.0, 5.0)
            self.daq_connect_requested.emit(
                str(self.daq_device_combo.currentData() or self.daq_device_combo.currentText()),
                ",".join(self.selected_daq_channels()),
                float(self.daq_rate_spin.value()),
                float(voltage_range[0]),
                float(voltage_range[1]),
                str(self.daq_terminal_combo.currentData() or "RSE"),
            )
            return
        self.connect_requested.emit(
            str(self.port_combo.currentData() or self.port_combo.currentText()),
            int(self.baud_combo.currentData() or 115200),
        )

    def current_transport(self) -> str:
        return str(self.transport_combo.currentData() or "serial")

    def set_transport(self, transport: str) -> None:
        index = self.transport_combo.findData(str(transport))
        if index >= 0:
            blocked = self.transport_combo.blockSignals(True)
            self.transport_combo.setCurrentIndex(index)
            self.connection_stack.setCurrentIndex(1 if str(transport) == "ni_daq" else 0)
            self.transport_combo.blockSignals(blocked)

    def set_ports(self, ports: list[dict[str, str]], preferred: str = "") -> None:
        current = preferred or str(self.port_combo.currentData() or "")
        self.port_combo.clear()
        for port in ports:
            name = str(port.get("name", ""))
            description = str(port.get("description", "")).strip()
            label = f"{name} — {description}" if description else name
            self.port_combo.addItem(label, name)
        index = self.port_combo.findData(current)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)

    def set_baud(self, baud: int) -> None:
        index = self.baud_combo.findData(int(baud))
        if index >= 0:
            self.baud_combo.setCurrentIndex(index)

    def set_daq_devices(self, devices: list[dict[str, str]], preferred: str = "") -> None:
        blocked = self.daq_device_combo.blockSignals(True)
        current = preferred or str(self.daq_device_combo.currentData() or "")
        self.daq_device_combo.clear()
        for device in devices:
            name = str(device.get("name", ""))
            product = str(device.get("product_type", "")).strip()
            label = f"{name} — {product}" if product else name
            self.daq_device_combo.addItem(label, name)
        index = self.daq_device_combo.findData(current)
        if index >= 0:
            self.daq_device_combo.setCurrentIndex(index)
        self.daq_device_combo.blockSignals(blocked)

    def set_daq_channels(self, channels: list[str], preferred: str = "") -> None:
        blocked = self.daq_channel_combo.blockSignals(True)
        current = preferred or str(
            self.daq_channel_combo.currentData() or self.daq_channel_combo.currentText()
        )
        self.daq_channel_combo.clear()
        for channel in channels:
            self.daq_channel_combo.addItem(str(channel), str(channel))
        index = self.daq_channel_combo.findData(current)
        if index >= 0:
            self.daq_channel_combo.setCurrentIndex(index)
        elif not channels and current:
            self.daq_channel_combo.setEditText(current)
        elif channels:
            self.daq_channel_combo.setCurrentIndex(0)
        self.daq_channel_combo.blockSignals(blocked)
        selected = {item.strip() for item in str(preferred or current).split(",") if item.strip()}
        self.daq_channel_list.clear()
        for channel in channels:
            item = QListWidgetItem(str(channel), self.daq_channel_list)
            item.setData(Qt.UserRole, str(channel))
            item.setSelected(str(channel) in selected)
        if channels and not self.daq_channel_list.selectedItems():
            self.daq_channel_list.item(0).setSelected(True)

    def selected_daq_channels(self) -> list[str]:
        selected = [
            str(item.data(Qt.UserRole) or item.text())
            for item in self.daq_channel_list.selectedItems()
        ]
        if selected:
            return selected
        fallback = str(
            self.daq_channel_combo.currentData() or self.daq_channel_combo.currentText()
        ).strip()
        return [fallback] if fallback else []

    def selected_signal_columns(self) -> list[str]:
        return [
            str(item.data(Qt.UserRole) or item.text())
            for item in self.signal_list.selectedItems()
        ]

    def _signal_selection_updated(self) -> None:
        selected = self.selected_signal_columns()
        if len(selected) > 8:
            keep = set(selected[:8])
            blocked = self.signal_list.blockSignals(True)
            for index in range(self.signal_list.count()):
                item = self.signal_list.item(index)
                item.setSelected(str(item.data(Qt.UserRole) or item.text()) in keep)
            self.signal_list.blockSignals(blocked)
            selected = selected[:8]
        if selected:
            blocked = self.signal_combo.blockSignals(True)
            self.signal_combo.setCurrentText(selected[0])
            self.signal_combo.blockSignals(blocked)
        self.signal_selection_changed.emit(selected)

    def set_daq_options(
        self,
        *,
        rate: float = 10.0,
        min_voltage: float = 0.0,
        max_voltage: float = 5.0,
        terminal: str = "RSE",
    ) -> None:
        self.daq_rate_spin.setValue(float(rate))
        for index in range(self.daq_range_combo.count()):
            lower, upper = self.daq_range_combo.itemData(index)
            if float(lower) == float(min_voltage) and float(upper) == float(max_voltage):
                self.daq_range_combo.setCurrentIndex(index)
                break
        terminal_index = self.daq_terminal_combo.findData(str(terminal).upper())
        if terminal_index >= 0:
            self.daq_terminal_combo.setCurrentIndex(terminal_index)

    def set_connection_state(self, connected: bool, message: str) -> None:
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.transport_combo.setEnabled(not connected)
        for widget in (
            self.port_combo, self.baud_combo, self.refresh_button,
            self.daq_device_combo, self.daq_channel_combo, self.daq_refresh_button,
            self.daq_channel_list,
            self.daq_rate_spin, self.daq_range_combo, self.daq_terminal_combo,
        ):
            widget.setEnabled(not connected)
        self.gas_on_button.setEnabled(connected)
        self.gas_off_button.setEnabled(connected)
        self.connection_status.setText(str(message))

    def set_signal_columns(
        self, columns: list[str], selected: str | list[str] | tuple[str, ...] = ""
    ) -> None:
        selected_values = (
            [str(value) for value in selected]
            if isinstance(selected, (list, tuple))
            else ([str(selected)] if selected else [])
        )[:8]
        blocked = self.signal_combo.blockSignals(True)
        self.signal_combo.clear()
        self.signal_combo.addItems([str(column) for column in columns])
        if selected_values and selected_values[0] in columns:
            self.signal_combo.setCurrentText(selected_values[0])
        self.signal_combo.blockSignals(blocked)
        blocked = self.signal_list.blockSignals(True)
        self.signal_list.clear()
        selected_set = set(selected_values)
        for column in columns:
            item = QListWidgetItem(str(column), self.signal_list)
            item.setData(Qt.UserRole, str(column))
            item.setSelected(str(column) in selected_set)
        if columns and not self.signal_list.selectedItems():
            self.signal_list.item(0).setSelected(True)
        self.signal_list.blockSignals(blocked)

    def update_status(self, status: dict[str, Any], latest: dict[str, Any] | None = None) -> None:
        errors = status.get("acquisition_errors", status.get("parse_errors", 0))
        self.stats_label.setText(
            f"{int(status.get('samples', 0)):,} samples · "
            f"{float(status.get('sample_rate_hz', 0.0)):.2f} Hz · "
            f"{int(errors)} errors"
        )
        values = latest or {}
        aliases = {
            "resistance": ("resistance", "res", "r", "ohm"),
            "voltage": ("voltage", "volt", "v"),
            "temperature": ("temperature", "temp", "t_c"),
            "humidity": ("humidity", "humid", "rh"),
        }
        folded = {str(key).casefold(): value for key, value in values.items()}
        for display, names in aliases.items():
            value = next((folded[name] for name in names if name in folded), None)
            if value is None:
                value = next(
                    (
                        field_value
                        for field, field_value in folded.items()
                        if any(len(alias) >= 3 and alias in field for alias in names)
                    ),
                    None,
                )
            self.value_labels[display].setText("—" if value is None else str(value))

    def append_raw_lines(self, lines: list[str]) -> None:
        for line in lines:
            self.raw_monitor.append(str(line))

    def set_flow_summary(self, config, running: bool = False) -> None:
        steps = []
        channels = tuple(getattr(config, "sensor_channels", ()) or ())
        if channels:
            steps.append(f"{len(channels)} sensor channels")
        if bool(getattr(config, "voltage_to_resistance", False)):
            steps.append("Voltage → resistance")
        if bool(getattr(config, "smoothing", False)):
            window = int(getattr(config, "smoothing_window", 5))
            steps.append(f"Moving average ({window})")
        if channels and any(
            getattr(channel, "voltage_to_resistance", False) for channel in channels
        ):
            steps.append("Per-sensor resistance")
        if channels and any(getattr(channel, "smoothing", False) for channel in channels):
            steps.append("Per-sensor smoothing")
        if not steps:
            steps.append("Raw samples · processors disabled")
        state = "RUNNING" if running else "READY"
        self.flow_summary_label.setText(" · ".join(steps) + f"\n{state}")
        self.open_flow_button.setText(
            "View Running Flow" if running else "Open Visual Flow Designer"
        )
