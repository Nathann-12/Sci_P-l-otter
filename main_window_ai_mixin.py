"""Wire the parked AI dock to the local assistant (ai/ package).

Inference runs on a worker QThread so a slow local model never freezes the UI.
Everything is defensive: if the ai package, Ollama, or the model is missing the
app still works and the dock simply reports that the assistant is unavailable.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class _AiWorker(QThread):
    """Runs one assistant turn off the UI thread and reports back the answer."""

    replied = Signal(str)

    def __init__(self, assistant, text: str, parent=None):
        super().__init__(parent)
        self._assistant = assistant
        self._text = text

    def run(self) -> None:  # executes on the worker thread
        try:
            result = self._assistant.ask(self._text)
            answer = getattr(result, "answer", "") or "(no reply)"
        except Exception as exc:  # never let a worker crash take down the app
            logger.debug("AI worker failed", exc_info=True)
            answer = f"AI error: {exc}"
        self.replied.emit(answer)


class MainWindowAIMixin:
    """Adds a local, tool-using AI assistant behind the parked AI dock."""

    def init_ai_assistant(self, client=None) -> bool:
        """Build the assistant and connect it to ``self.ai_dock``.

        Returns True when wiring succeeded. ``client`` can be injected for tests.
        """
        self._ai_assistant = None
        self._ai_busy = False
        self._ai_worker = None
        # Run inference inline instead of on a QThread when True (tests).
        self._ai_synchronous = False
        try:
            from ai.agent import LocalAssistant
            from ai.app_tools import build_app_registry

            if client is None:
                from ai.ollama_client import OllamaClient
                from settings import settings_manager

                ai_cfg = settings_manager.get_ai()
                if not getattr(ai_cfg, "enabled", True):
                    return False
                client = OllamaClient(model=ai_cfg.model, base_url=ai_cfg.base_url)

            self._ai_registry = build_app_registry(self)
            self._ai_assistant = LocalAssistant(self._ai_registry, client)
        except Exception:
            logger.debug("AI assistant init skipped", exc_info=True)
            return False

        dock = getattr(self, "ai_dock", None)
        if dock is not None and hasattr(dock, "message_submitted"):
            dock.message_submitted.connect(self._on_ai_message)
        return True

    # ------------------------------------------------------------------ slots
    def _on_ai_message(self, text: str) -> None:
        assistant = getattr(self, "_ai_assistant", None)
        dock = getattr(self, "ai_dock", None)
        if assistant is None or dock is None:
            return
        if getattr(self, "_ai_busy", False):
            dock.append_message("AI", "Still working on the previous request…")
            return

        self._ai_busy = True
        if getattr(self, "_ai_synchronous", False):
            try:
                answer = assistant.ask(text).answer
            except Exception as exc:
                answer = f"AI error: {exc}"
            self._on_ai_reply(answer)
            return

        dock.append_message("AI", "…")
        worker = _AiWorker(assistant, text, self)
        worker.replied.connect(self._on_ai_reply)
        worker.finished.connect(worker.deleteLater)
        self._ai_worker = worker
        worker.start()

    def _on_ai_reply(self, answer: str) -> None:
        self._ai_busy = False
        dock = getattr(self, "ai_dock", None)
        if dock is not None:
            dock.append_message("AI", answer)
