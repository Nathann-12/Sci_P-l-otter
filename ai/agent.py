"""The agent loop: user text -> (tool calls)* -> final answer.

Protocol is prompt-based rather than model-native tool-calling, so it works
with any Ollama model including tiny ones. Each turn the model only selects a
tool or answers. Tool arguments are resolved deterministically from the user's
text and the active Book; model-authored arguments are never executed.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ai.command_router import route_command
from ai.safe_router import (
    ArgumentResolution,
    merge_argument_resolutions,
    resolution_has_new_details,
    resolve_tool_arguments,
)
from ai.tool_catalog import (
    TOOL_SCHEMA_VERSION,
    select_high_confidence_tool,
    select_tool_names,
)
from ai.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_CANCEL_RE = re.compile(
    r"^\s*(?:cancel|never\s*mind|stop|ยกเลิก|ไม่ต้อง(?:แล้ว)?|พอแล้ว)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")


@dataclass
class AssistantResult:
    answer: str
    trace: List[Tuple[str, Dict[str, Any], str]] = field(default_factory=list)
    steps: int = 0
    error: str = ""
    needs_input: bool = False
    cancelled: bool = False


@dataclass
class _PendingRequest:
    tool_name: str
    user_text: str
    context_token: str
    resolution: ArgumentResolution


class LocalAssistant:
    """Runs the tool-using loop against an injected chat client.

    The client only needs a ``chat(messages, *, format_json=False)`` method, so
    the whole loop is unit-testable with a scripted fake and never needs a real
    model or a network connection.
    """

    def __init__(self, registry: ToolRegistry, client: Any, max_steps: int = 4) -> None:
        self.registry = registry
        self.client = client
        self.max_steps = max(1, int(max_steps))
        self._pending_request: _PendingRequest | None = None

    def clear_pending_request(self) -> None:
        """Forget any incomplete clarification chain without running a tool."""
        self._pending_request = None

    # ------------------------------------------------------------------ prompt
    def system_prompt(self, user_text: str = "") -> str:
        names = select_tool_names(user_text, self.registry.names())
        selected_tools = []
        for name in names:
            tool = self.registry.get(name)
            if tool is not None:
                selected_tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description[:220],
                        "category": tool.category,
                        "risk": tool.risk,
                    }
                )
        tools = json.dumps(
            selected_tools,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            "You are SciPlotter's private local scientific-data assistant. "
            "Use app tools for data facts and actions; never invent results.\n"
            f"TOOL SCHEMA v{TOOL_SCHEMA_VERSION} (only these tools are allowed this turn):\n"
            f"{tools}\n\n"
            "Output exactly one JSON object and no markdown:\n"
            '{"tool":"<name>"} or {"answer":"<text>"}\n'
            "RULES:\n"
            "- Data columns, values, statistics, plots and analyses require a listed tool.\n"
            "- Select the tool only. Never output arguments; SciPlotter resolves them from the request and active Book.\n"
            "- Never claim an action before its tool succeeds.\n"
            "- Explanations, privacy/safety requests, clarification and requests not to act use answer, not a tool.\n"
            "- After a tool result, call another listed tool or answer from that result only.\n"
            "- Mutation/device tools may require confirmation.\n"
            "- Keep answers short and use the user's Thai or English.\n/no_think"
        )

    def reply_schema(self, user_text: str = "") -> Dict[str, Any]:
        """Return the strict tool-selection-only contract for local runtimes."""
        variants: List[Dict[str, Any]] = [
            {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            }
        ]
        for name in select_tool_names(user_text, self.registry.names()):
            tool = self.registry.get(name)
            if tool is None:
                continue
            variants.append(
                {
                    "type": "object",
                    "properties": {"tool": {"const": name}},
                    "required": ["tool"],
                    "additionalProperties": False,
                }
            )
        return {"oneOf": variants}

    # -------------------------------------------------------------------- loop
    def ask(
        self,
        user_text: str,
        on_tool_start: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> AssistantResult:
        user_text = str(user_text or "").strip()
        if self._pending_request is not None and _CANCEL_RE.match(user_text):
            self._pending_request = None
            answer = "ยกเลิกคำสั่งที่รอข้อมูลแล้ว โดยยังไม่ได้เปลี่ยนแปลงข้อมูล" if _THAI_RE.search(user_text) else (
                "Cancelled the pending request; no changes were made."
            )
            return AssistantResult(answer=answer, cancelled=True)

        direct_call = route_command(user_text)
        if direct_call is not None and self.registry.has(direct_call[0]):
            self._pending_request = None
            tool_name, arguments = direct_call
            if on_tool_start is not None:
                on_tool_start(tool_name, arguments)
            observation = self.registry.execute(tool_name, arguments)
            error = ""
            if observation.casefold().startswith(
                ("error", "could not", "no active", "unknown", "provide ", "ไม่มีข้อมูล")
            ):
                error = observation
            return AssistantResult(
                answer=observation,
                trace=[(tool_name, arguments, observation)],
                steps=1,
                error=error,
            )

        turn_context = self.registry.argument_context()
        pending_result = self._continue_pending_request(
            user_text,
            turn_context,
            on_tool_start,
        )
        if pending_result is not None:
            return pending_result

        trusted_tool_name = select_high_confidence_tool(
            user_text,
            self.registry.names(),
        )
        if trusted_tool_name:
            tool = self.registry.get(trusted_tool_name)
            assert tool is not None
            context_token = str(turn_context.get("book_token", "") or "")
            resolution = resolve_tool_arguments(user_text, tool, turn_context)
            if not resolution.ready:
                self._pending_request = _PendingRequest(
                    tool_name=trusted_tool_name,
                    user_text=user_text,
                    context_token=context_token,
                    resolution=resolution,
                )
                return AssistantResult(
                    answer=resolution.clarification,
                    steps=1,
                    needs_input=True,
                )
            arguments = resolution.arguments
            if on_tool_start is not None:
                on_tool_start(trusted_tool_name, arguments)
            observation = self.registry.execute(
                trusted_tool_name,
                arguments,
                validate=True,
                expected_context_token=context_token,
            )
            error = observation if _observation_is_error(observation) else ""
            return AssistantResult(
                answer=observation,
                trace=[(trusted_tool_name, arguments, observation)],
                steps=1,
                error=error,
            )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt(user_text)},
            {"role": "user", "content": str(user_text)},
        ]
        trace: List[Tuple[str, Dict[str, Any], str]] = []

        for step in range(1, self.max_steps + 1):
            try:
                chat_options: Dict[str, Any] = {"format_json": True}
                if getattr(self.client, "supports_json_schema", False):
                    chat_options["json_schema"] = self.reply_schema(user_text)
                content = self.client.chat(messages, **chat_options)
            except Exception as exc:
                logger.debug("AI chat call failed", exc_info=True)
                return AssistantResult(
                    answer="Local AI is unavailable right now.",
                    trace=trace,
                    steps=step - 1,
                    error=str(exc),
                )

            data = _parse_reply(content)

            tool_name = data.get("tool")
            if isinstance(tool_name, str) and tool_name:
                tool = self.registry.get(tool_name)
                if tool is None:
                    arguments: Dict[str, Any] = {}
                    context_token = ""
                else:
                    current_context = self.registry.argument_context()
                    context_token = str(current_context.get("book_token", "") or "")
                    turn_token = str(turn_context.get("book_token", "") or "")
                    if turn_token and context_token and turn_token != context_token:
                        self._pending_request = None
                        return AssistantResult(
                            answer=_book_changed_answer(user_text),
                            trace=trace,
                            steps=step,
                            needs_input=True,
                        )
                    resolution = resolve_tool_arguments(
                        user_text,
                        tool,
                        current_context,
                    )
                    if not resolution.ready:
                        self._pending_request = _PendingRequest(
                            tool_name=tool_name,
                            user_text=user_text,
                            context_token=context_token,
                            resolution=resolution,
                        )
                        return AssistantResult(
                            answer=resolution.clarification,
                            trace=trace,
                            steps=step,
                            needs_input=True,
                        )
                    arguments = resolution.arguments
                if on_tool_start is not None:
                    on_tool_start(tool_name, arguments)
                # The model only selected the tool. Arguments came from trusted,
                # deterministic app code and are still checked against the schema.
                observation = self.registry.execute(
                    tool_name,
                    arguments,
                    validate=True,
                    expected_context_token=context_token,
                )
                trace.append((tool_name, arguments, observation))
                if observation.startswith("Active Book changed"):
                    self._pending_request = None
                    return AssistantResult(
                        answer=_book_changed_answer(user_text),
                        trace=trace,
                        steps=step,
                        needs_input=True,
                    )
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {"role": "user", "content": f"Tool '{tool_name}' result:\n{observation}"}
                )
                continue

            answer = data.get("answer")
            if isinstance(answer, str) and answer.strip():
                self._pending_request = None
                return AssistantResult(answer=answer.strip(), trace=trace, steps=step)

            # Model produced neither a tool nor an answer -> use raw text.
            return AssistantResult(answer=content.strip() or "(no reply)", trace=trace, steps=step)

        return AssistantResult(
            answer="I couldn't finish that within the step limit. Try rephrasing.",
            trace=trace,
            steps=self.max_steps,
        )

    def _continue_pending_request(
        self,
        user_text: str,
        context: Dict[str, Any],
        on_tool_start: Optional[Callable[[str, Dict[str, Any]], None]],
    ) -> AssistantResult | None:
        pending = self._pending_request
        if pending is None:
            return None
        current_token = str(context.get("book_token", "") or "")
        if pending.context_token and current_token and pending.context_token != current_token:
            self._pending_request = None
            return AssistantResult(
                answer=_book_changed_answer(user_text),
                needs_input=True,
            )
        tool = self.registry.get(pending.tool_name)
        if tool is None:
            self._pending_request = None
            return None

        update = resolve_tool_arguments(user_text, tool, context)
        if not resolution_has_new_details(pending.resolution, update):
            # This is a new, unrelated request rather than a clarification.
            self._pending_request = None
            return None
        resolution = merge_argument_resolutions(
            user_text,
            tool,
            pending.resolution,
            update,
        )
        if not resolution.ready:
            pending.user_text = f"{pending.user_text}\n{user_text}"
            pending.resolution = resolution
            return AssistantResult(
                answer=resolution.clarification,
                needs_input=True,
            )

        self._pending_request = None
        arguments = resolution.arguments
        if on_tool_start is not None:
            on_tool_start(tool.name, arguments)
        observation = self.registry.execute(
            tool.name,
            arguments,
            validate=True,
            expected_context_token=current_token,
        )
        if observation.startswith("Active Book changed"):
            return AssistantResult(
                answer=_book_changed_answer(user_text),
                trace=[(tool.name, arguments, observation)],
                steps=1,
                needs_input=True,
            )
        error = observation if _observation_is_error(observation) else ""
        return AssistantResult(
            answer=observation,
            trace=[(tool.name, arguments, observation)],
            steps=1,
            error=error,
        )


def _parse_reply(content: str) -> Dict[str, Any]:
    """Best-effort JSON extraction; falls back to treating text as an answer."""
    text = (content or "").strip()
    if not text:
        return {"answer": ""}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    match = _JSON_OBJECT_RE.search(text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            logger.debug("AI reply JSON extraction failed", exc_info=True)
    return {"answer": text}


def _observation_is_error(observation: str) -> bool:
    return str(observation or "").casefold().startswith(
        ("error", "could not", "no active", "unknown", "provide ", "ไม่มีข้อมูล")
    )


def _book_changed_answer(user_text: str) -> str:
    if _THAI_RE.search(str(user_text or "")):
        return "Book ที่กำลังใช้งานเปลี่ยนไประหว่างประมวลผล จึงยังไม่ได้รันคำสั่ง กรุณาส่งคำสั่งอีกครั้ง"
    return (
        "The active Book changed while the request was being prepared, so the "
        "action was not run. Please submit the request again."
    )
