from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core.gas_daq import GasDaqController, NIDaqmxBackend


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeDaqBackend:
    def __init__(self):
        self.open_args = None
        self.closed = False
        self.samples = []
        self.read_error = None

    def dependency_status(self):
        return True, "available"

    def available_devices(self):
        return [{"name": "Dev1", "product_type": "USB-6008", "serial_number": "42"}]

    def available_channels(self, device_name):
        assert device_name == "Dev1"
        return ["Dev1/ai0", "Dev1/ai1"]

    def open(self, *args):
        self.open_args = args
        self.closed = False

    def read_available(self):
        if self.read_error is not None:
            raise self.read_error
        result, self.samples = self.samples, []
        return result

    def close(self):
        self.closed = True


def test_nidaq_backend_normalizes_single_and_multi_channel_reads():
    assert NIDaqmxBackend._normalize_read_data(1.25, 1) == [[1.25]]
    assert NIDaqmxBackend._normalize_read_data([1.0, 2.0], 1) == [[1.0], [2.0]]
    assert NIDaqmxBackend._normalize_read_data([[1.0, 2.0], [3.0, 4.0]], 2) == [
        [1.0, 3.0], [2.0, 4.0]
    ]
    with pytest.raises(RuntimeError, match="uneven"):
        NIDaqmxBackend._normalize_read_data([[1.0], [2.0, 3.0]], 2)

    class TerminalValues:
        RSE = object()
        DIFF = object()

    assert NIDaqmxBackend._resolve_terminal(TerminalValues, "RSE") is TerminalValues.RSE
    assert (
        NIDaqmxBackend._resolve_terminal(TerminalValues, "DIFFERENTIAL")
        is TerminalValues.DIFF
    )


def test_daq_controller_enumerates_and_validates_configuration(qapp):
    backend = FakeDaqBackend()
    controller = GasDaqController(backend=backend)
    assert controller.available_devices()[0]["product_type"] == "USB-6008"
    assert controller.available_channels("Dev1") == ["Dev1/ai0", "Dev1/ai1"]
    assert controller.column_names(["Dev1/ai0", "Dev1/ai1"]) == [
        "ai0_voltage_v", "ai1_voltage_v"
    ]
    assert not controller.connect_device("", "Dev1/ai0")[0]
    assert not controller.connect_device("Dev1", "", 10)[0]
    assert not controller.connect_device("Dev1", "Dev1/ai0", 21)[0]
    assert not controller.connect_device("Dev1", "Dev1/ai0", 10, 5, 0)[0]
    assert backend.open_args is None


def test_daq_controller_batches_all_samples_and_preserves_markers(qapp):
    backend = FakeDaqBackend()
    now = [100.0]
    controller = GasDaqController(backend=backend, clock=lambda: now[0])
    records = []
    raw = []
    markers = []
    controller.records_ready.connect(records.extend)
    controller.raw_lines_ready.connect(raw.extend)
    controller.marker_created.connect(lambda *args: markers.append(args))

    ok, message = controller.connect_device(
        "Dev1", "Dev1/ai0", 10.0, 0.0, 5.0, "RSE"
    )
    assert ok and "Dev1/ai0" in message
    assert backend.open_args == ("Dev1", ["Dev1/ai0"], 10.0, 0.0, 5.0, "RSE")
    now[0] = 100.2
    assert controller.mark_exposure("on", "ethanol")[0]
    backend.samples = [[1.0], [1.1], [1.2]]
    assert controller.poll_available() == 3
    assert controller.flush_pending() == 3

    assert [row["ai0_voltage_v"] for row in records] == [1.0, 1.1, 1.2]
    assert [row["elapsed_s"] for row in records] == pytest.approx([0.0, 0.1, 0.2])
    assert records[0]["event"] == "gas_on:ethanol"
    assert records[0]["gas_state"] == "on"
    assert len(raw) == 3 and "ai0_voltage_v=1" in raw[0]
    assert markers[0][0] == "on"
    assert markers[0][1] == pytest.approx(0.2)
    status = controller.status()
    assert status["transport"] == "ni_daq"
    assert status["configured_rate_hz"] == 10.0
    assert status["samples"] == 3

    controller.disconnect_device()
    assert backend.closed and not controller.connected


def test_daq_controller_flushes_marker_only_row_on_disconnect(qapp):
    backend = FakeDaqBackend()
    controller = GasDaqController(backend=backend)
    records = []
    controller.records_ready.connect(records.extend)
    assert controller.connect_device("Dev1", "Dev1/ai0", 5.0)[0]
    backend.samples = [[2.5]]
    controller.poll_available()
    controller.flush_pending()
    controller.mark_exposure("off")
    controller.disconnect_device()
    assert len(records) == 2
    assert records[-1]["ai0_voltage_v"] is None
    assert records[-1]["event"] == "gas_off"


def test_daq_controller_read_error_disconnects_and_flushes(qapp):
    backend = FakeDaqBackend()
    controller = GasDaqController(backend=backend)
    states = []
    errors = []
    controller.state_changed.connect(lambda *args: states.append(args))
    controller.parse_errors.connect(errors.extend)
    assert controller.connect_device("Dev1", "Dev1/ai0")[0]
    backend.read_error = RuntimeError("DAQ device was removed")
    assert controller.poll_available() == 0
    assert not controller.connected and backend.closed
    assert errors == ["DAQ device was removed"]
    assert states[-1] == (False, "DAQ device was removed")


def test_daq_controller_acquires_multiple_selected_channels(qapp):
    backend = FakeDaqBackend()
    controller = GasDaqController(backend=backend)
    records = []
    controller.records_ready.connect(records.extend)
    assert controller.connect_device(
        "Dev1", "Dev1/ai0,Dev1/ai1", 20.0, -10.0, 10.0, "DIFFERENTIAL"
    )[0]
    assert backend.open_args[1] == ["Dev1/ai0", "Dev1/ai1"]
    backend.samples = [[1.0, 2.0], [1.1, 2.1]]
    controller.poll_available()
    controller.flush_pending()
    assert records[0]["ai0_voltage_v"] == 1.0
    assert records[0]["ai1_voltage_v"] == 2.0
    assert records[1]["ai0_voltage_v"] == 1.1
    assert records[1]["ai1_voltage_v"] == 2.1
    controller.disconnect_device()
