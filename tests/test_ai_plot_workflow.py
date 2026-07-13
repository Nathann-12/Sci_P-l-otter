"""User-level AI plotting test in an isolated real application process."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ai_plot_commands_create_real_graphs_in_app_process():
    scenario = textwrap.dedent(
        r"""
        import os
        import time

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        import pandas as pd
        from PySide6.QtWidgets import QApplication
        import main as app_main

        class NeverCallModel:
            model = "deterministic-test"

            def chat(self, *_args, **_kwargs):
                raise AssertionError("simple plot commands must not call the LLM")

        app = QApplication.instance() or QApplication([])
        window = app_main.MainWindow()
        assert window.init_ai_assistant(client=NeverCallModel()) is True
        data = pd.DataFrame(
            {
                "time": [0.0, 1.0, 2.0, 3.0],
                "voltage": [1.0, 4.0, 2.0, 5.0],
                "current": [0.2, 0.5, 0.3, 0.7],
            }
        )
        window.workbook.set_dataframe(data)
        window.workbook.dataset_name = "Book1"
        window._df = data
        window.load_columns_from_df()
        window._refresh_ai_context()

        analysis = window._ai_assistant.ask("วิเคราะห์")
        assert analysis.trace[0][0] == "summarize_data"
        assert "4 แถว" in analysis.answer
        assert "voltage" in analysis.answer
        assert "ขอโทษ" not in analysis.answer

        graph_count = window.tabs.count()
        result = window._ai_assistant.ask(
            "plot voltage and current vs time as a line graph"
        )
        assert result.error == "", result.error
        assert result.trace[0][0] == "plot_columns"
        assert window.tabs.count() == graph_count + 1
        axes = window.tabs.currentWidget().get_axes()
        assert len(axes.get_lines()) == 2
        assert axes.get_xlabel() == "time"
        assert {line.get_label() for line in axes.get_lines()} == {
            "voltage vs time",
            "current vs time",
        }

        graph_count = window.tabs.count()
        window.ai_dock.input_edit.setText("plot voltage vs time as scatter")
        window.ai_dock._submit()
        deadline = time.monotonic() + 10.0
        while (
            window._ai_busy or window._ai_worker is not None
        ) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        app.processEvents()

        assert window._ai_busy is False
        assert window._ai_worker is None
        assert window.tabs.count() == graph_count + 1
        axes = window.tabs.currentWidget().get_axes()
        assert len(axes.collections) == 1
        assert axes.get_xlabel() == "time"
        assert axes.get_ylabel() == "voltage"
        assert "AI: Created a scatter graph" in window.ai_dock.transcript_text()
        assert "plot_columns" in window.ai_dock.action_label.text()

        window.close()
        app.processEvents()
        print("AI_PLOT_WORKFLOW_OK")
        """
    )
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["PYTHONPATH"] = str(PROJECT_ROOT)
    completed = subprocess.run(
        [sys.executable, "-c", scenario],
        cwd=str(PROJECT_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, (
        f"isolated AI plotting workflow failed\nSTDOUT:\n{completed.stdout}\n"
        f"STDERR:\n{completed.stderr}"
    )
    assert "AI_PLOT_WORKFLOW_OK" in completed.stdout
