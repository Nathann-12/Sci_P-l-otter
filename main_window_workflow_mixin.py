from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import pandas as pd

from core.history import (
    REPLAY_REGISTRY,
    AnalysisHistory,
    dataframe_checksum,
    generate_python_script,
    replay,
)

logger = logging.getLogger(__name__)


class MainWindowWorkflowMixin:
    """Reproducibility (ROADMAP F): analysis history → workflow file → re-run
    → auto-generated Python script.

    Data ops (features mixin) call :meth:`_record_op` after every successful
    transformation; this mixin owns the history object and the Tools-menu
    flows. All prompts go through the view seam so tests run headless.
    """

    # ------------------------------------------------------------------ setup
    def init_workflow_module(self):
        self.analysis_history = AnalysisHistory()
        menu = getattr(self, "toolsMenu", None)
        if menu is None:
            menu = self.menuBar().addMenu("&Workflow")
        else:
            menu.addSeparator()
        menu.addAction("Analysis History...").triggered.connect(self.wf_show_history)
        menu.addAction("Export Workflow (JSON)...").triggered.connect(self.wf_export)
        menu.addAction("Import Workflow -> Re-run...").triggered.connect(self.wf_import_and_run)
        menu.addAction("Generate Python Script...").triggered.connect(self.wf_generate_script)
        menu.addSeparator()
        menu.addAction("Auto Report (HTML)...").triggered.connect(self.wf_auto_report)
        menu.addAction("Project Snapshot (JSON)...").triggered.connect(self.wf_project_snapshot)
        menu.addAction("Compare with Last Snapshot").triggered.connect(self.wf_compare_versions)
        menu.addAction("Audit Trail Book").triggered.connect(self.wf_audit_trail)
        menu.addAction("Clear Analysis History").triggered.connect(self.wf_clear)

    # -------------------------------------------------------------- recording
    def _record_op(self, op: str, **params):
        """Record one operation into history and the operation log dock."""
        history = getattr(self, "analysis_history", None)
        if history is None:
            self.analysis_history = history = AnalysisHistory()
        entry = history.record(op, **params)
        try:
            dock = getattr(self, "op_log_dock", None)
            if dock is not None:
                shown = ", ".join(f"{k}={v}" for k, v in params.items() if v is not None)
                dock.add_entry(f"{op}({shown})")
        except Exception:
            logger.debug("op log entry skipped", exc_info=True)
        return entry

    # ------------------------------------------------------------------ flows
    def wf_show_history(self):
        history = getattr(self, "analysis_history", None)
        if history is None or len(history) == 0:
            self.inform(
                "Analysis History",
                "No operations have been recorded yet. Use Process or Analysis actions first.",
            )
            return
        lines = []
        for i, entry in enumerate(history.entries, start=1):
            params = ", ".join(f"{k}={v}" for k, v in entry["params"].items() if v is not None)
            lines.append(f"{i}. [{entry['time']}] {entry['op']}({params})")
        self.inform(f"Analysis History ({len(history)} items)", "\n".join(lines))

    def wf_export(self):
        history = getattr(self, "analysis_history", None)
        if history is None or len(history) == 0:
            self.inform("No history", "Run at least one operation before exporting a workflow.")
            return
        path = self.ask_save_path("Save Workflow", "workflow.json", "Workflow (*.json)")
        if not path:
            return
        checksum = None
        try:
            if self._df is not None and not self._df.empty:
                checksum = dataframe_checksum(self._df)
        except Exception:
            logger.debug("checksum skipped", exc_info=True)
        try:
            text = history.to_json(source_path=getattr(self, "_current_path", None),
                                   checksum=checksum)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.notify(f"Workflow saved: {os.path.basename(path)} "
                        f"({len(history)} operations)")
        except Exception as e:
            self.error_box("Export failed", f"Reason: {e}")

    def wf_import_and_run(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform(
                "No data",
                "Open or select a Book with data before re-running a workflow.",
            )
            return
        path = self.ask_open_path("Open Workflow", "Workflow (*.json);;All Files (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = AnalysisHistory.from_json(f.read())
        except Exception as e:
            self.error_box("Read workflow failed", f"Reason: {e}")
            return
        # Re-run is lenient (like the generated script): a recorded history can
        # legitimately contain analysis-only ops that produced a result Book
        # (descriptive_statistics, covariance_matrix, peak_metrics, …) and never
        # transformed the primary data — those have no replay entry, so a strict
        # replay would abort the whole workflow. Skip them and tell the user.
        replayable = [e for e in history.entries if e["op"] in REPLAY_REGISTRY]
        skipped = [e["op"] for e in history.entries if e["op"] not in REPLAY_REGISTRY]
        try:
            new_df = replay(history, self._df, strict=False)
        except Exception as e:
            self.error_box("Re-run failed", f"Reason: {e}")
            return
        self._swap_dataframe(new_df)
        # Current history is the workflow that just ran; users can export it.
        self.analysis_history = history
        msg = (
            f"Workflow re-run complete ({len(replayable)} data operations applied); "
            f"current data: {len(new_df)} rows x {len(new_df.columns)} columns"
        )
        if skipped:
            unique_skipped = ", ".join(dict.fromkeys(skipped))
            msg += f"; skipped {len(skipped)} non-transform op(s): {unique_skipped}"
        self.notify(msg)

    def wf_generate_script(self):
        history = getattr(self, "analysis_history", None)
        if history is None or len(history) == 0:
            self.inform("No history", "Run at least one operation before generating a script.")
            return
        path = self.ask_save_path("Save Python Script", "workflow_script.py",
                                  "Python (*.py)")
        if not path:
            return
        try:
            script = generate_python_script(
                history, source_path=getattr(self, "_current_path", None))
            with open(path, "w", encoding="utf-8") as f:
                f.write(script)
            self.notify(f"Python script generated: {os.path.basename(path)}")
        except Exception as e:
            self.error_box("Generate script failed", f"Reason: {e}")

    def _current_workflow_dataframe(self) -> pd.DataFrame:
        getter = getattr(self, "get_current_dataframe", None)
        if callable(getter):
            df = getter()
            if isinstance(df, pd.DataFrame):
                return df
        df = getattr(self, "_df", None)
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    def _snapshot_payload(self) -> dict:
        df = self._current_workflow_dataframe()
        datasets = getattr(self, "_datasets", {})
        dataset_rows = []
        if isinstance(datasets, dict):
            for name, payload in datasets.items():
                data = payload.get("df") if isinstance(payload, dict) else None
                if isinstance(data, pd.DataFrame):
                    dataset_rows.append({
                        "name": str(name),
                        "rows": int(len(data)),
                        "columns": int(len(data.columns)),
                        "checksum": dataframe_checksum(data) if not data.empty else "",
                    })
        history = getattr(self, "analysis_history", None)
        active_book = getattr(self, "_active_book_label", lambda: "Book1")()
        return {
            "app": "SciPlotter",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "active_book": active_book,
            "active_rows": int(len(df)),
            "active_columns": int(len(df.columns)),
            "active_checksum": dataframe_checksum(df) if not df.empty else "",
            "datasets": dataset_rows,
            "history": list(getattr(history, "entries", [])) if history is not None else [],
        }

    def wf_auto_report(self):
        df = self._current_workflow_dataframe()
        if df.empty:
            self.inform("No data", "Open or select a Book before generating a report.")
            return
        path = self.ask_save_path(
            "Save Auto Report",
            "sciplotter_auto_report.html",
            "HTML Report (*.html);;All Files (*.*)",
        )
        if not path:
            return
        try:
            payload = self._snapshot_payload()
            stats = df.describe(include="all").transpose().reset_index()
            history = pd.DataFrame(payload["history"])
            html = "\n".join([
                "<!doctype html><html><head><meta charset='utf-8'>",
                "<title>SciPlotter Auto Report</title>",
                "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#17202a}"
                "table{border-collapse:collapse;width:100%;margin:16px 0}"
                "td,th{border:1px solid #d0d7de;padding:6px 8px;text-align:left}"
                "th{background:#edf3fb}code{background:#f6f8fa;padding:2px 4px}</style>",
                "</head><body>",
                "<h1>SciPlotter Auto Report</h1>",
                f"<p><b>Created:</b> {payload['created_at']}<br>",
                f"<b>Active Book:</b> {payload['active_book']}<br>",
                f"<b>Rows x Columns:</b> {payload['active_rows']} x {payload['active_columns']}<br>",
                f"<b>Checksum:</b> <code>{payload['active_checksum']}</code></p>",
                "<h2>Column Summary</h2>",
                stats.to_html(index=False, escape=True),
                "<h2>Workflow History</h2>",
                history.to_html(index=False, escape=True) if not history.empty else "<p>No recorded operations.</p>",
                "</body></html>",
            ])
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            self.notify(f"Auto report saved: {os.path.basename(path)}")
        except Exception as e:
            self.error_box("Auto Report failed", f"Reason: {e}")

    def wf_project_snapshot(self):
        df = self._current_workflow_dataframe()
        if df.empty:
            self.inform("No data", "Open or select a Book before saving a snapshot.")
            return
        path = self.ask_save_path(
            "Save Project Snapshot",
            "sciplotter_snapshot.json",
            "Snapshot (*.json);;All Files (*.*)",
        )
        if not path:
            return
        try:
            payload = self._snapshot_payload()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self._last_snapshot_payload = payload
            self.notify(f"Project snapshot saved: {os.path.basename(path)}")
        except Exception as e:
            self.error_box("Project Snapshot failed", f"Reason: {e}")

    def wf_compare_versions(self):
        current = self._snapshot_payload()
        previous = getattr(self, "_last_snapshot_payload", None)
        if not isinstance(previous, dict):
            self._last_snapshot_payload = current
            self.inform(
                "Snapshot baseline captured",
                "No previous snapshot was loaded in this session. Current state is now the comparison baseline.",
            )
            return
        rows = []
        for key in ("active_book", "active_rows", "active_columns", "active_checksum"):
            rows.append({
                "field": key,
                "previous": previous.get(key),
                "current": current.get(key),
                "changed": previous.get(key) != current.get(key),
            })
        table = pd.DataFrame(rows)
        opener = getattr(self, "_open_signal_result_book", None)
        if callable(opener):
            target = opener("Snapshot Compare", table)
            self.notify(f"Snapshot comparison -> {target}")
        else:
            changed = int(table["changed"].sum())
            self.inform("Snapshot comparison", f"{changed} fields changed.")

    def wf_audit_trail(self):
        payload = self._snapshot_payload()
        history = payload.get("history", [])
        rows = []
        for index, entry in enumerate(history, start=1):
            rows.append({
                "index": index,
                "time": entry.get("time", ""),
                "operation": entry.get("op", ""),
                "parameters": json.dumps(entry.get("params", {}), ensure_ascii=False, sort_keys=True),
                "active_checksum": payload.get("active_checksum", ""),
            })
        if not rows:
            rows.append({
                "index": 1,
                "time": payload.get("created_at", ""),
                "operation": "snapshot",
                "parameters": json.dumps({"active_book": payload.get("active_book")}, ensure_ascii=False),
                "active_checksum": payload.get("active_checksum", ""),
            })
        table = pd.DataFrame(rows)
        opener = getattr(self, "_open_signal_result_book", None)
        if callable(opener):
            target = opener("Audit Trail", table)
            self.notify(f"Audit trail -> {target}")
        else:
            self.inform("Audit trail", table.to_string(index=False))

    def wf_clear(self):
        history = getattr(self, "analysis_history", None)
        if history is not None:
            history.clear()
        self.notify("Analysis history cleared.")
