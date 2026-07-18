"""One-click publication reports: assemble open Graphs + result Books + an
auto-written narrative into a self-contained HTML / Markdown / PDF document.

The document model and renderers are pure in ``core/report.py``; this mixin
collects live app state, previews in the in-app browser, and exports. Every
step has a param-taking core so the AI ``generate_report`` tool runs the same
path with no dialogs.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from core import report as R

logger = logging.getLogger(__name__)


class MainWindowReportMixin:
    """Report / Publishing workflow (menu + preview + export + AI core)."""

    def init_report_module(self):
        menu = self.menuBar().addMenu("&Report")
        act = menu.addAction("Generate Report...")
        act.setShortcut("Ctrl+Shift+R")
        act.triggered.connect(self.report_builder_dialog)
        menu.addAction("Quick Report (everything)").triggered.connect(
            self.report_quick)
        menu.addSeparator()
        menu.addAction("Export Report as HTML...").triggered.connect(
            lambda: self._report_export_dialog("html"))
        menu.addAction("Export Report as PDF...").triggered.connect(
            lambda: self._report_export_dialog("pdf"))
        menu.addAction("Export Report as Markdown...").triggered.connect(
            lambda: self._report_export_dialog("md"))
        self._report_menu = menu

    # --------------------------------------------------------------- collectors
    def _report_graphs(self):
        """[(title, png_bytes), ...] for every open Graph that has content."""
        out = []
        tabs = getattr(self.tabs, "tabs", None)
        if not isinstance(tabs, dict):
            return out
        titles = dict(self.tabs.get_open_tabs()) if hasattr(self.tabs, "get_open_tabs") else {}
        for tab_id, tab in tabs.items():
            try:
                fig = tab.get_figure() if hasattr(tab, "get_figure") else None
                ax = tab.get_axes() if hasattr(tab, "get_axes") else None
                if fig is None or ax is None:
                    continue
                has_content = bool(ax.lines or ax.collections or ax.images
                                   or ax.patches or getattr(fig, "axes", None) and
                                   any(a.has_data() for a in fig.axes))
                if not has_content:
                    continue
                buffer = io.BytesIO()
                fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight",
                            facecolor=fig.get_facecolor())
                title = titles.get(tab_id) or getattr(tab, "name", "") or "Graph"
                out.append((str(title), buffer.getvalue()))
            except Exception:
                logger.debug("report graph capture failed", exc_info=True)
        return out

    def _report_tables(self):
        """[(name, frame, provenance), ...] for open data/result Books."""
        out = []
        datasets = getattr(self, "_datasets", None)
        if not isinstance(datasets, dict):
            return out
        for name, payload in datasets.items():
            if not isinstance(payload, dict):
                continue
            frame = payload.get("df")
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                out.append((str(name), frame, payload.get("analysis_provenance")))
        return out

    def _auto_narrative(self, tables) -> str:
        """A data-driven summary paragraph — beats Origin's empty report even
        with no AI model available."""
        if not tables:
            return "This report was generated from the current SciPlotter session."
        bits = []
        for name, frame, _prov in tables[:4]:
            numeric = frame.select_dtypes(include=[np.number])
            if numeric.empty:
                bits.append(f"“{name}” has {len(frame)} rows across "
                            f"{len(frame.columns)} columns.")
                continue
            col = numeric.columns[0]
            series = numeric[col].dropna()
            if series.empty:
                continue
            bits.append(
                f"In “{name}”, {col} ranges {series.min():.4g}–{series.max():.4g} "
                f"(mean {series.mean():.4g}, n={len(series)}).")
        head = (f"This report summarises {len(tables)} dataset(s) and the current "
                f"figures. ")
        return head + " ".join(bits)

    # ---------------------------------------------------------------- build core
    def generate_report_core(self, *, title=None, author="", subtitle="",
                             template="Lab Report", include_graphs=True,
                             include_tables=True, include_narrative=True,
                             table_names=None, max_table_rows=30):
        """Assemble a :class:`core.report.ReportDocument` from live app state."""
        doc = R.ReportDocument(
            title=title or "SciPlotter Report", subtitle=subtitle,
            author=author, template=template)
        tables = self._report_tables()
        if table_names is not None:
            wanted = set(table_names)
            tables = [t for t in tables if t[0] in wanted]
        if include_narrative:
            doc.add_text("Summary", self._auto_narrative(tables))
        if include_graphs:
            for gtitle, png in self._report_graphs():
                doc.add_figure(gtitle, png, f"Figure. {gtitle}.")
        if include_tables:
            for name, frame, _prov in tables:
                doc.add_table(name, frame,
                              f"Table. {name} ({len(frame)} rows × {len(frame.columns)} cols).",
                              max_rows=int(max_table_rows))
        return doc

    def _report_render_html_to_tempfile(self, doc) -> str:
        html = R.render_html(doc)
        import tempfile

        path = Path(tempfile.gettempdir()) / "sciplotter_report_preview.html"
        path.write_text(html, encoding="utf-8")
        return str(path)

    def report_export(self, doc, path: str) -> str:
        """Write *doc* to *path*; format chosen by the file extension."""
        suffix = Path(path).suffix.lower()
        if suffix in (".html", ".htm"):
            Path(path).write_text(R.render_html(doc), encoding="utf-8")
        elif suffix in (".md", ".markdown"):
            image_dir = Path(path).parent
            Path(path).write_text(
                R.render_markdown(doc, image_dir=image_dir), encoding="utf-8")
        elif suffix == ".pdf":
            R.render_pdf(doc, path)
        else:
            raise ValueError(f"Unsupported report format: {suffix or '(none)'}")
        return path

    # --------------------------------------------------------------------- UI
    def report_quick(self):
        """Zero-decision report of everything currently open, previewed live."""
        doc = self.generate_report_core(
            title=self._report_default_title(), author=self._report_default_author())
        c = doc.counts()
        if c["figures"] == 0 and c["tables"] == 0:
            self.inform("Report", "Nothing to report yet — plot something or run an analysis.")
            return
        self._report_preview(doc)

    def report_builder_dialog(self):
        from dialogs.report_builder_dialog import ReportBuilderDialog

        tables = [t[0] for t in self._report_tables()]
        graphs = [g[0] for g in self._report_graphs()]
        if not tables and not graphs:
            self.inform("Report", "Nothing to report yet — plot something or run an analysis.")
            return
        dialog = ReportBuilderDialog(
            tables, graphs, default_title=self._report_default_title(),
            default_author=self._report_default_author(), parent=self)
        if dialog.exec() != _accepted():
            return
        values = dialog.values()
        doc = self.generate_report_core(
            title=values["title"], author=values["author"],
            subtitle=values["subtitle"], template=values["template"],
            include_graphs=values["include_graphs"],
            include_tables=values["include_tables"],
            include_narrative=values["include_narrative"],
            table_names=values["table_names"])
        if values["action"] == "export":
            self._report_export_doc(doc)
        else:
            self._report_preview(doc)

    def _report_preview(self, doc) -> None:
        path = self._report_render_html_to_tempfile(doc)
        opened = False
        starter = getattr(self, "preview_start", None)  # in-app browser, if present
        try:
            import webbrowser

            opened = webbrowser.open(Path(path).as_uri())
        except Exception:
            logger.debug("report preview browser open failed", exc_info=True)
        counts = doc.counts()
        self.notify(
            f"Report preview: {counts['figures']} figure(s), {counts['tables']} table(s)"
            + ("" if opened else f" — open {path}"))

    def _report_export_dialog(self, fmt: str):
        doc = self.generate_report_core(
            title=self._report_default_title(), author=self._report_default_author())
        c = doc.counts()
        if c["figures"] == 0 and c["tables"] == 0:
            self.inform("Report", "Nothing to report yet.")
            return
        self._report_export_doc(doc, fmt=fmt)

    def _report_export_doc(self, doc, fmt: str = "html"):
        filters = {
            "html": "HTML report (*.html)",
            "pdf": "PDF report (*.pdf)",
            "md": "Markdown report (*.md)",
        }
        ext = {"html": ".html", "pdf": ".pdf", "md": ".md"}[fmt]
        path = self.ask_save_path("Export Report",
                                  f"{_safe_name(doc.title)}{ext}", filters[fmt])
        if not path:
            return
        if not Path(path).suffix:
            path += ext
        try:
            self.report_export(doc, path)
        except Exception as exc:
            logger.debug("report export failed", exc_info=True)
            self.error_box("Report export failed", str(exc))
            return
        self.notify(f"Report saved: {path}")

    # ------------------------------------------------------------------ helpers
    def _report_default_title(self) -> str:
        label = ""
        getter = getattr(self, "_active_book_label", None)
        if callable(getter):
            label = str(getter() or "")
        return f"{label} — Analysis Report" if label else "SciPlotter Report"

    def _report_default_author(self) -> str:
        try:
            settings = getattr(self, "settings", None)
            if settings is not None and hasattr(settings, "get_ai"):
                pass
        except Exception:
            logger.debug("author default lookup failed", exc_info=True)
        return ""


def _accepted():
    from PySide6.QtWidgets import QDialog

    return QDialog.Accepted


def _safe_name(text: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_" else "_" for c in str(text))
    return (keep.strip() or "report")[:60]
