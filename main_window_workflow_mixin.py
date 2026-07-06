from __future__ import annotations

import logging
import os

from core.history import (
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
        menu.addAction("Analysis History…").triggered.connect(self.wf_show_history)
        menu.addAction("Export Workflow (JSON)…").triggered.connect(self.wf_export)
        menu.addAction("Import Workflow → Re-run…").triggered.connect(self.wf_import_and_run)
        menu.addAction("Generate Python Script…").triggered.connect(self.wf_generate_script)
        menu.addAction("Clear Analysis History").triggered.connect(self.wf_clear)

    # -------------------------------------------------------------- recording
    def _record_op(self, op: str, **params):
        """บันทึกหนึ่ง operation ลงประวัติ + operation log dock"""
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
            self.inform("ประวัติการวิเคราะห์",
                        "ยังไม่มี operation ที่บันทึกไว้ — ใช้เมนู Process/Filters ก่อน")
            return
        lines = []
        for i, entry in enumerate(history.entries, start=1):
            params = ", ".join(f"{k}={v}" for k, v in entry["params"].items() if v is not None)
            lines.append(f"{i}. [{entry['time']}] {entry['op']}({params})")
        self.inform(f"ประวัติการวิเคราะห์ ({len(history)} รายการ)", "\n".join(lines))

    def wf_export(self):
        history = getattr(self, "analysis_history", None)
        if history is None or len(history) == 0:
            self.inform("ยังไม่มีประวัติ", "ทำ operation ก่อนแล้วค่อย export workflow")
            return
        path = self.ask_save_path("บันทึก Workflow", "workflow.json", "Workflow (*.json)")
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
            self.notify(f"บันทึก workflow แล้ว: {os.path.basename(path)} "
                        f"({len(history)} operations)")
        except Exception as e:
            self.error_box("Export ไม่สำเร็จ", f"สาเหตุ: {e}")

    def wf_import_and_run(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล",
                        "เปิด/เลือก Book ที่มีข้อมูลก่อน แล้ว workflow จะถูก re-run กับข้อมูลนั้น")
            return
        path = self.ask_open_path("เลือกไฟล์ Workflow", "Workflow (*.json);;All Files (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = AnalysisHistory.from_json(f.read())
        except Exception as e:
            self.error_box("อ่าน workflow ไม่สำเร็จ", f"สาเหตุ: {e}")
            return
        try:
            new_df = replay(history, self._df)
        except Exception as e:
            self.error_box("Re-run ไม่สำเร็จ", f"สาเหตุ: {e}")
            return
        self._swap_dataframe(new_df)
        # ประวัติปัจจุบัน = workflow ที่เพิ่ง run (จะ export/สร้างสคริปต์ต่อได้)
        self.analysis_history = history
        self.notify(f"Re-run workflow แล้ว ({len(history)} operations) — "
                    f"ข้อมูลตอนนี้ {len(new_df)} แถว × {len(new_df.columns)} คอลัมน์")

    def wf_generate_script(self):
        history = getattr(self, "analysis_history", None)
        if history is None or len(history) == 0:
            self.inform("ยังไม่มีประวัติ", "ทำ operation ก่อนแล้วค่อยสร้างสคริปต์")
            return
        path = self.ask_save_path("บันทึกสคริปต์ Python", "workflow_script.py",
                                  "Python (*.py)")
        if not path:
            return
        try:
            script = generate_python_script(
                history, source_path=getattr(self, "_current_path", None))
            with open(path, "w", encoding="utf-8") as f:
                f.write(script)
            self.notify(f"สร้างสคริปต์แล้ว: {os.path.basename(path)}")
        except Exception as e:
            self.error_box("สร้างสคริปต์ไม่สำเร็จ", f"สาเหตุ: {e}")

    def wf_clear(self):
        history = getattr(self, "analysis_history", None)
        if history is not None:
            history.clear()
        self.notify("ล้างประวัติการวิเคราะห์แล้ว")
