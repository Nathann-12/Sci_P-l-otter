"""Wire + behavior tests for the Gas Sensor module inside the real MainWindow
(headless). The math itself is covered in test_gas_sensor.py."""
from __future__ import annotations

import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QAbstractItemView, QApplication

from core.gas_live import GasLiveController
from core.gas_daq import GasDaqController


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    w.gs_live_configure_flow({})
    w.gs_live_configure_wiring([
        ["source", "divider"], ["divider", "smooth"],
        ["smooth", "book"], ["book", "graph"],
    ])
    yield w
    w.close()


def _stub_prompts(win, forms=()):
    """Feed scripted form results (one dict per ask_form call) and capture
    inform() calls."""
    reports = []
    form_iter = iter(forms)
    win.ask_form = lambda *a, **k: next(form_iter)
    win.inform = lambda title, text: reports.append((title, text))
    return reports


class _FakeSerialPort(QObject):
    readyRead = Signal()
    errorOccurred = Signal(object)

    def __init__(self):
        super().__init__()
        self.opened = False
        self.buffer = bytearray()
        self.port_name = ""
        self.baud = 0

    def setPortName(self, value):
        self.port_name = value

    def setBaudRate(self, value):
        self.baud = value
        return True

    def open(self, _mode):
        self.opened = True
        return True

    def isOpen(self):
        return self.opened

    def close(self):
        self.opened = False

    def errorString(self):
        return ""

    def readAll(self):
        data = bytes(self.buffer)
        self.buffer.clear()
        return data

    def feed(self, data: bytes):
        self.buffer.extend(data)
        self.readyRead.emit()


def _install_fake_live_controller(win):
    fake = _FakeSerialPort()
    now = [100.0]
    controller = GasLiveController(win, serial_port=fake, clock=lambda: now[0])
    controller.state_changed.connect(win._gs_live_state_changed)
    controller.records_ready.connect(win._gs_live_records_ready)
    controller.raw_lines_ready.connect(win.gas_sensor_panel.append_raw_lines)
    controller.parse_errors.connect(win._gs_live_parse_errors)
    controller.marker_created.connect(win._gs_live_marker_created)
    win.gas_live_controller = controller
    return fake, controller, now


class _FakeDaqBackend:
    def __init__(self):
        self.samples = []
        self.open_args = None
        self.closed = False

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
        result, self.samples = self.samples, []
        return result

    def close(self):
        self.closed = True


def _install_fake_daq_controller(win):
    backend = _FakeDaqBackend()
    now = [200.0]
    controller = GasDaqController(win, backend=backend, clock=lambda: now[0])
    controller.state_changed.connect(win._gs_live_daq_state_changed)
    controller.records_ready.connect(win._gs_live_records_ready)
    controller.raw_lines_ready.connect(win.gas_sensor_panel.append_raw_lines)
    controller.parse_errors.connect(win._gs_live_parse_errors)
    controller.marker_created.connect(win._gs_live_marker_created)
    win.gas_daq_controller = controller
    return backend, controller, now


def test_module_registered_in_modules_gallery_and_menu(win):
    assert win.shell.context_widget("modules") is win.modules_panel
    assert win.modules_panel.module_widget("gas_sensor") is win.gas_sensor_panel
    assert win.shell.context_widget("gas_sensor") is None
    assert win.shell.rail.isHidden()
    assert win.shell.context_stack.isHidden()

    win.show_module_gallery("gas_sensor")

    assert not win.shell.rail.isHidden()
    assert not win.shell.context_stack.isHidden()
    assert win.shell.current_context_id() == "modules"
    assert win.modules_panel.current_module_id() == "gas_sensor"

    win.modules_panel.close_button.click()
    assert win.shell.rail.isHidden()
    assert win.shell.context_stack.isHidden()

    win.show_module_gallery("gas_sensor")
    menu_titles = [a.text().replace("&", "") for a in win.menuBar().actions()]
    assert "Modules" in menu_titles
    assert "Gas Sensor" not in menu_titles
    modules_menu = next(
        action.menu()
        for action in win.menuBar().actions()
        if action.text().replace("&", "") == "Modules"
    )
    gas_menu = next(
        action.menu()
        for action in modules_menu.actions()
        if action.text().replace("&", "") == "Gas Sensor"
    )
    live_action = next(
        action for action in gas_menu.actions() if action.text() == "Live Acquisition..."
    )
    live_action.trigger()
    assert win.gas_sensor_panel.tabs.currentWidget() is win.gas_sensor_panel.live_tab
    flow_action = next(
        action
        for action in gas_menu.actions()
        if action.text() == "Visual Acquisition Flow..."
    )
    flow_action.trigger()
    assert win.gas_flow_designer is not None and win.gas_flow_designer.isVisible()
    for name in ("gs_analyze_response", "gs_detect_cycles",
                 "gs_calibration", "gs_dilution"):
        assert callable(getattr(win, name))


def test_gs_analyze_response_end_to_end(win):
    # synthetic exposure: Ra=100 → Rg=20 (exponential, tau=5)
    t = np.linspace(0, 300, 3001)
    y = np.full_like(t, 100.0)
    on = (t >= 50) & (t < 150)
    y[on] = 20 + 80 * np.exp(-(t[on] - 50) / 5.0)
    rec = t >= 150
    y[rec] = 100 - 80 * np.exp(-(t[rec] - 150) / 5.0)
    df = pd.DataFrame({"time": t, "resistance": y})
    win._stage_insert("gas.csv [ตาราง]", df, None)

    reports = _stub_prompts(
        win, forms=[{"y_col": "resistance", "t_on": 50.0, "t_off": 150.0}])
    win.gs_analyze_response()

    assert reports, "analysis must report via inform()"
    title, text = reports[-1]
    assert "resistance" in title
    assert "Response: 80" in text            # 80 %
    assert "Sensitivity" in text and "5" in text  # Ra/Rg = 5


def test_gs_detect_cycles_reports_three_pulses(win):
    t = np.linspace(0, 600, 6001)
    y = np.full_like(t, 100.0)
    for on, off in ((100, 150), (300, 350), (500, 550)):
        y[(t >= on) & (t <= off)] = 30.0
    df = pd.DataFrame({"time": t, "r": y})
    win._stage_insert("cycles.csv [ตาราง]", df, None)

    reports = _stub_prompts(
        win, forms=[{"y_col": "r", "threshold_pct": 5.0}])
    win.gs_detect_cycles()

    assert reports
    _title, text = reports[-1]
    assert "พบ 3 รอบ" in text


def test_gs_calibration_plots_new_graph_and_reports_lod(win):
    conc = [10.0, 20.0, 50.0, 100.0]
    resp = [0.4 * c + 2.0 for c in conc]
    df = pd.DataFrame({"conc": conc, "resp": resp})
    win._stage_insert("calib.csv [ตาราง]", df, None)

    graphs_before = win.tabs.count()
    reports = _stub_prompts(win, forms=[{
        "conc_col": "conc", "resp_col": "resp", "model": "linear", "noise_std": 0.2}])
    win.gs_calibration()

    assert win.tabs.count() == graphs_before + 1  # new calibration Graph
    _title, text = reports[-1]
    assert "slope: 0.4" in text
    assert "R²: 1" in text
    assert "LOD" in text and "1.5" in text  # 3*0.2/0.4 = 1.5


def test_gs_dilution_computes_ppm(win):
    reports = _stub_prompts(win, forms=[{
        "source_ppm": 1000.0, "flow_gas": 2.0, "flow_total": 100.0}])
    win.gs_dilution()

    _title, text = reports[-1]
    assert "20 ppm" in text


def test_gas_live_stream_creates_dedicated_book_graph_and_markers(win, qapp):
    fake, controller, now = _install_fake_live_controller(win)
    assert win.gs_live_connect("COM_TEST", 115200)[0]

    now[0] = 100.1
    fake.feed(b'{"resistance":100,"voltage":1.0,"temperature":25,"humidity":40}\n')
    controller.flush_pending()
    qapp.processEvents()

    name = win._gs_live_dataset_name
    workbook = win._gs_live_workbook
    graph_id = win._gs_live_graph_id
    assert name.startswith("Live Gas ") and name in win._datasets
    assert workbook.source_df.shape == (1, 7)
    assert list(workbook.source_df.columns) == [
        "elapsed_s", "resistance", "voltage", "temperature", "humidity",
        "gas_state", "event",
    ]
    assert workbook.table.editTriggers() == QAbstractItemView.NoEditTriggers
    assert graph_id in win.tabs.tabs
    assert win._gs_live_signal == "resistance"
    assert len(win._gs_live_line.get_xdata()) == 1

    other_graph = win.tabs.add_tab("Unrelated Graph")
    other_lines_before = len(win.tabs.tabs[other_graph].get_axes().lines)
    now[0] = 100.3
    assert win.gs_live_mark("on", "ethanol")[0]
    fake.feed(b'{"resistance":80,"voltage":1.2,"temperature":26,"humidity":41}\n')
    controller.flush_pending()
    win._gs_live_flush_book()
    qapp.processEvents()

    assert workbook.source_df.shape[0] == 2
    assert workbook.source_df.iloc[-1]["gas_state"] == "on"
    assert workbook.source_df.iloc[-1]["event"] == "gas_on:ethanol"
    assert len(win._gs_live_line.get_xdata()) == 2
    assert len(win.tabs.tabs[graph_id].get_axes().lines) >= 2  # signal + marker
    assert len(win.tabs.tabs[other_graph].get_axes().lines) == other_lines_before

    win.gs_live_select_signal("voltage")
    np.testing.assert_allclose(win._gs_live_line.get_ydata(), [1.0, 1.2])
    assert win.gs_live_disconnect()[0]
    assert workbook.table.editTriggers() != QAbstractItemView.NoEditTriggers
    assert name in win._datasets and len(win._datasets[name]["df"]) == 2


def test_gas_live_reconnect_starts_a_new_preserved_session(win, qapp):
    fake, controller, now = _install_fake_live_controller(win)
    assert win.gs_live_connect("COM_TEST")[0]
    now[0] = 101.0
    fake.feed(b'{"resistance":50}\n')
    controller.flush_pending()
    first_name = win._gs_live_dataset_name
    win.gs_live_disconnect()

    assert win.gs_live_connect("COM_TEST")[0]
    now[0] = 102.0
    fake.feed(b'time,resistance\n0,60\n')
    controller.flush_pending()
    second_name = win._gs_live_dataset_name
    win.gs_live_disconnect()
    qapp.processEvents()

    assert first_name != second_name
    assert first_name in win._datasets and second_name in win._datasets
    assert win._datasets[first_name]["df"]["resistance"].tolist() == [50]
    assert win._datasets[second_name]["df"]["resistance"].tolist() == [60]


def test_gas_live_port_is_closed_with_main_window(win, qapp):
    fake, _controller, _now = _install_fake_live_controller(win)
    assert win.gs_live_connect("COM_CLOSE")[0]
    assert fake.opened
    win.close()
    qapp.processEvents()
    assert not fake.opened


def test_gas_live_ni_daq_creates_shared_book_graph_and_preserves_session(win, qapp):
    backend, controller, now = _install_fake_daq_controller(win)
    devices = win.gs_live_refresh_daq_devices()
    assert devices[0]["product_type"] == "USB-6008"
    assert win.gas_sensor_panel.daq_channel_combo.currentData() == "Dev1/ai0"

    ok, message = win.gs_live_connect_daq(
        "Dev1", "Dev1/ai0", 5.0, 0.0, 5.0, "RSE"
    )
    assert ok and "Dev1/ai0" in message
    backend.samples = [[1.0], [1.2]]
    controller.poll_available()
    controller.flush_pending()
    qapp.processEvents()

    name = win._gs_live_dataset_name
    workbook = win._gs_live_workbook
    graph_id = win._gs_live_graph_id
    assert name.startswith("Live Gas ")
    assert list(workbook.source_df.columns) == [
        "elapsed_s", "ai0_voltage_v", "gas_state", "event"
    ]
    assert workbook.source_df["ai0_voltage_v"].tolist() == [1.0, 1.2]
    assert win._gs_live_signal == "ai0_voltage_v"
    assert graph_id in win.tabs.tabs
    assert win.gas_sensor_panel.value_labels["voltage"].text() == "1.2"

    now[0] = 200.5
    assert win.gs_live_mark("on", "sample A")[0]
    backend.samples = [[1.5]]
    controller.poll_available()
    controller.flush_pending()
    win._gs_live_flush_book()
    assert workbook.source_df.iloc[-1]["event"] == "gas_on:sample A"
    assert win.gs_live_status()["transport"] == "ni_daq"

    assert win.gs_live_disconnect()[0]
    assert backend.closed
    assert name in win._datasets
    assert workbook.table.editTriggers() != QAbstractItemView.NoEditTriggers


def test_gas_live_multi_sensor_processing_and_multi_line_graph(win, qapp):
    backend, controller, _now = _install_fake_daq_controller(win)
    ok, _message = win.gs_live_configure_flow({"sensor_channels": [
        {
            "source_field": "ai0_voltage_v",
            "alias": "MQ-2 A",
            "voltage_to_resistance": True,
            "smoothing": True,
            "smoothing_window": 2,
        },
        {
            "source_field": "ai1_voltage_v",
            "alias": "MQ-135 B",
            "voltage_to_resistance": True,
            "reference_resistance_ohm": 20_000,
        },
    ]})
    assert ok
    assert win.gs_live_connect_daq(
        "Dev1", "Dev1/ai0,Dev1/ai1", 10.0
    )[0]
    backend.samples = [[2.5, 1.0], [2.0, 2.5]]
    controller.poll_available()
    controller.flush_pending()
    qapp.processEvents()

    frame = win._gs_live_workbook.source_df
    assert "MQ-2 A resistance_ohm_ma2" in frame
    assert "MQ-135 B resistance_ohm" in frame
    assert frame["MQ-2 A resistance_ohm_ma2"].tolist() == pytest.approx([10_000, 12_500])
    assert frame["MQ-135 B resistance_ohm"].tolist() == pytest.approx([80_000, 20_000])
    assert win._gs_live_signals == [
        "MQ-2 A resistance_ohm_ma2", "MQ-135 B resistance_ohm"
    ]
    assert set(win._gs_live_lines) == set(win._gs_live_signals)
    assert len(win.tabs.tabs[win._gs_live_graph_id].get_axes().lines) == 2

    win.gs_live_select_signals(["ai0_voltage_v", "ai1_voltage_v"])
    assert set(win._gs_live_lines) == {"ai0_voltage_v", "ai1_voltage_v"}
    np.testing.assert_allclose(win._gs_live_lines["ai1_voltage_v"].get_ydata(), [1.0, 2.5])
    win.gs_live_disconnect()
    assert win.gs_live_configure_flow({})[0]


def test_visual_flow_processes_daq_samples_before_live_book_and_graph(win, qapp):
    backend, controller, _now = _install_fake_daq_controller(win)
    ok, summary = win.gs_live_configure_flow(None,
        voltage_to_resistance=True,
        voltage_field="ai0_voltage_v",
        supply_voltage_v=5.0,
        reference_resistance_ohm=10_000.0,
        divider_topology="sensor_high",
        smoothing=True,
        smoothing_field="resistance_ohm",
        smoothing_window=2,
    )
    assert ok and "moving_average" in summary
    assert win.gs_live_connect_daq("Dev1", "Dev1/ai0", 10.0)[0]
    assert not win.gs_live_configure_flow(None, smoothing=False)[0]

    backend.samples = [[2.5], [2.0]]
    controller.poll_available()
    controller.flush_pending()
    qapp.processEvents()

    workbook = win._gs_live_workbook
    assert list(workbook.source_df.columns) == [
        "elapsed_s", "ai0_voltage_v", "gas_state", "event",
        "resistance_ohm", "resistance_ohm_ma2",
    ]
    assert workbook.source_df["resistance_ohm"].tolist() == pytest.approx([10_000, 15_000])
    assert workbook.source_df["resistance_ohm_ma2"].tolist() == pytest.approx([10_000, 12_500])
    assert win._gs_live_signal == "resistance_ohm_ma2"
    assert win.gas_sensor_panel.flow_summary_label.text().endswith("RUNNING")

    designer = win.gs_live_open_flow_designer()
    assert designer.isVisible() and not designer.settings_body.isEnabled()
    win.gs_live_disconnect()
    assert designer.settings_body.isEnabled()
    assert win.gs_live_configure_flow({})[0]


def test_visual_flow_wiring_bypasses_nodes_and_invalid_canvas_blocks_connect(win, qapp):
    backend, controller, _now = _install_fake_daq_controller(win)
    assert win.gs_live_configure_flow(None,
        voltage_to_resistance=True,
        voltage_field="ai0_voltage_v",
        smoothing=True,
        smoothing_field="resistance_ohm",
    )[0]
    assert win.gs_live_configure_wiring([
        ["source", "book"], ["book", "graph"]
    ])[0]
    assert win.gs_live_flow_status()["nodes"] == ["input", "live_book", "rolling_graph"]
    assert win.gs_live_connect_daq("Dev1", "Dev1/ai0", 10.0)[0]
    backend.samples = [[2.5]]
    controller.poll_available()
    controller.flush_pending()
    assert list(win._gs_live_workbook.source_df.columns) == [
        "elapsed_s", "ai0_voltage_v", "gas_state", "event"
    ]
    win.gs_live_disconnect()

    designer = win.gs_live_open_flow_designer()
    designer.clear_wires()
    ok, message = win.gs_live_connect_daq("Dev1", "Dev1/ai0", 10.0)
    assert not ok and "wiring is invalid" in message
    designer.auto_wire()
    assert designer.wiring_valid()
    assert win.gs_live_configure_flow({})[0]
    assert win.gs_live_configure_wiring([
        ["source", "divider"], ["divider", "smooth"],
        ["smooth", "book"], ["book", "graph"],
    ])[0]
