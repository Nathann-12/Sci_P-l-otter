"""Pure record processing for the Gas Sensor visual acquisition flow."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable


_META_FIELDS = {"elapsed_s", "gas_state", "event"}
FLOW_NODE_IDS = ("source", "divider", "smooth", "book", "graph")
DEFAULT_FLOW_WIRING = (
    ("source", "divider"),
    ("divider", "smooth"),
    ("smooth", "book"),
    ("book", "graph"),
)


def validate_flow_wiring(
    edges: Iterable[Iterable[str]],
) -> tuple[tuple[str, str], ...]:
    """Validate the fixed-port visual graph and return normalized edges."""
    normalized: list[tuple[str, str]] = []
    for raw in edges:
        try:
            source, target = tuple(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Each flow wire must contain one source and one target.") from exc
        source, target = str(source), str(target)
        if source not in FLOW_NODE_IDS or target not in FLOW_NODE_IDS:
            raise ValueError(f"Unknown flow node in wire: {source} → {target}.")
        if source == target:
            raise ValueError("A flow node cannot connect to itself.")
        edge = (source, target)
        if edge not in normalized:
            normalized.append(edge)
    if any(target == "source" for _source, target in normalized):
        raise ValueError("The acquisition input cannot have an incoming wire.")
    if any(source == "graph" for source, _target in normalized):
        raise ValueError("The rolling graph cannot have an outgoing wire.")
    incoming: dict[str, int] = {node: 0 for node in FLOW_NODE_IDS}
    outgoing: dict[str, list[str]] = {node: [] for node in FLOW_NODE_IDS}
    for source, target in normalized:
        incoming[target] += 1
        outgoing[source].append(target)
    if any(incoming[node] > 1 for node in FLOW_NODE_IDS if node != "source"):
        raise ValueError("Each flow input port accepts only one wire.")

    pending = dict(incoming)
    queue = [node for node in FLOW_NODE_IDS if pending[node] == 0]
    visited = []
    while queue:
        node = queue.pop(0)
        visited.append(node)
        for target in outgoing[node]:
            pending[target] -= 1
            if pending[target] == 0:
                queue.append(target)
    if len(visited) != len(FLOW_NODE_IDS):
        raise ValueError("Flow wiring contains a loop.")

    reachable = {"source"}
    frontier = ["source"]
    while frontier:
        node = frontier.pop()
        for target in outgoing[node]:
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    if "book" not in reachable or "graph" not in reachable:
        raise ValueError("Flow input must reach both Live Book and Rolling Graph.")
    return tuple(normalized)


def flow_wiring_order(edges: Iterable[Iterable[str]]) -> tuple[str, ...]:
    wiring = validate_flow_wiring(edges)
    incoming: dict[str, int] = {node: 0 for node in FLOW_NODE_IDS}
    outgoing: dict[str, list[str]] = {node: [] for node in FLOW_NODE_IDS}
    for source, target in wiring:
        incoming[target] += 1
        outgoing[source].append(target)
    reachable = {"source"}
    frontier = ["source"]
    while frontier:
        node = frontier.pop()
        for target in outgoing[node]:
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    reverse: dict[str, list[str]] = {node: [] for node in FLOW_NODE_IDS}
    for source, target in wiring:
        reverse[target].append(source)
    productive = {"graph"}
    frontier = ["graph"]
    while frontier:
        node = frontier.pop()
        for source in reverse[node]:
            if source not in productive:
                productive.add(source)
                frontier.append(source)
    queue = [node for node in FLOW_NODE_IDS if incoming[node] == 0]
    order = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for target in outgoing[node]:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    return tuple(node for node in order if node in reachable and node in productive)


@dataclass(frozen=True)
class GasSensorChannelConfig:
    """Independent processing settings for one physical sensor channel."""

    source_field: str
    alias: str
    voltage_to_resistance: bool = False
    supply_voltage_v: float = 5.0
    reference_resistance_ohm: float = 10_000.0
    divider_topology: str = "sensor_high"
    smoothing: bool = False
    smoothing_window: int = 5

    def validated(self) -> "GasSensorChannelConfig":
        source = str(self.source_field or "").strip()
        alias = str(self.alias or "").strip()
        if not source:
            raise ValueError("Sensor source field cannot be empty.")
        if not alias:
            raise ValueError("Sensor display name cannot be empty.")
        supply = float(self.supply_voltage_v)
        reference = float(self.reference_resistance_ohm)
        window = int(self.smoothing_window)
        topology = str(self.divider_topology).strip().lower()
        if not math.isfinite(supply) or supply <= 0:
            raise ValueError("Sensor supply voltage must be greater than zero.")
        if not math.isfinite(reference) or reference <= 0:
            raise ValueError("Sensor reference resistance must be greater than zero.")
        if topology not in {"sensor_high", "sensor_low"}:
            raise ValueError("Sensor divider topology must be sensor_high or sensor_low.")
        if not 1 <= window <= 10_000:
            raise ValueError("Sensor moving-average window must be between 1 and 10000.")
        return GasSensorChannelConfig(
            source_field=source,
            alias=alias,
            voltage_to_resistance=bool(self.voltage_to_resistance),
            supply_voltage_v=supply,
            reference_resistance_ohm=reference,
            divider_topology=topology,
            smoothing=bool(self.smoothing),
            smoothing_window=window,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.validated())

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "GasSensorChannelConfig":
        source = values if isinstance(values, dict) else {}
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in source.items() if key in allowed}).validated()

    @property
    def resistance_field(self) -> str:
        return f"{self.alias} resistance_ohm"

    @property
    def output_field(self) -> str:
        base = self.resistance_field if self.voltage_to_resistance else self.alias
        return f"{base}_ma{self.smoothing_window}" if self.smoothing else base


@dataclass(frozen=True)
class GasFlowConfig:
    voltage_to_resistance: bool = False
    voltage_field: str = ""
    supply_voltage_v: float = 5.0
    reference_resistance_ohm: float = 10_000.0
    divider_topology: str = "sensor_high"
    smoothing: bool = False
    smoothing_field: str = "resistance_ohm"
    smoothing_window: int = 5
    sensor_channels: tuple[GasSensorChannelConfig, ...] = ()

    def validated(self) -> "GasFlowConfig":
        supply = float(self.supply_voltage_v)
        reference = float(self.reference_resistance_ohm)
        window = int(self.smoothing_window)
        topology = str(self.divider_topology).strip().lower()
        if not math.isfinite(supply) or supply <= 0:
            raise ValueError("Supply voltage must be greater than zero.")
        if not math.isfinite(reference) or reference <= 0:
            raise ValueError("Reference resistance must be greater than zero.")
        if topology not in {"sensor_high", "sensor_low"}:
            raise ValueError("Divider topology must be sensor_high or sensor_low.")
        if not 1 <= window <= 10_000:
            raise ValueError("Moving-average window must be between 1 and 10000.")
        channels = tuple(
            channel.validated()
            if isinstance(channel, GasSensorChannelConfig)
            else GasSensorChannelConfig.from_dict(channel)
            for channel in self.sensor_channels
        )
        sources = [channel.source_field.casefold() for channel in channels]
        aliases = [channel.alias.casefold() for channel in channels]
        if len(sources) != len(set(sources)):
            raise ValueError("Each sensor source field can only be configured once.")
        if len(aliases) != len(set(aliases)):
            raise ValueError("Sensor display names must be unique.")
        return GasFlowConfig(
            voltage_to_resistance=bool(self.voltage_to_resistance),
            voltage_field=str(self.voltage_field or "").strip(),
            supply_voltage_v=supply,
            reference_resistance_ohm=reference,
            divider_topology=topology,
            smoothing=bool(self.smoothing),
            smoothing_field=str(self.smoothing_field or "").strip(),
            smoothing_window=window,
            sensor_channels=channels,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.validated())

    @classmethod
    def from_dict(cls, values: dict[str, Any] | None) -> "GasFlowConfig":
        source = values if isinstance(values, dict) else {}
        allowed = {field for field in cls.__dataclass_fields__}
        normalized = {key: value for key, value in source.items() if key in allowed}
        raw_channels = normalized.get("sensor_channels", ())
        normalized["sensor_channels"] = tuple(
            item if isinstance(item, GasSensorChannelConfig)
            else GasSensorChannelConfig.from_dict(item)
            for item in (raw_channels or ())
        )
        return cls(**normalized).validated()


class GasFlowProcessor:
    """Apply enabled nodes to dictionaries while preserving every input row."""

    def __init__(
        self,
        config: GasFlowConfig | None = None,
        wiring: Iterable[Iterable[str]] | None = None,
    ) -> None:
        self._config = (config or GasFlowConfig()).validated()
        self._wiring = validate_flow_wiring(wiring or DEFAULT_FLOW_WIRING)
        self._windows: dict[str, deque[float]] = {}

    @property
    def config(self) -> GasFlowConfig:
        return self._config

    @property
    def wiring(self) -> tuple[tuple[str, str], ...]:
        return self._wiring

    def configure(self, config: GasFlowConfig) -> None:
        self._config = config.validated()
        self.reset()

    def configure_wiring(self, edges: Iterable[Iterable[str]]) -> None:
        self._wiring = validate_flow_wiring(edges)
        self.reset()

    def reset(self) -> None:
        self._windows.clear()

    def process_records(self, records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.process_record(record) for record in records]

    def process_record(self, source: dict[str, Any]) -> dict[str, Any]:
        record = dict(source)
        config = self._config
        active_nodes = flow_wiring_order(self._wiring)
        self._process_sensor_channels(record, config, active_nodes)
        for node in active_nodes:
            if node == "divider" and config.voltage_to_resistance:
                voltage_field = self._resolve_field(
                    record, config.voltage_field, ("voltage", "volt")
                )
                voltage = self._finite_float(record.get(voltage_field)) if voltage_field else None
                record["resistance_ohm"] = self._divider_resistance(voltage, config)
            elif node == "smooth" and config.smoothing:
                preferred = config.smoothing_field
                aliases = ("resistance", "res", "ohm", "voltage", "volt")
                field = self._resolve_field(record, preferred, aliases)
                value = self._finite_float(record.get(field)) if field else None
                output = f"{field}_ma{config.smoothing_window}" if field else "signal_smoothed"
                record[output] = self._moving_average(output, value, config.smoothing_window)
        return record

    def _process_sensor_channels(
        self,
        record: dict[str, Any],
        config: GasFlowConfig,
        active_nodes: tuple[str, ...],
    ) -> None:
        """Create named, independently processed outputs without dropping raw fields."""
        for channel in config.sensor_channels:
            value = self._finite_float(record.get(channel.source_field))
            record[channel.alias] = value
            output_field = channel.alias
            if channel.voltage_to_resistance and "divider" in active_nodes:
                divider_config = GasFlowConfig(
                    supply_voltage_v=channel.supply_voltage_v,
                    reference_resistance_ohm=channel.reference_resistance_ohm,
                    divider_topology=channel.divider_topology,
                )
                output_field = channel.resistance_field
                record[output_field] = self._divider_resistance(value, divider_config)
            if channel.smoothing and "smooth" in active_nodes:
                smooth_field = f"{output_field}_ma{channel.smoothing_window}"
                record[smooth_field] = self._moving_average(
                    f"sensor:{channel.source_field}:{smooth_field}",
                    self._finite_float(record.get(output_field)),
                    channel.smoothing_window,
                )

    @staticmethod
    def _divider_resistance(
        voltage: float | None, config: GasFlowConfig
    ) -> float | None:
        if voltage is None or not 0.0 < voltage < config.supply_voltage_v:
            return None
        if config.divider_topology == "sensor_high":
            result = config.reference_resistance_ohm * (
                config.supply_voltage_v / voltage - 1.0
            )
        else:
            result = config.reference_resistance_ohm * voltage / (
                config.supply_voltage_v - voltage
            )
        return float(result) if math.isfinite(result) and result >= 0 else None

    def _moving_average(self, key: str, value: float | None, window: int) -> float | None:
        if value is None:
            return None
        values = self._windows.get(key)
        if values is None or values.maxlen != window:
            values = deque(maxlen=window)
            self._windows[key] = values
        values.append(value)
        return float(sum(values) / len(values))

    @staticmethod
    def _resolve_field(
        record: dict[str, Any], preferred: str, aliases: tuple[str, ...]
    ) -> str | None:
        if preferred in record:
            return preferred
        folded = {str(key).casefold(): str(key) for key in record if key not in _META_FIELDS}
        for alias in aliases:
            if alias in folded:
                return folded[alias]
        for alias in aliases:
            if len(alias) >= 3:
                for folded_name, original in folded.items():
                    if alias in folded_name:
                        return original
        return None

    @staticmethod
    def _finite_float(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
