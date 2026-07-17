from __future__ import annotations

import json

from ai.agent import LocalAssistant
from ai.app_tools import build_app_registry
from ai.tool_catalog import MAX_PROMPT_TOOLS, TOOL_SCHEMA_VERSION, select_tool_names
from ai.tool_registry import ToolRegistry


class _Client:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, *, format_json=False):
        self.calls.append(messages)
        return self.replies.pop(0)


class _SchemaClient:
    supports_json_schema = True

    def __init__(self):
        self.schema = None

    def chat(self, messages, *, format_json=False, json_schema=None):
        self.schema = json_schema
        return '{"answer":"done"}'


def test_large_registry_prompt_uses_only_relevant_tools():
    registry = build_app_registry(object())
    assistant = LocalAssistant(registry, _Client([]))

    prompt = assistant.system_prompt("plot a scatter graph of voltage vs time")

    assert f"TOOL SCHEMA v{TOOL_SCHEMA_VERSION}" in prompt
    assert '"name":"plot_columns"' in prompt
    assert '"name":"gas_live_control"' not in prompt
    assert prompt.count('"name":') <= MAX_PROMPT_TOOLS
    assert len(prompt) < 10_000


def test_signal_request_routes_signal_tools_not_unrelated_specialty_tools():
    names = build_app_registry(object()).names()
    selected = select_tool_names("FFT and power spectrum", names)
    assert "run_fft" in selected
    assert "power_spectrum" in selected
    assert "tafel_analysis" not in selected


def test_model_authored_arguments_are_ignored_and_rebuilt_from_user_text():
    calls = []
    registry = ToolRegistry()
    registry.add(
        "safe_tool",
        "test",
        {"count": {"type": "integer", "required": True}},
        lambda arguments: calls.append(arguments) or "ran",
    )
    client = _Client([
        json.dumps({"tool": "safe_tool", "arguments": {"count": "many"}}),
        json.dumps({"answer": "done"}),
    ])

    result = LocalAssistant(registry, client).ask("run it with count 3")

    assert calls == [{"count": 3}]
    assert result.trace[0][2] == "ran"


def test_mutating_tool_requires_approval_when_policy_is_installed():
    calls = []
    registry = ToolRegistry(approval_callback=lambda _tool, _arguments: False)
    registry.add(
        "normalize",
        "normalize data",
        {},
        lambda arguments: calls.append(arguments) or "changed",
    )

    observation = registry.execute("normalize", {})

    assert calls == []
    assert "confirmation declined" in observation.casefold()
    assert registry.get("normalize").risk == "mutate"


def test_schema_capable_client_receives_tool_selection_only_contract():
    registry = ToolRegistry()
    registry.add(
        "safe_tool",
        "test",
        {
            "count": {"type": "integer", "required": True},
            "mode": {
                "type": "string",
                "required": False,
                "enum": ["fast", "careful"],
            },
        },
        lambda _arguments: "ran",
    )
    client = _SchemaClient()

    LocalAssistant(registry, client).ask("explain the available action")

    assert client.schema is not None
    tool_variant = next(
        variant
        for variant in client.schema["oneOf"]
        if variant.get("properties", {}).get("tool", {}).get("const") == "safe_tool"
    )
    assert tool_variant["required"] == ["tool"]
    assert set(tool_variant["properties"]) == {"tool"}
    assert tool_variant["additionalProperties"] is False


def test_registry_rejects_values_outside_parameter_enum():
    registry = ToolRegistry()
    registry.add(
        "mode_tool",
        "test",
        {"mode": {"type": "string", "enum": ["a", "b"]}},
        lambda _arguments: "ran",
    )

    assert registry.validate_arguments("mode_tool", {"mode": "a"}) is None
    assert "must be one of" in registry.validate_arguments(
        "mode_tool", {"mode": "invented"}
    )
