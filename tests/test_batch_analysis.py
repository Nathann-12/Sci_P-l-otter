from __future__ import annotations

import json

import pandas as pd
import pytest

from analysis.batch import (
    BatchAnalysisError,
    dataframe_checksum,
    export_batch_report,
    load_scientific_dataframe,
    run_batch_analysis,
)


def _write_csv(path, values):
    pd.DataFrame({"x": range(len(values)), "y": values}).to_csv(path, index=False)


def test_batch_runs_real_files_and_collects_auditable_metrics(tmp_path):
    one = tmp_path / "one.csv"
    two = tmp_path / "two.csv"
    _write_csv(one, [1.0, 2.0, 3.0])
    _write_csv(two, [4.0, 6.0])

    seen = []

    def analyze(frame, context):
        seen.append((context.index, context.source_checksum))
        return {"mean_y": frame["y"].mean(), "n": len(frame)}

    result = run_batch_analysis(
        [one, two], loader=pd.read_csv, analyzer=analyze, recipe_name="Mean Y"
    )

    assert result.success_count == 2
    assert result.failure_count == 0
    assert result.recipe_name == "Mean Y"
    assert [i.metrics["mean_y"] for i in result.items] == [2.0, 5.0]
    assert all(checksum.startswith("sha256:") for _, checksum in seen)
    assert result.summary_frame()["input_rows"].tolist() == [3, 2]


def test_batch_isolates_bad_inputs_and_can_fail_fast(tmp_path):
    good = tmp_path / "good.csv"
    bad = tmp_path / "bad.csv"
    later = tmp_path / "later.csv"
    _write_csv(good, [1])
    bad.write_text("not,y\na,b\n", encoding="utf-8")
    _write_csv(later, [3])

    def analyze(frame, _context):
        return {"total": pd.to_numeric(frame["y"]).sum()}

    result = run_batch_analysis(
        [good, bad, later], loader=pd.read_csv, analyzer=analyze
    )
    assert [item.status for item in result.items] == ["success", "failed", "success"]
    assert result.items[1].error_type
    assert result.failure_count == 1

    stopped = run_batch_analysis(
        [bad, later], loader=pd.read_csv, analyzer=analyze, fail_fast=True
    )
    assert len(stopped.items) == 1
    assert stopped.failure_count == 1


def test_cancellation_marks_remaining_sources_skipped(tmp_path):
    paths = [tmp_path / f"{i}.csv" for i in range(3)]
    for i, path in enumerate(paths):
        _write_csv(path, [i])
    calls = {"n": 0}

    def cancelled():
        calls["n"] += 1
        return calls["n"] > 1

    result = run_batch_analysis(
        paths, loader=pd.read_csv, analyzer=lambda df, ctx: {"n": len(df)},
        is_cancelled=cancelled,
    )
    assert result.cancelled is True
    assert [item.status for item in result.items] == ["success", "skipped", "skipped"]


@pytest.mark.parametrize("suffix", [".csv", ".json", ".xlsx", ".html"])
def test_export_batch_report_formats_are_readable_and_atomic(tmp_path, suffix):
    source = tmp_path / "source.csv"
    _write_csv(source, [1, 2])
    result = run_batch_analysis(
        [source], loader=pd.read_csv,
        analyzer=lambda frame, ctx: pd.DataFrame({"mean": [frame.y.mean()]}),
        recipe_name="Summary",
    )
    destination = tmp_path / f"report{suffix}"
    assert export_batch_report(result, destination) == destination
    assert destination.exists() and destination.stat().st_size > 0
    if suffix == ".json":
        payload = json.loads(destination.read_text(encoding="utf-8"))
        assert payload["success_count"] == 1
    elif suffix == ".xlsx":
        with pd.ExcelFile(destination) as workbook:
            assert "Batch Summary" in workbook.sheet_names


def test_dataframe_checksum_changes_with_values_schema_and_index():
    base = pd.DataFrame({"x": [1, 2]})
    assert dataframe_checksum(base) == dataframe_checksum(base.copy())
    assert dataframe_checksum(base) != dataframe_checksum(pd.DataFrame({"x": [1, 3]}))
    assert dataframe_checksum(base) != dataframe_checksum(pd.DataFrame({"z": [1, 2]}))
    assert dataframe_checksum(base) != dataframe_checksum(base.set_index(pd.Index([5, 6])))


def test_batch_rejects_empty_source_list():
    with pytest.raises(BatchAnalysisError, match="at least one"):
        run_batch_analysis([], loader=pd.read_csv, analyzer=lambda *_: None)


def test_headless_batch_loader_reads_supported_tabular_file(tmp_path):
    source = tmp_path / "source.csv"
    _write_csv(source, [1, 2])
    assert load_scientific_dataframe(source)["y"].tolist() == [1, 2]


def test_batch_extracts_headline_metrics_from_sciplotter_report_table(tmp_path):
    source = tmp_path / "source.csv"
    _write_csv(source, [1, 2, 3])
    result = run_batch_analysis(
        [source], loader=pd.read_csv,
        analyzer=lambda *_: pd.DataFrame({
            "section": ["Test", "Test"],
            "metric": ["statistic", "p_value"],
            "value": [2.5, 0.03],
        }),
    )
    assert result.items[0].metrics == {"statistic": 2.5, "p_value": 0.03}
    assert result.summary_frame().loc[0, "metric.p_value"] == 0.03
