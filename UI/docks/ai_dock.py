from __future__ import annotations

import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class AiAssistantDock(QWidget):
    """Compact command workspace for the local tool-using assistant."""

    message_submitted = Signal(str)
    cancel_requested = Signal()
    conversation_cleared = Signal()
    manage_models_requested = Signal()

    QUICK_ACTIONS = (
        ("Plot line", "Plot the active data as a line graph."),
        ("Scatter", "Plot the active data as a scatter graph."),
        ("Analyze", "Analyze the active data."),
        ("Find peaks", "Find peaks in the active Y column."),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AiAssistantDock")
        self._available = True
        self._busy = False
        self._has_data = False
        self._last_prompt = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(9, 9, 9, 9)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.title_label = QLabel("SciPlotter AI", self)
        self.title_label.setObjectName("AiTitle")
        self.model_label = QLabel("Local tools", self)
        self.model_label.setObjectName("AiModelLabel")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.model_label)
        header.addLayout(title_box, 1)
        self.models_button = QToolButton(self)
        self.models_button.setObjectName("AiModelsButton")
        self.models_button.setText("Models")
        self.models_button.setToolTip("Install or switch the private local AI model")
        header.addWidget(self.models_button)
        self.clear_button = QToolButton(self)
        self.clear_button.setObjectName("AiClearButton")
        self.clear_button.setText("Clear")
        self.clear_button.setToolTip("Clear this conversation")
        header.addWidget(self.clear_button)
        root.addLayout(header)

        self.context_frame = QFrame(self)
        self.context_frame.setObjectName("AiContextCard")
        context_layout = QVBoxLayout(self.context_frame)
        context_layout.setContentsMargins(9, 7, 9, 7)
        context_layout.setSpacing(1)
        self.context_label = QLabel("No active data", self.context_frame)
        self.context_label.setObjectName("AiContextTitle")
        self.context_meta = QLabel("Open a file or activate a Book", self.context_frame)
        self.context_meta.setObjectName("AiContextMeta")
        self.context_columns = QLabel(self.context_frame)
        self.context_columns.setObjectName("AiContextColumns")
        self.context_columns.setWordWrap(True)
        self.context_columns.hide()
        context_layout.addWidget(self.context_label)
        context_layout.addWidget(self.context_meta)
        context_layout.addWidget(self.context_columns)
        root.addWidget(self.context_frame)

        quick_label = QLabel("QUICK ACTIONS", self)
        quick_label.setObjectName("AiSectionLabel")
        root.addWidget(quick_label)
        quick_grid = QGridLayout()
        quick_grid.setContentsMargins(0, 0, 0, 0)
        quick_grid.setHorizontalSpacing(5)
        quick_grid.setVerticalSpacing(5)
        self.quick_buttons = []
        for index, (label, prompt) in enumerate(self.QUICK_ACTIONS):
            button = QPushButton(label, self)
            button.setObjectName("AiQuickAction")
            button.setToolTip(prompt)
            button.clicked.connect(
                lambda _checked=False, text=prompt: self._submit_text(text)
            )
            quick_grid.addWidget(button, index // 2, index % 2)
            self.quick_buttons.append(button)
        root.addLayout(quick_grid)

        self.content_stack = QStackedWidget(self)
        self.content_stack.setObjectName("AiContentStack")
        empty_page = QWidget(self.content_stack)
        empty_page.setObjectName("AiEmptyState")
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(10, 12, 10, 12)
        empty_layout.setSpacing(5)
        empty_layout.addStretch(1)
        empty_title = QLabel("Ask with plain language", empty_page)
        empty_title.setObjectName("AiEmptyTitle")
        empty_title.setWordWrap(True)
        empty_layout.addWidget(empty_title)
        self.empty_copy = QLabel(
            'Try: "plot voltage vs time as scatter"\n'
            'ไทย: "พล็อต voltage เทียบ time แบบจุด"',
            empty_page,
        )
        self.empty_copy.setObjectName("AiEmptyCopy")
        self.empty_copy.setWordWrap(True)
        empty_layout.addWidget(self.empty_copy)
        empty_layout.addStretch(1)

        self.transcript = QTextEdit(self.content_stack)
        self.transcript.setObjectName("AiTranscript")
        self.transcript.setReadOnly(True)
        self.transcript.setMinimumHeight(80)
        self.content_stack.addWidget(empty_page)
        self.content_stack.addWidget(self.transcript)
        self.content_stack.setCurrentIndex(0)
        root.addWidget(self.content_stack, 1)

        self.action_label = QLabel(self)
        self.action_label.setObjectName("AiActionTrace")
        self.action_label.setWordWrap(True)
        self.action_label.hide()
        root.addWidget(self.action_label)

        status_row = QHBoxLayout()
        status_row.setSpacing(5)
        self.status_label = QLabel("Ready", self)
        self.status_label.setObjectName("AiStatusLabel")
        status_row.addWidget(self.status_label, 1)
        self.retry_button = QToolButton(self)
        self.retry_button.setObjectName("AiRetryButton")
        self.retry_button.setText("Retry")
        self.retry_button.hide()
        status_row.addWidget(self.retry_button)
        root.addLayout(status_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(5)
        self.input_edit = QLineEdit(self)
        self.input_edit.setObjectName("AiInput")
        self.input_edit.setPlaceholderText("Ask or command the active data...")
        self.input_edit.setClearButtonEnabled(True)
        input_row.addWidget(self.input_edit, 1)
        self.send_button = QPushButton("Run", self)
        self.send_button.setObjectName("AiSendButton")
        self.send_button.setToolTip("Run command (Enter)")
        input_row.addWidget(self.send_button)
        root.addLayout(input_row)

        self.send_button.clicked.connect(self._run_or_cancel)
        self.input_edit.returnPressed.connect(self._submit)
        self.clear_button.clicked.connect(self.clear)
        self.retry_button.clicked.connect(self._retry)
        self.models_button.clicked.connect(self.manage_models_requested)
        self._sync_enabled_state()

    def _submit(self) -> None:
        self._submit_text(self.input_edit.text())

    def _run_or_cancel(self) -> None:
        if self._busy:
            self.cancel_requested.emit()
        else:
            self._submit()

    def _submit_text(self, text: str) -> None:
        prompt = str(text or "").strip()
        if not prompt or self._busy or not self._available:
            return
        self._last_prompt = prompt
        self.append_message("You", prompt)
        self.input_edit.clear()
        self.retry_button.hide()
        self.message_submitted.emit(prompt)

    def _retry(self) -> None:
        if self._last_prompt:
            self._submit_text(self._last_prompt)

    def append_message(self, sender: str, text: str) -> None:
        self.content_stack.setCurrentIndex(1)
        self.transcript.append(f"{sender}: {str(text or '').strip()}")

    def transcript_text(self) -> str:
        return self.transcript.toPlainText()

    def clear(self) -> None:
        self.transcript.clear()
        self.content_stack.setCurrentIndex(0)
        self.action_label.clear()
        self.action_label.hide()
        self.retry_button.hide()
        self.status_label.setText("Ready" if self._available else "Unavailable")
        self.conversation_cleared.emit()

    def set_model(self, model: str) -> None:
        model = str(model or "Local tools").strip()
        self.model_label.setText(f"Local · {model}")
        self.model_label.setToolTip(model)

    def set_context(
        self,
        book: str,
        rows: int,
        columns: int,
        column_names=None,
    ) -> None:
        rows = max(0, int(rows or 0))
        columns = max(0, int(columns or 0))
        names = [str(name) for name in (column_names or []) if str(name)]
        self._has_data = rows > 0 and columns > 0
        if self._has_data:
            self.context_label.setText(book or "Active Book")
            self.context_meta.setText(f"{rows:,} rows · {columns} columns · ready to plot")
            visible_names = names[:4]
            suffix = f" · +{len(names) - 4}" if len(names) > 4 else ""
            self.context_columns.setText(" · ".join(visible_names) + suffix)
            self.context_columns.setToolTip(", ".join(names))
            self.context_columns.setVisible(bool(names))
            if len(names) >= 2:
                example = f"plot {names[1]} vs {names[0]} as scatter"
                self.empty_copy.setText(
                    f'Try: "{example}"\n'
                    f'ไทย: "พล็อต {names[1]} เทียบ {names[0]} แบบจุด"'
                )
                self.input_edit.setPlaceholderText(example)
            else:
                self.empty_copy.setText(
                    'Try: "plot voltage vs time as scatter"\n'
                    'ไทย: "พล็อต voltage เทียบ time แบบจุด"'
                )
                self.input_edit.setPlaceholderText("Ask or command the active data...")
        else:
            self.context_label.setText(book or "No active data")
            self.context_meta.setText("Open a file or activate a Book")
            self.context_columns.clear()
            self.context_columns.hide()
            self.empty_copy.setText(
                'Try: "plot voltage vs time as scatter"\n'
                'ไทย: "พล็อต voltage เทียบ time แบบจุด"'
            )
            self.input_edit.setPlaceholderText("Ask or command the active data...")
        self._sync_enabled_state()

    def set_available(self, available: bool, detail: str = "") -> None:
        self._available = bool(available)
        if self._available:
            self.status_label.setText("Ready")
        else:
            self.status_label.setText(detail or "Unavailable")
        self._sync_enabled_state()

    def set_busy(self, busy: bool, status: str = "") -> None:
        self._busy = bool(busy)
        if self._busy:
            self.status_label.setText(status or "Working")
            self.send_button.setText("Cancel")
            self.send_button.setToolTip("Cancel the current local AI request")
        else:
            self.send_button.setText("Run")
            self.send_button.setToolTip("Run command (Enter)")
            if self._available:
                self.status_label.setText(status or "Ready")
        self._sync_enabled_state()

    def complete_request(self, result) -> None:
        answer = str(getattr(result, "answer", result) or "(no reply)")
        trace = list(getattr(result, "trace", []) or [])
        error = str(getattr(result, "error", "") or "")
        needs_input = bool(getattr(result, "needs_input", False))
        cancelled = bool(getattr(result, "cancelled", False))
        self.set_busy(False)
        self.append_message("AI", answer)

        if trace:
            names = []
            previews = []
            tooltip_lines = []
            failed = False
            for name, arguments, observation in trace:
                if name not in names:
                    names.append(str(name))
                if arguments:
                    rendered = ", ".join(
                        f"{key}={value}" for key, value in list(arguments.items())[:4]
                    )
                    previews.append(rendered)
                tooltip_lines.append(
                    f"{name}\nArguments: "
                    f"{json.dumps(arguments or {}, ensure_ascii=False)}\n"
                    f"Result: {observation}"
                )
                folded = str(observation or "").casefold()
                failed = failed or folded.startswith(
                    ("error", "could not", "no active", "unknown", "provide ", "ไม่มีข้อมูล")
                )
            prefix = "Needs attention" if failed else "Completed"
            detail = f" · {previews[-1]}" if previews else ""
            self.action_label.setText(f"{prefix} · {' → '.join(names)}{detail}")
            self.action_label.setToolTip("\n\n".join(tooltip_lines))
            self.action_label.show()
            error = error or ("Tool action failed" if failed else "")

        if cancelled:
            self.status_label.setText("Cancelled")
            self.retry_button.hide()
        elif needs_input:
            self.status_label.setText("Needs input")
            self.retry_button.hide()
        elif error:
            self.status_label.setText("Needs attention")
            self.retry_button.setVisible(bool(self._last_prompt))
        else:
            self.status_label.setText("Completed")
            self.retry_button.hide()

    def _sync_enabled_state(self) -> None:
        can_submit = self._available and not self._busy
        self.input_edit.setEnabled(can_submit)
        self.send_button.setEnabled(self._available)
        self.clear_button.setEnabled(not self._busy)
        self.models_button.setEnabled(not self._busy)
        for button in self.quick_buttons:
            button.setEnabled(can_submit and self._has_data)
