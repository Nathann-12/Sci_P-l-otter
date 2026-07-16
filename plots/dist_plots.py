"""Origin-style distribution / density plots.

Pure Matplotlib plotters: each ``func(ax, df, **opts) -> None`` clears the axes
and draws one distribution per numeric column. No Qt, no file IO, no project
imports except :mod:`plots._common`. Functions never raise -- on insufficient
data they call :func:`placeholder` and return.
"""
from __future__ import annotations

import numpy as np

from plots._common import (
    numeric_series,
    numeric_columns,
    placeholder,
    color_cycle,
    downsample,
)

# reuse the shared down-sample cap for point clouds
_MAX_PTS = 2000


def _kde(values, grid):
    """gaussian_kde(values) evaluated on *grid*, or None on failure."""
    try:
        from scipy.stats import gaussian_kde

        v = np.asarray(values, dtype=float)
        if v.size < 2 or np.ptp(v) == 0:
            return None
        return gaussian_kde(v)(grid)
    except Exception:
        return None


def box(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Box Chart needs at least one numeric column.")
        return
    names = [n for n, _ in series]
    ax.boxplot([v for _, v in series])
    ax.set_xticklabels(names)
    ax.set_ylabel("Value")
    ax.set_title("Box Chart")


def box_notched(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Box Chart needs at least one numeric column.")
        return
    names = [n for n, _ in series]
    ax.boxplot([v for _, v in series], notch=True)
    ax.set_xticklabels(names)
    ax.set_ylabel("Value")
    ax.set_title("Box Chart (Notched)")


def half_box(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Half Box needs at least one numeric column.")
        return
    rng = np.random.default_rng(0)
    colors = color_cycle(len(series))
    for i, (name, v) in enumerate(series):
        pos = i + 1
        # box on the left half of the slot
        ax.boxplot([v], positions=[pos - 0.18], widths=0.28,
                   patch_artist=False, showfliers=False)
        # jittered raw points on the right half
        pts = downsample(v, _MAX_PTS)
        jitter = pos + 0.18 + rng.uniform(-0.08, 0.08, size=pts.size)
        ax.scatter(jitter, pts, s=6, alpha=0.4, color=colors[i])
    ax.set_xticks(range(1, len(series) + 1))
    ax.set_xticklabels([n for n, _ in series])
    ax.set_ylabel("Value")
    ax.set_title("Half Box")


def violin(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Violin Plot needs at least one numeric column.")
        return
    ax.violinplot([v for _, v in series], showmedians=True)
    ax.set_xticks(range(1, len(series) + 1))
    ax.set_xticklabels([n for n, _ in series])
    ax.set_ylabel("Value")
    ax.set_title("Violin Plot")


def violin_box(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Violin Plot needs at least one numeric column.")
        return
    data = [v for _, v in series]
    ax.violinplot(data, showextrema=False)
    ax.boxplot(data, widths=0.12, showfliers=False,
               patch_artist=True,
               boxprops=dict(facecolor="black", edgecolor="black"),
               medianprops=dict(color="white"),
               whiskerprops=dict(color="black"))
    ax.set_xticks(range(1, len(series) + 1))
    ax.set_xticklabels([n for n, _ in series])
    ax.set_ylabel("Value")
    ax.set_title("Violin + Box")


def violin_quartile(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Violin Plot needs at least one numeric column.")
        return
    for i, (_, v) in enumerate(series):
        pos = i + 1
        ax.violinplot([v], positions=[pos], showextrema=False)
        q1, med, q3 = np.percentile(v, [25, 50, 75])
        for y, ls in ((q1, ":"), (med, "-"), (q3, ":")):
            ax.hlines(y, pos - 0.35, pos + 0.35, color="black", linestyle=ls, lw=1.2)
    ax.set_xticks(range(1, len(series) + 1))
    ax.set_xticklabels([n for n, _ in series])
    ax.set_ylabel("Value")
    ax.set_title("Violin (Quartile)")


def _half_kde(values, side, pos, npts=100, width=0.4):
    """Return (x, y) polygon coords for one side of a KDE violin, or None."""
    v = np.asarray(values, dtype=float)
    lo, hi = np.min(v), np.max(v)
    if lo == hi:
        return None
    grid = np.linspace(lo, hi, npts)
    dens = _kde(v, grid)
    if dens is None:
        return None
    dens = dens / dens.max() * width
    xs = pos + side * dens
    # close the polygon along the center line
    xpoly = np.concatenate([[pos], xs, [pos]])
    ypoly = np.concatenate([[grid[0]], grid, [grid[-1]]])
    return xpoly, ypoly


def split_violin(ax, df, **opts):
    ax.clear()
    series = numeric_series(df, max_n=2)
    if len(series) < 2:
        placeholder(ax, "Split Violin needs at least two numeric columns.")
        return
    colors = color_cycle(2)
    pos = 1.0
    ok = False
    for side, (name, v), c in ((-1, series[0], colors[0]), (1, series[1], colors[1])):
        poly = _half_kde(v, side, pos)
        if poly is None:
            continue
        ax.fill(poly[0], poly[1], color=c, alpha=0.6, label=str(name))
        ok = True
    if not ok:
        placeholder(ax, "Not enough spread to build a split violin.")
        return
    ax.set_xticks([pos])
    ax.set_xticklabels([f"{series[0][0]} | {series[1][0]}"])
    ax.set_ylabel("Value")
    ax.set_title("Split Violin")
    ax.legend(loc="best")


def half_violin(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Half Violin needs at least one numeric column.")
        return
    rng = np.random.default_rng(1)
    colors = color_cycle(len(series))
    for i, (_, v) in enumerate(series):
        pos = i + 1
        poly = _half_kde(v, -1, pos, width=0.35)
        if poly is not None:
            ax.fill(poly[0], poly[1], color=colors[i], alpha=0.5)
        pts = downsample(v, _MAX_PTS)
        jitter = pos + 0.15 + rng.uniform(0, 0.12, size=pts.size)
        ax.scatter(jitter, pts, s=6, alpha=0.4, color=colors[i])
    ax.set_xticks(range(1, len(series) + 1))
    ax.set_xticklabels([n for n, _ in series])
    ax.set_ylabel("Value")
    ax.set_title("Half Violin")


def beeswarm(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Beeswarm needs at least one numeric column.")
        return
    rng = np.random.default_rng(2)
    colors = color_cycle(len(series))
    for i, (_, v) in enumerate(series):
        pts = downsample(v, _MAX_PTS)
        jitter = (i + 1) + rng.uniform(-0.22, 0.22, size=pts.size)
        ax.scatter(jitter, pts, s=8, alpha=0.5, color=colors[i])
    ax.set_xticks(range(1, len(series) + 1))
    ax.set_xticklabels([n for n, _ in series])
    ax.set_ylabel("Value")
    ax.set_title("Beeswarm")


def ridgeline(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Ridgeline needs at least one numeric column.")
        return
    colors = color_cycle(len(series))
    offset_step = 0.8
    yticks, ylabels = [], []
    drew = False
    for i, (name, v) in enumerate(series):
        base = i * offset_step
        yticks.append(base)
        ylabels.append(str(name))
        lo, hi = np.min(v), np.max(v)
        if lo == hi:
            continue
        grid = np.linspace(lo, hi, 200)
        dens = _kde(v, grid)
        if dens is None:
            hist, edges = np.histogram(v, bins=20, density=True)
            grid = 0.5 * (edges[:-1] + edges[1:])
            dens = hist
        dmax = dens.max() or 1.0
        dens = dens / dmax * offset_step * 1.6
        ax.fill_between(grid, base, base + dens, color=colors[i], alpha=0.6)
        ax.plot(grid, base + dens, color="black", lw=0.8)
        drew = True
    if not drew:
        placeholder(ax, "Not enough spread to build a ridgeline.")
        return
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels)
    ax.set_xlabel("Value")
    ax.set_title("Ridgeline")


def prepare_ridgeline(df, cancel_token=None):
    """Compute all KDE curves in a cancelable background worker."""
    prepared = []
    for name, v in numeric_series(df):
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        lo, hi = np.min(v), np.max(v)
        if lo == hi:
            continue
        grid = np.linspace(lo, hi, 200)
        dens = _kde(v, grid)
        if dens is None:
            dens, edges = np.histogram(v, bins=20, density=True)
            grid = 0.5 * (edges[:-1] + edges[1:])
        prepared.append((name, grid, np.asarray(dens, dtype=float)))
    return prepared


def draw_ridgeline_prepared(ax, prepared):
    ax.clear()
    if not prepared:
        placeholder(ax, "Not enough spread to build a ridgeline.")
        return
    colors = color_cycle(len(prepared))
    offset_step = 0.8
    for i, ((name, grid, dens), color) in enumerate(zip(prepared, colors)):
        base = i * offset_step
        dmax = float(np.max(dens)) or 1.0
        scaled = dens / dmax * offset_step * 1.6
        ax.fill_between(grid, base, base + scaled, color=color, alpha=0.6)
        ax.plot(grid, base + scaled, color="black", lw=0.8)
    ax.set_yticks([i * offset_step for i in range(len(prepared))])
    ax.set_yticklabels([str(item[0]) for item in prepared])
    ax.set_xlabel("Value")
    ax.set_title("Ridgeline")


def histogram(ax, df, **opts):
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series:
        placeholder(ax, "Histogram needs at least one numeric column.")
        return
    name, v = series[0]
    ax.hist(v, bins=20, color=color_cycle(1)[0], edgecolor="black", alpha=0.85)
    ax.set_xlabel(str(name))
    ax.set_ylabel("Count")
    ax.set_title("Histogram")


def histogram_rug(ax, df, **opts):
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series:
        placeholder(ax, "Histogram needs at least one numeric column.")
        return
    name, v = series[0]
    ax.hist(v, bins=20, color=color_cycle(1)[0], edgecolor="black", alpha=0.85)
    pts = downsample(v, _MAX_PTS)
    ax.plot(pts, np.full(pts.size, 0.0), "|", color="black",
            markersize=10, alpha=0.5, transform=ax.get_xaxis_transform())
    ax.set_xlabel(str(name))
    ax.set_ylabel("Count")
    ax.set_title("Histogram + Rug")


def distribution(ax, df, **opts):
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series:
        placeholder(ax, "Distribution needs at least one numeric column.")
        return
    name, v = series[0]
    ax.hist(v, bins=20, density=True, color=color_cycle(1)[0],
            edgecolor="black", alpha=0.6)
    lo, hi = np.min(v), np.max(v)
    if lo != hi:
        grid = np.linspace(lo, hi, 200)
        dens = _kde(v, grid)
        if dens is not None:
            ax.plot(grid, dens, color="crimson", lw=1.8, label="KDE")
            ax.legend(loc="best")
    ax.set_xlabel(str(name))
    ax.set_ylabel("Density")
    ax.set_title("Distribution")


def prepare_distribution(df, cancel_token=None):
    """Compute the full-data histogram and KDE outside the GUI thread."""
    series = numeric_series(df, max_n=1)
    if not series:
        return None
    name, values = series[0]
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    counts, edges = np.histogram(values, bins=20, density=True)
    grid = density = None
    lo, hi = np.min(values), np.max(values)
    if lo != hi:
        grid = np.linspace(lo, hi, 200)
        density = _kde(values, grid)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    return str(name), counts, edges, grid, density


def draw_distribution_prepared(ax, prepared):
    ax.clear()
    if prepared is None:
        placeholder(ax, "Distribution needs at least one numeric column.")
        return
    name, counts, edges, grid, density = prepared
    ax.stairs(counts, edges, fill=True, color=color_cycle(1)[0], alpha=0.6)
    if grid is not None and density is not None:
        ax.plot(grid, density, color="crimson", lw=1.8, label="KDE")
        ax.legend(loc="best")
    ax.set_xlabel(str(name))
    ax.set_ylabel("Density")
    ax.set_title("Distribution")


def stacked_histogram(ax, df, **opts):
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Stacked Histogram needs at least one numeric column.")
        return
    data = [v for _, v in series]
    labels = [n for n, _ in series]
    ax.hist(data, bins=20, stacked=True, label=labels,
            color=color_cycle(len(series)), edgecolor="black", alpha=0.85)
    ax.set_xlabel("Value")
    ax.set_ylabel("Count")
    ax.set_title("Stacked Histogram")
    if len(series) > 1:
        ax.legend(loc="best")


def dot_plot(ax, df, **opts):
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series:
        placeholder(ax, "Dot Plot needs at least one numeric column.")
        return
    name, v = series[0]
    lo, hi = np.min(v), np.max(v)
    if lo == hi:
        placeholder(ax, "Dot Plot needs a range of values.")
        return
    nbins = min(30, max(10, int(np.sqrt(v.size))))
    counts, edges = np.histogram(v, bins=nbins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    color = color_cycle(1)[0]
    for c, n in zip(centers, counts):
        if n:
            ax.scatter(np.full(n, c), np.arange(1, n + 1),
                       s=20, color=color, edgecolor="black", linewidths=0.3)
    ax.set_xlabel(str(name))
    ax.set_ylabel("Count (stack)")
    ax.set_title("Dot Plot")


PLOTS = [
    {"key": "box", "title": "Box Chart", "category": "Distribution", "func": box,
     "desc": "Box-and-whisker per numeric column", "min_cols": 1, "multi": False},
    {"key": "box_notched", "title": "Box Chart (Notched)", "category": "Distribution", "func": box_notched,
     "desc": "Notched box-and-whisker per numeric column", "min_cols": 1, "multi": False},
    {"key": "half_box", "title": "Half Box", "category": "Distribution", "func": half_box,
     "desc": "Box on one side, jittered raw points on the other", "min_cols": 1, "multi": False},
    {"key": "violin", "title": "Violin Plot", "category": "Distribution", "func": violin,
     "desc": "Kernel-density violin per numeric column", "min_cols": 1, "multi": False},
    {"key": "violin_box", "title": "Violin + Box", "category": "Distribution", "func": violin_box,
     "desc": "Violin with a thin inner box per column", "min_cols": 1, "multi": False},
    {"key": "violin_quartile", "title": "Violin (Quartile)", "category": "Distribution", "func": violin_quartile,
     "desc": "Violin with Q1/median/Q3 lines per column", "min_cols": 1, "multi": False},
    {"key": "split_violin", "title": "Split Violin", "category": "Distribution", "func": split_violin,
     "desc": "Left half of col-1 vs right half of col-2", "min_cols": 2, "multi": False},
    {"key": "half_violin", "title": "Half Violin", "category": "Distribution", "func": half_violin,
     "desc": "One-sided violin with jittered points", "min_cols": 1, "multi": False},
    {"key": "beeswarm", "title": "Beeswarm", "category": "Distribution", "func": beeswarm,
     "desc": "Jittered strip/beeswarm points per column", "min_cols": 1, "multi": False},
    {"key": "ridgeline", "title": "Ridgeline", "category": "Distribution", "func": ridgeline,
     "prepare": prepare_ridgeline, "draw_prepared": draw_ridgeline_prepared, "heavy": True,
     "desc": "Stacked, overlapping KDE curves (joyplot)", "min_cols": 1, "multi": False},
    {"key": "histogram", "title": "Histogram", "category": "Distribution", "func": histogram,
     "desc": "Histogram of the first numeric column", "min_cols": 1, "multi": False},
    {"key": "histogram_rug", "title": "Histogram + Rug", "category": "Distribution", "func": histogram_rug,
     "desc": "Histogram with a rug of tick marks", "min_cols": 1, "multi": False},
    {"key": "distribution", "title": "Distribution", "category": "Distribution", "func": distribution,
     "prepare": prepare_distribution, "draw_prepared": draw_distribution_prepared, "heavy": True,
     "desc": "Density histogram with overlaid KDE", "min_cols": 1, "multi": False},
    {"key": "stacked_histogram", "title": "Stacked Histogram", "category": "Distribution", "func": stacked_histogram,
     "desc": "Stacked histograms of all numeric columns", "min_cols": 1, "multi": False},
    {"key": "dot_plot", "title": "Dot Plot", "category": "Distribution", "func": dot_plot,
     "desc": "Wilkinson-style stacked dot plot", "min_cols": 1, "multi": False},
]
