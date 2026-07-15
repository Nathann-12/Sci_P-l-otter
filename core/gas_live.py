"""Qt serial acquisition controller for the Gas Sensor module."""
from __future__ import annotations

import time
from typing import Any, Callable

from PySide6.QtCore import QIODevice, QObject, QTimer, Signal
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

from analysis.gas_serial import SerialFrameParser, SerialParseBatch


class GasLiveController(QObject):
    """Own a receive-only serial session and emit parsed records in UI batches."""

    state_changed = Signal(bool, str)
    records_ready = Signal(object)
    raw_lines_ready = Signal(object)
    parse_errors = Signal(object)
    marker_created = Signal(str, float, str)

    def __init__(
        self,
        parent=None,
        *,
        serial_port=None,
        clock: Callable[[], float] | None = None,
        batch_interval_ms: int = 200,
    ) -> None:
        super().__init__(parent)
        self._port = serial_port if serial_port is not None else QSerialPort(self)
        self._clock = clock or time.monotonic
        self._parser = SerialFrameParser()
        self._pending: list[dict[str, Any]] = []
        self._connected = False
        self._port_name = ""
        self._baud = 115200
        self._started_at: float | None = None
        self._sample_count = 0
        self._error_count = 0
        self._gas_state = "unknown"
        self._pending_events: list[str] = []
        self._last_message = "Disconnected"
        self._timer = QTimer(self)
        self._timer.setInterval(max(20, int(batch_interval_ms)))
        self._timer.timeout.connect(self.flush_pending)
        self._port.readyRead.connect(self._read_ready)
        self._port.errorOccurred.connect(self._on_serial_error)

    @staticmethod
    def available_ports() -> list[dict[str, str]]:
        result = []
        for info in QSerialPortInfo.availablePorts():
            result.append({
                "name": info.portName(),
                "description": info.description(),
                "manufacturer": info.manufacturer(),
                "serial_number": info.serialNumber(),
            })
        return result

    @property
    def connected(self) -> bool:
        return self._connected

    def connect_port(self, port_name: str, baud: int = 115200) -> tuple[bool, str]:
        port_name = str(port_name or "").strip()
        if not port_name:
            return False, "Select a serial port first."
        if self._connected:
            return False, f"Already connected to {self._port_name}."
        self._parser.reset()
        self._pending.clear()
        self._sample_count = 0
        self._error_count = 0
        self._gas_state = "unknown"
        self._pending_events.clear()
        self._port_name = port_name
        self._baud = int(baud)
        self._port.setPortName(port_name)
        self._port.setBaudRate(self._baud)
        if not self._port.open(QIODevice.ReadOnly):
            message = self._port.errorString() or f"Could not open {port_name}."
            self._last_message = message
            self.state_changed.emit(False, message)
            return False, message
        self._connected = True
        self._started_at = self._clock()
        self._last_message = f"Connected to {port_name} @ {self._baud}"
        self._timer.start()
        self.state_changed.emit(True, self._last_message)
        return True, self._last_message

    def disconnect_port(self, reason: str = "Disconnected") -> None:
        if self._connected:
            self._accept_batch(self._parser.flush())
            # Preserve a marker even when the user disconnects before the next
            # sensor sample. Event-only rows keep the locked device schema and
            # therefore append cleanly to the same Live Book.
            if self._pending_events and self._parser.schema:
                marker_row = {"elapsed_s": self._elapsed()}
                marker_row.update({key: None for key in self._parser.schema})
                marker_row["gas_state"] = self._gas_state
                marker_row["event"] = ";".join(self._pending_events)
                self._pending_events.clear()
                self._pending.append(marker_row)
            self.flush_pending()
        self._timer.stop()
        if self._port.isOpen():
            self._port.close()
        was_connected = self._connected
        self._connected = False
        self._last_message = reason
        if was_connected or reason != "Disconnected":
            self.state_changed.emit(False, reason)

    def ingest_bytes(self, data: bytes | bytearray | str) -> None:
        """Public test/transport seam; real sessions call it from ``readyRead``."""
        self._accept_batch(self._parser.feed(data))

    def flush_pending(self) -> int:
        if not self._pending:
            return 0
        records = list(self._pending)
        self._pending.clear()
        self.records_ready.emit(records)
        return len(records)

    def mark_exposure(self, state: str, label: str = "") -> tuple[bool, str]:
        if not self._connected:
            return False, "Gas live acquisition is not connected."
        normalized = str(state).strip().lower()
        if normalized not in {"on", "off"}:
            return False, "Marker state must be 'on' or 'off'."
        self._gas_state = normalized
        event = f"gas_{normalized}"
        clean_label = str(label or "").strip()
        if clean_label:
            event = f"{event}:{clean_label}"
        self._pending_events.append(event)
        elapsed = self._elapsed()
        self.marker_created.emit(normalized, elapsed, event)
        return True, f"Marked gas {normalized.upper()} at {elapsed:.3f} s."

    def status(self) -> dict[str, Any]:
        elapsed = self._elapsed()
        rate = self._sample_count / elapsed if elapsed > 0 else 0.0
        return {
            "transport": "serial",
            "connected": self._connected,
            "port": self._port_name,
            "baud": self._baud,
            "samples": self._sample_count,
            "sample_rate_hz": rate,
            "parse_errors": self._error_count,
            "format": self._parser.mode or "pending",
            "schema": list(self._parser.schema),
            "elapsed_s": elapsed,
            "message": self._last_message,
        }

    def close(self) -> None:
        self.disconnect_port("Application closing")

    def _elapsed(self) -> float:
        if self._started_at is None:
            return 0.0
        return max(0.0, float(self._clock() - self._started_at))

    def _read_ready(self) -> None:
        self.ingest_bytes(bytes(self._port.readAll()))

    def _accept_batch(self, batch: SerialParseBatch) -> None:
        if batch.raw_lines:
            self.raw_lines_ready.emit(batch.raw_lines)
        if batch.errors:
            self._error_count += len(batch.errors)
            self.parse_errors.emit(batch.errors)
        for source in batch.records:
            record = {"elapsed_s": self._elapsed(), **source}
            record["gas_state"] = self._gas_state
            record["event"] = ";".join(self._pending_events)
            self._pending_events.clear()
            self._pending.append(record)
            self._sample_count += 1

    def _on_serial_error(self, error) -> None:
        try:
            no_error = QSerialPort.SerialPortError.NoError
            fatal_errors = {
                QSerialPort.SerialPortError.ResourceError,
                QSerialPort.SerialPortError.DeviceNotFoundError,
                QSerialPort.SerialPortError.PermissionError,
            }
        except AttributeError:
            return
        if error == no_error or not self._connected:
            return
        message = self._port.errorString() or "Serial port error"
        if error in fatal_errors:
            self.disconnect_port(message)
        else:
            self._last_message = message
            self.state_changed.emit(True, message)
