"""Stateful viewport LOD controller owned by a GraphTab."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from typing import Any

from PySide6.QtCore import QObject, QTimer

from core.render_optimization import (
    apply_bar_lod,
    apply_line_lod,
    canvas_pixel_width,
    render_status,
)

logger = logging.getLogger(__name__)


class ViewportLODController(QObject):
    """Keep render-only layer representations matched to screen resolution.

    The controller mutates existing artists in place, so layer manager, Plot
    Details and decoration references stay valid.  Full arrays live on the
    artist and are never replaced by the decimated representation.
    """

    def __init__(self, graph_tab, *, debounce_ms: int = 80):
        super().__init__(graph_tab)
        self.graph_tab = graph_tab
        self._axes_callbacks: dict[Any, int] = {}
        self._resize_cid: int | None = None
        self._refreshing = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(1, int(debounce_ms)))
        self._timer.timeout.connect(self.refresh)
        self._connect_resize()

    def _connect_resize(self) -> None:
        canvas = getattr(self.graph_tab, "canvas", None)
        if canvas is None or self._resize_cid is not None:
            return
        try:
            self._resize_cid = canvas.mpl_connect("resize_event", self.schedule_refresh)
        except Exception:
            logger.debug("LOD resize callback connection failed", exc_info=True)

    def attach_layer(self, layer_id: str) -> None:
        info = getattr(self.graph_tab, "layers", {}).get(layer_id)
        if not info:
            return
        for artist in info.get("artists", []):
            ax = getattr(artist, "axes", None)
            if ax is None or ax in self._axes_callbacks:
                continue
            try:
                cid = ax.callbacks.connect("xlim_changed", self.schedule_refresh)
                self._axes_callbacks[ax] = cid
            except Exception:
                logger.debug("LOD xlim callback connection failed", exc_info=True)

    def detach_axes(self) -> None:
        for ax, cid in list(self._axes_callbacks.items()):
            try:
                ax.callbacks.disconnect(cid)
            except Exception:
                pass
        self._axes_callbacks.clear()

    def rebind(self) -> None:
        self.detach_axes()
        for layer_id in list(getattr(self.graph_tab, "layers", {})):
            self.attach_layer(layer_id)

    def schedule_refresh(self, *_args) -> None:
        if self._refreshing:
            return
        self._timer.start()

    def refresh(self, *, pixel_width: int | None = None, emit_status: bool = True) -> list[dict[str, Any]]:
        if self._refreshing:
            return []
        self._refreshing = True
        results: list[dict[str, Any]] = []
        try:
            for info in list(getattr(self.graph_tab, "layers", {}).values()):
                if not info.get("visible", True):
                    continue
                style = str(info.get("style", "")).casefold()
                artists = list(info.get("artists", []))
                if not artists:
                    continue
                artist = artists[0]
                ax = getattr(artist, "axes", None)
                if ax is None:
                    continue
                width = pixel_width or canvas_pixel_width(ax)
                try:
                    if style == "line" and hasattr(artist, "set_data"):
                        render_info = apply_line_lod(ax, artist, pixel_width=width)
                    elif style == "bar" and hasattr(artist, "set_verts") and hasattr(
                        artist, "_sciplotter_bar_reducer"
                    ):
                        render_info = apply_bar_lod(ax, artist, pixel_width=width)
                    else:
                        continue
                except Exception:
                    logger.debug("LOD layer refresh failed", exc_info=True)
                    continue
                info.setdefault("meta", {})["render"] = dict(render_info)
                results.append({"style": style, **render_info})
            if results:
                try:
                    self.graph_tab.canvas.draw_idle()
                except Exception:
                    pass
                if emit_status:
                    latest = results[-1]
                    try:
                        self.graph_tab.renderStatusChanged.emit(
                            render_status(latest["style"], latest)
                        )
                    except Exception:
                        pass
        finally:
            self._refreshing = False
        return results

    @contextmanager
    def export_render(self, pixel_width: int):
        """Temporarily render at export resolution, then restore screen LOD."""
        self._timer.stop()
        self.refresh(pixel_width=max(2, int(pixel_width)), emit_status=False)
        try:
            yield
        finally:
            self.refresh(pixel_width=None, emit_status=False)

    def shutdown(self) -> None:
        self._timer.stop()
        self.detach_axes()
        canvas = getattr(self.graph_tab, "canvas", None)
        if canvas is not None and self._resize_cid is not None:
            try:
                canvas.mpl_disconnect(self._resize_cid)
            except Exception:
                pass
        self._resize_cid = None
