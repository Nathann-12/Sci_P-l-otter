"""Behavioral tests for core.history (ROADMAP section F — reproducibility)."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("scipy")

from analysis.cleaning import fill_missing, normalize_column, remove_outliers
from analysis.signal_filters import butterworth_filter
from core.history import (
    AnalysisHistory,
    dataframe_checksum,
    generate_python_script,
    replay,
    version_stamp,
)


def _sample_df():
    fs = 100.0
    t = np.arange(0, 5, 1 / fs)
    y = np.sin(2 * np.pi * 2 * t) + np.sin(2 * np.pi * 20 * t)
    y[10] = np.nan
    return pd.DataFrame({"t": t, "y": y})


def _sample_history():
    h = AnalysisHistory()
    h.record("fill_missing", col="y", method="mean")
    h.record("butterworth_filter", col="y_filled", fs=100.0,
             kind="lowpass", cutoff=5.0, order=4, new_col="y_lp")
    h.record("normalize_column", col="y_lp", method="minmax")
    return h


def test_record_and_json_roundtrip():
    h = _sample_history()
    assert len(h) == 3
    text = h.to_json(source_path="data.csv", checksum="abc123")
    restored = AnalysisHistory.from_json(text)
    assert [e["op"] for e in restored.entries] == [e["op"] for e in h.entries]
    assert restored.entries[1]["params"]["cutoff"] == 5.0
    # version stamp present in the workflow file
    import json
    payload = json.loads(text)
    assert payload["stamp"]["app"] == "SciPlotter"
    assert payload["stamp"]["pandas"] == pd.__version__
    assert payload["source_checksum"] == "abc123"


def test_from_json_rejects_bad_payload():
    with pytest.raises(ValueError):
        AnalysisHistory.from_json('{"no_ops": true}')


def test_replay_reproduces_manual_pipeline():
    df = _sample_df()
    result = replay(_sample_history(), df)

    expected = _sample_df()
    fill_missing(expected, "y", method="mean")
    expected["y_lp"] = butterworth_filter(expected["y_filled"], 100.0,
                                          kind="lowpass", cutoff=5.0, order=4)
    normalize_column(expected, "y_lp", method="minmax")

    assert list(result.columns) == list(expected.columns)
    assert np.allclose(result["y_lp_minmax"], expected["y_lp_minmax"])
    # replay never mutates the input frame
    assert "y_filled" not in df.columns


def test_replay_row_ops_and_strict_mode():
    df = pd.DataFrame({"v": [1.0] * 10 + [999.0]})
    h = AnalysisHistory()
    h.record("remove_outliers", col="v", method="zscore", threshold=3.0)
    out = replay(h, df)
    expected = remove_outliers(df, "v", method="zscore", threshold=3.0)[0]
    assert out["v"].tolist() == expected["v"].tolist()

    h.record("mystery_op", foo=1)
    with pytest.raises(ValueError):
        replay(h, df)
    assert len(replay(h, df, strict=False)) == 10  # skips unknown op


def test_checksum_stable_and_sensitive():
    df = _sample_df()
    a = dataframe_checksum(df)
    assert a == dataframe_checksum(df.copy())
    changed = df.copy()
    changed.iloc[0, 1] = 12345.0
    assert dataframe_checksum(changed) != a


def test_generated_script_executes_and_matches_replay(tmp_path):
    """The strongest guarantee: exec the generated script's apply_workflow()
    and require the same result as replay()."""
    h = _sample_history()
    script = generate_python_script(h, source_path="data.csv")
    assert "def apply_workflow(df):" in script
    assert "cleaning.fill_missing" in script
    assert "signal_filters.butterworth_filter" in script
    assert version_stamp()["pandas"] in script

    namespace: dict = {"__name__": "workflow_test"}
    exec(compile(script, "generated_workflow.py", "exec"), namespace)
    result = namespace["apply_workflow"](_sample_df().copy())

    expected = replay(h, _sample_df())
    assert list(result.columns) == list(expected.columns)
    assert np.allclose(result["y_lp_minmax"], expected["y_lp_minmax"])


def test_generated_script_handles_empty_history_and_unknown_ops():
    h = AnalysisHistory()
    script = generate_python_script(h)
    assert "pass" in script
    h.record("mystery_op", foo=1)
    script2 = generate_python_script(h)
    assert "Skipped unknown operation" in script2
