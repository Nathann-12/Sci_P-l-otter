from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import widgets.chart_mega_menu as chart_menu_module
from widgets.chart_mega_menu import OriginChartMenu


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_chart_mega_menu_has_origin_style_categories_and_lazy_tiles(qapp):
    picked = []
    menu = OriginChartMenu(
        on_basic=lambda spec: picked.append(("basic", spec.key)),
        on_registry=lambda entry: picked.append(("registry", entry["key"])),
    )

    assert menu.title() == "Charts"
    assert menu._host.size().width() == 930
    assert menu._host.size().height() >= 600
    assert list(menu._categories)[:3] == [
        "Recently Used",
        "Basic 2D",
        "Bar, Pie, Area",
    ]
    assert "Contour, Heatmap" in menu._categories
    assert "Multi-Column" in menu._categories
    assert "Multi-Panel, Multi-Axis" in menu._categories
    assert "Specialized" in menu._categories
    assert "Signal & Frequency" in menu._categories
    assert menu._categories["Multi-Panel, Multi-Axis"]
    assert menu._categories["Specialized"]
    assert menu._categories["Signal & Frequency"]
    assert any(
        menu._items_by_id[item_id].projection == "polar"
        for item_id in menu._categories["Specialized"]
    )
    assert any(
        menu._items_by_id[item_id].registry_entry["key"] == "bode_plot"
        for item_id in menu._categories["Signal & Frequency"]
    )
    assert menu._tiles == []  # thumbnails are lazy; app startup stays cheap

    menu._show_category(1)

    assert len(menu._tiles) >= 6
    line_tile = next(tile for tile in menu._tiles if tile.text() == "Line")
    line_tile.click()
    assert picked == [("basic", "line")]
    assert menu._recent_ids == ["basic:line"]
    menu.close()


def test_chart_mega_menu_registry_tile_uses_gallery_callback(qapp):
    picked = []
    menu = OriginChartMenu(
        on_basic=lambda spec: None,
        on_registry=lambda entry: picked.append(entry["key"]),
    )
    statistical_row = list(menu._categories).index("Statistical")

    menu._show_category(statistical_row)
    assert menu._tiles
    menu._tiles[0].click()

    assert picked
    assert menu._recent_ids[0].startswith("registry:")
    menu.close()


def test_empty_active_book_still_uses_numeric_example_thumbnails(qapp, monkeypatch):
    rendered_frames = []
    monkeypatch.setattr(
        chart_menu_module,
        "_render_thumbnail",
        lambda item, dataframe: rendered_frames.append(dataframe.copy()) or QIcon(),
    )
    menu = OriginChartMenu(
        on_basic=lambda spec: None,
        on_registry=lambda entry: None,
    )
    statistical_row = list(menu._categories).index("Statistical")

    menu._show_category(statistical_row)

    assert rendered_frames
    assert all(
        len(frame.select_dtypes(include="number").columns) >= 4
        for frame in rendered_frames
    )
    assert all(not frame.empty for frame in rendered_frames)
    menu.close()
