"""Lightweight local-AI assistant for SciPlotter.

The assistant is intentionally small: it treats a local LLM (via Ollama) as an
intent router + explainer, not a compute engine. All real work is done by the
app's own tools, which are exposed to the model through :mod:`ai.tool_registry`.

The core (registry / client / agent) has no Qt dependency so it stays fast to
unit-test with a fake client and never blocks on a model being installed.
"""

from ai.tool_registry import AITool, ToolRegistry
from ai.agent import AssistantResult, LocalAssistant
from ai.ollama_client import OllamaClient
from ai.llama_cpp_client import LlamaCppClient
from ai.model_manager import ModelManager
from ai.runtime_manager import RuntimeManager

__all__ = [
    "AITool",
    "ToolRegistry",
    "LocalAssistant",
    "AssistantResult",
    "OllamaClient",
    "LlamaCppClient",
    "ModelManager",
    "RuntimeManager",
]
