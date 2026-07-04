"""OriginPro-style MDI workspace for SciPlotter.

This module provides :class:`MdiWorkspace`, a ``QWidget`` that wraps a
``QMdiArea`` and hosts each graph (a :class:`widgets.plot_tabs.GraphTab`) inside
its own ``QMdiSubWindow``, just like OriginPro hosts Graph and Book windows.

Adapter shape — (a): ``MdiWorkspace`` *itself* exposes the full TabManager
public surface, so the rest of the app can do ``self.tabs = MdiWorkspace(mw)``
as a drop-in replacement for ``widgets.plot_tabs.TabManager`` without any other
code change. (Shape (b) — a separate adapter object — was rejected because the
existing code reads ``self.tabs.tabs`` directly and connects to TabManager's
``currentChanged``/``tabCreated``/``tabRemoved`` signals; keeping everything on
one QObject avoids a second indirection.)

TabManager-compatible API exposed by ``MdiWorkspace``:
  - ``tabs``                      dict ``{tab_id: GraphTab}`` (live, read/iterated)
  - ``add_tab(name=None)``        create a graph sub-window, return its tab_id
  - ``remove_all_tabs()``         close every graph sub-window
  - ``count()``                   number of graph tabs
  - ``widget(i)``                 i-th GraphTab by insertion order
  - ``currentWidget()``           active GraphTab (focused graph sub-window)
  - ``addTab(widget, label="")``  QTabWidget-compat: host ``widget`` in a sub-window
  - ``setCurrentIndex(i)``        activate the i-th graph sub-window
  - ``currentIndex()``            index of the active graph (or -1)
  - ``get_current_tab_id()``      tab_id of the active graph, or None
  - ``get_open_tabs()``           list of ``(tab_id, name)``
  - ``plot_to_tabs(...)``         ported from TabManager (replace/overlay aware)
  - ``add_series_to_tabs(...)``   ported from TabManager (overlay)
  - ``add_series_to_current_tab(...)``
  - signals ``currentChanged(int)``, ``tabCreated(str)``, ``tabRemoved(str)``
  - ``setSizePolicy(...)``        inherited from QWidget (forwarded as-is)

Extras for a future Project Explorer:
  - ``add_book(widget, title="Book1")``  host an arbitrary widget (e.g. a
    WorkbookWidget) in a sub-window titled like Origin
  - ``sub_windows()``  list of ``(kind, title, sub_window)`` where kind is
    ``"graph"`` or ``"book"``
  - signals ``subWindowAdded(str, str)``, ``subWindowRemoved(str, str)``,
    ``subWindowRenamed(str, str)`` (kind, title)

Could NOT replicate from TabManager (QTabWidget-specific, not used by the app on
``self.tabs`` — verified by grep): ``tabBar()``, ``setTabsClosable``,
``setMovable``, ``setTabText``/``tabText`` (renaming is done on the sub-window
title here), ``removeTab(index)`` by index (use ``_remove_tab_by_id``),
``setDocumentMode``, ``setUsesScrollButtons``. These are stubbed where harmless
or simply omitted; nothing in ``main_window_*`` / ``main.py`` calls them on the
tabs object.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QMdiArea,
    QMdiSubWindow,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.plot_data import (
    axis_uses_dates,
    clamp_date_limits,
    is_invalid_plot_value,
    prepare_plot_data,
    reset_numeric_axis,
    to_sequence_for_plot,
)
from widgets.plot_tabs import GraphTab

logger = logging.getLogger(__name__)


# Dark styling for the MDI area + sub-window frames, matching shell.qss /
# dark_modern.qss palette (bg #1e2126, surface #23272e, border #3a3f44,
# accent #4F9CF9, text #e6e6e6). The backdrop sits one step darker than the
# shell panels so Book/Graph windows visibly float above it.
_MDI_STYLESHEET = """
#MdiWorkspace {
    background-color: #1e2126;
}
QMdiArea#MdiArea {
    background-color: #15181d;
    border: none;
}
QMdiSubWindow {
    background-color: #23272e;
    border: 1px solid #3a3f44;
    /* QStyleSheetStyle resolves the title-bar Highlight from
       selection-background-color, overriding any widget palette — this is
       what actually sets the active title bar tone (muted Origin navy). */
    selection-background-color: #2b4066;
    selection-color: #e8eef7;
}
QMdiSubWindow:focus,
QMdiSubWindow[active="true"] {
    border: 1px solid #4F9CF9;
}
QMdiSubWindow > QWidget {
    background-color: #1e2126;
}
"""


def _sub_window_icon(kind: str):
    """qtawesome icon for a sub-window title bar (graph/book), or None.

    Replaces the default Qt logo icon; matches main.py's _QTA_ICON_MAP style
    (fa5s set, light gray so it reads on the dark title bar).
    """
    try:
        import qtawesome as qta

        name = "fa5s.chart-line" if kind == "graph" else "fa5s.table"
        return qta.icon(name, color="#cfd3d6")
    except Exception:
        logger.debug("qtawesome sub-window icon unavailable", exc_info=True)
        return None


class _GraphSubWindow(QMdiSubWindow):
    """A graph sub-window that keeps the workspace registry in sync when the
    user closes it via the title-bar button (so ``self.tabs`` never goes stale)."""

    def __init__(self, workspace, tab_id):
        super().__init__()
        self._workspace = workspace
        self._tab_id = tab_id
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def closeEvent(self, event):
        try:
            proceed = self._workspace._detach_graph(self._tab_id, self, event)
        except Exception:
            proceed = True
        if proceed:
            super().closeEvent(event)


class MdiWorkspace(QWidget):
    """OriginPro-style MDI workspace exposing a TabManager-compatible surface.

    See module docstring for the chosen adapter shape (a) and the full API.
    """

    # --- TabManager-compatible signals --------------------------------------
    currentChanged = Signal(int)
    tabCreated = Signal(str)
    tabRemoved = Signal(str)

    # --- Project Explorer helper signals ------------------------------------
    subWindowAdded = Signal(str, str)    # (kind, title)
    subWindowRemoved = Signal(str, str)  # (kind, title)
    subWindowRenamed = Signal(str, str)  # (kind, title)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MdiWorkspace")

        self._tab_counter = 0
        self._book_counter = 0
        # Insertion-ordered registry of graph tabs (Python 3.7+ dicts are ordered).
        self.tabs: Dict[str, GraphTab] = {}
        # tab_id -> QMdiSubWindow (graph sub-windows only)
        self._graph_subs: Dict[str, QMdiSubWindow] = {}
        # Book registry: title -> (widget, sub_window)
        self._books: Dict[str, Tuple[QWidget, QMdiSubWindow]] = {}
        self._suppress_activation = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.mdi = QMdiArea(self)
        self.mdi.setObjectName("MdiArea")
        self.mdi.setViewMode(QMdiArea.SubWindowView)
        self.mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.mdi.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        try:
            self.mdi.setActivationOrder(QMdiArea.ActivationHistoryOrder)
        except Exception:
            logger.debug("Could not set MDI activation order", exc_info=True)
        layout.addWidget(self.mdi)

        self.setStyleSheet(_MDI_STYLESHEET)
        # Origin-like muted title bars: the style draws QMdiSubWindow titles
        # from QPalette.Highlight/HighlightedText, which the base theme sets to
        # the bright accent blue. Override on the MDI area (inherited by every
        # sub-window) with a deep desaturated navy for active windows and a
        # neutral frame tone for inactive ones.
        try:
            # Fusion lightens Highlight when painting the title gradient, so
            # these are set a step darker than the tone we actually want on
            # screen (~#2b4066 for the active bar).
            pal = self.mdi.palette()
            pal.setColor(QPalette.Active, QPalette.Highlight, QColor("#253853"))
            pal.setColor(QPalette.Inactive, QPalette.Highlight, QColor("#242a33"))
            pal.setColor(QPalette.Active, QPalette.HighlightedText, QColor("#e8eef7"))
            pal.setColor(QPalette.Inactive, QPalette.HighlightedText, QColor("#9aa3af"))
            self.mdi.setPalette(pal)
        except Exception:
            logger.debug("MDI title palette override skipped", exc_info=True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.mdi.subWindowActivated.connect(self._on_sub_window_activated)

        # Match TabManager: start with one graph so the app always has a canvas.
        self.add_tab("Graph 1")

    # ======================================================================
    # MainWindow accessor (TabManager used parent() to reach MainWindow for
    # plot_mode). We mirror that: the workspace's parent is the MainWindow.
    # ======================================================================
    def _main_window(self):
        try:
            return self.parent()
        except Exception:
            return None

    # ======================================================================
    # Graph sub-window lifecycle
    # ======================================================================
    def add_tab(self, name=None) -> str:
        """Create a new graph (GraphTab in a new sub-window). Returns tab_id.

        Mirrors ``TabManager.add_tab``: increments the counter, defaults the
        name to ``"Graph N"``, registers the GraphTab in ``self.tabs``,
        activates it, and emits ``tabCreated``.
        """
        self._tab_counter += 1
        if name is None:
            name = f"Graph {self._tab_counter}"
        tab_id = f"tab_{self._tab_counter}"

        graph_tab = GraphTab(tab_id, name, self)
        sub = _GraphSubWindow(self, tab_id)
        sub.setWidget(graph_tab)
        sub.setWindowTitle(name)
        icon = _sub_window_icon("graph")
        if icon is not None:
            sub.setWindowIcon(icon)
        # Origin-like default geometry; cascading offsets keep new graphs visible.
        offset = 24 * (len(self._graph_subs) % 6)
        self.mdi.addSubWindow(sub)
        sub.resize(560, 420)
        sub.move(20 + offset, 20 + offset)
        sub.show()

        self.tabs[tab_id] = graph_tab
        self._graph_subs[tab_id] = sub

        self._suppress_activation = True
        try:
            self.mdi.setActiveSubWindow(sub)
        finally:
            self._suppress_activation = False

        try:
            self.tabCreated.emit(tab_id)
        except Exception:
            logger.debug("tabCreated emit failed", exc_info=True)
        try:
            self.subWindowAdded.emit("graph", name)
        except Exception:
            logger.debug("subWindowAdded emit failed", exc_info=True)
        # Emit currentChanged so listeners (canvas reference) refresh.
        try:
            self.currentChanged.emit(self.currentIndex())
        except Exception:
            logger.debug("currentChanged emit failed", exc_info=True)
        return tab_id

    def add_book(self, widget: QWidget, title: str = "Book1") -> QMdiSubWindow:
        """Host an arbitrary widget (e.g. a WorkbookWidget) in a sub-window.

        Returns the created QMdiSubWindow. Titled like Origin (Book1, Book2…)
        when the default title collides.
        """
        self._book_counter += 1
        if title in self._books:
            title = f"Book{self._book_counter}"
        sub = QMdiSubWindow()
        sub.setWidget(widget)
        sub.setWindowTitle(title)
        sub.setAttribute(Qt.WA_DeleteOnClose, False)
        icon = _sub_window_icon("book")
        if icon is not None:
            sub.setWindowIcon(icon)
        offset = 24 * (len(self._books) % 6)
        self.mdi.addSubWindow(sub)
        sub.resize(620, 440)
        sub.move(80 + offset, 60 + offset)
        sub.show()
        self._books[title] = (widget, sub)
        try:
            self.subWindowAdded.emit("book", title)
        except Exception:
            logger.debug("subWindowAdded emit failed", exc_info=True)
        return sub

    def remove_all_tabs(self) -> None:
        """Close every graph sub-window, emitting ``tabRemoved`` for each."""
        for tab_id in list(self._graph_subs.keys()):
            self._remove_tab_by_id(tab_id, force=True)

    def _remove_tab_by_id(self, tab_id: str, force: bool = False) -> None:
        if tab_id not in self._graph_subs:
            return
        # TabManager refuses to close the last tab via the close button; keep
        # the same guard for interactive closes, but allow remove_all_tabs.
        if not force and len(self._graph_subs) <= 1:
            return
        sub = self._graph_subs.pop(tab_id, None)
        graph_tab = self.tabs.pop(tab_id, None)
        title = sub.windowTitle() if sub is not None else ""
        if sub is not None:
            self._suppress_activation = True
            try:
                self.mdi.removeSubWindow(sub)
            except Exception:
                logger.debug("removeSubWindow failed", exc_info=True)
            finally:
                self._suppress_activation = False
            try:
                sub.deleteLater()
            except Exception:
                logger.debug("sub.deleteLater failed", exc_info=True)
        if graph_tab is not None:
            try:
                graph_tab.deleteLater()
            except Exception:
                logger.debug("graph_tab.deleteLater failed", exc_info=True)
        try:
            self.tabRemoved.emit(tab_id)
        except Exception:
            logger.debug("tabRemoved emit failed", exc_info=True)
        try:
            self.subWindowRemoved.emit("graph", title)
        except Exception:
            logger.debug("subWindowRemoved emit failed", exc_info=True)
        try:
            self.currentChanged.emit(self.currentIndex())
        except Exception:
            logger.debug("currentChanged emit failed", exc_info=True)

    def _detach_graph(self, tab_id: str, sub: QMdiSubWindow, event) -> bool:
        """Sync registries when a graph sub-window is closed interactively.

        Keeps at least one graph (matching TabManager's last-tab guard): vetoes
        the close and returns False when this is the last graph; otherwise pops
        it from the registries, emits removal signals, and returns True so the
        window may close (WA_DeleteOnClose then deletes it).
        """
        if len(self._graph_subs) <= 1 and tab_id in self._graph_subs:
            try:
                event.ignore()
            except Exception:
                logger.debug("close ignore failed", exc_info=True)
            return False
        self._graph_subs.pop(tab_id, None)
        self.tabs.pop(tab_id, None)
        title = sub.windowTitle() if sub is not None else ""
        for _sig, _args in (
            (self.tabRemoved, (tab_id,)),
            (self.subWindowRemoved, ("graph", title)),
            (self.currentChanged, (self.currentIndex(),)),
        ):
            try:
                _sig.emit(*_args)
            except Exception:
                logger.debug("signal emit failed on graph close", exc_info=True)
        return True

    # ======================================================================
    # QTabWidget-compatible surface
    # ======================================================================
    def count(self) -> int:
        return len(self._graph_subs)

    def widget(self, index: int) -> Optional[GraphTab]:
        """Return the i-th GraphTab by insertion order (TabManager semantics)."""
        graphs = list(self.tabs.values())
        if 0 <= index < len(graphs):
            return graphs[index]
        return None

    def tabText(self, index: int) -> str:
        """QTabWidget-compat: title of the i-th graph (used by session save)."""
        subs = list(self._graph_subs.values())
        if 0 <= index < len(subs):
            return subs[index].windowTitle()
        return ""

    def setTabText(self, index: int, text: str) -> None:
        """QTabWidget-compat: rename the i-th graph's sub-window."""
        ids = list(self._graph_subs.keys())
        if 0 <= index < len(ids):
            self.rename_tab(ids[index], text)

    def addTab(self, widget: QWidget, label: str = "") -> int:
        """QTabWidget-style compat: host ``widget`` in a new sub-window.

        Returns the sub-window's index. If ``widget`` is a GraphTab it is
        registered in ``self.tabs`` so the rest of the API sees it; otherwise
        it is treated as a book-like window.
        """
        if isinstance(widget, GraphTab):
            tab_id = getattr(widget, "tab_id", None)
            if not tab_id:
                self._tab_counter += 1
                tab_id = f"tab_{self._tab_counter}"
                widget.tab_id = tab_id
            sub = QMdiSubWindow()
            sub.setWidget(widget)
            sub.setWindowTitle(label or getattr(widget, "name", "") or tab_id)
            sub.setAttribute(Qt.WA_DeleteOnClose, False)
            icon = _sub_window_icon("graph")
            if icon is not None:
                sub.setWindowIcon(icon)
            self.mdi.addSubWindow(sub)
            sub.show()
            self.tabs[tab_id] = widget
            self._graph_subs[tab_id] = sub
            try:
                self.tabCreated.emit(tab_id)
                self.subWindowAdded.emit("graph", sub.windowTitle())
            except Exception:
                logger.debug("addTab emit failed", exc_info=True)
            return self.indexOf(widget)
        # Non-graph widget → book window.
        self.add_book(widget, title=label or f"Book{self._book_counter + 1}")
        return self.count()

    def indexOf(self, widget: QWidget) -> int:
        graphs = list(self.tabs.values())
        for i, gt in enumerate(graphs):
            if gt is widget:
                return i
        return -1

    def currentWidget(self) -> Optional[GraphTab]:
        """Return the active GraphTab (the one in the focused graph sub-window).

        Falls back to the first graph if no graph sub-window is currently the
        active one (e.g. a book window has focus, or nothing is active).
        """
        active = self.mdi.activeSubWindow()
        if active is not None:
            for tab_id, sub in self._graph_subs.items():
                if sub is active:
                    return self.tabs.get(tab_id)
        # Fallback: first graph by insertion order (never None while a graph exists).
        return next(iter(self.tabs.values()), None)

    def currentIndex(self) -> int:
        current = self.currentWidget()
        if current is None:
            return -1
        return self.indexOf(current)

    def setCurrentIndex(self, index: int) -> None:
        graphs = list(self.tabs.items())
        if 0 <= index < len(graphs):
            tab_id, _ = graphs[index]
            sub = self._graph_subs.get(tab_id)
            if sub is not None:
                self.mdi.setActiveSubWindow(sub)

    # ======================================================================
    # tab_id helpers (ported from TabManager)
    # ======================================================================
    def get_current_tab_id(self) -> Optional[str]:
        """Return the active graph's tab_id, mapped from the active sub-window."""
        active = self.mdi.activeSubWindow()
        if active is not None:
            for tab_id, sub in self._graph_subs.items():
                if sub is active:
                    return tab_id
        # Fallback consistent with currentWidget(): first graph.
        current = self.currentWidget()
        for tab_id, gt in self.tabs.items():
            if gt is current:
                return tab_id
        return None

    def get_open_tabs(self) -> List[Tuple[str, str]]:
        result: List[Tuple[str, str]] = []
        for tab_id, sub in self._graph_subs.items():
            result.append((tab_id, sub.windowTitle()))
        return result

    def rename_tab(self, tab_id: str, new_name: str) -> None:
        """Rename a graph sub-window title (Origin-style window rename)."""
        sub = self._graph_subs.get(tab_id)
        gt = self.tabs.get(tab_id)
        if sub is None:
            return
        new_name = (new_name or "").strip()
        if not new_name:
            return
        sub.setWindowTitle(new_name)
        if gt is not None and hasattr(gt, "name"):
            gt.name = new_name
        try:
            self.subWindowRenamed.emit("graph", new_name)
        except Exception:
            logger.debug("subWindowRenamed emit failed", exc_info=True)

    # ======================================================================
    # Project Explorer helper
    # ======================================================================
    def sub_windows(self) -> List[Tuple[str, str, QMdiSubWindow]]:
        """Return ``[(kind, title, sub_window), ...]`` for graphs then books."""
        items: List[Tuple[str, str, QMdiSubWindow]] = []
        for sub in self._graph_subs.values():
            items.append(("graph", sub.windowTitle(), sub))
        for title, (_w, sub) in self._books.items():
            items.append(("book", sub.windowTitle() or title, sub))
        return items

    def all_windows(self) -> List[Tuple[str, str, QMdiSubWindow]]:
        """Alias of :meth:`sub_windows` — every window (graphs then books).

        Provided for the Project Explorer, which enumerates the whole project
        via ``all_windows()``. Books are listed after graphs so the tree reads
        in a stable, Origin-like order.
        """
        return self.sub_windows()

    # Convenience layout actions (Origin-style window arrangement).
    def tile(self) -> None:
        self.mdi.tileSubWindows()

    def cascade(self) -> None:
        self.mdi.cascadeSubWindows()

    # ======================================================================
    # Activation handling
    # ======================================================================
    def _on_sub_window_activated(self, sub: Optional[QMdiSubWindow]) -> None:
        if self._suppress_activation:
            return
        if sub is None:
            return
        # Only emit currentChanged when a *graph* sub-window becomes active,
        # mirroring TabManager (which only ever held graph tabs).
        for _tab_id, gsub in self._graph_subs.items():
            if gsub is sub:
                try:
                    self.currentChanged.emit(self.currentIndex())
                except Exception:
                    logger.debug("currentChanged emit failed", exc_info=True)
                return

    # ======================================================================
    # Plotting surface — ported from TabManager (operates on self.tabs +
    # GraphTab objects, so the logic transfers unchanged to MDI-hosted graphs).
    # ======================================================================
    def plot_to_tabs(
        self,
        tab_ids,
        x,
        y,
        label="",
        style="line",
        meta: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        created = []
        base_kwargs = dict(kwargs)
        for tab_id in tab_ids:
            if tab_id not in self.tabs:
                continue
            tab = self.tabs[tab_id]
            ax = tab.get_axes()
            try:
                mw = self._main_window()
                mode = getattr(mw, "plot_mode", None)
            except Exception:
                mode = None
            overlay_mode = mode is not None and not str(mode).endswith("REPLACE")
            if overlay_mode:
                created.extend(
                    self.add_series_to_tabs(
                        [tab_id], x, y, label=label, style=style, meta=meta, **kwargs
                    )
                )
                continue
            tab.clear_layers()
            ax.clear()
            local_kwargs = dict(base_kwargs)
            artists = []
            auto_label = label
            if not auto_label:
                try:
                    auto_label = getattr(tab, "name", "Series")
                except Exception:
                    auto_label = "Series"
            x_vals, y_vals, x_is_datetime = prepare_plot_data(x, y)
            try:
                if style == "histogram":
                    hist_source = []
                    for val in to_sequence_for_plot(y):
                        if is_invalid_plot_value(val):
                            continue
                        try:
                            hist_source.append(float(val))
                        except Exception:
                            continue
                    if not hist_source:
                        continue
                    y_vals = hist_source
                    x_vals = list(range(len(y_vals)))
                    x_is_datetime = False
                    hist = ax.hist(y_vals, label=auto_label, **local_kwargs)
                    artists = list(hist[2]) if len(hist) >= 3 else []
                else:
                    if not x_vals or not y_vals:
                        continue
                    if style == "line":
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                    elif style == "scatter":
                        artists = [ax.scatter(x_vals, y_vals, label=auto_label, **local_kwargs)]
                    elif style == "bar":
                        container = ax.bar(range(len(x_vals)), y_vals, label=auto_label, **local_kwargs)
                        artists = list(container)
                        ax.set_xticks(range(len(x_vals)))
                        try:
                            ax.set_xticklabels(list(map(str, x_vals)), rotation=45, ha="right")
                        except Exception:
                            pass
                    else:
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                ax.relim()
                ax.autoscale_view()
                if not x_is_datetime and axis_uses_dates(ax.xaxis):
                    reset_numeric_axis(ax)
                if x_is_datetime and len(x_vals) >= 2:
                    ax.set_xlim(min(x_vals), max(x_vals))
                clamp_date_limits(ax)
                ax.grid(True, alpha=0.3)
                if auto_label:
                    try:
                        ax.legend(loc="best")
                    except Exception:
                        pass
                try:
                    from processors import beautify_axes

                    beautify_axes(ax, x_is_datetime=x_is_datetime)
                except Exception:
                    pass
                clamp_date_limits(ax)
                try:
                    tab.canvas.fig.tight_layout()
                except Exception:
                    pass
                clamp_date_limits(ax)
                try:
                    tab.draw()
                except Exception:
                    try:
                        tab.canvas.draw()
                    except Exception:
                        try:
                            tab.canvas.fig.canvas.draw_idle()
                        except Exception:
                            pass
                layer_meta = dict(meta or {})
                layer_meta.setdefault("style", style)
                layer_meta.setdefault("label", auto_label)
                layer_id = tab.register_layer(
                    artists, auto_label or label or "", style, meta=layer_meta, kwargs=local_kwargs
                )
                if layer_id:
                    created.append((tab_id, layer_id))
                    if hasattr(tab, "_refresh_legend"):
                        tab._refresh_legend()
            except Exception:
                logger.debug("plot_to_tabs failed for %s", tab_id, exc_info=True)
        return created

    def add_series_to_tabs(
        self,
        tab_ids,
        x,
        y,
        label: str = "",
        style: str = "line",
        meta: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        created = []
        base_kwargs = dict(kwargs)
        for tab_id in tab_ids:
            if tab_id not in self.tabs:
                continue
            tab = self.tabs[tab_id]
            ax = tab.get_axes()
            auto_label = label
            if not auto_label:
                try:
                    auto_label = (
                        f"Series {len([l for l in ax.get_lines() if not l.get_label().startswith('_')]) + 1}"
                    )
                except Exception:
                    auto_label = "Series"
            local_kwargs = dict(base_kwargs)
            artists = []
            x_vals, y_vals, x_is_datetime = prepare_plot_data(x, y)
            try:
                if style == "histogram":
                    hist_source = []
                    for val in to_sequence_for_plot(y):
                        if is_invalid_plot_value(val):
                            continue
                        try:
                            hist_source.append(float(val))
                        except Exception:
                            continue
                    if not hist_source:
                        continue
                    y_vals = hist_source
                    x_vals = list(range(len(y_vals)))
                    x_is_datetime = False
                    hist = ax.hist(y_vals, label=auto_label, **local_kwargs)
                    artists = list(hist[2]) if len(hist) >= 3 else []
                else:
                    if not x_vals or not y_vals:
                        continue
                    if style == "line":
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                    elif style == "scatter":
                        artists = [ax.scatter(x_vals, y_vals, label=auto_label, **local_kwargs)]
                    elif style == "bar":
                        container = ax.bar(range(len(x_vals)), y_vals, label=auto_label, **local_kwargs)
                        artists = list(container)
                        ax.set_xticks(range(len(x_vals)))
                        try:
                            ax.set_xticklabels(list(map(str, x_vals)), rotation=45, ha="right")
                        except Exception:
                            pass
                    else:
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                ax.relim()
                ax.autoscale_view()
                if not x_is_datetime and axis_uses_dates(ax.xaxis):
                    reset_numeric_axis(ax)
                if x_is_datetime and len(x_vals) >= 2:
                    ax.set_xlim(min(x_vals), max(x_vals))
                clamp_date_limits(ax)
                try:
                    handles, labels = ax.get_legend_handles_labels()
                    if any(lbl and not lbl.startswith("_") for lbl in labels):
                        ax.legend(loc="best")
                except Exception:
                    pass
                clamp_date_limits(ax)
                try:
                    from processors import beautify_axes

                    beautify_axes(ax, x_is_datetime=x_is_datetime)
                except Exception:
                    pass
                clamp_date_limits(ax)
                try:
                    tab.canvas.fig.tight_layout()
                except Exception:
                    pass
                clamp_date_limits(ax)
                try:
                    tab.draw()
                except Exception:
                    try:
                        tab.canvas.draw()
                    except Exception:
                        try:
                            tab.canvas.fig.canvas.draw_idle()
                        except Exception:
                            pass
                layer_meta = dict(meta or {})
                layer_meta.setdefault("style", style)
                layer_meta.setdefault("label", auto_label)
                layer_id = tab.register_layer(
                    artists, auto_label or label or "", style, meta=layer_meta, kwargs=local_kwargs
                )
                if layer_id:
                    created.append((tab_id, layer_id))
                    if hasattr(tab, "_refresh_legend"):
                        tab._refresh_legend()
            except Exception:
                logger.debug("add_series_to_tabs failed for %s", tab_id, exc_info=True)
        return created

    def add_series_to_current_tab(
        self,
        x,
        y,
        label: str = "",
        style: str = "line",
        meta: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        current_tab_id = self.get_current_tab_id()
        if not current_tab_id:
            return []
        return self.add_series_to_tabs(
            [current_tab_id], x, y, label=label, style=style, meta=meta, **kwargs
        )
