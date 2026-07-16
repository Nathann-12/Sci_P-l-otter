from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.figure import Figure


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.render_optimization import (
    FAST_BAR_THRESHOLD,
    LINE_LOD_THRESHOLD,
    MAX_CATEGORICAL_TICKS,
    SCATTER_DENSITY_THRESHOLD,
    SCATTER_RASTER_THRESHOLD,
    aggregate_bars_for_pixels,
    apply_line_lod,
    categorical_tick_indexes,
    draw_bar_series,
    draw_scatter_series,
    minmax_decimate,
    render_info_for,
    scatter_kwargs_for_count,
)


def _axes():
    figure = Figure()
    return figure.add_subplot(111)


def test_large_bar_uses_one_collection_and_bounded_ticks():
    ax = _axes()
    count = 5_000

    artists, info = draw_bar_series(
        ax,
        [f"row-{index}" for index in range(count)],
        np.sin(np.arange(count) / 50.0),
        label="signal",
        width=0.8,
    )

    assert len(artists) == 1
    assert isinstance(artists[0], PolyCollection)
    assert info["render_mode"] == "polycollection"
    assert info["artist_count"] == 1
    assert info["rendered_count"] == count
    assert len(ax.patches) == 0
    assert len(ax.collections) == 1
    assert len(ax.get_xticks()) <= MAX_CATEGORICAL_TICKS
    assert artists[0]._sciplotter_x_values[0] == "row-0"
    assert len(artists[0]._sciplotter_y_values) == count


def test_small_bar_preserves_standard_rectangle_behavior():
    ax = _axes()
    artists, info = draw_bar_series(ax, ["a", "b", "c"], [3, 1, 2], width=0.8)

    assert len(artists) == 3
    assert info["render_mode"] == "patches"
    assert len(ax.patches) == 3
    assert [tick.get_text() for tick in ax.get_xticklabels()] == ["a", "b", "c"]


def test_render_plan_is_transparent_and_never_decimates_phase_one():
    x = list(range(FAST_BAR_THRESHOLD))
    y = [float(index) for index in x]
    info = render_info_for("bar", x, y)

    assert info == {
        "source_count": FAST_BAR_THRESHOLD,
        "rendered_count": FAST_BAR_THRESHOLD,
        "render_mode": "polycollection",
        "artist_count": 1,
        "lod_applied": False,
    }


def test_large_scatter_enables_rasterization_without_changing_count():
    kwargs = scatter_kwargs_for_count(SCATTER_RASTER_THRESHOLD, {"s": 6})
    info = render_info_for(
        "scatter",
        range(SCATTER_RASTER_THRESHOLD),
        range(SCATTER_RASTER_THRESHOLD),
    )

    assert kwargs == {"s": 6, "rasterized": True}
    assert info["rendered_count"] == info["source_count"] == SCATTER_RASTER_THRESHOLD
    assert info["render_mode"] == "rasterized"
    assert info["lod_applied"] is False


def test_categorical_tick_sampling_retains_endpoints():
    indexes = categorical_tick_indexes(5_000)

    assert len(indexes) <= MAX_CATEGORICAL_TICKS
    assert indexes[0] == 0
    assert indexes[-1] == 4_999


def test_minmax_decimation_preserves_positive_and_negative_spikes():
    count = 100_000
    x = np.arange(count, dtype=float)
    y = np.zeros(count)
    y[12_345] = 99.0
    y[54_321] = -77.0

    _rx, rendered_y, indexes = minmax_decimate(x, y, pixel_width=800)

    assert len(indexes) <= 1_602
    assert 12_345 in indexes
    assert 54_321 in indexes
    assert max(rendered_y) == 99.0
    assert min(rendered_y) == -77.0


def test_line_lod_uses_log_axis_pixel_transform_and_retains_full_source():
    ax = _axes()
    x = np.geomspace(1.0, 1_000_000.0, 50_000)
    y = np.sin(np.linspace(0, 500, x.size))
    y[20_000] = 50.0
    (line,) = ax.plot(x, y)
    line._sciplotter_x_values = x.tolist()
    line._sciplotter_y_values = y.tolist()
    ax.set_xscale("log")
    ax.set_xlim(1.0, 1_000_000.0)

    info = apply_line_lod(ax, line, pixel_width=600)

    assert info["render_mode"] == "minmax"
    assert info["rendered_count"] <= 1_202
    assert max(line.get_ydata()) == 50.0
    assert len(line._sciplotter_y_values) == 50_000


def test_line_lod_supports_datetime_x_values():
    ax = _axes()
    start = np.datetime64("2024-01-01T00:00:00")
    x = start + np.arange(20_000).astype("timedelta64[s]")
    y = np.cos(np.linspace(0, 200, x.size))
    y[9_999] = 25.0
    (line,) = ax.plot(x, y)
    line._sciplotter_x_values = x.tolist()
    line._sciplotter_y_values = y.tolist()
    ax.relim()
    ax.autoscale_view()

    info = apply_line_lod(ax, line, pixel_width=500)

    assert info["render_mode"] == "minmax"
    assert info["rendered_count"] <= 1_010
    assert max(line.get_ydata()) == 25.0
    assert len(line._sciplotter_x_values) == 20_000


def test_bar_pixel_sum_and_mean_are_explicit_and_deterministic():
    values = np.arange(1.0, 101.0)
    _x, summed, _widths, _indexes = aggregate_bars_for_pixels(
        values, pixel_width=10, reducer="sum"
    )
    _x, means, _widths, _indexes = aggregate_bars_for_pixels(
        values, pixel_width=10, reducer="mean"
    )

    assert summed.size == means.size == 10
    assert np.isclose(summed.sum(), values.sum())
    assert np.allclose(means, [np.mean(chunk) for chunk in np.array_split(values, 10)])


def test_scatter_auto_density_retains_full_arrays_and_reports_bins():
    ax = _axes()
    count = SCATTER_DENSITY_THRESHOLD
    x = np.linspace(-5.0, 5.0, count)
    y = np.sin(x * 7.0)

    artists, info = draw_scatter_series(ax, x, y, scatter_mode="auto")

    assert info["render_mode"] == "density"
    assert info["source_count"] == info["rendered_count"] == count
    assert info["bin_count"] > 0
    assert len(artists[0]._sciplotter_x_values) == count
    assert info["lod_applied"] is True
