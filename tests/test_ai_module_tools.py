"""Behavioural tests for the specialized-module AI tools (no network/model)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ai.app_tools import build_app_registry


class _Win:
    """Minimal MainWindow-like host: just an active DataFrame + column sync."""

    def __init__(self, df):
        self._df = df
        self.added = []

    def _resolve_active_dataframe(self):
        return self._df

    def selected_y_column(self):
        return ""

    def add_y_column_option(self, name):
        self.added.append(name)


def _run(df, tool, args):
    return build_app_registry(_Win(df)).execute(tool, args)


def _assert_ok(out, keyword):
    assert "could not" not in out.lower() and "provide" not in out.lower()
    assert keyword.lower() in out.lower()


# ---------------------------------------------------------------- Gas Sensor
def test_gas_response():
    t = np.linspace(0, 100, 400)
    y = np.full_like(t, 100.0)
    y[(t >= 20) & (t <= 60)] = 160.0           # exposure plateau
    y[t > 60] = 100.0                           # recovered
    df = pd.DataFrame({"t": t, "R": y})
    out = _run(df, "gas_response", {"t_on": 20, "t_off": 60, "time_column": "t", "column": "R"})
    _assert_ok(out, "response")
    assert "%" in out


def test_gas_response_requires_times():
    df = pd.DataFrame({"t": [0, 1, 2], "R": [1, 2, 3]})
    out = _run(df, "gas_response", {})
    assert "t_on" in out


# ------------------------------------------------------------- Electrochemistry
def test_cv_peaks():
    v = np.concatenate([np.linspace(-0.5, 0.5, 100), np.linspace(0.5, -0.5, 100)])
    i = np.concatenate([
        np.exp(-((np.linspace(-0.5, 0.5, 100) - 0.2) ** 2) / 0.01),     # ox peak
        -np.exp(-((np.linspace(0.5, -0.5, 100) - 0.1) ** 2) / 0.01),     # red peak
    ])
    out = _run(pd.DataFrame({"V": v, "I": i}), "cv_peaks",
               {"potential_column": "V", "current_column": "I"})
    _assert_ok(out, "cv peaks")


def test_tafel_analysis():
    eta = np.linspace(0.05, 0.3, 40)
    i = 10 ** (eta / 0.06)                       # Tafel slope 60 mV/dec
    out = _run(pd.DataFrame({"eta": eta, "i": i}), "tafel_analysis",
               {"overpotential_column": "eta", "current_column": "i"})
    _assert_ok(out, "tafel")


# ------------------------------------------------------------------ Spectroscopy
def test_raman_dg():
    x = np.linspace(1000, 1800, 400)
    y = (np.exp(-((x - 1350) ** 2) / 400) + 1.5 * np.exp(-((x - 1580) ** 2) / 400))
    out = _run(pd.DataFrame({"shift": x, "int": y}), "raman_dg",
               {"x_column": "shift", "y_column": "int"})
    _assert_ok(out, "d/g")


def test_normalize_spectrum_adds_column():
    df = pd.DataFrame({"int": [1.0, 5.0, 2.0, 8.0]})
    out = _run(df, "normalize_spectrum", {"mode": "max", "column": "int"})
    _assert_ok(out, "normalized")


# --------------------------------------------------------------- Materials Sci.
def test_iv_conductivity():
    i = np.linspace(0, 1e-3, 40)
    v = i * 50.0                                 # R = 50 ohm
    out = _run(pd.DataFrame({"V": v, "I": i}), "iv_conductivity",
               {"length_m": 0.01, "area_m2": 1e-6, "voltage_column": "V", "current_column": "I"})
    _assert_ok(out, "conductivity")


def test_iv_conductivity_requires_geometry():
    df = pd.DataFrame({"V": [0, 1, 2], "I": [0, 1e-3, 2e-3]})
    assert "geometry" in _run(df, "iv_conductivity", {}).lower()


def test_arrhenius():
    temp = np.linspace(300, 500, 20)
    sigma = np.exp(-5000.0 / temp)               # Arrhenius behaviour
    out = _run(pd.DataFrame({"T": temp, "sigma": sigma}), "arrhenius",
               {"temperature_column": "T", "conductivity_column": "sigma"})
    _assert_ok(out, "activation energy")


# --------------------------------------------------------------- Physics / Lab
def test_ohms_law():
    i = np.linspace(0, 0.1, 30)
    v = i * 220.0
    out = _run(pd.DataFrame({"I": i, "V": v}), "ohms_law",
               {"current_column": "I", "voltage_column": "V"})
    _assert_ok(out, "ohm")


def test_rc_time_constant():
    t = np.linspace(0, 5, 200)
    v = 5.0 * (1 - np.exp(-t / 1.0))             # tau = 1 s charge
    out = _run(pd.DataFrame({"t": t, "v": v}), "rc_time_constant",
               {"time_column": "t", "value_column": "v", "mode": "charge"})
    _assert_ok(out, "time constant")


def test_pendulum_gravity():
    length = np.linspace(0.2, 1.0, 10)
    period = 2 * np.pi * np.sqrt(length / 9.81)
    out = _run(pd.DataFrame({"L": length, "T": period}), "pendulum_gravity",
               {"length_column": "L", "period_column": "T"})
    _assert_ok(out, "gravity")
