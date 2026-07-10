from __future__ import annotations

import logging
from typing import Callable, Iterable, Optional, Tuple

from PySide6.QtWidgets import QMenu, QStyle

logger = logging.getLogger(__name__)

ModuleAction = Tuple[str, Callable[[], None]]


class MainWindowModulesMixin:
    """Shared UX shell for specialty/domain modules."""

    def ensure_modules_gallery(self):
        panel = getattr(self, "modules_panel", None)
        if panel is not None:
            return panel

        from UI.modules_panel import ModulesPanel

        panel = ModulesPanel(self)
        self.modules_panel = panel
        self._module_pins = self._load_module_pins()
        panel.pin_changed.connect(self._save_module_pin)
        panel.close_requested.connect(self.shell.hide_activity_context)
        try:
            icon = self._icon("modules", QStyle.StandardPixmap.SP_FileDialogDetailedView)
        except Exception:
            icon = None
        self.shell.register_context("modules", "Modules", panel, icon=icon)
        return panel

    def modules_menu(self) -> QMenu:
        menu = getattr(self, "_modules_menu", None)
        if menu is not None:
            return menu

        for action in self.menuBar().actions():
            existing = action.menu()
            if existing is not None and existing.title().replace("&", "") == "Modules":
                self._modules_menu = existing
                return existing

        menu = QMenu("&Modules", self)
        self.menuBar().addMenu(menu)
        self._modules_menu = menu
        open_action = menu.addAction("Open Modules Gallery")
        open_action.triggered.connect(lambda: self.show_module_gallery())
        menu.addSeparator()
        return menu

    def register_specialty_module(
        self,
        *,
        module_id: str,
        title: str,
        subtitle: str,
        panel,
        icon_key: str,
        fallback_icon: QStyle.StandardPixmap,
        actions: Iterable[ModuleAction],
    ) -> QMenu:
        gallery = self.ensure_modules_gallery()
        action_items = tuple(actions)
        try:
            icon = self._icon(icon_key, fallback_icon)
        except Exception:
            icon = None
        gallery.add_module(
            module_id,
            title,
            subtitle,
            panel,
            icon=icon,
            search_terms=[label for label, _callback in action_items],
        )
        if module_id in getattr(self, "_module_pins", set()):
            gallery.set_module_pinned(module_id, True)

        menu = self.modules_menu()
        submenu = getattr(self, f"_{module_id}_menu", None)
        if submenu is None:
            submenu = QMenu(title, menu)
            setattr(self, f"_{module_id}_menu", submenu)
            menu.addMenu(submenu)
        else:
            submenu.clear()

        open_action = submenu.addAction(f"Open {title} Panel")
        open_action.triggered.connect(lambda _checked=False, mid=module_id: self.show_module_gallery(mid))
        submenu.addSeparator()
        for label, callback in action_items:
            submenu.addAction(label).triggered.connect(callback)
        return submenu

    def show_module_gallery(self, module_id: Optional[str] = None) -> None:
        panel = self.ensure_modules_gallery()
        if module_id:
            panel.show_module(module_id)
        self.shell.show_activity_context("modules")

    def _load_module_pins(self) -> set[str]:
        try:
            settings = getattr(self, "settings", None)
            raw = settings.value("modules/pinned", []) if settings is not None else []
        except Exception:
            return set()
        if isinstance(raw, str):
            return {item for item in raw.split(",") if item}
        try:
            return {str(item) for item in raw if str(item)}
        except TypeError:
            return set()

    def _save_module_pin(self, module_id: str, pinned: bool) -> None:
        pins = set(getattr(self, "_module_pins", set()))
        if pinned:
            pins.add(module_id)
        else:
            pins.discard(module_id)
        self._module_pins = pins
        try:
            settings = getattr(self, "settings", None)
            if settings is not None:
                settings.setValue("modules/pinned", sorted(pins))
        except Exception:
            logger.debug("module pin persistence skipped", exc_info=True)
