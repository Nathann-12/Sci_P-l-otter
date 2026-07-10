from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import logging
import textwrap
from typing import Any, Callable
import warnings

import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QWidgetAction,
)

from charts_gallery import ChartSpec, _mk_specs
from plots.registry import all_plots

logger = logging.getLogger(__name__)


def example_thumbnail_dataframe() -> pd.DataFrame:
    """Stable sample data for catalog thumbnails; never used for real plots."""
    rng = np.random.default_rng(20260706)
    x = np.linspace(0.0, 12.0, 120)
    group = np.resize(np.array(["A", "B", "C", "D"]), x.size)
    signal = np.sin(x) + rng.normal(0.0, 0.12, x.size)
    response = 0.65 * signal + np.cos(x * 0.45) + rng.normal(0.0, 0.1, x.size)
    return pd.DataFrame(
        {
            "time": x,
            "signal": signal,
            "response": response,
            "magnitude": np.abs(rng.normal(1.2, 0.4, x.size)),
            "group": group,
        }
    )


@dataclass(frozen=True, slots=True)
class MenuPlotItem:
    item_id: str
    title: str
    description: str
    draw: Callable[[Any, pd.DataFrame], None]
    basic_spec: ChartSpec | None = None
    registry_entry: dict[str, Any] | None = None
    is_3d: bool = False
    projection: str | None = None


def _basic_item(spec: ChartSpec) -> MenuPlotItem:
    return MenuPlotItem(
        item_id=f"basic:{spec.key}",
        title=spec.title,
        description=f"Create a new {spec.title} graph",
        draw=spec.preview_func,
        basic_spec=spec,
        is_3d=spec.is3d,
        projection="3d" if spec.is3d else None,
    )


def _registry_item(entry: dict[str, Any]) -> MenuPlotItem:
    return MenuPlotItem(
        item_id=f"registry:{entry['key']}",
        title=entry.get("title", entry["key"]),
        description=entry.get("desc", ""),
        draw=entry["func"],
        registry_entry=entry,
        is_3d=bool(entry.get("is3d")),
        projection=entry.get("projection") or ("3d" if entry.get("is3d") else None),
    )


def _render_thumbnail(item: MenuPlotItem, dataframe: pd.DataFrame) -> QIcon:
    figure = Figure(figsize=(1.45, 0.9), dpi=80, facecolor="#20242a")
    canvas = FigureCanvasAgg(figure)
    axes = figure.add_subplot(111, projection=item.projection)
    axes.set_facecolor("#20242a")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        try:
            item.draw(axes, dataframe)
        except Exception:
            logger.debug("chart menu thumbnail failed for %s", item.item_id, exc_info=True)
            axes.clear()
            axes.text(0.5, 0.5, "-", ha="center", va="center", color="#9aa4b2")

    for axis in figure.axes:
        axis.set_facecolor("#20242a")
        axis.set_title("")
        axis.set_xlabel("")
        axis.set_ylabel("")
        legend = axis.get_legend()
        if legend is not None:
            legend.remove()
        axis.tick_params(labelsize=0, length=0, colors="#6b7685")
        for spine in axis.spines.values():
            spine.set_color("#697382")
        palette = ("#4f9cf9", "#56c4a0", "#f2a541", "#e76f8a")
        for index, line in enumerate(axis.lines):
            line.set_color(palette[index % len(palette)])
        for index, collection in enumerate(axis.collections):
            try:
                collection.set_facecolor(palette[index % len(palette)])
                collection.set_edgecolor(palette[index % len(palette)])
            except Exception:
                pass
        for index, patch in enumerate(axis.patches):
            try:
                patch.set_facecolor(palette[index % len(palette)])
                patch.set_edgecolor("#aeb9c7")
            except Exception:
                pass
    figure.subplots_adjust(left=0.04, right=0.96, top=0.96, bottom=0.06)

    canvas.draw()
    rgba = np.asarray(canvas.buffer_rgba()).copy()
    height, width, _ = rgba.shape
    image = QImage(
        rgba.data,
        width,
        height,
        rgba.strides[0],
        QImage.Format_RGBA8888,
    ).copy()
    return QIcon(QPixmap.fromImage(image))


def _tile_caption(title: str) -> str:
    lines = textwrap.wrap(
        title,
        width=16,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if len(lines) <= 2:
        return "\n".join(lines)
    return f"{lines[0]}\n{lines[1]}..."


class OriginChartMenu(QMenu):
    """Origin-style chart picker embedded in the top menu bar."""

    def __init__(
        self,
        on_basic: Callable[[ChartSpec], None],
        on_registry: Callable[[dict[str, Any]], None],
        parent=None,
    ):
        super().__init__("Charts", parent)
        self._on_basic = on_basic
        self._on_registry = on_registry
        self._recent_ids: list[str] = []
        self._tiles: list[QToolButton] = []

        self._items_by_id, self._categories = self._build_catalog()
        self._host = QWidget(self)
        self._host.setObjectName("ChartMegaMenu")
        self._host.setFixedSize(930, 640)
        self._host.setFont(QFont("Segoe UI", 10))
        self._build_ui()

        action = QWidgetAction(self)
        action.setDefaultWidget(self._host)
        self.addAction(action)
        self.aboutToShow.connect(self._refresh_current_category)

    def _build_catalog(
        self,
    ) -> tuple[dict[str, MenuPlotItem], "OrderedDict[str, list[str]]"]:
        basic = {spec.key: _basic_item(spec) for spec in _mk_specs()}
        registered = {
            entry["key"]: _registry_item(entry)
            for entry in all_plots()
        }
        items = {
            item.item_id: item
            for item in (*basic.values(), *registered.values())
        }

        def ids(*selected: MenuPlotItem | None) -> list[str]:
            return [item.item_id for item in selected if item is not None]

        categories: "OrderedDict[str, list[str]]" = OrderedDict()
        categories["Recently Used"] = []
        categories["Basic 2D"] = ids(
            basic.get("line"),
            basic.get("scatter"),
            basic.get("area"),
            registered.get("dot_plot"),
            registered.get("run_chart"),
            registered.get("paired_comparison"),
            registered.get("bland_altman"),
            registered.get("residual_plot"),
        )
        categories["Bar, Pie, Area"] = ids(
            basic.get("bar"),
            basic.get("pie"),
            basic.get("area"),
            registered.get("bar_mean_sd"),
            registered.get("interval_plot"),
            registered.get("main_effects"),
            registered.get("interaction_plot"),
            registered.get("population_pyramid"),
        )
        categories["Statistical"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") in {"Distribution", "Probability"}
        ]
        categories["Relational"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") == "Relational"
        ]
        categories["Contour, Heatmap"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") == "Contour, Heatmap"
        ]
        categories["Multi-Column"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") == "Multi-Column"
        ]
        categories["Multi-Panel"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") == "Multi-Panel"
        ]
        categories["Polar"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") == "Polar"
        ]
        categories["Frequency Response"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") == "Frequency Response"
        ]
        categories["Quality Control"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") == "Quality"
        ]
        categories["Categorical"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") == "Categorical"
        ]
        categories["3D"] = ids(basic.get("3d_scatter"))
        categories["Multi-Panel, Multi-Axis"] = categories.pop("Multi-Panel")
        categories["Specialized"] = categories.pop("Polar")
        categories["Signal & Frequency"] = categories.pop("Frequency Response")
        preferred_order = (
            "Recently Used",
            "Basic 2D",
            "Bar, Pie, Area",
            "Multi-Panel, Multi-Axis",
            "Multi-Column",
            "Statistical",
            "Contour, Heatmap",
            "Specialized",
            "Signal & Frequency",
            "Relational",
            "Quality Control",
            "Categorical",
            "3D",
        )
        ordered = OrderedDict(
            (category, categories[category])
            for category in preferred_order
            if category in categories
        )
        return items, ordered

    def _build_ui(self) -> None:
        root = QHBoxLayout(self._host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.category_list = QListWidget(self._host)
        self.category_list.setObjectName("ChartCategoryList")
        self.category_list.setFixedWidth(225)
        for category in self._categories:
            QListWidgetItem(category, self.category_list)
        self.category_list.currentRowChanged.connect(self._show_category)
        root.addWidget(self.category_list)

        right = QWidget(self._host)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 10, 12, 10)
        right_layout.setSpacing(6)

        self.category_title = QLabel(right)
        self.category_title.setObjectName("ChartCategoryTitle")
        right_layout.addWidget(self.category_title)

        self.scroll = QScrollArea(right)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 4, 0, 4)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        right_layout.addWidget(self.scroll, 1)

        self.empty_label = QLabel("Choose a chart to add it to a new Graph window.")
        self.empty_label.setObjectName("ChartMenuHint")
        right_layout.addWidget(self.empty_label)
        root.addWidget(right, 1)

        self._host.setStyleSheet(
            """
            #ChartMegaMenu {
                background: #1e2126;
                border: 1px solid #3a3f44;
            }
            #ChartCategoryList {
                background: #20242a;
                border: 0;
                border-right: 1px solid #3a3f44;
                color: #dce3eb;
                font-size: 14px;
                font-weight: 600;
                outline: 0;
                padding: 4px 0;
            }
            #ChartCategoryList::item {
                min-height: 42px;
                padding: 0 12px;
                border-left: 3px solid transparent;
            }
            #ChartCategoryList::item:hover {
                background: #2a3038;
            }
            #ChartCategoryList::item:selected {
                background: #14598b;
                border-left-color: #4f9cf9;
                color: white;
            }
            #ChartCategoryTitle {
                color: #f3f6fa;
                font-size: 15px;
                font-weight: 700;
                padding: 2px 4px 6px 4px;
            }
            #ChartMenuHint {
                color: #8f9aa8;
                padding: 4px;
            }
            QScrollArea, QScrollArea > QWidget > QWidget {
                background: #1e2126;
            }
            QToolButton {
                color: #dce3eb;
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 4px;
                font-size: 12px;
            }
            QToolButton:hover {
                background: #29313a;
                border-color: #4f9cf9;
            }
            QToolButton:pressed {
                background: #174f7d;
            }
            """
        )

        initial_row = 1 if self.category_list.count() > 1 else 0
        self.category_list.blockSignals(True)
        self.category_list.setCurrentRow(initial_row)
        self.category_list.blockSignals(False)
        initial_category = list(self._categories)[initial_row]
        self.category_title.setText(initial_category)
        self.empty_label.setText("Open the menu to preview charts from the active Book.")

    def _clear_grid(self) -> None:
        self._tiles.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _show_category(self, row: int) -> None:
        self._clear_grid()
        categories = list(self._categories)
        if not 0 <= row < len(categories):
            return
        category = categories[row]
        self.category_title.setText(category)
        item_ids = self._recent_ids if category == "Recently Used" else self._categories[category]
        dataframe = example_thumbnail_dataframe()
        for index, item_id in enumerate(item_ids):
            item = self._items_by_id.get(item_id)
            if item is None:
                continue
            tile = QToolButton(self.grid_host)
            tile.setText(_tile_caption(item.title))
            tile.setToolTip(item.description)
            tile.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            tile.setIconSize(QSize(88, 58))
            tile.setFixedSize(104, 104)
            tile.setIcon(_render_thumbnail(item, dataframe))
            tile.clicked.connect(lambda _=False, selected=item: self._activate(selected))
            self.grid.addWidget(tile, index // 6, index % 6)
            self._tiles.append(tile)
        self.empty_label.setText(
            "No recent charts yet. Pick a chart from another category."
            if category == "Recently Used" and not item_ids
            else "Preview examples only. Click a chart, choose data columns, then plot the active Book."
        )

    def _activate(self, item: MenuPlotItem) -> None:
        if item.item_id in self._recent_ids:
            self._recent_ids.remove(item.item_id)
        self._recent_ids.insert(0, item.item_id)
        del self._recent_ids[8:]
        try:
            if item.basic_spec is not None:
                self._on_basic(item.basic_spec)
            elif item.registry_entry is not None:
                self._on_registry(item.registry_entry)
        finally:
            self.hide()

    def _refresh_current_category(self) -> None:
        self._show_category(self.category_list.currentRow())
