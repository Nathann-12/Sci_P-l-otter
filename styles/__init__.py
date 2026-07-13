# SciPlotter Styles Module
# This file makes the styles directory a Python package

from .theme import (
    apply_theme, apply_theme_from_config, apply_mpl_from_config, refresh_matplotlib_canvases,
    apply_qss, apply_font, apply_mpl_style, apply_mpl_overrides,
    apply_matplotlib_to_figure
)

__all__ = [
    'apply_theme', 'apply_theme_from_config', 'apply_mpl_from_config', 'refresh_matplotlib_canvases',
    'apply_qss', 'apply_font', 'apply_mpl_style', 'apply_mpl_overrides',
    'apply_matplotlib_to_figure'
]
