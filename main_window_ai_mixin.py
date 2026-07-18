"""Wire the parked AI dock to the local assistant (ai/ package).

Inference runs on a background worker so a slow local model never freezes the UI.
Everything is defensive: if the ai package, Ollama, or the model is missing the
app still works and the dock simply reports that the assistant is unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from threading import Event, Lock, Thread, current_thread
from typing import Any, Callable, Dict

from PySide6.QtCore import QMetaObject, QObject, QThread, Qt, Signal, Slot

logger = logging.getLogger(__name__)


@dataclass
class _GuiToolCall:
    handler: Callable[[Dict[str, Any]], Any]
    arguments: Dict[str, Any]
    result: Any = None
    error: BaseException | None = None


class _GuiToolExecutor(QObject):
    """Synchronously execute an AI tool handler on the Qt GUI thread.

    The AI worker runs on a background thread but tools may touch Qt/Matplotlib,
    which is only safe on the GUI thread. We hop threads with a *blocking queued*
    ``invokeMethod`` call and keep the pending call on ``self`` instead of sending
    a Python object across a queued signal. Only one AI turn runs at a time
    (guarded by ``_ai_busy``), so a single ``_pending`` slot is enough.

    This executor must be owned by the QApplication, not a MainWindow — see
    ``_shared_gui_tool_executor`` for why per-window ownership corrupted the heap.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = Lock()
        self._pending: _GuiToolCall | None = None

    def __call__(self, handler, arguments):
        if QThread.currentThread() == self.thread():
            return handler(arguments)
        call = _GuiToolCall(handler=handler, arguments=dict(arguments or {}))
        with self._lock:
            self._pending = call
            # BlockingQueuedConnection runs _run_pending on the GUI thread and
            # blocks this worker thread until it returns. Safe because the guard
            # above proves we are not already on the GUI thread (no self-deadlock).
            ok = QMetaObject.invokeMethod(
                self, "_run_pending", Qt.BlockingQueuedConnection
            )
            self._pending = None
        if not ok:
            raise RuntimeError("could not marshal the AI action to the GUI thread")
        if call.error is not None:
            raise call.error
        return call.result

    @Slot()
    def _run_pending(self) -> None:
        call = self._pending
        if call is None:
            return
        try:
            call.result = call.handler(call.arguments)
        except BaseException as exc:
            call.error = exc


def _shared_gui_tool_executor() -> "_GuiToolExecutor | None":
    """Return one process-wide executor owned by the QApplication.

    A per-window executor was created as a *child of the MainWindow*; when the
    test harness force-deletes windows via ``sendPostedEvents(DeferredDelete)``
    the C++ object was freed while the mixin still held a Python reference,
    double-freeing at GC and corrupting the heap (a wandering segfault at the
    next Qt allocation). Parenting a single executor to the long-lived
    QApplication removes that per-window create/destroy churn entirely.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return _GuiToolExecutor()
    executor = app.findChild(_GuiToolExecutor, "sciplotter_ai_executor")
    if executor is None:
        executor = _GuiToolExecutor(app)
        executor.setObjectName("sciplotter_ai_executor")
    return executor


class _AiWorker(QObject):
    """Runs one assistant turn on a daemon thread and reports back through Qt."""

    replied = Signal(object)
    finished = Signal()
    progress = Signal(str)

    def __init__(self, assistant, text: str, parent=None):
        super().__init__(parent)
        self._assistant = assistant
        self._text = text
        self._cancelled = Event()
        self._thread = None

    def start(self) -> None:
        self._thread = Thread(target=self._run, name="SciPlotterAI", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def join(self, timeout: float = 1.0) -> None:
        thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=max(0.0, float(timeout)))

    def _run(self) -> None:
        try:
            result = self._assistant.ask(
                self._text,
                on_tool_start=lambda name, _arguments: self.progress.emit(name),
                cancelled=self._cancelled.is_set,
            )
        except Exception as exc:  # never let a worker crash take down the app
            logger.debug("AI worker failed", exc_info=True)
            from ai.agent import AssistantResult

            result = AssistantResult(answer=f"AI error: {exc}", error=str(exc))
        if not self._cancelled.is_set():
            try:
                self.replied.emit(result)
            except RuntimeError:
                # The owning window may have closed between the cancellation
                # check and signal delivery.
                return
        try:
            self.finished.emit()
        except RuntimeError:
            return


class MainWindowAIMixin:
    """Adds a local, tool-using AI assistant behind the parked AI dock."""

    def init_ai_assistant(self, client=None) -> bool:
        """Build the assistant and connect it to ``self.ai_dock``.

        Returns True when wiring succeeded. ``client`` can be injected for tests.
        """
        self._ai_assistant = None
        self._ai_busy = False
        self._ai_worker = None
        self._ai_tool_executor = None
        # Run inference inline instead of on a QThread when True (tests).
        self._ai_synchronous = False
        dock = getattr(self, "ai_dock", None)
        if (
            dock is not None
            and hasattr(dock, "manage_models_requested")
            and not getattr(self, "_ai_models_connected", False)
        ):
            dock.manage_models_requested.connect(self._open_ai_model_manager)
            self._ai_models_connected = True
        try:
            from ai.agent import LocalAssistant
            from ai.app_tools import build_app_registry

            if client is None:
                from settings import settings_manager

                ai_cfg = settings_manager.get_ai()
                if not getattr(ai_cfg, "enabled", True):
                    if dock is not None and hasattr(dock, "set_available"):
                        dock.set_available(False, "Disabled in Settings")
                    return False
                client = self._build_ai_client(ai_cfg)

            self._ai_registry = build_app_registry(self)
            self._ai_tool_executor = _shared_gui_tool_executor()
            self._ai_registry.set_executor(self._ai_tool_executor)
            self._ai_registry.set_approval_callback(self._approve_ai_tool)
            self._ai_assistant = LocalAssistant(self._ai_registry, client)
        except Exception as exc:
            logger.debug("AI assistant init skipped", exc_info=True)
            if dock is not None and hasattr(dock, "set_available"):
                readiness = getattr(exc, "readiness", None)
                detail = str(getattr(readiness, "detail", "") or "Assistant unavailable")
                dock.set_available(False, detail)
            return False

        if dock is not None and hasattr(dock, "message_submitted"):
            if not getattr(self, "_ai_dock_connected", False):
                dock.message_submitted.connect(self._on_ai_message)
                self._ai_dock_connected = True
            if (
                hasattr(dock, "cancel_requested")
                and not getattr(self, "_ai_cancel_connected", False)
            ):
                dock.cancel_requested.connect(self._cancel_ai_request)
                self._ai_cancel_connected = True
            if (
                hasattr(dock, "conversation_cleared")
                and not getattr(self, "_ai_clear_connected", False)
            ):
                dock.conversation_cleared.connect(self._clear_ai_conversation)
                self._ai_clear_connected = True
            if hasattr(dock, "set_model"):
                dock.set_model(getattr(client, "model", "Local tools"))
            if hasattr(dock, "set_available"):
                dock.set_available(True)
        self._refresh_ai_context()
        return True

    def _build_ai_client(self, ai_cfg):
        """Return a usable local client or raise a setup error.

        ``auto`` keeps the legacy Ollama fallback, but only when the configured
        model is actually present.  This prevents a clean install from showing
        a misleading Ready state and failing on the first prompt.
        """
        backend = str(getattr(ai_cfg, "backend", "auto") or "auto").casefold()
        pack_id = str(getattr(ai_cfg, "pack_id", "qwen3-0.6b-q8") or "")
        bundled_readiness = None
        if backend in {"auto", "bundled"}:
            from ai.llama_cpp_client import LlamaCppClient
            from ai.model_catalog import get_model_pack
            from ai.model_manager import ModelManager
            from ai.readiness import AISetupRequired, inspect_bundled_ai

            manager = ModelManager()
            bundled_readiness = inspect_bundled_ai(
                pack_id,
                getattr(ai_cfg, "runtime_path", ""),
                manager=manager,
            )
            if bundled_readiness.ready:
                pack = get_model_pack(pack_id)
                return LlamaCppClient(
                    bundled_readiness.model_path,
                    runtime_path=bundled_readiness.runtime_path,
                    model=(
                        pack.display_name
                        if getattr(pack, "release_status", "preview") == "release"
                        else f"{pack.display_name} · Preview"
                    ),
                    context_size=getattr(ai_cfg, "context_size", pack.context_size),
                )
            if backend == "bundled":
                raise AISetupRequired(bundled_readiness)

        from ai.ollama_client import OllamaClient
        from ai.readiness import AIReadiness, AISetupRequired

        client = OllamaClient(model=ai_cfg.model, base_url=ai_cfg.base_url)
        installed = client.list_models(timeout=1.0)
        wanted = str(ai_cfg.model or "").strip().casefold()
        aliases = {str(name).strip().casefold() for name in installed}
        if wanted in aliases or (":" not in wanted and f"{wanted}:latest" in aliases):
            return client

        if backend == "auto" and bundled_readiness is not None:
            raise AISetupRequired(bundled_readiness)
        detail = (
            f"Install the local Ollama model '{ai_cfg.model}' before using SciPlotter AI."
            if installed
            else "Start Ollama and install the selected local model before using SciPlotter AI."
        )
        raise AISetupRequired(
            AIReadiness(
                state="ollama_unavailable",
                ready=False,
                detail=detail,
                pack_id="",
            )
        )

    def _approve_ai_tool(self, tool, arguments: Dict[str, Any]) -> bool:
        """Ask on the GUI thread before the model mutates data or hardware."""
        executor = getattr(self, "_ai_tool_executor", None)
        if executor is None:
            return False

        def show_confirmation(_unused):
            from PySide6.QtWidgets import QMessageBox

            details = "\n".join(
                f"• {key}: {value}" for key, value in (arguments or {}).items()
            ) or "• No additional parameters"
            book_getter = getattr(self, "_active_book_label", None)
            book = book_getter() if callable(book_getter) else ""
            risk_label = "hardware/device" if tool.risk == "device" else "active data"
            answer = QMessageBox.question(
                self,
                "Confirm AI action",
                f"SciPlotter AI wants to run: {tool.name}\n"
                f"Active Book: {book or '(none)'}\n"
                f"This can change {risk_label}.\n\nResolved inputs:\n{details}\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return answer == QMessageBox.Yes

        return bool(executor(show_confirmation, {}))

    def _clear_ai_conversation(self) -> None:
        assistant = getattr(self, "_ai_assistant", None)
        clear = getattr(assistant, "clear_pending_request", None)
        if callable(clear):
            clear()

    def _cancel_ai_request(self) -> None:
        worker = getattr(self, "_ai_worker", None)
        if worker is None or not getattr(self, "_ai_busy", False):
            return
        worker.cancel()
        assistant = getattr(self, "_ai_assistant", None)
        client = getattr(assistant, "client", None)
        cancel = getattr(client, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception:
                logger.debug("Could not interrupt local AI runtime", exc_info=True)
        dock = getattr(self, "ai_dock", None)
        if dock is not None and hasattr(dock, "set_busy"):
            dock.set_busy(True, "Cancelling request")

    def _open_ai_model_manager(self) -> None:
        """Open the verified model installer and activate the chosen pack."""
        try:
            from PySide6.QtWidgets import QDialog
            from dialogs.ai_model_manager_dialog import AiModelManagerDialog
            from settings import settings_manager

            ai_cfg = settings_manager.get_ai()
            before = str(getattr(ai_cfg, "pack_id", "") or "")
            dialog = AiModelManagerDialog(
                self,
                active_pack_id=before,
                runtime_path=getattr(ai_cfg, "runtime_path", ""),
            )
            accepted = dialog.exec() == QDialog.Accepted
            selected = dialog.active_pack_id
            if not accepted or not selected:
                return
            settings_manager.update_ai(
                backend="bundled",
                pack_id=selected,
                runtime_path=dialog.runtime_path,
                enabled=True,
            )
            settings_manager.save()
            assistant = getattr(self, "_ai_assistant", None)
            old_client = getattr(assistant, "client", None)
            close = getattr(old_client, "close", None)
            if callable(close):
                close()
            self.init_ai_assistant()
        except Exception:
            logger.debug("Could not open AI model manager", exc_info=True)
            dock = getattr(self, "ai_dock", None)
            if dock is not None and hasattr(dock, "set_available"):
                dock.set_available(False, "Local model needs setup")

    def _refresh_ai_context(self) -> None:
        dock = getattr(self, "ai_dock", None)
        if dock is None or not hasattr(dock, "set_context"):
            return
        df_getter = getattr(self, "_resolve_active_dataframe", None)
        df = df_getter() if callable(df_getter) else getattr(self, "_df", None)
        book_getter = getattr(self, "_active_book_label", None)
        book = book_getter() if callable(book_getter) else ""
        rows = len(df) if df is not None else 0
        columns = len(getattr(df, "columns", [])) if df is not None else 0
        column_names = list(getattr(df, "columns", [])) if df is not None else []
        dock.set_context(book or "", rows, columns, column_names)

    # ------------------------------------------------------------------ slots
    def _on_ai_message(self, text: str) -> None:
        assistant = getattr(self, "_ai_assistant", None)
        dock = getattr(self, "ai_dock", None)
        if assistant is None or dock is None:
            if dock is not None:
                dock.append_message("AI", "The assistant is disabled or unavailable.")
            return
        if getattr(self, "_ai_busy", False):
            dock.append_message("AI", "Still working on the previous request.")
            return

        self._ai_busy = True
        self._refresh_ai_context()
        if hasattr(dock, "set_busy"):
            dock.set_busy(True, "Understanding request")
        if getattr(self, "_ai_synchronous", False):
            try:
                result = assistant.ask(
                    text,
                    on_tool_start=lambda name, _arguments: self._on_ai_progress(name),
                )
            except Exception as exc:
                from ai.agent import AssistantResult

                result = AssistantResult(answer=f"AI error: {exc}", error=str(exc))
            self._on_ai_reply(result)
            return

        parent = self if isinstance(self, QObject) else None
        worker = _AiWorker(assistant, text, parent)
        worker.progress.connect(self._on_ai_progress, Qt.QueuedConnection)
        worker.replied.connect(self._on_ai_reply, Qt.QueuedConnection)
        worker.finished.connect(self._on_ai_worker_finished, Qt.QueuedConnection)
        self._ai_worker = worker
        worker.start()

    def _on_ai_progress(self, tool_name: str) -> None:
        dock = getattr(self, "ai_dock", None)
        if dock is None or not hasattr(dock, "set_busy"):
            return
        labels = {
            "plot_columns": "Creating graph",
            "plot_chart": "Creating chart",
            "summarize_data": "Analyzing active data",
            "describe_data": "Describing data",
            "fit_curve": "Fitting curve",
            "gas_live_control": "Controlling gas live acquisition",
            "detect_peaks": "Finding peaks",
            "run_fft": "Running FFT",
            "open_file": "Opening file",
        }
        status = labels.get(str(tool_name), str(tool_name).replace("_", " ").title())
        dock.set_busy(True, status)

    def _on_ai_reply(self, result) -> None:
        self._ai_busy = False
        dock = getattr(self, "ai_dock", None)
        if dock is not None:
            if hasattr(dock, "complete_request"):
                dock.complete_request(result)
            else:
                answer = getattr(result, "answer", result) or "(no reply)"
                dock.append_message("AI", str(answer))
        self._refresh_ai_context()

    def _on_ai_worker_finished(self) -> None:
        worker = self._ai_worker
        cancelled = bool(worker is not None and worker.cancelled)
        if worker is not None:
            worker.join()
            worker.deleteLater()
        self._ai_worker = None
        if cancelled:
            self._ai_busy = False
            dock = getattr(self, "ai_dock", None)
            if dock is not None:
                if hasattr(dock, "set_busy"):
                    dock.set_busy(False, "Cancelled")
                if hasattr(dock, "append_message"):
                    dock.append_message(
                        "AI",
                        "Cancelled. An action that already started may have "
                        "completed; check the active Book or Operation Log.",
                    )

    def closeEvent(self, event) -> None:
        worker = getattr(self, "_ai_worker", None)
        if worker is not None:
            worker.cancel()
            self._ai_worker = None
        self._ai_busy = False
        assistant = getattr(self, "_ai_assistant", None)
        client = getattr(assistant, "client", None)
        close = getattr(client, "close", None)
        if callable(close):
            close()
        super().closeEvent(event)
