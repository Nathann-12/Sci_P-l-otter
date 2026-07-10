"""OriginPro-style Project Explorer for SciPlotter.

This module provides :class:`ProjectExplorer`, a ``QDockWidget`` that lists every
window in the MDI project (Books and Graphs) as a tree and activates a window
when its node is double-clicked (or Enter is pressed on it), just like Origin's
left-hand Project Explorer panel. The main shell parks it inside
``SidePanelTabs`` instead of showing it as a native Qt dock.

It stays in sync with the :class:`UI.mdi_workspace.MdiWorkspace` by connecting to
its ``subWindowAdded`` / ``subWindowRemoved`` / ``subWindowRenamed`` signals and
rebuilding the tree from ``all_windows()``. The tree can also be rebuilt on
demand via :meth:`refresh`.

Public API
----------
- ``ProjectExplorer(parent=None, workspace=None)`` — construct; optionally bind
  the workspace immediately.
- ``set_workspace(mdi_workspace)`` — (re)bind an :class:`MdiWorkspace`, wire its
  signals, and refresh the tree.
- ``refresh()`` — rebuild the tree from ``workspace.all_windows()``.

Styling is scoped to ``objectName == "ProjectExplorer"`` so it layers cleanly on
top of qdarktheme + the app's dark palette (bg #1e2126, surface #23272e, accent
#4F9CF9).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
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
    ``QMdiSubWindow``. The tree rebuilds automatically as windows are added,
    removed, or renamed, and can be refreshed on demand via :meth:`refresh`.
    """

    def __init__(self, parent=None, workspace=None):
        super().__init__("Project Explorer", parent)
        self.setObjectName("ProjectExplorer")
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)

        self._workspace = None
        # Live mapping of tree item -> QMdiSubWindow for activation.
        self._item_to_sub: Dict[QTreeWidgetItem, object] = {}

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("ProjectExplorerTree")
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)  # double-click activates, not toggle
        self.tree.setAnimated(True)
        self.setWidget(self.tree)
        self.setStyleSheet(_EXPLORER_STYLESHEET)

        # Activation on double-click or Enter.
        self.tree.itemDoubleClicked.connect(self._on_item_activated)
        self.tree.itemActivated.connect(self._on_item_activated)

        if workspace is not None:
            self.set_workspace(workspace)
        else:
            self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_workspace(self, mdi_workspace) -> None:
        """Bind an :class:`MdiWorkspace`, wire its signals, and refresh.

        Safe to call more than once: the previous workspace's signals are
        disconnected before the new one is wired.
        """
        if self._workspace is mdi_workspace:
            self.refresh()
            return
        self._disconnect_workspace(self._workspace)
        self._workspace = mdi_workspace
        self._connect_workspace(mdi_workspace)
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the tree from the workspace's ``all_windows()``.

        Groups windows under a root node, then two folders — Books and Graphs —
        mirroring Origin's structure. Empty folders are omitted.
        """
        self.tree.clear()
        self._item_to_sub.clear()

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

        self.tree.expandAll()

    # ------------------------------------------------------------------
    # Tree construction helpers
    # ------------------------------------------------------------------
    def _add_window_node(self, parent, kind: str, title: str, sub) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent)
        item.setText(0, title)
        item.setToolTip(0, f"{kind.capitalize()}: {title}")
        sp = QStyle.SP_FileDialogDetailedView if kind == "graph" else QStyle.SP_FileIcon
        item.setIcon(0, self._icon(sp))
        item.setData(0, _SUB_ROLE, None)  # keep the column populated for role reads
        self._item_to_sub[item] = sub
        return item

    def _project_name(self) -> str:
        return "Project"

    def _icon(self, standard_pixmap):
        try:
            return self.style().standardIcon(standard_pixmap)
        except Exception:
            from PySide6.QtGui import QIcon

            return QIcon()

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------
    def _on_item_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        sub = self._item_to_sub.get(item)
        if sub is None:
            return
        self._activate_sub(sub)

    def _activate_sub(self, sub) -> None:
        if self._workspace is None:
            return
        try:
            # Restore if the sub-window is minimized so it becomes visible.
            if hasattr(sub, "isMinimized") and sub.isMinimized():
                sub.showNormal()
            self._workspace.mdi.setActiveSubWindow(sub)
        except Exception:
            logger.debug("activate sub-window failed", exc_info=True)

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

    def _disconnect_workspace(self, ws) -> None:
        if ws is None:
            return
        for name in ("subWindowAdded", "subWindowRemoved", "subWindowRenamed"):
            sig = getattr(ws, name, None)
            if sig is not None:
                try:
                    sig.disconnect(self._on_windows_changed)
                except (RuntimeError, TypeError):
                    # Not connected / already gone — harmless.
                    logger.debug("disconnect %s skipped", name, exc_info=True)

    def _on_windows_changed(self, *_args) -> None:
        """Rebuild the tree whenever the set/titles of windows change."""
        self.refresh()
