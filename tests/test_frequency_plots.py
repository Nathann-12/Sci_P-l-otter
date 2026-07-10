from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from plots import frequency_plots


def _response_dataframe() -> pd.DataFrame:
    frequency = np.array([10.0, 1.0, 100.0])
    response = 1.0 / (1.0 + 1j * frequency)
    return pd.DataFrame(
        {
            "frequency_hz": frequency,
            "real": response.real,
            "imag": response.imag,
            "magnitude": np.abs(response),
            "phase": np.rad2deg(np.angle(response)),
        }
    )


def test_phase_plot_uses_successive_samples_when_only_one_numeric_column():
    dataframe = pd.DataFrame({"signal": [1.0, 2.0, np.nan, 4.0]})
    figure, axes = plt.subplots()
    try:
        frequency_plots.phase_plot(axes, dataframe)

        np.testing.assert_allclose(axes.lines[0].get_xdata(), [1.0, 2.0])
        np.testing.assert_allclose(axes.lines[0].get_ydata(), [2.0, 4.0])
        assert axes.get_xlabel() == "signal(n)"
    finally:
        plt.close(figure)


def test_nyquist_plot_uses_real_and_imaginary_aliases_without_sign_flip():
    dataframe = _response_dataframe()
    figure, axes = plt.subplots()
    try:
        frequency_plots.nyquist_plot(axes, dataframe)

        expected = dataframe.sort_values("frequency_hz", kind="mergesort")
        np.testing.assert_allclose(axes.lines[0].get_xdata(), expected["real"])
        np.testing.assert_allclose(axes.lines[0].get_ydata(), expected["imag"])
        assert axes.get_xlabel() == "real"
        assert axes.get_ylabel() == "imag"
    finally:
        plt.close(figure)


def test_bode_plot_uses_frequency_magnitude_phase_aliases_and_sorts_positive_frequency():
    dataframe = pd.DataFrame(
        {
            "frequency": [100.0, -1.0, 1.0, 10.0],
            "magnitude": [0.1, 100.0, 0.5, 0.25],
            "phase": [-80.0, 0.0, -20.0, -45.0],
        }
    )
    figure, axes = plt.subplots()
    try:
        frequency_plots.bode_plot(axes, dataframe)

        assert len(figure.axes) == 2
        magnitude_axes, phase_axes = figure.axes
        np.testing.assert_allclose(magnitude_axes.lines[0].get_xdata(), [1.0, 10.0, 100.0])
        np.testing.assert_allclose(
            magnitude_axes.lines[0].get_ydata(),
            20.0 * np.log10([0.5, 0.25, 0.1]),
        )
        np.testing.assert_allclose(phase_axes.lines[0].get_ydata(), [-20.0, -45.0, -80.0])
    finally:
        plt.close(figure)


def test_bode_plot_can_derive_magnitude_and_phase_from_complex_columns():
    dataframe = _response_dataframe()
    figure, axes = plt.subplots()
    try:
        frequency_plots.bode_plot(axes, dataframe[["frequency_hz", "real", "imag"]])

        expected = dataframe.sort_values("frequency_hz", kind="mergesort")
        assert len(figure.axes) == 2
        magnitude_axes, phase_axes = figure.axes
        np.testing.assert_allclose(magnitude_axes.lines[0].get_xdata(), expected["frequency_hz"])
        np.testing.assert_allclose(
            magnitude_axes.lines[0].get_ydata(),
            20.0 * np.log10(expected["magnitude"]),
        )
        np.testing.assert_allclose(phase_axes.lines[0].get_ydata(), expected["phase"])
    finally:
        plt.close(figure)


@pytest.mark.parametrize("spec", frequency_plots.PLOTS, ids=lambda spec: spec["key"])
def test_frequency_plot_handles_empty_dataframe(spec):
    figure, axes = plt.subplots()
    try:
        spec["func"](axes, pd.DataFrame())
        assert axes.texts
    finally:
        plt.close(figure)


def test_bode_plot_handles_only_nonpositive_frequency_with_placeholder():
    dataframe = pd.DataFrame(
        {
            "frequency": [-10.0, 0.0],
            "magnitude": [1.0, 2.0],
            "phase": [0.0, 1.0],
        }
    )
    figure, axes = plt.subplots()
    try:
        frequency_plots.bode_plot(axes, dataframe)

        assert axes.texts
        assert "positive frequency" in axes.texts[0].get_text()
    finally:
        plt.close(figure)


def test_frequency_catalog_contract():
    assert {entry["key"] for entry in frequency_plots.PLOTS} == {
        "phase_plot",
        "nyquist_plot",
        "bode_plot",
    }
    assert all(entry["category"] == "Frequency Response" for entry in frequency_plots.PLOTS)
