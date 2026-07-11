"""The agent loop: user text -> (tool calls)* -> final answer.

Protocol is prompt-based rather than model-native tool-calling, so it works
with any Ollama model including tiny ones. Each turn the model must reply with a
single JSON object: either ``{"tool": name, "arguments": {...}}`` to call a tool
or ``{"answer": text}`` to reply. ``format: "json"`` guarantees the reply parses.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

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
    def system_prompt(self) -> str:
        tools = json.dumps(self.registry.specs(), ensure_ascii=False, indent=2)
        return (
            "You are SciPlotter's built-in data-analysis assistant. SciPlotter is "
            "a desktop app for plotting and analysing scientific data.\n"
            "You can use the tools below to inspect the user's data and drive the "
            "app. Do the real work with tools; never invent numbers.\n\n"
            f"TOOLS (JSON schema):\n{tools}\n\n"
            "Reply with EXACTLY ONE JSON object and nothing else, either:\n"
            '  {"tool": "<tool_name>", "arguments": { ... }}   to call a tool, or\n'
            '  {"answer": "<reply to the user>"}                to answer.\n\n'
            "RULES:\n"
            "- If the user asks about their data's columns, values, statistics, or "
            "asks you to plot/analyse, you MUST call the matching tool first and "
            "base your answer ONLY on its result.\n"
            "- NEVER write placeholder values like '[insert mean]' or made-up "
            "numbers. If you don't have a value, call a tool to get it.\n"
            "- After a tool result comes back, either call another tool or answer.\n"
            "- Keep answers short and reply in the user's language (Thai or English)."
        )

    # -------------------------------------------------------------------- loop
    def ask(self, user_text: str) -> AssistantResult:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content": str(user_text)},
        ]
        trace: List[Tuple[str, Dict[str, Any], str]] = []

        for step in range(1, self.max_steps + 1):
            try:
                content = self.client.chat(messages, format_json=True)
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
                arguments = data.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                observation = self.registry.execute(tool_name, arguments)
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
