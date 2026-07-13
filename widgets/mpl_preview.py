from __future__ import annotations

import logging

import matplotlib
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


logger = logging.getLogger(__name__)


class MatplotlibPreview(QWidget):
    """Isolated live preview that never mutates application-wide rcParams."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._create_sample_data()
        self.setup_ui()
        self.render_style({})

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        title = QLabel("Live plot preview", self)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(title)

        self.preview_frame = QFrame(self)
        self.preview_frame.setFrameStyle(QFrame.Box)
        self.preview_frame.setMinimumSize(300, 220)
        layout.addWidget(self.preview_frame)

        self.figure = Figure(figsize=(5, 3), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        frame_layout = QVBoxLayout(self.preview_frame)
        frame_layout.setContentsMargins(4, 4, 4, 4)
        frame_layout.addWidget(self.canvas)

    def _create_sample_data(self) -> None:
        rng = np.random.default_rng(42)
        x = np.linspace(0, 10, 50)
        self.sample_data = {
            "x": x,
            "y1": np.sin(x) + rng.normal(0, 0.1, 50),
            "y2": np.cos(x) + rng.normal(0, 0.1, 50),
            "y3": 0.5 * np.sin(2 * x) + rng.normal(0, 0.1, 50),
        }

    def _rebuild_plot(self, style_file: str | None = None) -> None:
        from matplotlib import style as mpl_style

        with matplotlib.rc_context():
            mpl_style.use(style_file or "default")
            self.figure.clear()
            self.figure.set_facecolor(matplotlib.rcParams["figure.facecolor"])
            self.ax = self.figure.add_subplot(111)
            self.ax.plot(
                self.sample_data["x"],
                self.sample_data["y1"],
                label="Signal A",
                marker="o",
                markevery=8,
            )
            self.ax.plot(
                self.sample_data["x"],
                self.sample_data["y2"],
                label="Signal B",
                marker="s",
                markevery=8,
            )
            self.ax.plot(
                self.sample_data["x"],
                self.sample_data["y3"],
                label="Signal C",
                marker="^",
                markevery=8,
            )
            self.ax.set_xlabel("Time (s)")
            self.ax.set_ylabel("Amplitude")
            self.ax.set_title("Scientific plot")
            self.ax.legend()
            self.ax.grid(bool(matplotlib.rcParams["axes.grid"]))
            self.figure.tight_layout()

    def render_style(self, style_dict: dict, style_file: str | None = None) -> bool:
        """Rebuild from an isolated base style, then apply dialog overrides."""
        try:
            self._rebuild_plot(style_file)
            self.update_style(style_dict)
            return True
        except Exception as exc:
            logger.debug("Matplotlib preview render failed", exc_info=True)
            return False

    def update_style(self, style_dict: dict) -> None:
        try:
            figure_color = style_dict.get("figure_facecolor")
            axes_color = style_dict.get("axes_facecolor")
            spine_color = style_dict.get("axes_color")
            text_color = style_dict.get("text_color")
            grid_color = style_dict.get("grid_color")

            if figure_color:
                self.figure.set_facecolor(figure_color)
            if axes_color:
                self.ax.set_facecolor(axes_color)
            if spine_color:
                for spine in self.ax.spines.values():
                    spine.set_color(spine_color)
            if text_color:
                self.ax.title.set_color(text_color)
                self.ax.xaxis.label.set_color(text_color)
                self.ax.yaxis.label.set_color(text_color)
                self.ax.tick_params(axis="both", colors=text_color)
                legend = self.ax.get_legend()
                if legend is not None:
                    for text in legend.get_texts():
                        text.set_color(text_color)

            grid = style_dict.get("grid", {})
            if grid.get("enabled", True):
                grid_kwargs = {
                    "alpha": grid.get("alpha", 0.3),
                    "linestyle": grid.get("linestyle", "-"),
                    "linewidth": grid.get("linewidth", 0.6),
                }
                if grid_color:
                    grid_kwargs["color"] = grid_color
                self.ax.grid(True, **grid_kwargs)
            else:
                self.ax.grid(False)

            colors = style_dict.get("color_cycle") or []
            line_width = style_dict.get("line_width", 2.0)
            marker_size = style_dict.get("marker_size", 5.5)
            for index, line in enumerate(self.ax.lines):
                line.set_linewidth(line_width)
                line.set_markersize(marker_size)
                if colors:
                    line.set_color(colors[index % len(colors)])

            font = style_dict.get("font", {})
            family = font.get("family")
            if family:
                for text in self.figure.findobj(match=matplotlib.text.Text):
                    text.set_fontfamily(family)
            self.ax.title.set_fontsize(font.get("title_size", 12))
            self.ax.xaxis.label.set_fontsize(font.get("label_size", 11))
            self.ax.yaxis.label.set_fontsize(font.get("label_size", 11))
            self.ax.tick_params(labelsize=font.get("tick_size", 10))
            legend = self.ax.get_legend()
            if legend is not None:
                for text in legend.get_texts():
                    text.set_fontsize(font.get("legend_size", 10))
                if axes_color:
                    legend.get_frame().set_facecolor(axes_color)
                if spine_color:
                    legend.get_frame().set_edgecolor(spine_color)

            self.figure.tight_layout()
            self.canvas.draw()
        except Exception:
            logger.debug("Matplotlib preview update failed", exc_info=True)

    def apply_mplstyle(self, style_file: str) -> bool:
        return self.render_style({}, style_file=style_file)

    def reset_style(self) -> None:
        self.render_style({})
