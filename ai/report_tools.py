"""AI tool for one-click reports — assemble the current session into a report
file (HTML/PDF/Markdown) via the same core the Report menu uses."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _tool_generate_report(window, args: Dict[str, Any]) -> str:
    builder = getattr(window, "generate_report_core", None)
    if not callable(builder):
        return "Reports are unavailable in this context."
    try:
        doc = builder(
            title=args.get("title") or None,
            author=str(args.get("author", "") or ""),
            subtitle=str(args.get("subtitle", "") or ""),
            include_graphs=bool(args.get("include_graphs", True)),
            include_tables=bool(args.get("include_tables", True)),
            include_narrative=bool(args.get("include_narrative", True)),
        )
    except Exception as exc:
        logger.debug("generate_report assembly failed", exc_info=True)
        return f"Could not assemble the report: {exc}"

    counts = doc.counts()
    if counts["figures"] == 0 and counts["tables"] == 0:
        return "Nothing to report yet — plot something or run an analysis first."

    fmt = str(args.get("format", "html") or "html").lower().lstrip(".")
    if fmt not in ("html", "pdf", "md", "markdown"):
        return "format must be html, pdf or md."
    ext = ".md" if fmt in ("md", "markdown") else f".{fmt}"

    path = args.get("path")
    if not path:
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in doc.title)[:50]
        path = str(Path(tempfile.gettempdir()) / f"{safe.strip() or 'report'}{ext}")
    elif not Path(path).suffix:
        path = f"{path}{ext}"

    try:
        window.report_export(doc, path)
    except Exception as exc:
        logger.debug("generate_report export failed", exc_info=True)
        return f"Could not write the report: {exc}"
    return (
        f"Report saved to {path} — {counts['figures']} figure(s), "
        f"{counts['tables']} table(s), with an auto summary."
    )


def register_report_tools(registry, window) -> None:
    registry.add(
        "generate_report",
        "Assemble the open figures and result tables plus an auto-written data "
        "summary into a publication report file (HTML/PDF/Markdown) and save it.",
        {
            "title": {"type": "string", "description": "report title", "required": False},
            "author": {"type": "string", "description": "author name", "required": False},
            "subtitle": {"type": "string", "description": "subtitle", "required": False},
            "format": {
                "type": "string", "required": False,
                "description": "html | pdf | md",
                "enum": ["html", "pdf", "md"],
            },
            "path": {"type": "string", "description": "output file path (optional)", "required": False},
            "include_graphs": {"type": "boolean", "description": "include figures", "required": False},
            "include_tables": {"type": "boolean", "description": "include tables", "required": False},
            "include_narrative": {"type": "boolean", "description": "include the auto summary", "required": False},
        },
        lambda args: _tool_generate_report(window, args),
    )
