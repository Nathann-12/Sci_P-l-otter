"""Relational & probability plots (Origin-style) for the plot gallery.

Pure Matplotlib/numpy/pandas/scipy plotting functions. Each ``f(ax, df, **opts)``
draws onto an Axes (or repaints ``ax.figure`` for multi-panel plots), never
raises, and falls back to :func:`plots._common.placeholder` when there is not
enough data. See the module-level :data:`PLOTS` catalog at the end.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from plots._common import (
    numeric_columns,
    numeric_series,
    clean_pair,
    placeholder,
    color_cycle,
    downsample,
)


def _normal_cdf(z: np.ndarray) -> np.ndarray:
    """Standard-normal CDF (scipy if available, else erf fallback)."""
    try:
        from scipy import stats
        return stats.norm.cdf(z)
    except Exception:
        from math import erf, sqrt
        vec = np.vectorize(lambda v: 0.5 * (1.0 + erf(v / sqrt(2.0))))
        return vec(np.asarray(z, dtype=float))


def _normal_ppf(p: np.ndarray) -> np.ndarray:
    """Standard-normal inverse CDF (probit); scipy if available, else approx."""
    p = np.asarray(p, dtype=float)
    try:
        from scipy import stats
        return stats.norm.ppf(p)
    except Exception:
        # Acklam's rational approximation (accurate enough for plotting).
        a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
             1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
        b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
             6.680131188771972e+01, -1.328068155288572e+01]
        c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
             -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
        d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
             3.754408661907416e+00]

        def one(pp):
            if not (0.0 < pp < 1.0):
                return np.nan
            if pp < 0.02425:
                q = np.sqrt(-2 * np.log(pp))
                return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                       ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
            if pp > 1 - 0.02425:
                q = np.sqrt(-2 * np.log(1 - pp))
                return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
            q = pp - 0.5
            r = q * q
            return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
                   (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)

        return np.vectorize(one)(p)


def corr_heatmap(ax, df, **opts) -> None:
    """Correlation-matrix heatmap over numeric columns."""
    ax.clear()
    cols = numeric_columns(df)
    if len(cols) < 2:
        placeholder(ax, "Need >= 2 numeric columns")
        return
    corr = df[cols].corr(numeric_only=True)
    mat = corr.to_numpy(dtype=float)
    labels = list(corr.columns)
    im = ax.imshow(mat, cmap="coolwarm", vmin=-1.0, vmax=1.0, aspect="auto")
    ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)
    for i in range(len(labels)):
        for j in range(len(labels)):
            val = mat[i, j]
            if np.isfinite(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        color="black" if abs(val) < 0.6 else "white", fontsize=8)
    ax.set_title("Correlation Plot")


def scatter_matrix(ax, df, **opts) -> None:
    """Pairwise scatter grid (diagonal = histogram) for numeric columns."""
    series = numeric_series(df, max_n=6)
    if len(series) < 2:
        placeholder(ax, "Need >= 2 numeric columns")
        return
    fig = ax.figure
    fig.clf()
    k = len(series)
    axes = fig.subplots(k, k, sharex=False, sharey=False)
    axes = np.atleast_2d(axes)
    names = [n for n, _ in series]
    for i in range(k):
        for j in range(k):
            a = axes[i, j]
            if i == j:
                a.hist(downsample(series[i][1]), bins=20, color=color_cycle(1)[0])
            else:
                x, y = clean_pair(series[j][1], series[i][1])
                a.scatter(downsample(x), downsample(y), s=6, alpha=0.5)
            if i == k - 1:
                a.set_xlabel(names[j], fontsize=8)
            if j == 0:
                a.set_ylabel(names[i], fontsize=8)
            a.tick_params(labelsize=6)
    fig.suptitle("Scatter Matrix")


def qq_plot(ax, df, **opts) -> None:
    """Q-Q plot of the first numeric column vs a normal distribution."""
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series or series[0][1].size < 3:
        placeholder(ax, "Need a numeric column")
        return
    name, data = series[0]
    data = downsample(np.sort(data))
    n = data.size
    try:
        from scipy import stats
        (theo, sample), (slope, intercept, _r) = stats.probplot(data, dist="norm")
    except Exception:
        probs = (np.arange(1, n + 1) - 0.5) / n
        theo = _normal_ppf(probs)
        sample = data
        slope, intercept = np.std(data, ddof=1), float(np.mean(data))
    ax.scatter(theo, sample, s=12, alpha=0.7)
    line_x = np.array([theo.min(), theo.max()])
    ax.plot(line_x, slope * line_x + intercept, color="crimson", lw=1.5, label="Reference")
    ax.set_title(f"Q-Q Plot ({name})")
    ax.set_xlabel("Theoretical quantiles")
    ax.set_ylabel("Sample quantiles")
    ax.legend()


def probability_plot(ax, df, **opts) -> None:
    """Normal probability plot: sorted values vs probit positions."""
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series or series[0][1].size < 3:
        placeholder(ax, "Need a numeric column")
        return
    name, data = series[0]
    data = downsample(np.sort(data))
    n = data.size
    probs = (np.arange(1, n + 1) - 0.375) / (n + 0.25)  # Blom plotting positions
    scores = _normal_ppf(probs)
    ax.scatter(data, scores, s=12, alpha=0.7)
    mu, sigma = float(np.mean(data)), float(np.std(data, ddof=1)) or 1.0
    ref_x = np.array([data.min(), data.max()])
    ax.plot(ref_x, (ref_x - mu) / sigma, color="crimson", lw=1.5, label="Reference")
    ax.set_title(f"Normal Probability Plot ({name})")
    ax.set_xlabel(name)
    ax.set_ylabel("Normal score")
    ax.legend()


def cdf_plot(ax, df, **opts) -> None:
    """Empirical CDF step plot for each numeric column."""
    ax.clear()
    series = numeric_series(df)
    if not series:
        placeholder(ax, "Need a numeric column")
        return
    colors = color_cycle(len(series))
    for (name, data), color in zip(series, colors):
        vals = downsample(np.sort(data))
        n = vals.size
        y = np.arange(1, n + 1) / n
        ax.step(vals, y, where="post", label=name, color=color)
    ax.set_title("Empirical CDF")
    ax.set_xlabel("Value")
    ax.set_ylabel("F(x)")
    ax.set_ylim(0, 1.02)
    if len(series) > 1:
        ax.legend()


def pp_plot(ax, df, **opts) -> None:
    """P-P plot: empirical CDF vs theoretical normal CDF for the first column."""
    ax.clear()
    series = numeric_series(df, max_n=1)
    if not series or series[0][1].size < 3:
        placeholder(ax, "Need a numeric column")
        return
    name, data = series[0]
    data = downsample(np.sort(data))
    n = data.size
    emp = (np.arange(1, n + 1) - 0.5) / n
    mu, sigma = float(np.mean(data)), float(np.std(data, ddof=1)) or 1.0
    theo = _normal_cdf((data - mu) / sigma)
    ax.scatter(theo, emp, s=12, alpha=0.7)
    ax.plot([0, 1], [0, 1], color="crimson", lw=1.5, label="45 deg")
    ax.set_title(f"P-P Plot ({name})")
    ax.set_xlabel("Theoretical CDF")
    ax.set_ylabel("Empirical CDF")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()


def bland_altman(ax, df, **opts) -> None:
    """Bland-Altman agreement plot for the first two numeric columns."""
    ax.clear()
    series = numeric_series(df, max_n=2)
    if len(series) < 2:
        placeholder(ax, "Need >= 2 numeric columns")
        return
    (n1, c1), (n2, c2) = series[0], series[1]
    a, b = clean_pair(c1, c2)
    if a.size < 2:
        placeholder(ax, "Not enough paired data")
        return
    mean = (a + b) / 2.0
    diff = a - b
    md = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1))
    ax.scatter(mean, diff, s=14, alpha=0.6)
    ax.axhline(md, color="crimson", lw=1.5, label=f"Mean diff = {md:.3g}")
    ax.axhline(md + 1.96 * sd, color="gray", ls="--", lw=1.2, label="+1.96 SD")
    ax.axhline(md - 1.96 * sd, color="gray", ls="--", lw=1.2, label="-1.96 SD")
    ax.set_title("Bland-Altman Plot")
    ax.set_xlabel(f"Mean of {n1} & {n2}")
    ax.set_ylabel(f"{n1} - {n2}")
    ax.legend()


def paired_comparison(ax, df, **opts) -> None:
    """Before/after paired comparison of the first two numeric columns."""
    ax.clear()
    series = numeric_series(df, max_n=2)
    if len(series) < 2:
        placeholder(ax, "Need >= 2 numeric columns")
        return
    (n1, c1), (n2, c2) = series[0], series[1]
    a, b = clean_pair(c1, c2)
    if a.size < 1:
        placeholder(ax, "Not enough paired data")
        return
    a, b = downsample(a), downsample(b)
    for xi, yi in zip(a, b):
        ax.plot([0, 1], [xi, yi], color="gray", alpha=0.4, lw=0.8, zorder=1)
    ax.scatter(np.zeros_like(a), a, s=16, color=color_cycle(2)[0], zorder=2)
    ax.scatter(np.ones_like(b), b, s=16, color=color_cycle(2)[1], zorder=2)
    m1, m2 = float(np.mean(a)), float(np.mean(b))
    ax.plot([0, 1], [m1, m2], color="crimson", lw=2.5, marker="D",
            label=f"Means: {m1:.3g} -> {m2:.3g}", zorder=3)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([n1, n2])
    ax.set_xlim(-0.3, 1.3)
    ax.set_title("Paired Comparison")
    ax.set_ylabel("Value")
    ax.legend()


def residual_plot(ax, df, **opts) -> None:
    """Residuals vs fitted values for a least-squares fit of col2 on col1."""
    ax.clear()
    series = numeric_series(df, max_n=2)
    if len(series) < 2:
        placeholder(ax, "Need >= 2 numeric columns")
        return
    (nx, cx), (ny, cy) = series[0], series[1]
    x, y = clean_pair(cx, cy)
    if x.size < 2:
        placeholder(ax, "Not enough paired data")
        return
    if np.ptp(x) == 0:
        placeholder(ax, "Residual plot needs varying X values")
        return
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    resid = y - fitted
    fitted, resid = downsample(fitted), downsample(resid)
    ax.scatter(fitted, resid, s=14, alpha=0.6)
    ax.axhline(0.0, color="crimson", lw=1.5, label="Zero")
    ax.set_title(f"Residual Plot ({ny} vs {nx})")
    ax.set_xlabel("Fitted values")
    ax.set_ylabel("Residuals")
    ax.legend()


PLOTS = [
    {"key": "corr_heatmap", "title": "Correlation Plot", "category": "Relational", "func": corr_heatmap,
     "desc": "Correlation-matrix heatmap", "min_cols": 2, "multi": False},
    {"key": "scatter_matrix", "title": "Scatter Matrix", "category": "Relational", "func": scatter_matrix,
     "desc": "Pairwise scatter grid (diagonal histograms)", "min_cols": 2, "multi": True},
    {"key": "qq_plot", "title": "Q-Q Plot", "category": "Probability", "func": qq_plot,
     "desc": "Quantile-quantile plot vs normal distribution", "min_cols": 1, "multi": False},
    {"key": "probability_plot", "title": "Normal Probability Plot", "category": "Probability", "func": probability_plot,
     "desc": "Sorted values vs normal-score positions", "min_cols": 1, "multi": False},
    {"key": "cdf_plot", "title": "Empirical CDF", "category": "Probability", "func": cdf_plot,
     "desc": "Empirical CDF step plot per column", "min_cols": 1, "multi": False},
    {"key": "pp_plot", "title": "P-P Plot", "category": "Probability", "func": pp_plot,
     "desc": "Empirical vs theoretical normal CDF", "min_cols": 1, "multi": False},
    {"key": "bland_altman", "title": "Bland-Altman Plot", "category": "Relational", "func": bland_altman,
     "desc": "Agreement plot (mean vs difference)", "min_cols": 2, "multi": False},
    {"key": "paired_comparison", "title": "Paired Comparison", "category": "Relational", "func": paired_comparison,
     "desc": "Before/after paired values with group means", "min_cols": 2, "multi": False},
    {"key": "residual_plot", "title": "Residual Plot", "category": "Relational", "func": residual_plot,
     "desc": "Residuals vs fitted values of a linear fit", "min_cols": 2, "multi": False},
]
