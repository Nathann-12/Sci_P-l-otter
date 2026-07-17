"""Registry of app capabilities the local AI is allowed to call.

A tool is a plain, defensive Python callable plus a small JSON-serialisable
schema the model reads. Handlers must return a short human/LLM-readable string
(what the model sees next) and must never raise — errors are caught and turned
into a text observation so the agent loop can recover instead of crashing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AITool:
    name: str
    description: str
    # {arg_name: {"type": "string"|"number"|..., "description": str, "required": bool}}
    parameters: Dict[str, Dict[str, Any]]
    handler: Callable[[Dict[str, Any]], Any]
    category: str = "general"
    risk: str = "read"
    version: str = "1.0"

    def spec(self, *, compact: bool = False) -> Dict[str, Any]:
        """Model-facing schema (no handler)."""
        parameters = self.parameters
        if compact:
            parameters = {
                name: {
                    key: value
                    for key, value in schema.items()
                    if key in {"type", "required"}
                }
                for name, schema in self.parameters.items()
            }
        return {
            "name": self.name,
            "description": self.description[:220] if compact else self.description,
            "parameters": parameters,
            "category": self.category,
            "risk": self.risk,
            "version": self.version,
        }


class ToolRegistry:
    """Ordered collection of :class:`AITool` with safe execution."""

    def __init__(
        self,
        executor: Optional[
            Callable[[Callable[[Dict[str, Any]], Any], Dict[str, Any]], Any]
        ] = None,
        approval_callback: Optional[Callable[[AITool, Dict[str, Any]], bool]] = None,
        context_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        self._tools: Dict[str, AITool] = {}
        self._executor = executor
        self._approval_callback = approval_callback
        self._context_provider = context_provider

    def set_executor(
        self,
        executor: Optional[
            Callable[[Callable[[Dict[str, Any]], Any], Dict[str, Any]], Any]
        ],
    ) -> None:
        """Route handlers through *executor* (used to marshal Qt work safely)."""
        self._executor = executor

    def set_approval_callback(
        self,
        callback: Optional[Callable[[AITool, Dict[str, Any]], bool]],
    ) -> None:
        """Set the UI approval hook for mutation and hardware actions."""
        self._approval_callback = callback

    def set_context_provider(
        self,
        provider: Optional[Callable[[], Dict[str, Any]]],
    ) -> None:
        """Provide live, read-only values used to resolve safe arguments.

        The provider is invoked through the registry executor when one is
        installed, so a background AI worker never reads Qt-owned state
        directly.
        """
        self._context_provider = provider

    def argument_context(self) -> Dict[str, Any]:
        """Return the current deterministic routing context, or an empty dict."""
        provider = self._context_provider
        if provider is None:
            return {}
        try:
            if self._executor is None:
                result = provider()
            else:
                result = self._executor(lambda _arguments: provider(), {})
        except Exception:
            logger.debug("AI argument context provider failed", exc_info=True)
            return {}
        return dict(result) if isinstance(result, dict) else {}

    def register(self, tool: AITool) -> AITool:
        self._tools[tool.name] = tool
        return tool

    def add(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Dict[str, Any]] | None,
        handler: Callable[[Dict[str, Any]], Any],
        *,
        category: str | None = None,
        risk: str | None = None,
        version: str = "1.0",
    ) -> AITool:
        # Metadata is centralised so existing tool registrations stay concise and
        # a release can audit every capability from one versioned catalogue.
        if category is None or risk is None:
            try:
                from ai.tool_catalog import metadata_for

                metadata = metadata_for(name)
            except Exception:
                metadata = {"category": "general", "risk": "read"}
            category = category or str(metadata["category"])
            risk = risk or str(metadata["risk"])
        return self.register(
            AITool(
                name,
                description,
                dict(parameters or {}),
                handler,
                str(category),
                str(risk),
                str(version),
            )
        )

    def names(self) -> List[str]:
        return list(self._tools)

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> AITool | None:
        return self._tools.get(name)

    def specs(
        self,
        names: List[str] | None = None,
        *,
        compact: bool = False,
    ) -> List[Dict[str, Any]]:
        selected = self._tools.values() if names is None else (
            self._tools[name] for name in names if name in self._tools
        )
        return [tool.spec(compact=compact) for tool in selected]

    def validate_arguments(
        self, name: str, arguments: Dict[str, Any] | None
    ) -> str | None:
        """Return a readable validation error, or ``None`` for a safe call."""
        tool = self._tools.get(name)
        if tool is None:
            return f"unknown tool '{name}'"
        if arguments is not None and not isinstance(arguments, dict):
            return "arguments must be a JSON object"
        values = dict(arguments or {})
        unknown = sorted(set(values) - set(tool.parameters))
        if unknown:
            return "unknown argument(s): " + ", ".join(unknown)
        for parameter, schema in tool.parameters.items():
            if schema.get("required") and parameter not in values:
                return f"missing required argument '{parameter}'"
            if parameter not in values or values[parameter] is None:
                continue
            expected = str(schema.get("type", "") or "").casefold()
            value = values[parameter]
            valid = {
                "string": isinstance(value, str),
                "number": isinstance(value, (int, float)) and not isinstance(value, bool),
                "integer": isinstance(value, int) and not isinstance(value, bool),
                "boolean": isinstance(value, bool),
                "array": isinstance(value, list),
                "object": isinstance(value, dict),
            }.get(expected, True)
            if not valid:
                return f"argument '{parameter}' must be {expected}"
            allowed = schema.get("enum")
            if isinstance(allowed, (list, tuple)) and value not in allowed:
                choices = ", ".join(repr(item) for item in allowed)
                return f"argument '{parameter}' must be one of: {choices}"
        return None

    def execute(
        self,
        name: str,
        arguments: Dict[str, Any] | None = None,
        *,
        validate: bool = False,
        expected_context_token: str = "",
    ) -> str:
        """Run a tool by name; always returns a string observation."""
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(self._tools) or "(none)"
            return f"Error: unknown tool '{name}'. Available tools: {available}."
        if validate:
            validation_error = self.validate_arguments(name, arguments)
            if validation_error:
                return f"Error: invalid call to '{name}': {validation_error}."
        if expected_context_token:
            current_token = str(self.argument_context().get("book_token", "") or "")
            if current_token and current_token != str(expected_context_token):
                return (
                    "Active Book changed before the action could run; "
                    "no changes were made. Please repeat the request."
                )
        try:
            resolved_arguments = dict(arguments or {})
            if (
                tool.risk in {"mutate", "device"}
                and self._approval_callback is not None
                and not self._approval_callback(tool, resolved_arguments)
            ):
                return f"Confirmation declined for '{name}'; no changes were made."
            if self._executor is None:
                result = tool.handler(resolved_arguments)
            else:
                result = self._executor(tool.handler, resolved_arguments)
        except Exception as exc:  # defensive: a tool must never crash the loop
            logger.debug("AI tool %r failed", name, exc_info=True)
            return f"Error running '{name}': {exc}"
        if result is None:
            return f"'{name}' completed."
        return str(result)
