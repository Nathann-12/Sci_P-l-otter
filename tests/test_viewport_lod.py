from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from widgets.plot_tabs import TabManager


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_line_zoom_rerenders_from_full_data_without_replacing_artist(qapp):
    tabs = TabManager()
    tab_id = tabs.get_current_tab_id()
    count = 50_000
    x = np.linspace(1.0, 1000.0, count)
    y = np.sin(x)
    y[25_000] = 80.0

    created = tabs.plot_to_tabs([tab_id], x, y, label="signal", style="line")
    layer_id = created[0][1]
    tab = tabs.tabs[tab_id]
    layer = tab.layers[layer_id]
    artist = layer["artists"][0]
    artist_id = id(artist)

    assert len(artist.get_xdata()) < count
    assert len(artist._sciplotter_x_values) == count
    assert max(artist.get_ydata()) == 80.0

    tab.get_axes().set_xlim(400.0, 600.0)
    results = tab.lod_controller.refresh(pixel_width=500, emit_status=False)

    assert id(layer["artists"][0]) == artist_id
    assert results[-1]["render_mode"] == "minmax"
    assert len(artist._sciplotter_x_values) == count
    assert 0 < len(artist.get_xdata()) <= 1_010


def test_export_uses_larger_pixel_budget_then_restores_screen_lod(qapp):
    tabs = TabManager()
    tab = tabs.tabs[tabs.get_current_tab_id()]
    x = np.arange(80_000, dtype=float)
    y = np.sin(x / 20.0)
    tabs.plot_to_tabs([tab.tab_id], x, y, label="wave", style="line")
    artist = next(iter(tab.layers.values()))["artists"][0]
    tab.get_axes().set_xlim(float(x.min()), float(x.max()))
    tab.lod_controller.refresh(pixel_width=400, emit_status=False)
    screen_count = len(artist.get_xdata())

    with tab.export_render(2400):
        export_count = len(artist.get_xdata())

    assert export_count > screen_count
    assert export_count <= 4_802
    assert len(artist.get_xdata()) < len(artist._sciplotter_x_values)


def test_bar_zoom_updates_same_collection_with_selected_reducer(qapp):
    tabs = TabManager()
    tab = tabs.tabs[tabs.get_current_tab_id()]
    count = 10_000
    created = tabs.plot_to_tabs(
        [tab.tab_id],
        [f"row-{i}" for i in range(count)],
        np.ones(count),
        label="counts",
        style="bar",
        bar_reducer="mean",
    )
    layer = tab.layers[created[0][1]]
    artist = layer["artists"][0]
    artist_id = id(artist)
    tab.get_axes().set_xlim(100.0, 300.0)

    results = tab.lod_controller.refresh(pixel_width=50, emit_status=False)

    assert id(layer["artists"][0]) == artist_id
    assert results[-1]["render_mode"] == "pixel-mean"
    assert results[-1]["rendered_count"] <= 50
    assert len(artist._sciplotter_y_values) == count
