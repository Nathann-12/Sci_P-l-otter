"""Aggregated catalog of the Origin-style plots.

Each plot module (:mod:`plots.dist_plots`, :mod:`plots.rel_plots`,
:mod:`plots.qc_plots`) exposes a module-level ``PLOTS`` list of dicts::

    {"key", "title", "category", "func", "desc", "min_cols", "multi"}

This module concatenates them (de-duplicating by ``key``) and groups them by
category so the gallery UI can render an Origin-like panel. Modules that fail to
import are skipped so a single broken plot never takes down the whole gallery.
"""
from __future__ import annotations

import importlib
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Source modules, in the order their categories should appear.
_MODULES = (
    "plots.basic_extra_plots",
    "plots.dist_plots",
    "plots.rel_plots",
    "plots.qc_plots",
    "plots.surface_plots",
    "plots.multicolumn_plots",
    "plots.colormap_plots",
    "plots.polar_plots",
    "plots.frequency_plots",
    "plots.three_d_plots",
)

# Preferred category ordering for the gallery sidebar.
_CATEGORY_ORDER = (
    "Distribution",
    "Basic 2D",
    "Relational",
    "Contour, Heatmap",
    "Multi-Column",
    "Multi-Panel",
    "Polar",
    "Frequency Response",
    "Probability",
    "Quality",
    "Categorical",
    "3D",
)

_REQUIRED_KEYS = ("key", "title", "category", "func")


def all_plots() -> List[Dict[str, Any]]:
    """Every registered plot spec (de-duplicated by ``key``, modules in order)."""
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for modname in _MODULES:
        try:
            mod = importlib.import_module(modname)
        except Exception:
            logger.debug("Plot module %s failed to import", modname, exc_info=True)
            continue
        for entry in getattr(mod, "PLOTS", []):
            key = entry.get("key")
            if not key or key in seen:
                continue
            if not all(k in entry for k in _REQUIRED_KEYS):
                logger.debug("Skipping malformed plot entry: %r", entry)
                continue
            if not callable(entry.get("func")):
                continue
            seen.add(key)
            out.append(entry)
    return out


def plots_by_category() -> "OrderedDict[str, List[Dict[str, Any]]]":
    """Plots grouped by category, preferred categories first."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in all_plots():
        grouped.setdefault(entry.get("category", "Other"), []).append(entry)
    ordered: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for cat in _CATEGORY_ORDER:
        if cat in grouped:
            ordered[cat] = grouped.pop(cat)
    for cat in sorted(grouped):
        ordered[cat] = grouped[cat]
    return ordered


def get_plot(key: str) -> Optional[Dict[str, Any]]:
    """Look up a single plot spec by its ``key`` (or None)."""
    for entry in all_plots():
        if entry.get("key") == key:
            return entry
    return None
