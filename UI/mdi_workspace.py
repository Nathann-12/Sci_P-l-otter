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
from PySide6.QtGui import QBrush, QPalette
from PySide6.QtWidgets import (
    QApplication,
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
from core.render_optimization import (
    apply_line_lod,
    canvas_pixel_width,
    draw_bar_series,
    draw_scatter_series,
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
    """Thin line qtawesome icon for a sub-window title bar (graph/book), or None.

    Replaces the default Qt logo icon; matches main.py's thin mdi icon style.
    """
    try:
        from main import _qtawesome_icon
        name = "mdi.chart-line" if kind == "graph" else "mdi.table"
        return _qtawesome_icon(name)
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


class _BookSubWindow(QMdiSubWindow):
    """A Book sub-window that removes itself from the workspace registry when the
    user closes it via the title-bar button, so the Project Explorer and the
    multi-book state never keep a Book the user already closed."""

    def __init__(self, workspace):
        super().__init__()
        self._workspace = workspace
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def closeEvent(self, event):
        try:
            proceed = self._workspace._detach_book(self)
        except Exception:
            proceed = True
        if proceed:
            super().closeEvent(event)
        else:
            event.ignore()


class MdiWorkspace(QWidget):
    """OriginPro-style MDI workspace exposing a TabManager-compatible surface.

    See module docstring for the chosen adapter shape (a) and the full API.
    """

    # --- TabManager-compatible signals --------------------------------------
    currentChanged = Signal(int)
    tabCreated = Signal(str)
    tabRemoved = Signal(str)
    renderStatusChanged = Signal(str)

    # --- Project Explorer helper signals ------------------------------------
    subWindowAdded = Signal(str, str)    # (kind, title)
    subWindowRemoved = Signal(str, str)  # (kind, title)
    subWindowRenamed = Signal(str, str)  # (kind, title)
    # Origin multi-book: emitted when a Book sub-window becomes active so the
    # MainWindow can switch its working DataFrame to that Book's data.
    bookActivated = Signal(str)          # (title)
    # Emitted after a Book sub-window is closed and removed from the registry so
    # the MainWindow can re-point its active DataFrame before the widget dies.
    bookClosed = Signal(str)             # (title)
    # Emitted instead when the user tries to close the last remaining Book (the
    # app is sheet-first and always needs at least one worksheet).
    bookCloseBlocked = Signal(str)       # (title)

    def __init__(self, parent=None, *, start_with_graph: bool = True):
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
        # Last graph selected by the user. When a Book has focus, graph-scoped
        # toolbar commands still need a deterministic graph target.
        self._current_graph_tab_id: Optional[str] = None
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
        # MDI title bars intentionally inherit Highlight/HighlightedText from
        # QApplication so the selected theme color reaches every sub-window.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.mdi.subWindowActivated.connect(self._on_sub_window_activated)

        # Standalone workspace keeps TabManager compatibility by default; the
        # main app passes start_with_graph=False for a clean worksheet-first
        # startup and creates graphs lazily when the user plots.
        if start_with_graph:
            self.add_tab("Graph 1")

    def apply_application_theme(self) -> None:
        """Sync QMdiArea's viewport brush, which QSS alone does not repaint."""
        app = QApplication.instance()
        if app is None or not hasattr(self, "mdi"):
            return
        color = app.palette().color(QPalette.Window)
        self.mdi.setBackground(QBrush(color))
        self.mdi.viewport().setPalette(app.palette())
        self.mdi.viewport().update()

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
        else:
            base_name = str(name).strip() or f"Graph {self._tab_counter}"
            existing = {tab.name for tab in self.tabs.values()}
            name = base_name
            suffix = 2
            while name in existing:
                name = f"{base_name} ({suffix})"
                suffix += 1
        tab_id = f"tab_{self._tab_counter}"

        graph_tab = GraphTab(tab_id, name, self)
        graph_tab.renderStatusChanged.connect(self.renderStatusChanged.emit)
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
        self._current_graph_tab_id = tab_id

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
        # _BookSubWindow syncs the registry (and re-points the active data) when
        # the user closes it via the title-bar X, and frees the widget on close.
        sub = _BookSubWindow(self)
        sub.setWidget(widget)
        sub.setWindowTitle(title)
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

    def remove_book(self, title: str | None = None, *, widget: QWidget | None = None) -> bool:
        """Remove a Book sub-window and keep the workspace registry in sync."""
        match_title = None
        match_widget = None
        match_sub = None
        for candidate_title, (candidate_widget, candidate_sub) in self._books.items():
            if (title is not None and candidate_title == title) or (
                widget is not None and candidate_widget is widget
            ):
                match_title = candidate_title
                match_widget = candidate_widget
                match_sub = candidate_sub
                break
        if match_title is None or match_sub is None:
            return False

        self._books.pop(match_title, None)
        try:
            self.mdi.removeSubWindow(match_sub)
            match_sub.hide()
            match_sub.setWidget(None)
            match_sub.deleteLater()
            if match_widget is not None:
                match_widget.deleteLater()
        except Exception:
            logger.debug("Book removal failed: %s", match_title, exc_info=True)
        try:
            self.subWindowRemoved.emit("book", match_title)
        except Exception:
            logger.debug("subWindowRemoved emit failed", exc_info=True)
        return True

    def _detach_book(self, sub) -> bool:
        """Sync registries when a Book sub-window is closed interactively.

        Blocks closing the *last* Book (the app is sheet-first and always needs a
        worksheet) and reports it via ``bookCloseBlocked``. Otherwise pops the
        Book, emits ``subWindowRemoved`` + ``bookClosed`` (so the MainWindow can
        re-point its active DataFrame while the widget is still alive) and returns
        True so the window may finish closing.
        """
        match_title = None
        for candidate_title, (_widget, candidate_sub) in self._books.items():
            if candidate_sub is sub:
                match_title = candidate_title
                break
        if match_title is None:
            return True  # not one of ours — allow the close
        if len(self._books) <= 1:
            try:
                self.bookCloseBlocked.emit(match_title)
            except Exception:
                logger.debug("bookCloseBlocked emit failed", exc_info=True)
            return False
        self._books.pop(match_title, None)
        for _sig, _args in (
            (self.subWindowRemoved, ("book", match_title)),
            (self.bookClosed, (match_title,)),
        ):
            try:
                _sig.emit(*_args)
            except Exception:
                logger.debug("signal emit failed on book close", exc_info=True)
        return True

    def remove_all_tabs(self) -> None:
        """Close every graph sub-window, emitting ``tabRemoved`` for each."""
        for tab_id in list(self._graph_subs.keys()):
            self._remove_tab_by_id(tab_id, force=True)

    def _remove_tab_by_id(self, tab_id: str, force: bool = False) -> None:
        if tab_id not in self._graph_subs:
            return
        # No last-graph guard: sheet-first means 0 graphs is a valid state, so
        # any graph (including the only one) can be discarded. ``force`` is kept
        # for API compatibility with remove_all_tabs.
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
        if self._current_graph_tab_id == tab_id:
            self._current_graph_tab_id = next(reversed(self.tabs), None) if self.tabs else None
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

        Pops the graph from the registries, emits removal signals and returns
        True so the window may close (WA_DeleteOnClose then deletes it). Unlike
        the old TabManager there is NO last-graph veto: the app is sheet-first
        (0 graphs is the startup state), so a user who plotted the wrong thing
        must be able to discard even the only graph — the next plot re-creates one.
        """
        self._graph_subs.pop(tab_id, None)
        self.tabs.pop(tab_id, None)
        if self._current_graph_tab_id == tab_id:
            self._current_graph_tab_id = next(reversed(self.tabs), None) if self.tabs else None
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
            self._current_graph_tab_id = tab_id
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

        Falls back to the last selected graph when a book window has focus.
        """
        active = self.mdi.activeSubWindow()
        if active is not None:
            for tab_id, sub in self._graph_subs.items():
                if sub is active:
                    self._current_graph_tab_id = tab_id
                    return self.tabs.get(tab_id)
        if self._current_graph_tab_id in self.tabs:
            return self.tabs[self._current_graph_tab_id]
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
                    self._current_graph_tab_id = tab_id
                    return tab_id
        if self._current_graph_tab_id in self.tabs:
            return self._current_graph_tab_id
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

    def raise_current_graph(self) -> None:
        """Bring the current graph's sub-window to the front (newest plot).

        Falls back to the most recently created graph — never the first one,
        which is what the old "raise any GraphTab" logic wrongly did (it kept
        yanking focus back to an empty Graph 1 after plotting on Graph N).
        """
        tab_id = self.get_current_tab_id()
        sub = self._graph_subs.get(tab_id) if tab_id else None
        if sub is None and self._graph_subs:
            sub = next(reversed(self._graph_subs.values()))
        if sub is not None:
            self.mdi.setActiveSubWindow(sub)

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
                self._current_graph_tab_id = _tab_id
                try:
                    self.currentChanged.emit(self.currentIndex())
                except Exception:
                    logger.debug("currentChanged emit failed", exc_info=True)
                return
        # A Book became active → tell listeners which one (Origin data switch).
        for title, (_w, bsub) in self._books.items():
            if bsub is sub:
                try:
                    self.bookActivated.emit(bsub.windowTitle() or title)
                except Exception:
                    logger.debug("bookActivated emit failed", exc_info=True)
                return

    def book_widget(self, title: str) -> Optional[QWidget]:
        """Return the widget hosted by the Book titled ``title`` (or None).

        Looks up by live sub-window title first (covers renames), then by the
        registry key the Book was created under.
        """
        for key, (widget, bsub) in self._books.items():
            if bsub.windowTitle() == title or key == title:
                return widget
        return None

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
            render_info = None
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
                        for artist in artists:
                            artist._sciplotter_x_values = list(x_vals)
                            artist._sciplotter_y_values = list(y_vals)
                    elif style == "scatter":
                        artists, render_info = draw_scatter_series(
                            ax, x_vals, y_vals, label=auto_label, **local_kwargs
                        )
                    elif style == "bar":
                        artists, render_info = draw_bar_series(
                            ax, x_vals, y_vals, label=auto_label, **local_kwargs
                        )
                    else:
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                ax.relim()
                ax.autoscale_view()
                if style == "line" and artists:
                    render_info = apply_line_lod(
                        ax, artists[0], pixel_width=canvas_pixel_width(ax)
                    )
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
                if render_info is not None:
                    layer_meta["render"] = dict(render_info)
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
            render_info = None
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
                        for artist in artists:
                            artist._sciplotter_x_values = list(x_vals)
                            artist._sciplotter_y_values = list(y_vals)
                    elif style == "scatter":
                        artists, render_info = draw_scatter_series(
                            ax, x_vals, y_vals, label=auto_label, **local_kwargs
                        )
                    elif style == "bar":
                        artists, render_info = draw_bar_series(
                            ax, x_vals, y_vals, label=auto_label, **local_kwargs
                        )
                    else:
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                ax.relim()
                ax.autoscale_view()
                if style == "line" and artists:
                    render_info = apply_line_lod(
                        ax, artists[0], pixel_width=canvas_pixel_width(ax)
                    )
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
                # Defer the render: schedule a redraw instead of forcing a full
                # figure render here. The plot mixin (_update_tabs_after_plot)
                # renders once at the end, so a blocking draw here plus tight_layout
                # meant every plot rendered the figure 2–3× (the "laggy" slowdown).
                try:
                    tab.canvas.draw_idle()
                except Exception:
                    pass
                layer_meta = dict(meta or {})
                layer_meta.setdefault("style", style)
                layer_meta.setdefault("label", auto_label)
                if render_info is not None:
                    layer_meta["render"] = dict(render_info)
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
