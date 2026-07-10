"""Small runtime guard for keeping user-facing chrome in English.

The project still contains a few legacy Thai strings and UTF-8 mojibake from
older UI code. This module does not translate user data; it only normalizes UI
labels/messages that pass through the view seam.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


_THAI_RE = re.compile(r"[\u0e00-\u0e7f]")
_MOJIBAKE_RE = re.compile(r"(?:\u00e0|\u00c3|\u00e2|\u00a0|\u00b8|\u00b9)")
_ASCII_RE = re.compile(r"[A-Za-z0-9_.,:;()[\]/+*%<>=\-\s]+")


_PHRASES = {
    "ยังไม่มีข้อมูล": "No data",
    "ไม่มีข้อมูล": "No data",
    "โปรดเปิดไฟล์ก่อน": "Open a data file first.",
    "โปรดเปิดไฟล์ข้อมูลก่อน": "Open a data file first.",
    "เปิดไฟล์": "Open file",
    "เลือกไฟล์ข้อมูล": "Select data file",
    "ลากไฟล์มาวาง หรือเปิดไฟล์": "Drag files here or open a file",
    "เริ่มต้นวิเคราะห์ข้อมูลของคุณได้เลย": "Start analyzing your data",
    "ไฟล์ล่าสุด": "Recent Files",
    "ยังไม่มีไฟล์ล่าสุด": "No recent files",
    "บันทึก": "Saved",
    "บันทึกรายงาน": "Save report",
    "รายงาน": "report",
    "สำเร็จ": "Success",
    "ไม่สำเร็จ": "failed",
    "สาเหตุ": "Reason",
    "ข้อผิดพลาด": "Error",
    "ข้อมูล": "data",
    "เลือกคอลัมน์": "Select column",
    "ค้นหาคอลัมน์": "Search columns",
    "ชื่อคอลัมน์ใหม่": "New column name",
    "พิมพ์สูตรที่นี่": "Type formula here",
    "คอลัมน์": "column",
    "คอลัมน์เวลา": "Time column",
    "คอลัมน์สัญญาณ": "Signal column",
    "แถว": "rows",
    "ตาราง": "worksheet",
    "กราฟ": "graph",
    "เลือกทั้งหมด": "Select All",
    "ไม่เลือกเลย": "Select None",
    "ตกลง": "OK",
    "ยกเลิก": "Cancel",
    "เลือก": "Select",
    "เลือกแท็บที่ต้องการพล็อต": "Select tabs to plot",
    "โหมดการวิเคราะห์": "Analysis mode",
    "โหมด": "Mode",
    "พารามิเตอร์ STFT": "STFT Parameters",
    "พารามิเตอร์ CWT": "CWT Parameters",
    "พารามิเตอร์": "Parameters",
    "ตัวเลือกการแสดงผล": "Display options",
    "แปลงเป็น Decibels (dB)": "Convert to decibels (dB)",
    "การตั้งค่าหน่วยและการสอบเทียบ": "Units and Calibration",
    "รายละเอียดคอลัมน์": "Column Details",
    "สูตร": "Formula",
    "เดิม": "Raw",
    "ใหม่": "Converted",
    "รันซ้ำล่าสุด": "Run Latest Again",
    "ถาม AI หรือสั่งงานด้วยภาษาไทย...": "Ask AI or type a command...",
    "ส่ง": "Send",
    "คุณ": "You",
    "พิมพ์เพื่อค้นหาคำสั่ง...": "Type to search commands...",
    "ฟีเจอร์เสริม": "Extra Features",
    "การจัดรูปแบบข้อมูล": "Data Formatting",
    "คำนวณ": "Calculated",
    "ประวัติการวิเคราะห์": "Analysis history",
    "ยังไม่มีประวัติ": "No history",
    "ล้างประวัติการวิเคราะห์แล้ว": "Analysis history cleared.",
    "สร้างสคริปต์แล้ว": "Python script generated",
    "เกิดข้อผิดพลาด": "Error",
}

_PHRASES.update({
    "\u0e44\u0e21\u0e48\u0e21\u0e35\u0e41\u0e17\u0e47\u0e1a\u0e17\u0e35\u0e48\u0e40\u0e1b\u0e34\u0e14\u0e2d\u0e22\u0e39\u0e48": "No open tabs",
    "\u0e44\u0e21\u0e48\u0e21\u0e35\u0e41\u0e17\u0e47\u0e1a": "No tab",
    "\u0e27\u0e48\u0e32\u0e07": "empty",
    "\u0e44\u0e21\u0e48\u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16\u0e41\u0e1b\u0e25\u0e07\u0e40\u0e1b\u0e47\u0e19\u0e15\u0e31\u0e27\u0e40\u0e25\u0e02\u0e2b\u0e23\u0e37\u0e2d\u0e40\u0e27\u0e25\u0e32\u0e44\u0e14\u0e49": "cannot be converted to numeric or datetime data",
    "\u0e44\u0e21\u0e48\u0e40\u0e17\u0e48\u0e32\u0e01\u0e31\u0e19": "do not match",
    "\u0e15\u0e49\u0e2d\u0e07\u0e21\u0e35\u0e2d\u0e22\u0e48\u0e32\u0e07\u0e19\u0e49\u0e2d\u0e22 10 \u0e08\u0e38\u0e14": "at least 10 points are required",
    "\u0e44\u0e21\u0e48\u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19\u0e44\u0e14\u0e49": "Not available",
    "\u0e43\u0e2a\u0e48 window": "Apply window",
    "\u0e41\u0e25\u0e49\u0e27": "completed",
})

_PUNCT = {
    "\u2026": "...",
    "\u2192": "->",
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
    "\u00d7": "x",
    "\u2248": "~",
    "\u2022": "-",
}


def _repair_mojibake(text: str) -> str:
    """Best-effort repair for UTF-8 Thai text decoded as cp1252/latin-1."""
    if "à" not in text and "Ã" not in text and "â" not in text:
        return text
    candidates = [text]
    for encoding in ("cp1252", "latin1"):
        try:
            candidates.append(text.encode(encoding).decode("utf-8"))
        except Exception:
            pass
    # Prefer a repaired candidate that has Thai and fewer mojibake markers.
    return min(
        candidates,
        key=lambda s: (
            0 if _THAI_RE.search(s) else 1,
            len(_MOJIBAKE_RE.findall(s)),
            len(s),
        ),
    )


def _normalize_punctuation(text: str) -> str:
    for old, new in _PUNCT.items():
        text = text.replace(old, new)
    return text


def contains_non_english_ui(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    fixed = _repair_mojibake(text)
    return bool(_THAI_RE.search(fixed) or _MOJIBAKE_RE.search(text))


def to_english(text: Any, fallback: str | None = None) -> Any:
    """Return an English UI string when legacy Thai/mojibake is detected.

    User-controlled data can appear inside a message, so this function first
    preserves all readable ASCII tokens instead of blindly returning a generic
    fallback.
    """
    if not isinstance(text, str):
        return text
    fixed = _normalize_punctuation(_repair_mojibake(text))
    for thai, english in sorted(_PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
        fixed = fixed.replace(thai, english)
    fixed = _normalize_punctuation(fixed)
    if not (_THAI_RE.search(fixed) or _MOJIBAKE_RE.search(fixed)):
        return fixed

    ascii_chunks = [chunk.strip() for chunk in _ASCII_RE.findall(fixed) if chunk.strip()]
    cleaned = " ".join(ascii_chunks).strip()
    if cleaned and any(ch.isalpha() for ch in cleaned):
        return cleaned
    return fallback if fallback is not None else "Message"


def sanitize_form_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize labels/help text in form specs without touching data options."""
    clean = deepcopy(fields)
    for field in clean:
        if "label" in field:
            field["label"] = to_english(field["label"], fallback="Field")
        if "placeholder" in field:
            field["placeholder"] = to_english(field["placeholder"], fallback="")
        if "help" in field:
            field["help"] = to_english(field["help"], fallback="")
    return clean
