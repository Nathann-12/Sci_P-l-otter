"""Reproducibility core (ROADMAP section F).

Pure logic, no Qt:

- :class:`AnalysisHistory` — ordered record of data operations + parameters
  with a version stamp, JSON export/import (the "workflow" file)
- :func:`replay` — re-run a recorded workflow against any DataFrame
- :func:`generate_python_script` — emit a standalone Python script that
  reproduces the workflow (imports the same analysis functions this app uses)
- :func:`dataframe_checksum` — stable content hash for audit purposes
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

WORKFLOW_FORMAT = 1


# --------------------------------------------------------------------- stamp
def version_stamp() -> Dict[str, str]:
    """Environment stamp embedded in every workflow (reproducibility!)."""
    import numpy

    return {
        "app": "SciPlotter",
        "workflow_format": str(WORKFLOW_FORMAT),
        "python": sys.version.split()[0],
        "pandas": pd.__version__,
        "numpy": numpy.__version__,
    }


def dataframe_checksum(df: pd.DataFrame) -> str:
    """Stable sha256 of the DataFrame contents (column order matters)."""
    hasher = hashlib.sha256()
    hasher.update("|".join(str(c) for c in df.columns).encode("utf-8"))
    hasher.update(pd.util.hash_pandas_object(df, index=False).values.tobytes())
    return hasher.hexdigest()


# ------------------------------------------------------------------- history
class AnalysisHistory:
    """Ordered log of operations: what ran, with which parameters, when."""

    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []

    def record(self, op: str, **params: Any) -> Dict[str, Any]:
        entry = {"op": op, "params": params, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.entries.append(entry)
        return entry

    def clear(self) -> None:
        self.entries.clear()

    def __len__(self) -> int:
        return len(self.entries)

    # ---- workflow (de)serialisation ----
    def to_json(self, source_path: Optional[str] = None,
                checksum: Optional[str] = None) -> str:
        payload = {
            "stamp": version_stamp(),
            "source_path": source_path,
            "source_checksum": checksum,
            "operations": self.entries,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "AnalysisHistory":
        data = json.loads(text)
        ops = data.get("operations")
        if not isinstance(ops, list):
            raise ValueError("ไฟล์ workflow ไม่มีรายการ operations")
        history = cls()
        for entry in ops:
            if not isinstance(entry, dict) or "op" not in entry:
                raise ValueError(f"รายการ workflow ไม่ถูกต้อง: {entry!r}")
            history.entries.append({
                "op": str(entry["op"]),
                "params": dict(entry.get("params") or {}),
                "time": entry.get("time", ""),
            })
        return history


# -------------------------------------------------------------------- replay
def _band(p: Dict[str, Any]):
    """cutoff may round-trip through JSON as a list — normalise band pairs."""
    cutoff = p["cutoff"]
    return tuple(cutoff) if isinstance(cutoff, (list, tuple)) else float(cutoff)


def _replay_fill(df, p):
    from analysis.cleaning import fill_missing
    fill_missing(df, p["col"], method=p.get("method", "mean"), value=p.get("value"))
    return df


def _replay_interpolate(df, p):
    from analysis.cleaning import interpolate_missing
    interpolate_missing(df, p["col"])
    return df


def _replay_dedupe(df, p):
    from analysis.cleaning import remove_duplicates
    return remove_duplicates(df)[0]


def _replay_outliers(df, p):
    from analysis.cleaning import remove_outliers
    return remove_outliers(df, p["col"], method=p.get("method", "zscore"),
                           threshold=p.get("threshold"))[0]


def _replay_normalize(df, p):
    from analysis.cleaning import normalize_column
    normalize_column(df, p["col"], method=p.get("method", "zscore"))
    return df


def _replay_detrend(df, p):
    from analysis.cleaning import detrend_polynomial
    detrend_polynomial(df, p["col"], order=int(p.get("order", 1)), x_col=p.get("x_col"))
    return df


def _replay_sort(df, p):
    from analysis.cleaning import sort_dataframe
    return sort_dataframe(df, p["col"], ascending=bool(p.get("ascending", True)))


def _replay_resample(df, p):
    from analysis.cleaning import resample_uniform
    return resample_uniform(df, p["x_col"], n_points=p.get("n_points"))


def _replay_butterworth(df, p):
    from analysis.signal_filters import butterworth_filter
    new_col = p.get("new_col") or f"{p['col']}_{p.get('kind', 'lowpass')}"
    df[new_col] = butterworth_filter(
        df[p["col"]], float(p["fs"]), kind=p.get("kind", "lowpass"),
        cutoff=_band(p), order=int(p.get("order", 4)))
    return df


def _replay_savgol(df, p):
    from analysis.signal_filters import savitzky_golay
    new_col = p.get("new_col") or f"{p['col']}_savgol"
    df[new_col] = savitzky_golay(df[p["col"]], window_length=int(p.get("window", 11)))
    return df


def _replay_median(df, p):
    from analysis.signal_filters import median_filter
    new_col = p.get("new_col") or f"{p['col']}_median"
    df[new_col] = median_filter(df[p["col"]], kernel_size=int(p.get("kernel", 5)))
    return df


def _replay_gaussian(df, p):
    from analysis.signal_filters import gaussian_smooth
    new_col = p.get("new_col") or f"{p['col']}_gauss"
    df[new_col] = gaussian_smooth(df[p["col"]], sigma=float(p.get("sigma", 2.0)))
    return df


def _replay_window(df, p):
    from analysis.signal_filters import apply_window
    window = p.get("window", "hann")
    new_col = p.get("new_col") or f"{p['col']}_{window}"
    df[new_col] = apply_window(df[p["col"]], window=window, beta=float(p.get("beta", 14.0)))
    return df


def _replay_moving_average(df, p):
    from processors import add_moving_average
    add_moving_average(df, p["col"], window=int(p.get("window", 25)))
    return df


REPLAY_REGISTRY: Dict[str, Callable[[pd.DataFrame, Dict[str, Any]], pd.DataFrame]] = {
    "fill_missing": _replay_fill,
    "interpolate_missing": _replay_interpolate,
    "remove_duplicates": _replay_dedupe,
    "remove_outliers": _replay_outliers,
    "normalize_column": _replay_normalize,
    "detrend_polynomial": _replay_detrend,
    "sort_dataframe": _replay_sort,
    "resample_uniform": _replay_resample,
    "butterworth_filter": _replay_butterworth,
    "savitzky_golay": _replay_savgol,
    "median_filter": _replay_median,
    "gaussian_smooth": _replay_gaussian,
    "apply_window": _replay_window,
    "add_moving_average": _replay_moving_average,
}


def replay(history: AnalysisHistory, df: pd.DataFrame,
           strict: bool = True) -> pd.DataFrame:
    """Re-run every recorded operation on a copy of ``df``.

    ``strict=False`` skips unknown operations instead of raising.
    Returns the transformed DataFrame.
    """
    out = df.copy()
    for entry in history.entries:
        op = entry["op"]
        fn = REPLAY_REGISTRY.get(op)
        if fn is None:
            if strict:
                raise ValueError(f"ไม่รู้จัก operation: {op!r} — re-run ไม่ได้")
            continue
        out = fn(out, entry.get("params") or {})
    return out


# ------------------------------------------------------------- script export
_SCRIPT_TEMPLATES: Dict[str, str] = {
    "fill_missing": "cleaning.fill_missing(df, {col!r}, method={method!r}, value={value!r})",
    "interpolate_missing": "cleaning.interpolate_missing(df, {col!r})",
    "remove_duplicates": "df, _removed = cleaning.remove_duplicates(df)",
    "remove_outliers": "df, _removed = cleaning.remove_outliers(df, {col!r}, method={method!r}, threshold={threshold!r})",
    "normalize_column": "cleaning.normalize_column(df, {col!r}, method={method!r})",
    "detrend_polynomial": "cleaning.detrend_polynomial(df, {col!r}, order={order!r}, x_col={x_col!r})",
    "sort_dataframe": "df = cleaning.sort_dataframe(df, {col!r}, ascending={ascending!r})",
    "resample_uniform": "df = cleaning.resample_uniform(df, {x_col!r}, n_points={n_points!r})",
    "butterworth_filter": "df[{new_col!r}] = signal_filters.butterworth_filter(df[{col!r}], {fs!r}, kind={kind!r}, cutoff={cutoff!r}, order={order!r})",
    "savitzky_golay": "df[{new_col!r}] = signal_filters.savitzky_golay(df[{col!r}], window_length={window!r})",
    "median_filter": "df[{new_col!r}] = signal_filters.median_filter(df[{col!r}], kernel_size={kernel!r})",
    "gaussian_smooth": "df[{new_col!r}] = signal_filters.gaussian_smooth(df[{col!r}], sigma={sigma!r})",
    "apply_window": "df[{new_col!r}] = signal_filters.apply_window(df[{col!r}], window={window!r}, beta={beta!r})",
    "add_moving_average": "processors.add_moving_average(df, {col!r}, window={window!r})",
}

# defaults merged under recorded params so templates never miss a key
_SCRIPT_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "fill_missing": {"method": "mean", "value": None},
    "remove_outliers": {"method": "zscore", "threshold": None},
    "normalize_column": {"method": "zscore"},
    "detrend_polynomial": {"order": 1, "x_col": None},
    "sort_dataframe": {"ascending": True},
    "resample_uniform": {"n_points": None},
    "butterworth_filter": {"kind": "lowpass", "order": 4},
    "savitzky_golay": {"window": 11},
    "median_filter": {"kernel": 5},
    "gaussian_smooth": {"sigma": 2.0},
    "apply_window": {"window": "hann", "beta": 14.0},
    "add_moving_average": {"window": 25},
}


def generate_python_script(history: AnalysisHistory,
                           source_path: Optional[str] = None) -> str:
    """Emit a standalone, runnable Python script reproducing the workflow.

    The script defines ``apply_workflow(df)`` (importable/testable) plus a
    ``__main__`` block that loads the source file and saves the result.
    """
    stamp = version_stamp()
    lines: List[str] = [
        '"""Auto-generated by SciPlotter — reproducible analysis workflow.',
        "",
        f"stamp: python {stamp['python']}, pandas {stamp['pandas']}, numpy {stamp['numpy']}",
        '"""',
        "import pandas as pd",
        "",
        "from analysis import cleaning, signal_filters",
        "import processors",
        "",
        "",
        "def apply_workflow(df):",
    ]
    body: List[str] = []
    for entry in history.entries:
        op = entry["op"]
        template = _SCRIPT_TEMPLATES.get(op)
        if template is None:
            body.append(f"# ข้าม operation ที่ไม่รู้จัก: {op}")
            continue
        params = dict(_SCRIPT_DEFAULTS.get(op, {}))
        params.update(entry.get("params") or {})
        if op in ("butterworth_filter", "savitzky_golay", "median_filter",
                  "gaussian_smooth", "apply_window") and not params.get("new_col"):
            suffix = {
                "butterworth_filter": params.get("kind", "lowpass"),
                "savitzky_golay": "savgol",
                "median_filter": "median",
                "gaussian_smooth": "gauss",
                "apply_window": params.get("window", "hann"),
            }[op]
            params["new_col"] = f"{params['col']}_{suffix}"
        if op == "butterworth_filter" and isinstance(params.get("cutoff"), list):
            params["cutoff"] = tuple(params["cutoff"])
        body.append(f"# {entry.get('time', '')} — {op}".rstrip(" —"))
        body.append(template.format(**params))
    if not body:
        body.append("pass  # ไม่มี operation ในประวัติ")
    lines.extend("    " + b for b in body)
    lines.extend([
        "    return df",
        "",
        "",
        'if __name__ == "__main__":',
        f"    df = pd.read_csv({source_path!r})" if source_path
        else "    df = pd.read_csv('input.csv')  # แก้ path ให้ตรงข้อมูลของคุณ",
        "    df = apply_workflow(df)",
        "    df.to_csv('workflow_output.csv', index=False)",
        "    print(df.head())",
        "",
    ])
    return "\n".join(lines)
