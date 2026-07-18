"""Headless, reproducible analysis recipes with dependency recalculation.

This module deliberately has no Qt dependencies.  A desktop UI, a command line
batch runner, and a worker process can therefore share exactly the same recipe
contract and execution semantics.

Executors receive named inputs, validated parameters, and an
:class:`ExecutionContext`::

    registry.register(
        "scale",
        lambda inputs, params, ctx: inputs["data"] * params["factor"],
        schema={
            "type": "object",
            "required": ["factor"],
            "properties": {"factor": {"type": "number"}},
            "additionalProperties": False,
        },
    )

Recipes store configuration and compact provenance, never full result data.
The engine keeps the most recent successful result in memory.  A failed or
cancelled recomputation cannot overwrite that last-good cache.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math
import os
import re
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


RECIPE_FORMAT = "sciplotter_analysis_recipe"
RECIPE_VERSION = 1
COMPONENT_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_RESULT_KINDS = frozenset({"any", "dataframe", "mapping", "scalar"})


# ---------------------------------------------------------------- exceptions
class AnalysisRecipeError(Exception):
    """Base class for recipe errors."""


class RecipeFormatError(AnalysisRecipeError, ValueError):
    """A persisted recipe does not satisfy the versioned file contract."""


class RecipeValidationError(AnalysisRecipeError, ValueError):
    """The dependency graph or a recipe definition is invalid."""


class OperationRegistrationError(AnalysisRecipeError, ValueError):
    """An operation registry entry is invalid or duplicated."""


class ParameterValidationError(AnalysisRecipeError, ValueError):
    """Operation parameters fail their schema or custom validator."""


class UnknownOperationError(AnalysisRecipeError, LookupError):
    """A recipe refers to an operation absent from the active registry."""


class MissingSourceError(AnalysisRecipeError, LookupError):
    """A required DataFrame source has not been supplied to the engine."""


class ResultValidationError(AnalysisRecipeError, TypeError):
    """An executor returned a value outside its declared output contract."""


class ExecutionCancelled(AnalysisRecipeError):
    """Cooperative cancellation requested by the caller."""


class NodeExecutionError(AnalysisRecipeError):
    """A node failed after its runtime state was safely updated."""

    def __init__(self, node_id: str, message: str, cause: Exception | None = None):
        super().__init__(f"Node {node_id!r} failed: {message}")
        self.node_id = node_id
        self.cause = cause


# -------------------------------------------------------------- JSON helpers
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _expect_mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeFormatError(f"{where} must be a JSON object")
    if not all(isinstance(key, str) for key in value):
        raise RecipeFormatError(f"{where} keys must be strings")
    return value


def _expect_keys(
    value: Mapping[str, Any],
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
    where: str,
) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = sorted(required_set - set(value))
    extra = sorted(set(value) - allowed)
    if missing:
        raise RecipeFormatError(f"{where} is missing required field(s): {', '.join(missing)}")
    if extra:
        raise RecipeFormatError(f"{where} contains unknown field(s): {', '.join(extra)}")


def _json_safe(value: Any, where: str = "value") -> Any:
    """Return a detached, strict-JSON-safe value or raise a clear error.

    Numpy scalars/arrays, timestamps, dates, tuples, and dataclasses exposing a
    ``to_dict`` method are normalised for practical scientific results.  NaN
    and infinity are rejected because they are not valid JSON values.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, np.generic):
        return _json_safe(value.item(), where)
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ResultValidationError(f"{where} contains a non-finite number")
        return float(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist(), where)
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ResultValidationError(f"{where} has a non-string mapping key: {key!r}")
            result[key] = _json_safe(item, f"{where}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, f"{where}[{index}]") for index, item in enumerate(value)]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _json_safe(to_dict(), where)
    raise ResultValidationError(f"{where} is not JSON-safe: {type(value).__name__}")


def _config_json_safe(value: Any, where: str) -> Any:
    try:
        return _json_safe(value, where)
    except ResultValidationError as exc:
        raise RecipeValidationError(str(exc)) from exc


def _canonical_hash(value: Any) -> str:
    safe = _json_safe(value)
    encoded = json.dumps(
        safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _identifier(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecipeValidationError(f"{where} must be a non-empty string")
    value = value.strip()
    if not _IDENTIFIER.fullmatch(value):
        raise RecipeValidationError(
            f"{where} {value!r} may contain only letters, digits, '.', '_', ':', and '-'"
        )
    return value


def _component_version(value: Any, where: str) -> int:
    if type(value) is not int or value != COMPONENT_VERSION:
        raise RecipeFormatError(
            f"unsupported {where} version {value!r}; expected {COMPONENT_VERSION}"
        )
    return value


def _copy_runtime_value(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=True)
    return copy.deepcopy(value)


# ---------------------------------------------------------- public dataclasses
class RecalculationMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    FROZEN = "frozen"

    @classmethod
    def parse(cls, value: "RecalculationMode | str") -> "RecalculationMode":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.strip().lower())
            except ValueError:
                pass
        allowed = ", ".join(item.value for item in cls)
        raise RecipeValidationError(f"recalculation mode must be one of: {allowed}")


@dataclass(frozen=True)
class RecipeInput:
    """Bind one executor argument to a DataFrame source or node output."""

    name: str
    kind: str
    source_id: str
    output: str = "result"
    version: int = COMPONENT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier(self.name, "input name"))
        if self.kind not in {"source", "node"}:
            raise RecipeValidationError("input kind must be 'source' or 'node'")
        object.__setattr__(self, "source_id", _identifier(self.source_id, "input source_id"))
        object.__setattr__(self, "output", _identifier(self.output, "input output"))
        if self.version != COMPONENT_VERSION:
            raise RecipeValidationError(f"unsupported RecipeInput version: {self.version}")

    @classmethod
    def source(cls, name: str, source_id: str) -> "RecipeInput":
        return cls(name=name, kind="source", source_id=source_id)

    @classmethod
    def node(cls, name: str, node_id: str, output: str = "result") -> "RecipeInput":
        return cls(name=name, kind="node", source_id=node_id, output=output)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "kind": self.kind,
            "source_id": self.source_id,
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, raw: Any, where: str = "input") -> "RecipeInput":
        data = _expect_mapping(raw, where)
        _expect_keys(
            data,
            required=("version", "name", "kind", "source_id", "output"),
            where=where,
        )
        try:
            return cls(
                version=_component_version(data["version"], "RecipeInput"),
                name=data["name"],
                kind=data["kind"],
                source_id=data["source_id"],
                output=data["output"],
            )
        except (TypeError, ValueError, RecipeValidationError) as exc:
            raise RecipeFormatError(f"invalid {where}: {exc}") from exc


@dataclass(frozen=True)
class RecipeOutput:
    """Declare a named node output and its runtime result kind."""

    name: str = "result"
    kind: str = "any"
    description: str = ""
    version: int = COMPONENT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier(self.name, "output name"))
        if self.kind not in _RESULT_KINDS:
            raise RecipeValidationError(
                f"output kind must be one of: {', '.join(sorted(_RESULT_KINDS))}"
            )
        if not isinstance(self.description, str):
            raise RecipeValidationError("output description must be a string")
        if self.version != COMPONENT_VERSION:
            raise RecipeValidationError(f"unsupported RecipeOutput version: {self.version}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, raw: Any, where: str = "output") -> "RecipeOutput":
        data = _expect_mapping(raw, where)
        _expect_keys(
            data, required=("version", "name", "kind", "description"), where=where
        )
        try:
            return cls(
                version=_component_version(data["version"], "RecipeOutput"),
                name=data["name"],
                kind=data["kind"],
                description=data["description"],
            )
        except (TypeError, ValueError, RecipeValidationError) as exc:
            raise RecipeFormatError(f"invalid {where}: {exc}") from exc


@dataclass(frozen=True)
class RecipeNode:
    """A versioned operation node in an :class:`AnalysisRecipe`."""

    node_id: str
    operation: str
    inputs: Tuple[RecipeInput, ...] | List[RecipeInput] = field(default_factory=tuple)
    outputs: Tuple[RecipeOutput, ...] | List[RecipeOutput] = field(
        default_factory=lambda: (RecipeOutput(),)
    )
    parameters: Mapping[str, Any] = field(default_factory=dict)
    recalculation_mode: RecalculationMode | str = RecalculationMode.AUTO
    enabled: bool = True
    label: str = ""
    version: int = COMPONENT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _identifier(self.node_id, "node_id"))
        object.__setattr__(self, "operation", _identifier(self.operation, "operation"))
        if not isinstance(self.inputs, (list, tuple)) or not all(
            isinstance(item, RecipeInput) for item in self.inputs
        ):
            raise RecipeValidationError("node inputs must contain RecipeInput objects")
        if not isinstance(self.outputs, (list, tuple)) or not self.outputs or not all(
            isinstance(item, RecipeOutput) for item in self.outputs
        ):
            raise RecipeValidationError("node outputs must contain at least one RecipeOutput")
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        if not isinstance(self.parameters, Mapping) or not all(
            isinstance(key, str) for key in self.parameters
        ):
            raise RecipeValidationError("node parameters must be an object with string keys")
        object.__setattr__(self, "parameters", _config_json_safe(dict(self.parameters), "parameters"))
        object.__setattr__(
            self, "recalculation_mode", RecalculationMode.parse(self.recalculation_mode)
        )
        if not isinstance(self.enabled, bool):
            raise RecipeValidationError("node enabled must be boolean")
        if not isinstance(self.label, str):
            raise RecipeValidationError("node label must be a string")
        if self.version != COMPONENT_VERSION:
            raise RecipeValidationError(f"unsupported RecipeNode version: {self.version}")
        input_names = [item.name for item in self.inputs]
        if len(input_names) != len(set(input_names)):
            raise RecipeValidationError(f"node {self.node_id!r} has duplicate input names")
        output_names = [item.name for item in self.outputs]
        if len(output_names) != len(set(output_names)):
            raise RecipeValidationError(f"node {self.node_id!r} has duplicate output names")

    @property
    def mode(self) -> RecalculationMode:
        """Short UI-friendly alias for ``recalculation_mode``."""
        return self.recalculation_mode

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "node_id": self.node_id,
            "operation": self.operation,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "parameters": _config_json_safe(self.parameters, "parameters"),
            "recalculation_mode": self.recalculation_mode.value,
            "enabled": self.enabled,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, raw: Any, where: str = "node") -> "RecipeNode":
        data = _expect_mapping(raw, where)
        _expect_keys(
            data,
            required=(
                "version",
                "node_id",
                "operation",
                "inputs",
                "outputs",
                "parameters",
                "recalculation_mode",
                "enabled",
                "label",
            ),
            where=where,
        )
        if not isinstance(data["inputs"], list) or not isinstance(data["outputs"], list):
            raise RecipeFormatError(f"{where} inputs and outputs must be arrays")
        try:
            return cls(
                version=_component_version(data["version"], "RecipeNode"),
                node_id=data["node_id"],
                operation=data["operation"],
                inputs=tuple(
                    RecipeInput.from_dict(item, f"{where}.inputs[{index}]")
                    for index, item in enumerate(data["inputs"])
                ),
                outputs=tuple(
                    RecipeOutput.from_dict(item, f"{where}.outputs[{index}]")
                    for index, item in enumerate(data["outputs"])
                ),
                parameters=data["parameters"],
                recalculation_mode=data["recalculation_mode"],
                enabled=data["enabled"],
                label=data["label"],
            )
        except (TypeError, ValueError, RecipeValidationError) as exc:
            raise RecipeFormatError(f"invalid {where}: {exc}") from exc


@dataclass(frozen=True)
class NodeProvenance:
    """One compact, JSON-safe execution attempt record."""

    run_id: str
    node_id: str
    operation: str
    operation_version: str
    started_at: str
    finished_at: str
    duration_ms: float
    success: bool
    parameter_checksum: str
    source_checksums: Mapping[str, str] = field(default_factory=dict)
    dependency_runs: Mapping[str, str] = field(default_factory=dict)
    result_summary: Mapping[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    version: int = COMPONENT_VERSION

    def __post_init__(self) -> None:
        for name in ("run_id", "operation_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise RecipeValidationError(f"provenance {name} must be a non-empty string")
        object.__setattr__(self, "node_id", _identifier(self.node_id, "provenance node_id"))
        object.__setattr__(
            self, "operation", _identifier(self.operation, "provenance operation")
        )
        for name in ("started_at", "finished_at", "parameter_checksum"):
            if not isinstance(getattr(self, name), str):
                raise RecipeValidationError(f"provenance {name} must be a string")
        if not isinstance(self.success, bool):
            raise RecipeValidationError("provenance success must be boolean")
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, (int, float)) or not math.isfinite(
            float(self.duration_ms)
        ) or float(self.duration_ms) < 0:
            raise RecipeValidationError("provenance duration_ms must be finite and non-negative")
        object.__setattr__(self, "duration_ms", round(float(self.duration_ms), 3))
        for name in ("source_checksums", "dependency_runs"):
            value = getattr(self, name)
            if not isinstance(value, Mapping) or not all(
                isinstance(key, str) and isinstance(item, str) for key, item in value.items()
            ):
                raise RecipeValidationError(f"provenance {name} must map strings to strings")
            object.__setattr__(self, name, dict(value))
        if not isinstance(self.result_summary, Mapping):
            raise RecipeValidationError("provenance result_summary must be an object")
        object.__setattr__(
            self,
            "result_summary",
            _config_json_safe(dict(self.result_summary), "result_summary"),
        )
        if self.error is not None and not isinstance(self.error, str):
            raise RecipeValidationError("provenance error must be a string or null")
        if self.version != COMPONENT_VERSION:
            raise RecipeValidationError(f"unsupported NodeProvenance version: {self.version}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "operation": self.operation,
            "operation_version": self.operation_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "parameter_checksum": self.parameter_checksum,
            "source_checksums": dict(self.source_checksums),
            "dependency_runs": dict(self.dependency_runs),
            "result_summary": _config_json_safe(self.result_summary, "result_summary"),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, raw: Any, where: str = "provenance") -> "NodeProvenance":
        data = _expect_mapping(raw, where)
        _expect_keys(
            data,
            required=(
                "version",
                "run_id",
                "node_id",
                "operation",
                "operation_version",
                "started_at",
                "finished_at",
                "duration_ms",
                "success",
                "parameter_checksum",
                "source_checksums",
                "dependency_runs",
                "result_summary",
                "error",
            ),
            where=where,
        )
        try:
            return cls(**dict(data))
        except (TypeError, ValueError, RecipeValidationError) as exc:
            raise RecipeFormatError(f"invalid {where}: {exc}") from exc


@dataclass
class AnalysisRecipe:
    """Versioned graph configuration plus compact execution provenance."""

    recipe_id: str
    name: str
    nodes: List[RecipeNode] | Tuple[RecipeNode, ...] = field(default_factory=list)
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: List[NodeProvenance] | Tuple[NodeProvenance, ...] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    version: int = RECIPE_VERSION

    def __post_init__(self) -> None:
        self.recipe_id = _identifier(self.recipe_id, "recipe_id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise RecipeValidationError("recipe name must be a non-empty string")
        self.name = self.name.strip()
        if not isinstance(self.description, str):
            raise RecipeValidationError("recipe description must be a string")
        if not isinstance(self.nodes, (list, tuple)) or not all(
            isinstance(node, RecipeNode) for node in self.nodes
        ):
            raise RecipeValidationError("recipe nodes must contain RecipeNode objects")
        self.nodes = list(self.nodes)
        if not isinstance(self.provenance, (list, tuple)) or not all(
            isinstance(item, NodeProvenance) for item in self.provenance
        ):
            raise RecipeValidationError("recipe provenance must contain NodeProvenance objects")
        self.provenance = list(self.provenance)
        if not isinstance(self.metadata, Mapping) or not all(
            isinstance(key, str) for key in self.metadata
        ):
            raise RecipeValidationError("recipe metadata must be an object with string keys")
        self.metadata = _config_json_safe(dict(self.metadata), "metadata")
        if not isinstance(self.created_at, str) or not isinstance(self.updated_at, str):
            raise RecipeValidationError("recipe timestamps must be strings")
        if self.version != RECIPE_VERSION:
            raise RecipeValidationError(f"unsupported recipe version: {self.version}")
        _validate_recipe_graph(self)

    @classmethod
    def create(cls, name: str, *, recipe_id: Optional[str] = None, **kwargs: Any) -> "AnalysisRecipe":
        return cls(recipe_id=recipe_id or f"recipe-{uuid.uuid4().hex}", name=name, **kwargs)

    def node(self, node_id: str) -> RecipeNode:
        for item in self.nodes:
            if item.node_id == node_id:
                return item
        raise RecipeValidationError(f"unknown node: {node_id!r}")

    def to_dict(self) -> Dict[str, Any]:
        _validate_recipe_graph(self)
        return {
            "format": RECIPE_FORMAT,
            "version": self.version,
            "recipe_id": self.recipe_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": _config_json_safe(self.metadata, "metadata"),
            "nodes": [node.to_dict() for node in self.nodes],
            "provenance": [item.to_dict() for item in self.provenance],
        }

    def to_json(self, *, indent: Optional[int] = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=False,
            allow_nan=False,
        )

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Atomically write the strict recipe JSON document."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(self.to_json() + "\n", encoding="utf-8")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    @classmethod
    def from_dict(cls, raw: Any) -> "AnalysisRecipe":
        data = _expect_mapping(raw, "recipe document")
        _expect_keys(
            data,
            required=(
                "format",
                "version",
                "recipe_id",
                "name",
                "description",
                "created_at",
                "updated_at",
                "metadata",
                "nodes",
                "provenance",
            ),
            where="recipe document",
        )
        if data["format"] != RECIPE_FORMAT:
            raise RecipeFormatError(
                f"unsupported recipe format {data['format']!r}; expected {RECIPE_FORMAT!r}"
            )
        if type(data["version"]) is not int or data["version"] != RECIPE_VERSION:
            raise RecipeFormatError(
                f"unsupported recipe version {data['version']!r}; expected {RECIPE_VERSION}"
            )
        if not isinstance(data["nodes"], list) or not isinstance(data["provenance"], list):
            raise RecipeFormatError("recipe nodes and provenance must be arrays")
        try:
            return cls(
                recipe_id=data["recipe_id"],
                name=data["name"],
                description=data["description"],
                created_at=data["created_at"],
                updated_at=data["updated_at"],
                metadata=data["metadata"],
                nodes=[
                    RecipeNode.from_dict(item, f"nodes[{index}]")
                    for index, item in enumerate(data["nodes"])
                ],
                provenance=[
                    NodeProvenance.from_dict(item, f"provenance[{index}]")
                    for index, item in enumerate(data["provenance"])
                ],
                version=data["version"],
            )
        except RecipeFormatError:
            raise
        except (TypeError, ValueError, RecipeValidationError) as exc:
            raise RecipeFormatError(f"invalid recipe document: {exc}") from exc

    @classmethod
    def from_json(cls, text: str) -> "AnalysisRecipe":
        if not isinstance(text, str):
            raise RecipeFormatError("recipe JSON must be text")
        try:
            raw = json.loads(text, parse_constant=lambda token: (_raise_nonfinite(token)))
        except (json.JSONDecodeError, ValueError) as exc:
            raise RecipeFormatError(f"invalid recipe JSON: {exc}") from exc
        return cls.from_dict(raw)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "AnalysisRecipe":
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RecipeFormatError(f"could not read recipe file: {exc}") from exc
        return cls.from_json(text)


def _raise_nonfinite(token: str) -> None:
    raise ValueError(f"non-finite JSON constant {token!r} is not allowed")


# ------------------------------------------------------ graph and checksumming
def dataframe_checksum(frame: pd.DataFrame) -> str:
    """Stable SHA-256 for values, index, columns, order, and dtypes."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("source must be a pandas DataFrame")
    digest = hashlib.sha256()
    header = {
        "columns": [repr(column) for column in frame.columns],
        "dtypes": [str(dtype) for dtype in frame.dtypes],
        "index_names": [repr(name) for name in frame.index.names],
        "index_type": type(frame.index).__name__,
        "shape": list(frame.shape),
    }
    digest.update(
        json.dumps(header, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    try:
        row_hashes = pd.util.hash_pandas_object(frame, index=True, categorize=True)
        digest.update(np.ascontiguousarray(row_hashes.to_numpy(dtype="uint64")).tobytes())
    except (TypeError, ValueError):
        # Object columns can contain unhashable scientific structures.  The
        # canonical repr fallback is slower but still deterministic in-process.
        canonical_rows = [
            [repr(item) for item in row]
            for row in frame.itertuples(index=True, name=None)
        ]
        digest.update(
            json.dumps(canonical_rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    return f"sha256:{digest.hexdigest()}"


def _validate_recipe_graph(recipe: AnalysisRecipe) -> Tuple[str, ...]:
    node_ids = [node.node_id for node in recipe.nodes]
    if len(node_ids) != len(set(node_ids)):
        duplicates = sorted({item for item in node_ids if node_ids.count(item) > 1})
        raise RecipeValidationError(f"duplicate node id(s): {', '.join(duplicates)}")
    nodes = {node.node_id: node for node in recipe.nodes}
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    dependencies: Dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    dependents: Dict[str, List[str]] = {node_id: [] for node_id in node_ids}
    for node in recipe.nodes:
        for binding in node.inputs:
            if binding.kind != "node":
                continue
            dependency = nodes.get(binding.source_id)
            if dependency is None:
                raise RecipeValidationError(
                    f"node {node.node_id!r} references missing dependency {binding.source_id!r}"
                )
            if binding.output not in {output.name for output in dependency.outputs}:
                raise RecipeValidationError(
                    f"node {node.node_id!r} requests missing output {binding.output!r} "
                    f"from dependency {binding.source_id!r}"
                )
            dependencies[node.node_id].add(binding.source_id)
            dependents[binding.source_id].append(node.node_id)

    indegree = {node_id: len(items) for node_id, items in dependencies.items()}
    ready = [node_id for node_id in node_ids if indegree[node_id] == 0]
    ready.sort(key=index.__getitem__)
    ordered: List[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(dependents[current], key=index.__getitem__):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort(key=index.__getitem__)
    if len(ordered) != len(node_ids):
        cyclic = [node_id for node_id in node_ids if indegree[node_id] > 0]
        raise RecipeValidationError(
            "recipe dependency cycle detected involving: " + ", ".join(cyclic)
        )
    return tuple(ordered)


# ----------------------------------------------------------- operation schema
_SCHEMA_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "description",
        "title",
        "default",
    }
)
_SCHEMA_TYPES = frozenset(
    {"object", "array", "string", "integer", "number", "boolean", "null"}
)


def _validate_schema_definition(schema: Any, path: str = "schema") -> None:
    """Validate the supported JSON-Schema subset at registration time."""
    if not isinstance(schema, Mapping) or not all(isinstance(key, str) for key in schema):
        raise OperationRegistrationError(f"{path} must be an object with string keys")
    unknown = set(schema) - _SCHEMA_KEYWORDS
    if unknown:
        raise OperationRegistrationError(
            f"{path} has unsupported keyword(s): {', '.join(sorted(unknown))}"
        )
    expected = schema.get("type")
    if expected is not None:
        types = [expected] if isinstance(expected, str) else expected
        if not isinstance(types, list) or not types or not all(
            isinstance(item, str) and item in _SCHEMA_TYPES for item in types
        ):
            raise OperationRegistrationError(
                f"{path}.type must use: {', '.join(sorted(_SCHEMA_TYPES))}"
            )
    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, Mapping) or not all(
            isinstance(key, str) for key in properties
        ):
            raise OperationRegistrationError(f"{path}.properties must be an object")
        for key, child in properties.items():
            _validate_schema_definition(child, f"{path}.properties.{key}")
    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise OperationRegistrationError(f"{path}.required must be an array of strings")
        if len(required) != len(set(required)):
            raise OperationRegistrationError(f"{path}.required contains duplicates")
    additional = schema.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        _validate_schema_definition(additional, f"{path}.additionalProperties")
    items = schema.get("items")
    if items is not None:
        _validate_schema_definition(items, f"{path}.items")
    enum = schema.get("enum")
    if enum is not None and (not isinstance(enum, list) or not enum):
        raise OperationRegistrationError(f"{path}.enum must be a non-empty array")
    for keyword in ("minItems", "maxItems", "minLength", "maxLength"):
        if keyword in schema and (
            type(schema[keyword]) is not int or schema[keyword] < 0
        ):
            raise OperationRegistrationError(f"{path}.{keyword} must be a non-negative integer")
    for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        if keyword in schema and (
            isinstance(schema[keyword], bool)
            or not isinstance(schema[keyword], (int, float))
            or not math.isfinite(float(schema[keyword]))
        ):
            raise OperationRegistrationError(f"{path}.{keyword} must be a finite number")
    if "pattern" in schema:
        if not isinstance(schema["pattern"], str):
            raise OperationRegistrationError(f"{path}.pattern must be a string")
        try:
            re.compile(schema["pattern"])
        except re.error as exc:
            raise OperationRegistrationError(f"{path}.pattern is invalid: {exc}") from exc


def _matches_schema_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "parameters") -> None:
    if not isinstance(schema, Mapping):
        raise OperationRegistrationError("operation schema must be a mapping")
    unknown_keywords = set(schema) - _SCHEMA_KEYWORDS
    if unknown_keywords:
        raise OperationRegistrationError(
            "unsupported schema keyword(s): " + ", ".join(sorted(unknown_keywords))
        )
    expected = schema.get("type")
    if expected is not None:
        types = [expected] if isinstance(expected, str) else expected
        if not isinstance(types, list) or not types or not all(isinstance(item, str) for item in types):
            raise OperationRegistrationError("schema type must be a string or array of strings")
        if not any(_matches_schema_type(value, item) for item in types):
            raise ParameterValidationError(
                f"{path} must be of type {' or '.join(types)}; got {type(value).__name__}"
            )
    if "enum" in schema and value not in schema["enum"]:
        raise ParameterValidationError(f"{path} must be one of {schema['enum']!r}")
    if "const" in schema and value != schema["const"]:
        raise ParameterValidationError(f"{path} must equal {schema['const']!r}")

    if isinstance(value, Mapping):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            raise OperationRegistrationError("object schema properties/required are malformed")
        missing = [name for name in required if name not in value]
        if missing:
            raise ParameterValidationError(
                f"{path} is missing required field(s): {', '.join(map(str, missing))}"
            )
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], f"{path}.{key}")
            elif additional is False:
                raise ParameterValidationError(f"{path} contains unknown field {key!r}")
            elif isinstance(additional, Mapping):
                _validate_schema(item, additional, f"{path}.{key}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ParameterValidationError(f"{path} must contain at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ParameterValidationError(f"{path} must contain at most {schema['maxItems']} items")
        if isinstance(schema.get("items"), Mapping):
            for index, item in enumerate(value):
                _validate_schema(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ParameterValidationError(f"{path} is shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ParameterValidationError(f"{path} is longer than {schema['maxLength']}")
        if "pattern" in schema and re.search(str(schema["pattern"]), value) is None:
            raise ParameterValidationError(f"{path} does not match required pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        bounds = (
            ("minimum", lambda a, b: a < b, ">="),
            ("maximum", lambda a, b: a > b, "<="),
            ("exclusiveMinimum", lambda a, b: a <= b, ">"),
            ("exclusiveMaximum", lambda a, b: a >= b, "<"),
        )
        for keyword, violates, symbol in bounds:
            if keyword in schema and violates(number, float(schema[keyword])):
                raise ParameterValidationError(f"{path} must be {symbol} {schema[keyword]}")


Validator = Callable[[Mapping[str, Any]], Any]
Executor = Callable[[Mapping[str, Any], Mapping[str, Any], "ExecutionContext"], Any]


@dataclass(frozen=True)
class OperationDefinition:
    name: str
    executor: Executor
    schema: Mapping[str, Any]
    validator: Optional[Validator] = None
    version: str = "1"
    description: str = ""

    def validate(self, parameters: Mapping[str, Any]) -> None:
        _validate_schema(parameters, self.schema)
        if self.validator is None:
            return
        try:
            result = self.validator(copy.deepcopy(dict(parameters)))
        except ParameterValidationError:
            raise
        except Exception as exc:
            raise ParameterValidationError(f"custom parameter validation failed: {exc}") from exc
        if result is False:
            raise ParameterValidationError("custom parameter validator rejected the parameters")
        if isinstance(result, str) and result:
            raise ParameterValidationError(result)
        if isinstance(result, Sequence) and not isinstance(result, (str, bytes)) and result:
            raise ParameterValidationError("; ".join(str(item) for item in result))


class OperationRegistry:
    """Explicit operation allow-list shared by UI and batch execution."""

    def __init__(self) -> None:
        self._operations: Dict[str, OperationDefinition] = {}

    def register(
        self,
        name: str,
        executor: Optional[Executor] = None,
        *,
        schema: Optional[Mapping[str, Any]] = None,
        validator: Optional[Validator] = None,
        version: str | int = "1",
        description: str = "",
        replace_existing: bool = False,
    ) -> OperationDefinition | Callable[[Executor], Executor]:
        """Register directly or act as a decorator when executor is omitted."""
        operation_name = _identifier(name, "operation name")
        operation_schema = schema if schema is not None else {
            "type": "object",
            "additionalProperties": True,
        }
        _config_json_safe(operation_schema, "operation schema")
        # Validate the schema shape/keywords independently of real parameters.
        if not isinstance(operation_schema, Mapping):
            raise OperationRegistrationError("operation schema must be a mapping")
        _validate_schema_definition(operation_schema)

        if executor is None:
            def decorator(function: Executor) -> Executor:
                self.register(
                    operation_name,
                    function,
                    schema=operation_schema,
                    validator=validator,
                    version=version,
                    description=description,
                    replace_existing=replace_existing,
                )
                return function

            return decorator

        if not callable(executor):
            raise OperationRegistrationError("operation executor must be callable")
        if validator is not None and not callable(validator):
            raise OperationRegistrationError("operation validator must be callable")
        if operation_name in self._operations and not replace_existing:
            raise OperationRegistrationError(f"operation {operation_name!r} is already registered")
        operation_version = str(version)
        if not operation_version:
            raise OperationRegistrationError("operation version must not be empty")
        try:
            signature = inspect.signature(executor)
            signature.bind({}, {}, None)
        except (TypeError, ValueError) as exc:
            raise OperationRegistrationError(
                "executor must accept (inputs, parameters, execution_context)"
            ) from exc
        definition = OperationDefinition(
            name=operation_name,
            executor=executor,
            schema=copy.deepcopy(dict(operation_schema)),
            validator=validator,
            version=operation_version,
            description=str(description),
        )
        self._operations[operation_name] = definition
        return definition

    operation = register

    def get(self, name: str) -> OperationDefinition:
        try:
            return self._operations[name]
        except KeyError as exc:
            raise UnknownOperationError(f"unknown operation: {name!r}") from exc

    def validate(self, name: str, parameters: Mapping[str, Any]) -> None:
        self.get(name).validate(parameters)

    def names(self) -> Tuple[str, ...]:
        return tuple(self._operations)

    def schema_for(self, name: str) -> Dict[str, Any]:
        return copy.deepcopy(dict(self.get(name).schema))

    def __contains__(self, name: object) -> bool:
        return name in self._operations

    def __len__(self) -> int:
        return len(self._operations)


# --------------------------------------------------------------- runtime API
def _cancel_requested(check: Optional[Callable[[], bool] | Any]) -> bool:
    if check is None:
        return False
    if callable(check):
        return bool(check())
    is_set = getattr(check, "is_set", None)
    if callable(is_set):
        return bool(is_set())
    raise TypeError("cancel_check must be callable or expose is_set()")


@dataclass(frozen=True)
class ExecutionContext:
    run_id: str
    node_id: str
    source_checksums: Mapping[str, str]
    _cancel_check: Optional[Callable[[], bool] | Any] = field(default=None, repr=False)

    @property
    def cancelled(self) -> bool:
        return _cancel_requested(self._cancel_check)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise ExecutionCancelled("execution cancelled")


@dataclass(frozen=True)
class NodeStateSnapshot:
    node_id: str
    status: str
    dirty: bool
    dirty_reasons: Tuple[str, ...]
    has_result: bool
    result_summary: Mapping[str, Any]
    error: Optional[str]
    last_success: Optional[NodeProvenance]
    last_attempt: Optional[NodeProvenance]

    @property
    def stale(self) -> bool:
        return self.dirty and self.has_result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "dirty": self.dirty,
            "dirty_reasons": list(self.dirty_reasons),
            "has_result": self.has_result,
            "stale": self.stale,
            "result_summary": _json_safe(self.result_summary),
            "error": self.error,
            "last_success": self.last_success.to_dict() if self.last_success else None,
            "last_attempt": self.last_attempt.to_dict() if self.last_attempt else None,
        }


@dataclass
class _NodeRuntimeState:
    status: str = "dirty"
    dirty: bool = True
    dirty_reasons: List[str] = field(default_factory=lambda: ["not yet calculated"])
    outputs: Dict[str, Any] = field(default_factory=dict)
    result_summary: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    last_success: Optional[NodeProvenance] = None
    last_attempt: Optional[NodeProvenance] = None


@dataclass(frozen=True)
class ExecutionReport:
    run_id: str
    requested_targets: Tuple[str, ...]
    executed: Tuple[str, ...]
    skipped: Mapping[str, str]
    blocked: Mapping[str, str]
    failed: Mapping[str, str]
    cancelled: bool
    started_at: str
    finished_at: str

    @property
    def ok(self) -> bool:
        return not self.failed and not self.blocked and not self.cancelled

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "requested_targets": list(self.requested_targets),
            "executed": list(self.executed),
            "skipped": dict(self.skipped),
            "blocked": dict(self.blocked),
            "failed": dict(self.failed),
            "cancelled": self.cancelled,
            "ok": self.ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def summarize_result(value: Any) -> Dict[str, Any]:
    """Return a bounded JSON-safe audit summary without embedding full data."""
    if isinstance(value, pd.DataFrame):
        return {
            "kind": "dataframe",
            "rows": int(value.shape[0]),
            "columns": int(value.shape[1]),
            "column_names": [str(item) for item in value.columns[:100]],
            "column_names_truncated": value.shape[1] > 100,
            "dtypes": {str(column): str(dtype) for column, dtype in zip(value.columns[:100], value.dtypes[:100])},
            "memory_bytes": int(value.memory_usage(index=True, deep=True).sum()),
            "checksum": dataframe_checksum(value),
        }
    safe = _json_safe(value, "result")
    if isinstance(safe, Mapping):
        keys = list(safe)[:100]
        return {
            "kind": "mapping",
            "keys": keys,
            "size": len(safe),
            "keys_truncated": len(safe) > 100,
            "checksum": _canonical_hash(safe),
        }
    return {"kind": "scalar", "type": type(safe).__name__, "value": safe}


class AnalysisRecipeEngine:
    """Execute a recipe deterministically while retaining last-good results."""

    def __init__(self, recipe: AnalysisRecipe, registry: OperationRegistry):
        if not isinstance(recipe, AnalysisRecipe):
            raise TypeError("recipe must be an AnalysisRecipe")
        if not isinstance(registry, OperationRegistry):
            raise TypeError("registry must be an OperationRegistry")
        self.recipe = recipe
        self.registry = registry
        self._order = _validate_recipe_graph(recipe)
        self._nodes = {node.node_id: node for node in recipe.nodes}
        self._dependents: Dict[str, List[str]] = {node_id: [] for node_id in self._order}
        self._source_consumers: Dict[str, List[str]] = {}
        for node in recipe.nodes:
            for binding in node.inputs:
                if binding.kind == "node":
                    if node.node_id not in self._dependents[binding.source_id]:
                        self._dependents[binding.source_id].append(node.node_id)
                else:
                    self._source_consumers.setdefault(binding.source_id, []).append(node.node_id)
        index = {node_id: number for number, node_id in enumerate(self._order)}
        for children in self._dependents.values():
            children.sort(key=index.__getitem__)
        self._sources: Dict[str, pd.DataFrame] = {}
        self._source_checksums: Dict[str, str] = {}
        self._states = {node_id: _NodeRuntimeState() for node_id in self._order}
        latest_attempt: Dict[str, NodeProvenance] = {}
        latest_success: Dict[str, NodeProvenance] = {}
        for item in recipe.provenance:
            latest_attempt[item.node_id] = item
            if item.success:
                latest_success[item.node_id] = item
        for node_id, provenance in latest_attempt.items():
            if node_id in self._states:
                self._states[node_id].last_attempt = provenance
                if not provenance.success:
                    self._states[node_id].status = "error"
                    self._states[node_id].error = provenance.error
        for node_id, provenance in latest_success.items():
            if node_id in self._states:
                self._states[node_id].last_success = provenance
                self._states[node_id].result_summary = copy.deepcopy(
                    dict(provenance.result_summary)
                )

    @property
    def topological_order(self) -> Tuple[str, ...]:
        return self._order

    @property
    def source_ids(self) -> Tuple[str, ...]:
        return tuple(self._source_checksums)

    def fork(self) -> "AnalysisRecipeEngine":
        """Return an isolated copy of this engine, including runtime cache.

        Desktop workers use a fork so a long calculation can run away from the
        GUI thread without mutating the live recipe/cache.  The caller may
        commit the fork after checking that its source generation is still
        current, or discard it when a newer edit supersedes the job.
        """

        clone = AnalysisRecipeEngine(
            AnalysisRecipe.from_dict(self.recipe.to_dict()),
            self.registry,
        )
        clone._sources = {
            source_id: frame.copy(deep=True)
            for source_id, frame in self._sources.items()
        }
        clone._source_checksums = dict(self._source_checksums)
        clone._states = {}
        for node_id, state in self._states.items():
            clone._states[node_id] = _NodeRuntimeState(
                status=state.status,
                dirty=state.dirty,
                dirty_reasons=list(state.dirty_reasons),
                outputs={
                    name: _copy_runtime_value(value)
                    for name, value in state.outputs.items()
                },
                result_summary=copy.deepcopy(state.result_summary),
                error=state.error,
                last_success=copy.deepcopy(state.last_success),
                last_attempt=copy.deepcopy(state.last_attempt),
            )
        return clone

    def source_checksum(self, source_id: str) -> str:
        try:
            return self._source_checksums[source_id]
        except KeyError as exc:
            raise MissingSourceError(f"missing source DataFrame: {source_id!r}") from exc

    def set_source(
        self,
        source_id: str,
        frame: pd.DataFrame,
        *,
        auto_run: bool = True,
        cancel_check: Optional[Callable[[], bool] | Any] = None,
    ) -> Optional[ExecutionReport]:
        source_id = _identifier(source_id, "source_id")
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("source must be a pandas DataFrame")
        snapshot = frame.copy(deep=True)
        checksum = dataframe_checksum(snapshot)
        changed = self._source_checksums.get(source_id) != checksum
        self._sources[source_id] = snapshot
        self._source_checksums[source_id] = checksum
        consumers = self._source_consumers.get(source_id, [])
        if changed:
            for node_id in consumers:
                self.mark_dirty(node_id, f"source {source_id!r} changed")
        affected = self._affected_nodes(consumers)
        return self._auto_run(cancel_check, affected) if changed and auto_run else None

    def remove_source(
        self, source_id: str, *, auto_run: bool = False
    ) -> Optional[ExecutionReport]:
        existed = source_id in self._sources
        self._sources.pop(source_id, None)
        self._source_checksums.pop(source_id, None)
        consumers = self._source_consumers.get(source_id, [])
        if existed:
            for node_id in consumers:
                self.mark_dirty(node_id, f"source {source_id!r} removed")
        return self._auto_run(None, self._affected_nodes(consumers)) if existed and auto_run else None

    def update_node_params(
        self,
        node_id: str,
        parameters: Mapping[str, Any],
        *,
        auto_run: bool = True,
        cancel_check: Optional[Callable[[], bool] | Any] = None,
    ) -> Optional[ExecutionReport]:
        node = self._node(node_id)
        if not isinstance(parameters, Mapping) or not all(isinstance(key, str) for key in parameters):
            raise RecipeValidationError("node parameters must be an object with string keys")
        safe = _config_json_safe(dict(parameters), "parameters")
        if _canonical_hash(safe) == _canonical_hash(node.parameters):
            return None
        replacement = replace(node, parameters=safe)
        self._replace_node(replacement)
        self.mark_dirty(node_id, "parameters changed")
        return self._auto_run(cancel_check, self._affected_nodes((node_id,))) if auto_run else None

    def set_recalculation_mode(
        self, node_id: str, mode: RecalculationMode | str
    ) -> None:
        node = self._node(node_id)
        self._replace_node(replace(node, recalculation_mode=RecalculationMode.parse(mode)))

    set_mode = set_recalculation_mode

    def mark_dirty(self, node_id: str, reason: str = "invalidated", *, propagate: bool = True) -> None:
        self._node(node_id)
        if not isinstance(reason, str) or not reason:
            raise ValueError("dirty reason must be a non-empty string")
        queue = deque([node_id])
        visited: set[str] = set()
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            state = self._states[current]
            state.dirty = True
            state.status = "dirty"
            state.error = None
            current_reason = reason if current == node_id else f"dependency {node_id!r} changed"
            if current_reason not in state.dirty_reasons:
                state.dirty_reasons.append(current_reason)
            if propagate:
                queue.extend(self._dependents[current])

    def _affected_nodes(self, roots: Iterable[str]) -> set[str]:
        affected: set[str] = set()
        queue = deque(roots)
        while queue:
            current = queue.popleft()
            if current in affected:
                continue
            affected.add(current)
            queue.extend(self._dependents.get(current, ()))
        return affected

    def get_state(self, node_id: str) -> NodeStateSnapshot:
        self._node(node_id)
        state = self._states[node_id]
        return NodeStateSnapshot(
            node_id=node_id,
            status=state.status,
            dirty=state.dirty,
            dirty_reasons=tuple(state.dirty_reasons),
            has_result=bool(state.outputs),
            result_summary=copy.deepcopy(state.result_summary),
            error=state.error,
            last_success=state.last_success,
            last_attempt=state.last_attempt,
        )

    def list_states(self) -> Tuple[NodeStateSnapshot, ...]:
        return tuple(self.get_state(node_id) for node_id in self._order)

    def get_result(
        self, node_id: str, output: str = "result", *, require_fresh: bool = False
    ) -> Any:
        self._node(node_id)
        state = self._states[node_id]
        if require_fresh and state.dirty:
            raise AnalysisRecipeError(f"result for node {node_id!r} is stale")
        if output not in state.outputs:
            available = ", ".join(state.outputs) or "none"
            raise AnalysisRecipeError(
                f"node {node_id!r} has no cached output {output!r}; available: {available}"
            )
        return _copy_runtime_value(state.outputs[output])

    def run(
        self,
        targets: Optional[Iterable[str] | str] = None,
        *,
        force: bool = False,
        cancel_check: Optional[Callable[[], bool] | Any] = None,
        raise_on_error: bool = False,
    ) -> ExecutionReport:
        return self._run(
            targets=targets,
            force=force,
            cancel_check=cancel_check,
            raise_on_error=raise_on_error,
            auto_only=False,
        )

    def recalculate(
        self,
        targets: Optional[Iterable[str] | str] = None,
        *,
        force: bool = False,
        cancel_check: Optional[Callable[[], bool] | Any] = None,
        raise_on_error: bool = False,
    ) -> ExecutionReport:
        return self.run(
            targets, force=force, cancel_check=cancel_check, raise_on_error=raise_on_error
        )

    def run_auto(
        self,
        targets: Optional[Iterable[str] | str] = None,
        *,
        cancel_check: Optional[Callable[[], bool] | Any] = None,
        raise_on_error: bool = False,
    ) -> ExecutionReport:
        """Run only dirty nodes configured for automatic recalculation.

        Manual/Frozen dependencies remain cached or block their dependants;
        this is the public counterpart of source-triggered auto execution for
        desktop schedulers that supply all sources as one atomic snapshot.
        """

        return self._run(
            targets=targets,
            force=False,
            cancel_check=cancel_check,
            raise_on_error=raise_on_error,
            auto_only=True,
        )

    def save(self, path: str | os.PathLike[str]) -> Path:
        return self.recipe.save(path)

    def _node(self, node_id: str) -> RecipeNode:
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise RecipeValidationError(f"unknown node: {node_id!r}") from exc

    def _replace_node(self, node: RecipeNode) -> None:
        self._nodes[node.node_id] = node
        for index, current in enumerate(self.recipe.nodes):
            if current.node_id == node.node_id:
                self.recipe.nodes[index] = node
                break
        self.recipe.updated_at = _utc_now()

    def _auto_run(
        self,
        cancel_check: Optional[Callable[[], bool] | Any],
        candidates: Optional[set[str]] = None,
    ) -> Optional[ExecutionReport]:
        targets = [
            node_id
            for node_id in self._order
            if self._states[node_id].dirty
            and self._nodes[node_id].recalculation_mode == RecalculationMode.AUTO
            and (candidates is None or node_id in candidates)
        ]
        if not targets:
            return None
        return self._run(
            targets=targets,
            force=False,
            cancel_check=cancel_check,
            raise_on_error=False,
            auto_only=True,
        )

    def _selected(self, targets: Optional[Iterable[str] | str]) -> Tuple[Tuple[str, ...], set[str]]:
        if targets is None:
            requested = self._order
        elif isinstance(targets, str):
            requested = (targets,)
        else:
            requested = tuple(targets)
        if not requested:
            return (), set()
        for node_id in requested:
            self._node(node_id)
        selected: set[str] = set()

        def include(node_id: str) -> None:
            if node_id in selected:
                return
            selected.add(node_id)
            for binding in self._nodes[node_id].inputs:
                if binding.kind == "node":
                    include(binding.source_id)

        for node_id in requested:
            include(node_id)
        return requested, selected

    def _run(
        self,
        *,
        targets: Optional[Iterable[str] | str],
        force: bool,
        cancel_check: Optional[Callable[[], bool] | Any],
        raise_on_error: bool,
        auto_only: bool,
    ) -> ExecutionReport:
        requested, selected = self._selected(targets)
        run_id = uuid.uuid4().hex
        started_at = _utc_now()
        executed: List[str] = []
        skipped: Dict[str, str] = {}
        blocked: Dict[str, str] = {}
        failed: Dict[str, str] = {}
        cancelled = False
        first_error: Optional[NodeExecutionError] = None

        for node_id in self._order:
            if node_id not in selected:
                continue
            node = self._nodes[node_id]
            state = self._states[node_id]
            if _cancel_requested(cancel_check):
                cancelled = True
                break
            if not node.enabled:
                skipped[node_id] = "disabled"
                continue
            if auto_only and state.dirty and node.recalculation_mode != RecalculationMode.AUTO:
                skipped[node_id] = f"{node.recalculation_mode.value} recalculation mode"
                continue
            if node.recalculation_mode == RecalculationMode.FROZEN and not force:
                skipped[node_id] = "frozen recalculation mode"
                continue
            if not state.dirty and not force:
                skipped[node_id] = "clean"
                continue

            unavailable = self._unavailable_dependencies(node)
            if unavailable:
                reason = "; ".join(unavailable)
                blocked[node_id] = reason
                state.status = "blocked"
                state.error = reason
                continue

            started_clock = time.perf_counter()
            node_started = _utc_now()
            state.status = "running"
            state.error = None
            definition: Optional[OperationDefinition] = None
            source_checksums: Dict[str, str] = {}
            dependency_runs: Dict[str, str] = {}
            try:
                definition = self.registry.get(node.operation)
                definition.validate(node.parameters)
                inputs = self._resolve_inputs(node, source_checksums, dependency_runs)
                context = ExecutionContext(
                    run_id=run_id,
                    node_id=node_id,
                    source_checksums=dict(source_checksums),
                    _cancel_check=cancel_check,
                )
                context.raise_if_cancelled()
                raw_result = definition.executor(
                    inputs,
                    copy.deepcopy(dict(node.parameters)),
                    context,
                )
                context.raise_if_cancelled()
                outputs = self._coerce_outputs(node, raw_result)
                summaries = {name: summarize_result(value) for name, value in outputs.items()}
                provenance = self._provenance(
                    run_id=run_id,
                    node=node,
                    definition=definition,
                    started_at=node_started,
                    started_clock=started_clock,
                    success=True,
                    source_checksums=source_checksums,
                    dependency_runs=dependency_runs,
                    result_summary=summaries,
                    error=None,
                )
                # Commit only after validation, summaries, and provenance all succeed.
                state.outputs = outputs
                state.result_summary = summaries
                state.last_success = provenance
                state.last_attempt = provenance
                state.dirty = False
                state.dirty_reasons.clear()
                state.status = "clean"
                state.error = None
                self.recipe.provenance.append(provenance)
                self.recipe.updated_at = provenance.finished_at
                executed.append(node_id)
            except ExecutionCancelled as exc:
                cancelled = True
                error_text = str(exc) or "execution cancelled"
                provenance = self._provenance(
                    run_id=run_id,
                    node=node,
                    definition=definition,
                    started_at=node_started,
                    started_clock=started_clock,
                    success=False,
                    source_checksums=source_checksums,
                    dependency_runs=dependency_runs,
                    result_summary=state.result_summary,
                    error=f"ExecutionCancelled: {error_text}",
                )
                state.last_attempt = provenance
                state.status = "cancelled"
                state.error = error_text
                state.dirty = True
                if "execution cancelled" not in state.dirty_reasons:
                    state.dirty_reasons.append("execution cancelled")
                self.recipe.provenance.append(provenance)
                self.recipe.updated_at = provenance.finished_at
                break
            except Exception as exc:  # state-safe boundary around third-party operations
                error_text = f"{type(exc).__name__}: {exc}"
                failed[node_id] = error_text
                provenance = self._provenance(
                    run_id=run_id,
                    node=node,
                    definition=definition,
                    started_at=node_started,
                    started_clock=started_clock,
                    success=False,
                    source_checksums=source_checksums,
                    dependency_runs=dependency_runs,
                    result_summary=state.result_summary,
                    error=error_text,
                )
                # Deliberately retain outputs/result_summary/last_success.
                state.last_attempt = provenance
                state.status = "error"
                state.error = error_text
                state.dirty = True
                failure_reason = f"last recomputation failed: {error_text}"
                if failure_reason not in state.dirty_reasons:
                    state.dirty_reasons.append(failure_reason)
                self.recipe.provenance.append(provenance)
                self.recipe.updated_at = provenance.finished_at
                if first_error is None:
                    first_error = NodeExecutionError(node_id, error_text, exc)

        report = ExecutionReport(
            run_id=run_id,
            requested_targets=requested,
            executed=tuple(executed),
            skipped=skipped,
            blocked=blocked,
            failed=failed,
            cancelled=cancelled,
            started_at=started_at,
            finished_at=_utc_now(),
        )
        if raise_on_error and first_error is not None:
            raise first_error
        return report

    def _unavailable_dependencies(self, node: RecipeNode) -> List[str]:
        reasons: List[str] = []
        for binding in node.inputs:
            if binding.kind == "source":
                if binding.source_id not in self._sources:
                    reasons.append(f"missing source {binding.source_id!r}")
                continue
            dependency = self._states[binding.source_id]
            if binding.output not in dependency.outputs:
                reasons.append(
                    f"dependency {binding.source_id!r} has no cached output {binding.output!r}"
                )
            elif dependency.dirty:
                reasons.append(f"dependency {binding.source_id!r} is stale")
        return reasons

    def _resolve_inputs(
        self,
        node: RecipeNode,
        source_checksums: Dict[str, str],
        dependency_runs: Dict[str, str],
    ) -> Dict[str, Any]:
        inputs: Dict[str, Any] = {}
        for binding in node.inputs:
            if binding.kind == "source":
                if binding.source_id not in self._sources:
                    raise MissingSourceError(f"missing source DataFrame: {binding.source_id!r}")
                source_checksums[binding.source_id] = self._source_checksums[binding.source_id]
                inputs[binding.name] = self._sources[binding.source_id].copy(deep=True)
            else:
                state = self._states[binding.source_id]
                if binding.output not in state.outputs:
                    raise AnalysisRecipeError(
                        f"dependency {binding.source_id!r} has no output {binding.output!r}"
                    )
                if state.last_success is not None:
                    dependency_runs[binding.source_id] = state.last_success.run_id
                    for source_id, checksum in state.last_success.source_checksums.items():
                        previous = source_checksums.get(source_id)
                        if previous is not None and previous != checksum:
                            raise AnalysisRecipeError(
                                f"dependencies disagree on checksum for source {source_id!r}"
                            )
                        source_checksums[source_id] = checksum
                inputs[binding.name] = _copy_runtime_value(state.outputs[binding.output])
        return inputs

    @staticmethod
    def _coerce_outputs(node: RecipeNode, raw_result: Any) -> Dict[str, Any]:
        if len(node.outputs) == 1:
            spec = node.outputs[0]
            values = {spec.name: raw_result}
        else:
            if not isinstance(raw_result, Mapping):
                raise ResultValidationError(
                    f"node {node.node_id!r} declares multiple outputs; executor must return a mapping"
                )
            expected = {output.name for output in node.outputs}
            actual = set(raw_result)
            if not all(isinstance(key, str) for key in raw_result):
                raise ResultValidationError("multi-output result keys must be strings")
            if expected != actual:
                missing = sorted(expected - actual)
                extra = sorted(actual - expected)
                details = []
                if missing:
                    details.append("missing " + ", ".join(missing))
                if extra:
                    details.append("unexpected " + ", ".join(extra))
                raise ResultValidationError("multi-output result mismatch: " + "; ".join(details))
            values = dict(raw_result)

        outputs: Dict[str, Any] = {}
        for spec in node.outputs:
            value = values[spec.name]
            if isinstance(value, pd.DataFrame):
                normalised = value.copy(deep=True)
                actual_kind = "dataframe"
            else:
                normalised = _json_safe(value, f"result.{spec.name}")
                actual_kind = "mapping" if isinstance(normalised, Mapping) else "scalar"
                if isinstance(normalised, list):
                    # Lists are valid inside a JSON mapping but are intentionally
                    # not a root result type in the public recipe contract.
                    raise ResultValidationError(
                        f"result.{spec.name} must be a DataFrame, mapping, or scalar"
                    )
            if spec.kind != "any" and spec.kind != actual_kind:
                raise ResultValidationError(
                    f"output {spec.name!r} expected {spec.kind}, got {actual_kind}"
                )
            outputs[spec.name] = normalised
        return outputs

    @staticmethod
    def _provenance(
        *,
        run_id: str,
        node: RecipeNode,
        definition: Optional[OperationDefinition],
        started_at: str,
        started_clock: float,
        success: bool,
        source_checksums: Mapping[str, str],
        dependency_runs: Mapping[str, str],
        result_summary: Mapping[str, Any],
        error: Optional[str],
    ) -> NodeProvenance:
        return NodeProvenance(
            run_id=run_id,
            node_id=node.node_id,
            operation=node.operation,
            operation_version=definition.version if definition else "unknown",
            started_at=started_at,
            finished_at=_utc_now(),
            duration_ms=max(0.0, (time.perf_counter() - started_clock) * 1000.0),
            success=success,
            parameter_checksum=_canonical_hash(node.parameters),
            source_checksums=dict(source_checksums),
            dependency_runs=dict(dependency_runs),
            result_summary=copy.deepcopy(dict(result_summary)),
            error=error,
        )


__all__ = [
    "RECIPE_FORMAT",
    "RECIPE_VERSION",
    "AnalysisRecipe",
    "AnalysisRecipeEngine",
    "AnalysisRecipeError",
    "ExecutionCancelled",
    "ExecutionContext",
    "ExecutionReport",
    "MissingSourceError",
    "NodeExecutionError",
    "NodeProvenance",
    "NodeStateSnapshot",
    "OperationDefinition",
    "OperationRegistrationError",
    "OperationRegistry",
    "ParameterValidationError",
    "RecalculationMode",
    "RecipeFormatError",
    "RecipeInput",
    "RecipeNode",
    "RecipeOutput",
    "RecipeValidationError",
    "ResultValidationError",
    "dataframe_checksum",
    "summarize_result",
]
