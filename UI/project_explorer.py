"""OriginPro-style Project Explorer for SciPlotter.

This module provides :class:`ProjectExplorer`, a ``QDockWidget`` that lists every
*open* window in the MDI project (Books and Graphs) as a tree and lets the user
**manage** them — activate, rename, or close — the way Origin's left-hand Project
Explorer does. Double-click (or Enter) activates a window; right-click opens a
context menu. The main shell parks it inside ``SidePanelTabs`` instead of showing
it as a native Qt dock.

Sync
----
It stays in sync with :class:`UI.mdi_workspace.MdiWorkspace` by connecting to its
``subWindowAdded`` / ``subWindowRemoved`` / ``subWindowRenamed`` signals *and* the
underlying ``QMdiArea.subWindowActivated`` signal, then rebuilding from
``all_windows()``. Closed windows that the workspace only *hides* (Book
sub-windows keep ``WA_DeleteOnClose == False``) are filtered out by visibility so
the tree never shows a window the user already closed. The tree also rebuilds
whenever the panel is shown and can be refreshed on demand via :meth:`refresh`.

Public API
----------
- ``ProjectExplorer(parent=None, workspace=None)``
- ``set_workspace(mdi_workspace)``
- ``refresh()``
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QInputDialog,
    QMenu,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
)

logger = logging.getLogger(__name__)


# Dark styling scoped to this dock so it reads as Origin's left panel while
# staying consistent with dark_modern.qss / shell.qss (bg #1e2126,
# surface #23272e, border #3a3f44, accent #4F9CF9, text #e6e6e6, muted #aab0b6).
_EXPLORER_STYLESHEET = """
#ProjectExplorer {
    background-color: #1e2126;
}
#ProjectExplorerTree {
    background-color: #1e2126;
    border: none;
    outline: 0;
    padding: 2px;
}
#ProjectExplorerTree::item {
    padding: 3px 2px;
    border-radius: 4px;
}
#ProjectExplorerTree::item:hover {
    background-color: rgba(255, 255, 255, 0.05);
}
#ProjectExplorerTree::item:selected {
    background-color: rgba(79, 156, 249, 0.18);
    color: #ffffff;
}
"""

# Role used to stash the target QMdiSubWindow on each window node.
_SUB_ROLE = Qt.UserRole + 1


class ProjectExplorer(QDockWidget):
    """OriginPro-style Project Explorer tree for the project's MDI windows.

    Double-clicking (or pressing Enter on) a window node activates the matching
    ``QMdiSubWindow``; right-clicking opens Activate / Rename / Close. The tree
    rebuilds automatically as windows are added, removed, renamed, or closed.
    """

    def __init__(self, parent=None, workspace=None):
        super().__init__("Project Explorer", parent)
        self.setObjectName("ProjectExplorer")
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)

        self._workspace = None
        # Live mapping of tree item -> QMdiSubWindow for activation, plus the
        # richer per-item metadata (kind, title, sub) used by the context menu.
        self._item_to_sub: Dict[QTreeWidgetItem, object] = {}
        self._item_meta: Dict[QTreeWidgetItem, Tuple[str, str, object]] = {}
        self._recipe_items: Dict[QTreeWidgetItem, str] = {}

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("ProjectExplorerTree")
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)  # double-click activates, not toggle
        self.tree.setAnimated(True)
        self.setWidget(self.tree)
        self.setStyleSheet(_EXPLORER_STYLESHEET)

        # Activation on double-click or Enter; right-click manages the window.
        self.tree.itemDoubleClicked.connect(self._on_item_activated)
        self.tree.itemActivated.connect(self._on_item_activated)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        if workspace is not None:
            self.set_workspace(workspace)
        else:
            self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_workspace(self, mdi_workspace) -> None:
        """Bind an :class:`MdiWorkspace`, wire its signals, and refresh."""
        if self._workspace is mdi_workspace:
            self.refresh()
            return
        self._disconnect_workspace(self._workspace)
        self._workspace = mdi_workspace
        self._connect_workspace(mdi_workspace)
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the tree from the workspace's *open* windows.

        Groups windows under a root node, then two folders — Books and Graphs —
        mirroring Origin's structure. Windows the workspace only hid on close
        (``isVisible()`` is False) are skipped so the tree never lists a window
        the user already closed. Empty folders are omitted.
        """
        self.tree.clear()
        self._item_to_sub.clear()
        self._item_meta.clear()
        self._recipe_items.clear()

        root = QTreeWidgetItem(self.tree)
        root.setText(0, self._project_name())
        root.setIcon(0, self._icon(QStyle.SP_DirIcon))
        root.setFlags(root.flags() & ~Qt.ItemIsSelectable)

        windows: List[Tuple[str, str, object]] = []
        if self._workspace is not None:
            try:
                windows = list(self._workspace.all_windows())
            except Exception:
                logger.debug("all_windows() failed", exc_info=True)
                windows = []

        windows = [w for w in windows if self._is_open(w[2])]
        books = [(t, s) for kind, t, s in windows if kind == "book"]
        graphs = [(t, s) for kind, t, s in windows if kind == "graph"]

        if books:
            book_folder = QTreeWidgetItem(root)
            book_folder.setText(0, "Books")
            book_folder.setIcon(0, self._icon(QStyle.SP_DirIcon))
            book_folder.setFlags(book_folder.flags() & ~Qt.ItemIsSelectable)
            for title, sub in books:
                self._add_window_node(book_folder, "book", title, sub)

        if graphs:
            graph_folder = QTreeWidgetItem(root)
            graph_folder.setText(0, "Graphs")
            graph_folder.setIcon(0, self._icon(QStyle.SP_DirIcon))
            graph_folder.setFlags(graph_folder.flags() & ~Qt.ItemIsSelectable)
            for title, sub in graphs:
                self._add_window_node(graph_folder, "graph", title, sub)

        # Analysis Recipes are project objects even though they are not MDI
        # windows. Listing them here makes the dependency/recalculation system
        # discoverable instead of hiding it solely in a menu.
        recipes = self._recipe_summaries()
        if recipes:
            recipe_folder = QTreeWidgetItem(root)
            recipe_folder.setText(0, "Analysis Recipes")
            recipe_folder.setIcon(0, self._icon(QStyle.SP_DirIcon))
            recipe_folder.setFlags(recipe_folder.flags() & ~Qt.ItemIsSelectable)
            for recipe in recipes:
                item = QTreeWidgetItem(recipe_folder)
                name = str(recipe.get("name", "Untitled Recipe"))
                status = str(recipe.get("status", ""))
                item.setText(0, f"{name} [{status}]" if status else name)
                item.setToolTip(
                    0,
                    f"Mode: {recipe.get('mode', '')} | Source: {recipe.get('source', '')} | "
                    f"Result: {recipe.get('result', '')}\nDouble-click to manage recipes.",
                )
                item.setIcon(0, self._icon(QStyle.SP_FileDialogContentsView))
                self._recipe_items[item] = str(recipe.get("id", ""))

        self.tree.expandAll()

    # ------------------------------------------------------------------
    # Tree construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _is_open(sub) -> bool:
        """True unless the sub-window was explicitly closed/hidden.

        Uses ``isHidden()`` (the explicit hide flag) rather than ``isVisible()``:
        ``isVisible()`` is also False whenever an ancestor window isn't shown
        (e.g. headless tests), which would wrongly hide every node. ``isHidden()``
        only flips when the window itself is closed/hidden — which is exactly the
        "Book closed but registry keeps it" case we want to filter. Minimized
        windows are not hidden, so they stay listed.
        """
        if sub is None:
            return False
        is_hidden = getattr(sub, "isHidden", None)
        if not callable(is_hidden):
            return True
        try:
            return not bool(is_hidden())
        except Exception:
            return True

    def _add_window_node(self, parent, kind: str, title: str, sub) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent)
        item.setText(0, title)
        item.setToolTip(0, f"{kind.capitalize()}: {title}  (double-click to open, "
                           f"right-click to manage)")
        sp = QStyle.SP_FileDialogDetailedView if kind == "graph" else QStyle.SP_FileIcon
        item.setIcon(0, self._icon(sp))
        item.setData(0, _SUB_ROLE, None)  # keep the column populated for role reads
        self._item_to_sub[item] = sub
        self._item_meta[item] = (kind, title, sub)
        return item

    def _project_name(self) -> str:
        return "Project"

    def _recipe_summaries(self) -> list[dict]:
        owner = self.parent()
        provider = getattr(owner, "analysis_recipe_summaries", None)
        if not callable(provider):
            return []
        try:
            return list(provider())
        except Exception:
            logger.debug("recipe summaries unavailable", exc_info=True)
            return []

    def _icon(self, standard_pixmap):
        try:
            return self.style().standardIcon(standard_pixmap)
        except Exception:
            from PySide6.QtGui import QIcon

            return QIcon()

    # ------------------------------------------------------------------
    # Activation + management
    # ------------------------------------------------------------------
    def _on_item_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        if item in self._recipe_items:
            self._manage_recipes()
            return
        sub = self._item_to_sub.get(item)
        if sub is not None:
            self._activate_sub(sub)

    def _activate_sub(self, sub) -> None:
        if self._workspace is None:
            return
        try:
            if hasattr(sub, "isMinimized") and sub.isMinimized():
                sub.showNormal()
            self._workspace.mdi.setActiveSubWindow(sub)
        except Exception:
            logger.debug("activate sub-window failed", exc_info=True)

    def _on_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        meta = self._item_meta.get(item) if item is not None else None
        menu = QMenu(self.tree)
        recipe_id = self._recipe_items.get(item) if item is not None else None
        if recipe_id:
            owner = self.parent()
            runner = getattr(owner, "_start_recipe_recalculation", None)
            if callable(runner):
                menu.addAction("Run / Recalculate", lambda: runner(recipe_id, force=True))
            menu.addAction("Manage Recipes...", self._manage_recipes)
            menu.addSeparator()
        if meta is not None:
            kind, title, sub = meta
            menu.addAction("Activate", lambda: self._activate_sub(sub))
            menu.addAction("Rename…", lambda: self._rename_item(kind, title, sub))
            menu.addSeparator()
            menu.addAction("Close", lambda: self._close_item(sub))
            menu.addSeparator()
        menu.addAction("Refresh", self.refresh)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _manage_recipes(self) -> None:
        manager = getattr(self.parent(), "scientific_manage_recipes", None)
        if callable(manager):
            manager()

    def _close_item(self, sub) -> None:
        """Close a window from the Explorer — same effect as its title-bar X."""
        try:
            sub.close()
        except Exception:
            logger.debug("close sub-window failed", exc_info=True)
        # Books are only hidden on close (WA_DeleteOnClose False) and emit no
        # removal signal, so refresh explicitly to drop the closed node.
        self.refresh()

    def _rename_item(self, kind: str, title: str, sub) -> None:
        new, ok = QInputDialog.getText(
            self, f"Rename {kind.capitalize()}", "New name:", text=title
        )
        new = (new or "").strip()
        if not ok or not new or new == title:
            return
        ws = self._workspace
        if ws is None:
            return
        try:
            if kind == "graph":
                tab_id = self._graph_tab_id_for(sub)
                if tab_id is not None:
                    ws.rename_tab(tab_id, new)
                else:  # fall back to a plain title change
                    sub.setWindowTitle(new)
                    ws.subWindowRenamed.emit("graph", new)
            else:
                self._rename_book(sub, new)
        except Exception:
            logger.debug("rename window failed", exc_info=True)
        self.refresh()

    def _rename_book(self, sub, new_name: str) -> None:
        """Rename a Book window and keep the workspace registry key in sync.

        Only the window title / registry key change — the Book's ``dataset_name``
        (which the data registry is keyed by) is left untouched, so the data
        still resolves after the rename.
        """
        ws = self._workspace
        books = getattr(ws, "_books", None)
        if isinstance(books, dict):
            for key, entry in list(books.items()):
                if entry and entry[1] is sub:
                    books.pop(key, None)
                    books[new_name] = entry
                    break
        try:
            sub.setWindowTitle(new_name)
        except Exception:
            logger.debug("set book title failed", exc_info=True)
        try:
            ws.subWindowRenamed.emit("book", new_name)
        except Exception:
            logger.debug("subWindowRenamed emit failed", exc_info=True)

    def _graph_tab_id_for(self, sub) -> Optional[str]:
        graph_subs = getattr(self._workspace, "_graph_subs", {}) or {}
        for tab_id, gsub in graph_subs.items():
            if gsub is sub:
                return tab_id
        return None

    # ------------------------------------------------------------------
    # Workspace signal wiring
    # ------------------------------------------------------------------
    def _connect_workspace(self, ws) -> None:
        if ws is None:
            return
        for name in ("subWindowAdded", "subWindowRemoved", "subWindowRenamed"):
            sig = getattr(ws, name, None)
            if sig is not None:
                try:
                    sig.connect(self._on_windows_changed)
                except Exception:
                    logger.debug("connect %s failed", name, exc_info=True)
        # QMdiArea fires this when the active window changes — including when the
        # active Book/Graph is closed — which is the trigger the Book-only "hide
        # on close" path lacks. Refreshing here drops the just-closed window.
        area = getattr(ws, "mdi", None)
        area_sig = getattr(area, "subWindowActivated", None)
        if area_sig is not None:
            try:
                area_sig.connect(self._on_windows_changed)
            except Exception:
                logger.debug("connect subWindowActivated failed", exc_info=True)

    def _disconnect_workspace(self, ws) -> None:
        if ws is None:
            return
        for name in ("subWindowAdded", "subWindowRemoved", "subWindowRenamed"):
            sig = getattr(ws, name, None)
            if sig is not None:
                try:
                    sig.disconnect(self._on_windows_changed)
                except (RuntimeError, TypeError):
                    logger.debug("disconnect %s skipped", name, exc_info=True)
        area = getattr(ws, "mdi", None)
        area_sig = getattr(area, "subWindowActivated", None)
        if area_sig is not None:
            try:
                area_sig.disconnect(self._on_windows_changed)
            except (RuntimeError, TypeError):
                logger.debug("disconnect subWindowActivated skipped", exc_info=True)

    def _on_windows_changed(self, *_args) -> None:
        """Rebuild the tree whenever the set/titles/visibility of windows change."""
        self.refresh()

    def showEvent(self, event):
        """Re-scan when the panel is shown so background closes can't leave it stale."""
        try:
            self.refresh()
        except Exception:
            logger.debug("refresh on show failed", exc_info=True)
        super().showEvent(event)
