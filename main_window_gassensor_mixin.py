from __future__ import annotations

from datetime import datetime
import json
import logging
import numpy as np
import pandas as pd
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QStyle

from analysis.gas_sensor import (
    analyze_response,
    calibration_curve,
    detect_gas_cycles,
    dilution_ppm,
    format_response_report,
    limit_of_detection,
)
from processors import beautify_axes

logger = logging.getLogger(__name__)


class MainWindowGasSensorMixin:
    """Gas Sensor specialty module (ROADMAP H) — first activity-rail module.

    UI flows only; the math lives in analysis/gas_sensor.py. Talks to the UI
    through the view seam (ask_choice/ask_number/inform/notify) so everything
    is testable headless.
    """

    # ------------------------------------------------------------------ setup
    def init_gas_sensor_module(self):
        """Register the Gas Sensor context in the activity rail + its menu."""
        from analysis.gas_flow import GasFlowConfig, GasFlowProcessor
        from core.gas_daq import GasDaqController
        from core.gas_live import GasLiveController
        from UI.gas_sensor_panel import GasSensorPanel

        panel = GasSensorPanel(self)
        panel.analyze_requested.connect(self.gs_analyze_response)
        panel.cycles_requested.connect(self.gs_detect_cycles)
        panel.calibration_requested.connect(self.gs_calibration)
        panel.dilution_requested.connect(self.gs_dilution)
        panel.connect_requested.connect(self.gs_live_connect)
        panel.daq_connect_requested.connect(self.gs_live_connect_daq)
        panel.disconnect_requested.connect(self.gs_live_disconnect)
        panel.refresh_ports_requested.connect(self.gs_live_refresh_ports)
        panel.daq_refresh_requested.connect(self.gs_live_refresh_daq_devices)
        panel.daq_device_changed.connect(self.gs_live_refresh_daq_channels)
        panel.transport_changed.connect(self.gs_live_transport_changed)
        panel.signal_changed.connect(self.gs_live_select_signal)
        panel.signal_selection_changed.connect(self.gs_live_select_signals)
        panel.marker_requested.connect(self.gs_live_mark)
        panel.flow_designer_requested.connect(self.gs_live_open_flow_designer)
        self.gas_sensor_panel = panel

        try:
            raw_flow = self.settings.value("gas_live/flow_config", "")
            if isinstance(raw_flow, str) and raw_flow.strip():
                flow_values = json.loads(raw_flow)
            elif isinstance(raw_flow, dict):
                flow_values = raw_flow
            else:
                flow_values = {}
            flow_config = GasFlowConfig.from_dict(flow_values)
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.debug("gas flow settings restore skipped", exc_info=True)
            flow_config = GasFlowConfig()
        try:
            raw_wiring = self.settings.value("gas_live/flow_wiring", "")
            flow_wiring = json.loads(raw_wiring) if isinstance(raw_wiring, str) and raw_wiring else None
            self.gas_flow_processor = GasFlowProcessor(flow_config, flow_wiring)
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.debug("gas flow wiring restore skipped", exc_info=True)
            self.gas_flow_processor = GasFlowProcessor(flow_config)
        self.gas_flow_designer = None
        panel.set_flow_summary(flow_config, False)

        controller = GasLiveController(self)
        controller.state_changed.connect(self._gs_live_state_changed)
        controller.records_ready.connect(self._gs_live_records_ready)
        controller.raw_lines_ready.connect(panel.append_raw_lines)
        controller.parse_errors.connect(self._gs_live_parse_errors)
        controller.marker_created.connect(self._gs_live_marker_created)
        self.gas_live_controller = controller

        daq_controller = GasDaqController(self)
        daq_controller.state_changed.connect(self._gs_live_daq_state_changed)
        daq_controller.records_ready.connect(self._gs_live_records_ready)
        daq_controller.raw_lines_ready.connect(panel.append_raw_lines)
        daq_controller.parse_errors.connect(self._gs_live_parse_errors)
        daq_controller.marker_created.connect(self._gs_live_marker_created)
        self.gas_daq_controller = daq_controller
        self._gs_live_active_transport = "serial"
        self._gs_live_book_timer = QTimer(self)
        self._gs_live_book_timer.setInterval(1000)
        self._gs_live_book_timer.timeout.connect(self._gs_live_flush_book)
        self._gs_live_reset_session()
        self.gs_live_refresh_ports()
        try:
            panel.set_baud(int(self.settings.value("gas_live/baud", 115200)))
        except Exception:
            panel.set_baud(115200)
        try:
            panel.set_daq_options(
                rate=float(self.settings.value("gas_live/daq_rate", 10.0)),
                min_voltage=float(self.settings.value("gas_live/daq_min_voltage", 0.0)),
                max_voltage=float(self.settings.value("gas_live/daq_max_voltage", 5.0)),
                terminal=str(self.settings.value("gas_live/daq_terminal", "RSE")),
            )
            panel.set_daq_channels([], str(self.settings.value("gas_live/daq_channel", "")))
            panel.set_transport(str(self.settings.value("gas_live/transport", "serial")))
            self._gs_live_active_transport = panel.current_transport()
            if self._gs_live_active_transport == "ni_daq":
                self.gs_live_refresh_daq_devices()
        except Exception:
            logger.debug("gas live DAQ settings restore skipped", exc_info=True)

        self.register_specialty_module(
            module_id="gas_sensor",
            title="Gas Sensor",
            subtitle="Live Serial/NI-DAQ, response, cycles, calibration, dilution",
            panel=panel,
            icon_key="gas",
            fallback_icon=QStyle.StandardPixmap.SP_DriveHDIcon,
            actions=(
                ("Live Acquisition...", self.gs_live_open_panel),
                ("Visual Acquisition Flow...", self.gs_live_open_flow_designer),
                ("Response Analysis (t90)...", self.gs_analyze_response),
                ("Detect Gas Cycles...", self.gs_detect_cycles),
                ("Calibration Curve + LOD...", self.gs_calibration),
                ("Gas Dilution (ppm)...", self.gs_dilution),
            ),
        )
        return panel

    # ----------------------------------------------------------- live serial
    def _gs_live_reset_session(self) -> None:
        previous = getattr(self, "_gs_live_workbook", None)
        if previous is not None and hasattr(previous, "set_streaming_mode"):
            previous.set_streaming_mode(False)
        self._gs_live_dataset_name = None
        self._gs_live_workbook = None
        self._gs_live_graph_id = None
        self._gs_live_line = None
        self._gs_live_signal = ""
        self._gs_live_lines: dict[str, object] = {}
        self._gs_live_signals: list[str] = []
        self._gs_live_all_records: list[dict] = []
        self._gs_live_book_buffer: list[dict] = []
        self._gs_live_markers: list[tuple[str, float, str]] = []
        processor = getattr(self, "gas_flow_processor", None)
        if processor is not None:
            processor.reset()

    def gs_live_open_panel(self):
        self.show_module_gallery("gas_sensor")
        panel = getattr(self, "gas_sensor_panel", None)
        if panel is not None:
            panel.tabs.setCurrentWidget(panel.live_tab)

    def gs_live_open_flow_designer(self):
        from UI.gas_flow_editor import GasFlowDesigner

        designer = getattr(self, "gas_flow_designer", None)
        if designer is None:
            designer = GasFlowDesigner(self)
            designer.config_changed.connect(self.gs_live_configure_flow)
            designer.wiring_changed.connect(self.gs_live_configure_wiring)
            self.gas_flow_designer = designer
        processor = getattr(self, "gas_flow_processor", None)
        if processor is not None:
            designer.set_config(processor.config)
            designer.set_wiring(processor.wiring, emit=False)
        transport = getattr(self, "_gs_live_active_transport", "serial")
        status = self.gs_live_status()
        if transport == "ni_daq":
            detail = ", ".join(status.get("channels", []))
        else:
            detail = str(status.get("port") or "JSON Lines / CSV records")
        designer.set_source(transport, detail)
        designer.set_running(self._gs_live_any_connected())
        designer.show()
        designer.raise_()
        designer.activateWindow()
        return designer

    def gs_live_configure_flow(self, config=None, **values):
        from analysis.gas_flow import GasFlowConfig

        if self._gs_live_any_connected():
            return False, "Disconnect acquisition before changing the visual flow."
        try:
            if isinstance(config, GasFlowConfig):
                flow_config = config.validated()
            elif isinstance(config, dict):
                flow_config = GasFlowConfig.from_dict(config)
            elif values:
                current = getattr(self.gas_flow_processor, "config", GasFlowConfig())
                merged = current.to_dict()
                merged.update(values)
                flow_config = GasFlowConfig.from_dict(merged)
            else:
                flow_config = GasFlowConfig()
        except (TypeError, ValueError) as exc:
            return False, str(exc)
        self.gas_flow_processor.configure(flow_config)
        try:
            self.settings.setValue(
                "gas_live/flow_config",
                json.dumps(flow_config.to_dict(), ensure_ascii=True, sort_keys=True),
            )
        except Exception:
            logger.debug("gas visual flow persistence skipped", exc_info=True)
        panel = getattr(self, "gas_sensor_panel", None)
        if panel is not None:
            panel.set_flow_summary(flow_config, False)
        designer = getattr(self, "gas_flow_designer", None)
        if designer is not None and designer.config() != flow_config:
            designer.set_config(flow_config)
        return True, self.gs_live_flow_status()["summary"]

    def gs_live_configure_wiring(self, edges):
        if self._gs_live_any_connected():
            return False, "Disconnect acquisition before changing flow wiring."
        processor = getattr(self, "gas_flow_processor", None)
        if processor is None:
            return False, "Gas visual flow is unavailable."
        try:
            processor.configure_wiring(edges)
        except (TypeError, ValueError) as exc:
            return False, str(exc)
        try:
            self.settings.setValue(
                "gas_live/flow_wiring",
                json.dumps([list(edge) for edge in processor.wiring]),
            )
        except Exception:
            logger.debug("gas visual flow wiring persistence skipped", exc_info=True)
        return True, "Flow wiring updated: " + " · ".join(
            f"{source}→{target}" for source, target in processor.wiring
        )

    def _gs_live_validate_flow_before_connect(self):
        designer = getattr(self, "gas_flow_designer", None)
        if designer is not None and not designer.wiring_valid():
            return False, "Visual flow wiring is invalid. Open the designer and reconnect the nodes."
        processor = getattr(self, "gas_flow_processor", None)
        if processor is None:
            return True, ""
        try:
            from analysis.gas_flow import validate_flow_wiring
            validate_flow_wiring(processor.wiring)
        except (TypeError, ValueError) as exc:
            return False, str(exc)
        return True, ""

    def gs_live_flow_status(self) -> dict:
        processor = getattr(self, "gas_flow_processor", None)
        if processor is None:
            return {"available": False, "summary": "Visual flow is unavailable."}
        from analysis.gas_flow import flow_wiring_order

        config = processor.config
        labels = {
            "source": "input",
            "divider": "voltage_to_resistance",
            "smooth": "moving_average",
            "book": "live_book",
            "graph": "rolling_graph",
        }
        nodes = []
        for node in flow_wiring_order(processor.wiring):
            if node == "divider" and not (
                config.voltage_to_resistance
                or any(channel.voltage_to_resistance for channel in config.sensor_channels)
            ):
                continue
            if node == "smooth" and not (
                config.smoothing
                or any(channel.smoothing for channel in config.sensor_channels)
            ):
                continue
            nodes.append(labels[node])
        summary = " → ".join(nodes)
        if config.sensor_channels:
            summary += f" · {len(config.sensor_channels)} sensor channels"
        return {
            "available": True,
            "running": self._gs_live_any_connected(),
            "nodes": nodes,
            "config": config.to_dict(),
            "wiring": [list(edge) for edge in processor.wiring],
            "summary": summary,
        }

    def gs_live_refresh_ports(self):
        controller = getattr(self, "gas_live_controller", None)
        panel = getattr(self, "gas_sensor_panel", None)
        if controller is None or panel is None:
            return []
        try:
            preferred = str(self.settings.value("gas_live/port", "") or "")
        except Exception:
            preferred = ""
        ports = controller.available_ports()
        panel.set_ports(ports, preferred=preferred)
        return ports

    def gs_live_transport_changed(self, transport: str) -> None:
        transport = "ni_daq" if str(transport) == "ni_daq" else "serial"
        if not self._gs_live_any_connected():
            self._gs_live_active_transport = transport
        try:
            self.settings.setValue("gas_live/transport", transport)
        except Exception:
            logger.debug("gas live transport persistence skipped", exc_info=True)
        if transport == "ni_daq":
            self.gs_live_refresh_daq_devices()

    def gs_live_refresh_daq_devices(self):
        controller = getattr(self, "gas_daq_controller", None)
        panel = getattr(self, "gas_sensor_panel", None)
        if controller is None or panel is None:
            return []
        try:
            preferred = str(self.settings.value("gas_live/daq_device", "") or "")
        except Exception:
            preferred = ""
        try:
            devices = controller.available_devices()
        except Exception as exc:
            message = " ".join(str(exc).split())[:240] or "Could not enumerate NI-DAQ devices."
            panel.set_daq_devices([])
            if panel.current_transport() == "ni_daq":
                panel.set_connection_state(False, message)
            return []
        panel.set_daq_devices(devices, preferred=preferred)
        device = str(panel.daq_device_combo.currentData() or "")
        if device:
            self.gs_live_refresh_daq_channels(device)
        elif panel.current_transport() == "ni_daq":
            panel.set_connection_state(False, "No NI-DAQ analog-input device was found.")
        return devices

    def gs_live_refresh_daq_channels(self, device_name: str):
        controller = getattr(self, "gas_daq_controller", None)
        panel = getattr(self, "gas_sensor_panel", None)
        device_name = str(device_name or "").strip()
        if controller is None or panel is None or not device_name:
            if panel is not None:
                panel.set_daq_channels([])
            return []
        try:
            preferred = str(self.settings.value("gas_live/daq_channel", "") or "")
        except Exception:
            preferred = ""
        try:
            channels = controller.available_channels(device_name)
        except Exception as exc:
            message = " ".join(str(exc).split())[:240] or "Could not enumerate NI-DAQ channels."
            panel.set_daq_channels([], preferred)
            if panel.current_transport() == "ni_daq":
                panel.set_connection_state(False, message)
            return []
        panel.set_daq_channels(channels, preferred)
        designer = getattr(self, "gas_flow_designer", None)
        if designer is not None:
            column_names = getattr(controller, "column_names", None)
            if callable(column_names):
                designer.set_available_fields(column_names(channels))
        return channels

    def _gs_live_any_connected(self) -> bool:
        return any(
            bool(getattr(getattr(self, name, None), "connected", False))
            for name in ("gas_live_controller", "gas_daq_controller")
        )

    def _gs_live_active_controller(self):
        if getattr(self, "_gs_live_active_transport", "serial") == "ni_daq":
            return getattr(self, "gas_daq_controller", None)
        return getattr(self, "gas_live_controller", None)

    def gs_live_connect(self, port_name: str, baud: int = 115200):
        controller = getattr(self, "gas_live_controller", None)
        if controller is None:
            return False, "Gas live controller is unavailable."
        if self._gs_live_any_connected():
            return False, "Gas live acquisition is already connected."
        flow_ok, flow_message = self._gs_live_validate_flow_before_connect()
        if not flow_ok:
            return False, flow_message
        self._gs_live_active_transport = "serial"
        self._gs_live_reset_session()
        ok, message = controller.connect_port(port_name, int(baud))
        if ok:
            self._gs_live_book_timer.start()
            try:
                self.settings.setValue("gas_live/port", str(port_name))
                self.settings.setValue("gas_live/baud", int(baud))
            except Exception:
                logger.debug("gas live settings persistence skipped", exc_info=True)
            self._gs_log(message)
        return ok, message

    def gs_live_connect_daq(
        self,
        device_name: str,
        channel: str,
        sample_rate_hz: float = 10.0,
        min_voltage: float = 0.0,
        max_voltage: float = 5.0,
        terminal_config: str = "RSE",
    ):
        controller = getattr(self, "gas_daq_controller", None)
        if controller is None:
            return False, "NI-DAQ live controller is unavailable."
        if self._gs_live_any_connected():
            return False, "Gas live acquisition is already connected."
        flow_ok, flow_message = self._gs_live_validate_flow_before_connect()
        if not flow_ok:
            return False, flow_message
        self._gs_live_active_transport = "ni_daq"
        self._gs_live_reset_session()
        ok, message = controller.connect_device(
            device_name,
            channel,
            float(sample_rate_hz),
            float(min_voltage),
            float(max_voltage),
            terminal_config,
        )
        if ok:
            self._gs_live_book_timer.start()
            try:
                self.settings.setValue("gas_live/transport", "ni_daq")
                self.settings.setValue("gas_live/daq_device", str(device_name))
                self.settings.setValue("gas_live/daq_channel", str(channel))
                self.settings.setValue("gas_live/daq_rate", float(sample_rate_hz))
                self.settings.setValue("gas_live/daq_min_voltage", float(min_voltage))
                self.settings.setValue("gas_live/daq_max_voltage", float(max_voltage))
                self.settings.setValue("gas_live/daq_terminal", str(terminal_config))
            except Exception:
                logger.debug("gas live DAQ settings persistence skipped", exc_info=True)
            self._gs_log(message)
        return ok, message

    def gs_live_disconnect(self):
        controller = self._gs_live_active_controller()
        if controller is None:
            return False, "Gas live controller is unavailable."
        was_connected = controller.connected
        disconnect = getattr(controller, "disconnect_device", None)
        if not callable(disconnect):
            disconnect = getattr(controller, "disconnect_port", None)
        if callable(disconnect):
            disconnect("Disconnected by user")
        self._gs_live_finalize_session()
        return was_connected, "Disconnected by user" if was_connected else "Already disconnected"

    def gs_live_mark(self, state: str, label: str = ""):
        controller = self._gs_live_active_controller()
        if controller is None:
            return False, "Gas live controller is unavailable."
        return controller.mark_exposure(state, label)

    def gs_live_status(self) -> dict:
        controller = self._gs_live_active_controller()
        if controller is None:
            return {"connected": False, "message": "Gas live controller is unavailable."}
        status = controller.status()
        status.setdefault("transport", getattr(self, "_gs_live_active_transport", "serial"))
        status["book"] = getattr(self, "_gs_live_dataset_name", None)
        status["graph"] = getattr(self, "_gs_live_graph_id", None)
        processor = getattr(self, "gas_flow_processor", None)
        if processor is not None:
            status["flow"] = processor.config.to_dict()
        status["plot_signals"] = list(getattr(self, "_gs_live_signals", []))
        return status

    def _gs_live_state_changed(self, connected: bool, message: str) -> None:
        self._gs_live_state_changed_for("serial", connected, message)

    def _gs_live_daq_state_changed(self, connected: bool, message: str) -> None:
        self._gs_live_state_changed_for("ni_daq", connected, message)

    def _gs_live_state_changed_for(
        self, transport: str, connected: bool, message: str
    ) -> None:
        if connected:
            self._gs_live_active_transport = transport
        elif (
            transport != getattr(self, "_gs_live_active_transport", "serial")
            and self._gs_live_any_connected()
        ):
            return
        panel = getattr(self, "gas_sensor_panel", None)
        if panel is not None:
            panel.set_transport(transport)
            panel.set_connection_state(connected, message)
            panel.update_status(self.gs_live_status())
            processor = getattr(self, "gas_flow_processor", None)
            if processor is not None:
                panel.set_flow_summary(processor.config, connected)
        designer = getattr(self, "gas_flow_designer", None)
        if designer is not None:
            designer.set_running(connected)
            designer.set_source(transport, message)
        if not connected:
            self._gs_live_finalize_session()
        self.notify(message)

    def _gs_live_parse_errors(self, errors) -> None:
        if errors:
            self._gs_log(f"Gas live acquisition warning: {errors[-1]}")
        panel = getattr(self, "gas_sensor_panel", None)
        if panel is not None:
            panel.update_status(self.gs_live_status())

    def _gs_live_records_ready(self, records) -> None:
        source_rows = [dict(record) for record in records if isinstance(record, dict)]
        if not source_rows:
            return
        designer = getattr(self, "gas_flow_designer", None)
        if designer is not None:
            fields = [
                str(field)
                for field in source_rows[0]
                if field not in {"elapsed_s", "gas_state", "event"}
            ]
            designer.set_available_fields(fields)
        processor = getattr(self, "gas_flow_processor", None)
        rows = processor.process_records(source_rows) if processor is not None else source_rows
        first_batch = self._gs_live_workbook is None
        self._gs_live_all_records.extend(rows)
        if first_batch:
            self._gs_live_create_session(pd.DataFrame(rows))
        else:
            self._gs_live_book_buffer.extend(rows)
        self._gs_live_update_graph()
        panel = getattr(self, "gas_sensor_panel", None)
        if panel is not None:
            panel.update_status(self.gs_live_status(), rows[-1])

    def _gs_live_unique_name(self) -> str:
        base = f"Live Gas {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        name = base
        index = 2
        while name in getattr(self, "_datasets", {}):
            name = f"{base} ({index})"
            index += 1
        return name

    def _gs_live_create_session(self, frame: pd.DataFrame) -> None:
        name = self._gs_live_unique_name()
        self._stage_insert(name, frame, None)
        workbook = self.mdi.book_widget(name)
        self._gs_live_dataset_name = name
        self._gs_live_workbook = workbook
        if workbook is not None and hasattr(workbook, "set_streaming_mode"):
            workbook.set_streaming_mode(True)

        signal_columns = []
        for column in frame.columns:
            if column in {"elapsed_s", "gas_state", "event"}:
                continue
            if pd.to_numeric(frame[column], errors="coerce").notna().any():
                signal_columns.append(str(column))
        preferred = self._gs_live_default_signal(signal_columns)
        processor = getattr(self, "gas_flow_processor", None)
        if processor is not None and processor.config.smoothing:
            suffix = f"_ma{processor.config.smoothing_window}"
            smoothed = [column for column in signal_columns if column.endswith(suffix)]
            if smoothed:
                preferred = smoothed[-1]
        selected = self._gs_live_default_signals(signal_columns, preferred)
        self._gs_live_signals = selected
        self._gs_live_signal = selected[0] if selected else ""
        panel = getattr(self, "gas_sensor_panel", None)
        if panel is not None:
            panel.set_signal_columns(signal_columns, selected)
        self._gs_live_create_graph()
        self._gs_log(f"Gas live session started: {name}")

    @staticmethod
    def _gs_live_default_signal(columns: list[str]) -> str:
        aliases = ("resistance", "res", "ohm", "voltage", "volt", "temperature", "temp", "humidity")
        folded = {column.casefold(): column for column in columns}
        for alias in aliases:
            if alias in folded:
                return folded[alias]
        for alias in aliases:
            for column in columns:
                if alias in column.casefold():
                    return column
        return columns[0] if columns else ""

    def _gs_live_default_signals(self, columns: list[str], preferred: str) -> list[str]:
        processor = getattr(self, "gas_flow_processor", None)
        configured: list[str] = []
        if processor is not None:
            for channel in processor.config.sensor_channels:
                candidates = (
                    channel.output_field,
                    channel.resistance_field,
                    channel.alias,
                    channel.source_field,
                )
                match = next((field for field in candidates if field in columns), None)
                if match and match not in configured:
                    configured.append(match)
        if configured:
            return configured[:8]
        daq_channels = [
            column for column in columns if column.casefold().endswith("_voltage_v")
        ]
        if len(daq_channels) > 1:
            return daq_channels[:8]
        return [preferred] if preferred else []

    def _gs_live_create_graph(self) -> None:
        signals = list(getattr(self, "_gs_live_signals", []))
        if not signals:
            return
        graph_id = self.tabs.add_tab("Live Gas Sensor")
        tab = self.tabs.tabs[graph_id]
        ax = tab.get_axes()
        lines = {}
        for signal in signals:
            line, = ax.plot([], [], linewidth=1.6, label=signal)
            lines[signal] = line
        ax.set_title("Live Gas Sensor")
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel(signals[0] if len(signals) == 1 else "Sensor signals")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
        tab.register_layer(
            list(lines.values()), "Live Gas Sensor", "line",
            meta={"kind": "gas_live", "dataset": self._gs_live_dataset_name},
        )
        self._gs_live_graph_id = graph_id
        self._gs_live_lines = lines
        self._gs_live_signal = signals[0]
        self._gs_live_line = lines[signals[0]]
        for state, elapsed, event in self._gs_live_markers:
            self._gs_live_draw_marker(state, elapsed, event)
        tab.draw()

    def gs_live_select_signal(self, column: str) -> None:
        if not column:
            return
        self.gs_live_select_signals([str(column)])

    def gs_live_select_signals(self, columns) -> None:
        selected = []
        for column in columns or ():
            column = str(column)
            if column and column not in selected:
                selected.append(column)
        if not selected:
            return
        self._gs_live_signals = selected[:8]
        self._gs_live_signal = self._gs_live_signals[0]
        self._gs_live_update_graph()

    def _gs_live_update_graph(self) -> None:
        signals = list(getattr(self, "_gs_live_signals", []))
        if not signals or not self._gs_live_all_records:
            return
        graph_id = getattr(self, "_gs_live_graph_id", None)
        if not graph_id or graph_id not in self.tabs.tabs:
            self._gs_live_create_graph()
            graph_id = self._gs_live_graph_id
        tab = self.tabs.tabs.get(graph_id)
        if tab is None:
            return
        ax = tab.get_axes()
        lines = getattr(self, "_gs_live_lines", {})
        for signal in list(lines):
            if signal not in signals:
                lines.pop(signal).remove()
        for signal in signals:
            if signal not in lines:
                line, = ax.plot([], [], linewidth=1.6, label=signal)
                lines[signal] = line
        self._gs_live_lines = lines
        recent = self._gs_live_all_records[-2000:]
        x = pd.to_numeric(
            pd.Series([row.get("elapsed_s") for row in recent]), errors="coerce"
        ).to_numpy(dtype=float)
        for signal in signals:
            y = pd.to_numeric(
                pd.Series([row.get(signal) for row in recent]), errors="coerce"
            ).to_numpy(dtype=float)
            finite = np.isfinite(x) & np.isfinite(y)
            source_x = x[finite]
            source_y = y[finite]
            line = lines[signal]
            line._sciplotter_x_values = source_x.tolist()
            line._sciplotter_y_values = source_y.tolist()
            try:
                del line._sciplotter_x_numeric
            except AttributeError:
                pass
            line.set_data(source_x, source_y)
            line.set_label(signal)
        self._gs_live_signal = signals[0]
        self._gs_live_line = lines[signals[0]]
        ax.set_ylabel(signals[0] if len(signals) == 1 else "Sensor signals")
        ax.relim()
        ax.autoscale_view()
        ax.legend(loc="best")
        tab.canvas.draw_idle()

    def _gs_live_marker_created(self, state: str, elapsed: float, event: str) -> None:
        marker = (str(state), float(elapsed), str(event))
        self._gs_live_markers.append(marker)
        self._gs_live_draw_marker(*marker)

    def _gs_live_draw_marker(self, state: str, elapsed: float, event: str) -> None:
        graph_id = getattr(self, "_gs_live_graph_id", None)
        tab = self.tabs.tabs.get(graph_id) if graph_id else None
        if tab is None:
            return
        color = "#2ECC71" if state == "on" else "#E74C3C"
        tab.get_axes().axvline(elapsed, color=color, linestyle="--", alpha=0.8, label=event)
        tab.canvas.draw_idle()

    def _gs_live_flush_book(self) -> int:
        workbook = getattr(self, "_gs_live_workbook", None)
        if workbook is None or not self._gs_live_book_buffer:
            return 0
        rows = self._gs_live_book_buffer
        self._gs_live_book_buffer = []
        columns = list(workbook.source_df.columns)
        frame = pd.DataFrame(rows).reindex(columns=columns)
        appended = workbook.append_dataframe_rows(frame)
        name = self._gs_live_dataset_name
        if name in self._datasets:
            self._datasets[name]["df"] = workbook.source_df
        if getattr(self, "workbook", None) is workbook:
            self._df = workbook.source_df
        refresh_ai = getattr(self, "_refresh_ai_context", None)
        if callable(refresh_ai):
            refresh_ai()
        return appended

    def _gs_live_finalize_session(self) -> None:
        timer = getattr(self, "_gs_live_book_timer", None)
        if timer is not None:
            timer.stop()
        self._gs_live_flush_book()
        workbook = getattr(self, "_gs_live_workbook", None)
        if workbook is not None and hasattr(workbook, "set_streaming_mode"):
            workbook.set_streaming_mode(False)

    def closeEvent(self, event) -> None:
        for name in ("gas_live_controller", "gas_daq_controller"):
            controller = getattr(self, name, None)
            if controller is not None:
                controller.close()
        self._gs_live_finalize_session()
        super().closeEvent(event)

    # ---------------------------------------------------------------- helpers
    def _gs_time_seconds(self, col: str) -> np.ndarray:
        """Column as seconds: datetime → seconds from start, else numeric."""
        ser = self._df[col]
        if pd.api.types.is_datetime64_any_dtype(ser):
            return (ser - ser.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        return pd.to_numeric(ser, errors="coerce").to_numpy(dtype=float)

    def _gs_x_and_options(self):
        """(x_name, y_options, cols) โดยเดา X = คอลัมน์เวลา/แกน X ที่เลือก (ไม่ prompt)."""
        cols = [str(c) for c in self._df.columns]
        x_name = self.selected_x_column()
        if x_name not in cols:
            time_like = [c for c in cols if str(c).lower() == "t"
                         or any(k in str(c).lower()
                                for k in ("time", "timestamp", "datetime", "date", "epoch"))]
            x_name = time_like[0] if time_like else cols[0]
        y_options = [c for c in cols if c != x_name]
        return x_name, y_options, cols

    def _gs_log(self, text: str) -> None:
        try:
            dock = getattr(self, "op_log_dock", None)
            if dock is not None:
                dock.add_entry(text)
        except Exception:
            logger.debug("gas log entry skipped", exc_info=True)

    # ------------------------------------------------------------------ flows
    def gs_analyze_response(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล", "เปิดไฟล์หรือคลิก Book ที่มีข้อมูลก่อน")
            return
        x_name, y_options, _cols = self._gs_x_and_options()
        if not y_options:
            self.inform("ข้อมูลไม่พอ", "ต้องมีคอลัมน์สัญญาณ (เช่น resistance) นอกจากคอลัมน์เวลา")
            return
        t = self._gs_time_seconds(x_name)
        finite_t = t[np.isfinite(t)]
        if finite_t.size < 3:
            self.inform("ข้อมูลไม่พอ", "คอลัมน์เวลาไม่มีค่าที่ใช้ได้")
            return
        t0, t1 = float(finite_t.min()), float(finite_t.max())
        span = t1 - t0
        y_sel = self.selected_y_column()
        res_form = self.ask_form("Response Analysis (t90)", [
            {"name": "y_col", "label": "Signal (Y)", "kind": "choice", "options": y_options,
             "default": y_sel if y_sel in y_options else y_options[0]},
            {"name": "t_on", "label": "Gas ON time t_on (s)", "kind": "float",
             "default": round(t0 + 0.25 * span, 4), "min": t0, "max": t1, "decimals": 4},
            {"name": "t_off", "label": "Gas OFF time t_off (s)", "kind": "float",
             "default": round(t0 + 0.75 * span, 4), "min": t0, "max": t1, "decimals": 4},
        ], description=f"Time range {t0:.4g}–{t1:.4g} s (X axis = {x_name})")
        if res_form is None:
            return
        y_name = res_form["y_col"]
        y = pd.to_numeric(self._df[y_name], errors="coerce").to_numpy(dtype=float)
        try:
            res = analyze_response(t, y, float(res_form["t_on"]), float(res_form["t_off"]))
        except Exception as e:
            self.error_box("วิเคราะห์ไม่สำเร็จ", f"สาเหตุ: {e}")
            return
        report = format_response_report(res)
        self.inform(f"Gas Response — {y_name}", report)
        self._gs_log(f"Gas response ({y_name}): {res.response_percent:.4g}% "
                     f"t90={res.response_time if res.response_time is not None else '-'}")
        self.notify(f"Response ของ {y_name}: {res.response_percent:.4g}% "
                    f"(sensitivity {res.sensitivity:.4g})")

    def gs_detect_cycles(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล", "เปิดไฟล์หรือคลิก Book ที่มีข้อมูลก่อน")
            return
        x_name, y_options, _cols = self._gs_x_and_options()
        if not y_options:
            self.inform("ข้อมูลไม่พอ", "ต้องมีคอลัมน์สัญญาณนอกจากคอลัมน์เวลา")
            return
        y_sel = self.selected_y_column()
        res_form = self.ask_form("Detect Gas Cycles", [
            {"name": "y_col", "label": "Signal (Y)", "kind": "choice", "options": y_options,
             "default": y_sel if y_sel in y_options else y_options[0]},
            {"name": "threshold_pct", "label": "Deviation from baseline (%)", "kind": "float",
             "default": 5.0, "min": 0.1, "max": 500.0, "decimals": 2},
        ], description=f"Find spans where the signal changes past the threshold (X axis = {x_name})")
        if res_form is None:
            return
        y_name = res_form["y_col"]
        threshold_pct = res_form["threshold_pct"]
        t = self._gs_time_seconds(x_name)
        y = pd.to_numeric(self._df[y_name], errors="coerce").to_numpy(dtype=float)
        try:
            cycles = detect_gas_cycles(t, y, rel_threshold=float(threshold_pct) / 100.0)
        except Exception as e:
            self.error_box("ตรวจจับไม่สำเร็จ", f"สาเหตุ: {e}")
            return
        if not cycles:
            self.inform("ไม่พบรอบแก๊ส",
                        "ไม่พบช่วงที่สัญญาณเบี่ยงเบนเกินเกณฑ์ — ลองลดเกณฑ์ %")
            return
        lines = [f"พบ {len(cycles)} รอบ (เกณฑ์ {threshold_pct:g}%):", ""]
        for i, (t_on, t_off) in enumerate(cycles, start=1):
            try:
                res = analyze_response(t, y, t_on, t_off)
                lines.append(
                    f"รอบ {i}: {t_on:.6g}→{t_off:.6g}  "
                    f"response {res.response_percent:.4g}%  "
                    f"t90 {res.response_time if res.response_time is not None else '-'}")
            except Exception:
                lines.append(f"รอบ {i}: {t_on:.6g}→{t_off:.6g} (คำนวณ response ไม่ได้)")
        self.inform(f"รอบเปิด-ปิดแก๊ส — {y_name}", "\n".join(lines))
        self._gs_log(f"Gas cycles ({y_name}): {len(cycles)} รอบ")

    def gs_calibration(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล", "เปิดตารางความเข้มข้น-response ใน Book ก่อน")
            return
        cols = [str(c) for c in self._df.columns]
        if len(cols) < 2:
            self.inform("ข้อมูลไม่พอ", "ต้องมีคอลัมน์ความเข้มข้นและคอลัมน์ response")
            return
        res_form = self.ask_form("Calibration Curve + LOD", [
            {"name": "conc_col", "label": "Concentration column", "kind": "choice",
             "options": cols, "default": cols[0]},
            {"name": "resp_col", "label": "Response column", "kind": "choice",
             "options": cols, "default": cols[1]},
            {"name": "model", "label": "Model", "kind": "choice",
             "options": ["linear", "power"], "default": "linear"},
            {"name": "noise_std", "label": "Noise σ (0 = skip LOD)", "kind": "float",
             "default": 0.0, "min": 0.0, "max": 1e12, "decimals": 6},
        ], description="Fit a calibration curve + compute LOD/LOQ, then plot a new graph")
        if res_form is None:
            return
        conc_col, resp_col = res_form["conc_col"], res_form["resp_col"]
        model, noise_std = res_form["model"], res_form["noise_std"]
        if conc_col == resp_col:
            self.inform("Duplicate column", "Concentration and response must be different columns")
            return
        conc = pd.to_numeric(self._df[conc_col], errors="coerce").to_numpy(dtype=float)
        resp = pd.to_numeric(self._df[resp_col], errors="coerce").to_numpy(dtype=float)
        try:
            fit = calibration_curve(conc, resp, model=model)
        except Exception as e:
            self.error_box("Fit ไม่สำเร็จ", f"สาเหตุ: {e}")
            return

        lines = [f"โมเดล: {fit['model']}"]
        if fit["model"] == "linear":
            slope = fit["slope"]
            lines.append(f"slope: {slope:.6g}   intercept: {fit['intercept']:.6g}")
        else:
            slope = None
            lines.append(f"response = {fit['a']:.6g} × conc^{fit['b']:.4g}")
        lines.append(f"R²: {fit['r_squared']:.6g}")
        if noise_std > 0:
            if fit["model"] == "linear" and slope:
                lod, loq = limit_of_detection(slope, float(noise_std))
                lines.append(f"LOD (3σ/slope): {lod:.6g}   LOQ (10σ/slope): {loq:.6g}")
            else:
                lines.append("LOD/LOQ: รองรับเฉพาะโมเดล linear")

        # กราฟ calibration: จุดข้อมูล + เส้น fit บน Graph ใหม่ (แบบ Origin)
        try:
            self.tabs.add_tab()
            tab = self.tabs.currentWidget()
            ax = tab.get_axes()
            good = np.isfinite(conc) & np.isfinite(resp)
            ax.scatter(conc[good], resp[good], s=28, label="data")
            xs = np.linspace(np.nanmin(conc[good]), np.nanmax(conc[good]), 200)
            ax.plot(xs, fit["predict"](xs), linewidth=2,
                    label=f"{fit['model']} fit (R²={fit['r_squared']:.4g})")
            ax.set_xlabel(conc_col)
            ax.set_ylabel(resp_col)
            ax.legend(loc="best")
            beautify_axes(ax, title=f"Calibration: {resp_col} vs {conc_col}")
            tab.draw()
            self._show_plot_view()
        except Exception:
            logger.debug("calibration plot skipped", exc_info=True)

        self.inform("Calibration Curve", "\n".join(lines))
        self._gs_log(f"Calibration {resp_col} vs {conc_col}: R²={fit['r_squared']:.4g}")

    def gs_dilution(self):
        res_form = self.ask_form("Gas Dilution (ppm)", [
            {"name": "source_ppm", "label": "Source concentration (ppm)", "kind": "float",
             "default": 1000.0, "min": 0.0, "max": 1e12, "decimals": 4},
            {"name": "flow_gas", "label": "Gas flow (sccm)", "kind": "float",
             "default": 10.0, "min": 1e-9, "max": 1e12, "decimals": 4},
            {"name": "flow_total", "label": "Total flow (sccm)", "kind": "float",
             "default": 100.0, "min": 1e-9, "max": 1e12, "decimals": 4},
        ], description="Diluted ppm = source × (flow_gas / flow_total)")
        if res_form is None:
            return
        source_ppm = res_form["source_ppm"]
        flow_gas = res_form["flow_gas"]
        flow_total = res_form["flow_total"]
        try:
            ppm = dilution_ppm(float(source_ppm), float(flow_gas), float(flow_total))
        except Exception as e:
            self.error_box("คำนวณไม่สำเร็จ", f"สาเหตุ: {e}")
            return
        self.inform(
            "ผลการเจือจางแก๊ส",
            f"{source_ppm:g} ppm × ({flow_gas:g} / {flow_total:g}) = {ppm:.6g} ppm")
        self._gs_log(f"Gas dilution: {ppm:.6g} ppm")
