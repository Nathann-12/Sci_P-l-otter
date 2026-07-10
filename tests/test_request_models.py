from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import matplotlib.dates as mdates
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from core.export_request import (
    BatchFigureExportOptions,
    ExportSeries,
    VisibleRangeExportRequest,
    batch_export_filename,
    dataframe_for_visible_range,
    safe_export_stem,
)
from core.plot_request import BarRequest, HistogramRequest, PlotOptions


def test_plot_options_validate_and_derive_scatter_size():
    options = PlotOptions(line_width=3, histogram_bins=12, bar_width=0.6)

    assert options.resolved_scatter_size == 15
    with pytest.raises(ValueError):
        PlotOptions(line_width=0)
    with pytest.raises(ValueError):
        PlotOptions(histogram_bins=0)


def test_histogram_and_bar_requests_expose_origin_style_labels():
    options = PlotOptions(histogram_bins=8)
    histogram = HistogramRequest([1, 2, 3], "signal", options)
    bar = BarRequest(["A", "B"], [4, 5], "group", "count", "Counts")

    assert histogram.title == "Histogram of signal (bins=8)"
    assert bar.label == "Counts"


def test_visible_range_request_filters_dataframe_without_widgets():
    dataframe = pd.DataFrame({"time": [0, 1, 2, 3], "value": [10, 20, 30, 40]})
    request = VisibleRangeExportRequest(dataframe, "time", 0.5, 2.5)

    result = dataframe_for_visible_range(request)

    assert result.to_dict(orient="list") == {"time": [1, 2], "value": [20, 30]}


def test_visible_range_request_falls_back_to_graph_series():
    dataframe = pd.DataFrame({"time": [10, 11], "value": [1, 2]})
    request = VisibleRangeExportRequest(
        dataframe,
        "time",
        0.5,
        1.5,
        series=(ExportSeries([0, 1, 2], [5, 6, 7], "signal"),),
    )

    result = dataframe_for_visible_range(request)

    assert result.to_dict(orient="list") == {"time": [1.0], "signal": [6]}


def test_visible_range_request_preserves_duplicate_x_without_cartesian_growth():
    dataframe = pd.DataFrame({"time": [10, 11], "value": [1, 2]})
    request = VisibleRangeExportRequest(
        dataframe,
        "time",
        -1,
        2,
        series=(
            ExportSeries([0, 0, 1], [10, 11, 12], "signal"),
            ExportSeries([0, 0, 1], [20, 21, 22], "signal"),
        ),
    )

    result = dataframe_for_visible_range(request)

    assert result.to_dict(orient="list") == {
        "time": [0.0, 0.0, 1.0],
        "signal": [10, 11, 12],
        "signal (2)": [20, 21, 22],
    }


def test_visible_range_request_preserves_datetime_x():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    dataframe = pd.DataFrame({"time": dates, "value": [1, 2, 3]})
    lower, upper = mdates.date2num(
        [datetime(2024, 1, 1, 12), datetime(2024, 1, 2, 12)]
    )
    request = VisibleRangeExportRequest(dataframe, "time", lower, upper)

    result = dataframe_for_visible_range(request)

    assert result["time"].tolist() == [pd.Timestamp("2024-01-02")]


def test_batch_export_options_validate_directory_and_dpi(tmp_path):
    options = BatchFigureExportOptions(
        format_name="PNG",
        directory=str(tmp_path),
        dpi=300,
    )
    assert options.directory == str(tmp_path)

    with pytest.raises(ValueError):
        BatchFigureExportOptions(format_name="PNG", directory="", dpi=300)
    with pytest.raises(ValueError):
        BatchFigureExportOptions(format_name="PNG", directory=str(tmp_path), dpi=0)


def test_batch_export_filename_is_windows_safe(tmp_path):
    assert safe_export_stem('Graph: 1 / "bad"*name') == "Graph_ 1 _ _bad_name"
    path = batch_export_filename(tmp_path, 'Graph: 1 / "bad"*name', 2, ".PNG")

    assert path.parent == tmp_path
    assert path.name == "02_Graph_ 1 _ _bad_name.png"
