"""Extra plot types: error bars, fill-between bands, secondary Y axis.

Pure matplotlib drawing helpers (take an Axes + arrays) so they are testable
without Qt. The MainWindow mixin picks columns via a form and calls these.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

import numpy as np


def _clean(*arrays) -> Tuple[np.ndarray, ...]:
    arrs = [np.asarray(a, dtype=float).ravel() for a in arrays]
    n = min(a.size for a in arrs)
    if n == 0:
        raise ValueError("empty data")
    arrs = [a[:n] for a in arrs]
    mask = np.ones(n, dtype=bool)
    for a in arrs:
        mask &= np.isfinite(a)
    if mask.sum() == 0:
        raise ValueError("no finite points in common")
    return tuple(a[mask] for a in arrs)


def draw_error_bars(ax, x, y, yerr, xerr=None, label: Optional[str] = None,
                    capsize: float = 3.0, **kwargs) -> Any:
    """Errorbar plot of y(x) with vertical (and optional horizontal) error."""
    if xerr is not None:
        x_, y_, ye, xe = _clean(x, y, yerr, xerr)
        return ax.errorbar(x_, y_, yerr=ye, xerr=xe, label=label,
                           capsize=capsize, fmt=kwargs.pop("fmt", "o-"), **kwargs)
    x_, y_, ye = _clean(x, y, yerr)
    return ax.errorbar(x_, y_, yerr=ye, label=label, capsize=capsize,
                       fmt=kwargs.pop("fmt", "o-"), **kwargs)


def draw_fill_between(ax, x, y1, y2, label: Optional[str] = None,
                      alpha: float = 0.3, **kwargs) -> Any:
    """Shaded band between two y curves over x (e.g. a confidence band)."""
    x_, a_, b_ = _clean(x, y1, y2)
    return ax.fill_between(x_, a_, b_, alpha=alpha, label=label, **kwargs)


def add_secondary_y(ax, x, y, label: Optional[str] = None,
                    color: Optional[str] = None, ylabel: str = "") -> Tuple[Any, Any]:
    """Plot y(x) on a twinned right-hand Y axis; returns (ax2, line).

    The right axis and its label/ticks are coloured to match the curve so the
    two Y scales stay readable (Origin-style multi-axis).
    """
    x_, y_ = _clean(x, y)
    ax2 = ax.twinx()
    (line,) = ax2.plot(x_, y_, label=label, color=color)
    c = color or line.get_color()
    if ylabel:
        ax2.set_ylabel(ylabel, color=c)
    ax2.tick_params(axis="y", colors=c)
    return ax2, line
