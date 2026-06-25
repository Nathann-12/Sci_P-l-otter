"""Behavioral tests for feature actions, now possible headless because the
logic talks to the view-accessor seam (which we stub) instead of popping
real Qt dialogs."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main_window_features_mixin import MainWindowFeaturesMixin


class DummyFeatures(MainWindowFeaturesMixin):
    """Feature logic with the view seam stubbed — no real widgets/dialogs."""

    def __init__(self, df: pd.DataFrame, x_sel: str = "", y_sel: str = "", choices=()):
        self._df = df
        self._x_sel = x_sel
        self._y_sel = y_sel
        self._choices = iter(choices)
        self.messages: list[str] = []
        self.errors: list[tuple] = []
        self.added_x: list[str] = []
        self.added_y: list[str] = []

    # --- stubbed view seam ---
    def inform(self, title, text):
        self.messages.append(f"info:{title}")

    def error_box(self, title, text):
        self.errors.append((title, text))

    def notify(self, msg, error=False):
        self.messages.append(msg)

    def x_column_count(self):
        return len(self._df.columns)

    def y_column_count(self):
        return len(self._df.columns)

    def selected_x_column(self):
        return self._x_sel

    def selected_y_column(self):
        return self._y_sel

    def selected_y_index(self):
        return 0

    def add_x_column_option(self, name):
        self.added_x.append(name)

    def add_y_column_option(self, name):
        self.added_y.append(name)

    def ask_choice(self, title, label, options, current=0):
        return next(self._choices)


def test_feature_add_moving_average_creates_column():
    df = pd.DataFrame({"t": range(60), "value": np.sin(np.linspace(0, 6, 60))})
    win = DummyFeatures(df, y_sel="value")

    win.feature_add_moving_average()

    assert not win.errors
    assert len(win.added_y) == 1
    new_col = win.added_y[0]
    assert new_col in win._df.columns
    assert any("Moving Average" in m for m in win.messages)


def test_feature_add_magnitude_creates_b_mag():
    df = pd.DataFrame({"Bx": [3.0, 0.0], "By": [4.0, 0.0], "Bz": [0.0, 5.0]})
    win = DummyFeatures(df, y_sel="Bx", choices=[("Bx", True), ("By", True), ("Bz", True)])

    win.feature_add_magnitude()

    assert not win.errors
    assert "B_mag" in win._df.columns
    assert win.added_y == ["B_mag"]
    # |(3,4,0)| == 5
    assert abs(float(win._df["B_mag"].iloc[0]) - 5.0) < 1e-9


def test_feature_add_magnitude_cancel_stops_early():
    df = pd.DataFrame({"Bx": [1.0], "By": [2.0], "Bz": [2.0]})
    win = DummyFeatures(df, y_sel="Bx", choices=[("Bx", False)])

    win.feature_add_magnitude()

    assert "B_mag" not in win._df.columns
    assert win.added_y == []
