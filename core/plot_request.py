from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PlotOptions:
    """Reusable plot styling independent from hidden Qt controls."""

    line_width: float = 2.0
    show_marker: bool = False
    marker: str = "o"
    scatter_size: float | None = None
    histogram_bins: int = 20
    fit_normal: bool = False
    bar_width: float = 0.8
    bar_reducer: str = "sum"
    scatter_mode: str = "auto"

    def __post_init__(self) -> None:
        if self.line_width <= 0:
            raise ValueError("line_width must be positive")
        if self.scatter_size is not None and self.scatter_size <= 0:
            raise ValueError("scatter_size must be positive")
        if self.histogram_bins <= 0:
            raise ValueError("histogram_bins must be positive")
        if not 0 < self.bar_width <= 1:
            raise ValueError("bar_width must be in the range (0, 1]")
        if self.bar_reducer not in {"none", "sum", "mean"}:
            raise ValueError("bar_reducer must be one of: none, sum, mean")
        if self.scatter_mode not in {"auto", "points", "density"}:
            raise ValueError("scatter_mode must be one of: auto, points, density")

    @property
    def resolved_scatter_size(self) -> float:
        return self.scatter_size if self.scatter_size is not None else self.line_width * 5


@dataclass(frozen=True, slots=True)
class PlotRequest:
    """Widget-independent data needed to draw one X/Y series."""

    x: Any
    y: Any
    x_column: str
    y_column: str
    x_is_datetime: bool = False

    @property
    def label(self) -> str:
        return f"{self.y_column} vs {self.x_column}"


@dataclass(frozen=True, slots=True)
class HistogramRequest:
    values: Any
    column: str
    options: PlotOptions = field(default_factory=PlotOptions)

    @property
    def title(self) -> str:
        return f"Histogram of {self.column} (bins={self.options.histogram_bins})"


@dataclass(frozen=True, slots=True)
class BarRequest:
    x: Any
    y: Any
    x_column: str = ""
    y_column: str = ""
    title: str = ""
    options: PlotOptions = field(default_factory=PlotOptions)

    @property
    def label(self) -> str:
        return self.title or self.y_column or "Bar Series"
