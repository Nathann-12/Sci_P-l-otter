"""Phase-space and frequency-response plots."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from plots._common import color_cycle, numeric_columns, placeholder


_FREQUENCY_ALIASES = ("frequency", "freq", "hz", "omega")
_REAL_ALIASES = ("real", "re")
_IMAGINARY_ALIASES = ("imaginary", "imag", "im")
_MAGNITUDE_ALIASES = ("magnitude", "mag", "gain", "amplitude", "amp")
_PHASE_ALIASES = ("phase", "angle", "phi")


def _normalized(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _find_column(
    columns: list[str],
    aliases: tuple[str, ...],
    used: set[str] | None = None,
) -> str | None:
    used = used or set()
    normalized_aliases = tuple(_normalized(alias) for alias in aliases)
    for column in columns:
        if column in used:
            continue
        normalized = _normalized(column)
        if any(
            alias == normalized or (len(alias) >= 4 and alias in normalized)
            for alias in normalized_aliases
        ):
            return column
    return None


def _aligned_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frame = df[columns].apply(pd.to_numeric, errors="coerce")
    return frame.replace([np.inf, -np.inf], np.nan).dropna()


def _finite_columns(df: pd.DataFrame, count: int):
    columns = numeric_columns(df)
    if len(columns) < count:
        return None
    frame = df[columns[:count]].apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    if frame.empty:
        return None
    return [str(column) for column in columns[:count]], [
        frame[column].to_numpy(dtype=float) for column in columns[:count]
    ]


def _complex_columns(df: pd.DataFrame):
    columns = numeric_columns(df)
    real_col = _find_column(columns, _REAL_ALIASES)
    used = {real_col} if real_col else set()
    imag_col = _find_column(columns, _IMAGINARY_ALIASES, used)
    if real_col is None or imag_col is None:
        if len(columns) < 2:
            return None
        real_col, imag_col = columns[:2]
    freq_col = _find_column(columns, _FREQUENCY_ALIASES, {real_col, imag_col})
    ordered_columns = [real_col, imag_col] + ([freq_col] if freq_col else [])
    frame = _aligned_frame(df, ordered_columns)
    if frame.empty:
        return None
    if freq_col:
        frame = frame.sort_values(freq_col, kind="mergesort")
    return (
        (str(real_col), str(imag_col), str(freq_col) if freq_col else None),
        frame[real_col].to_numpy(dtype=float),
        frame[imag_col].to_numpy(dtype=float),
    )


def _bode_columns(df: pd.DataFrame):
    columns = numeric_columns(df)
    freq_col = _find_column(columns, _FREQUENCY_ALIASES)
    if freq_col is not None:
        used = {freq_col}
        mag_col = _find_column(columns, _MAGNITUDE_ALIASES, used)
        if mag_col is not None:
            used.add(mag_col)
        phase_col = _find_column(columns, _PHASE_ALIASES, used)
        if mag_col is not None and phase_col is not None:
            frame = _aligned_frame(df, [freq_col, mag_col, phase_col])
            if not frame.empty:
                return (
                    (str(freq_col), str(mag_col), str(phase_col)),
                    [
                        frame[freq_col].to_numpy(dtype=float),
                        frame[mag_col].to_numpy(dtype=float),
                        frame[phase_col].to_numpy(dtype=float),
                    ],
                )

        real_col = _find_column(columns, _REAL_ALIASES, used)
        if real_col is not None:
            used.add(real_col)
        imag_col = _find_column(columns, _IMAGINARY_ALIASES, used)
        if real_col is not None and imag_col is not None:
            frame = _aligned_frame(df, [freq_col, real_col, imag_col])
            if not frame.empty:
                real = frame[real_col].to_numpy(dtype=float)
                imaginary = frame[imag_col].to_numpy(dtype=float)
                response = real + 1j * imaginary
                return (
                    (str(freq_col), "|response|", "phase"),
                    [
                        frame[freq_col].to_numpy(dtype=float),
                        np.abs(response),
                        np.rad2deg(np.angle(response)),
                    ],
                )

    return _finite_columns(df, 3)


def phase_plot(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    columns = numeric_columns(df)
    if not columns:
        placeholder(ax, "Phase plot needs numeric data.")
        return
    if len(columns) >= 2:
        prepared = _finite_columns(df, 2)
        if prepared is None:
            placeholder(ax, "Phase plot has no finite paired values.")
            return
        names, (x, y) = prepared
        x_label, y_label = names
    else:
        values = pd.to_numeric(df[columns[0]], errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(values)
        values = values[mask]
        if values.size < 2:
            placeholder(ax, "Phase plot needs at least two finite values.")
            return
        x, y = values[:-1], values[1:]
        x_label = f"{columns[0]}(n)"
        y_label = f"{columns[0]}(n+1)"
    ax.plot(x, y, color=color_cycle(1)[0], linewidth=1.2)
    ax.scatter(x, y, color=color_cycle(1)[0], s=10, alpha=0.6)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title("Phase Plot")


def nyquist_plot(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _complex_columns(df)
    if prepared is None:
        placeholder(ax, "Nyquist plot needs real and imaginary columns.")
        return
    names, real, imaginary = prepared
    color = color_cycle(1)[0]
    ax.plot(real, imaginary, color=color, linewidth=1.4)
    ax.scatter(real, imaginary, color=color, s=14)
    ax.axhline(0.0, color="#7f8a99", linewidth=0.8)
    ax.axvline(0.0, color="#7f8a99", linewidth=0.8)
    ax.set_xlabel(names[0])
    ax.set_ylabel(names[1])
    ax.set_title("Nyquist Plot")
    ax.set_aspect("equal", adjustable="datalim")


def bode_plot(ax, df: pd.DataFrame, **opts) -> None:
    ax.clear()
    prepared = _bode_columns(df)
    if prepared is None:
        placeholder(ax, "Bode plot needs frequency, magnitude and phase columns.")
        return
    names, (frequency, magnitude, phase) = prepared
    mask = frequency > 0
    frequency, magnitude, phase = frequency[mask], magnitude[mask], phase[mask]
    if frequency.size == 0:
        placeholder(ax, "Bode plot needs positive frequency values.")
        return
    order = np.argsort(frequency, kind="mergesort")
    frequency, magnitude, phase = frequency[order], magnitude[order], phase[order]
    magnitude_db = 20.0 * np.log10(np.maximum(np.abs(magnitude), np.finfo(float).tiny))
    magnitude_color, phase_color = color_cycle(2)
    ax.semilogx(frequency, magnitude_db, color=magnitude_color, label="Magnitude")
    ax.set_xlabel(names[0])
    ax.set_ylabel("Magnitude (dB)", color=magnitude_color)
    ax.tick_params(axis="y", labelcolor=magnitude_color)
    phase_axes = ax.twinx()
    phase_axes.semilogx(frequency, phase, color=phase_color, label="Phase")
    phase_axes.set_ylabel(f"{names[2]} (deg)", color=phase_color)
    phase_axes.tick_params(axis="y", labelcolor=phase_color)
    ax.set_title("Bode Plot")
    ax.grid(True, which="both", alpha=0.25)


PLOTS = [
    {
        "key": "phase_plot",
        "title": "Phase Plot",
        "category": "Frequency Response",
        "func": phase_plot,
        "desc": "Phase portrait from two columns or successive samples",
        "min_cols": 1,
        "multi": False,
    },
    {
        "key": "nyquist_plot",
        "title": "Nyquist Plot",
        "category": "Frequency Response",
        "func": nyquist_plot,
        "desc": "Imaginary response versus real response",
        "min_cols": 2,
        "multi": False,
    },
    {
        "key": "bode_plot",
        "title": "Bode Plot",
        "category": "Frequency Response",
        "func": bode_plot,
        "desc": "Magnitude and phase versus positive logarithmic frequency",
        "min_cols": 3,
        "multi": False,
    },
]
