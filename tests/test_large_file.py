import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from file_io import _read_csv_chunked
from loaders import _read_csv_chunked_simple, load_tabular


def _write_sequence_csv(path: Path, rows: int = 7) -> pd.DataFrame:
    expected = pd.DataFrame({
        "row_id": list(range(rows)),
        "value": [f"value-{idx}" for idx in range(rows)],
    })
    expected.to_csv(path, index=False)
    return expected


def _assert_sequence_frame(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    actual = actual.reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, expected)
    assert actual["row_id"].tolist() == list(range(len(expected)))


def test_file_io_chunked_reader_does_not_repeat_first_chunk(tmp_path):
    csv_path = tmp_path / "chunked.csv"
    expected = _write_sequence_csv(csv_path, rows=7)

    actual = _read_csv_chunked(csv_path, sep=",", encoding="utf-8", chunk_size=3)

    _assert_sequence_frame(actual, expected)


def test_loaders_chunked_reader_does_not_repeat_first_chunk(tmp_path):
    csv_path = tmp_path / "chunked.csv"
    expected = _write_sequence_csv(csv_path, rows=7)

    actual = _read_csv_chunked_simple(str(csv_path), sep=",", encoding="utf-8", chunk_size=3)

    _assert_sequence_frame(actual, expected)


def test_load_tabular_large_csv_path_uses_chunked_reader_without_duplicate_rows(tmp_path, monkeypatch):
    csv_path = tmp_path / "large.csv"
    expected = _write_sequence_csv(csv_path, rows=7)
    monkeypatch.setattr("loaders.os.path.getsize", lambda _: 101 * 1024 * 1024)

    actual, note = load_tabular(csv_path)

    _assert_sequence_frame(actual, expected)
    assert "csv" in note
