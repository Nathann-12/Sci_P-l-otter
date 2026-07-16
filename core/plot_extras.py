"""Extra plot types: error bars, fill-between bands, secondary/broken axes.

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


def _line_style(line) -> dict[str, Any]:
    return {
        "label": line.get_label(),
        "color": line.get_color(),
        "linestyle": line.get_linestyle(),
        "linewidth": line.get_linewidth(),
        "marker": line.get_marker(),
        "markersize": line.get_markersize(),
        "alpha": line.get_alpha(),
    }


def _finite_line_data(ax):
    payload = []
    for line in ax.get_lines():
        source_x = getattr(line, "_sciplotter_x_values", line.get_xdata(orig=False))
        source_y = getattr(line, "_sciplotter_y_values", line.get_ydata(orig=False))
        x, y = _clean(source_x, source_y)
        payload.append((x, y, _line_style(line)))
    if not payload:
        raise ValueError("broken axis needs at least one line plot")
    return payload


def _break_marks_y(top, bottom) -> None:
    d = 0.012
    kwargs = dict(color="#d7dde6", clip_on=False, linewidth=1.0)
    top.plot((-d, +d), (-d, +d), transform=top.transAxes, **kwargs)
    top.plot((1 - d, 1 + d), (-d, +d), transform=top.transAxes, **kwargs)
    bottom.plot((-d, +d), (1 - d, 1 + d), transform=bottom.transAxes, **kwargs)
    bottom.plot((1 - d, 1 + d), (1 - d, 1 + d), transform=bottom.transAxes, **kwargs)


def _break_marks_x(left, right) -> None:
    d = 0.012
    kwargs = dict(color="#d7dde6", clip_on=False, linewidth=1.0)
    left.plot((1 - d, 1 + d), (-d, +d), transform=left.transAxes, **kwargs)
    left.plot((1 - d, 1 + d), (1 - d, 1 + d), transform=left.transAxes, **kwargs)
    right.plot((-d, +d), (-d, +d), transform=right.transAxes, **kwargs)
    right.plot((-d, +d), (1 - d, 1 + d), transform=right.transAxes, **kwargs)


def draw_broken_axis(ax, axis: str, lower: float, upper: float) -> Tuple[Any, Any]:
    """Redraw line plots on split axes with a hidden range between lower/upper."""
    axis = str(axis).lower()[0]
    if axis not in {"x", "y"}:
        raise ValueError("axis must be x or y")
    lower = float(lower)
    upper = float(upper)
    if not np.isfinite(lower) or not np.isfinite(upper) or lower >= upper:
        raise ValueError("lower break must be less than upper break")

    payload = _finite_line_data(ax)
    title = ax.get_title()
    xlabel = ax.get_xlabel()
    ylabel = ax.get_ylabel()
    figure = ax.figure
    x_values = np.concatenate([x for x, _y, _style in payload])
    y_values = np.concatenate([y for _x, y, _style in payload])
    x_min, x_max = float(np.nanmin(x_values)), float(np.nanmax(x_values))
    y_min, y_max = float(np.nanmin(y_values)), float(np.nanmax(y_values))
    if axis == "y" and not (y_min < lower < upper < y_max):
        raise ValueError("Y break range must be inside the plotted data range")
    if axis == "x" and not (x_min < lower < upper < x_max):
        raise ValueError("X break range must be inside the plotted data range")

    figure.clf()
    if axis == "y":
        top, bottom = figure.subplots(
            2,
            1,
            sharex=True,
            gridspec_kw={"height_ratios": [1, 1], "hspace": 0.06},
        )
        target_axes = (top, bottom)
        top.set_ylim(upper, y_max)
        bottom.set_ylim(y_min, lower)
        top.spines["bottom"].set_visible(False)
        bottom.spines["top"].set_visible(False)
        top.tick_params(labelbottom=False)
        bottom.set_xlabel(xlabel)
        top.set_ylabel(ylabel)
        bottom.set_ylabel(ylabel)
        _break_marks_y(top, bottom)
    else:
        left, right = figure.subplots(
            1,
            2,
            sharey=True,
            gridspec_kw={"width_ratios": [1, 1], "wspace": 0.06},
        )
        target_axes = (left, right)
        left.set_xlim(x_min, lower)
        right.set_xlim(upper, x_max)
        left.spines["right"].set_visible(False)
        right.spines["left"].set_visible(False)
        right.tick_params(labelleft=False)
        left.set_xlabel(xlabel)
        right.set_xlabel(xlabel)
        left.set_ylabel(ylabel)
        _break_marks_x(left, right)

    for target in target_axes:
        for x, y, style in payload:
            (line,) = target.plot(x, y, **style)
            line._sciplotter_x_values = x.tolist()
            line._sciplotter_y_values = y.tolist()
        target.grid(True, alpha=0.25)
    if title:
        figure.suptitle(title)
    handles, labels = target_axes[0].get_legend_handles_labels()
    pairs = [
        (handle, label)
        for handle, label in zip(handles, labels)
        if label and not str(label).startswith("_")
    ]
    if pairs:
        handles, labels = zip(*pairs)
        target_axes[0].legend(handles, labels, loc="best")
    try:
        figure.tight_layout()
    except Exception:
        pass
    return target_axes
