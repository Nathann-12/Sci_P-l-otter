"""Behavioral tests for the new import formats (ROADMAP A):
JSON / HDF5 / MAT / XML loaders + Batch import through the real MainWindow."""
from __future__ import annotations

import os
import importlib
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

from loaders import load_hdf5, load_json, load_mat, load_xml


def _import_optional_h5py():
    try:
        return importlib.import_module("h5py")
    except Exception as exc:
        pytest.skip(f"h5py is installed but unavailable: {exc}")


# ---------------- JSON ----------------

def test_load_json_records(tmp_path):
    p = tmp_path / "records.json"
    p.write_text('[{"t": 0, "y": 1.5}, {"t": 1, "y": 2.5}]', encoding="utf-8")
    df, note = load_json(p)
    assert df["t"].tolist() == [0, 1]
    assert df["y"].tolist() == [1.5, 2.5]
    assert "records" in note


def test_load_json_dict_of_lists(tmp_path):
    p = tmp_path / "cols.json"
    p.write_text('{"t": [0, 1, 2], "y": [5, 6, 7]}', encoding="utf-8")
    df, note = load_json(p)
    assert list(df.columns) == ["t", "y"]
    assert len(df) == 3
    assert "columns" in note


def test_load_json_nested_records_are_flattened(tmp_path):
    p = tmp_path / "nested.json"
    p.write_text('[{"t": 0, "sensor": {"r": 10}}, {"t": 1, "sensor": {"r": 20}}]',
                 encoding="utf-8")
    df, _note = load_json(p)
    assert "sensor.r" in df.columns
    assert df["sensor.r"].tolist() == [10, 20]


def test_load_json_rejects_scalar(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('42', encoding="utf-8")
    with pytest.raises(ValueError):
        load_json(p)


# ---------------- MAT ----------------

def test_load_mat_roundtrip(tmp_path):
    from scipy.io import savemat
    p = tmp_path / "data.mat"
    savemat(str(p), {"t": np.arange(5.0), "y": np.arange(5.0) * 2,
                     "meta": "ignored-string"})
    df, note = load_mat(p)
    assert sorted(c for c in df.columns) == ["t", "y"]
    assert df["y"].tolist() == [0.0, 2.0, 4.0, 6.0, 8.0]
    assert "mat" in note


def test_load_mat_2d_fallback(tmp_path):
    from scipy.io import savemat
    p = tmp_path / "matrix.mat"
    savemat(str(p), {"M": np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])})
    df, note = load_mat(p)
    assert df.shape == (3, 2)
    assert "2D" in note


# ---------------- HDF5 ----------------

def test_load_hdf5_generic_1d_datasets(tmp_path):
    h5py = _import_optional_h5py()
    p = tmp_path / "data.h5"
    with h5py.File(str(p), "w") as f:
        f.create_dataset("t", data=np.arange(10.0))
        grp = f.create_group("signals")
        grp.create_dataset("y", data=np.arange(10.0) * 3)
        f.create_dataset("short", data=np.arange(3.0))  # ความยาวไม่เข้ากลุ่ม → ตัดทิ้ง
    df, note = load_hdf5(p)
    assert sorted(df.columns) == ["t", "y"]
    assert len(df) == 10
    assert df["y"].iloc[-1] == 27.0
    assert "hdf5" in note


def test_load_hdf5_rejects_empty(tmp_path):
    h5py = _import_optional_h5py()
    p = tmp_path / "empty.h5"
    with h5py.File(str(p), "w") as f:
        f.create_group("nothing")
    with pytest.raises(ValueError):
        load_hdf5(p)


# ---------------- XML ----------------

def test_load_xml_flat_rows(tmp_path):
    pytest.importorskip("lxml")
    p = tmp_path / "data.xml"
    p.write_text(
        "<data><row><t>0</t><y>1.5</y></row><row><t>1</t><y>2.5</y></row></data>",
        encoding="utf-8")
    df, note = load_xml(p)
    assert df["t"].tolist() == [0, 1]
    assert df["y"].tolist() == [1.5, 2.5]
    assert "xml" in note


# ---------------- ผ่าน MainWindow จริง (Book funnel + batch) ----------------

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    yield w
    w.close()


def test_load_data_json_opens_book(win, tmp_path):
    p = tmp_path / "drop.json"
    p.write_text('{"t": [0, 1, 2], "y": [7, 8, 9]}', encoding="utf-8")
    books_before = len(win.mdi._books)

    win.load_data(str(p))

    assert len(win.mdi._books) == books_before + 1
    assert win._df["y"].tolist() == [7, 8, 9]


def test_batch_import_opens_book_per_file(win, tmp_path, monkeypatch):
    a = tmp_path / "one.csv"
    a.write_text("t,y\n0,1\n1,2\n", encoding="utf-8")
    b = tmp_path / "two.json"
    b.write_text('{"t": [0, 1], "z": [5, 6]}', encoding="utf-8")

    import main_window_session_mixin as session_module
    monkeypatch.setattr(
        session_module.QFileDialog, "getOpenFileNames",
        staticmethod(lambda *args, **kwargs: ([str(a), str(b)], "Data Files")))

    books_before = len(win.mdi._books)
    win.stage_add_files()

    assert len(win.mdi._books) == books_before + 2
    # ไฟล์สุดท้ายที่เปิดกลายเป็น Book ที่ active → ข้อมูลพร้อมใช้
    assert "z" in win._df.columns
