"""Reusable, auditable batch-analysis pipeline.

The GUI deliberately stays outside this module.  A batch job receives a
loader and an analyzer, which makes the same implementation usable from the
desktop UI, tests, scripts, and (later) the local AI tool layer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


SCHEMA_VERSION = 1


class BatchAnalysisError(RuntimeError):
    """Raised for invalid batch configuration or report output."""


@dataclass(frozen=True)
class BatchContext:
    """Read-only metadata passed to the analyzer for every input."""

    index: int
    total: int
    source: str
    source_name: str
    source_checksum: str


@dataclass
class BatchItemResult:
    source: str
    source_checksum: str
    status: str
    started_at: str
    duration_seconds: float
    input_rows: int = 0
    input_columns: int = 0
    output_rows: int = 0
    output_columns: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    error_message: str = ""
    output: Any = field(default=None, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def to_record(self) -> dict[str, Any]:
        record = {
            "source": self.source,
            "source_checksum": self.source_checksum,
            "status": self.status,
            "started_at": self.started_at,
            "duration_seconds": round(float(self.duration_seconds), 6),
            "input_rows": int(self.input_rows),
            "input_columns": int(self.input_columns),
            "output_rows": int(self.output_rows),
            "output_columns": int(self.output_columns),
            "error_type": self.error_type,
            "error_message": self.error_message,
        }
        for key, value in sorted(self.metrics.items()):
            record[f"metric.{key}"] = _json_safe(value)
        return record


@dataclass
class BatchRunResult:
    started_at: str
    finished_at: str
    recipe_name: str
    recipe_version: int
    items: list[BatchItemResult]
    cancelled: bool = False
    schema_version: int = SCHEMA_VERSION

    @property
    def success_count(self) -> int:
        return sum(item.ok for item in self.items)

    @property
    def failure_count(self) -> int:
        return sum(item.status == "failed" for item in self.items)

    @property
    def skipped_count(self) -> int:
        return sum(item.status == "skipped" for item in self.items)

    def summary_frame(self) -> pd.DataFrame:
        return pd.DataFrame.from_records([item.to_record() for item in self.items])

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "recipe_name": self.recipe_name,
            "recipe_version": self.recipe_version,
            "cancelled": self.cancelled,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "skipped_count": self.skipped_count,
            "items": [item.to_record() for item in self.items],
        }


def run_batch_analysis(
    sources: Iterable[str | Path],
    *,
    loader: Callable[[str], pd.DataFrame],
    analyzer: Callable[[pd.DataFrame, BatchContext], Any],
    recipe_name: str = "Analysis Recipe",
    recipe_version: int = 1,
    is_cancelled: Optional[Callable[[], bool]] = None,
    progress: Optional[Callable[[int, int, Optional[BatchItemResult]], None]] = None,
    fail_fast: bool = False,
) -> BatchRunResult:
    """Run ``analyzer`` once per source and retain failures in the report.

    ``analyzer`` may return a DataFrame, mapping, dataclass, scalar, or an
    object exposing ``to_dict``.  Scalar mapping fields become summary
    metrics; rich results remain available as ``BatchItemResult.output``.
    Cancellation is cooperative and checked before loading every file.
    """

    paths = [str(Path(source)) for source in sources]
    if not paths:
        raise BatchAnalysisError("Select at least one input file.")
    if not callable(loader) or not callable(analyzer):
        raise BatchAnalysisError("loader and analyzer must be callable.")
    if int(recipe_version) < 1:
        raise BatchAnalysisError("recipe_version must be at least 1.")

    started = _utc_now()
    results: list[BatchItemResult] = []
    cancelled = False
    total = len(paths)
    if progress:
        progress(0, total, None)

    for index, source in enumerate(paths):
        if is_cancelled and is_cancelled():
            cancelled = True
            break

        tick = time.perf_counter()
        item_started = _utc_now()
        checksum = ""
        in_rows = in_cols = 0
        try:
            checksum = file_checksum(source)
            frame = loader(source)
            if not isinstance(frame, pd.DataFrame):
                raise TypeError("The loader must return a pandas DataFrame.")
            in_rows, in_cols = frame.shape
            context = BatchContext(
                index=index,
                total=total,
                source=source,
                source_name=Path(source).name,
                source_checksum=checksum,
            )
            output = analyzer(frame.copy(deep=False), context)
            out_rows, out_cols = _output_shape(output)
            item = BatchItemResult(
                source=source,
                source_checksum=checksum,
                status="success",
                started_at=item_started,
                duration_seconds=time.perf_counter() - tick,
                input_rows=in_rows,
                input_columns=in_cols,
                output_rows=out_rows,
                output_columns=out_cols,
                metrics=_extract_metrics(output),
                output=output,
            )
        except Exception as exc:  # a failed input must not discard the batch
            item = BatchItemResult(
                source=source,
                source_checksum=checksum,
                status="failed",
                started_at=item_started,
                duration_seconds=time.perf_counter() - tick,
                input_rows=in_rows,
                input_columns=in_cols,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            results.append(item)
            if progress:
                progress(index + 1, total, item)
            if fail_fast:
                break
            continue

        results.append(item)
        if progress:
            progress(index + 1, total, item)

    if cancelled:
        for source in paths[len(results):]:
            results.append(BatchItemResult(
                source=source,
                source_checksum="",
                status="skipped",
                started_at=_utc_now(),
                duration_seconds=0.0,
                error_message="Cancelled before processing.",
            ))

    return BatchRunResult(
        started_at=started,
        finished_at=_utc_now(),
        recipe_name=str(recipe_name).strip() or "Analysis Recipe",
        recipe_version=int(recipe_version),
        items=results,
        cancelled=cancelled,
    )


def load_scientific_dataframe(path: str | Path) -> pd.DataFrame:
    """Load every tabular format supported by SciPlotter without opening UI.

    Batch workers must never invoke a CDF variable-selection dialog from their
    background thread, so NetCDF/CDF explicitly use the loader's automatic
    path (``parent=None``).
    """
    from loaders import (
        load_cdf_nc_on_demand, load_hdf5, load_json, load_mat, load_tabular, load_xml,
    )

    source = str(path)
    suffix = Path(source).suffix.lower()
    if suffix in {".csv", ".txt", ".tsv", ".xlsx"}:
        frame, _note = load_tabular(source, suffix)
    elif suffix in {".nc", ".cdf"}:
        frame = load_cdf_nc_on_demand(None, source)
    elif suffix == ".json":
        frame, _note = load_json(source)
    elif suffix in {".h5", ".hdf5", ".hdf"}:
        frame, _note = load_hdf5(source)
    elif suffix == ".mat":
        frame, _note = load_mat(source)
    elif suffix == ".xml":
        frame, _note = load_xml(source)
    else:
        raise BatchAnalysisError(f"Unsupported input format: {suffix or '(none)'}")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise BatchAnalysisError(f"Input has no tabular data: {Path(source).name}")
    return frame


def export_batch_report(result: BatchRunResult, destination: str | Path) -> Path:
    """Atomically export a CSV, JSON, XLSX, or self-contained HTML report."""

    path = Path(destination)
    suffix = path.suffix.lower()
    if suffix not in {".csv", ".json", ".xlsx", ".html", ".htm"}:
        raise BatchAnalysisError("Report format must be CSV, JSON, XLSX, or HTML.")
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=f".{path.stem}.", suffix=suffix, dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        frame = result.summary_frame()
        if suffix == ".csv":
            frame.to_csv(temporary, index=False)
        elif suffix == ".json":
            temporary.write_text(
                json.dumps(result.manifest(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        elif suffix in {".html", ".htm"}:
            temporary.write_text(_html_report(result), encoding="utf-8")
        else:
            _write_excel_report(result, temporary)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def file_checksum(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def dataframe_checksum(frame: pd.DataFrame) -> str:
    """Stable checksum including values, index, column labels, and dtypes."""

    digest = hashlib.sha256()
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    digest.update(json.dumps([str(c) for c in frame.columns]).encode("utf-8"))
    digest.update(json.dumps([str(t) for t in frame.dtypes]).encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _output_shape(value: Any) -> tuple[int, int]:
    if isinstance(value, pd.DataFrame):
        return value.shape
    if isinstance(value, pd.Series):
        return len(value), 1
    if isinstance(value, Mapping):
        return 1, len(value)
    return (1, 1) if value is not None else (0, 0)


def _extract_metrics(value: Any) -> dict[str, Any]:
    if isinstance(value, pd.DataFrame):
        metrics: dict[str, Any] = {}
        # SciPlotter report tables use metric/value or term/value. Preserve
        # scalar headline metrics without serialising large residual tables.
        label_column = "metric" if "metric" in value.columns else (
            "term" if "term" in value.columns else None
        )
        if label_column and "value" in value.columns:
            for _, row in value.iterrows():
                label = row.get(label_column)
                metric = row.get("value")
                if pd.notna(label) and _is_scalar(metric) and pd.notna(metric):
                    key = str(label)
                    if key in metrics and "section" in value.columns:
                        key = f"{row.get('section', '')}.{key}".strip(".")
                    metrics[key] = _json_safe(metric)
        elif len(value) == 1:
            for key, metric in value.iloc[0].items():
                if _is_scalar(metric) and pd.notna(metric):
                    metrics[str(key)] = _json_safe(metric)
        return metrics
    if is_dataclass(value):
        value = asdict(value)
    elif hasattr(value, "to_dict") and not isinstance(value, (pd.DataFrame, pd.Series)):
        try:
            value = value.to_dict()
        except Exception:
            pass
    if isinstance(value, pd.Series):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        return {"value": _json_safe(value)} if _is_scalar(value) else {}
    metrics: dict[str, Any] = {}
    for key, item in value.items():
        if _is_scalar(item):
            metrics[str(key)] = _json_safe(item)
    return metrics


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float, np.generic))


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _safe_sheet_name(name: str, used: set[str]) -> str:
    clean = re.sub(r"[\\/*?:\[\]]", "_", name).strip(" '") or "Result"
    clean = clean[:31]
    candidate = clean
    counter = 2
    while candidate.lower() in used:
        tail = f" {counter}"
        candidate = f"{clean[:31-len(tail)]}{tail}"
        counter += 1
    used.add(candidate.lower())
    return candidate


def _write_excel_report(result: BatchRunResult, path: Path) -> None:
    used: set[str] = set()
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        result.summary_frame().to_excel(
            writer, sheet_name=_safe_sheet_name("Batch Summary", used), index=False
        )
        for index, item in enumerate(result.items, start=1):
            if not item.ok:
                continue
            output = item.output
            if isinstance(output, pd.Series):
                output = output.to_frame()
            elif isinstance(output, Mapping):
                output = pd.DataFrame([dict(output)])
            elif is_dataclass(output):
                output = pd.DataFrame([asdict(output)])
            if not isinstance(output, pd.DataFrame):
                continue
            label = f"{index:03d} {Path(item.source).stem}"
            output.to_excel(writer, sheet_name=_safe_sheet_name(label, used), index=False)


def _html_report(result: BatchRunResult) -> str:
    title = "SciPlotter Batch Analysis Report"
    summary = result.summary_frame().to_html(index=False, border=0, classes="summary")
    recipe_name = escape(result.recipe_name, quote=True)
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>{title}</title>
<style>body{{font:14px system-ui;margin:32px;color:#20242a}}table{{border-collapse:collapse}}
th,td{{padding:7px 10px;border:1px solid #ccd2d8;text-align:left}}th{{background:#eef2f5}}
.cards{{display:flex;gap:16px;margin:16px 0}}.card{{padding:12px 18px;background:#f4f6f8;border-radius:8px}}</style>
</head><body><h1>{title}</h1><p>Recipe: <strong>{recipe_name}</strong> (v{result.recipe_version})</p>
<div class=\"cards\"><div class=\"card\">Success: {result.success_count}</div>
<div class=\"card\">Failed: {result.failure_count}</div><div class=\"card\">Skipped: {result.skipped_count}</div></div>
{summary}</body></html>"""


__all__ = [
    "BatchAnalysisError",
    "BatchContext",
    "BatchItemResult",
    "BatchRunResult",
    "dataframe_checksum",
    "export_batch_report",
    "file_checksum",
    "load_scientific_dataframe",
    "run_batch_analysis",
]
