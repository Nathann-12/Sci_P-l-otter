"""Per-graph undo/redo for already-applied formatting edits.

Matplotlib formatting is normally mutated in place.  Qt's :class:`QUndoStack`
expects a command to *perform* its edit when it is pushed, so the command in
this module deliberately skips its first ``redo()``: callers capture the graph,
apply the edit normally, then record the before/after pair.

The runtime snapshot builds on :mod:`core.format_clipboard`, but unlike the
cross-graph clipboard it also keeps graph content that a formatting UI can
legitimately edit (titles, labels, limits), logical layer labels/visibility and
SciPlotter-owned inset/colorbar/reference-line configuration.  It never copies
the plotted x/y data arrays.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import hashlib
import logging
import math
import weakref
from typing import Any, Iterator

import numpy as np
from matplotlib.artist import Artist
from PySide6.QtGui import QUndoCommand, QUndoStack

from core import format_clipboard as _clipboard
from core.edit_sequence import next_edit_sequence


LOG = logging.getLogger(__name__)
GRAPH_FORMAT_STATE_VERSION = 1
DEFAULT_UNDO_LIMIT = 30


def _safe_copy(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


def _copy_layer_mapping(value: Any, *, meta: bool = False) -> dict[str, Any]:
    """Copy mutable style dictionaries without duplicating plotted arrays.

    Layer kwargs may contain a 100k-point ``c``/``s`` mapping. Formatting
    operations replace style keys rather than mutating those arrays, so a
    shallow snapshot is both exact and bounded.
    """
    result = dict(value) if isinstance(value, dict) else {}
    if meta and isinstance(result.get("style_kwargs"), dict):
        result["style_kwargs"] = dict(result["style_kwargs"])
    return result


def _capture_reference_lines(ax: Any) -> dict[str, Any]:
    """Read the Plot Details reference guides from their stable ``gid`` tags."""
    result: dict[str, Any] = {
        "refline_h": None,
        "refline_v": None,
        "refline_h_label": "",
        "refline_v_label": "",
        "refline_color": "#ff6b6b",
        "refline_style": "--",
        "refline_width": 1.2,
        "refline_alpha": 1.0,
    }
    reference = None
    for line in list(getattr(ax, "lines", ())):
        gid = str(getattr(line, "get_gid", lambda: "")() or "")
        if gid not in {"_ps_refline_h", "_ps_refline_v"}:
            continue
        reference = reference or line
        try:
            values = line.get_ydata() if gid.endswith("_h") else line.get_xdata()
            value = float(np.asarray(values).ravel()[0])
            result["refline_h" if gid.endswith("_h") else "refline_v"] = value
        except Exception:
            pass
    if reference is not None:
        try:
            result["refline_color"] = _clipboard._hex(reference.get_color())
            result["refline_style"] = reference.get_linestyle()
            result["refline_width"] = float(reference.get_linewidth())
            alpha = reference.get_alpha()
            result["refline_alpha"] = float(alpha if alpha is not None else 1.0)
        except Exception:
            pass
    for text in list(getattr(ax, "texts", ())):
        gid = str(getattr(text, "get_gid", lambda: "")() or "")
        if gid == "_ps_refline_h_label":
            result["refline_h_label"] = str(text.get_text())
        elif gid == "_ps_refline_v_label":
            result["refline_v_label"] = str(text.get_text())
    return result


def _capture_authored_text(fig: Any, axes: list[Any]) -> dict[str, Any]:
    axis_records = []
    for ax in axes:
        titles = {}
        for loc in ("left", "center", "right"):
            try:
                artist = {
                    "left": ax._left_title,
                    "center": ax.title,
                    "right": ax._right_title,
                }[loc]
                titles[loc] = {
                    "text": str(artist.get_text()),
                    "style": _clipboard._capture_text(artist),
                }
            except Exception:
                titles[loc] = {"text": "", "style": {}}
        axis_records.append({"titles": titles})

    suptitle = getattr(fig, "_suptitle", None)
    return {
        "figure_title": (
            {
                "exists": True,
                "text": str(suptitle.get_text()),
                "style": _clipboard._capture_text(suptitle),
            }
            if suptitle is not None
            else {"exists": False, "text": "", "style": {}}
        ),
        "axes": axis_records,
    }


def _capture_layer_state(tab: Any) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for layer_id, info in (getattr(tab, "layers", {}) or {}).items():
        if not isinstance(info, dict):
            continue
        records[str(layer_id)] = {
            "label": str(info.get("label", "")),
            "visible": bool(info.get("visible", True)),
            "kwargs": _copy_layer_mapping(info.get("kwargs", {})),
            "meta": _copy_layer_mapping(info.get("meta", {}), meta=True),
        }
    return records


def _capture_owned_state(axes: list[Any]) -> list[dict[str, Any]]:
    records = []
    for ax in axes:
        semantic = _safe_copy(_clipboard._capture_owned_axis_state(ax))
        # These generated objects have exact, separately captured fallbacks
        # below. Applying both copies would rebuild them twice on every Undo.
        for key in ("inset", "colorbar", "reference_lines"):
            semantic.pop(key, None)
        records.append({
            "semantic": semantic,
            "inset": _safe_copy(getattr(ax, "_ps_inset_cfg", None)),
            "colorbar": _safe_copy(getattr(ax, "_ps_colorbar_cfg", None)),
            "reference_lines": _capture_reference_lines(ax),
        })
    return records


def _freeze(value: Any) -> Any:
    """Convert a runtime snapshot into a deterministic equality fingerprint."""
    if value is None or isinstance(value, (str, bytes, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan")
        if math.isinf(value):
            return ("float", "inf" if value > 0 else "-inf")
        return value
    if isinstance(value, np.ndarray):
        array = np.asarray(value)
        if array.size > 512:
            # Large per-point style mappings are immutable-by-contract during
            # a format transaction. Setters replace their ndarray, so identity
            # detects edits without hashing millions of bytes on the UI thread.
            return ("large-ndarray", id(value), str(array.dtype), tuple(array.shape))
        array = np.ascontiguousarray(array)
        if array.dtype.hasobject:
            payload = repr(tuple(_freeze(item) for item in array.ravel())).encode("utf-8")
            digest = hashlib.sha256(payload).hexdigest()
        else:
            digest = hashlib.sha256(array.view(np.uint8)).hexdigest()
        return ("ndarray", str(array.dtype), tuple(array.shape), digest)
    if isinstance(value, np.generic):
        return _freeze(value.item())
    if isinstance(value, Artist):
        # Legend content contains live source handles.  Identity is stable for
        # the lifetime of one GraphTab and avoids retaining/copying plot data.
        return ("artist", id(value))
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        if len(value) > 512:
            # Large scientific mappings are immutable-by-contract inside a
            # format transaction. Identity + length detects replacement while
            # keeping Ctrl+Z latency independent of row count.
            return ("large-sequence", id(value), len(value))
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    try:
        attrs = vars(value)
    except Exception:
        attrs = None
    if attrs is not None:
        return (
            type(value).__module__,
            type(value).__qualname__,
            _freeze(attrs),
        )
    return (type(value).__module__, type(value).__qualname__, repr(value))


def capture_graph_format_state(tab: Any) -> dict[str, Any]:
    """Capture a restorable, in-memory formatting state for one graph tab.

    The returned object may contain live Matplotlib legend handles and is not a
    project-file format.  It is intentionally bounded by the tab's undo limit.
    """
    fmt = _clipboard._capture_state(
        tab, include_content=True, exact_style=True,
    )
    fig, axes = _clipboard._format_axes(tab)
    state = {
        "version": GRAPH_FORMAT_STATE_VERSION,
        "format": fmt,
        "authored_text": _capture_authored_text(fig, axes),
        "layers": _capture_layer_state(tab),
        "owned": _capture_owned_state(axes),
    }
    state["fingerprint"] = _freeze(state)
    return state


def _restore_layer_state(tab: Any, records: dict[str, Any]) -> None:
    layers = getattr(tab, "layers", {}) or {}
    for layer_id, saved in records.items():
        info = layers.get(layer_id)
        if not isinstance(info, dict) or not isinstance(saved, dict):
            continue
        wanted_label = str(saved.get("label", ""))
        if str(info.get("label", "")) != wanted_label:
            rename = getattr(tab, "_rename_layer_raw", None)
            if callable(rename):
                rename(layer_id, wanted_label)
            else:
                rename = getattr(tab, "_on_layer_rename", None)
                if callable(rename):
                    rename(layer_id, wanted_label)
        info["kwargs"] = _copy_layer_mapping(saved.get("kwargs", {}))
        info["meta"] = _copy_layer_mapping(saved.get("meta", {}), meta=True)
        info["label"] = wanted_label
        visible = bool(saved.get("visible", True))
        setter = getattr(tab, "_set_layer_visibility", None)
        if callable(setter):
            setter(layer_id, visible, refresh=False)
        else:
            for artist in info.get("artists", ()):
                try:
                    artist.set_visible(visible)
                except Exception:
                    pass
            info["visible"] = visible
        manager = getattr(tab, "layer_manager", None)
        if manager is not None:
            try:
                manager.update_layer_label(layer_id, wanted_label)
                manager.update_layer_visibility(layer_id, visible)
            except Exception:
                pass


def _restore_authored_text(fig: Any, axes: list[Any], state: dict[str, Any]) -> None:
    for ax, record in zip(axes, state.get("axes", ())):
        titles = record.get("titles", {}) if isinstance(record, dict) else {}
        for loc, artist in (
            ("left", getattr(ax, "_left_title", None)),
            ("center", getattr(ax, "title", None)),
            ("right", getattr(ax, "_right_title", None)),
        ):
            saved = titles.get(loc, {}) if isinstance(titles, dict) else {}
            if artist is None or not isinstance(saved, dict):
                continue
            try:
                artist.set_text(str(saved.get("text", "")))
                _clipboard._apply_text(artist, saved.get("style", {}))
            except Exception:
                pass

    saved_title = state.get("figure_title", {})
    if not isinstance(saved_title, dict):
        return
    current = getattr(fig, "_suptitle", None)
    if saved_title.get("exists"):
        if current is None:
            current = fig.suptitle(str(saved_title.get("text", "")))
        else:
            current.set_text(str(saved_title.get("text", "")))
        try:
            _clipboard._apply_text(current, saved_title.get("style", {}))
        except Exception:
            pass
    elif current is not None:
        try:
            current.remove()
        except Exception:
            pass
        try:
            fig._suptitle = None
        except Exception:
            pass


def _restore_owned_state(fig: Any, axes: list[Any], records: list[dict[str, Any]]) -> None:
    from core.plot_style import (
        COLORBAR_DEFAULTS,
        INSET_DEFAULTS,
        apply_style,
    )

    for ax, saved in zip(axes, records):
        if not isinstance(saved, dict):
            continue
        semantic = saved.get("semantic")
        if isinstance(semantic, dict):
            _clipboard._apply_owned_axis_state(ax, _safe_copy(semantic), fig)
        inset = saved.get("inset")
        colorbar = saved.get("colorbar")
        apply_style(
            ax,
            {
                "inset": (
                    _safe_copy(inset)
                    if isinstance(inset, dict)
                    else {**INSET_DEFAULTS, "enabled": False}
                ),
                "colorbar": (
                    _safe_copy(colorbar)
                    if isinstance(colorbar, dict)
                    else {**COLORBAR_DEFAULTS, "enabled": False}
                ),
            },
            fig,
            live=True,
        )
        refs = saved.get("reference_lines")
        if isinstance(refs, dict):
            apply_style(ax, {"axes": _safe_copy(refs)}, fig, live=True)

def _restore_graph_format_state_unchecked(tab: Any, state: dict[str, Any]) -> None:
    if not isinstance(state, dict) or state.get("version") != GRAPH_FORMAT_STATE_VERSION:
        raise ValueError("Invalid or unsupported graph-format history state")
    fmt = state.get("format")
    if not _clipboard.is_graph_format_snapshot(fmt):
        raise ValueError("Graph-format history state has no valid format snapshot")

    _restore_layer_state(tab, state.get("layers", {}))
    # For undo, source content (not current target content) must be restored.
    _clipboard._apply_state(
        tab,
        fmt,
        fmt,
        restore_print_presence=not bool(fmt.get("print_figure_present")),
    )
    # The clipboard render pass deliberately normalizes persistent style
    # aliases from the live artist.  Undo must be byte-for-byte faithful to
    # the layer model that existed before the edit, so put its dictionaries
    # back after rendering (labels/visibility are idempotent here).
    _restore_layer_state(tab, state.get("layers", {}))
    fig, axes = _clipboard._format_axes(tab)
    _restore_authored_text(fig, axes, state.get("authored_text", {}))
    _restore_owned_state(fig, axes, state.get("owned", []))

    refresh = getattr(tab, "_refresh_legend", None)
    if callable(refresh):
        refresh()
    if hasattr(tab, "draw"):
        tab.draw()
    elif getattr(fig, "canvas", None) is not None:
        fig.canvas.draw_idle()


def restore_graph_format_state(tab: Any, state: dict[str, Any]) -> None:
    """Restore a runtime snapshot transactionally.

    If a strict adapter fails, the current graph is put back before the error
    is re-raised.  GraphTab history recording is suspended during both passes.
    """
    history = getattr(tab, "graph_format_history", None)
    suspension = history.suspend() if history is not None else nullcontext()
    with suspension:
        current = capture_graph_format_state(tab)
        try:
            _restore_graph_format_state_unchecked(tab, state)
        except Exception:
            try:
                _restore_graph_format_state_unchecked(tab, current)
            except Exception:
                LOG.exception("Graph-format history rollback failed")
            raise


class GraphFormatSnapshotCommand(QUndoCommand):
    """One formatting command whose visual mutation already happened."""

    def __init__(
        self,
        history: "GraphFormatHistory",
        label: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        super().__init__(str(label) or "Format graph")
        self._history_ref = weakref.ref(history)
        self._before = before
        self._after = after
        self._first_redo = True
        self.edit_sequence = next_edit_sequence()

    def _restore(self, state: dict[str, Any]) -> None:
        history = self._history_ref()
        if history is not None:
            history.restore(state)

    def undo(self) -> None:
        self._restore(self._before)

    def redo(self) -> None:
        # QUndoStack.push() invokes redo immediately.  The caller has already
        # applied the edit, so only later redo operations restore ``after``.
        if self._first_redo:
            self._first_redo = False
            return
        self._restore(self._after)


@dataclass
class _ActiveTransaction:
    label: str
    before: dict[str, Any]
    depth: int = 1
    failed: bool = False
    cancelled: bool = False


class GraphFormatHistory:
    """Bounded formatting history owned by exactly one GraphTab."""

    def __init__(self, tab: Any, *, undo_limit: int = DEFAULT_UNDO_LIMIT) -> None:
        self._tab_ref = weakref.ref(tab)
        self.stack = QUndoStack(tab)
        self.stack.setUndoLimit(max(1, int(undo_limit)))
        self._suspend_depth = 0
        self._active: _ActiveTransaction | None = None

    @property
    def is_suspended(self) -> bool:
        return self._suspend_depth > 0

    @contextmanager
    def suspend(self) -> Iterator[None]:
        self._suspend_depth += 1
        try:
            yield
        finally:
            self._suspend_depth = max(0, self._suspend_depth - 1)

    def capture(self) -> dict[str, Any]:
        tab = self._tab_ref()
        if tab is None:
            raise RuntimeError("The graph tab has already been destroyed")
        return capture_graph_format_state(tab)

    def restore(self, state: dict[str, Any]) -> None:
        tab = self._tab_ref()
        if tab is None:
            return
        with self.suspend():
            restore_graph_format_state(tab, state)

    def clear(self) -> None:
        if self._active is not None:
            self._active.cancelled = True
        self._active = None
        self.stack.clear()
        tab = self._tab_ref()
        if tab is not None:
            tab._graph_redo_invalidated = False

    def record_applied(
        self,
        label: str,
        before: dict[str, Any],
        after: dict[str, Any] | None = None,
    ) -> bool:
        """Record an edit that is already visible without applying it again."""
        if self.is_suspended:
            return False
        after = after or self.capture()
        if before.get("fingerprint") == after.get("fingerprint"):
            return False
        tab = self._tab_ref()
        if tab is not None:
            manager = getattr(tab, "annotation_manager", None)
            if manager is not None:
                getattr(manager, "_redo", []).clear()
                getattr(manager, "_redo_sequences", []).clear()
            tab._graph_redo_invalidated = False
        self.stack.push(GraphFormatSnapshotCommand(self, label, before, after))
        return True

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        """Capture one before/after pair around a formatting mutation.

        Nested transactions collapse into the outer command.  An exception
        restores the outer pre-edit state and leaves the undo stack unchanged.
        """
        if self.is_suspended:
            yield
            return

        outermost = self._active is None
        if outermost:
            self._active = _ActiveTransaction(str(label), self.capture())
        else:
            self._active.depth += 1
        active = self._active
        try:
            yield
        except Exception:
            active.failed = True
            raise
        finally:
            active.depth -= 1
            if active.depth == 0:
                if self._active is active:
                    self._active = None
                if active.cancelled:
                    pass
                elif active.failed:
                    self.restore(active.before)
                else:
                    self.record_applied(active.label, active.before)


def graph_format_transaction(tab: Any, label: str):
    """Public convenience wrapper used by graph-facing mixins."""
    history = getattr(tab, "graph_format_history", None)
    if history is None:
        return nullcontext()
    return history.transaction(label)


__all__ = [
    "DEFAULT_UNDO_LIMIT",
    "GRAPH_FORMAT_STATE_VERSION",
    "GraphFormatHistory",
    "GraphFormatSnapshotCommand",
    "capture_graph_format_state",
    "graph_format_transaction",
    "restore_graph_format_state",
]
