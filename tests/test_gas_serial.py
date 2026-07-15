from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtSerialPort import QSerialPort
from PySide6.QtWidgets import QApplication

from analysis.gas_serial import SerialFrameParser
from core.gas_live import GasLiveController


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeSerialPort(QObject):
    readyRead = Signal()
    errorOccurred = Signal(object)

    def __init__(self):
        super().__init__()
        self.name = ""
        self.baud = 0
        self.opened = False
        self.buffer = bytearray()
        self.open_result = True
        self.error_text = "fake serial error"

    def setPortName(self, value):
        self.name = value

    def setBaudRate(self, value):
        self.baud = value
        return True

    def open(self, _mode):
        self.opened = bool(self.open_result)
        return self.opened

    def isOpen(self):
        return self.opened

    def close(self):
        self.opened = False

    def errorString(self):
        return self.error_text

    def readAll(self):
        result = bytes(self.buffer)
        self.buffer.clear()
        return result

    def feed(self, data: bytes):
        self.buffer.extend(data)
        self.readyRead.emit()


def test_json_parser_handles_fragments_and_locks_schema():
    parser = SerialFrameParser()
    first = parser.feed(b'{"resistance":100,')
    second = parser.feed(b'"temperature":25}\r\n')
    changed = parser.feed(b'{"resistance":90,"temperature":26,"extra":7}\n')
    malformed = parser.feed(b'{bad json}\n')

    assert first.records == []
    assert second.records == [{"resistance": 100, "temperature": 25}]
    assert parser.mode == "json"
    assert parser.schema == ("resistance", "temperature")
    assert changed.records == [{"resistance": 90, "temperature": 26}]
    assert "ignored field(s): extra" in changed.errors[0]
    assert malformed.records == [] and "Invalid JSON" in malformed.errors[0]


def test_csv_parser_requires_header_and_reports_bad_rows_and_missing_values():
    parser = SerialFrameParser()
    header = parser.feed("time,resistance,resistance,humidity\n")
    good = parser.feed("0,100,,45.5\n")
    bad = parser.feed("1,90\n")

    assert header.records == []
    assert parser.mode == "csv"
    assert parser.schema == ("time", "resistance", "resistance.1", "humidity")
    assert good.records == [{
        "time": 0, "resistance": 100, "resistance.1": None, "humidity": 45.5
    }]
    assert bad.records == [] and "expected 4" in bad.errors[0]


def test_parser_flushes_final_line_and_rejects_non_numeric_record():
    parser = SerialFrameParser()
    parser.feed(b'{"status":"ready"}')
    result = parser.flush()
    assert result.records == []
    assert "numeric field" in result.errors[0]


def test_controller_batches_all_samples_and_decorates_markers(qapp):
    fake = FakeSerialPort()
    now = [10.0]
    controller = GasLiveController(serial_port=fake, clock=lambda: now[0])
    batches = []
    markers = []
    controller.records_ready.connect(lambda rows: batches.extend(rows))
    controller.marker_created.connect(lambda *args: markers.append(args))

    assert controller.connect_port("COM_TEST", 115200)[0]
    now[0] = 10.5
    fake.feed(b'{"resistance":100,"voltage":1.2}\n')
    assert controller.mark_exposure("on", "sample A")[0]
    now[0] = 10.7
    fake.feed(b'{"resistance":90,"voltage":1.3}\n')
    assert controller.flush_pending() == 2

    assert len(batches) == 2
    assert batches[0]["elapsed_s"] == pytest.approx(0.5)
    assert batches[0]["gas_state"] == "unknown"
    assert batches[1]["gas_state"] == "on"
    assert batches[1]["event"] == "gas_on:sample A"
    assert markers[0][0] == "on" and markers[0][1] == pytest.approx(0.5)
    assert markers[0][2] == "gas_on:sample A"
    assert controller.status()["samples"] == 2


def test_controller_preserves_multiple_markers_before_the_next_sample(qapp):
    fake = FakeSerialPort()
    controller = GasLiveController(serial_port=fake)
    records = []
    controller.records_ready.connect(lambda rows: records.extend(rows))
    assert controller.connect_port("COM_MARKERS")[0]
    controller.mark_exposure("on")
    controller.mark_exposure("off")
    fake.feed(b'{"value":1}\n')
    controller.flush_pending()
    assert records[0]["event"] == "gas_on;gas_off"
    assert records[0]["gas_state"] == "off"


def test_controller_flushes_event_only_row_when_disconnect_precedes_next_sample(qapp):
    fake = FakeSerialPort()
    controller = GasLiveController(serial_port=fake)
    records = []
    controller.records_ready.connect(lambda rows: records.extend(rows))
    assert controller.connect_port("COM_EVENT")[0]
    fake.feed(b'{"resistance":100}\n')
    controller.flush_pending()
    controller.mark_exposure("on")
    controller.disconnect_port()

    assert len(records) == 2
    assert records[-1]["resistance"] is None
    assert records[-1]["gas_state"] == "on"
    assert records[-1]["event"] == "gas_on"
    assert controller.status()["samples"] == 1


def test_controller_has_no_loss_at_twenty_hz_and_flushes_tail_on_disconnect(qapp):
    fake = FakeSerialPort()
    now = [0.0]
    controller = GasLiveController(serial_port=fake, clock=lambda: now[0])
    records = []
    controller.records_ready.connect(lambda rows: records.extend(rows))
    assert controller.connect_port("COM_RATE")[0]
    payload = b"".join(
        f'{{"value":{index}}}\n'.encode("ascii") for index in range(200)
    )
    now[0] = 10.0
    fake.feed(payload)
    fake.feed(b'{"value":200}')
    controller.disconnect_port("done")

    assert len(records) == 201
    assert records[-1]["value"] == 200
    assert controller.status()["samples"] == 201
    assert not controller.connected and not fake.opened


def test_controller_fatal_serial_error_disconnects(qapp):
    fake = FakeSerialPort()
    controller = GasLiveController(serial_port=fake)
    states = []
    controller.state_changed.connect(lambda connected, message: states.append((connected, message)))
    assert controller.connect_port("COM_ERR")[0]
    fake.errorOccurred.emit(QSerialPort.SerialPortError.ResourceError)
    assert not controller.connected
    assert states[-1] == (False, "fake serial error")
