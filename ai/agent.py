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
from ai.safe_router import resolve_tool_arguments
from ai.tool_catalog import TOOL_SCHEMA_VERSION, select_tool_names
from ai.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class AssistantResult:
    answer: str
    trace: List[Tuple[str, Dict[str, Any], str]] = field(default_factory=list)
    steps: int = 0
    error: str = ""


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
        direct_call = route_command(user_text)
        if direct_call is not None and self.registry.has(direct_call[0]):
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
                else:
                    resolution = resolve_tool_arguments(
                        user_text,
                        tool,
                        self.registry.argument_context(),
                    )
                    if not resolution.ready:
                        return AssistantResult(
                            answer=resolution.clarification,
                            trace=trace,
                            steps=step,
                        )
                    arguments = resolution.arguments
                if on_tool_start is not None:
                    on_tool_start(tool_name, arguments)
                # The model only selected the tool. Arguments came from trusted,
                # deterministic app code and are still checked against the schema.
                observation = self.registry.execute(tool_name, arguments, validate=True)
                trace.append((tool_name, arguments, observation))
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {"role": "user", "content": f"Tool '{tool_name}' result:\n{observation}"}
                )
                continue

            answer = data.get("answer")
            if isinstance(answer, str) and answer.strip():
                return AssistantResult(answer=answer.strip(), trace=trace, steps=step)

            # Model produced neither a tool nor an answer -> use raw text.
            return AssistantResult(answer=content.strip() or "(no reply)", trace=trace, steps=step)

        return AssistantResult(
            answer="I couldn't finish that within the step limit. Try rephrasing.",
            trace=trace,
            steps=self.max_steps,
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
