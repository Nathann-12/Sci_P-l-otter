"""
Widgets package for SciPlotter
"""

from .color_button import ColorButton, ColorButtonWithLabel
from .mpl_preview import MatplotlibPreview
from .plot_tabs import CompactPlotPanel, GraphTab, PlotCanvas, TabManager

__all__ = [
    'ColorButton',
    'ColorButtonWithLabel', 
    'MatplotlibPreview',
    'PlotCanvas',
    'GraphTab',
    'TabManager',
    'CompactPlotPanel',
]
