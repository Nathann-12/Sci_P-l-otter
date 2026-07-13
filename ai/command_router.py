"""Deterministic routing for common commands that should never depend on an LLM.

The local model remains responsible for open-ended analysis. High-frequency app
actions such as plotting get a conservative fast path so they still work with a
small model, or when Ollama is temporarily unavailable.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


ToolCall = Tuple[str, Dict[str, Any]]

_EXPLICIT_PLOT_RE = re.compile(
    r"(?:\bplot\b|\bdraw\s+(?:a\s+)?(?:graph|chart|plot)\b|"
    r"\b(?:make|create)\s+(?:me\s+)?(?:a\s+)?(?:graph|chart|plot)\b|"
    r"พล็อต|พลอต|สร้าง\s*กราฟ|วาด\s*กราฟ|ทำ\s*กราฟ)",
    re.IGNORECASE,
)
_STYLE_COMMAND_RE = re.compile(
    r"^\s*(?:line(?:\s+plot)?|scatter(?:\s*plot)?|bar(?:\s+chart)?|"
    r"histogram|กราฟเส้น|กราฟจุด|กราฟกระจาย|กราฟแท่ง|ฮิสโตแกรม)\b",
    re.IGNORECASE,
)
_NON_ACTION_RE = re.compile(
    r"(?:explain|describe|recommend|which|what|why|how|"
    r"อธิบาย|แนะนำ|อะไรดี|เหมาะ(?:กับ)?อะไร|คืออะไร|ทำไม)",
    re.IGNORECASE,
)
_NEGATED_PLOT_RE = re.compile(
    r"(?:\b(?:do\s+not|don't|dont|never)\s+"
    r"(?:plot|draw\s+(?:a\s+)?(?:plot|graph|chart)|"
    r"(?:make|create)\s+(?:a\s+)?(?:plot|graph|chart))\b|"
    r"\bwithout\s+(?:a\s+)?(?:plot|graph|chart)\b|"
    r"(?:ไม่ต้อง|อย่า|ห้าม)\s*(?:พล็อต|พลอต|สร้าง\s*กราฟ|วาด\s*กราฟ|ทำ\s*กราฟ))",
    re.IGNORECASE,
)
_ANALYZE_RE = re.compile(
    r"(?:\b(?:analy[sz]e|summari[sz]e|inspect)\b|วิเคราะห์|สรุป(?:ข้อมูล)?)",
    re.IGNORECASE,
)
_COLUMNS_RE = re.compile(
    r"(?:\b(?:list|show)\s+(?:the\s+)?columns?\b|"
    r"\bwhat\s+columns?\b|คอลัมน์(?:อะไร|ไหน|ทั้งหมด)?|แสดง\s*คอลัมน์)",
    re.IGNORECASE,
)
_PEAK_RE = re.compile(
    r"(?:\b(?:find|detect)\s+(?:the\s+)?peaks?\b|หาพีค|ตรวจ(?:จับ)?\s*พีค|หาจุดสูงสุด)",
    re.IGNORECASE,
)
_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")


def _plot_style(text: str) -> str:
    folded = text.casefold()
    if re.search(r"histogram|ฮิสโตแกรม|การแจกแจง", folded):
        return "histogram"
    if re.search(r"scatter(?:\s*plot)?|กราฟกระจาย|กราฟจุด|แบบจุด", folded):
        return "scatter"
    if re.search(r"bar(?:\s+chart)?|column(?:\s+chart)?|กราฟแท่ง|แบบแท่ง", folded):
        return "bar"
    if re.search(r"line\s*(?:\+|and|with)\s*(?:symbol|marker)|เส้น(?:พร้อม|และ)จุด", folded):
        return "linesymbol"
    return "line"


def route_command(text: str) -> Optional[ToolCall]:
    """Return a safe direct tool call for an unambiguous app command."""
    original = str(text or "").strip()
    if not original:
        return None

    language = "th" if _THAI_RE.search(original) else "en"
    plot_requested = _EXPLICIT_PLOT_RE.search(original) is not None
    if _PEAK_RE.search(original) and not plot_requested:
        return (
            "detect_peaks",
            {"language": language, "auto": True},
        )
    if _ANALYZE_RE.search(original) and not plot_requested:
        return (
            "summarize_data",
            {"language": language, "instruction": original},
        )
    if _COLUMNS_RE.search(original) and not plot_requested:
        return (
            "list_columns",
            {"language": language},
        )
    if _NEGATED_PLOT_RE.search(original):
        return None

    explicit = plot_requested
    style_command = _STYLE_COMMAND_RE.search(original) is not None
    if _NON_ACTION_RE.search(original):
        return None
    if not explicit and not style_command:
        return None

    return (
        "plot_columns",
        {
            "style": _plot_style(original),
            "instruction": original,
            "new_graph": True,
        },
    )
