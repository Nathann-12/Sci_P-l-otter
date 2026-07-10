from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import warnings

import matplotlib.dates as mdates
from matplotlib.figure import Figure


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.plot_data import clamp_date_limits, mostly_numeric, prepare_plot_data


def test_prepare_plot_data_converts_mostly_valid_datetime_strings():
    x_values = ["2024-01-01", "bad", "2024-01-03", "2024-01-04"]
    y_values = [10, 20, 30, 40]

    x_prepared, y_prepared, x_is_datetime = prepare_plot_data(x_values, y_values)

    assert x_is_datetime is True
    assert y_prepared == [10, 30, 40]
    assert x_prepared == mdates.date2num(
        [
            datetime(2024, 1, 1),
            datetime(2024, 1, 3),
            datetime(2024, 1, 4),
        ]
    ).tolist()


def test_prepare_plot_data_keeps_sparse_datetime_strings_as_plain_values():
    x_values = ["2024-01-01", "bad", "still bad"]
    y_values = [1, 2, 3]

    x_prepared, y_prepared, x_is_datetime = prepare_plot_data(x_values, y_values)

    assert x_is_datetime is False
    assert x_prepared == x_values
    assert y_prepared == y_values


def test_prepare_plot_data_does_not_warn_for_categorical_strings():
    x_values = ["alpha", "beta", "gamma"]
    y_values = [1, 2, 3]

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        x_prepared, y_prepared, x_is_datetime = prepare_plot_data(x_values, y_values)

    assert x_prepared == x_values
    assert y_prepared == y_values
    assert x_is_datetime is False


def test_prepare_plot_data_truncates_to_shortest_series_after_filtering():
    x_values = [0, 1, 2, 3]
    y_values = [10, None, 30]

    x_prepared, y_prepared, x_is_datetime = prepare_plot_data(x_values, y_values)

    assert x_is_datetime is False
    assert x_prepared == [0, 2]
    assert y_prepared == [10, 30]


def test_mostly_numeric_accepts_threshold_with_string_numbers():
    values = [1, "2.5", 3, "4", False]

    assert mostly_numeric(values) is True


def test_clamp_date_limits_clamps_datetime_axes_to_supported_range():
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([datetime(2024, 1, 1), datetime(2024, 1, 2)], [1, 2])

    min_ord = mdates.date2num(datetime(1, 1, 1))
    max_ord = mdates.date2num(datetime(9999, 12, 31))
    ax.set_xlim(min_ord - 1000, max_ord + 1000)

    clamp_date_limits(ax)

    assert ax.get_xlim() == (min_ord, max_ord)
