from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import logging
import textwrap
from typing import Any, Callable
import warnings

import numpy as np
import pandas as pd
import matplotlib as mpl
from cycler import cycler
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


THUMBNAIL_PALETTE = ("#59a5ff", "#61d0ad", "#ffb44c", "#f27a92")


def example_thumbnail_dataframe() -> pd.DataFrame:
    """Generic deterministic sample retained as a safe thumbnail fallback."""
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


def _line_example() -> pd.DataFrame:
    x = np.linspace(0.0, 10.0, 72)
    return pd.DataFrame(
        {
            "Time": x,
            "Sensor A": 2.3 + 0.72 * np.sin(x * 0.85),
            "Sensor B": 1.55 + 0.48 * np.cos(x * 0.85 + 0.35),
        }
    )


def _scatter_example() -> pd.DataFrame:
    rng = np.random.default_rng(22)
    dose = np.linspace(0.2, 10.0, 58)
    response = 1.1 + 0.72 * dose + rng.normal(0.0, 0.55, dose.size)
    return pd.DataFrame({"Dose": dose, "Response": response})


def _errorbar_example() -> pd.DataFrame:
    dose = np.linspace(0.5, 8.0, 10)
    response = 2.0 + 0.8 * dose + 0.22 * np.sin(dose * 1.4)
    uncertainty = 0.25 + 0.12 * np.cos(dose * 0.7) ** 2
    return pd.DataFrame(
        {"Dose": dose, "Mean response": response, "Uncertainty": uncertainty}
    )


def _step_example() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Time": np.arange(14, dtype=float),
            "State": [1, 1, 1, 2, 2, 4, 4, 3, 3, 3, 5, 5, 2, 2],
        }
    )


def _stem_example() -> pd.DataFrame:
    frequency = np.arange(18, dtype=float)
    amplitude = np.array(
        [
            0.2, 0.7, 2.8, 0.5, 0.25, 1.8, 0.35, 0.18, 1.15,
            0.22, 0.7, 0.15, 0.42, 0.1, 0.3, 0.08, 0.18, 0.05,
        ]
    )
    return pd.DataFrame({"Frequency bin": frequency, "Amplitude": amplitude})


def _bubble_example() -> pd.DataFrame:
    rng = np.random.default_rng(26)
    x = rng.uniform(1.0, 10.0, 34)
    y = 1.5 + 0.65 * x + rng.normal(0.0, 1.1, x.size)
    return pd.DataFrame(
        {
            "Cost": x,
            "Performance": y,
            "Sample size": rng.uniform(10.0, 120.0, x.size),
            "Efficiency": y / x,
        }
    )


def _hexbin_example() -> pd.DataFrame:
    rng = np.random.default_rng(29)
    x = rng.normal(0.0, 1.0, 650)
    y = 0.72 * x + rng.normal(0.0, 0.65, x.size)
    return pd.DataFrame({"Measurement A": x, "Measurement B": y})


def _area_example() -> pd.DataFrame:
    x = np.arange(1, 13, dtype=float)
    return pd.DataFrame(
        {
            "Month": x,
            "Product A": 18 + 4.0 * np.sin(x / 2.1),
            "Product B": 11 + 2.5 * np.cos(x / 2.6),
            "Product C": 6 + 1.5 * np.sin(x / 1.4 + 0.8),
        }
    )


def _bar_example() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Group": np.arange(5, dtype=float),
            "Control": [24, 31, 29, 36, 33],
            "Treatment": [31, 39, 42, 45, 48],
        }
    )


def _category_example() -> pd.DataFrame:
    rng = np.random.default_rng(31)
    return pd.DataFrame(
        {
            "Control": rng.normal(42, 3.8, 48),
            "Low dose": rng.normal(51, 4.6, 48),
            "High dose": rng.normal(63, 5.1, 48),
        }
    )


def _distribution_example() -> pd.DataFrame:
    rng = np.random.default_rng(47)
    return pd.DataFrame(
        {
            "Control": rng.normal(0.0, 0.75, 90),
            "Treatment A": rng.normal(1.05, 0.52, 90),
            "Treatment B": rng.normal(2.0, 0.9, 90),
        }
    )


def _relational_example() -> pd.DataFrame:
    rng = np.random.default_rng(59)
    x = np.linspace(1.0, 10.0, 70)
    y = 0.85 * x + rng.normal(0.0, 0.72, x.size)
    z = -0.55 * x + rng.normal(0.0, 0.9, x.size)
    return pd.DataFrame({"Temperature": x, "Yield": y, "Defects": z})


def _agreement_example() -> pd.DataFrame:
    rng = np.random.default_rng(71)
    reference = np.linspace(72.0, 128.0, 46) + rng.normal(0.0, 2.2, 46)
    device = reference + 1.8 + rng.normal(0.0, 3.0, reference.size)
    return pd.DataFrame({"Reference": reference, "New device": device})


def _paired_example() -> pd.DataFrame:
    rng = np.random.default_rng(83)
    before = rng.normal(68.0, 7.0, 18)
    after = before - rng.normal(8.0, 2.7, before.size)
    return pd.DataFrame({"Before": before, "After": after})


def _residual_example() -> pd.DataFrame:
    rng = np.random.default_rng(97)
    x = np.linspace(0.0, 12.0, 62)
    y = 3.0 + 1.45 * x + rng.normal(0.0, 1.25, x.size)
    return pd.DataFrame({"Dose": x, "Response": y})


def _quality_example() -> pd.DataFrame:
    rng = np.random.default_rng(109)
    measurement = 50.0 + rng.normal(0.0, 0.85, 36)
    measurement[26] = 54.3
    return pd.DataFrame({"Measurement": measurement})


def _pareto_example() -> pd.DataFrame:
    return pd.DataFrame({"Defect count": [42, 29, 18, 12, 7, 4]})


def _interaction_example() -> pd.DataFrame:
    level = np.tile(np.array([0.0, 1.0]), 18)
    run = np.arange(level.size, dtype=float)
    return pd.DataFrame(
        {
            "Temperature level": level,
            "Catalyst A": 42 + 12 * level + 1.2 * np.sin(run),
            "Catalyst B": 55 - 8 * level + 1.0 * np.cos(run),
        }
    )


def _population_example() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Female": [24, 29, 35, 43, 51, 47, 37, 25, 14],
            "Male": [26, 31, 38, 46, 49, 43, 32, 20, 10],
        }
    )


def _surface_example() -> pd.DataFrame:
    grid = np.linspace(-2.6, 2.6, 16)
    x, y = np.meshgrid(grid, grid)
    z = (
        1.25 * np.exp(-((x - 0.8) ** 2 + (y - 0.35) ** 2))
        - 0.75 * np.exp(-((x + 1.0) ** 2 + (y + 0.9) ** 2) / 0.7)
    )
    return pd.DataFrame({"X": x.ravel(), "Y": y.ravel(), "Intensity": z.ravel()})


def _matrix_example() -> pd.DataFrame:
    x = np.linspace(0.0, 2.0 * np.pi, 42)
    return pd.DataFrame(
        {
            "Sample A": np.sin(x),
            "Sample B": np.sin(x + 0.65),
            "Sample C": np.sin(x + 1.3),
            "Sample D": np.sin(x + 1.95),
        }
    )


def _multi_column_example() -> pd.DataFrame:
    x = np.linspace(0.0, 9.0, 72)
    return pd.DataFrame(
        {
            "Time": x,
            "Channel 1": np.sin(x),
            "Channel 2": 0.75 * np.sin(x + 0.7),
            "Channel 3": 0.52 * np.sin(x + 1.5),
        }
    )


def _polar_example() -> pd.DataFrame:
    theta = np.linspace(0.0, 2.0 * np.pi, 72)
    radius = 1.15 + 0.48 * np.cos(3.0 * theta)
    return pd.DataFrame({"Direction": theta, "Magnitude": radius})


def _nyquist_example() -> pd.DataFrame:
    theta = np.linspace(0.05, np.pi - 0.05, 54)
    return pd.DataFrame(
        {
            "Z real": 4.0 + 8.5 * (1.0 + np.cos(theta)),
            "Z imaginary": 8.5 * np.sin(theta),
        }
    )


def _bode_example() -> pd.DataFrame:
    frequency = np.logspace(0, 4, 72)
    corner = 180.0
    magnitude = -10.0 * np.log10(1.0 + (frequency / corner) ** 2)
    phase = -np.degrees(np.arctan(frequency / corner))
    return pd.DataFrame(
        {"Frequency (Hz)": frequency, "Magnitude (dB)": magnitude, "Phase (deg)": phase}
    )


def _phase_example() -> pd.DataFrame:
    t = np.linspace(0.0, 2.0 * np.pi, 96)
    return pd.DataFrame({"Position": np.sin(t), "Velocity": np.cos(t)})


def _three_dimensional_example() -> pd.DataFrame:
    t = np.linspace(0.0, 5.0 * np.pi, 90)
    return pd.DataFrame(
        {"X": np.cos(t), "Y": np.sin(t), "Z": np.linspace(-1.0, 1.0, t.size)}
    )


def _bar_3d_example() -> pd.DataFrame:
    x, y = np.meshgrid(np.arange(5, dtype=float), np.arange(4, dtype=float))
    z = 1.0 + 4.0 * np.exp(-((x - 2.2) ** 2 + (y - 1.5) ** 2) / 2.8)
    return pd.DataFrame({"X category": x.ravel(), "Y category": y.ravel(), "Value": z.ravel()})


def example_dataframe_for(item: "MenuPlotItem") -> pd.DataFrame:
    """Return an explanatory deterministic dataset tailored to one chart type."""
    key = item.item_id.partition(":")[2]
    category = (
        item.registry_entry.get("category", "")
        if item.registry_entry is not None
        else ""
    )

    exact_examples: dict[str, Callable[[], pd.DataFrame]] = {
        "line": _line_example,
        "scatter": _scatter_example,
        "bar": _bar_example,
        "area": _area_example,
        "hist": _distribution_example,
        "box": _distribution_example,
        "pie": lambda: pd.DataFrame({"Market share": [42.0, 28.0, 18.0, 12.0]}),
        "3d_scatter": _three_dimensional_example,
        "bland_altman": _agreement_example,
        "paired_comparison": _paired_example,
        "residual_plot": _residual_example,
        "step_plot": _step_example,
        "stem_plot": _stem_example,
        "error_bar_plot": _errorbar_example,
        "bubble_plot": _bubble_example,
        "hexbin_plot": _hexbin_example,
        "run_chart": _quality_example,
        "control_xbar": _quality_example,
        "control_imr": _quality_example,
        "pareto": _pareto_example,
        "interaction_plot": _interaction_example,
        "population_pyramid": _population_example,
        "filled_contour": _surface_example,
        "contour_lines": _surface_example,
        "matrix_heatmap": _matrix_example,
        "polar_line": _polar_example,
        "polar_scatter": _polar_example,
        "wind_rose": _polar_example,
        "phase_plot": _phase_example,
        "nyquist_plot": _nyquist_example,
        "bode_plot": _bode_example,
        "waterfall_3d": _multi_column_example,
        "stacked_lines_y_offset": _multi_column_example,
        "subplot_grid": _multi_column_example,
        "scatter_3d": _three_dimensional_example,
        "trajectory_3d": _three_dimensional_example,
        "stem_3d": _three_dimensional_example,
        "bar_3d": _bar_3d_example,
        "surface_3d": _surface_example,
        "wireframe_3d": _surface_example,
        "contour_3d": _surface_example,
        "trisurface_3d": _surface_example,
    }
    if key in exact_examples:
        return exact_examples[key]()
    if category in {"Distribution", "Probability"}:
        return _distribution_example()
    if category == "Relational":
        return _relational_example()
    if category == "Quality":
        return _quality_example()
    if category == "Categorical":
        return _category_example()
    if category == "Contour, Heatmap":
        return _surface_example()
    if category in {"Multi-Column", "Multi-Panel"}:
        return _multi_column_example()
    return example_thumbnail_dataframe()


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
    descriptions = {
        "line": "Show trends and continuous change along an X axis",
        "scatter": "Reveal the relationship between two measurements",
        "bar": "Compare values across discrete groups",
        "area": "Show how several components contribute to a total",
        "hist": "See the shape and spread of a numeric distribution",
        "box": "Compare medians, spread, and outliers across groups",
        "pie": "Show parts of a whole for a small number of categories",
        "3d_scatter": "Explore the relationship among three measurements",
    }
    return MenuPlotItem(
        item_id=f"basic:{spec.key}",
        title=spec.title,
        description=descriptions.get(spec.key, f"Create a new {spec.title} graph"),
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
    figure = Figure(figsize=(1.7, 1.05), dpi=90, facecolor="#171c23")
    canvas = FigureCanvasAgg(figure)
    axes = figure.add_subplot(111, projection=item.projection)
    axes.set_facecolor("#171c23")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        try:
            with mpl.rc_context(
                {
                    "axes.prop_cycle": cycler(color=THUMBNAIL_PALETTE),
                    "axes.facecolor": "#171c23",
                    "figure.facecolor": "#171c23",
                    "axes.edgecolor": "#536171",
                    "axes.labelcolor": "#aeb9c7",
                    "text.color": "#dce5ef",
                    "xtick.color": "#718093",
                    "ytick.color": "#718093",
                    "grid.color": "#536171",
                }
            ):
                item.draw(axes, dataframe)
        except Exception:
            logger.debug("chart menu thumbnail failed for %s", item.item_id, exc_info=True)
            axes.clear()
            axes.text(0.5, 0.5, "-", ha="center", va="center", color="#9aa4b2")

    for axis in figure.axes:
        axis.set_facecolor("#171c23")
        axis.set_title("")
        axis.set_xlabel("")
        axis.set_ylabel("")
        legend = axis.get_legend()
        if legend is not None:
            legend.remove()
        axis.tick_params(labelsize=0, length=0, colors="#6b7685")
        for spine in axis.spines.values():
            spine.set_color("#536171")
        for annotation in axis.texts:
            annotation.set_fontsize(4)
    if figure._suptitle is not None:
        figure._suptitle.remove()
    try:
        figure.subplots_adjust(left=0.035, right=0.965, top=0.965, bottom=0.04)
    except Exception:
        pass

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
        self._thumbnail_cache: dict[str, QIcon] = {}

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
            registered.get("step_plot"),
            registered.get("stem_plot"),
            registered.get("error_bar_plot"),
            registered.get("bubble_plot"),
            registered.get("hexbin_plot"),
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
        categories["3D"] = [
            item.item_id
            for item in registered.values()
            if item.registry_entry
            and item.registry_entry.get("category") == "3D"
        ] + ids(registered.get("waterfall_3d"))
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
        self.empty_label.setText("Hover for a description. Click a chart to use it with the active Book.")

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
        for index, item_id in enumerate(item_ids):
            item = self._items_by_id.get(item_id)
            if item is None:
                continue
            tile = QToolButton(self.grid_host)
            tile.setProperty("preserveIconColors", True)
            tile.setText(_tile_caption(item.title))
            tile.setToolTip(f"<b>{item.title}</b><br>{item.description}")
            tile.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            tile.setIconSize(QSize(116, 72))
            tile.setFixedSize(128, 112)
            icon = self._thumbnail_cache.get(item.item_id)
            if icon is None:
                icon = _render_thumbnail(item, example_dataframe_for(item))
                self._thumbnail_cache[item.item_id] = icon
            tile.setIcon(icon)
            tile.clicked.connect(lambda _=False, selected=item: self._activate(selected))
            self.grid.addWidget(tile, index // 5, index % 5)
            self._tiles.append(tile)
        self.empty_label.setText(
            "No recent charts yet. Pick a chart from another category."
            if category == "Recently Used" and not item_ids
            else "Hover for a description. Click a chart, choose columns, then plot the active Book."
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
