"""Pure readiness checks for SciPlotter's managed, local AI stack.

The UI and startup path use the same probe so that ``Ready`` has one precise
meaning: the selected catalogue model exists, a local llama.cpp runtime is
available, and the machine meets the model's stated minimum memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ai.llama_cpp_client import resolve_llama_server
from ai.model_manager import ModelManager, system_ram_gb
from ai.runtime_manager import RuntimeManager
from ai.tool_catalog import ROUTER_PROTOCOL_VERSION, TOOL_SCHEMA_VERSION


class AISetupRequired(RuntimeError):
    """Raised when the selected offline AI backend is not runnable yet."""

    def __init__(self, readiness: "AIReadiness") -> None:
        super().__init__(readiness.detail)
        self.readiness = readiness


@dataclass(frozen=True)
class AIReadiness:
    """Result of a side-effect-free managed-AI readiness probe."""

    state: str
    ready: bool
    detail: str
    pack_id: str
    pack_name: str = ""
    model_path: Path | None = None
    runtime_path: Path | None = None
    ram_gb: float = 0.0
    recommended_pack_id: str = ""
    warning: str = ""
    release_status: str = "preview"

    @property
    def missing(self) -> tuple[str, ...]:
        missing: list[str] = []
        if self.state in {"model_missing", "model_and_runtime_missing"}:
            missing.append("model")
        if self.state in {
            "runtime_missing",
            "unverified_runtime",
            "model_and_runtime_missing",
        }:
            missing.append("runtime")
        return tuple(missing)


def inspect_bundled_ai(
    pack_id: str,
    runtime_path: str | Path | None = None,
    *,
    manager: ModelManager | None = None,
    runtime_manager: RuntimeManager | None = None,
    ram_gb: float | None = None,
    runtime_resolver: Callable[[str | Path | None], Path | None] | None = None,
) -> AIReadiness:
    """Inspect the selected catalogue pack without starting inference.

    Dependency injection keeps this inexpensive to test and lets the model
    manager dialog inspect a temporary/custom installation root.
    """

    manager = manager or ModelManager()
    runtime_manager = runtime_manager or RuntimeManager()
    resolver = runtime_resolver or resolve_llama_server
    ram = system_ram_gb() if ram_gb is None else max(0.0, float(ram_gb))
    recommended = manager.recommended_pack(ram)
    packs = {pack.pack_id: pack for pack in manager.packs()}
    pack = packs.get(str(pack_id or ""))
    if pack is None:
        return AIReadiness(
            state="unknown_model",
            ready=False,
            detail="The selected AI model is not supported by this SciPlotter version.",
            pack_id=str(pack_id or ""),
            ram_gb=ram,
            recommended_pack_id=recommended.pack_id,
        )

    release_status = str(getattr(pack, "release_status", "preview") or "preview")
    if (
        str(getattr(pack, "router_protocol", "")) != ROUTER_PROTOCOL_VERSION
        or str(getattr(pack, "tool_schema_version", "")) != TOOL_SCHEMA_VERSION
    ):
        return AIReadiness(
            state="incompatible_model",
            ready=False,
            detail=(
                "This AI pack targets a different router/tool schema. "
                "Install a pack compatible with this SciPlotter version."
            ),
            pack_id=pack.pack_id,
            pack_name=pack.display_name,
            ram_gb=ram,
            recommended_pack_id=recommended.pack_id,
            release_status=release_status,
        )
    if ram and ram < pack.min_ram_gb:
        return AIReadiness(
            state="insufficient_memory",
            ready=False,
            detail=(
                f"This model needs at least {pack.min_ram_gb:g} GB RAM; "
                f"this computer reports {ram:.1f} GB."
            ),
            pack_id=pack.pack_id,
            pack_name=pack.display_name,
            ram_gb=ram,
            recommended_pack_id=recommended.pack_id,
            release_status=release_status,
        )

    model_ready = manager.is_installed(pack.pack_id)
    model = manager.model_path(pack.pack_id) if model_ready else None

    resolved_runtime: Path | None = None
    unverified_runtime_found = False
    configured = Path(runtime_path).expanduser() if runtime_path else None
    if runtime_manager.is_installed() and runtime_manager.runtime_path.is_file():
        resolved_runtime = runtime_manager.runtime_path.resolve()
    else:
        unverified_runtime_found = configured is not None and configured.is_file()
        try:
            candidate = resolver(runtime_path)
            unverified_runtime_found = unverified_runtime_found or (
                candidate is not None and candidate.is_file()
            )
        except Exception:
            pass
    runtime_ready = resolved_runtime is not None and resolved_runtime.is_file()

    if not model_ready and not runtime_ready:
        state = "model_and_runtime_missing"
        detail = "Set up the local AI runtime and model before using SciPlotter AI."
    elif not model_ready:
        state = "model_missing"
        detail = f"Install {pack.display_name} to finish local AI setup."
    elif not runtime_ready:
        state = "unverified_runtime" if unverified_runtime_found else "runtime_missing"
        detail = (
            "A custom or unverified runtime was found. Install the pinned, verified "
            "SciPlotter AI runtime before using this model."
            if unverified_runtime_found
            else "Install the verified local AI runtime to use this model."
        )
    else:
        warning = ""
        if ram and ram < pack.recommended_ram_gb:
            warning = (
                f"Performance may be limited below the recommended "
                f"{pack.recommended_ram_gb:g} GB RAM."
            )
        return AIReadiness(
            state="ready",
            ready=True,
            detail=(
                "Ready for private, on-device AI."
                if release_status == "release"
                else "Ready for private, on-device AI with a preview model."
            ),
            pack_id=pack.pack_id,
            pack_name=pack.display_name,
            model_path=model,
            runtime_path=resolved_runtime,
            ram_gb=ram,
            recommended_pack_id=recommended.pack_id,
            warning=warning,
            release_status=release_status,
        )

    return AIReadiness(
        state=state,
        ready=False,
        detail=detail,
        pack_id=pack.pack_id,
        pack_name=pack.display_name,
        model_path=model,
        runtime_path=resolved_runtime,
        ram_gb=ram,
        recommended_pack_id=recommended.pack_id,
        release_status=release_status,
    )
