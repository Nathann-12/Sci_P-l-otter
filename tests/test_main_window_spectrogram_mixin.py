from __future__ import annotations

import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


pytest.importorskip("PySide6")
pytest.importorskip("numexpr")

from PySide6.QtWidgets import QApplication, QWidget

import dialogs_spectrogram
import main_window_spectrogram_mixin as spectrogram_mixin_module
from main_window_spectrogram_mixin import MainWindowSpectrogramMixin
from widgets.plot_tabs import TabManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _StatusBar:
    def __init__(self):
        self.messages = []

    def showMessage(self, message: str, *_args) -> None:
        self.messages.append(message)


class _Event:
    def __init__(self, inaxes, xdata, ydata):
        self.inaxes = inaxes
        self.xdata = xdata
        self.ydata = ydata


class DummySpectrogramWindow(QWidget, MainWindowSpectrogramMixin):
    def __init__(self):
        super().__init__()
        self.tabs = TabManager(self)
        current_tab = self.tabs.currentWidget()
        self.canvas = current_tab.canvas
        self._status_bar = _StatusBar()
        self._df = pd.DataFrame(
            {
                "time": np.linspace(0.0, 11.0, 12),
                "signal": np.linspace(1.0, 12.0, 12),
            }
        )
        self.plot_mode = "REPLACE"
        self._last_cbar = None
        self._cid_motion = None
        self.fft_calls = 0
        self.curvefit_calls = 0

    def statusBar(self):
        return self._status_bar

    def run_fft_dialog(self):
        self.fft_calls += 1

    def _open_fit_dialog(self):
        self.curvefit_calls += 1


def _stft_params():
    return {
        "time_col": "time",
        "signal_col": "signal",
        "mode": "STFT (Spectrogram)",
        "to_db": True,
        "window": "hann",
        "nperseg": 8,
        "noverlap": 4,
        "scaling": "density",
        "detrend": True,
        "contrast_percentiles": (5, 95),
        "max_frequency": 50,
    }


def test_open_spectrogram_dialog_wires_signals_and_shows_non_modal(qapp, monkeypatch):
    captured = {}

    class FakeSignal:
        def __init__(self, name):
            self.name = name
            self.connected = []

        def connect(self, callback):
            self.connected.append(callback)

    class FakeDialog:
        def __init__(self, df, parent):
            captured["df"] = df.copy()
            captured["parent"] = parent
            self.preview_requested = FakeSignal("preview")
            self.export_image_requested = FakeSignal("image")
            self.export_csv_requested = FakeSignal("csv")
            self.send_to_fft_requested = FakeSignal("fft")
            self.send_to_curvefit_requested = FakeSignal("curvefit")
            captured["dialog"] = self

        def setWindowModality(self, value):
            captured["modality"] = value

        def setAttribute(self, attr, value):
            captured["attribute"] = (attr, value)

        def resize(self, w, h):
            captured["size"] = (w, h)

        def show(self):
            captured["shown"] = True

    monkeypatch.setattr(dialogs_spectrogram, "SpectrogramDialog", FakeDialog)
    monkeypatch.setattr(spectrogram_mixin_module, "SpectrogramDialog", FakeDialog)

    window = DummySpectrogramWindow()
    window.open_spectrogram_dialog()

    dialog = captured["dialog"]
    assert captured["parent"] is window
    assert captured["df"].equals(window._df)
    assert dialog.preview_requested.connected == [window.on_spectrogram_preview]
    assert dialog.export_image_requested.connected == [window.on_spectrogram_export_image]
    assert dialog.export_csv_requested.connected == [window.on_spectrogram_export_csv]
    assert dialog.send_to_fft_requested.connected == [window.on_spectrogram_send_to_fft]
    assert dialog.send_to_curvefit_requested.connected == [window.on_spectrogram_send_to_curvefit]
    assert captured["shown"] is True


def test_on_spectrogram_preview_renders_and_stores_current_state(qapp, monkeypatch):
    window = DummySpectrogramWindow()
    params = _stft_params()
    prior_cid = window.canvas.mpl_connect("motion_notify_event", lambda event: None)
    window._cid_motion = prior_cid

    def fake_compute_spectrogram(*_args, **_kwargs):
        return (
            np.array([0.0, 1.0, 2.0]),
            np.array([0.0, 1.0, 2.0, 3.0]),
            np.arange(12, dtype=float).reshape(3, 4),
            {"is_datetime": False, "vmin": 1.0, "vmax": 10.0, "to_db": True},
        )

    monkeypatch.setattr(spectrogram_mixin_module, "compute_spectrogram", fake_compute_spectrogram)

    window.on_spectrogram_preview(params)

    assert window._current_spectrogram["params"] == params
    assert window._current_spectrogram["meta"]["is_datetime"] is False
    assert window.canvas.ax.get_xlabel() == "Time"
    assert window.canvas.ax.get_ylabel() == "Frequency (Hz)"
    assert window.canvas.ax.get_title() == "Spectrogram (STFT) - signal"
    assert len(window.canvas.ax.images) == 1
    assert window._last_cbar is not None
    assert window._cid_motion != prior_cid
    assert window.statusBar().messages[-1] == "Spectrogram preview เสร็จสิ้น: STFT"


def test_spectrogram_export_image_and_csv_use_current_preview(qapp, monkeypatch, tmp_path):
    window = DummySpectrogramWindow()
    image_path = tmp_path / "spectrogram.png"
    csv_path = tmp_path / "spectrogram.csv"
    params = _stft_params()
    saved = {}

    window._current_spectrogram = {
        "T": np.array([0.0, 1.0]),
        "F": np.array([5.0, 10.0]),
        "S": np.array([[1.0, 2.0], [3.0, 4.0]]),
        "meta": {"is_datetime": False},
        "params": params,
    }

    monkeypatch.setattr(
        spectrogram_mixin_module.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(image_path), "PNG Files (*.png)"),
    )
    monkeypatch.setattr(
        window.canvas.fig,
        "savefig",
        lambda filename, **kwargs: saved.update({"image": (filename, kwargs)}),
    )

    window.on_spectrogram_export_image(params)

    assert saved["image"][0] == str(image_path)
    assert saved["image"][1]["dpi"] == 150
    assert window.statusBar().messages[-1] == f"บันทึก Spectrogram เป็น {image_path}"

    monkeypatch.setattr(
        spectrogram_mixin_module.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(csv_path), "CSV Files (*.csv)"),
    )
    monkeypatch.setattr(
        spectrogram_mixin_module,
        "export_spectrogram_data",
        lambda T, F, S, meta, filename: saved.update(
            {"csv": (T.copy(), F.copy(), S.copy(), dict(meta), filename)}
        ),
    )

    window.on_spectrogram_export_csv(params)

    np.testing.assert_allclose(saved["csv"][0], np.array([0.0, 1.0]))
    np.testing.assert_allclose(saved["csv"][1], np.array([5.0, 10.0]))
    np.testing.assert_allclose(saved["csv"][2], np.array([[1.0, 2.0], [3.0, 4.0]]))
    assert saved["csv"][3] == {"is_datetime": False}
    assert saved["csv"][4] == str(csv_path)
    assert window.statusBar().messages[-1] == f"บันทึก Spectrogram CSV เป็น {csv_path}"


def test_spectrogram_send_actions_and_mouse_move_status(qapp):
    window = DummySpectrogramWindow()
    params = _stft_params()
    window._current_spectrogram = {
        "T": np.array([0.0, 1.0, 2.0]),
        "F": np.array([0.0, 1.0, 2.0]),
        "S": np.array([[1.0, 2.0, 3.0], [4.0, 5.5, 6.0], [7.0, 8.0, 9.0]]),
        "meta": {"is_datetime": False, "to_db": True},
        "params": params,
    }

    window.on_spectrogram_send_to_fft(params)
    window.on_spectrogram_send_to_curvefit(params)
    window._on_spectrogram_mouse_move(_Event(window.canvas.ax, 1.0, 1.0))

    assert window.fft_calls == 1
    assert window.curvefit_calls == 1
    assert window.statusBar().messages[-3:] == [
        "ส่งข้อมูลไปยัง FFT แล้ว",
        "ส่งข้อมูลไปยัง CurveFit แล้ว",
        "Time: 1.000 | Freq: 1.00 Hz | Power: 5.50 dB",
    ]
