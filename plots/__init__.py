"""Origin-style plot library.

Each plot is a *pure* function ``f(ax, df, **opts) -> None`` that draws onto a
Matplotlib ``Axes`` (or repaints ``ax.figure`` for multi-panel plots) using a
pandas ``DataFrame``. Functions never raise on empty/insufficient data — they
draw a placeholder message instead. Every module exposes a module-level
``PLOTS`` list describing its plots for the gallery registry.

See :mod:`plots._common` for shared helpers and :mod:`plots.registry` for the
aggregated catalog.
"""
