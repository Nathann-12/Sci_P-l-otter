from __future__ import annotations

from dataclasses import replace
import logging
from typing import Any, Dict, Iterable, Optional

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QMessageBox

from core.plot_request import BarRequest, HistogramRequest, PlotOptions, PlotRequest
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
        request: PlotRequest | BarRequest | None = None,
    ) -> Dict[str, Any]:
        meta = {
            "style": style,
            "label": label,
            "dataset_path": getattr(self, "_current_path", "") or "",
            "dataset_name": self._get_dataset_name_for_path(getattr(self, "_current_path", "")),
            "x_column": request.x_column if request is not None else (
                self.cbX.currentText() if hasattr(self, "cbX") else ""
            ),
            "y_column": request.y_column if request is not None else (
                self.cbY.currentText() if hasattr(self, "cbY") else ""
            ),
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

    def _resolve_plot_options(self, options: PlotOptions | None = None) -> PlotOptions:
        if isinstance(options, PlotOptions):
            return options
        getter = getattr(self, "current_plot_options", None)
        if callable(getter):
            current = getter()
            if isinstance(current, PlotOptions):
                return current
        current = getattr(self, "_plot_options", None)
        return current if isinstance(current, PlotOptions) else PlotOptions()

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
            # single tight_layout here (once), then one draw — NOT a per-draw
            # layout engine, which recursed ~990× on wide/large tick labels
            try:
                ax.figure.tight_layout()
            except Exception:
                logger.debug("tight_layout skipped", exc_info=True)
            self._draw_tab(tab, attempts=draw_attempts)

    def _build_row_index_plot_request(
        self,
        y_column: str,
        *,
        x_label: str = "Row",
    ) -> PlotRequest | None:
        """Build an Excel-style one-column request: selected values vs row number."""
        if self._df is None or y_column not in self._df.columns:
            return None
        values = pd.to_numeric(self._df[y_column], errors="coerce")
        mask = values.notna().to_numpy()
        if not mask.any():
            QMessageBox.information(
                self,
                "ไม่มีข้อมูล",
                f"คอลัมน์ '{y_column}' ไม่มีข้อมูลตัวเลขสำหรับพล็อต",
            )
            return None
        x = np.arange(1, len(values) + 1, dtype=float)[mask]
        y = values.to_numpy(dtype=float)[mask]
        return PlotRequest(
            x=x,
            y=y,
            x_column=x_label,
            y_column=y_column,
            x_is_datetime=False,
        )

    def _build_row_index_bar_request(
        self,
        y_column: str,
        *,
        options: PlotOptions,
        x_label: str = "Row",
    ) -> BarRequest | None:
        request = self._build_row_index_plot_request(y_column, x_label=x_label)
        if request is None:
            return None
        return BarRequest(
            x=request.x,
            y=request.y,
            x_column=request.x_column,
            y_column=request.y_column,
            title=f"{y_column} by {x_label}",
            options=options,
        )

    def plot_from_workbook(self, style: str = "line", new_graph: bool = True):
        """Origin-style: เลือกคอลัมน์บนชีต → พล็อต

        ``new_graph=True`` (ดีฟอลต์แบบ OriginPro): สร้าง Graph window ใหม่เสมอ;
        ``new_graph=False``: เพิ่มลงกราฟที่ active อยู่ (เส้นทาง overlay เดิม)

        กติกาเลือกคอลัมน์ (ตาม designation แบบ Origin — ดูหัวคอลัมน์ A(X)/B(Y)):
        X = คอลัมน์ที่ตั้ง Set As X ไว้ (ดีฟอลต์ = คอลัมน์เวลา/คอลัมน์แรก);
        Y = คอลัมน์ที่เลือกบนชีต (ยกเว้น X และคอลัมน์ Disregard) — เลือกหลาย
        คอลัมน์ได้หลายเส้น; เลือกคอลัมน์เดียวใด ๆ → plot คอลัมน์นั้นเทียบ Row
        แบบ Excel; ไม่ได้เลือกเลย → คอลัมน์ Y ตัวแรกเทียบ X designation

        styles: ``line`` / ``scatter`` / ``linesymbol`` / ``bar`` / ``histogram``
        """
        wb = getattr(self, "workbook", None)
        if wb is None:
            return
        # Book สะอาด (ข้อมูลจากไฟล์, ไม่ได้แก้เซลล์) → ใช้ source_df ตรง ๆ ไม่ต้อง
        # อ่าน QTableWidget ทั้งตาราง; ชีตที่ถูกพิมพ์/แก้ → adopt จากชีตก่อนเสมอ
        src = getattr(wb, "source_df", None)
        if src is not None and not getattr(wb, "is_dirty", True) and not src.empty:
            self._df = src
            try:
                self.load_columns_from_df()
            except Exception:
                logger.debug("column reload before plot failed", exc_info=True)
        elif not self.adopt_workbook_data():
            return
        cols = [str(c) for c in self._df.columns]
        sel = [i for i in wb.selected_column_indexes() if i < len(cols)]

        # X มาจาก designation (Set As X); ดีฟอลต์คอลัมน์แรก
        x_idx = None
        if hasattr(wb, "x_column_index"):
            x_idx = wb.x_column_index()
        if x_idx is None or x_idx >= len(cols):
            x_idx = 0
        x_name = cols[x_idx]

        def _ignored(i: int) -> bool:
            return hasattr(wb, "column_designation") and wb.column_designation(i) == "ignore"

        def _usable(i: int) -> bool:
            if i == x_idx:
                return False
            if _ignored(i):
                return False
            return True

        use_row_index = False
        explicit_ignored_selection = bool(sel) and all(_ignored(i) for i in sel)

        if style == "histogram":
            if sel:
                y_names = [cols[i] for i in sel if not _ignored(i)]
            else:
                if hasattr(wb, "y_column_indexes"):
                    candidates = [i for i in wb.y_column_indexes() if i < len(cols)]
                else:
                    candidates = list(range(len(cols)))
                y_names = [cols[candidates[0]]] if candidates else []
        elif len(sel) == 1 and not _ignored(sel[0]):
            selected_idx = sel[0]
            y_names = [cols[selected_idx]]
            use_row_index = True
        else:
            sel_y = [i for i in sel if _usable(i)]
            if sel_y:
                y_names = [cols[i] for i in sel_y]
            else:
                if hasattr(wb, "y_column_indexes"):
                    candidates = [i for i in wb.y_column_indexes() if i < len(cols) and i != x_idx]
                else:
                    candidates = [i for i in range(len(cols)) if i != x_idx]
                y_names = [cols[candidates[0]]] if candidates else []

        if not y_names and not explicit_ignored_selection and style != "histogram" and len(cols) == 1:
            y_names = [x_name]
            use_row_index = True
        if not y_names and not explicit_ignored_selection and style == "histogram" and len(cols) == 1:
            y_names = [x_name]

        if not y_names:
            message = (
                "คอลัมน์ที่เลือกถูกตั้งเป็น Disregard — คลิกขวาที่หัวคอลัมน์แล้ว Set As Y ก่อนพล็อต"
                if explicit_ignored_selection
                else "ต้องมีคอลัมน์ Y อย่างน้อย 1 คอลัมน์ (ดูหัวคอลัมน์ A(X)/B(Y) — คลิกขวาเพื่อ Set As)"
            )
            QMessageBox.information(self, "ข้อมูลไม่พอ", message)
            return

        # Keep the first selection visible in the UI; plotting uses explicit requests.
        if not use_row_index:
            self.cbX.setCurrentText(x_name)
        self.cbY.setCurrentText(y_names[0])
        options = self._resolve_plot_options()
        if style == "histogram":
            primary_request = self.build_histogram_request(y_names[0], options)
            if primary_request is None:
                self.plot_histogram()
                return
            requests = [primary_request]
        elif style == "bar":
            if use_row_index:
                primary_request = self._build_row_index_bar_request(y_names[0], options=options)
            else:
                primary_request = self.build_bar_request(
                    x_name,
                    y_names[0],
                    title=f"{y_names[0]} vs {x_name}",
                    options=options,
                )
            if primary_request is None:
                QMessageBox.information(
                    self, "ไม่มีข้อมูล", "เลือกคอลัมน์ X/Y ที่ใช้สร้างกราฟแท่งได้"
                )
                return
            requests = [primary_request]
        else:
            if style == "linesymbol":
                options = replace(options, show_marker=True)
            base = "scatter" if style == "scatter" else "line"
            if use_row_index:
                requests = [self._build_row_index_plot_request(y_names[0])]
            else:
                requests = [
                    self.build_plot_request(x_name, y_name)
                    for y_name in y_names
                ]
            if not requests or requests[0] is None:
                return
            requests = [request for request in requests if request is not None]

        if new_graph:
            try:
                self.tabs.add_tab()  # Origin: คำสั่งพล็อต = Graph window ใหม่
            except Exception:
                logger.debug("add new graph failed; plotting into current", exc_info=True)

        if style == "histogram":
            self.plot_histogram(requests[0])
        elif style == "bar":
            self.plot_bar(requests[0])
        else:
            (self.plot_line if base == "line" else self.plot_scatter)(
                requests[0], options
            )
            for request in requests[1:]:
                (self.add_line_overlay if base == "line" else self.add_scatter_overlay)(
                    request, options
                )
        try:
            self._show_plot_view()
        except Exception:
            logger.debug("show plot view skipped", exc_info=True)

    def plot_line(
        self,
        request: PlotRequest | None = None,
        options: PlotOptions | None = None,
    ):
        request = request or self.build_plot_request()
        if request is None:
            return
        options = self._resolve_plot_options(options)

        selected_tab_ids = self._get_current_plot_tab_ids()
        if not selected_tab_ids:
            return

        try:
            label = request.label
            plot_kwargs = {"linewidth": options.line_width}
            if options.show_marker:
                plot_kwargs["marker"] = options.marker
            meta = self._build_layer_meta(
                "line", label, plot_kwargs, source="plot_line", request=request
            )

            plotter = self.tabs.add_series_to_tabs if self._is_overlay_plot_mode() else self.tabs.plot_to_tabs
            plotter(
                selected_tab_ids,
                request.x,
                request.y,
                label=label,
                style="line",
                meta=meta,
                **plot_kwargs,
            )

            self._update_tabs_after_plot(
                selected_tab_ids,
                xlabel=request.x_column,
                ylabel=request.y_column,
                x_is_datetime=request.x_is_datetime,
                draw_attempts=3,
            )
            self.statusBar().showMessage("Line plot created.")
        except Exception as exc:
            QMessageBox.critical(self, "Line plot failed", f"Reason: {exc}")

    def plot_scatter(
        self,
        request: PlotRequest | None = None,
        options: PlotOptions | None = None,
    ):
        request = request or self.build_plot_request()
        if request is None:
            return
        options = self._resolve_plot_options(options)

        selected_tab_ids = self._get_current_plot_tab_ids()
        if not selected_tab_ids:
            return

        try:
            label = request.label
            plot_kwargs = {"s": options.resolved_scatter_size}
            meta = self._build_layer_meta(
                "scatter", label, plot_kwargs, source="plot_scatter", request=request
            )

            plotter = self.tabs.add_series_to_tabs if self._is_overlay_plot_mode() else self.tabs.plot_to_tabs
            plotter(
                selected_tab_ids,
                request.x,
                request.y,
                label=label,
                style="scatter",
                meta=meta,
                **plot_kwargs,
            )

            self._update_tabs_after_plot(
                selected_tab_ids,
                xlabel=request.x_column,
                ylabel=request.y_column,
                x_is_datetime=request.x_is_datetime,
            )
            self.statusBar().showMessage("Scatter plot created.")
        except Exception as exc:
            QMessageBox.critical(self, "Scatter plot failed", f"Reason: {exc}")

    def add_line_overlay(
        self,
        request: PlotRequest | None = None,
        options: PlotOptions | None = None,
    ):
        request = request or self.build_plot_request()
        if request is None:
            return
        options = self._resolve_plot_options(options)

        selected_tab_ids = self._get_current_plot_tab_ids(
            warning_title="No Tab",
            warning_text="Please create/select a graph tab first",
        )
        if not selected_tab_ids:
            return

        label = request.label
        plot_kwargs = {"linewidth": options.line_width}
        if options.show_marker:
            plot_kwargs["marker"] = options.marker
        meta = self._build_layer_meta(
            "line", label, plot_kwargs, source="add_line_overlay", request=request
        )

        try:
            self.tabs.add_series_to_tabs(
                selected_tab_ids,
                request.x,
                request.y,
                label=label,
                style="line",
                meta=meta,
                **plot_kwargs,
            )
            self._update_tabs_after_plot(
                selected_tab_ids,
                xlabel=request.x_column,
                ylabel=request.y_column,
                x_is_datetime=request.x_is_datetime,
            )
            self.statusBar().showMessage("Added line series (overlay)")
        except Exception:
            logger.debug("Failed to add line overlay", exc_info=True)

    def add_scatter_overlay(
        self,
        request: PlotRequest | None = None,
        options: PlotOptions | None = None,
    ):
        request = request or self.build_plot_request()
        if request is None:
            return
        options = self._resolve_plot_options(options)

        selected_tab_ids = self._get_current_plot_tab_ids(
            warning_title="No Tab",
            warning_text="Please create/select a graph tab first",
        )
        if not selected_tab_ids:
            return

        label = request.label
        plot_kwargs = {"s": options.resolved_scatter_size}
        meta = self._build_layer_meta(
            "scatter", label, plot_kwargs, source="add_scatter_overlay", request=request
        )

        try:
            self.tabs.add_series_to_tabs(
                selected_tab_ids,
                request.x,
                request.y,
                label=label,
                style="scatter",
                meta=meta,
                **plot_kwargs,
            )
            self._update_tabs_after_plot(
                selected_tab_ids,
                xlabel=request.x_column,
                ylabel=request.y_column,
                x_is_datetime=request.x_is_datetime,
            )
            self.statusBar().showMessage("Added scatter series (overlay)")
        except Exception:
            logger.debug("Failed to add scatter overlay", exc_info=True)

    def plot_histogram(self, request: HistogramRequest | None = None):
        request = request or self.build_histogram_request(
            options=self._resolve_plot_options()
        )
        if request is None:
            QMessageBox.information(
                self,
                "ไม่มีข้อมูล",
                "เลือกคอลัมน์ Y ที่มีข้อมูลตัวเลขสำหรับฮิสโตแกรม",
            )
            return

        selected_tab_ids = self._get_current_plot_tab_ids()
        if not selected_tab_ids:
            return

        try:
            vals = np.asarray(request.values, dtype=float)
            col = request.column
            bins = request.options.histogram_bins

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
                    ax.set_title(request.title)

                    if request.options.fit_normal:
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

            self.statusBar().showMessage("Histogram created.")
        except Exception as exc:
            QMessageBox.critical(self, "Plot failed", f"Reason: {exc}")

    def plot_bar(
        self,
        request,
        y=None,
        *,
        xlabel: str = "",
        ylabel: str = "",
        title: str = "",
        options: PlotOptions | None = None,
    ):
        if request is None:
            QMessageBox.information(self, "ไม่มีข้อมูล", "เลือกคอลัมน์ X/Y สำหรับกราฟแท่ง")
            return
        if not isinstance(request, BarRequest):
            request = BarRequest(
                x=request,
                y=y,
                x_column=xlabel,
                y_column=ylabel,
                title=title,
                options=self._resolve_plot_options(options),
            )
        selected_tab_ids = self._get_current_plot_tab_ids()
        if not selected_tab_ids:
            return

        label = request.label
        meta = self._build_layer_meta(
            "bar", label, {"width": request.options.bar_width}, source="plot_bar", request=request
        )
        self.tabs.plot_to_tabs(
            selected_tab_ids,
            request.x,
            request.y,
            label=label,
            style="bar",
            meta=meta,
            width=request.options.bar_width,
        )
        self._update_tabs_after_plot(
            selected_tab_ids,
            xlabel=request.x_column,
            ylabel=request.y_column,
            title=request.title,
            x_tick_labels=request.x,
        )
