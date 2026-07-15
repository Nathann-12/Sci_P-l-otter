"""NI-DAQmx analog-input acquisition for the Gas Sensor module.

The NI dependency is loaded lazily so SciPlotter remains usable on machines
that do not have NI hardware or the NI-DAQmx runtime installed.
"""
from __future__ import annotations

import math
import logging
import re
import time
from typing import Any, Callable, Iterable

from PySide6.QtCore import QObject, QTimer, Signal


logger = logging.getLogger(__name__)


class NIDaqmxBackend:
    """Small adapter around nidaqmx, kept injectable for headless tests."""

    def __init__(self) -> None:
        self._task = None
        self._channel_count = 0

    @staticmethod
    def _api():
        try:
            import nidaqmx
            from nidaqmx.constants import (
                AcquisitionType,
                TerminalConfiguration,
            )
        except (ImportError, OSError) as exc:
            raise RuntimeError(
                "NI-DAQmx support is not installed. Install the NI-DAQmx driver "
                "and run: pip install nidaqmx"
            ) from exc
        return nidaqmx, AcquisitionType, TerminalConfiguration

    def dependency_status(self) -> tuple[bool, str]:
        try:
            nidaqmx, _acquisition_type, _terminal_configuration = self._api()
            nidaqmx.system.System.local()
        except Exception as exc:
            text = " ".join(str(exc).strip().split())
            return False, (text or "NI-DAQmx driver is unavailable.")[:240]
        return True, "NI-DAQmx is available."

    def available_devices(self) -> list[dict[str, str]]:
        nidaqmx, _acquisition_type, _terminal_configuration = self._api()
        devices = nidaqmx.system.System.local().devices
        return [
            {
                "name": str(device.name),
                "product_type": str(getattr(device, "product_type", "") or ""),
                "serial_number": str(getattr(device, "dev_serial_num", "") or ""),
            }
            for device in devices
        ]

    def available_channels(self, device_name: str) -> list[str]:
        nidaqmx, _acquisition_type, _terminal_configuration = self._api()
        device = nidaqmx.system.System.local().devices[str(device_name)]
        return [str(channel.name) for channel in device.ai_physical_chans]

    def open(
        self,
        device_name: str,
        channels: list[str],
        sample_rate_hz: float,
        min_voltage: float,
        max_voltage: float,
        terminal_config: str,
    ) -> None:
        nidaqmx, acquisition_type, terminal_configuration = self._api()
        terminal_key = str(terminal_config or "RSE").strip().upper()
        terminal = self._resolve_terminal(terminal_configuration, terminal_key)
        if terminal is None:
            raise ValueError(f"Unsupported terminal configuration: {terminal_config}")
        task = nidaqmx.Task(new_task_name="SciPlotter_Gas_Live")
        try:
            for channel in channels:
                physical = str(channel)
                if "/" not in physical:
                    physical = f"{device_name}/{physical}"
                task.ai_channels.add_ai_voltage_chan(
                    physical,
                    terminal_config=terminal,
                    min_val=float(min_voltage),
                    max_val=float(max_voltage),
                )
            buffer_samples = max(10, int(math.ceil(float(sample_rate_hz) * 5.0)))
            task.timing.cfg_samp_clk_timing(
                rate=float(sample_rate_hz),
                sample_mode=acquisition_type.CONTINUOUS,
                samps_per_chan=buffer_samples,
            )
            task.start()
        except Exception:
            task.close()
            raise
        self._task = task
        self._channel_count = len(channels)

    @staticmethod
    def _resolve_terminal(terminal_configuration, key: str):
        attribute = "DIFF" if str(key).upper() == "DIFFERENTIAL" else str(key).upper()
        return getattr(terminal_configuration, attribute, None)

    def read_available(self) -> list[list[float]]:
        if self._task is None:
            return []
        count = int(self._task.in_stream.avail_samp_per_chan)
        if count <= 0:
            return []
        data = self._task.read(number_of_samples_per_channel=count, timeout=0.0)
        return self._normalize_read_data(data, self._channel_count)

    @staticmethod
    def _normalize_read_data(data: Any, channel_count: int) -> list[list[float]]:
        """Normalize nidaqmx scalar/1-D/2-D read shapes into sample rows."""
        if channel_count <= 0:
            return []
        if channel_count == 1:
            values = data if isinstance(data, (list, tuple)) else [data]
            return [[float(value)] for value in values]
        if not isinstance(data, (list, tuple)) or len(data) != channel_count:
            raise RuntimeError("NI-DAQmx returned an unexpected multi-channel data shape.")
        per_channel = [
            values if isinstance(values, (list, tuple)) else [values]
            for values in data
        ]
        sample_counts = {len(values) for values in per_channel}
        if len(sample_counts) != 1:
            raise RuntimeError("NI-DAQmx returned uneven channel sample counts.")
        return [
            [float(per_channel[channel][sample]) for channel in range(channel_count)]
            for sample in range(next(iter(sample_counts), 0))
        ]

    def close(self) -> None:
        task, self._task = self._task, None
        self._channel_count = 0
        if task is None:
            return
        try:
            task.stop()
        except Exception:
            logger.debug("NI-DAQ task stop skipped", exc_info=True)
        task.close()


class GasDaqController(QObject):
    """Acquire hardware-timed NI analog-input samples in UI-safe batches."""

    state_changed = Signal(bool, str)
    records_ready = Signal(object)
    raw_lines_ready = Signal(object)
    parse_errors = Signal(object)
    marker_created = Signal(str, float, str)

    def __init__(
        self,
        parent=None,
        *,
        backend=None,
        clock: Callable[[], float] | None = None,
        batch_interval_ms: int = 200,
        poll_interval_ms: int = 50,
    ) -> None:
        super().__init__(parent)
        self._backend = backend if backend is not None else NIDaqmxBackend()
        self._clock = clock or time.monotonic
        self._pending: list[dict[str, Any]] = []
        self._connected = False
        self._device = ""
        self._channels: list[str] = []
        self._columns: list[str] = []
        self._sample_rate_hz = 10.0
        self._min_voltage = 0.0
        self._max_voltage = 5.0
        self._terminal_config = "RSE"
        self._started_at: float | None = None
        self._sample_count = 0
        self._error_count = 0
        self._gas_state = "unknown"
        self._pending_events: list[str] = []
        self._last_message = "Disconnected"
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(max(20, int(poll_interval_ms)))
        self._poll_timer.timeout.connect(self.poll_available)
        self._batch_timer = QTimer(self)
        self._batch_timer.setInterval(max(20, int(batch_interval_ms)))
        self._batch_timer.timeout.connect(self.flush_pending)

    @property
    def connected(self) -> bool:
        return self._connected

    def dependency_status(self) -> tuple[bool, str]:
        return self._backend.dependency_status()

    def available_devices(self) -> list[dict[str, str]]:
        return self._backend.available_devices()

    def available_channels(self, device_name: str) -> list[str]:
        return self._backend.available_channels(device_name)

    def column_names(self, channels: Iterable[str]) -> list[str]:
        """Return the stable Live Book field names for physical AI channels."""
        return self._column_names([str(channel) for channel in channels])

    def connect_device(
        self,
        device_name: str,
        channels: str | Iterable[str],
        sample_rate_hz: float = 10.0,
        min_voltage: float = 0.0,
        max_voltage: float = 5.0,
        terminal_config: str = "RSE",
    ) -> tuple[bool, str]:
        device_name = str(device_name or "").strip()
        if isinstance(channels, str):
            channel_list = [item.strip() for item in channels.split(",") if item.strip()]
        else:
            channel_list = [str(item).strip() for item in channels if str(item).strip()]
        try:
            rate = float(sample_rate_hz)
            lower, upper = float(min_voltage), float(max_voltage)
        except (TypeError, ValueError):
            return False, "NI-DAQ rate and voltage range must be numeric."
        terminal = str(terminal_config or "RSE").strip().upper()
        if not device_name:
            return False, "Select an NI-DAQ device first."
        if not channel_list:
            return False, "Select at least one analog-input channel."
        if not 1.0 <= rate <= 20.0:
            return False, "NI-DAQ sample rate must be between 1 and 20 Hz."
        if not lower < upper:
            return False, "NI-DAQ minimum voltage must be below maximum voltage."
        if terminal not in {"RSE", "NRSE", "DIFFERENTIAL"}:
            return False, "NI-DAQ terminal mode must be RSE, NRSE, or Differential."
        if self._connected:
            return False, f"Already connected to {self._device}."

        columns = self._column_names(channel_list)
        try:
            self._backend.open(device_name, channel_list, rate, lower, upper, terminal)
        except Exception as exc:
            message = self._short_error(exc)
            self._last_message = message
            self.state_changed.emit(False, message)
            return False, message

        self._pending.clear()
        self._device = device_name
        self._channels = channel_list
        self._columns = columns
        self._sample_rate_hz = rate
        self._min_voltage = lower
        self._max_voltage = upper
        self._terminal_config = terminal
        self._sample_count = 0
        self._error_count = 0
        self._gas_state = "unknown"
        self._pending_events.clear()
        self._started_at = self._clock()
        self._connected = True
        channel_text = ", ".join(channel_list)
        self._last_message = f"Connected to {device_name}: {channel_text} @ {rate:g} Hz"
        self._poll_timer.start()
        self._batch_timer.start()
        self.state_changed.emit(True, self._last_message)
        return True, self._last_message

    def poll_available(self) -> int:
        if not self._connected:
            return 0
        try:
            samples = self._backend.read_available()
        except Exception as exc:
            self._error_count += 1
            message = self._short_error(exc)
            self.parse_errors.emit([message])
            self.disconnect_device(message, drain=False)
            return 0
        raw_lines = []
        for values in samples:
            if len(values) != len(self._columns):
                self._error_count += 1
                message = "NI-DAQ sample width did not match the selected channels."
                self.parse_errors.emit([message])
                continue
            elapsed = self._sample_count / self._sample_rate_hz
            record = {"elapsed_s": elapsed}
            record.update(zip(self._columns, (float(value) for value in values)))
            record["gas_state"] = self._gas_state
            record["event"] = ";".join(self._pending_events)
            self._pending_events.clear()
            self._pending.append(record)
            self._sample_count += 1
            raw_lines.append(
                ", ".join(f"{name}={record[name]:.9g}" for name in self._columns)
            )
        if raw_lines:
            self.raw_lines_ready.emit(raw_lines)
        return len(samples)

    def flush_pending(self) -> int:
        if not self._pending:
            return 0
        records = list(self._pending)
        self._pending.clear()
        self.records_ready.emit(records)
        return len(records)

    def disconnect_device(self, reason: str = "Disconnected", *, drain: bool = True) -> None:
        if self._connected and drain:
            self.poll_available()
            if not self._connected:
                return
        if self._connected and self._pending_events and self._columns:
            marker_row = {"elapsed_s": self._elapsed()}
            marker_row.update({column: None for column in self._columns})
            marker_row["gas_state"] = self._gas_state
            marker_row["event"] = ";".join(self._pending_events)
            self._pending_events.clear()
            self._pending.append(marker_row)
        self.flush_pending()
        self._poll_timer.stop()
        self._batch_timer.stop()
        try:
            self._backend.close()
        except Exception:
            logger.debug("NI-DAQ backend close failed", exc_info=True)
        was_connected = self._connected
        self._connected = False
        self._last_message = str(reason)
        if was_connected or reason != "Disconnected":
            self.state_changed.emit(False, self._last_message)

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
        measured_rate = self._sample_count / elapsed if elapsed > 0 else 0.0
        return {
            "transport": "ni_daq",
            "connected": self._connected,
            "device": self._device,
            "channels": list(self._channels),
            "schema": list(self._columns),
            "sample_rate_hz": measured_rate,
            "configured_rate_hz": self._sample_rate_hz,
            "samples": self._sample_count,
            "parse_errors": self._error_count,
            "acquisition_errors": self._error_count,
            "min_voltage": self._min_voltage,
            "max_voltage": self._max_voltage,
            "terminal_config": self._terminal_config,
            "elapsed_s": elapsed,
            "message": self._last_message,
        }

    def close(self) -> None:
        self.disconnect_device("Application closing")

    def _elapsed(self) -> float:
        if self._started_at is None:
            return 0.0
        return max(0.0, float(self._clock() - self._started_at))

    @staticmethod
    def _column_names(channels: list[str]) -> list[str]:
        result = []
        used: set[str] = set()
        for index, channel in enumerate(channels, start=1):
            short = str(channel).rsplit("/", 1)[-1]
            short = re.sub(r"[^0-9A-Za-z_]+", "_", short).strip("_") or f"ai{index - 1}"
            base = f"{short}_voltage_v"
            name, suffix = base, 2
            while name.casefold() in used:
                name = f"{base}_{suffix}"
                suffix += 1
            used.add(name.casefold())
            result.append(name)
        return result

    @staticmethod
    def _short_error(exc: Exception) -> str:
        text = " ".join(str(exc).strip().split())
        if not text:
            text = exc.__class__.__name__
        return text[:240]
