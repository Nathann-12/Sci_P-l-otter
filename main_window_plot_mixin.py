from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QMessageBox

from processors import beautify_axes


logger = logging.getLogger(__name__)


class MainWindowPlotMixin:
    """Reusable plotting actions extracted from MainWindow."""

    def _get_dataset_name_for_path(self, path: Optional[str]) -> str:
        if not path:
            return ""
        datasets = getattr(self, "_datasets", {}) if hasattr(self, "_datasets") else {}
        if isinstance(datasets, dict):
            for name, info in datasets.items():
                if isinstance(info, dict) and info.get("path") == path:
                    return name or ""
        return ""

    def _build_layer_meta(
        self,
        style: str,
        label: str,
        extra_kwargs: Optional[Dict[str, Any]] = None,
        source: str = "manual",
    ) -> Dict[str, Any]:
        meta = {
            "style": style,
            "label": label,
            "dataset_path": getattr(self, "_current_path", "") or "",
            "dataset_name": self._get_dataset_name_for_path(getattr(self, "_current_path", "")),
            "x_column": self.cbX.currentText() if hasattr(self, "cbX") else "",
            "y_column": self.cbY.currentText() if hasattr(self, "cbY") else "",
            "source": source,
        }
        if extra_kwargs:
            cleaned = {k: v for k, v in extra_kwargs.items() if v is not None}
            if cleaned:
                meta["style_kwargs"] = cleaned
        return meta

    def _is_overlay_plot_mode(self) -> bool:
        mode = getattr(self, "plot_mode", "overlay")
        return not str(mode).lower().endswith("replace")

    def _get_current_plot_tab_ids(
        self,
        *,
        warning_title: str = "ไม่มีแท็บ",
        warning_text: str = "ไม่มีแท็บที่เปิดอยู่",
    ) -> list[str]:
        current_tab_id = self.tabs.get_current_tab_id()
        if not current_tab_id:
            QMessageBox.warning(self, warning_title, warning_text)
            return []
        return [current_tab_id]

    def _iter_tabs(self, tab_ids: Iterable[str]):
        for tab_id in tab_ids:
            if tab_id in self.tabs.tabs:
                yield self.tabs.tabs[tab_id]

    def _draw_tab(self, tab, *, attempts: int = 1) -> None:
        for attempt in range(attempts):
            try:
                tab.draw()
                return
            except Exception:
                if attempt + 1 == attempts:
                    try:
                        tab.canvas.fig.canvas.draw_idle()
                    except Exception:
                        logger.debug("Failed to redraw tab", exc_info=True)

    def _update_tabs_after_plot(
        self,
        tab_ids: Iterable[str],
        *,
        xlabel: str = "",
        ylabel: str = "",
        title: str = "",
        x_tick_labels: Optional[Iterable[Any]] = None,
        x_is_datetime: bool = False,
        draw_attempts: int = 1,
    ) -> None:
        tick_labels = list(x_tick_labels) if x_tick_labels is not None else None
        for tab in self._iter_tabs(tab_ids):
            ax = tab.get_axes()
            if xlabel:
                ax.set_xlabel(xlabel)
            if ylabel:
                ax.set_ylabel(ylabel)
            if title:
                ax.set_title(title)
            if tick_labels is not None:
                ax.set_xticks(range(len(tick_labels)))
                try:
                    ax.set_xticklabels(list(map(str, tick_labels)), rotation=45, ha="right")
                except Exception:
                    pass
            try:
                beautify_axes(ax, title=title or None, x_is_datetime=x_is_datetime)
            except Exception:
                logger.debug("Failed to beautify axes", exc_info=True)
            self._draw_tab(tab, attempts=draw_attempts)

    def plot_line(self):
        x, y = self._get_xy()
        if x is None:
            return

        selected_tab_ids = self._get_current_plot_tab_ids()
        if not selected_tab_ids:
            return

        try:
            lw = self.spLineWidth.value()
            marker = "o" if self.chkMarker.isChecked() else None
            label = f"{self.cbY.currentText()} vs {self.cbX.currentText()}"
            plot_kwargs = {"linewidth": lw}
            if marker:
                plot_kwargs["marker"] = marker
            meta = self._build_layer_meta("line", label, plot_kwargs, source="plot_line")

            plotter = self.tabs.add_series_to_tabs if self._is_overlay_plot_mode() else self.tabs.plot_to_tabs
            plotter(selected_tab_ids, x, y, label=label, style="line", meta=meta, **plot_kwargs)

            self._update_tabs_after_plot(
                selected_tab_ids,
                xlabel=self.cbX.currentText(),
                ylabel=self.cbY.currentText(),
                x_is_datetime=self._is_datetime_column(self.cbX.currentText()),
                draw_attempts=3,
            )
            self.statusBar().showMessage("พล็อตกราฟเส้นสำเร็จ")
        except Exception as exc:
            QMessageBox.critical(self, "พล็อตกราฟเส้นไม่สำเร็จ", f"สาเหตุ: {exc}")

    def plot_scatter(self):
        x, y = self._get_xy()
        if x is None:
            return

        selected_tab_ids = self._get_current_plot_tab_ids()
        if not selected_tab_ids:
            return

        try:
            size = self.spLineWidth.value() * 5
            label = f"{self.cbY.currentText()} vs {self.cbX.currentText()}"
            plot_kwargs = {"s": size}
            meta = self._build_layer_meta("scatter", label, plot_kwargs, source="plot_scatter")

            plotter = self.tabs.add_series_to_tabs if self._is_overlay_plot_mode() else self.tabs.plot_to_tabs
            plotter(selected_tab_ids, x, y, label=label, style="scatter", meta=meta, **plot_kwargs)

            self._update_tabs_after_plot(
                selected_tab_ids,
                xlabel=self.cbX.currentText(),
                ylabel=self.cbY.currentText(),
                x_is_datetime=self._is_datetime_column(self.cbX.currentText()),
            )
            self.statusBar().showMessage("พล็อตกราฟจุดสำเร็จ")
        except Exception as exc:
            QMessageBox.critical(self, "พล็อตกราฟจุดไม่สำเร็จ", f"สาเหตุ: {exc}")

    def add_line_overlay(self):
        x, y = self._get_xy()
        if x is None:
            return

        selected_tab_ids = self._get_current_plot_tab_ids(
            warning_title="No Tab",
            warning_text="Please create/select a graph tab first",
        )
        if not selected_tab_ids:
            return

        lw = self.spLineWidth.value()
        marker = "o" if self.chkMarker.isChecked() else None
        label = f"{self.cbY.currentText()} vs {self.cbX.currentText()}"
        plot_kwargs = {"linewidth": lw}
        if marker:
            plot_kwargs["marker"] = marker
        meta = self._build_layer_meta("line", label, plot_kwargs, source="add_line_overlay")

        try:
            self.tabs.add_series_to_tabs(
                selected_tab_ids,
                x,
                y,
                label=label,
                style="line",
                meta=meta,
                **plot_kwargs,
            )
            self._update_tabs_after_plot(
                selected_tab_ids,
                xlabel=self.cbX.currentText(),
                ylabel=self.cbY.currentText(),
                x_is_datetime=self._is_datetime_column(self.cbX.currentText()),
            )
            self.statusBar().showMessage("Added line series (overlay)")
        except Exception:
            logger.debug("Failed to add line overlay", exc_info=True)

    def add_scatter_overlay(self):
        x, y = self._get_xy()
        if x is None:
            return

        selected_tab_ids = self._get_current_plot_tab_ids(
            warning_title="No Tab",
            warning_text="Please create/select a graph tab first",
        )
        if not selected_tab_ids:
            return

        size = self.spLineWidth.value() * 5
        label = f"{self.cbY.currentText()} vs {self.cbX.currentText()}"
        plot_kwargs = {"s": size}
        meta = self._build_layer_meta("scatter", label, plot_kwargs, source="add_scatter_overlay")

        try:
            self.tabs.add_series_to_tabs(
                selected_tab_ids,
                x,
                y,
                label=label,
                style="scatter",
                meta=meta,
                **plot_kwargs,
            )
            self._update_tabs_after_plot(
                selected_tab_ids,
                xlabel=self.cbX.currentText(),
                ylabel=self.cbY.currentText(),
                x_is_datetime=self._is_datetime_column(self.cbX.currentText()),
            )
            self.statusBar().showMessage("Added scatter series (overlay)")
        except Exception:
            logger.debug("Failed to add scatter overlay", exc_info=True)

    def plot_histogram(self):
        if self._df is None or self._df.empty:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน")
            return

        col = self.cbHist.currentText()
        if not col or col not in self._df.columns:
            QMessageBox.information(self, "เลือกคอลัมน์", "โปรดเลือกคอลัมน์ข้อมูลสำหรับฮิสโตแกรม")
            return

        selected_tab_ids = self._get_current_plot_tab_ids()
        if not selected_tab_ids:
            return

        try:
            vals = pd.to_numeric(self._df[col], errors="coerce").dropna().values
            if vals.size == 0:
                QMessageBox.information(self, "ไม่มีข้อมูล", "คอลัมน์ที่เลือกไม่มีค่าตัวเลข")
                return

            bins = int(self.spHistBins.value())
            if bins <= 0:
                bins = 20

            for tab in self._iter_tabs(selected_tab_ids):
                tab.clear()

            for tab in self._iter_tabs(selected_tab_ids):
                ax = tab.get_axes()
                try:
                    _, edges, _ = ax.hist(
                        vals,
                        bins=bins,
                        alpha=0.7,
                        color="#6aa0f8",
                        edgecolor="#2d3a5a",
                    )
                    ax.set_xlabel(col)
                    ax.set_ylabel("Count")
                    ax.set_title(f"Histogram of {col} (bins={bins})")

                    if self.chkHistFit.isChecked():
                        mu = float(np.mean(vals))
                        sigma = float(np.std(vals, ddof=0)) if vals.size > 0 else 0.0
                        if sigma > 0:
                            xs = np.linspace(edges[0], edges[-1], 400)
                            bin_width = (edges[-1] - edges[0]) / bins if bins > 0 else 1.0
                            pdf = (1.0 / (sigma * np.sqrt(2.0 * np.pi))) * np.exp(
                                -0.5 * ((xs - mu) / sigma) ** 2
                            )
                            ax.plot(
                                xs,
                                pdf * vals.size * bin_width,
                                color="#e36a6a",
                                linewidth=2,
                                label=f"Normal fit mu={mu:.2f}, sigma={sigma:.2f}",
                            )
                            ax.legend(loc="best")

                    try:
                        beautify_axes(ax)
                    except Exception:
                        logger.debug("Failed to beautify histogram axes", exc_info=True)
                    self._draw_tab(tab)
                except Exception as hist_error:
                    QMessageBox.critical(self, "สร้างฮิสโตแกรมไม่สำเร็จ", f"สาเหตุ: {hist_error}")
                    return

            self.statusBar().showMessage("พล็อต Histogram สำเร็จ")
        except Exception as exc:
            QMessageBox.critical(self, "พล็อตไม่สำเร็จ", f"สาเหตุ: {exc}")

    def plot_bar(self, x, y, *, xlabel: str = "", ylabel: str = "", title: str = ""):
        selected_tab_ids = self._get_current_plot_tab_ids()
        if not selected_tab_ids:
            return

        label = title or ylabel or "Bar Series"
        meta = self._build_layer_meta("bar", label, {}, source="plot_bar")
        self.tabs.plot_to_tabs(selected_tab_ids, x, y, label=label, style="bar", meta=meta)
        self._update_tabs_after_plot(
            selected_tab_ids,
            xlabel=xlabel,
            ylabel=ylabel,
            title=title,
            x_tick_labels=x,
        )
