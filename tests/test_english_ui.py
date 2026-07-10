from __future__ import annotations

from core.english_ui import contains_non_english_ui, sanitize_form_fields, to_english


def test_to_english_repairs_legacy_thai_ui_text():
    text = to_english("ยังไม่มีข้อมูล - โปรดเปิดไฟล์ก่อน")

    assert text == "No data - Open a data file first."
    assert not contains_non_english_ui(text)


def test_to_english_repairs_mojibake_and_normalizes_punctuation():
    text = to_english("à¸¢à¸±à¸‡à¹„à¸¡à¹ˆà¸¡à¸µà¸‚à¹‰à¸­à¸¡à¸¹à¸¥ â†’ Book")

    assert "No data" in text
    assert "Book" in text
    assert "->" in text
    assert not contains_non_english_ui(text)


def test_sanitize_form_fields_does_not_touch_data_options():
    fields = [
        {
            "name": "col",
            "label": "เลือกคอลัมน์",
            "kind": "choice",
            "options": ["สัญญาณ", "time"],
            "default": "สัญญาณ",
        }
    ]

    clean = sanitize_form_fields(fields)

    assert clean[0]["label"] == "Select column"
    assert clean[0]["options"] == ["สัญญาณ", "time"]
    assert clean[0]["default"] == "สัญญาณ"
