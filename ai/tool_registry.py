"""Registry of app capabilities the local AI is allowed to call.

A tool is a plain, defensive Python callable plus a small JSON-serialisable
schema the model reads. Handlers must return a short human/LLM-readable string
(what the model sees next) and must never raise — errors are caught and turned
into a text observation so the agent loop can recover instead of crashing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AITool:
    name: str
    description: str
    # {arg_name: {"type": "string"|"number"|..., "description": str, "required": bool}}
    parameters: Dict[str, Dict[str, Any]]
    handler: Callable[[Dict[str, Any]], Any]

    def spec(self) -> Dict[str, Any]:
        """Model-facing schema (no handler)."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    """Ordered collection of :class:`AITool` with safe execution."""

    def __init__(self) -> None:
        self._tools: Dict[str, AITool] = {}

    def register(self, tool: AITool) -> AITool:
        self._tools[tool.name] = tool
        return tool

    def add(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Dict[str, Any]] | None,
        handler: Callable[[Dict[str, Any]], Any],
    ) -> AITool:
        return self.register(AITool(name, description, dict(parameters or {}), handler))

    def names(self) -> List[str]:
        return list(self._tools)

    def has(self, name: str) -> bool:
        return name in self._tools

    def specs(self) -> List[Dict[str, Any]]:
        return [tool.spec() for tool in self._tools.values()]

    def execute(self, name: str, arguments: Dict[str, Any] | None = None) -> str:
        """Run a tool by name; always returns a string observation."""
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(self._tools) or "(none)"
            return f"Error: unknown tool '{name}'. Available tools: {available}."
        try:
            result = tool.handler(dict(arguments or {}))
        except Exception as exc:  # defensive: a tool must never crash the loop
            logger.debug("AI tool %r failed", name, exc_info=True)
            return f"Error running '{name}': {exc}"
        if result is None:
            return f"'{name}' completed."
        return str(result)
