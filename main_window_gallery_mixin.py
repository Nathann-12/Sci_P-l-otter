"""Plot Gallery seam — opens the Origin-style :class:`PlotGalleryDialog` and
draws the chosen statistical/QC/relational plot into a **new** Graph window
(Origin loop: every plot command = a fresh Graph).

Logic for the individual plots lives in the pure :mod:`plots` package; this
mixin only bridges the active DataFrame + the ``apply_plot`` canvas seam to the
selected plot spec. New plots need no changes here — they register themselves in
their module's ``PLOTS`` list and appear automatically.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class MainWindowGalleryMixin:
    def plot_basic_gallery_chart(self, spec) -> None:
        """Route top-menu basics through the same Origin-style graph workflow."""
        style = {
            "line": "line",
            "scatter": "scatter",
            "bar": "bar",
            "hist": "histogram",
        }.get(getattr(spec, "key", ""))
        if style is not None:
            self.plot_from_workbook(style, new_graph=True)
            return

        df = self._gallery_dataframe()
        if df is None or getattr(df, "empty", True):
            self.warn("No data", "Open or type some data first, then pick a chart.")
            return
        mapped_df = self._prepare_gallery_dataframe(
            {"title": getattr(spec, "title", "Chart"), "key": getattr(spec, "key", "")},
            df,
        )
        if mapped_df is None:
            return
        try:
            self.tabs.add_tab()
            self.apply_plot(
                lambda ax: spec.apply_func(ax, mapped_df),
                prefer_3d=bool(getattr(spec, "is3d", False)),
                projection=getattr(spec, "projection", None),
            )
            self._show_status(f"Plotted: {getattr(spec, 'title', 'Chart')}")
            self._show_plot_view()
        except Exception:
            logger.debug("basic chart menu plot failed", exc_info=True)
            self.error_box("Plot failed", "Could not draw the selected chart.")

    def open_plot_gallery(self) -> None:
        """Open the categorized plot gallery for the active data."""
        df = self._gallery_dataframe()
        if df is None or getattr(df, "empty", True):
            self.notify("Open or type some data first, then pick a plot.", level="warning")
            return
        try:
            from dialogs.plot_gallery_dialog import PlotGalleryDialog
        except Exception:
            logger.debug("gallery dialog import failed", exc_info=True)
            self.notify("Plot gallery is unavailable.", level="error")
            return
        dlg = PlotGalleryDialog(
            get_dataframe=self._gallery_dataframe,
            on_pick=self.plot_from_gallery,
            parent=self,
        )
        dlg.exec()

    def plot_from_gallery(self, entry: Dict[str, Any]) -> None:
        """Draw a gallery plot spec into a new Graph window."""
        df = self._gallery_dataframe()
        if df is None or getattr(df, "empty", True):
            self.notify("No data to plot.", level="warning")
            return
        func = entry.get("func")
        if not callable(func):
            return
        title = entry.get("title", entry.get("key", "Plot"))
        plot_df = self._prepare_gallery_dataframe(entry, df)
        if plot_df is None:
            return

        prepare = entry.get("prepare")
        draw_prepared = entry.get("draw_prepared")
        if (
            entry.get("heavy")
            and callable(prepare)
            and callable(draw_prepared)
            and self._should_background_gallery_plot(entry, plot_df)
        ):
            self._start_heavy_gallery_plot(entry, plot_df, title)
            return

        # Origin loop: a plot command always opens a fresh Graph.
        try:
            self.tabs.add_tab()
        except Exception:
            logger.debug("add_tab failed; gallery plot cancelled", exc_info=True)
            self.notify("Could not create a new Graph window.", level="error")
            return

        if entry.get("multi"):
            self._draw_multi_panel(func, plot_df, title)
        else:
            try:
                self.apply_plot(
                    lambda ax: func(ax, plot_df),
                    prefer_3d=bool(entry.get("is3d")),
                    projection=entry.get("projection"),
                )
            except Exception:
                logger.debug("apply_plot failed for %s", entry.get("key"), exc_info=True)
                self.notify(f"Could not draw {title}.", level="error")
                return
        try:
            self._show_status(f"Plotted: {title}")
        except Exception:
            pass

    def _should_background_gallery_plot(self, entry, dataframe: pd.DataFrame) -> bool:
        """Use a worker only when computation is large enough to help."""
        if bool(getattr(self, "_force_background_plots", False)):
            return True
        rows = len(dataframe)
        if entry.get("key") == "scatter_matrix":
            numeric = int(dataframe.select_dtypes(include="number").shape[1])
            return rows * max(1, min(numeric, 6) ** 2) >= 200_000
        return rows >= 20_000

    def _start_heavy_gallery_plot(
        self,
        entry: Dict[str, Any],
        dataframe: pd.DataFrame,
        title: str,
    ) -> None:
        """Prepare NumPy/SciPy data off-thread with a visible Cancel action."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QProgressDialog

        from widgets.heavy_plot_worker import HeavyPlotWorker

        previous = getattr(self, "_heavy_plot_worker", None)
        if previous is not None:
            previous.cancel()

        worker = HeavyPlotWorker(entry["prepare"], dataframe.copy(deep=False))
        progress = QProgressDialog(
            f"Preparing {title}…",
            "Cancel",
            0,
            0,
            self,
        )
        progress.setWindowTitle("Large plot")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        self._heavy_plot_worker = worker
        self._heavy_plot_progress = progress

        progress.canceled.connect(worker.cancel)
        worker.signals.finished.connect(
            lambda prepared, w=worker: self._finish_heavy_gallery_plot(
                w, entry, prepared, title
            )
        )
        worker.signals.cancelled.connect(
            lambda w=worker: self._close_heavy_gallery_plot(
                w, f"Cancelled: {title}"
            )
        )
        worker.signals.failed.connect(
            lambda details, w=worker: self._fail_heavy_gallery_plot(
                w, title, details
            )
        )
        progress.show()
        self._show_status(f"Preparing {title} in background…")
        worker.start()

    def _finish_heavy_gallery_plot(self, worker, entry, prepared, title: str) -> None:
        if worker is not getattr(self, "_heavy_plot_worker", None):
            return
        self._close_heavy_gallery_plot(worker)
        try:
            self.tabs.add_tab()
        except Exception:
            logger.debug("add_tab failed after heavy preparation", exc_info=True)
            self.notify("Could not create a new Graph window.", level="error")
            return
        draw_prepared = entry["draw_prepared"]
        try:
            if entry.get("multi"):
                self._draw_multi_panel(draw_prepared, prepared, title)
            else:
                self.apply_plot(lambda ax: draw_prepared(ax, prepared))
        except Exception:
            logger.debug("heavy gallery draw failed for %s", entry.get("key"), exc_info=True)
            self.notify(f"Could not draw {title}.", level="error")
            return
        self._show_status(f"Plotted: {title}")

    def _close_heavy_gallery_plot(self, worker, message: str | None = None) -> None:
        if worker is not getattr(self, "_heavy_plot_worker", None):
            return
        progress = getattr(self, "_heavy_plot_progress", None)
        if progress is not None:
            progress.close()
            progress.deleteLater()
        self._heavy_plot_worker = None
        self._heavy_plot_progress = None
        if message:
            self._show_status(message)

    def _fail_heavy_gallery_plot(self, worker, title: str, details: str) -> None:
        if worker is not getattr(self, "_heavy_plot_worker", None):
            return
        logger.error("Background plot preparation failed for %s\n%s", title, details)
        self._close_heavy_gallery_plot(worker)
        self.notify(f"Could not prepare {title}.", level="error")

    # ----- helpers -----
    def _gallery_dataframe(self) -> Optional[pd.DataFrame]:
        try:
            df = self._resolve_active_dataframe()
        except Exception:
            logger.debug("active dataframe resolution failed", exc_info=True)
            return None
        return df if isinstance(df, pd.DataFrame) else None

    def _prepare_gallery_dataframe(
        self,
        entry: Dict[str, Any],
        df: pd.DataFrame,
    ) -> Optional[pd.DataFrame]:
        """Let users override the registry's first-column heuristics.

        Tests and scripted callers may set ``_suppress_plot_mapping_dialog`` to
        keep the old direct path. In the GUI, accepting the dialog returns a
        temporary reordered DataFrame; cancelling aborts before a Graph is made.
        """
        if bool(getattr(self, "_suppress_plot_mapping_dialog", False)):
            return df
        try:
            from dialogs.plot_data_mapping_dialog import PlotDataMappingDialog
        except Exception:
            logger.debug("plot data mapping dialog import failed", exc_info=True)
            return df
        try:
            dlg = PlotDataMappingDialog(
                df,
                plot_title=str(entry.get("title") or entry.get("key") or "Plot"),
                parent=self,
            )
            if dlg.exec() != dlg.Accepted:
                return None
            mapped = dlg.mapped_dataframe()
            return mapped if isinstance(mapped, pd.DataFrame) else df
        except Exception:
            logger.debug("plot data mapping failed; falling back to active DataFrame", exc_info=True)
            return df

    def _draw_multi_panel(self, func, df: pd.DataFrame, title: str) -> None:
        """Multi-panel plots repaint the whole figure, so bypass the single-axes
        ``apply_plot`` path and hand the plot the fresh graph's figure."""
        tab = None
        try:
            tab = self.tabs.currentWidget()
        except Exception:
            logger.debug("no current tab for multi-panel plot", exc_info=True)
        canvas = getattr(tab, "canvas", None)
        if canvas is None:
            # last resort: still try the single-axes seam
            try:
                self.apply_plot(lambda ax: func(ax, df))
            except Exception:
                logger.debug("multi-panel fallback failed", exc_info=True)
            return
        try:
            self.canvas = canvas
            fig = canvas.fig
            fig.clf()
            ax = fig.add_subplot(111)
            func(ax, df)
            if fig.axes:
                canvas.ax = fig.axes[0]
            try:
                fig.tight_layout()
            except Exception:
                pass
            canvas.draw()
        except Exception:
            logger.debug("multi-panel draw failed for %s", title, exc_info=True)
            self.notify(f"Could not draw {title}.", level="error")
