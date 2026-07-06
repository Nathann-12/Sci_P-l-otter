# dialogs/plot_details_dialog.py
"""OriginPro-style "Plot Details" dialog — deep, tabbed graph customization.

The dialog is pure Qt: it is seeded from a style dict (see core.plot_style) plus
a list of per-curve style dicts, and reads back edited values via
:meth:`get_style` / :meth:`get_line_styles`. It never touches matplotlib — the
caller applies the returned dicts. An ``applied`` signal lets the caller do a
live "Apply" without closing.
"""
from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from widgets.color_button import ColorButton
from core.plot_style import (
    LEGEND_LOCS,
    LINE_STYLES,
    MARKERS,
    SCALES,
    TICK_DIRECTIONS,
)


def _hex_to_qcolor(h: str) -> QColor:
    c = QColor(h)
    return c if c.isValid() else QColor("#000000")


class PlotDetailsDialog(QDialog):
    applied = Signal()

    def __init__(self, style: Dict[str, Any], line_styles: List[Dict[str, Any]],
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plot Details")
        self.setModal(True)
        self._line_styles = [dict(d) for d in line_styles]

        outer = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.addTab(self._build_axes_tab(style.get("axes", {})), "Axes")
        tabs.addTab(self._build_grid_legend_tab(style.get("grid", {}),
                                                style.get("legend", {})), "Grid && Legend")
        tabs.addTab(self._build_lines_tab(), "Lines")
        tabs.addTab(self._build_figure_tab(style.get("figure", {})), "Figure")
        outer.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Apply | QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.setMinimumWidth(440)

    # ------------------------------------------------------------------ Axes
    def _build_axes_tab(self, a: Dict[str, Any]) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.ed_title = QLineEdit(a.get("title", ""))
        self.sp_title_size = _spin(a.get("title_size", 12), 4, 72)
        self.ed_xlabel = QLineEdit(a.get("xlabel", ""))
        self.ed_ylabel = QLineEdit(a.get("ylabel", ""))
        self.sp_label_size = _spin(a.get("label_size", 10), 4, 72)
        self.sp_tick_size = _spin(a.get("tick_size", 10), 4, 72)
        form.addRow("Title", self.ed_title)
        form.addRow("Title size", self.sp_title_size)
        form.addRow("X label", self.ed_xlabel)
        form.addRow("Y label", self.ed_ylabel)
        form.addRow("Label size", self.sp_label_size)
        form.addRow("Tick size", self.sp_tick_size)

        # X range
        self.chk_xauto = QCheckBox("Auto")
        self.chk_xauto.setChecked(bool(a.get("x_autoscale", True)))
        self.sp_xmin = _dspin(a.get("xmin", 0.0))
        self.sp_xmax = _dspin(a.get("xmax", 1.0))
        form.addRow("X range", _range_row(self.chk_xauto, self.sp_xmin, self.sp_xmax))
        self.chk_yauto = QCheckBox("Auto")
        self.chk_yauto.setChecked(bool(a.get("y_autoscale", True)))
        self.sp_ymin = _dspin(a.get("ymin", 0.0))
        self.sp_ymax = _dspin(a.get("ymax", 1.0))
        form.addRow("Y range", _range_row(self.chk_yauto, self.sp_ymin, self.sp_ymax))

        self.cb_xscale = _combo(SCALES, a.get("xscale", "linear"))
        self.cb_yscale = _combo(SCALES, a.get("yscale", "linear"))
        form.addRow("X scale", self.cb_xscale)
        form.addRow("Y scale", self.cb_yscale)
        self.chk_invx = QCheckBox("Reverse X")
        self.chk_invx.setChecked(bool(a.get("invert_x", False)))
        self.chk_invy = QCheckBox("Reverse Y")
        self.chk_invy.setChecked(bool(a.get("invert_y", False)))
        form.addRow("", self.chk_invx)
        form.addRow("", self.chk_invy)
        self.cb_tickdir = _combo(TICK_DIRECTIONS, a.get("tick_direction", "out"))
        form.addRow("Tick direction", self.cb_tickdir)
        return w

    # -------------------------------------------------------- Grid & Legend
    def _build_grid_legend_tab(self, g: Dict[str, Any], leg: Dict[str, Any]) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        gb_grid = QGroupBox("Grid")
        gf = QFormLayout(gb_grid)
        self.chk_grid = QCheckBox("Show major grid")
        self.chk_grid.setChecked(bool(g.get("major", False)))
        self.chk_gridminor = QCheckBox("Show minor grid")
        self.chk_gridminor.setChecked(bool(g.get("minor", False)))
        self.btn_gridcolor = ColorButton(_hex_to_qcolor(g.get("color", "#3a3f44")))
        self.cb_gridstyle = _combo(LINE_STYLES, g.get("linestyle", "-"))
        self.sp_gridalpha = _dspin(g.get("alpha", 0.3), 0.0, 1.0, decimals=2, step=0.05)
        gf.addRow("", self.chk_grid)
        gf.addRow("", self.chk_gridminor)
        gf.addRow("Grid color", self.btn_gridcolor)
        gf.addRow("Grid style", self.cb_gridstyle)
        gf.addRow("Grid alpha", self.sp_gridalpha)
        v.addWidget(gb_grid)

        gb_leg = QGroupBox("Legend")
        lf = QFormLayout(gb_leg)
        self.chk_legend = QCheckBox("Show legend")
        self.chk_legend.setChecked(bool(leg.get("visible", False)))
        self.cb_legloc = _combo(LEGEND_LOCS, leg.get("loc", "best"))
        self.sp_legsize = _spin(leg.get("fontsize", 10), 4, 48)
        self.sp_legcol = _spin(leg.get("ncol", 1), 1, 8)
        self.chk_legframe = QCheckBox("Frame")
        self.chk_legframe.setChecked(bool(leg.get("frame", True)))
        lf.addRow("", self.chk_legend)
        lf.addRow("Location", self.cb_legloc)
        lf.addRow("Font size", self.sp_legsize)
        lf.addRow("Columns", self.sp_legcol)
        lf.addRow("", self.chk_legframe)
        v.addWidget(gb_leg)
        v.addStretch(1)
        return w

    # ----------------------------------------------------------------- Lines
    def _build_lines_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.cb_line = QComboBox()
        for i, d in enumerate(self._line_styles):
            self.cb_line.addItem(d.get("label") or f"Curve {i + 1}")
        v.addWidget(QLabel("Curve"))
        v.addWidget(self.cb_line)

        form = QFormLayout()
        self.ed_linelabel = QLineEdit()
        self.btn_linecolor = ColorButton(QColor("#000000"))
        self.sp_linewidth = _dspin(1.5, 0.1, 50.0, decimals=2, step=0.5)
        self.cb_linestyle = _combo(LINE_STYLES, "-")
        self.cb_marker = _combo(MARKERS, "None")
        self.sp_markersize = _dspin(6.0, 0.0, 50.0, decimals=1, step=1.0)
        self.sp_linealpha = _dspin(1.0, 0.0, 1.0, decimals=2, step=0.05)
        form.addRow("Label", self.ed_linelabel)
        form.addRow("Color", self.btn_linecolor)
        form.addRow("Line width", self.sp_linewidth)
        form.addRow("Line style", self.cb_linestyle)
        form.addRow("Marker", self.cb_marker)
        form.addRow("Marker size", self.sp_markersize)
        form.addRow("Opacity", self.sp_linealpha)
        v.addLayout(form)
        v.addStretch(1)

        if not self._line_styles:
            w.setEnabled(False)
        else:
            self._current_line = 0
            self._load_line(0)
            self.cb_line.currentIndexChanged.connect(self._on_line_changed)
        return w

    def _load_line(self, i: int) -> None:
        d = self._line_styles[i]
        self.ed_linelabel.setText(str(d.get("label", "")))
        self.btn_linecolor.setColor(_hex_to_qcolor(d.get("color", "#000000")))
        self.sp_linewidth.setValue(float(d.get("linewidth", 1.5)))
        _set_combo(self.cb_linestyle, d.get("linestyle", "-"))
        _set_combo(self.cb_marker, d.get("marker", "None"))
        self.sp_markersize.setValue(float(d.get("markersize", 6.0)))
        self.sp_linealpha.setValue(float(d.get("alpha", 1.0)))

    def _store_line(self, i: int) -> None:
        self._line_styles[i] = {
            "label": self.ed_linelabel.text(),
            "color": self.btn_linecolor.color().name(),
            "linewidth": self.sp_linewidth.value(),
            "linestyle": self.cb_linestyle.currentText(),
            "marker": self.cb_marker.currentText(),
            "markersize": self.sp_markersize.value(),
            "alpha": self.sp_linealpha.value(),
        }

    def _on_line_changed(self, i: int) -> None:
        self._store_line(self._current_line)
        self._current_line = i
        self._load_line(i)

    # ---------------------------------------------------------------- Figure
    def _build_figure_tab(self, f: Dict[str, Any]) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.btn_axesbg = ColorButton(_hex_to_qcolor(f.get("facecolor", "#1e2126")))
        self.btn_figbg = ColorButton(_hex_to_qcolor(f.get("fig_facecolor", "#1e2126")))
        form.addRow("Axes background", self.btn_axesbg)
        form.addRow("Figure background", self.btn_figbg)
        return w

    # ------------------------------------------------------------------ read
    def get_style(self) -> Dict[str, Any]:
        return {
            "axes": {
                "title": self.ed_title.text(),
                "title_size": self.sp_title_size.value(),
                "xlabel": self.ed_xlabel.text(),
                "ylabel": self.ed_ylabel.text(),
                "label_size": self.sp_label_size.value(),
                "tick_size": self.sp_tick_size.value(),
                "tick_direction": self.cb_tickdir.currentText(),
                "x_autoscale": self.chk_xauto.isChecked(),
                "xmin": self.sp_xmin.value(), "xmax": self.sp_xmax.value(),
                "y_autoscale": self.chk_yauto.isChecked(),
                "ymin": self.sp_ymin.value(), "ymax": self.sp_ymax.value(),
                "xscale": self.cb_xscale.currentText(),
                "yscale": self.cb_yscale.currentText(),
                "invert_x": self.chk_invx.isChecked(),
                "invert_y": self.chk_invy.isChecked(),
            },
            "grid": {
                "major": self.chk_grid.isChecked(),
                "minor": self.chk_gridminor.isChecked(),
                "color": self.btn_gridcolor.color().name(),
                "linestyle": self.cb_gridstyle.currentText(),
                "alpha": self.sp_gridalpha.value(),
            },
            "legend": {
                "visible": self.chk_legend.isChecked(),
                "loc": self.cb_legloc.currentText(),
                "fontsize": self.sp_legsize.value(),
                "ncol": self.sp_legcol.value(),
                "frame": self.chk_legframe.isChecked(),
            },
            "figure": {
                "facecolor": self.btn_axesbg.color().name(),
                "fig_facecolor": self.btn_figbg.color().name(),
            },
        }

    def get_line_styles(self) -> List[Dict[str, Any]]:
        if self._line_styles:
            self._store_line(self._current_line)
        return [dict(d) for d in self._line_styles]

    def _on_apply(self) -> None:
        self.applied.emit()


# --- tiny widget factories --------------------------------------------------
def _spin(value, lo, hi):
    s = QSpinBox()
    s.setRange(int(lo), int(hi))
    s.setValue(int(round(float(value))))
    return s


def _dspin(value, lo=-1e12, hi=1e12, decimals=4, step=1.0):
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(float(lo), float(hi))
    s.setSingleStep(step)
    s.setValue(float(value))
    return s


def _combo(options, current):
    c = QComboBox()
    c.addItems([str(o) for o in options])
    _set_combo(c, current)
    return c


def _set_combo(combo: QComboBox, value) -> None:
    idx = combo.findText(str(value))
    if idx >= 0:
        combo.setCurrentIndex(idx)


def _range_row(chk, sp_min, sp_max):
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(chk)
    h.addWidget(sp_min)
    h.addWidget(QLabel("→"))
    h.addWidget(sp_max)
    # disable min/max while auto is on
    def _sync(on):
        sp_min.setEnabled(not on)
        sp_max.setEnabled(not on)
    chk.toggled.connect(_sync)
    _sync(chk.isChecked())
    return row
