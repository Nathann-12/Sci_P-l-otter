"""Pure line-oriented parser for gas-sensor serial acquisition.

The protocol is intentionally small: a session is either newline-delimited
JSON objects or CSV with one header row.  The first non-empty line chooses the
mode and the schema remains stable until :meth:`SerialFrameParser.reset`.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
import io
import json
from typing import Any


@dataclass
class SerialParseBatch:
    records: list[dict[str, Any]] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _csv_value(text: str) -> Any:
    value = text.strip()
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer() and not any(mark in value.lower() for mark in (".", "e")):
        return int(number)
    return number


def _unique_headers(values: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    headers: list[str] = []
    for index, raw in enumerate(values, start=1):
        base = raw.strip() or f"column_{index}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        headers.append(base if count == 0 else f"{base}.{count}")
    return headers


class SerialFrameParser:
    """Incrementally parse UTF-8 bytes into stable-schema records."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._buffer = bytearray()
        self.mode: str | None = None
        self.schema: tuple[str, ...] = ()

    def feed(self, data: bytes | bytearray | str) -> SerialParseBatch:
        if isinstance(data, str):
            incoming = data.encode("utf-8")
        else:
            incoming = bytes(data)
        self._buffer.extend(incoming)
        batch = SerialParseBatch()
        while b"\n" in self._buffer:
            raw, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            self._parse_line(raw.rstrip(b"\r"), batch)
        return batch

    def flush(self) -> SerialParseBatch:
        batch = SerialParseBatch()
        if self._buffer:
            raw = bytes(self._buffer).rstrip(b"\r")
            self._buffer.clear()
            self._parse_line(raw, batch)
        return batch

    def _parse_line(self, raw: bytes, batch: SerialParseBatch) -> None:
        try:
            line = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            line = raw.decode("utf-8", errors="replace")
            batch.raw_lines.append(line)
            batch.errors.append(f"UTF-8 decode error: {exc}")
            return
        line = line.strip()
        if not line:
            return
        batch.raw_lines.append(line)
        if self.mode is None:
            self.mode = "json" if line.startswith("{") else "csv"
        if self.mode == "json":
            self._parse_json(line, batch)
        else:
            self._parse_csv(line, batch)

    def _parse_json(self, line: str, batch: SerialParseBatch) -> None:
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            batch.errors.append(f"Invalid JSON: {exc.msg}")
            return
        if not isinstance(value, dict):
            batch.errors.append("JSON record must be an object")
            return
        scalars = {str(key): item for key, item in value.items() if _scalar(item)}
        if not any(_number(item) for item in scalars.values()):
            batch.errors.append("JSON record needs at least one numeric field")
            return
        if not self.schema:
            self.schema = tuple(scalars.keys())
        extras = [key for key in scalars if key not in self.schema]
        if extras:
            batch.errors.append("Schema changed; ignored field(s): " + ", ".join(extras))
        batch.records.append({key: scalars.get(key) for key in self.schema})

    def _parse_csv(self, line: str, batch: SerialParseBatch) -> None:
        try:
            row = next(csv.reader(io.StringIO(line)))
        except (csv.Error, StopIteration) as exc:
            batch.errors.append(f"Invalid CSV: {exc}")
            return
        if not self.schema:
            if not row:
                batch.errors.append("CSV header is empty")
                return
            self.schema = tuple(_unique_headers(row))
            return
        if len(row) != len(self.schema):
            batch.errors.append(
                f"CSV row has {len(row)} values; expected {len(self.schema)}"
            )
            return
        record = {key: _csv_value(item) for key, item in zip(self.schema, row)}
        if not any(_number(item) for item in record.values()):
            batch.errors.append("CSV record needs at least one numeric field")
            return
        batch.records.append(record)
