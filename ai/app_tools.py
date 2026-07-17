"""Bind a handful of SciPlotter capabilities as AI tools.

Handlers are thin, defensive adapters over existing MainWindow seams
(``_resolve_active_dataframe``, ``plot_from_workbook`` ...). They return short
text so the model can reason about the result. The window is captured lazily so
this module imports fine (and unit-tests) without a running app.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

import pandas as pd

from ai.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_PLOT_STYLES = {"line", "linesymbol", "scatter", "bar", "histogram"}
_PLOT_STYLE_ALIASES = {
    "line": "line",
    "line plot": "line",
    "linesymbol": "linesymbol",
    "line+symbol": "linesymbol",
    "line + symbol": "linesymbol",
    "line with markers": "linesymbol",
    "scatter": "scatter",
    "scatterplot": "scatter",
    "scatter plot": "scatter",
    "scatter_plot": "scatter",
    "กราฟจุด": "scatter",
    "กราฟกระจาย": "scatter",
    "bar": "bar",
    "bar chart": "bar",
    "column": "bar",
    "column chart": "bar",
    "กราฟแท่ง": "bar",
    "hist": "histogram",
    "histogram": "histogram",
    "ฮิสโตแกรม": "histogram",
}
_TIME_LIKE_COLUMN_KEYS = ("time", "timestamp", "date", "datetime", "elapsed", "seconds")


def _active_df(window):
    getter = getattr(window, "_resolve_active_dataframe", None)
    return getter() if callable(getter) else None


def _safe_argument_context(window) -> Dict[str, Any]:
    """Return live values that the deterministic AI router may reference."""
    df = _active_df(window)
    columns = [str(column) for column in getattr(df, "columns", [])] if df is not None else []
    label_getter = getattr(window, "_active_book_label", None)
    book_label = str(label_getter() or "") if callable(label_getter) else ""
    book_token = (
        f"{id(df)}:{len(df)}:{'|'.join(columns)}" if df is not None else ""
    )
    numeric_columns = []
    if df is not None:
        numeric_columns = [
            str(column)
            for column in getattr(df, "columns", [])
            if _column_is_numeric(df, column)
        ]

    parameter_values: Dict[str, List[str]] = {}
    try:
        from analysis.fitting import list_available_models

        parameter_values["fit_curve.model"] = list_available_models()
    except Exception:
        logger.debug("Could not load fit model choices for AI routing", exc_info=True)
    try:
        from plots.registry import all_plots

        parameter_values["plot_chart.chart_type"] = [
            str(entry.get("key")) for entry in all_plots() if entry.get("key")
        ]
    except Exception:
        logger.debug("Could not load chart choices for AI routing", exc_info=True)
    return {
        "book_label": book_label,
        "book_token": book_token,
        "columns": columns,
        "numeric_columns": numeric_columns,
        "parameter_values": parameter_values,
    }


def _tool_list_columns(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    thai = str(args.get("language", "")).casefold() == "th"
    if df is None or getattr(df, "empty", True):
        return (
            "ไม่มีข้อมูลที่กำลังใช้งาน กรุณาเปิดไฟล์หรือเลือก Book ก่อน"
            if thai
            else "No active data. Ask the user to open a file or a Book first."
        )
    cols = [str(c) for c in df.columns]
    if thai:
        return f"ข้อมูลปัจจุบันมี {len(df):,} แถว และ {len(cols)} คอลัมน์: {', '.join(cols)}"
    return f"Active data has {len(df)} rows and {len(cols)} columns: {', '.join(cols)}."


def _tool_describe_data(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data to describe."
    try:
        from analysis.descriptive import descriptive_table

        requested = args.get("columns")
        cols = [str(c) for c in requested] if isinstance(requested, list) and requested else None
        table = descriptive_table(df, cols)
        return "Descriptive statistics:\n" + table.to_string()
    except Exception as exc:
        logger.debug("describe_data tool failed", exc_info=True)
        return f"Could not compute statistics: {exc}"


def _format_summary_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not pd.notna(number):
        return "n/a"
    magnitude = abs(number)
    if magnitude >= 1_000_000 or (0 < magnitude < 0.001):
        return f"{number:.4e}"
    return f"{number:,.5g}"


def _tool_summarize_data(window, args: Dict[str, Any]) -> str:
    """Return a compact, evidence-backed dataset analysis without another LLM turn."""
    import numpy as np

    df = _active_df(window)
    thai = str(args.get("language", "")).casefold() == "th"
    if df is None or getattr(df, "empty", True):
        return (
            "ไม่มีข้อมูลที่กำลังใช้งาน กรุณาเปิดไฟล์หรือเลือก Book ก่อน"
            if thai
            else "No active data. Open a file or activate a Book first."
        )

    numeric = {}
    for column in df.columns:
        values = pd.to_numeric(df[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        if values.notna().any():
            numeric[column] = values
    if not numeric:
        return (
            f"ข้อมูลมี {len(df):,} แถว แต่ไม่พบคอลัมน์ตัวเลขสำหรับวิเคราะห์"
            if thai
            else f"The data has {len(df):,} rows but no numeric columns to analyze."
        )

    label_getter = getattr(window, "_active_book_label", None)
    book = label_getter() if callable(label_getter) else ""
    book = str(book or "Active Book")
    column_names = [str(column) for column in df.columns]
    columns_text = ", ".join(column_names[:8])
    if len(column_names) > 8:
        remaining = len(column_names) - 8
        columns_text += (
            f", อีก {remaining} คอลัมน์"
            if thai
            else f", +{remaining} more"
        )
    missing = int(df.isna().sum().sum())

    x_getter = getattr(window, "selected_x_column", None)
    y_getter = getattr(window, "selected_y_column", None)
    x_column = _resolve_column_name(df, x_getter() if callable(x_getter) else None)
    y_column = _resolve_column_name(df, y_getter() if callable(y_getter) else None)
    numeric_columns = list(numeric)
    if x_column not in numeric:
        x_column = numeric_columns[0] if len(numeric_columns) >= 2 else None
    if y_column not in numeric or y_column == x_column:
        y_column = next(
            (column for column in reversed(numeric_columns) if column != x_column),
            numeric_columns[0],
        )

    if thai:
        lines = [
            f"วิเคราะห์ข้อมูลจริงจาก {book}",
            f"• ขนาด: {len(df):,} แถว × {len(df.columns)} คอลัมน์",
            f"• คอลัมน์: {columns_text}",
            f"• ค่าว่าง: {missing:,} ค่า",
        ]
    else:
        lines = [
            f"Analysis of the actual data in {book}",
            f"• Size: {len(df):,} rows × {len(df.columns)} columns",
            f"• Columns: {columns_text}",
            f"• Missing values: {missing:,}",
        ]

    for column in numeric_columns[:6]:
        clean = numeric[column].dropna()
        std = clean.std(ddof=1) if len(clean) > 1 else 0.0
        if thai:
            lines.append(
                f"• {column}: ช่วง {_format_summary_number(clean.min())}–"
                f"{_format_summary_number(clean.max())} | เฉลี่ย "
                f"{_format_summary_number(clean.mean())} | SD {_format_summary_number(std)}"
            )
        else:
            lines.append(
                f"• {column}: range {_format_summary_number(clean.min())}–"
                f"{_format_summary_number(clean.max())} | mean "
                f"{_format_summary_number(clean.mean())} | SD {_format_summary_number(std)}"
            )
    if len(numeric_columns) > 6:
        remaining = len(numeric_columns) - 6
        lines.append(f"• {'อีก' if thai else 'Plus'} {remaining} {'คอลัมน์ตัวเลข' if thai else 'numeric columns'}")

    x_values = (
        numeric[x_column]
        if x_column in numeric
        else pd.Series(np.arange(1, len(df) + 1, dtype=float), index=df.index)
    )
    pair = pd.DataFrame({"x": x_values, "y": numeric[y_column]}).dropna()
    x_label = str(x_column) if x_column is not None else "Row"
    if not pair.empty:
        max_row = pair.iloc[int(np.argmax(pair["y"].to_numpy(dtype=float)))]
        if thai:
            lines.append(
                f"• จุดสูงสุดของ {y_column}: {_format_summary_number(max_row['y'])} "
                f"ที่ {x_label} = {_format_summary_number(max_row['x'])}"
            )
        else:
            lines.append(
                f"• Maximum {y_column}: {_format_summary_number(max_row['y'])} "
                f"at {x_label} = {_format_summary_number(max_row['x'])}"
            )

    if len(pair) >= 3 and x_column is not None:
        x_array = pair["x"].to_numpy(dtype=float)
        y_array = pair["y"].to_numpy(dtype=float)
        if np.std(x_array) > 0 and np.std(y_array) > 0:
            correlation = float(np.corrcoef(x_array, y_array)[0, 1])
            label = "Pearson correlation" if not thai else "สหสัมพันธ์ Pearson"
            lines.append(f"• {label}: {_format_summary_number(correlation)}")

        try:
            from scipy.signal import find_peaks

            spread = float(np.nanpercentile(y_array, 95) - np.nanpercentile(y_array, 5))
            prominence = max(spread * 0.08, float(np.nanstd(y_array)) * 0.15, 1e-12)
            peak_indexes, properties = find_peaks(
                y_array,
                prominence=prominence,
                distance=max(1, len(y_array) // 250),
            )
            if len(peak_indexes):
                order = np.argsort(properties["prominences"])[::-1][:5]
                strongest = peak_indexes[order]
                peaks = ", ".join(
                    f"{_format_summary_number(x_array[index])} "
                    f"({_format_summary_number(y_array[index])})"
                    for index in strongest
                )
                lines.append(
                    f"• {'พีคเด่น' if thai else 'Prominent peaks'} [{x_label} ({y_column})]: {peaks}"
                )
        except Exception:
            logger.debug("automatic summary peak scan skipped", exc_info=True)

    folded_x = str(x_column or "").casefold().replace("-", "").replace("_", "")
    folded_y = str(y_column).casefold().replace("-", "").replace("_", "")
    xrd_like = ("theta" in folded_x or "2θ" in folded_x) and "intens" in folded_y
    if xrd_like:
        lines.append(
            "• รูปแบบข้อมูลคล้าย XRD (2θ–Intensity): ระบุตำแหน่งพีคได้ แต่การระบุ phase ต้องเทียบฐานข้อมูลอ้างอิง"
            if thai
            else "• XRD-like data (2θ–Intensity): peak positions are measurable, but phase identification requires a reference database."
        )

    if thai:
        lines.append(
            f"แนะนำต่อ: พิมพ์ “plot {y_column} vs {x_label} as line” หรือ “หาพีค”"
        )
    else:
        lines.append(
            f'Next: try "plot {y_column} vs {x_label} as line" or "find peaks".'
        )
    return "\n".join(lines)


def _normalise_plot_style(value: Any) -> str:
    raw = " ".join(str(value or "line").strip().casefold().split())
    return _PLOT_STYLE_ALIASES.get(raw, raw)


def _resolve_column_name(df, value: Any):
    try:
        if value in getattr(df, "columns", []):
            return value
    except (TypeError, ValueError):
        pass
    requested = str(value or "").strip().casefold()
    if not requested:
        return None
    for column in df.columns:
        if str(column).strip().casefold() == requested:
            return column
    return None


def _column_is_numeric(df, column) -> bool:
    series = df[column]
    if pd.api.types.is_numeric_dtype(series):
        return True
    try:
        return bool(pd.to_numeric(series, errors="coerce").notna().any())
    except Exception:
        return False


def _column_is_time_like(df, column) -> bool:
    name = str(column).strip().casefold()
    if name == "t" or any(key in name for key in _TIME_LIKE_COLUMN_KEYS):
        return True
    try:
        return bool(pd.api.types.is_datetime64_any_dtype(df[column]))
    except Exception:
        return False


def _columns_in_instruction(df, instruction: str) -> List[Any]:
    folded = str(instruction or "").casefold()
    matches = []
    for column in df.columns:
        needle = str(column).strip().casefold()
        if not needle:
            continue
        match = re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", folded)
        if match is None and len(needle) >= 3 and any(ord(char) > 127 for char in needle):
            position = folded.find(needle)
        else:
            position = match.start() if match is not None else -1
        if position >= 0:
            matches.append((position, -len(needle), column))
    matches.sort(key=lambda item: (item[0], item[1]))
    ordered = []
    for _position, _length, column in matches:
        if column not in ordered:
            ordered.append(column)
    return ordered


def _default_plot_x(window, df, numeric_columns: List[Any]):
    getter = getattr(window, "selected_x_column", None)
    selected = _resolve_column_name(df, getter() if callable(getter) else None)
    if selected is not None and (selected in numeric_columns or _column_is_time_like(df, selected)):
        return selected
    for column in df.columns:
        if _column_is_time_like(df, column):
            return column
    return numeric_columns[0] if numeric_columns else None


def _explicit_y_values(args: Dict[str, Any]) -> List[Any]:
    requested = args.get("y_columns")
    if requested is None:
        requested = args.get("y_column")
    if requested is None:
        return []
    if isinstance(requested, (list, tuple)):
        return list(requested)
    if isinstance(requested, str) and ("," in requested or ";" in requested):
        return [part.strip() for part in re.split(r"[,;]", requested) if part.strip()]
    return [requested]


def _boolean_argument(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        folded = value.strip().casefold()
        if folded in {"false", "no", "off", "0"}:
            return False
        if folded in {"true", "yes", "on", "1"}:
            return True
    return bool(value)


def _resolve_plot_mapping(window, df, args: Dict[str, Any], style: str):
    columns_text = ", ".join(str(column) for column in df.columns)
    numeric_columns = [column for column in df.columns if _column_is_numeric(df, column)]
    if not numeric_columns:
        raise ValueError("the active data has no numeric columns")

    requested_x = args.get("x_column")
    x_column = _resolve_column_name(df, requested_x)
    if requested_x not in (None, "") and x_column is None:
        raise ValueError(f"X column '{requested_x}' was not found. Available: {columns_text}")

    requested_y = _explicit_y_values(args)
    y_columns = []
    missing_y = []
    for value in requested_y:
        resolved = _resolve_column_name(df, value)
        if resolved is None:
            missing_y.append(str(value))
        elif resolved not in y_columns:
            y_columns.append(resolved)
    if missing_y:
        raise ValueError(
            f"Y column(s) {', '.join(missing_y)} were not found. Available: {columns_text}"
        )
    non_numeric_y = [str(column) for column in y_columns if column not in numeric_columns]
    if non_numeric_y:
        raise ValueError(f"Y column(s) {', '.join(non_numeric_y)} contain no numeric values")

    instruction = str(args.get("instruction", "") or "")
    mentioned = _columns_in_instruction(df, instruction)
    default_x = x_column or _default_plot_x(window, df, numeric_columns)

    if style == "histogram":
        if not y_columns:
            candidates = [column for column in mentioned if column in numeric_columns]
            if not candidates:
                getter = getattr(window, "selected_y_column", None)
                selected_y = _resolve_column_name(df, getter() if callable(getter) else None)
                candidates = [selected_y] if selected_y in numeric_columns else numeric_columns
            y_columns = candidates[:1]
        return None, y_columns[:1]

    if not y_columns and len(mentioned) >= 2:
        separator = re.search(
            r"\b(?:vs\.?|versus|against)\b|เทียบ(?:กับ)?",
            instruction.casefold(),
        )
        if separator is not None:
            positions = {
                column: instruction.casefold().find(str(column).casefold())
                for column in mentioned
            }
            before = [column for column in mentioned if 0 <= positions[column] < separator.start()]
            after = [column for column in mentioned if positions[column] >= separator.end()]
            if before and after:
                x_column = x_column or after[0]
                y_columns = [column for column in before if column in numeric_columns]

    if not y_columns and mentioned:
        mentioned_numeric = [column for column in mentioned if column in numeric_columns]
        if x_column is None:
            mentioned_x = next(
                (column for column in mentioned if _column_is_time_like(df, column)),
                None,
            )
            if mentioned_x is not None:
                x_column = mentioned_x
            elif default_x is not None and default_x not in mentioned:
                x_column = default_x
            elif len(mentioned) >= 2:
                x_column = mentioned[0]
        y_columns = [column for column in mentioned_numeric if column != x_column]
        if len(mentioned) == 1 and mentioned[0] in numeric_columns and mentioned[0] != x_column:
            y_columns = [mentioned[0]]

    x_column = x_column or default_x
    if not y_columns:
        getter = getattr(window, "selected_y_column", None)
        selected_y = _resolve_column_name(df, getter() if callable(getter) else None)
        if selected_y in numeric_columns and selected_y != x_column:
            y_columns = [selected_y]
        else:
            y_columns = [column for column in numeric_columns if column != x_column]

    if not y_columns and len(numeric_columns) == 1:
        x_column = None
        y_columns = numeric_columns[:1]
    if not y_columns:
        raise ValueError("choose at least one numeric Y column")
    if x_column is not None and not (
        x_column in numeric_columns or _column_is_time_like(df, x_column) or style == "bar"
    ):
        raise ValueError(f"X column '{x_column}' is not numeric or datetime")

    if style == "bar":
        y_columns = y_columns[:1]
    return x_column, y_columns


def _tool_plot(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data to plot. Open a file or activate a Book first."

    style = _normalise_plot_style(args.get("style", "line"))
    if style not in _PLOT_STYLES:
        return f"Unknown style '{style}'. Use one of: {', '.join(sorted(_PLOT_STYLES))}."

    try:
        x_column, y_columns = _resolve_plot_mapping(window, df, args, style)
    except ValueError as exc:
        return f"Could not create the plot: {exc}."

    new_graph = _boolean_argument(args.get("new_graph"), True)
    explicit_plotter = getattr(window, "plot_explicit_columns", None)
    try:
        if callable(explicit_plotter):
            result = explicit_plotter(
                style,
                str(x_column) if x_column is not None else None,
                [str(column) for column in y_columns],
                new_graph=new_graph,
            )
            if not result:
                return "Could not create the plot: the graph renderer did not add any artists."
        else:
            plotter = getattr(window, "plot_from_workbook", None)
            if not callable(plotter):
                return "Plotting is not available in this context."
            plotter(style, new_graph=new_graph)
    except Exception as exc:
        logger.debug("plot tool failed", exc_info=True)
        return f"Could not create the plot: {exc}"

    style_label = "line + symbol" if style == "linesymbol" else style
    y_label = ", ".join(str(column) for column in y_columns)
    if style == "histogram":
        mapping = f"{y_label}"
    else:
        mapping = f"{y_label} vs {x_column if x_column is not None else 'Row'}"
    destination = "new" if new_graph else "active"
    return f"Created a {style_label} graph in the {destination} Graph: {mapping} ({len(df)} rows)."


def _tool_active_book(window, _args: Dict[str, Any]) -> str:
    label = getattr(window, "_active_book_label", None)
    name = label() if callable(label) else None
    return f"Active Book: {name}" if name else "No active Book."


def _tool_gas_live_control(window, args: Dict[str, Any]) -> str:
    action = str(args.get("action", "status") or "status").strip().lower()
    try:
        if action == "flow_status":
            getter = getattr(window, "gs_live_flow_status", None)
            if not callable(getter):
                return "Gas visual acquisition flow is unavailable."
            status = getter()
            state = "running" if status.get("running") else "ready"
            wiring = status.get("wiring", [])
            return (
                f"Gas visual flow is {state}: {status.get('summary', '-')}; "
                f"wires={wiring}"
            )
        if action == "configure_wiring":
            configure = getattr(window, "gs_live_configure_wiring", None)
            if not callable(configure):
                return "Gas visual acquisition wiring is unavailable."
            edges = args.get("edges")
            if isinstance(edges, str):
                parsed = []
                for item in edges.split(","):
                    parts = item.replace("->", ">").split(">")
                    if len(parts) == 2:
                        parsed.append([parts[0].strip(), parts[1].strip()])
                edges = parsed
            if not isinstance(edges, (list, tuple)):
                return "Provide flow 'edges' as pairs or source>target comma-separated text."
            ok, message = configure(edges)
            return message if ok else f"Could not configure gas flow wiring: {message}"
        if action == "configure_flow":
            configure = getattr(window, "gs_live_configure_flow", None)
            if not callable(configure):
                return "Gas visual acquisition flow is unavailable."
            preset = str(args.get("preset", "") or "").strip().lower()
            updates: Dict[str, Any] = {}
            if preset in {"raw", "voltage"}:
                updates.update(voltage_to_resistance=False, smoothing=False)
            elif preset in {"resistance", "voltage_to_resistance"}:
                updates.update(voltage_to_resistance=True, smoothing=False)
            elif preset in {"smoothed", "resistance_smoothed"}:
                updates.update(
                    voltage_to_resistance=True,
                    smoothing=True,
                    smoothing_field="resistance_ohm",
                )
            elif preset:
                return "Unknown flow preset. Use raw, resistance, or smoothed."
            for key in (
                "voltage_to_resistance", "voltage_field", "supply_voltage_v",
                "reference_resistance_ohm", "divider_topology", "smoothing",
                "smoothing_field", "smoothing_window", "sensor_channels",
            ):
                if key in args:
                    updates[key] = args[key]
            ok, message = configure(None, **updates)
            return message if ok else f"Could not configure gas visual flow: {message}"
        if action == "status":
            getter = getattr(window, "gs_live_status", None)
            if not callable(getter):
                return "Gas live acquisition is unavailable."
            status = getter()
            state = "connected" if status.get("connected") else "disconnected"
            transport = str(status.get("transport", "serial"))
            if transport == "ni_daq":
                channels = ",".join(str(value) for value in status.get("channels", [])) or "-"
                return (
                    f"Gas live is {state}: transport=ni_daq, "
                    f"device={status.get('device') or '-'}, channels={channels}, "
                    f"configured_rate={float(status.get('configured_rate_hz', 0.0)):.2f} Hz, "
                    f"samples={status.get('samples', 0)}, "
                    f"measured_rate={float(status.get('sample_rate_hz', 0.0)):.2f} Hz, "
                    f"errors={status.get('acquisition_errors', 0)}, "
                    f"book={status.get('book') or '-'}"
                )
            return (
                f"Gas live is {state}: transport=serial, port={status.get('port') or '-'}, "
                f"baud={status.get('baud', '-')}, samples={status.get('samples', 0)}, "
                f"rate={float(status.get('sample_rate_hz', 0.0)):.2f} Hz, "
                f"parse_errors={status.get('parse_errors', 0)}, "
                f"book={status.get('book') or '-'}"
            )
        if action == "connect":
            transport = str(args.get("transport", "serial") or "serial").strip().lower()
            if transport in {"ni_daq", "nidaq", "daq", "ni-daq"}:
                connector = getattr(window, "gs_live_connect_daq", None)
                if not callable(connector):
                    return "NI-DAQ gas live acquisition is unavailable."
                device = str(args.get("device", "") or "").strip()
                channel = str(args.get("channel", "") or "").strip()
                if not device or not channel:
                    return "Provide NI-DAQ 'device' and analog-input 'channel' to connect."
                ok, message = connector(
                    device,
                    channel,
                    float(args.get("sample_rate_hz", 10.0) or 10.0),
                    float(args.get("min_voltage", 0.0)),
                    float(args.get("max_voltage", 5.0)),
                    str(args.get("terminal_config", "RSE") or "RSE"),
                )
                return message if ok else f"Could not connect NI-DAQ gas live: {message}"
            connector = getattr(window, "gs_live_connect", None)
            if not callable(connector):
                return "Gas live acquisition is unavailable."
            port = str(args.get("port", "") or "").strip()
            if not port:
                return "Provide a serial 'port' to connect gas live acquisition."
            ok, message = connector(port, int(args.get("baud", 115200) or 115200))
            return message if ok else f"Could not connect gas live: {message}"
        if action == "disconnect":
            disconnect = getattr(window, "gs_live_disconnect", None)
            if not callable(disconnect):
                return "Gas live acquisition is unavailable."
            _ok, message = disconnect()
            return message
        if action in {"mark_on", "mark_off"}:
            marker = getattr(window, "gs_live_mark", None)
            if not callable(marker):
                return "Gas live acquisition is unavailable."
            state = "on" if action == "mark_on" else "off"
            ok, message = marker(state, str(args.get("label", "") or ""))
            return message if ok else f"Could not mark gas state: {message}"
        return (
            "Unknown gas live action. Use status, connect, disconnect, mark_on, "
            "mark_off, flow_status, configure_flow, or configure_wiring."
        )
    except Exception as exc:
        logger.debug("gas_live_control tool failed", exc_info=True)
        return f"Gas live control failed: {exc}"


def _tool_list_fit_models(_window, _args: Dict[str, Any]) -> str:
    try:
        from analysis.fitting import list_available_models

        return "Available fit models: " + ", ".join(list_available_models())
    except Exception as exc:
        logger.debug("list_fit_models tool failed", exc_info=True)
        return f"Could not list fit models: {exc}"


def _numeric_columns(df):
    return [c for c in df.columns if str(df[c].dtype) != "object"]


def _tool_fit_curve(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data to fit."
    model = str(args.get("model", "linear")).strip() or "linear"
    numeric = _numeric_columns(df)
    x_col = args.get("x_column") or (numeric[0] if len(numeric) >= 1 else None)
    y_col = args.get("y_column") or (numeric[1] if len(numeric) >= 2 else None)
    if x_col is None or y_col is None or x_col not in df.columns or y_col not in df.columns:
        return "Need at least two numeric columns (or pass x_column and y_column) to fit."
    try:
        weight_column_arg = args.get("weight_column")
        weighting = str(args.get("weighting", "none") or "none").strip().lower()
        if weight_column_arg not in (None, "") or weighting != "none":
            weight_col = _resolve_column_name(df, weight_column_arg)
            if weight_col is None:
                return "Weighted fitting needs a valid weight_column from the active Book."
            if weighting not in {"sigma", "1/sigma^2"}:
                return "Unknown weighting. Use 'sigma' or '1/sigma^2'."

            from processors import nonlinear_fit

            model_key = model.strip().lower().replace(" ", "_").replace("-", "_")
            custom_expr = None
            custom_params = None
            if model_key == "linear":
                nonlinear_model = "custom"
                custom_expr = "m*x+b"
                custom_params = ["m", "b"]
            elif model_key == "exponential":
                nonlinear_model = "custom"
                custom_expr = "A*exp(B*x)+C"
                custom_params = ["A", "B", "C"]
            else:
                nonlinear_model = {
                    "power_law": "power",
                }.get(model_key, model_key)
            weighted_models = {
                "gaussian", "lorentzian", "voigt", "logistic", "exp1",
                "exp2", "power", "sine", "custom",
            }
            if nonlinear_model not in weighted_models:
                return (
                    "Weighted fitting supports linear, gaussian, lorentzian, voigt, "
                    "logistic, exponential/exp1, exp2, power-law, and sine models."
                )
            result = nonlinear_fit(
                df[x_col].to_numpy(),
                df[y_col].to_numpy(),
                nonlinear_model,
                {},
                sigma=df[weight_col].to_numpy(),
                weighting=weighting,
                custom_expr=custom_expr,
                custom_params=custom_params,
                calc_ci=True,
            )
            if not result.success:
                return f"Could not fit: {result.message}"
            params = ", ".join(f"{k}={v:.4g}" for k, v in result.params.items())
            ci_text = "95% CI available" if result.ci95_lower is not None else "95% CI unavailable"
            return (
                f"Weighted fit '{model}' of {y_col} vs {x_col} using {weight_col} "
                f"({weighting}): {params} (R^2 = {result.r2:.4f}, "
                f"RMSE = {result.rmse:.4g}, chi^2_red = {result.chi2_red:.4g}; {ci_text})."
            )

        from analysis.fitting import fit_curve

        result = fit_curve(df[x_col].to_numpy(), df[y_col].to_numpy(), model)
        params = ", ".join(f"{k}={v:.4g}" for k, v in result.params.items())
        return (
            f"Fit '{result.model}' of {y_col} vs {x_col}: {params} "
            f"(R^2 = {result.r_squared:.4f})."
        )
    except Exception as exc:
        logger.debug("fit_curve tool failed", exc_info=True)
        return f"Could not fit: {exc}"


def _resolve_y_column(window, df, args: Dict[str, Any]):
    """Pick the column to operate on: explicit arg -> selected Y -> last numeric."""
    requested = args.get("column")
    if requested and requested in df.columns:
        return requested
    getter = getattr(window, "selected_y_column", None)
    selected = getter() if callable(getter) else None
    if selected and selected in df.columns:
        return selected
    numeric = _numeric_columns(df)
    return numeric[-1] if numeric else None


def _tool_smooth(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data to smooth."
    if not callable(getattr(window, "smooth_column", None)):
        return "Smoothing is not available in this context."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column to smooth."
    method = str(args.get("method", "savitzky-golay")).strip().lower()
    try:
        new_col = window.smooth_column(
            col, method,
            window=int(args.get("window", 11)),
            kernel=int(args.get("kernel", 5)),
            sigma=float(args.get("sigma", 2.0)),
        )
        return f"Smoothed '{col}' ({method}) into new column '{new_col}'."
    except Exception as exc:
        logger.debug("smooth tool failed", exc_info=True)
        return f"Could not smooth: {exc}"


def _tool_filter_signal(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data to filter."
    if not callable(getattr(window, "filter_column_butterworth", None)):
        return "Filtering is not available in this context."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column to filter."
    try:
        fs = float(args.get("fs", 0) or 0)
    except (TypeError, ValueError):
        fs = 0.0
    if fs <= 0:
        return "Provide the sampling rate 'fs' (Hz)."
    kind = str(args.get("kind", "lowpass")).strip().lower()
    cutoff = args.get("cutoff")
    try:
        new_col = window.filter_column_butterworth(col, fs, kind=kind, cutoff=cutoff)
        return f"Filtered '{col}' ({kind}, fs={fs:g} Hz) into new column '{new_col}'."
    except Exception as exc:
        logger.debug("filter_signal tool failed", exc_info=True)
        return f"Could not filter: {exc}"


def _sync_new_column(window, new_col: str) -> None:
    adder = getattr(window, "add_y_column_option", None)
    if callable(adder):
        try:
            adder(new_col)
        except Exception:
            logger.debug("add_y_column_option failed for %s", new_col, exc_info=True)


def _swap_dataframe(window, new_df) -> None:
    swap = getattr(window, "_swap_dataframe", None)
    if callable(swap):
        swap(new_df)
    else:
        window._df = new_df


def _tool_moving_average(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        from processors import add_moving_average

        window_size = int(args.get("window", 25))
        new_col = add_moving_average(df, col, window=window_size)
        _sync_new_column(window, new_col)
        return f"Added moving average (window {window_size}) of '{col}' as '{new_col}'."
    except Exception as exc:
        logger.debug("moving_average tool failed", exc_info=True)
        return f"Could not compute moving average: {exc}"


def _tool_fill_missing(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    method = str(args.get("method", "mean")).strip().lower()
    value = args.get("value")
    try:
        from analysis.cleaning import fill_missing

        new_col = fill_missing(df, col, method=method, value=value)
        _sync_new_column(window, new_col)
        return f"Filled missing values in '{col}' (method {method}) into '{new_col}'."
    except Exception as exc:
        logger.debug("fill_missing tool failed", exc_info=True)
        return f"Could not fill missing values: {exc}"


def _tool_interpolate(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        from analysis.cleaning import interpolate_missing

        new_col = interpolate_missing(df, col)
        _sync_new_column(window, new_col)
        return f"Interpolated missing values in '{col}' into '{new_col}'."
    except Exception as exc:
        logger.debug("interpolate tool failed", exc_info=True)
        return f"Could not interpolate: {exc}"


def _tool_normalize(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    method = str(args.get("method", "zscore")).strip().lower()
    try:
        from analysis.cleaning import normalize_column

        new_col = normalize_column(df, col, method=method)
        _sync_new_column(window, new_col)
        return f"Normalized '{col}' ({method}) into '{new_col}'."
    except Exception as exc:
        logger.debug("normalize tool failed", exc_info=True)
        return f"Could not normalize: {exc}"


def _tool_detrend(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    x_getter = getattr(window, "selected_x_column", None)
    x_col = x_getter() if callable(x_getter) else None
    if x_col not in getattr(df, "columns", []):
        x_col = None
    try:
        from analysis.cleaning import detrend_polynomial

        order = int(args.get("order", 1))
        new_col = detrend_polynomial(df, col, order=order, x_col=x_col)
        _sync_new_column(window, new_col)
        return f"Removed order-{order} trend from '{col}' into '{new_col}'."
    except Exception as exc:
        logger.debug("detrend tool failed", exc_info=True)
        return f"Could not detrend: {exc}"


def _tool_remove_outliers(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    method = str(args.get("method", "zscore")).strip().lower()
    threshold = args.get("threshold")
    try:
        from analysis.cleaning import remove_outliers

        new_df, removed = remove_outliers(
            df, col, method=method,
            threshold=float(threshold) if threshold is not None else None,
        )
        _swap_dataframe(window, new_df)
        return f"Removed {removed} outlier rows from '{col}' (method {method}); {len(new_df)} rows remain."
    except Exception as exc:
        logger.debug("remove_outliers tool failed", exc_info=True)
        return f"Could not remove outliers: {exc}"


def _tool_find_anomalies(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    method = str(args.get("method", "zscore")).strip().lower()
    threshold = args.get("threshold")
    try:
        from analysis.cleaning import summarize_anomalies

        report = summarize_anomalies(
            df[col],
            method=method,
            threshold=float(threshold) if threshold is not None else None,
        )
        n = report["n_anomalies"]
        if n == 0:
            return (
                f"No anomalies in '{col}' ({report['n_total']} points, "
                f"method {report['method']} @ {report['threshold']:g})."
            )
        pct = report["fraction"] * 100.0
        head = ", ".join(
            f"row {p['index']}={p['value']:g} (z={p['zscore']:.1f})"
            for p in report["points"][:5]
        )
        more = "" if n <= 5 else f" (+{n - 5} more)"
        return (
            f"Found {n} anomalies in '{col}' of {report['n_total']} points "
            f"({pct:.1f}%, method {report['method']} @ {report['threshold']:g}). "
            f"Most extreme: {head}{more}."
        )
    except Exception as exc:
        logger.debug("find_anomalies tool failed", exc_info=True)
        return f"Could not find anomalies: {exc}"


def _tool_remove_duplicates(window, _args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    try:
        from analysis.cleaning import remove_duplicates

        new_df, removed = remove_duplicates(df)
        _swap_dataframe(window, new_df)
        return f"Removed {removed} duplicate rows; {len(new_df)} rows remain."
    except Exception as exc:
        logger.debug("remove_duplicates tool failed", exc_info=True)
        return f"Could not remove duplicates: {exc}"


def _tool_sort_data(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = args.get("column")
    if not col or col not in df.columns:
        return f"Provide a valid 'column' to sort by. Available: {', '.join(str(c) for c in df.columns)}."
    ascending = args.get("ascending", True)
    ascending = str(ascending).strip().lower() not in {"false", "0", "desc", "descending", "no"}
    try:
        from analysis.cleaning import sort_dataframe

        new_df = sort_dataframe(df, col, ascending=ascending)
        _swap_dataframe(window, new_df)
        return f"Sorted data by '{col}' ({'ascending' if ascending else 'descending'})."
    except Exception as exc:
        logger.debug("sort_data tool failed", exc_info=True)
        return f"Could not sort: {exc}"


def _tool_list_books(window, _args: Dict[str, Any]) -> str:
    getter = getattr(window, "_dataset_names", None)
    names = getter() if callable(getter) else None
    if not names:
        label = getattr(window, "_active_book_label", None)
        active = label() if callable(label) else None
        return f"Open Books: {active}" if active else "No Books are open."
    active_getter = getattr(window, "_active_book_label", None)
    active = active_getter() if callable(active_getter) else None
    marked = [f"{n} (active)" if n == active else n for n in names]
    return f"Open Books ({len(names)}): " + ", ".join(marked)


def _tool_envelope(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        from analysis.signal_filters import signal_envelope

        env = signal_envelope(df[col])
        new_col = f"{col}_envelope"
        df[new_col] = env
        _sync_new_column(window, new_col)
        return f"Computed the amplitude envelope of '{col}' as '{new_col}'."
    except Exception as exc:
        logger.debug("envelope tool failed", exc_info=True)
        return f"Could not compute envelope: {exc}"


def _tool_signal_quality(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        fs = float(args.get("fs", 1.0) or 1.0)
    except (TypeError, ValueError):
        fs = 1.0
    try:
        from analysis.signal_filters import signal_quality_summary

        summary = signal_quality_summary(df[col], fs=fs)
        return (
            f"Signal quality of '{col}' (fs={summary['fs_hz']:g} Hz): "
            f"SNR ≈ {summary['snr_db']:.2f} dB, noise floor ≈ {summary['noise_floor']:.4g}."
        )
    except Exception as exc:
        logger.debug("signal_quality tool failed", exc_info=True)
        return f"Could not assess signal quality: {exc}"


def _tool_fft(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data for FFT."
    numeric = _numeric_columns(df)
    if not numeric:
        return "Need a numeric column for FFT."
    y_col = _resolve_y_column(window, df, args)
    x_req = args.get("x_column")
    x_getter = getattr(window, "selected_x_column", None)
    x_sel = x_getter() if callable(x_getter) else None
    x_col = (x_req if x_req in df.columns else None) or (x_sel if x_sel in df.columns else None) or numeric[0]
    if y_col is None or y_col == x_col:
        y_col = next((c for c in numeric if c != x_col), y_col)
    if y_col is None:
        return "Need a numeric signal column for FFT."
    try:
        from processors import compute_fft

        df_fft, fs = compute_fft(df, x_col=x_col, y_col=y_col)
        opener = getattr(window, "_open_signal_result_book", None)
        if callable(opener):
            opener(f"FFT_{y_col}", df_fft)
        peak_freq = float(df_fft.loc[df_fft["amplitude"].idxmax(), "freq_Hz"])
        return (
            f"Computed FFT of '{y_col}' (fs≈{fs:.4g} Hz). Dominant frequency "
            f"≈ {peak_freq:.4g} Hz. Spectrum opened as a result Book."
        )
    except Exception as exc:
        logger.debug("fft tool failed", exc_info=True)
        return f"Could not compute FFT: {exc}"


def _open_result(window, name: str, result_df) -> bool:
    opener = getattr(window, "_open_signal_result_book", None)
    if callable(opener):
        opener(name, result_df)
        return True
    return False


def _tool_power_spectrum(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        fs = float(args.get("fs", 1.0) or 1.0)
    except (TypeError, ValueError):
        fs = 1.0
    try:
        import pandas as pd
        from analysis.signal_filters import compute_psd

        freqs, psd = compute_psd(df[col], fs=fs)
        _open_result(window, f"PSD_{col}", pd.DataFrame({"freq_Hz": freqs, "psd": psd}))
        peak = float(freqs[int(psd.argmax())]) if len(psd) else 0.0
        return f"Power spectral density of '{col}' (fs={fs:g} Hz); peak at ≈ {peak:.4g} Hz. Opened as a Book."
    except Exception as exc:
        logger.debug("psd tool failed", exc_info=True)
        return f"Could not compute PSD: {exc}"


def _tool_autocorrelation(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        import pandas as pd
        from analysis.signal_filters import autocorrelation

        lags, corr = autocorrelation(df[col])
        _open_result(window, f"Autocorr_{col}", pd.DataFrame({"lag": lags, "autocorr": corr}))
        return f"Auto-correlation of '{col}' computed ({len(lags)} lags). Opened as a Book."
    except Exception as exc:
        logger.debug("autocorrelation tool failed", exc_info=True)
        return f"Could not compute auto-correlation: {exc}"


def _tool_instantaneous_frequency(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        fs = float(args.get("fs", 1.0) or 1.0)
    except (TypeError, ValueError):
        fs = 1.0
    try:
        from analysis.signal_filters import instantaneous_frequency

        inst = instantaneous_frequency(df[col], fs=fs)
        new_col = f"{col}_inst_freq"
        df[new_col] = inst
        _sync_new_column(window, new_col)
        return f"Instantaneous frequency of '{col}' (fs={fs:g} Hz) added as '{new_col}'."
    except Exception as exc:
        logger.debug("instantaneous_frequency tool failed", exc_info=True)
        return f"Could not compute instantaneous frequency: {exc}"


def _tool_harmonic_analysis(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric column."
    try:
        fs = float(args.get("fs", 1.0) or 1.0)
    except (TypeError, ValueError):
        fs = 1.0
    try:
        import numpy as np
        import pandas as pd
        from analysis.signal_filters import harmonic_analysis

        result = harmonic_analysis(df[col], fs=fs)
        columns = {k: np.asarray(v) for k, v in result.items() if np.ndim(v) > 0}
        _open_result(window, f"Harmonics_{col}", pd.DataFrame(columns))
        n = len(next(iter(columns.values()))) if columns else 0
        return f"Harmonic analysis of '{col}' (fs={fs:g} Hz): {n} components. Opened as a Book."
    except Exception as exc:
        logger.debug("harmonic_analysis tool failed", exc_info=True)
        return f"Could not run harmonic analysis: {exc}"


def _xy_arrays(window, df, args: Dict[str, Any]):
    """Return (x, y) numpy arrays: y = resolved column, x = selected X or row index."""
    import numpy as np

    y_col = _resolve_y_column(window, df, args)
    if y_col is None:
        return None, None, None
    x_getter = getattr(window, "selected_x_column", None)
    x_col = x_getter() if callable(x_getter) else None
    if x_col in getattr(df, "columns", []) and x_col != y_col:
        x = df[x_col].to_numpy(dtype=float)
    else:
        x = np.arange(len(df), dtype=float)
    return x, df[y_col].to_numpy(dtype=float), y_col


def _tool_peak_metrics(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    x, y, col = _xy_arrays(window, df, args)
    if y is None:
        return "Need a numeric column."
    try:
        from analysis.signal_filters import peak_metrics_summary

        m = peak_metrics_summary(x, y)
        fwhm = f"{m['fwhm']:.4g}" if m.get("fwhm") is not None else "n/a"
        return (
            f"Main peak of '{col}': height {m['peak_height']:.4g} at x={m['peak_x']:.4g}, "
            f"area {m['area']:.4g}, FWHM {fwhm}."
        )
    except Exception as exc:
        logger.debug("peak_metrics tool failed", exc_info=True)
        return f"Could not compute peak metrics: {exc}"


def _tool_detect_peaks(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    thai = str(args.get("language", "")).casefold() == "th"
    if df is None or getattr(df, "empty", True):
        return "ไม่มีข้อมูลที่กำลังใช้งาน" if thai else "No active data."
    x, y, col = _xy_arrays(window, df, args)
    if y is None:
        return "ต้องมีคอลัมน์ตัวเลขสำหรับหาพีค" if thai else "Need a numeric column."
    try:
        import numpy as np
        import pandas as pd
        from scipy.signal import find_peaks

        finite = np.isfinite(x) & np.isfinite(y)
        x = np.asarray(x, dtype=float)[finite]
        y = np.asarray(y, dtype=float)[finite]
        if len(y) < 3:
            return "ข้อมูลน้อยเกินไปสำหรับหาพีค" if thai else "Need at least 3 finite points to find peaks."
        kwargs = {}
        if args.get("prominence") is not None:
            kwargs["prominence"] = float(args["prominence"])
        if args.get("distance") is not None:
            kwargs["distance"] = max(1, int(args["distance"]))
        if args.get("auto") and "prominence" not in kwargs:
            spread = float(np.nanpercentile(y, 95) - np.nanpercentile(y, 5))
            kwargs["prominence"] = max(
                spread * 0.08,
                float(np.nanstd(y)) * 0.15,
                1e-12,
            )
            kwargs.setdefault("distance", max(1, len(y) // 250))
        idx, _props = find_peaks(y, **kwargs)
        if len(idx) == 0:
            return (
                f"ไม่พบพีคใน '{col}' ลองลดค่า prominence"
                if thai
                else f"No peaks found in '{col}'. Try a lower prominence."
            )
        _open_result(
            window, f"Peaks_{col}",
            pd.DataFrame({"peak_x": x[idx], "peak_height": y[idx]}),
        )
        top = idx[np.argsort(y[idx])[::-1][:3]]
        tops = ", ".join(f"x={x[i]:.4g} (h={y[i]:.4g})" for i in top)
        return (
            f"พบ {len(idx)} พีคใน '{col}' พีคเด่น: {tops} เปิดตารางผลลัพธ์เป็น Book แล้ว"
            if thai
            else f"Found {len(idx)} peaks in '{col}'. Strongest: {tops}. Table opened as a Book."
        )
    except Exception as exc:
        logger.debug("detect_peaks tool failed", exc_info=True)
        return f"Could not detect peaks: {exc}"


def _tool_cross_correlation(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    numeric = _numeric_columns(df)
    a_col = args.get("column_a") or (numeric[0] if len(numeric) >= 1 else None)
    b_col = args.get("column_b") or (numeric[1] if len(numeric) >= 2 else None)
    if a_col not in df.columns or b_col not in df.columns or a_col == b_col:
        return "Need two different numeric columns (column_a and column_b)."
    try:
        import numpy as np
        import pandas as pd
        from scipy.signal import correlate, correlation_lags

        a = df[a_col].to_numpy(dtype=float)
        b = df[b_col].to_numpy(dtype=float)
        a = a - np.nanmean(a)
        b = b - np.nanmean(b)
        corr = correlate(a, b, mode="full")
        lags = correlation_lags(len(a), len(b), mode="full")
        denom = np.sqrt(np.sum(a * a) * np.sum(b * b)) or 1.0
        corr = corr / denom
        _open_result(window, f"XCorr_{a_col}_{b_col}", pd.DataFrame({"lag": lags, "xcorr": corr}))
        best = int(np.argmax(np.abs(corr)))
        return (
            f"Cross-correlation of '{a_col}' vs '{b_col}': peak {corr[best]:.3f} at lag "
            f"{int(lags[best])} samples. Result opened as a Book."
        )
    except Exception as exc:
        logger.debug("cross_correlation tool failed", exc_info=True)
        return f"Could not cross-correlate: {exc}"


def _tool_format_graph(window, args: Dict[str, Any]) -> str:
    axes_getter = getattr(window, "active_axes", None)
    ax = axes_getter() if callable(axes_getter) else None
    if ax is None:
        return "No active graph to format. Create a plot first."
    changed = []
    try:
        if args.get("title") is not None:
            ax.set_title(str(args["title"])); changed.append("title")
        if args.get("xlabel") is not None:
            ax.set_xlabel(str(args["xlabel"])); changed.append("x-label")
        if args.get("ylabel") is not None:
            ax.set_ylabel(str(args["ylabel"])); changed.append("y-label")
        if "grid" in args:
            ax.grid(bool(args["grid"])); changed.append("grid")
        if args.get("legend"):
            ax.legend(); changed.append("legend")
        if args.get("logx"):
            ax.set_xscale("log"); changed.append("log-x")
        if args.get("logy"):
            ax.set_yscale("log"); changed.append("log-y")
        fig = getattr(ax, "figure", None)
        if fig is not None and getattr(fig, "canvas", None) is not None:
            fig.canvas.draw_idle()
    except Exception as exc:
        logger.debug("format_graph tool failed", exc_info=True)
        return f"Could not format the graph: {exc}"
    return f"Updated the graph: {', '.join(changed)}." if changed else "Nothing to change."


def _tool_list_charts(_window, _args: Dict[str, Any]) -> str:
    try:
        from plots.registry import all_plots

        keys = [str(p.get("key")) for p in all_plots() if p.get("key")]
        return f"Available chart types ({len(keys)}): " + ", ".join(keys)
    except Exception as exc:
        logger.debug("list_charts tool failed", exc_info=True)
        return f"Could not list charts: {exc}"


def _tool_plot_chart(window, args: Dict[str, Any]) -> str:
    key = str(args.get("chart_type", "")).strip()
    if not key:
        return "Provide 'chart_type' (see list_charts for options)."
    try:
        from plots.registry import get_plot
    except Exception as exc:
        return f"Charts unavailable: {exc}"
    entry = get_plot(key)
    if entry is None:
        return f"Unknown chart '{key}'. Use list_charts to see valid types."
    if not callable(getattr(window, "plot_from_gallery", None)):
        return "Charts are not available in this context."
    previous = getattr(window, "_suppress_plot_mapping_dialog", False)
    window._suppress_plot_mapping_dialog = True  # non-interactive: use active data
    try:
        window.plot_from_gallery(entry)
    except Exception as exc:
        logger.debug("plot_chart tool failed", exc_info=True)
        return f"Could not create the chart: {exc}"
    finally:
        window._suppress_plot_mapping_dialog = previous
    return f"Created a '{entry.get('title', key)}' chart in a new Graph."


def _tool_open_file(window, args: Dict[str, Any]) -> str:
    import os

    path = str(args.get("path", "")).strip()
    if not path:
        return "Provide a 'path' to the data file to open."
    if not os.path.isfile(path):
        return f"File not found: {path}"
    inserter = getattr(window, "_stage_insert", None)
    if not callable(inserter):
        return "Opening files is not available in this context."
    try:
        from loaders import load_tabular

        df, name = load_tabular(path)
        inserter(name, df, path)
        return f"Opened '{name}' ({len(df)} rows, {len(df.columns)} columns) into a new Book."
    except Exception as exc:
        logger.debug("open_file tool failed", exc_info=True)
        return f"Could not open '{path}': {exc}"


def build_app_registry(window) -> ToolRegistry:
    """Registry of tools bound to *window* (a MainWindow-like object)."""
    registry = ToolRegistry()
    registry.set_context_provider(lambda: _safe_argument_context(window))
    registry.add(
        "list_columns",
        "List the column names, row count and column count of the active data table (Book).",
        {},
        lambda args: _tool_list_columns(window, args),
    )
    registry.add(
        "describe_data",
        "Compute descriptive statistics (count, mean, std, min, max, ...) for the active data. "
        "Optional 'columns' is a list of column names; omit it for all numeric columns.",
        {"columns": {"type": "array", "description": "column names to describe", "required": False}},
        lambda args: _tool_describe_data(window, args),
    )
    registry.add(
        "summarize_data",
        "Analyze the active Book directly and return a concise evidence-backed summary: "
        "shape, missing values, numeric ranges, mean/SD, correlation, maximum and "
        "prominent peaks. Supports Thai or English output.",
        {
            "language": {
                "type": "string",
                "description": "th | en",
                "required": False,
                "enum": ["th", "en"],
            }
        },
        lambda args: _tool_summarize_data(window, args),
    )
    registry.add(
        "plot_columns",
        "Create a real graph from the active Book. Prefer explicit x_column and y_columns "
        "when the user names columns. If omitted, SciPlotter resolves columns from the "
        "original instruction and then from the active Book designations.",
        {
            "style": {
                "type": "string",
                "description": "line | linesymbol | scatter | bar | histogram",
                "required": False,
                "enum": ["line", "linesymbol", "scatter", "bar", "histogram"],
            },
            "x_column": {
                "type": "string",
                "description": "column for the X axis; omit for histogram or row index",
                "required": False,
            },
            "y_columns": {
                "type": "array",
                "description": "one or more numeric Y columns",
                "required": False,
            },
            "instruction": {
                "type": "string",
                "description": "the user's original plot command, used to resolve named columns",
                "required": False,
            },
            "new_graph": {
                "type": "boolean",
                "description": "true creates a new Graph; false adds to the active Graph",
                "required": False,
            },
        },
        lambda args: _tool_plot(window, args),
    )
    registry.add(
        "active_book",
        "Report which data Book (dataset) is currently active.",
        {},
        lambda args: _tool_active_book(window, args),
    )
    registry.add(
        "gas_live_control",
        "Control receive-only Serial or NI-DAQmx gas-sensor acquisition without dialogs. "
        "action: status|connect|disconnect|mark_on|mark_off|flow_status|configure_flow|configure_wiring. Serial connect requires port; "
        "NI-DAQ connect requires transport=ni_daq, device, and channel. Markers only annotate SciPlotter.",
        {
            "action": {"type": "string", "description": "status|connect|disconnect|mark_on|mark_off|flow_status|configure_flow|configure_wiring", "required": True, "enum": ["status", "connect", "disconnect", "mark_on", "mark_off", "flow_status", "configure_flow", "configure_wiring"]},
            "transport": {"type": "string", "description": "serial|ni_daq; default serial", "required": False, "enum": ["serial", "ni_daq"]},
            "port": {"type": "string", "description": "serial port for connect", "required": False},
            "baud": {"type": "number", "description": "baud rate; default 115200", "required": False},
            "device": {"type": "string", "description": "NI-DAQ device, for example Dev1", "required": False},
            "channel": {"type": "string", "description": "one or more comma-separated NI analog-input channels, for example Dev1/ai0,Dev1/ai1", "required": False},
            "sample_rate_hz": {"type": "number", "description": "NI-DAQ rate from 1 to 20 Hz", "required": False},
            "min_voltage": {"type": "number", "description": "NI-DAQ input minimum voltage", "required": False},
            "max_voltage": {"type": "number", "description": "NI-DAQ input maximum voltage", "required": False},
            "terminal_config": {"type": "string", "description": "RSE|DIFFERENTIAL|NRSE", "required": False, "enum": ["RSE", "DIFFERENTIAL", "NRSE"]},
            "label": {"type": "string", "description": "optional exposure marker label", "required": False},
            "preset": {"type": "string", "description": "visual flow preset: raw|resistance|smoothed", "required": False, "enum": ["raw", "resistance", "smoothed"]},
            "voltage_to_resistance": {"type": "boolean", "description": "enable voltage-divider conversion", "required": False},
            "voltage_field": {"type": "string", "description": "flow input voltage field; blank auto-detects", "required": False},
            "supply_voltage_v": {"type": "number", "description": "voltage-divider supply voltage", "required": False},
            "reference_resistance_ohm": {"type": "number", "description": "known divider resistor in ohms", "required": False},
            "divider_topology": {"type": "string", "description": "sensor_high|sensor_low", "required": False, "enum": ["sensor_high", "sensor_low"]},
            "smoothing": {"type": "boolean", "description": "enable moving-average node", "required": False},
            "smoothing_field": {"type": "string", "description": "moving-average input field", "required": False},
            "smoothing_window": {"type": "number", "description": "moving-average window in samples", "required": False},
            "sensor_channels": {
                "type": "array",
                "description": "independent sensor mappings with source_field, alias, voltage_to_resistance, supply_voltage_v, reference_resistance_ohm, divider_topology, smoothing, and smoothing_window",
                "required": False,
            },
            "edges": {"type": "array", "description": "flow wire pairs, e.g. [[source,divider],[divider,book],[book,graph]]", "required": False},
        },
        lambda args: _tool_gas_live_control(window, args),
    )
    registry.add(
        "list_fit_models",
        "List the curve-fit models available (linear, exponential, gaussian, ...).",
        {},
        lambda args: _tool_list_fit_models(window, args),
    )
    registry.add(
        "fit_curve",
        "Fit a curve to the active data and return the parameters and R-squared. "
        "'model' is a fit model name; x_column/y_column are optional (default: first "
        "two numeric columns). For weighted fitting, pass weight_column and weighting "
        "as 'sigma' (absolute uncertainty) or '1/sigma^2' (inverse-variance weights).",
        {
            "model": {"type": "string", "description": "fit model name", "required": True},
            "x_column": {"type": "string", "description": "x column name", "required": False},
            "y_column": {"type": "string", "description": "y column name", "required": False},
            "weight_column": {
                "type": "string",
                "description": "column containing absolute uncertainty or inverse-variance weights",
                "required": False,
            },
            "weighting": {
                "type": "string",
                "description": "none|sigma|1/sigma^2",
                "required": False,
                "enum": ["none", "sigma", "1/sigma^2"],
            },
        },
        lambda args: _tool_fit_curve(window, args),
    )
    registry.add(
        "smooth_data",
        "Smooth a column and add the result as a new column. method: "
        "savitzky-golay | median | gaussian. column optional (default: active Y / last numeric).",
        {
            "method": {"type": "string", "description": "savitzky-golay|median|gaussian", "required": False, "enum": ["savitzky-golay", "median", "gaussian"]},
            "column": {"type": "string", "description": "column to smooth", "required": False},
            "window": {"type": "number", "description": "savgol window (odd)", "required": False},
        },
        lambda args: _tool_smooth(window, args),
    )
    registry.add(
        "filter_signal",
        "Apply a zero-phase Butterworth filter and add the result as a new column. "
        "Requires 'fs' (Hz). kind: lowpass|highpass|bandpass|bandstop. cutoff is a "
        "number (low/high pass) or [low, high] (band pass/stop).",
        {
            "fs": {"type": "number", "description": "sampling rate in Hz", "required": True},
            "kind": {"type": "string", "description": "lowpass|highpass|bandpass|bandstop", "required": False, "enum": ["lowpass", "highpass", "bandpass", "bandstop"]},
            "cutoff": {"type": "number", "description": "cutoff Hz (or [low,high])", "required": False},
            "column": {"type": "string", "description": "column to filter", "required": False},
        },
        lambda args: _tool_filter_signal(window, args),
    )
    registry.add(
        "moving_average",
        "Add a moving-average (rolling mean) column. window optional (default 25).",
        {
            "window": {"type": "number", "description": "window size", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_moving_average(window, args),
    )
    registry.add(
        "fill_missing",
        "Fill missing (NaN) values in a column into a new column. method: "
        "mean | median | ffill | bfill | value (with 'value').",
        {
            "method": {"type": "string", "description": "fill method", "required": False, "enum": ["mean", "median", "ffill", "bfill", "value"]},
            "value": {"type": "number", "description": "value when method=value", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_fill_missing(window, args),
    )
    registry.add(
        "interpolate",
        "Interpolate missing values in a column into a new column.",
        {"column": {"type": "string", "description": "column", "required": False}},
        lambda args: _tool_interpolate(window, args),
    )
    registry.add(
        "normalize",
        "Rescale a column into a new column. method: zscore (mean 0/std 1) or minmax (0-1).",
        {
            "method": {"type": "string", "description": "zscore|minmax", "required": False, "enum": ["zscore", "minmax"]},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_normalize(window, args),
    )
    registry.add(
        "detrend",
        "Remove a polynomial trend/baseline from a column into a new column. "
        "order optional (1 = linear).",
        {
            "order": {"type": "number", "description": "polynomial order", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_detrend(window, args),
    )
    registry.add(
        "remove_outliers",
        "Drop rows where a column is an outlier (replaces the active data). "
        "method: zscore | iqr; threshold optional.",
        {
            "method": {"type": "string", "description": "zscore|iqr", "required": False, "enum": ["zscore", "iqr"]},
            "threshold": {"type": "number", "description": "threshold", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_remove_outliers(window, args),
    )
    registry.add(
        "find_anomalies",
        "Report anomalous/outlier points in a column WITHOUT changing the data. "
        "method: zscore | iqr; threshold optional. Returns count and the most "
        "extreme points (row index, value, z-score).",
        {
            "method": {"type": "string", "description": "zscore|iqr", "required": False, "enum": ["zscore", "iqr"]},
            "threshold": {"type": "number", "description": "threshold", "required": False},
            "column": {"type": "string", "description": "column", "required": False},
        },
        lambda args: _tool_find_anomalies(window, args),
    )
    registry.add(
        "remove_duplicates",
        "Remove duplicate rows from the active data (replaces it).",
        {},
        lambda args: _tool_remove_duplicates(window, args),
    )
    registry.add(
        "sort_data",
        "Sort the active data by a column (replaces it). ascending true/false.",
        {
            "column": {"type": "string", "description": "column to sort by", "required": True},
            "ascending": {"type": "boolean", "description": "ascending order", "required": False},
        },
        lambda args: _tool_sort_data(window, args),
    )
    registry.add(
        "run_fft",
        "Compute the FFT amplitude/power spectrum of a signal column and open it "
        "as a result Book; reports the dominant frequency. column/x_column optional.",
        {
            "column": {"type": "string", "description": "signal (Y) column", "required": False},
            "x_column": {"type": "string", "description": "time/X column for fs", "required": False},
        },
        lambda args: _tool_fft(window, args),
    )
    registry.add(
        "envelope",
        "Compute the amplitude (Hilbert) envelope of a signal column into a new column.",
        {"column": {"type": "string", "description": "signal column", "required": False}},
        lambda args: _tool_envelope(window, args),
    )
    registry.add(
        "signal_quality",
        "Report a signal's SNR (dB) and noise floor. fs optional (Hz).",
        {
            "fs": {"type": "number", "description": "sampling rate Hz", "required": False},
            "column": {"type": "string", "description": "signal column", "required": False},
        },
        lambda args: _tool_signal_quality(window, args),
    )
    registry.add(
        "power_spectrum",
        "Compute the power spectral density (PSD) of a signal column and open it "
        "as a result Book; reports the peak. fs optional (Hz).",
        {
            "fs": {"type": "number", "description": "sampling rate Hz", "required": False},
            "column": {"type": "string", "description": "signal column", "required": False},
        },
        lambda args: _tool_power_spectrum(window, args),
    )
    registry.add(
        "autocorrelation",
        "Compute the auto-correlation of a signal column and open it as a result Book.",
        {"column": {"type": "string", "description": "signal column", "required": False}},
        lambda args: _tool_autocorrelation(window, args),
    )
    registry.add(
        "instantaneous_frequency",
        "Add the instantaneous frequency (Hz, from the Hilbert phase) of a signal "
        "column as a new column. fs optional.",
        {
            "fs": {"type": "number", "description": "sampling rate Hz", "required": False},
            "column": {"type": "string", "description": "signal column", "required": False},
        },
        lambda args: _tool_instantaneous_frequency(window, args),
    )
    registry.add(
        "harmonic_analysis",
        "Find the strongest harmonic components of a signal column and open them "
        "as a result Book. fs optional.",
        {
            "fs": {"type": "number", "description": "sampling rate Hz", "required": False},
            "column": {"type": "string", "description": "signal column", "required": False},
        },
        lambda args: _tool_harmonic_analysis(window, args),
    )
    registry.add(
        "peak_metrics",
        "Report the main peak of a column: height, position, area and FWHM.",
        {"column": {"type": "string", "description": "signal column", "required": False}},
        lambda args: _tool_peak_metrics(window, args),
    )
    registry.add(
        "detect_peaks",
        "Find peaks in a column and open a table of peak positions/heights as a Book. "
        "prominence/distance optional.",
        {
            "column": {"type": "string", "description": "signal column", "required": False},
            "prominence": {"type": "number", "description": "min prominence", "required": False},
            "distance": {"type": "number", "description": "min samples between peaks", "required": False},
            "auto": {"type": "boolean", "description": "derive robust prominence and distance", "required": False},
            "language": {"type": "string", "description": "th | en", "required": False, "enum": ["th", "en"]},
        },
        lambda args: _tool_detect_peaks(window, args),
    )
    registry.add(
        "cross_correlation",
        "Cross-correlate two numeric columns; report the peak correlation and its "
        "lag, and open the full curve as a Book. Defaults to the first two numeric columns.",
        {
            "column_a": {"type": "string", "description": "first column", "required": False},
            "column_b": {"type": "string", "description": "second column", "required": False},
        },
        lambda args: _tool_cross_correlation(window, args),
    )
    registry.add(
        "format_graph",
        "Decorate the active graph: set title / xlabel / ylabel, toggle grid or "
        "legend, or switch axes to log (logx/logy).",
        {
            "title": {"type": "string", "description": "graph title", "required": False},
            "xlabel": {"type": "string", "description": "x axis label", "required": False},
            "ylabel": {"type": "string", "description": "y axis label", "required": False},
            "grid": {"type": "boolean", "description": "show grid", "required": False},
            "legend": {"type": "boolean", "description": "show legend", "required": False},
            "logx": {"type": "boolean", "description": "log x axis", "required": False},
            "logy": {"type": "boolean", "description": "log y axis", "required": False},
        },
        lambda args: _tool_format_graph(window, args),
    )
    registry.add(
        "list_charts",
        "List the advanced chart types available in the Chart Gallery.",
        {},
        lambda args: _tool_list_charts(window, args),
    )
    registry.add(
        "plot_chart",
        "Create an advanced chart from the active data in a new Graph. "
        "chart_type is one of the keys from list_charts.",
        {"chart_type": {"type": "string", "description": "chart key", "required": True}},
        lambda args: _tool_plot_chart(window, args),
    )
    registry.add(
        "list_books",
        "List the open data Books (datasets) and which one is active. "
        "Use this before operating on a specific Book.",
        {},
        lambda args: _tool_list_books(window, args),
    )
    registry.add(
        "open_file",
        "Open a data file (CSV/Excel/...) from an absolute path into a new Book.",
        {"path": {"type": "string", "description": "absolute file path", "required": True}},
        lambda args: _tool_open_file(window, args),
    )
    # Specialized science modules (Gas Sensor / Echem / Spectroscopy / ...).
    try:
        from ai.module_tools import register_module_tools

        register_module_tools(registry, window)
    except Exception:
        logger.debug("module tools registration skipped", exc_info=True)
    return registry
