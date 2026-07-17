"""Deterministic argument resolution for the local AI tool router.

The local model is intentionally limited to selecting a tool (or answering).
Arguments are reconstructed from the user's original text, the registered tool
schema and the active Book's real column names.  This keeps a small model from
inventing columns, thresholds or device settings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from ai.tool_registry import AITool


_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
_QUOTED_RE = re.compile(r"(?P<quote>['\"`])(?P<value>.+?)(?P=quote)")
_NUMBER = r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
_VS_RE = re.compile(r"\b(?:vs\.?|versus|against)\b|เทียบ(?:กับ)?", re.IGNORECASE)


_COLUMN_PARAMETERS = {
    "column",
    "columns",
    "column_a",
    "column_b",
    "x_column",
    "y_column",
    "y_columns",
    "weight_column",
    "time_column",
    "potential_column",
    "current_column",
    "overpotential_column",
    "voltage_column",
    "temperature_column",
    "conductivity_column",
    "value_column",
    "length_column",
    "period_column",
}

_ENUM_ALIASES: Dict[str, Sequence[str]] = {
    "line": ("line plot", "กราฟเส้น", "แบบเส้น"),
    "linesymbol": ("line+symbol", "line with markers", "เส้นพร้อมจุด", "เส้นและจุด"),
    "scatter": ("scatter plot", "กราฟจุด", "กราฟกระจาย", "แบบจุด"),
    "bar": ("bar chart", "column chart", "กราฟแท่ง", "แบบแท่ง"),
    "histogram": ("hist", "ฮิสโตแกรม", "การแจกแจง"),
    "savitzky-golay": ("savitzky golay", "savgol"),
    "gaussian": ("gauss", "เกาส์เซียน"),
    "median": ("ค่ามัธยฐาน", "มัธยฐาน"),
    "mean": ("ค่าเฉลี่ย",),
    "zscore": ("z-score", "z score"),
    "minmax": ("min-max", "min max", "0 ถึง 1", "0-1"),
    "lowpass": ("low-pass", "low pass", "โลว์พาส", "ผ่านต่ำ"),
    "highpass": ("high-pass", "high pass", "ไฮพาส", "ผ่านสูง"),
    "bandpass": ("band-pass", "band pass", "แบนด์พาส"),
    "bandstop": ("band-stop", "band stop", "notch", "แบนด์สต็อป"),
    "sigma": ("uncertainty", "ค่าความไม่แน่นอน"),
    "1/sigma^2": ("inverse variance", "inverse-variance"),
    "charge": ("charging", "ชาร์จ"),
    "discharge": ("discharging", "คายประจุ"),
}

_NUMBER_ALIASES: Dict[str, Sequence[str]] = {
    "fs": ("fs", "sampling rate", "sample rate", "อัตราสุ่ม", "ความถี่สุ่ม"),
    "sample_rate_hz": ("sample rate", "sampling rate", "rate", "อัตราสุ่ม", "ความถี่สุ่ม"),
    "cutoff": ("cutoff", "cut-off", "cutoff frequency", "ความถี่ตัด"),
    "window": ("window", "window size", "หน้าต่าง", "ขนาดหน้าต่าง"),
    "smoothing_window": ("smoothing window", "window", "หน้าต่างเฉลี่ย"),
    "threshold": ("threshold", "เกณฑ์"),
    "prominence": ("prominence", "ความเด่น"),
    "distance": ("distance", "ระยะห่าง"),
    "baud": ("baud", "baud rate", "บอดเรต"),
    "min_voltage": ("minimum voltage", "min voltage", "แรงดันต่ำสุด"),
    "max_voltage": ("maximum voltage", "max voltage", "แรงดันสูงสุด"),
    "supply_voltage_v": ("supply voltage", "แรงดันจ่าย"),
    "reference_resistance_ohm": ("reference resistance", "ตัวต้านทานอ้างอิง"),
    "t_on": ("t on", "t_on", "on at", "เวลาเปิด", "เวลา on"),
    "t_off": ("t off", "t_off", "off at", "เวลาปิด", "เวลา off"),
    "length_m": ("sample length", "length", "ความยาวตัวอย่าง", "ความยาว"),
    "area_m2": ("cross-section area", "cross sectional area", "area", "พื้นที่หน้าตัด"),
    "thickness_m": ("film thickness", "thickness", "ความหนา"),
    "order": ("order", "อันดับ"),
    "value": ("value", "ค่า"),
}

_BOOLEAN_ALIASES: Dict[str, tuple[Sequence[str], Sequence[str]]] = {
    "ascending": (
        ("ascending", "low to high", "small to large", "น้อยไปมาก", "ต่ำไปสูง"),
        ("descending", "high to low", "large to small", "มากไปน้อย", "สูงไปต่ำ"),
    ),
    "new_graph": (
        ("new graph", "new plot", "กราฟใหม่"),
        ("active graph", "same graph", "existing graph", "กราฟเดิม"),
    ),
    "grid": (("show grid", "enable grid", "เปิดกริด", "แสดงกริด"), ("hide grid", "disable grid", "ปิดกริด", "ซ่อนกริด")),
    "legend": (("show legend", "enable legend", "แสดงคำอธิบาย", "เปิด legend"), ("hide legend", "disable legend", "ซ่อนคำอธิบาย", "ปิด legend")),
    "logx": (("log x", "log-x", "แกน x ล็อก", "แกน x log"), ("linear x", "แกน x เชิงเส้น")),
    "logy": (("log y", "log-y", "แกน y ล็อก", "แกน y log"), ("linear y", "แกน y เชิงเส้น")),
    "auto": (("automatic", "automatically", "auto", "อัตโนมัติ"), ("manual", "ด้วยตนเอง")),
    "smoothing": (("enable smoothing", "with smoothing", "เปิด smoothing"), ("disable smoothing", "without smoothing", "ปิด smoothing")),
    "voltage_to_resistance": (("voltage to resistance", "convert to resistance", "แปลงเป็นความต้านทาน"), ("raw voltage", "ไม่แปลงความต้านทาน")),
}

_ROLE_ALIASES: Dict[str, Sequence[str]] = {
    "x_column": ("x", "x axis", "x column", "แกน x", "คอลัมน์ x"),
    "y_column": ("y", "y axis", "y column", "แกน y", "คอลัมน์ y"),
    "y_columns": ("y", "y axis", "y columns", "แกน y", "คอลัมน์ y"),
    "weight_column": ("weight", "weights", "uncertainty", "น้ำหนัก", "ความไม่แน่นอน"),
    "time_column": ("time", "time column", "เวลา", "คอลัมน์เวลา"),
    "potential_column": ("potential", "potential column", "ศักย์ไฟฟ้า"),
    "overpotential_column": ("overpotential", "overpotential column", "โอเวอร์โพเทนเชียล"),
    "current_column": ("current", "current column", "กระแส", "คอลัมน์กระแส"),
    "voltage_column": ("voltage", "voltage column", "แรงดัน", "คอลัมน์แรงดัน"),
    "temperature_column": ("temperature", "temperature column", "อุณหภูมิ"),
    "conductivity_column": ("conductivity", "conductivity column", "การนำไฟฟ้า"),
    "value_column": ("value", "signal", "ค่าข้อมูล", "สัญญาณ"),
    "length_column": ("length", "length column", "ความยาว"),
    "period_column": ("period", "period column", "คาบ"),
    "column_a": ("column a", "first column", "คอลัมน์แรก", "คอลัมน์ a"),
    "column_b": ("column b", "second column", "คอลัมน์ที่สอง", "คอลัมน์ b"),
}

_DISPLAY_NAMES = {
    "fs": "sampling rate (fs)",
    "sample_rate_hz": "sampling rate",
    "x_column": "X column",
    "y_column": "Y column",
    "y_columns": "Y column",
    "column_a": "first column",
    "column_b": "second column",
    "chart_type": "chart type",
    "t_on": "gas ON time",
    "t_off": "gas OFF time",
    "length_m": "sample length",
    "area_m2": "cross-section area",
}

_UNIT_FACTORS: Dict[str, Dict[str, float]] = {
    "fs": {"hz": 1.0, "khz": 1e3, "mhz": 1e6},
    "sample_rate_hz": {"hz": 1.0, "khz": 1e3, "mhz": 1e6},
    "cutoff": {"hz": 1.0, "khz": 1e3, "mhz": 1e6},
    "length_m": {"m": 1.0, "cm": 1e-2, "mm": 1e-3, "um": 1e-6, "nm": 1e-9},
    "thickness_m": {"m": 1.0, "cm": 1e-2, "mm": 1e-3, "um": 1e-6, "nm": 1e-9},
    "area_m2": {"m2": 1.0, "cm2": 1e-4, "mm2": 1e-6, "um2": 1e-12, "nm2": 1e-18},
    "min_voltage": {"v": 1.0, "mv": 1e-3, "uv": 1e-6},
    "max_voltage": {"v": 1.0, "mv": 1e-3, "uv": 1e-6},
    "supply_voltage_v": {"v": 1.0, "mv": 1e-3, "uv": 1e-6},
    "reference_resistance_ohm": {
        "ohm": 1.0,
        "kohm": 1e3,
        "mohm": 1e6,
    },
}

_UNIT_STOPWORDS = {
    "and", "with", "using", "at", "for", "area", "length", "thickness",
    "cutoff", "sampling", "sample", "column", "from", "to",
}


@dataclass(frozen=True)
class _ColumnMention:
    name: str
    start: int
    end: int


@dataclass
class ArgumentResolution:
    arguments: Dict[str, Any] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    clarification: str = ""

    @property
    def ready(self) -> bool:
        return not self.missing and not self.problems


def resolve_tool_arguments(
    user_text: str,
    tool: AITool,
    context: Mapping[str, Any] | None = None,
) -> ArgumentResolution:
    """Resolve a model-selected tool call without trusting model arguments."""
    text = str(user_text or "").strip()
    context = dict(context or {})
    parameters = tool.parameters
    arguments: Dict[str, Any] = {}
    problems: List[str] = []

    columns = [str(value) for value in context.get("columns", []) if str(value).strip()]
    column_parameters = [
        name for name in parameters if _is_column_parameter(name, parameters[name])
    ]
    mentions, quoted_problems, unknown_quoted = _find_column_mentions(text, columns)

    consumed_literals: set[str] = set()
    for name, schema in parameters.items():
        if name in column_parameters or name == "instruction":
            continue
        expected = str(schema.get("type", "") or "").casefold()
        allowed = _allowed_values(tool.name, name, schema, context)
        if name == "language" and expected == "string":
            arguments[name] = "th" if _THAI_RE.search(text) else "en"
            continue
        if allowed:
            matched = _match_allowed_values(text, allowed)
            if len(matched) == 1:
                arguments[name] = matched[0]
                consumed_literals.add(str(matched[0]).casefold())
            elif len(matched) > 1:
                problems.append(
                    f"'{name}' matches more than one value: {', '.join(map(str, matched))}"
                )
            continue
        if expected in {"number", "integer"}:
            value, unit_problem = _extract_number(
                text, name, integer=expected == "integer"
            )
            if unit_problem:
                problems.append(unit_problem)
            if value is not None:
                arguments[name] = value
            continue
        if expected == "boolean":
            value, ambiguous = _extract_boolean(text, name)
            if ambiguous:
                problems.append(f"'{name}' contains both enabled and disabled directions")
            elif value is not None:
                arguments[name] = value
            continue
        if expected == "string":
            value = _extract_string(text, name)
            if value is not None:
                arguments[name] = value
                consumed_literals.add(str(value).casefold())

    if tool.name == "plot_columns" and "instruction" in parameters:
        arguments["instruction"] = text

    column_arguments, column_problems = _assign_columns(
        text, column_parameters, parameters, mentions
    )
    arguments.update(column_arguments)
    problems.extend(quoted_problems)
    problems.extend(column_problems)

    # A quoted token is treated as an intended column only for tools that have
    # column inputs. Values already consumed as an enum/path/label are excluded.
    for token in unknown_quoted:
        if column_parameters and token.casefold() not in consumed_literals:
            problems.append(
                f"quoted column '{token}' is not in the active Book"
                + (f" (available: {', '.join(columns)})" if columns else "")
            )

    missing = [
        name
        for name, schema in parameters.items()
        if schema.get("required") and name not in arguments
    ]
    result = ArgumentResolution(arguments=arguments, missing=missing, problems=problems)
    if not result.ready:
        result.clarification = _clarification(text, tool.name, missing, problems)
    return result


def merge_argument_resolutions(
    user_text: str,
    tool: AITool,
    base: ArgumentResolution,
    update: ArgumentResolution,
) -> ArgumentResolution:
    """Merge a short clarification reply into a previously unresolved call."""
    arguments = dict(base.arguments)
    arguments.update(update.arguments)

    resolved_parameters = set(update.arguments)
    resolved_a_column = any(
        _is_column_parameter(name, tool.parameters.get(name, {}))
        for name in resolved_parameters
    )
    remaining_problems = []
    for problem in base.problems:
        explicitly_resolved = any(f"'{name}'" in problem for name in resolved_parameters)
        column_resolved = resolved_a_column and "column" in problem.casefold()
        if not explicitly_resolved and not column_resolved:
            remaining_problems.append(problem)
    problems = remaining_problems + list(update.problems)
    missing = [
        name
        for name, schema in tool.parameters.items()
        if schema.get("required") and name not in arguments
    ]
    result = ArgumentResolution(
        arguments=arguments,
        missing=missing,
        problems=problems,
    )
    if not result.ready:
        result.clarification = _clarification(user_text, tool.name, missing, problems)
    return result


def resolution_has_new_details(
    base: ArgumentResolution,
    update: ArgumentResolution,
) -> bool:
    """Whether a reply contains a value that can advance a pending request."""
    ignored = {"language", "instruction"}
    if any(
        name not in ignored and base.arguments.get(name) != value
        for name, value in update.arguments.items()
    ):
        return True
    return bool(update.problems)


def _is_column_parameter(name: str, schema: Mapping[str, Any]) -> bool:
    source = str(schema.get("source", "") or "").casefold()
    return source == "active_column" or name in _COLUMN_PARAMETERS or name.endswith("_column")


def _allowed_values(
    tool_name: str,
    parameter: str,
    schema: Mapping[str, Any],
    context: Mapping[str, Any],
) -> List[Any]:
    values = schema.get("enum")
    if isinstance(values, (list, tuple)) and values:
        return list(values)
    dynamic = context.get("parameter_values", {})
    if isinstance(dynamic, Mapping):
        values = dynamic.get(f"{tool_name}.{parameter}")
        if isinstance(values, (list, tuple)):
            return list(values)
    return []


def _phrase_present(text: str, phrase: str) -> bool:
    folded = text.casefold()
    needle = str(phrase or "").strip().casefold()
    if not needle:
        return False
    if not needle.isascii():
        return needle in folded
    if any(character.isalnum() for character in needle):
        return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", folded) is not None
    return needle in folded


def _match_allowed_values(text: str, allowed: Iterable[Any]) -> List[Any]:
    matches: List[tuple[int, Any]] = []
    for value in allowed:
        canonical = str(value)
        aliases = (
            canonical,
            canonical.replace("_", " "),
            canonical.replace("_", "-"),
            canonical.replace("-", " "),
            *_ENUM_ALIASES.get(canonical.casefold(), ()),
        )
        scores = [len(alias) for alias in aliases if _phrase_present(text, alias)]
        if scores:
            matches.append((max(scores), value))
    if not matches:
        return []
    best = max(score for score, _value in matches)
    return [value for score, value in matches if score == best]


def _find_column_mentions(
    text: str, columns: Sequence[str]
) -> tuple[List[_ColumnMention], List[str], List[str]]:
    folded = text.casefold()
    candidates: List[_ColumnMention] = []
    for column in columns:
        needle = column.strip().casefold()
        if not needle:
            continue
        matches = list(re.finditer(rf"(?<!\w){re.escape(needle)}(?!\w)", folded))
        if matches:
            for match in matches:
                candidates.append(_ColumnMention(column, match.start(), match.end()))
        elif not needle.isascii():
            start = folded.find(needle)
            while start >= 0:
                candidates.append(_ColumnMention(column, start, start + len(needle)))
                start = folded.find(needle, start + len(needle))

    # When column names overlap ("Signal" and "Signal Raw"), prefer the
    # longest actual name at that location instead of reporting a false clash.
    candidates.sort(key=lambda item: (item.start, -(item.end - item.start)))
    selected: List[_ColumnMention] = []
    for candidate in candidates:
        if any(candidate.start < item.end and item.start < candidate.end for item in selected):
            continue
        if candidate.name not in [item.name for item in selected]:
            selected.append(candidate)

    problems: List[str] = []
    unknown: List[str] = []
    for quote in _QUOTED_RE.finditer(text):
        token = quote.group("value").strip()
        if not token:
            continue
        exact = [column for column in columns if column.strip().casefold() == token.casefold()]
        partial = exact or [
            column for column in columns
            if len(token) >= 2 and token.casefold() in column.casefold()
        ]
        if len(partial) == 1:
            name = partial[0]
            if name not in [item.name for item in selected]:
                selected.append(_ColumnMention(name, quote.start("value"), quote.end("value")))
        elif len(partial) > 1:
            problems.append(
                f"quoted column '{token}' is ambiguous: {', '.join(partial)}"
            )
        elif token.casefold() not in [column.casefold() for column in columns]:
            unknown.append(token)

    selected.sort(key=lambda item: item.start)
    return selected, problems, unknown


def _assign_columns(
    text: str,
    column_parameters: Sequence[str],
    schemas: Mapping[str, Mapping[str, Any]],
    mentions: Sequence[_ColumnMention],
) -> tuple[Dict[str, Any], List[str]]:
    if not column_parameters or not mentions:
        return {}, []

    assigned: Dict[str, Any] = {}
    problems: List[str] = []
    used: set[str] = set()
    mention_names = [item.name for item in mentions]

    # Scientific convention: "Y vs X" / "Y เทียบ X" is explicit enough to
    # map axes without guessing from column order.
    separator = _VS_RE.search(text)
    if separator is not None and "x_column" in column_parameters:
        before = [item.name for item in mentions if item.end <= separator.start()]
        after = [item.name for item in mentions if item.start >= separator.end()]
        y_parameter = "y_columns" if "y_columns" in column_parameters else (
            "y_column" if "y_column" in column_parameters else None
        )
        if before and after and y_parameter:
            assigned["x_column"] = after[0]
            assigned[y_parameter] = before if y_parameter == "y_columns" else before[-1]
            used.update(before)
            used.add(after[0])

    # Explicit labels such as "X column Time" or "Voltage as Y".
    for parameter in column_parameters:
        if parameter in assigned:
            continue
        matches = [
            item.name
            for item in mentions
            if item.name not in used and _column_has_role(text, item.name, parameter)
        ]
        if len(matches) == 1:
            assigned[parameter] = matches if schemas[parameter].get("type") == "array" else matches[0]
            used.update(matches)
        elif len(matches) > 1 and schemas[parameter].get("type") != "array":
            problems.append(
                f"more than one column was assigned to '{parameter}': {', '.join(matches)}"
            )

    # Domain-specific column names can safely map to equally named roles:
    # Current -> current_column, Potential -> potential_column, etc.
    for parameter in column_parameters:
        if parameter in assigned or parameter in {"column", "columns", "x_column", "y_column", "y_columns", "column_a", "column_b"}:
            continue
        role = parameter.removesuffix("_column").replace("_", " ").casefold()
        matches = [
            item.name for item in mentions
            if item.name not in used and _phrase_present(item.name, role)
        ]
        if len(matches) == 1:
            assigned[parameter] = matches[0]
            used.add(matches[0])

    remaining = [name for name in mention_names if name not in used]
    unresolved = [name for name in column_parameters if name not in assigned]

    if unresolved == ["columns"] or (
        len(unresolved) == 1 and schemas[unresolved[0]].get("type") == "array"
    ):
        if remaining:
            assigned[unresolved[0]] = remaining
            used.update(remaining)
        return assigned, problems

    if unresolved == ["column"]:
        if len(remaining) == 1:
            assigned["column"] = remaining[0]
        elif len(remaining) > 1:
            problems.append(
                "choose one target column from: " + ", ".join(remaining)
            )
        return assigned, problems

    if set(unresolved) == {"column_a", "column_b"} and len(remaining) == 2:
        assigned["column_a"], assigned["column_b"] = remaining
        return assigned, problems

    # One unambiguous column and one remaining slot is safe. Multiple unmatched
    # columns/roles are surfaced to the user instead of assigned by position.
    if len(unresolved) == 1 and len(remaining) == 1:
        name = unresolved[0]
        assigned[name] = [remaining[0]] if schemas[name].get("type") == "array" else remaining[0]
    elif remaining and unresolved:
        problems.append(
            "column roles are ambiguous for "
            + ", ".join(remaining)
            + "; specify "
            + ", ".join(unresolved)
        )
    return assigned, problems


def _column_has_role(text: str, column: str, parameter: str) -> bool:
    aliases = _ROLE_ALIASES.get(parameter, ())
    if not aliases:
        return False
    column_pattern = re.escape(column)
    for alias in aliases:
        role_pattern = re.escape(alias)
        role_token = role_pattern if not alias.isascii() else rf"(?<!\w){role_pattern}(?!\w)"
        column_token = column_pattern if not column.isascii() else rf"(?<!\w){column_pattern}(?!\w)"
        before = rf"{role_token}\s*(?:=|:|is|เป็น|คือ|ใช้)?\s*['\"`]?{column_token}"
        after = rf"{column_token}\s*(?:as|เป็น|คือ|ใช้เป็น)\s*{role_token}"
        if re.search(before, text, re.IGNORECASE) or re.search(after, text, re.IGNORECASE):
            return True
    return False


def _extract_number(
    text: str, parameter: str, *, integer: bool
) -> tuple[int | float | None, str | None]:
    aliases = _NUMBER_ALIASES.get(parameter, (parameter.replace("_", " "),))
    for alias in aliases:
        if alias.isascii():
            alias_pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"
        else:
            alias_pattern = re.escape(alias)
        pattern = (
            rf"{alias_pattern}\s*"
            rf"(?:=|:|is|at|of|เป็น|คือ)?\s*({_NUMBER})"
            rf"(?:\s*([A-Za-zµμΩ²^0-9/]+))?"
        )
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1).replace(",", ""))
            unit = _normalise_unit(match.group(2))
            factors = _UNIT_FACTORS.get(parameter)
            if factors and unit:
                if unit in factors:
                    value *= factors[unit]
                elif unit not in _UNIT_STOPWORDS:
                    choices = ", ".join(factors)
                    return None, (
                        f"'{parameter}' has unsupported unit '{match.group(2)}'; "
                        f"use one of: {choices}"
                    )
            if integer:
                return (
                    (int(value), None)
                    if value.is_integer()
                    else (None, f"'{parameter}' must be a whole number")
                )
            return value, None
    return None, None


def _normalise_unit(value: str | None) -> str:
    unit = str(value or "").strip()
    if not unit:
        return ""
    unit = unit.replace("Ω", "ohm").replace("µ", "u").replace("μ", "u")
    unit = unit.replace("²", "2").replace("^", "").replace("/", "")
    return unit.casefold()


def _extract_boolean(text: str, parameter: str) -> tuple[bool | None, bool]:
    positives, negatives = _BOOLEAN_ALIASES.get(parameter, ((), ()))
    positive = any(_phrase_present(text, phrase) for phrase in positives)
    negative = any(_phrase_present(text, phrase) for phrase in negatives)

    label = parameter.replace("_", " ")
    positive = positive or re.search(
        rf"(?<!\w){re.escape(label)}(?!\w)\s*(?:=|:|is|เป็น|คือ)?\s*(?:true|yes|on|เปิด)",
        text,
        re.IGNORECASE,
    ) is not None
    negative = negative or re.search(
        rf"(?<!\w){re.escape(label)}(?!\w)\s*(?:=|:|is|เป็น|คือ)?\s*(?:false|no|off|ปิด)",
        text,
        re.IGNORECASE,
    ) is not None
    if positive and negative:
        return None, True
    if positive:
        return True, False
    if negative:
        return False, False
    return None, False


def _extract_string(text: str, parameter: str) -> str | None:
    if parameter == "path":
        for match in _QUOTED_RE.finditer(text):
            candidate = match.group("value").strip()
            if re.match(r"^(?:[A-Za-z]:[\\/]|/)", candidate):
                return candidate
        match = re.search(
            r"(?:[A-Za-z]:[\\/]|/)[^\r\n'\"]+?\.(?:csv|tsv|txt|xlsx|xls|json|parquet)",
            text,
            re.IGNORECASE,
        )
        return match.group(0).strip().rstrip(".,") if match else None
    if parameter == "port":
        match = re.search(r"\bCOM\d+\b", text, re.IGNORECASE)
        return match.group(0).upper() if match else None
    if parameter == "device":
        match = re.search(r"\bDev\d+\b", text, re.IGNORECASE)
        return match.group(0) if match else None
    if parameter == "channel":
        match = re.search(r"\b(?:Dev\d+/)?ai\d+(?:\s*,\s*(?:Dev\d+/)?ai\d+)*\b", text, re.IGNORECASE)
        return re.sub(r"\s+", "", match.group(0)) if match else None

    aliases = {
        "title": ("title", "graph title", "ชื่อกราฟ"),
        "xlabel": ("xlabel", "x label", "ชื่อแกน x"),
        "ylabel": ("ylabel", "y label", "ชื่อแกน y"),
        "label": ("label", "ป้าย"),
    }.get(parameter, (parameter.replace("_", " "),))
    for alias in aliases:
        match = re.search(
            rf"(?<!\w){re.escape(alias)}(?!\w)\s*(?:=|:|is|to|เป็น|คือ)?\s*['\"`](.+?)['\"`]",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
    return None


def _clarification(
    user_text: str, tool_name: str, missing: Sequence[str], problems: Sequence[str]
) -> str:
    thai = _THAI_RE.search(user_text) is not None
    readable_missing = [_DISPLAY_NAMES.get(name, name.replace("_", " ")) for name in missing]
    if thai:
        parts: List[str] = []
        if problems:
            parts.append("ข้อมูลที่ระบุยังกำกวมหรือไม่ตรงกับ Book: " + "; ".join(problems))
        if readable_missing:
            parts.append("กรุณาระบุ " + ", ".join(readable_missing))
        return "ยังไม่รันคำสั่งเพื่อป้องกันการใช้ข้อมูลผิด — " + " ".join(parts)
    parts = []
    if problems:
        parts.append("The request is ambiguous or does not match the active Book: " + "; ".join(problems) + ".")
    if readable_missing:
        parts.append("Please specify " + ", ".join(readable_missing) + ".")
    return f"I did not run '{tool_name}' yet. " + " ".join(parts)
