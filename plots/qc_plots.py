"""Origin-style quality-control & categorical plots.

Pure Matplotlib plotting functions. Each ``func(ax, df, **opts) -> None``:

* clears the axes first, draws, sets a title + axis labels;
* never raises — insufficient data falls back to :func:`placeholder`;
* depends only on numpy / pandas / scipy / matplotlib and :mod:`plots._common`.

The module-level :data:`PLOTS` registry describes each plot for the gallery UI.
"""
from __future__ import annotations

import numpy as np

from plots._common import (
    numeric_columns,
    numeric_series,
    placeholder,
    color_cycle,
    downsample,
    clean_pair,
)


def run_chart(ax, df, **opts) -> None:
    """Run chart: first numeric column in sequence with a median line."""
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series:
        placeholder(ax, "Run Chart needs a numeric column")
        return
    name, values = series[0]
    values = downsample(values)
    x = np.arange(values.size)
    ax.plot(x, values, "-o", ms=3, color=color_cycle(1)[0], label=name)
    med = float(np.median(values))
    ax.axhline(med, color="#e0653a", lw=1.5, label=f"Median = {med:.3g}")
    ax.set_title("Run Chart")
    ax.set_xlabel("Observation")
    ax.set_ylabel(name)
    ax.legend(loc="best", fontsize=8)


def control_xbar(ax, df, **opts) -> None:
    """X-bar control chart: CL = mean, UCL/LCL = mean +/- 3*sigma."""
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series or series[0][1].size < 2:
        placeholder(ax, "Control chart needs >= 2 values")
        return
    name, values = series[0]
    mean = float(np.mean(values))
    sigma = float(np.std(values, ddof=1))
    ucl, lcl = mean + 3 * sigma, mean - 3 * sigma
    x = np.arange(values.size)
    ax.plot(x, values, "-o", ms=3, color=color_cycle(1)[0], label=name)
    ax.axhline(mean, color="#2a9d4a", lw=1.5, label=f"CL = {mean:.3g}")
    ax.axhline(ucl, color="#d62728", lw=1.2, ls="--", label=f"UCL = {ucl:.3g}")
    ax.axhline(lcl, color="#d62728", lw=1.2, ls="--", label=f"LCL = {lcl:.3g}")
    out = (values > ucl) | (values < lcl)
    if out.any():
        ax.scatter(x[out], values[out], s=70, facecolors="none",
                   edgecolors="#d62728", linewidths=1.8, zorder=5,
                   label="Out of control")
    ax.set_title("X-bar Control Chart")
    ax.set_xlabel("Observation")
    ax.set_ylabel(name)
    ax.legend(loc="best", fontsize=8)


def control_imr(ax, df, **opts) -> None:
    """I-MR individuals chart: CL = mean, limits from average moving range."""
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series or series[0][1].size < 2:
        placeholder(ax, "I-MR chart needs >= 2 values")
        return
    name, values = series[0]
    mean = float(np.mean(values))
    mr_bar = float(np.mean(np.abs(np.diff(values))))
    ucl, lcl = mean + 2.66 * mr_bar, mean - 2.66 * mr_bar
    x = np.arange(values.size)
    ax.plot(x, values, "-o", ms=3, color=color_cycle(1)[0], label=name)
    ax.axhline(mean, color="#2a9d4a", lw=1.5, label=f"CL = {mean:.3g}")
    ax.axhline(ucl, color="#d62728", lw=1.2, ls="--", label=f"UCL = {ucl:.3g}")
    ax.axhline(lcl, color="#d62728", lw=1.2, ls="--", label=f"LCL = {lcl:.3g}")
    out = (values > ucl) | (values < lcl)
    if out.any():
        ax.scatter(x[out], values[out], s=70, facecolors="none",
                   edgecolors="#d62728", linewidths=1.8, zorder=5)
    ax.set_title("I-MR (Individuals) Chart")
    ax.set_xlabel("Observation")
    ax.set_ylabel(name)
    ax.legend(loc="best", fontsize=8)


def pareto(ax, df, **opts) -> None:
    """Pareto chart: sorted bars + cumulative-% line with an 80% reference."""
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series:
        placeholder(ax, "Pareto needs a numeric column")
        return
    name, values = series[0]
    values = np.abs(values)
    order = np.sort(values)[::-1]
    total = float(order.sum())
    if total <= 0:
        placeholder(ax, "Pareto needs positive values")
        return
    order = downsample(order)
    total = float(order.sum())
    x = np.arange(order.size)
    ax.bar(x, order, color=color_cycle(1)[0], label=name)
    ax.set_title("Pareto Chart")
    ax.set_xlabel("Category (sorted)")
    ax.set_ylabel(name)
    cum = np.cumsum(order) / total * 100.0
    ax2 = ax.twinx()
    ax2.plot(x, cum, "-o", ms=3, color="#d62728", label="Cumulative %")
    ax2.axhline(80.0, color="#888888", lw=1.0, ls=":", label="80%")
    ax2.set_ylabel("Cumulative %")
    ax2.set_ylim(0, 105)
    ax.legend(loc="upper left", fontsize=8)
    ax2.legend(loc="lower right", fontsize=8)


def main_effects(ax, df, **opts) -> None:
    """Main effects plot: column means connected across columns."""
    ax.clear()
    series = numeric_series(df)
    if len(series) < 2:
        placeholder(ax, "Main Effects needs >= 2 columns")
        return
    names = [n for n, _ in series]
    means = [float(np.mean(v)) for _, v in series]
    x = np.arange(len(names))
    ax.plot(x, means, "-o", ms=6, color=color_cycle(1)[0])
    grand = float(np.mean(means))
    ax.axhline(grand, color="#888888", lw=1.0, ls="--", label=f"Grand mean = {grand:.3g}")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_title("Main Effects Plot")
    ax.set_xlabel("Factor")
    ax.set_ylabel("Mean")
    ax.legend(loc="best", fontsize=8)


def interaction_plot(ax, df, **opts) -> None:
    """Interaction plot: col1 binned into low/high; means of responses per level."""
    ax.clear()
    cols = numeric_columns(df)
    if len(cols) < 2:
        placeholder(ax, "Interaction Plot needs >= 2 columns")
        return
    group_name = cols[0]
    responses = cols[1:]
    levels = ["Low", "High"]
    xpos = np.array([0, 1])
    colors = color_cycle(len(responses))
    plotted = False
    for i, resp in enumerate(responses):
        g, y = clean_pair(df[group_name], df[resp])
        if g.size < 2:
            continue
        med = float(np.median(g))
        low_mask = g <= med
        high_mask = ~low_mask
        if not low_mask.any() or not high_mask.any():
            continue
        means = [float(np.mean(y[low_mask])), float(np.mean(y[high_mask]))]
        ax.plot(xpos, means, "-o", ms=6, color=colors[i], label=str(resp))
        plotted = True
    if not plotted:
        placeholder(ax, "Not enough data to split by median")
        return
    ax.set_xticks(xpos)
    ax.set_xticklabels(levels)
    ax.set_title("Interaction Plot")
    ax.set_xlabel(f"{group_name} (by median)")
    ax.set_ylabel("Response mean")
    ax.legend(loc="best", fontsize=8)


def bar_mean_sd(ax, df, **opts) -> None:
    """Bar chart of per-column mean with a symmetric SD error bar."""
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Bar (Mean +/- SD) needs a numeric column")
        return
    names = [n for n, _ in series]
    means = [float(np.mean(v)) for _, v in series]
    sds = [float(np.std(v, ddof=1)) if v.size > 1 else 0.0 for _, v in series]
    x = np.arange(len(names))
    ax.bar(x, means, yerr=sds, capsize=4, color=color_cycle(len(names)),
           error_kw={"ecolor": "#333333", "elinewidth": 1.2})
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_title("Bar (Mean +/- SD)")
    ax.set_xlabel("Column")
    ax.set_ylabel("Mean")


def interval_plot(ax, df, **opts) -> None:
    """Interval plot: per-column mean point with a 95% CI error bar."""
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Interval Plot needs a numeric column")
        return
    names = [n for n, _ in series]
    means = [float(np.mean(v)) for _, v in series]
    cis = []
    for _, v in series:
        if v.size > 1:
            cis.append(1.96 * float(np.std(v, ddof=1)) / np.sqrt(v.size))
        else:
            cis.append(0.0)
    x = np.arange(len(names))
    ax.errorbar(x, means, yerr=cis, fmt="o", ms=7, capsize=5,
                color=color_cycle(1)[0], ecolor="#333333", elinewidth=1.4)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_xlim(-0.5, len(names) - 0.5)
    ax.set_title("Interval Plot (95% CI)")
    ax.set_xlabel("Column")
    ax.set_ylabel("Mean")


def population_pyramid(ax, df, **opts) -> None:
    """Population pyramid: col1 to the left (negated), col2 to the right."""
    ax.clear()
    series = numeric_series(df, max_n=2)
    if len(series) < 2:
        placeholder(ax, "Population Pyramid needs >= 2 columns")
        return
    (n1, left), (n2, right) = series[0], series[1]
    m = min(left.size, right.size)
    left, right = np.abs(left[:m]), np.abs(right[:m])
    if m > 40:
        step = int(np.ceil(m / 40))
        left, right = left[::step], right[::step]
        m = left.size
    y = np.arange(m)
    cols = color_cycle(2)
    ax.barh(y, -left, color=cols[0], label=str(n1))
    ax.barh(y, right, color=cols[1], label=str(n2))
    ax.axvline(0, color="#333333", lw=1.0)
    ax.set_title("Population Pyramid")
    ax.set_xlabel("Value (left <-> right)")
    ax.set_ylabel("Category (row index)")
    ax.legend(loc="best", fontsize=8)


PLOTS = [
    {"key": "run_chart", "title": "Run Chart", "category": "Quality", "func": run_chart,
     "desc": "Values in sequence with the median line", "min_cols": 1, "multi": False},
    {"key": "control_xbar", "title": "X-bar Control Chart", "category": "Quality", "func": control_xbar,
     "desc": "Points with CL and +/-3 sigma control limits", "min_cols": 1, "multi": False},
    {"key": "control_imr", "title": "I-MR (Individuals) Chart", "category": "Quality", "func": control_imr,
     "desc": "Individuals with limits from the average moving range", "min_cols": 1, "multi": False},
    {"key": "pareto", "title": "Pareto Chart", "category": "Quality", "func": pareto,
     "desc": "Sorted bars with a cumulative-% line and 80% reference", "min_cols": 1, "multi": False},
    {"key": "main_effects", "title": "Main Effects Plot", "category": "Categorical", "func": main_effects,
     "desc": "Compare the mean of each numeric column", "min_cols": 2, "multi": False},
    {"key": "interaction_plot", "title": "Interaction Plot", "category": "Categorical", "func": interaction_plot,
     "desc": "Response means across two levels of the first column", "min_cols": 2, "multi": False},
    {"key": "bar_mean_sd", "title": "Bar (Mean +/- SD)", "category": "Categorical", "func": bar_mean_sd,
     "desc": "One bar per column at its mean with an SD error bar", "min_cols": 1, "multi": False},
    {"key": "interval_plot", "title": "Interval Plot", "category": "Categorical", "func": interval_plot,
     "desc": "Per-column mean with a 95% confidence interval", "min_cols": 1, "multi": False},
    {"key": "population_pyramid", "title": "Population Pyramid", "category": "Categorical", "func": population_pyramid,
     "desc": "Two columns as opposing horizontal bars", "min_cols": 2, "multi": False},
]
