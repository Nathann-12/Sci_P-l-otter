# dialogs/plot_details_dialog.py
"""OriginPro-style "Plot Details" dialog — deep, tabbed graph customization.

The dialog is pure Qt: it is seeded from a style dict (see core.plot_style) plus
a list of per-curve style dicts, and reads back edited values via
:meth:`get_style` / :meth:`get_line_styles`. It never touches matplotlib — the
caller applies the returned dicts. An ``applied`` signal lets the caller do a
live "Apply" without closing.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
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
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtWidgets import QPushButton

from widgets.color_button import ColorButton
from core.plot_style import (
    COLORMAPS,
    DRAW_STYLES,
    ERRORBAR_MODES,
    FILL_MODES,
    FILL_STYLES,
    FONT_FAMILIES,
    GRID_AXES,
    HATCH_PATTERNS,
    INSET_LOCS,
    JOURNAL_PRESETS,
    LEGEND_LOCS,
    LINE_STYLES,
    list_palettes,
    MARKERS,
    SCALES,
    TICK_LABEL_AXES,
    TICK_LABEL_NOTATIONS,
    TICK_DIRECTIONS,
)


def _hex_to_qcolor(h: str) -> QColor:
    c = QColor(h)
    return c if c.isValid() else QColor("#000000")


class PlotDetailsDialog(QDialog):
    applied = Signal()
    # emitted with a template name to save / load; the mixin owns the store
    save_template_requested = Signal(str)
    load_template_requested = Signal(str)
    delete_template_requested = Signal(str)

    def __init__(self, style: Dict[str, Any], line_styles: List[Dict[str, Any]],
                 parent=None, template_names: Optional[List[str]] = None):
        super().__init__(parent)
        self.setWindowTitle("Plot Details")
        self.setModal(True)
        self._line_styles = [dict(d) for d in line_styles]
        self._template_names = list(template_names or [])

        outer = QVBoxLayout(self)
        search_row = QHBoxLayout()
        self.ed_search = QLineEdit(self)
        self.ed_search.setPlaceholderText("Search settings…  (Ctrl+F)")
        self.ed_search.setClearButtonEnabled(True)
        self.lbl_search = QLabel("", self)
        search_row.addWidget(self.ed_search, 1)
        search_row.addWidget(self.lbl_search)
        outer.addLayout(search_row)
        tabs = QTabWidget(self)
        tabs.addTab(_scrolled(self._build_axes_tab(style.get("axes", {}))), "Axes")
        tabs.addTab(_scrolled(self._build_scale_tab(style.get("axes", {}))), "Scale")
        tabs.addTab(
            _scrolled(self._build_ticks_tab(style.get("axes", {}))), "Ticks && Spines")
        tabs.addTab(
            _scrolled(self._build_tick_labels_tab(style.get("tick_labels", {}))),
            "Tick Labels",
        )
        tabs.addTab(
            _scrolled(self._build_reference_lines_tab(style.get("axes", {}))),
            "Reference Lines",
        )
        tabs.addTab(
            _scrolled(self._build_grid_legend_tab(style.get("grid", {}),
                                                  style.get("legend", {}))),
            "Grid && Legend")
        tabs.addTab(_scrolled(self._build_lines_tab()), "Lines")
        tabs.addTab(
            _scrolled(self._build_figure_tab(
                style.get("figure", {}),
                style.get("axes", {}),
                style.get("effects", {}),
            )),
            "Figure",
        )
        tabs.addTab(
            _scrolled(self._build_inset_colorbar_tab(
                style.get("inset", {}), style.get("colorbar", {})
            )),
            "Inset && Colorbar",
        )
        tabs.addTab(self._build_preset_tab(), "Presets && Templates")
        self._tabs = tabs
        outer.addWidget(tabs)
        self._build_search_index()
        self.ed_search.textChanged.connect(self._filter_setting_tabs)
        self._search_shortcut = QShortcut(QKeySequence.Find, self)
        self._search_shortcut.activated.connect(self.ed_search.setFocus)

        # Live preview: edits redraw the graph instantly, no button needed.
        # A short debounce coalesces rapid changes (spin scroll, typing) into
        # one redraw. Cancel restores the original — the mixin owns that.
        self._loading = False
        self.chk_live = QCheckBox("Live preview")
        self.chk_live.setChecked(True)
        self.chk_live.setToolTip("Update the graph as you edit — no Apply needed")
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(180)
        self._live_timer.timeout.connect(self._on_apply)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Apply | QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(self.chk_live)
        bottom.addStretch(1)
        bottom.addWidget(buttons)
        outer.addLayout(bottom)
        self.setMinimumWidth(480)
        self.setMinimumHeight(520)

        # Stability baseline: the dialog's own normalized output right after
        # seeding. Appliers diff against this so an untouched control can never
        # restyle the graph (identity Apply = visual no-op) — even when the
        # seed read something the current theme renders differently.
        self._seed_style = self.get_style()
        self._seed_line_styles = self.get_line_styles()

        # Once seeded, connect every control to the live-preview scheduler.
        self._wire_live_preview()
        # A pending debounced redraw must never fire after the dialog closes.
        self.finished.connect(lambda *_: self._live_timer.stop())

    # ------------------------------------------------------------ live preview
    def _wire_live_preview(self) -> None:
        """Connect every editable control's change signal to the debounce timer.

        Controls that don't feed ``get_style()`` (preset/template pickers)
        simply diff to a no-op, so a blanket connection is safe. Programmatic
        updates set ``_loading`` to suppress feedback loops.
        """
        for w in self.findChildren(QLineEdit):
            if w is self.ed_search:
                continue
            w.textChanged.connect(self._schedule_live)
        for w in self.findChildren(QSpinBox):
            w.valueChanged.connect(self._schedule_live)
        for w in self.findChildren(QDoubleSpinBox):
            w.valueChanged.connect(self._schedule_live)
        for w in self.findChildren(QCheckBox):
            if w is not self.chk_live:
                w.toggled.connect(self._schedule_live)
        # Management pickers (which curve is shown, preset/template selection)
        # only repopulate controls — they must not schedule a redraw. The
        # palette picker DOES recolour live, so it stays connected.
        skip_combos = {
            getattr(self, "cb_line", None),
            getattr(self, "cb_preset", None),
            getattr(self, "cb_template", None),
        }
        for w in self.findChildren(QComboBox):
            if w in skip_combos:
                continue
            w.currentIndexChanged.connect(self._schedule_live)
        for w in self.findChildren(ColorButton):
            w.colorChanged.connect(self._schedule_live)

    def _build_search_index(self) -> None:
        """Index visible control text so the deep dialog stays discoverable."""
        from PySide6.QtWidgets import QAbstractButton

        self._setting_search_index = []
        for index in range(self._tabs.count()):
            page = self._tabs.widget(index)
            words = [self._tabs.tabText(index)]
            for cls in (QLabel, QGroupBox, QAbstractButton):
                for widget in page.findChildren(cls):
                    getter = getattr(widget, "text", None)
                    if callable(getter):
                        words.append(str(getter()))
                    else:
                        words.append(str(getattr(widget, "title", lambda: "")()))
            for combo in page.findChildren(QComboBox):
                words.extend(combo.itemText(i) for i in range(combo.count()))
            self._setting_search_index.append(" ".join(words).casefold())

    def _filter_setting_tabs(self, value: str) -> None:
        query = str(value or "").strip().casefold()
        visible = []
        for index, haystack in enumerate(self._setting_search_index):
            match = not query or all(token in haystack for token in query.split())
            visible.append(match)
            try:
                self._tabs.setTabVisible(index, match)
            except AttributeError:
                self._tabs.setTabEnabled(index, match)
        matches = sum(visible)
        self.lbl_search.setText("" if not query else f"{matches} tab{'s' if matches != 1 else ''}")
        if matches and not visible[self._tabs.currentIndex()]:
            self._tabs.setCurrentIndex(visible.index(True))

    def _schedule_live(self, *_args) -> None:
        if self._loading or not self.chk_live.isChecked():
            return
        self._live_timer.start()

    # ------------------------------------------------------------------ Axes
    def _build_axes_tab(self, a: Dict[str, Any]) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        # --- Title & labels (text + typography) ---
        gb_text = QGroupBox("Title && Labels")
        form = QFormLayout(gb_text)
        self.ed_title = QLineEdit(a.get("title", ""))
        self.sp_title_size = _spin(a.get("title_size", 12), 4, 72)
        self.btn_titlecolor = ColorButton(_hex_to_qcolor(a.get("title_color", "#e6e6e6")))
        self.chk_titlebold = QCheckBox("Bold")
        self.chk_titlebold.setChecked(bool(a.get("title_bold", False)))
        self.chk_titleital = QCheckBox("Italic")
        self.chk_titleital.setChecked(bool(a.get("title_italic", False)))
        self.ed_xlabel = QLineEdit(a.get("xlabel", ""))
        self.ed_ylabel = QLineEdit(a.get("ylabel", ""))
        self.sp_label_size = _spin(a.get("label_size", 10), 4, 72)
        self.btn_labelcolor = ColorButton(_hex_to_qcolor(a.get("label_color", "#e6e6e6")))
        self.chk_labelbold = QCheckBox("Bold")
        self.chk_labelbold.setChecked(bool(a.get("label_bold", False)))
        self.cb_fontfamily = _combo(FONT_FAMILIES, a.get("font_family", "sans-serif"))
        self.sp_labelpad = _dspin(a.get("label_pad", 4.0), 0.0, 40.0, decimals=1, step=1.0)
        form.addRow("Title", self.ed_title)
        form.addRow("Title size", self.sp_title_size)
        form.addRow("Title color", self.btn_titlecolor)
        form.addRow("Title style", _flags_row(self.chk_titlebold, self.chk_titleital))
        form.addRow("X label", self.ed_xlabel)
        form.addRow("Y label", self.ed_ylabel)
        form.addRow("Label size", self.sp_label_size)
        form.addRow("Label color", self.btn_labelcolor)
        form.addRow("Label style", _flags_row(self.chk_labelbold))
        form.addRow("Font family", self.cb_fontfamily)
        form.addRow("Label padding", self.sp_labelpad)
        v.addWidget(gb_text)

        v.addStretch(1)
        return w

    # ----------------------------------------------------------------- Scale
    def _build_scale_tab(self, a: Dict[str, Any]) -> QWidget:
        """Origin-style Scale tab: From/To, Type, Rescale margin, Reverse and
        Major (By Increment + Anchor Tick) / Minor (By Increment or By Counts)
        ticks — one group per axis, like Origin's Horizontal/Vertical panes."""
        w = QWidget()
        v = QVBoxLayout(w)

        # --- Horizontal (X) ---
        gb_x = QGroupBox("Horizontal (X)")
        xf = QFormLayout(gb_x)
        self.chk_xauto = QCheckBox("Auto")
        self.chk_xauto.setChecked(bool(a.get("x_autoscale", True)))
        self.sp_xmin = _dspin(a.get("xmin", 0.0))
        self.sp_xmax = _dspin(a.get("xmax", 1.0))
        xf.addRow("From → To", _range_row(self.chk_xauto, self.sp_xmin, self.sp_xmax))
        self.cb_xscale = _combo(SCALES, a.get("xscale", "linear"))
        xf.addRow("Type", self.cb_xscale)
        self.sp_xmargin = _dspin(_nz(a.get("x_rescale_margin"), 5.0), 0.0, 50.0,
                                 decimals=1, step=1.0)
        xf.addRow("Rescale margin (%)", self.sp_xmargin)
        self.chk_invx = QCheckBox("Reverse")
        self.chk_invx.setChecked(bool(a.get("invert_x", False)))
        xf.addRow("", self.chk_invx)
        self.sp_xmajor = _dspin(a.get("x_major_spacing") or 0.0, 0.0, 1e12, decimals=4)
        xf.addRow("Major ticks: increment (0=auto)", self.sp_xmajor)
        self.chk_xanchor = QCheckBox("Anchor tick")
        self.chk_xanchor.setChecked(a.get("x_anchor_tick") is not None)
        self.sp_xanchor = _dspin(_nz(a.get("x_anchor_tick"), 0.0))
        xf.addRow("", _range_row(self.chk_xanchor, self.sp_xanchor))
        self.sp_xminor = _dspin(a.get("x_minor_spacing") or 0.0, 0.0, 1e12, decimals=4)
        xf.addRow("Minor ticks: increment (0=off)", self.sp_xminor)
        self.sp_xminorcount = _spin(int(a.get("x_minor_count") or 0), 0, 100)
        xf.addRow("Minor ticks: by counts (0=off)", self.sp_xminorcount)
        v.addWidget(gb_x)

        # --- Vertical (Y) ---
        gb_y = QGroupBox("Vertical (Y)")
        yf = QFormLayout(gb_y)
        self.chk_yauto = QCheckBox("Auto")
        self.chk_yauto.setChecked(bool(a.get("y_autoscale", True)))
        self.sp_ymin = _dspin(a.get("ymin", 0.0))
        self.sp_ymax = _dspin(a.get("ymax", 1.0))
        yf.addRow("From → To", _range_row(self.chk_yauto, self.sp_ymin, self.sp_ymax))
        self.cb_yscale = _combo(SCALES, a.get("yscale", "linear"))
        yf.addRow("Type", self.cb_yscale)
        self.sp_ymargin = _dspin(_nz(a.get("y_rescale_margin"), 5.0), 0.0, 50.0,
                                 decimals=1, step=1.0)
        yf.addRow("Rescale margin (%)", self.sp_ymargin)
        self.chk_invy = QCheckBox("Reverse")
        self.chk_invy.setChecked(bool(a.get("invert_y", False)))
        yf.addRow("", self.chk_invy)
        self.sp_ymajor = _dspin(a.get("y_major_spacing") or 0.0, 0.0, 1e12, decimals=4)
        yf.addRow("Major ticks: increment (0=auto)", self.sp_ymajor)
        self.chk_yanchor = QCheckBox("Anchor tick")
        self.chk_yanchor.setChecked(a.get("y_anchor_tick") is not None)
        self.sp_yanchor = _dspin(_nz(a.get("y_anchor_tick"), 0.0))
        yf.addRow("", _range_row(self.chk_yanchor, self.sp_yanchor))
        self.sp_yminor = _dspin(a.get("y_minor_spacing") or 0.0, 0.0, 1e12, decimals=4)
        yf.addRow("Minor ticks: increment (0=off)", self.sp_yminor)
        self.sp_yminorcount = _spin(int(a.get("y_minor_count") or 0), 0, 100)
        yf.addRow("Minor ticks: by counts (0=off)", self.sp_yminorcount)
        v.addWidget(gb_y)

        self.chk_scinote = QCheckBox("Scientific notation on tick labels")
        self.chk_scinote.setChecked(bool(a.get("sci_notation", False)))
        v.addWidget(self.chk_scinote)

        note = QLabel(
            "Major tick positions are anchored so one tick lands exactly on the "
            "Anchor Tick value. \"By counts\" is ignored when a minor increment is set."
        )
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch(1)
        return w

    # ------------------------------------------------------- Ticks & Spines
    def _build_ticks_tab(self, a: Dict[str, Any]) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        gb_tick = QGroupBox("Ticks")
        tf = QFormLayout(gb_tick)
        self.sp_tick_size = _spin(a.get("tick_size", 10), 4, 72)
        self.cb_tickdir = _combo(TICK_DIRECTIONS, a.get("tick_direction", "out"))
        self.sp_ticklength = _dspin(a.get("tick_length", 3.5), 0.0, 20.0, decimals=1, step=0.5)
        self.sp_tickwidth = _dspin(a.get("tick_width", 0.8), 0.0, 5.0, decimals=2, step=0.1)
        self.btn_tickcolor = ColorButton(_hex_to_qcolor(a.get("tick_color", "#3a3f44")))
        self.btn_ticklabelcolor = ColorButton(
            _hex_to_qcolor(a.get("tick_label_color", "#e6e6e6")))
        self.sp_tickxrot = _dspin(a.get("tick_x_rotation", 0.0), -90.0, 90.0, decimals=1, step=5.0)
        self.chk_minorticks = QCheckBox("Show minor ticks")
        self.chk_minorticks.setChecked(bool(a.get("minor_ticks", False)))
        self.chk_mirrorticks = QCheckBox("Mirror ticks (top/right)")
        self.chk_mirrorticks.setChecked(bool(a.get("mirror_ticks", False)))
        tf.addRow("Tick label size", self.sp_tick_size)
        tf.addRow("Tick direction", self.cb_tickdir)
        tf.addRow("Tick length", self.sp_ticklength)
        tf.addRow("Tick width", self.sp_tickwidth)
        tf.addRow("Tick color", self.btn_tickcolor)
        tf.addRow("Tick label color", self.btn_ticklabelcolor)
        tf.addRow("X tick rotation", self.sp_tickxrot)
        tf.addRow("", self.chk_minorticks)
        tf.addRow("", self.chk_mirrorticks)
        v.addWidget(gb_tick)

        gb_spine = QGroupBox("Spines")
        sf = QFormLayout(gb_spine)
        self.chk_spinetop = QCheckBox("Top")
        self.chk_spinetop.setChecked(bool(a.get("spine_top", True)))
        self.chk_spineright = QCheckBox("Right")
        self.chk_spineright.setChecked(bool(a.get("spine_right", True)))
        self.chk_spineleft = QCheckBox("Left")
        self.chk_spineleft.setChecked(bool(a.get("spine_left", True)))
        self.chk_spinebottom = QCheckBox("Bottom")
        self.chk_spinebottom.setChecked(bool(a.get("spine_bottom", True)))
        sf.addRow("Visible sides",
                  _flags_row(self.chk_spinetop, self.chk_spineright,
                             self.chk_spineleft, self.chk_spinebottom))
        v.addWidget(gb_spine)
        v.addStretch(1)
        return w

    # ------------------------------------------------------------ Tick labels
    def _build_tick_labels_tab(self, t: Dict[str, Any]) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        gb_display = QGroupBox("Display")
        form = QFormLayout(gb_display)
        self.chk_ticklabeloverride = QCheckBox("Override tick-label display")
        self.chk_ticklabeloverride.setChecked(bool(t.get("enabled", False)))
        self.cb_ticklabelaxis = _combo(TICK_LABEL_AXES, t.get("axis", "both"))
        self.cb_ticklabelnotation = _combo(TICK_LABEL_NOTATIONS, t.get("notation", "auto"))
        self.chk_ticklabeldecimals = QCheckBox("Set decimal places")
        self.chk_ticklabeldecimals.setChecked(bool(t.get("decimals_enabled", False)))
        self.sp_ticklabeldecimals = _spin(t.get("decimals", 2), 0, 12)
        self.chk_ticklabelthousands = QCheckBox("Use thousands separator")
        self.chk_ticklabelthousands.setChecked(bool(t.get("thousands", False)))
        self.sp_ticklabeldivide = _dspin(
            t.get("divide_by", 1.0),
            -1e12,
            1e12,
            decimals=6,
            step=1.0,
        )
        form.addRow("", self.chk_ticklabeloverride)
        form.addRow("Apply to axis", self.cb_ticklabelaxis)
        form.addRow("Type", self.cb_ticklabelnotation)
        form.addRow("", self.chk_ticklabeldecimals)
        form.addRow("Decimal places", self.sp_ticklabeldecimals)
        form.addRow("", self.chk_ticklabelthousands)
        form.addRow("Divide by factor", self.sp_ticklabeldivide)
        self.ed_ticklabelformula = QLineEdit(str(t.get("formula", "")))
        self.ed_ticklabelformula.setPlaceholderText("e.g. 2 * x")
        form.addRow("Formula", self.ed_ticklabelformula)
        formula_note = QLabel(
            'Example: 2 * x.  "Divide by Factor" is ignored when a Formula is used.'
        )
        formula_note.setWordWrap(True)
        form.addRow("", formula_note)
        v.addWidget(gb_display)

        gb_text = QGroupBox("Text")
        tf = QFormLayout(gb_text)
        self.ed_ticklabelprefix = QLineEdit(str(t.get("prefix", "")))
        self.ed_ticklabelsuffix = QLineEdit(str(t.get("suffix", "")))
        self.chk_ticklabelplus = QCheckBox("Show plus sign for positive values")
        self.chk_ticklabelplus.setChecked(bool(t.get("plus_sign", False)))
        self.chk_ticklabelminus = QCheckBox("Show minus sign for negative values")
        self.chk_ticklabelminus.setChecked(bool(t.get("minus_sign", True)))
        tf.addRow("Prefix", self.ed_ticklabelprefix)
        tf.addRow("Suffix", self.ed_ticklabelsuffix)
        tf.addRow("", self.chk_ticklabelplus)
        tf.addRow("", self.chk_ticklabelminus)
        v.addWidget(gb_text)

        note = QLabel(
            "Examples: Decimal + divide by 1000 turns 2500000 into 2,500.00. "
            "Engineering uses SI-style suffixes such as k, M, u."
        )
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch(1)
        return w

    # ---------------------------------------------------------- Ref. lines
    def _build_reference_lines_tab(self, a: Dict[str, Any]) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        gb_ref = QGroupBox("Reference Lines")
        xf = QFormLayout(gb_ref)
        self.chk_reflineh = QCheckBox("Enable")
        self.sp_reflineh = _dspin(_nz(a.get("refline_h"), 0.0))
        self.chk_reflineh.setChecked(a.get("refline_h") is not None)
        self.ed_reflinehlabel = QLineEdit(str(a.get("refline_h_label", "")))
        self.chk_reflinev = QCheckBox("Enable")
        self.sp_reflinev = _dspin(_nz(a.get("refline_v"), 0.0))
        self.chk_reflinev.setChecked(a.get("refline_v") is not None)
        self.ed_reflinevlabel = QLineEdit(str(a.get("refline_v_label", "")))
        self.btn_reflinecolor = ColorButton(_hex_to_qcolor(a.get("refline_color", "#ff6b6b")))
        self.cb_reflinestyle = _combo(LINE_STYLES, a.get("refline_style", "--"))
        self.sp_reflinewidth = _dspin(a.get("refline_width", 1.2), 0.1, 20.0, decimals=2, step=0.2)
        self.sp_reflinealpha = _dspin(a.get("refline_alpha", 1.0), 0.0, 1.0, decimals=2, step=0.05)
        xf.addRow("Horizontal (y=)", _range_row(self.chk_reflineh, self.sp_reflineh))
        xf.addRow("Horizontal label", self.ed_reflinehlabel)
        xf.addRow("Vertical (x=)", _range_row(self.chk_reflinev, self.sp_reflinev))
        xf.addRow("Vertical label", self.ed_reflinevlabel)
        xf.addRow("Color", self.btn_reflinecolor)
        xf.addRow("Style", self.cb_reflinestyle)
        xf.addRow("Line width", self.sp_reflinewidth)
        xf.addRow("Opacity", self.sp_reflinealpha)
        v.addWidget(gb_ref)

        note = QLabel(
            "Reference lines are refreshed by ID on every Apply, so repeated "
            "Apply/Preset operations do not stack duplicate guide lines."
        )
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch(1)
        return w

    # ------------------------------------------------- Inset & Colorbar
    def _build_inset_colorbar_tab(self, ins: Dict[str, Any], cb: Dict[str, Any]) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        gb_inset = QGroupBox("Zoom inset")
        inf = QFormLayout(gb_inset)
        self.chk_inset = QCheckBox("Show a zoomed inset panel")
        self.chk_inset.setChecked(bool(ins.get("enabled", False)))
        self.sp_insetxmin = _dspin(float(ins.get("xmin", 0.0)))
        self.sp_insetxmax = _dspin(float(ins.get("xmax", 1.0)))
        self.cb_insetloc = _combo(list(INSET_LOCS), ins.get("loc", "upper right"))
        self.sp_insetsize = _dspin(float(ins.get("size", 38.0)), 15.0, 60.0,
                                   decimals=0, step=1.0)
        self.chk_insetbox = QCheckBox("Mark the zoomed region on the main plot")
        self.chk_insetbox.setChecked(bool(ins.get("indicate", True)))
        inf.addRow("", self.chk_inset)
        inf.addRow("X from", self.sp_insetxmin)
        inf.addRow("X to", self.sp_insetxmax)
        inf.addRow("Position", self.cb_insetloc)
        inf.addRow("Size (% of plot)", self.sp_insetsize)
        inf.addRow("", self.chk_insetbox)
        v.addWidget(gb_inset)

        gb_cbar = QGroupBox("Colormap && Colorbar (heatmap / image plots)")
        cf = QFormLayout(gb_cbar)
        self.cb_cmap = _combo(["(keep)"] + list(COLORMAPS), cb.get("cmap") or "(keep)")
        self.chk_cbar = QCheckBox("Show colorbar")
        self.chk_cbar.setChecked(bool(cb.get("enabled", False)))
        self.ed_cbarlabel = QLineEdit(str(cb.get("label", "")))
        self.sp_cbarshrink = _dspin(float(cb.get("shrink", 1.0)), 0.3, 1.0,
                                    decimals=2, step=0.05)
        self.sp_cbarticksize = _dspin(float(cb.get("tick_size", 8.0)), 4.0, 20.0,
                                      decimals=1, step=1.0)
        cf.addRow("Colormap", self.cb_cmap)
        cf.addRow("", self.chk_cbar)
        cf.addRow("Label", self.ed_cbarlabel)
        cf.addRow("Shrink", self.sp_cbarshrink)
        cf.addRow("Tick size", self.sp_cbarticksize)
        v.addWidget(gb_cbar)
        v.addStretch(1)
        return w

    def focus_line(self, index: int) -> None:
        """Open the Lines tab with curve *index* selected (canvas pick-to-edit)."""
        try:
            for t in range(self._tabs.count()):
                if self._tabs.tabText(t).startswith("Lines"):
                    self._tabs.setCurrentIndex(t)
                    break
            if 0 <= index < self.cb_line.count():
                self.cb_line.setCurrentIndex(index)
        except Exception:
            logger.debug("focus_line failed", exc_info=True)

    # ------------------------------------------------- Presets & Templates
    def _build_preset_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        gb_preset = QGroupBox("Journal preset")
        pf = QFormLayout(gb_preset)
        self.cb_preset = QComboBox()
        self.cb_preset.addItems(list(JOURNAL_PRESETS.keys()))
        btn_preset = QPushButton("Apply preset")
        btn_preset.clicked.connect(self._on_apply_preset)
        pf.addRow("Preset", self.cb_preset)
        pf.addRow("", btn_preset)
        v.addWidget(gb_preset)

        # Colorblind-safe scientific palettes — one click recolours every series.
        gb_palette = QGroupBox("Color palette")
        qf = QFormLayout(gb_palette)
        self._palette_keep = "— keep colors —"
        self._palette_line_width = None
        self.cb_palette = QComboBox()
        self.cb_palette.addItem(self._palette_keep)
        self.cb_palette.addItems(list_palettes())
        btn_palette = QPushButton("Recolor series")
        btn_palette.clicked.connect(self._on_apply)
        qf.addRow("Palette", self.cb_palette)
        qf.addRow("", btn_palette)
        v.addWidget(gb_palette)

        gb_tpl = QGroupBox("My templates")
        tf = QFormLayout(gb_tpl)
        self.cb_template = QComboBox()
        self.btn_load_template = QPushButton("Load template")
        self.btn_load_template.clicked.connect(
            lambda: self._template_names and self.load_template_requested.emit(
                self.cb_template.currentText()))
        self.btn_delete_template = QPushButton("Delete template")
        self.btn_delete_template.clicked.connect(
            lambda: self._template_names and self.delete_template_requested.emit(
                self.cb_template.currentText()))
        self.ed_tplname = QLineEdit()
        self.ed_tplname.setPlaceholderText("template name…")
        btn_save = QPushButton("Save current as template")
        btn_save.clicked.connect(
            lambda: self.ed_tplname.text().strip()
            and self.save_template_requested.emit(self.ed_tplname.text().strip()))
        tf.addRow("Template", self.cb_template)
        tf.addRow("", _flags_row(self.btn_load_template, self.btn_delete_template))
        tf.addRow("Save as", self.ed_tplname)
        tf.addRow("", btn_save)
        v.addWidget(gb_tpl)
        v.addStretch(1)
        self.set_template_names(self._template_names)
        return w

    def _on_apply_preset(self) -> None:
        """Merge the selected journal preset into the current widgets."""
        from core.plot_style import get_preset_style
        preset = get_preset_style(self.cb_preset.currentText())
        # Palette + line width ride along with the preset but are applied as a
        # recolour action, not as style controls — pull them out first.
        palette_name = preset.pop("palette", None)
        line_width = preset.pop("line_width", None)
        self._loading = True
        try:
            self.load_style_into_controls(preset)
            if palette_name:
                index = self.cb_palette.findText(palette_name)
                if index >= 0:
                    self.cb_palette.setCurrentIndex(index)
                self._palette_line_width = line_width
        finally:
            self._loading = False
        self._on_apply()  # apply the whole preset in one redraw

    def set_template_names(self, names: List[str]) -> None:
        self._template_names = list(names or [])
        if not hasattr(self, "cb_template"):
            return
        current = self.cb_template.currentText()
        self.cb_template.blockSignals(True)
        self.cb_template.clear()
        self.cb_template.addItems(self._template_names)
        if current in self._template_names:
            self.cb_template.setCurrentText(current)
        self.cb_template.blockSignals(False)
        has_templates = bool(self._template_names)
        if hasattr(self, "btn_load_template"):
            self.btn_load_template.setEnabled(has_templates)
        if hasattr(self, "btn_delete_template"):
            self.btn_delete_template.setEnabled(has_templates)

    def load_style_into_controls(self, style: Dict[str, Any]) -> None:
        a = style.get("axes", {})
        if "title" in a:
            self.ed_title.setText(str(a["title"]))
        if "title_size" in a:
            self.sp_title_size.setValue(int(round(float(a["title_size"]))))
        if "title_color" in a:
            self.btn_titlecolor.setColor(_hex_to_qcolor(a["title_color"]))
        if "title_bold" in a:
            self.chk_titlebold.setChecked(bool(a["title_bold"]))
        if "title_italic" in a:
            self.chk_titleital.setChecked(bool(a["title_italic"]))
        if "xlabel" in a:
            self.ed_xlabel.setText(str(a["xlabel"]))
        if "ylabel" in a:
            self.ed_ylabel.setText(str(a["ylabel"]))
        if "label_size" in a:
            self.sp_label_size.setValue(int(round(float(a["label_size"]))))
        if "label_color" in a:
            self.btn_labelcolor.setColor(_hex_to_qcolor(a["label_color"]))
        if "label_bold" in a:
            self.chk_labelbold.setChecked(bool(a["label_bold"]))
        if "font_family" in a:
            _set_combo(self.cb_fontfamily, str(a["font_family"]))
        if "label_pad" in a:
            self.sp_labelpad.setValue(float(a["label_pad"]))
        if "tick_size" in a:
            self.sp_tick_size.setValue(int(round(float(a["tick_size"]))))
        if "tick_direction" in a:
            _set_combo(self.cb_tickdir, str(a["tick_direction"]))
        if "tick_length" in a:
            self.sp_ticklength.setValue(float(a["tick_length"]))
        if "tick_width" in a:
            self.sp_tickwidth.setValue(float(a["tick_width"]))
        if "tick_color" in a:
            self.btn_tickcolor.setColor(_hex_to_qcolor(a["tick_color"]))
        if "tick_label_color" in a:
            self.btn_ticklabelcolor.setColor(_hex_to_qcolor(a["tick_label_color"]))
        if "tick_x_rotation" in a:
            self.sp_tickxrot.setValue(float(a["tick_x_rotation"]))
        if "minor_ticks" in a:
            self.chk_minorticks.setChecked(bool(a["minor_ticks"]))
        if "mirror_ticks" in a:
            self.chk_mirrorticks.setChecked(bool(a["mirror_ticks"]))
        if "sci_notation" in a:
            self.chk_scinote.setChecked(bool(a["sci_notation"]))
        if "x_autoscale" in a:
            self.chk_xauto.setChecked(bool(a["x_autoscale"]))
        if "xmin" in a:
            self.sp_xmin.setValue(float(a["xmin"]))
        if "xmax" in a:
            self.sp_xmax.setValue(float(a["xmax"]))
        if "y_autoscale" in a:
            self.chk_yauto.setChecked(bool(a["y_autoscale"]))
        if "ymin" in a:
            self.sp_ymin.setValue(float(a["ymin"]))
        if "ymax" in a:
            self.sp_ymax.setValue(float(a["ymax"]))
        if "xscale" in a:
            _set_combo(self.cb_xscale, str(a["xscale"]))
        if "yscale" in a:
            _set_combo(self.cb_yscale, str(a["yscale"]))
        if "invert_x" in a:
            self.chk_invx.setChecked(bool(a["invert_x"]))
        if "invert_y" in a:
            self.chk_invy.setChecked(bool(a["invert_y"]))
        if "x_major_spacing" in a:
            self.sp_xmajor.setValue(_nz(a["x_major_spacing"]))
        if "x_minor_spacing" in a:
            self.sp_xminor.setValue(_nz(a["x_minor_spacing"]))
        if "y_major_spacing" in a:
            self.sp_ymajor.setValue(_nz(a["y_major_spacing"]))
        if "y_minor_spacing" in a:
            self.sp_yminor.setValue(_nz(a["y_minor_spacing"]))
        if "x_anchor_tick" in a:
            self.chk_xanchor.setChecked(a["x_anchor_tick"] is not None)
            self.sp_xanchor.setValue(_nz(a["x_anchor_tick"]))
        if "y_anchor_tick" in a:
            self.chk_yanchor.setChecked(a["y_anchor_tick"] is not None)
            self.sp_yanchor.setValue(_nz(a["y_anchor_tick"]))
        if "x_minor_count" in a:
            self.sp_xminorcount.setValue(int(a["x_minor_count"] or 0))
        if "y_minor_count" in a:
            self.sp_yminorcount.setValue(int(a["y_minor_count"] or 0))
        if "x_rescale_margin" in a:
            self.sp_xmargin.setValue(float(a["x_rescale_margin"]))
        if "y_rescale_margin" in a:
            self.sp_ymargin.setValue(float(a["y_rescale_margin"]))
        if "spine_color" in a:
            self.btn_spinecolor.setColor(_hex_to_qcolor(a["spine_color"]))
        if "spine_width" in a:
            self.sp_spinewidth.setValue(float(a["spine_width"]))
        if "spine_top" in a:
            self.chk_spinetop.setChecked(bool(a["spine_top"]))
        if "spine_right" in a:
            self.chk_spineright.setChecked(bool(a["spine_right"]))
        if "spine_left" in a:
            self.chk_spineleft.setChecked(bool(a["spine_left"]))
        if "spine_bottom" in a:
            self.chk_spinebottom.setChecked(bool(a["spine_bottom"]))
        if "refline_h" in a:
            self.chk_reflineh.setChecked(a["refline_h"] is not None)
            self.sp_reflineh.setValue(_nz(a["refline_h"]))
        if "refline_v" in a:
            self.chk_reflinev.setChecked(a["refline_v"] is not None)
            self.sp_reflinev.setValue(_nz(a["refline_v"]))
        if "refline_h_label" in a:
            self.ed_reflinehlabel.setText(str(a["refline_h_label"]))
        if "refline_v_label" in a:
            self.ed_reflinevlabel.setText(str(a["refline_v_label"]))
        if "refline_color" in a:
            self.btn_reflinecolor.setColor(_hex_to_qcolor(a["refline_color"]))
        if "refline_style" in a:
            _set_combo(self.cb_reflinestyle, str(a["refline_style"]))
        if "refline_width" in a:
            self.sp_reflinewidth.setValue(float(a["refline_width"]))
        if "refline_alpha" in a:
            self.sp_reflinealpha.setValue(float(a["refline_alpha"]))

        t = style.get("tick_labels", {})
        if "enabled" in t:
            self.chk_ticklabeloverride.setChecked(bool(t["enabled"]))
        if "axis" in t:
            _set_combo(self.cb_ticklabelaxis, str(t["axis"]))
        if "notation" in t:
            _set_combo(self.cb_ticklabelnotation, str(t["notation"]))
        if "decimals_enabled" in t:
            self.chk_ticklabeldecimals.setChecked(bool(t["decimals_enabled"]))
        if "decimals" in t:
            self.sp_ticklabeldecimals.setValue(int(t["decimals"]))
        if "thousands" in t:
            self.chk_ticklabelthousands.setChecked(bool(t["thousands"]))
        if "divide_by" in t:
            self.sp_ticklabeldivide.setValue(float(t["divide_by"]))
        if "formula" in t:
            self.ed_ticklabelformula.setText(str(t["formula"]))
        if "prefix" in t:
            self.ed_ticklabelprefix.setText(str(t["prefix"]))
        if "suffix" in t:
            self.ed_ticklabelsuffix.setText(str(t["suffix"]))
        if "plus_sign" in t:
            self.chk_ticklabelplus.setChecked(bool(t["plus_sign"]))
        if "minus_sign" in t:
            self.chk_ticklabelminus.setChecked(bool(t["minus_sign"]))

        g = style.get("grid", {})
        if "major" in g:
            self.chk_grid.setChecked(bool(g["major"]))
        if "minor" in g:
            self.chk_gridminor.setChecked(bool(g["minor"]))
        if "axis" in g:
            _set_combo(self.cb_gridaxis, str(g["axis"]))
        if "color" in g:
            self.btn_gridcolor.setColor(_hex_to_qcolor(g["color"]))
        if "linestyle" in g:
            _set_combo(self.cb_gridstyle, str(g["linestyle"]))
        if "linewidth" in g:
            self.sp_gridwidth.setValue(float(g["linewidth"]))
        if "alpha" in g:
            self.sp_gridalpha.setValue(float(g["alpha"]))
        if "minor_color" in g:
            self.btn_gridmincolor.setColor(_hex_to_qcolor(g["minor_color"]))
        if "minor_linestyle" in g:
            _set_combo(self.cb_gridminstyle, str(g["minor_linestyle"]))
        if "minor_linewidth" in g:
            self.sp_gridminwidth.setValue(float(g["minor_linewidth"]))
        if "minor_alpha" in g:
            self.sp_gridminalpha.setValue(float(g["minor_alpha"]))

        leg = style.get("legend", {})
        if "visible" in leg:
            self.chk_legend.setChecked(bool(leg["visible"]))
        if "loc" in leg:
            _set_combo(self.cb_legloc, str(leg["loc"]))
        if "fontsize" in leg:
            self.sp_legsize.setValue(int(round(float(leg["fontsize"]))))
        if "ncol" in leg:
            self.sp_legcol.setValue(int(leg["ncol"]))
        if "frame" in leg:
            self.chk_legframe.setChecked(bool(leg["frame"]))
        if "facecolor" in leg:
            self.btn_legface.setColor(_hex_to_qcolor(leg["facecolor"]))
        if "edgecolor" in leg:
            self.btn_legedge.setColor(_hex_to_qcolor(leg["edgecolor"]))
        if "alpha" in leg:
            self.sp_legalpha.setValue(float(leg["alpha"]))
        if "shadow" in leg:
            self.chk_legshadow.setChecked(bool(leg["shadow"]))
        if "fancybox" in leg:
            self.chk_leground.setChecked(bool(leg["fancybox"]))
        if "title" in leg:
            self.ed_legtitle.setText(str(leg["title"]))
        if "title_size" in leg:
            self.sp_legtitlesize.setValue(float(leg["title_size"]))
        if "columnspacing" in leg:
            self.sp_legcolspacing.setValue(float(leg["columnspacing"]))
        if "labelspacing" in leg:
            self.sp_leglabelspacing.setValue(float(leg["labelspacing"]))
        if "markerscale" in leg:
            self.sp_legmarkerscale.setValue(float(leg["markerscale"]))
        if "borderpad" in leg:
            self.sp_legborderpad.setValue(float(leg["borderpad"]))
        if "handlelength" in leg:
            self.sp_leghandlelen.setValue(float(leg["handlelength"]))
        if "draggable" in leg:
            self.chk_legdraggable.setChecked(bool(leg["draggable"]))

        f = style.get("figure", {})
        if "facecolor" in f:
            self.btn_axesbg.setColor(_hex_to_qcolor(f["facecolor"]))
        if "fig_facecolor" in f:
            self.btn_figbg.setColor(_hex_to_qcolor(f["fig_facecolor"]))
        if "width_in" in f:
            self.sp_figw.setValue(float(f["width_in"]))
        if "height_in" in f:
            self.sp_figh.setValue(float(f["height_in"]))
        if "dpi" in f:
            self.sp_figdpi.setValue(int(round(float(f["dpi"]))))

        effects = style.get("effects", {})
        if "axes_shadow" in effects:
            self.chk_axesshadow.setChecked(bool(effects["axes_shadow"]))
        if "shadow_color" in effects:
            self.btn_shadowcolor.setColor(_hex_to_qcolor(effects["shadow_color"]))
        if "shadow_alpha" in effects:
            self.sp_shadowalpha.setValue(float(effects["shadow_alpha"]))
        if "shadow_offset_x" in effects:
            self.sp_shadowx.setValue(float(effects["shadow_offset_x"]))
        if "shadow_offset_y" in effects:
            self.sp_shadowy.setValue(float(effects["shadow_offset_y"]))

        ins = style.get("inset", {})
        if "enabled" in ins:
            self.chk_inset.setChecked(bool(ins["enabled"]))
        if "xmin" in ins:
            self.sp_insetxmin.setValue(float(ins["xmin"]))
        if "xmax" in ins:
            self.sp_insetxmax.setValue(float(ins["xmax"]))
        if "loc" in ins:
            _set_combo(self.cb_insetloc, ins["loc"])
        if "size" in ins:
            self.sp_insetsize.setValue(float(ins["size"]))
        if "indicate" in ins:
            self.chk_insetbox.setChecked(bool(ins["indicate"]))

        cbar = style.get("colorbar", {})
        if "enabled" in cbar:
            self.chk_cbar.setChecked(bool(cbar["enabled"]))
        if "cmap" in cbar:
            _set_combo(self.cb_cmap, cbar["cmap"] or "(keep)")
        if "label" in cbar:
            self.ed_cbarlabel.setText(str(cbar["label"]))
        if "shrink" in cbar:
            self.sp_cbarshrink.setValue(float(cbar["shrink"]))
        if "tick_size" in cbar:
            self.sp_cbarticksize.setValue(float(cbar["tick_size"]))

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
        self.cb_gridaxis = _combo(GRID_AXES, g.get("axis", "both"))
        self.btn_gridcolor = ColorButton(_hex_to_qcolor(g.get("color", "#3a3f44")))
        self.cb_gridstyle = _combo(LINE_STYLES, g.get("linestyle", "-"))
        self.sp_gridwidth = _dspin(g.get("linewidth", 0.8), 0.0, 5.0, decimals=2, step=0.1)
        self.sp_gridalpha = _dspin(g.get("alpha", 0.3), 0.0, 1.0, decimals=2, step=0.05)
        self.btn_gridmincolor = ColorButton(_hex_to_qcolor(g.get("minor_color", "#3a3f44")))
        self.cb_gridminstyle = _combo(LINE_STYLES, g.get("minor_linestyle", ":"))
        self.sp_gridminwidth = _dspin(g.get("minor_linewidth", 0.5), 0.0, 5.0, decimals=2, step=0.1)
        self.sp_gridminalpha = _dspin(g.get("minor_alpha", 0.15), 0.0, 1.0, decimals=2, step=0.05)
        gf.addRow("", self.chk_grid)
        gf.addRow("", self.chk_gridminor)
        gf.addRow("Grid axis", self.cb_gridaxis)
        gf.addRow("Grid color", self.btn_gridcolor)
        gf.addRow("Grid style", self.cb_gridstyle)
        gf.addRow("Grid width", self.sp_gridwidth)
        gf.addRow("Grid alpha", self.sp_gridalpha)
        gf.addRow("Minor color", self.btn_gridmincolor)
        gf.addRow("Minor style", self.cb_gridminstyle)
        gf.addRow("Minor width", self.sp_gridminwidth)
        gf.addRow("Minor alpha", self.sp_gridminalpha)
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
        self.btn_legface = ColorButton(_hex_to_qcolor(leg.get("facecolor", "#1e2126")))
        self.btn_legedge = ColorButton(_hex_to_qcolor(leg.get("edgecolor", "#3a3f44")))
        self.sp_legalpha = _dspin(leg.get("alpha", 1.0), 0.0, 1.0, decimals=2, step=0.05)
        self.chk_legshadow = QCheckBox("Drop shadow")
        self.chk_legshadow.setChecked(bool(leg.get("shadow", False)))
        self.chk_leground = QCheckBox("Rounded corners")
        self.chk_leground.setChecked(bool(leg.get("fancybox", True)))
        self.chk_legdraggable = QCheckBox("Drag directly on graph")
        self.chk_legdraggable.setChecked(bool(leg.get("draggable", True)))
        self.ed_legtitle = QLineEdit(str(leg.get("title", "")))
        self.sp_legtitlesize = _dspin(leg.get("title_size", 10.0), 4.0, 40.0, decimals=1, step=1.0)
        self.sp_legcolspacing = _dspin(leg.get("columnspacing", 2.0), 0.0, 10.0, decimals=2, step=0.25)
        self.sp_leglabelspacing = _dspin(leg.get("labelspacing", 0.5), 0.0, 5.0, decimals=2, step=0.1)
        self.sp_legmarkerscale = _dspin(leg.get("markerscale", 1.0), 0.1, 5.0, decimals=2, step=0.1)
        self.sp_legborderpad = _dspin(leg.get("borderpad", 0.4), 0.0, 5.0, decimals=2, step=0.1)
        self.sp_leghandlelen = _dspin(leg.get("handlelength", 2.0), 0.0, 10.0, decimals=2, step=0.25)
        lf.addRow("", self.chk_legend)
        lf.addRow("Location", self.cb_legloc)
        lf.addRow("Font size", self.sp_legsize)
        lf.addRow("Columns", self.sp_legcol)
        lf.addRow("Title", self.ed_legtitle)
        lf.addRow("Title size", self.sp_legtitlesize)
        lf.addRow("", self.chk_legframe)
        lf.addRow("Fill", self.btn_legface)
        lf.addRow("Border", self.btn_legedge)
        lf.addRow("Opacity", self.sp_legalpha)
        lf.addRow("", self.chk_legshadow)
        lf.addRow("", self.chk_leground)
        lf.addRow("", self.chk_legdraggable)
        lf.addRow("Column spacing", self.sp_legcolspacing)
        lf.addRow("Label spacing", self.sp_leglabelspacing)
        lf.addRow("Marker scale", self.sp_legmarkerscale)
        lf.addRow("Border pad", self.sp_legborderpad)
        lf.addRow("Handle length", self.sp_leghandlelen)
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
        self.cb_drawstyle = _combo(DRAW_STYLES, "default")
        self.cb_marker = _combo(MARKERS, "None")
        self.sp_markersize = _dspin(6.0, 0.0, 50.0, decimals=1, step=1.0)
        self.btn_mfc = ColorButton(QColor("#000000"))
        self.btn_mec = ColorButton(QColor("#000000"))
        self.sp_mew = _dspin(1.0, 0.0, 5.0, decimals=2, step=0.1)
        self.cb_fillstyle = _combo(FILL_STYLES, "full")
        self.sp_zorder = _dspin(2.0, 0.0, 20.0, decimals=1, step=1.0)
        self.sp_linealpha = _dspin(1.0, 0.0, 1.0, decimals=2, step=0.05)
        self.chk_lineglow = QCheckBox("Glow")
        self.btn_lineglow = ColorButton(QColor("#4F9CF9"))
        self.sp_lineglowwidth = _dspin(5.0, 0.0, 30.0, decimals=1, step=0.5)
        self.sp_lineglowalpha = _dspin(0.35, 0.0, 1.0, decimals=2, step=0.05)
        self.chk_lineshadow = QCheckBox("Drop shadow")
        self.sp_lineshadowalpha = _dspin(0.25, 0.0, 1.0, decimals=2, step=0.05)
        form.addRow("Label", self.ed_linelabel)
        form.addRow("Color", self.btn_linecolor)
        form.addRow("Line width", self.sp_linewidth)
        form.addRow("Line style", self.cb_linestyle)
        form.addRow("Draw style", self.cb_drawstyle)
        form.addRow("Marker", self.cb_marker)
        form.addRow("Marker size", self.sp_markersize)
        form.addRow("Marker fill", self.btn_mfc)
        form.addRow("Marker edge", self.btn_mec)
        form.addRow("Marker edge width", self.sp_mew)
        form.addRow("Fill style", self.cb_fillstyle)
        form.addRow("Z-order", self.sp_zorder)
        form.addRow("Opacity", self.sp_linealpha)
        form.addRow("", self.chk_lineglow)
        form.addRow("Glow color", self.btn_lineglow)
        form.addRow("Glow width", self.sp_lineglowwidth)
        form.addRow("Glow opacity", self.sp_lineglowalpha)
        form.addRow("", self.chk_lineshadow)
        form.addRow("Shadow opacity", self.sp_lineshadowalpha)
        v.addLayout(form)

        # --- Fill under / between curves ---
        gb_fill = QGroupBox("Area fill")
        ff = QFormLayout(gb_fill)
        self.cb_linefill = _combo(list(FILL_MODES), "none")
        self.chk_fillauto = QCheckBox("Match line color")
        self.chk_fillauto.setChecked(True)
        self.btn_fillcolor = ColorButton(QColor("#4F9CF9"))
        self.sp_fillalpha = _dspin(0.25, 0.02, 1.0, decimals=2, step=0.05)
        self.cb_fillhatch = _combo(list(HATCH_PATTERNS), "")
        self.chk_fillgradient = QCheckBox("Gradient (fade to baseline)")
        ff.addRow("Fill", self.cb_linefill)
        ff.addRow("", _flags_row(self.chk_fillauto))
        ff.addRow("Fill color", self.btn_fillcolor)
        ff.addRow("Fill opacity", self.sp_fillalpha)
        ff.addRow("Pattern", self.cb_fillhatch)
        ff.addRow("", _flags_row(self.chk_fillgradient))
        v.addWidget(gb_fill)

        # --- Drop lines (vertical guides from each point to the baseline) ---
        gb_drop = QGroupBox("Drop lines")
        df = QFormLayout(gb_drop)
        self.chk_droplines = QCheckBox("Show drop lines to baseline")
        self.chk_dropauto = QCheckBox("Match line color")
        self.chk_dropauto.setChecked(True)
        self.btn_dropcolor = ColorButton(QColor("#888888"))
        self.cb_dropstyle = _combo(list(LINE_STYLES), "-")
        self.sp_dropwidth = _dspin(0.8, 0.2, 8.0, decimals=1, step=0.2)
        df.addRow("", self.chk_droplines)
        df.addRow("", _flags_row(self.chk_dropauto))
        df.addRow("Color", self.btn_dropcolor)
        df.addRow("Style", self.cb_dropstyle)
        df.addRow("Width", self.sp_dropwidth)
        v.addWidget(gb_drop)

        # --- Error bars (constant or percent, as decoration) ---
        gb_err = QGroupBox("Error bars (Y)")
        ef = QFormLayout(gb_err)
        self.cb_errmode = _combo(list(ERRORBAR_MODES), "none")
        self.sp_errvalue = _dspin(5.0, 0.0, 1e9, decimals=3, step=1.0)
        self.sp_errcap = _dspin(3.0, 0.0, 20.0, decimals=1, step=0.5)
        ef.addRow("Mode", self.cb_errmode)
        ef.addRow("Value (abs or %)", self.sp_errvalue)
        ef.addRow("Cap size", self.sp_errcap)
        v.addWidget(gb_err)

        # --- Data point value labels ---
        gb_vlab = QGroupBox("Value labels")
        vf = QFormLayout(gb_vlab)
        self.chk_vlabels = QCheckBox("Label data points")
        self.ed_vfmt = QLineEdit("%.3g")
        self.sp_vevery = _spin(1, 1, 1000)
        self.sp_vsize = _dspin(8.0, 4.0, 24.0, decimals=1, step=1.0)
        vf.addRow("", self.chk_vlabels)
        vf.addRow("Format", self.ed_vfmt)
        vf.addRow("Every Nth point", self.sp_vevery)
        vf.addRow("Font size", self.sp_vsize)
        v.addWidget(gb_vlab)

        # --- Mark & label max / min ---
        gb_ext = QGroupBox("Max / Min labels")
        xf = QFormLayout(gb_ext)
        self.chk_extrema = QCheckBox("Mark and label the peak and valley")
        self.ed_extfmt = QLineEdit("%.3g")
        self.sp_extsize = _dspin(9.0, 4.0, 24.0, decimals=1, step=1.0)
        xf.addRow("", self.chk_extrema)
        xf.addRow("Format", self.ed_extfmt)
        xf.addRow("Font size", self.sp_extsize)
        v.addWidget(gb_ext)
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
        color = d.get("color", "#000000")
        self.ed_linelabel.setText(str(d.get("label", "")))
        self.btn_linecolor.setColor(_hex_to_qcolor(color))
        self.sp_linewidth.setValue(float(d.get("linewidth", 1.5)))
        _set_combo(self.cb_linestyle, d.get("linestyle", "-"))
        _set_combo(self.cb_drawstyle, d.get("drawstyle", "default"))
        _set_combo(self.cb_marker, d.get("marker", "None"))
        self.sp_markersize.setValue(float(d.get("markersize", 6.0)))
        self.btn_mfc.setColor(_hex_to_qcolor(d.get("markerfacecolor", color)))
        self.btn_mec.setColor(_hex_to_qcolor(d.get("markeredgecolor", color)))
        self.sp_mew.setValue(float(d.get("markeredgewidth", 1.0)))
        _set_combo(self.cb_fillstyle, d.get("fillstyle", "full"))
        self.sp_zorder.setValue(float(d.get("zorder", 2.0)))
        self.sp_linealpha.setValue(float(d.get("alpha", 1.0)))
        self.chk_lineglow.setChecked(bool(d.get("glow", False)))
        self.btn_lineglow.setColor(_hex_to_qcolor(d.get("glow_color", color)))
        self.sp_lineglowwidth.setValue(float(d.get("glow_width", 5.0)))
        self.sp_lineglowalpha.setValue(float(d.get("glow_alpha", 0.35)))
        self.chk_lineshadow.setChecked(bool(d.get("shadow", False)))
        self.sp_lineshadowalpha.setValue(float(d.get("shadow_alpha", 0.25)))
        _set_combo(self.cb_linefill, d.get("fill", "none"))
        fill_color = d.get("fill_color") or ""
        self.chk_fillauto.setChecked(not fill_color)
        self.btn_fillcolor.setColor(_hex_to_qcolor(fill_color or color))
        self.sp_fillalpha.setValue(float(d.get("fill_alpha", 0.25)))
        _set_combo(self.cb_fillhatch, d.get("fill_hatch", ""))
        self.chk_fillgradient.setChecked(bool(d.get("fill_gradient", False)))
        drop_color = d.get("drop_line_color") or ""
        self.chk_droplines.setChecked(bool(d.get("drop_lines", False)))
        self.chk_dropauto.setChecked(not drop_color)
        self.btn_dropcolor.setColor(_hex_to_qcolor(drop_color or color))
        _set_combo(self.cb_dropstyle, d.get("drop_line_style", "-"))
        self.sp_dropwidth.setValue(float(d.get("drop_line_width", 0.8)))
        _set_combo(self.cb_errmode, d.get("errorbar_mode", "none"))
        self.sp_errvalue.setValue(float(d.get("errorbar_value", 5.0)))
        self.sp_errcap.setValue(float(d.get("errorbar_capsize", 3.0)))
        self.chk_vlabels.setChecked(bool(d.get("value_labels", False)))
        self.ed_vfmt.setText(str(d.get("value_labels_fmt", "%.3g")))
        self.sp_vevery.setValue(int(d.get("value_labels_every", 1) or 1))
        self.sp_vsize.setValue(float(d.get("value_labels_size", 8.0)))
        self.chk_extrema.setChecked(bool(d.get("label_extrema", False)))
        self.ed_extfmt.setText(str(d.get("extrema_fmt", "%.3g")))
        self.sp_extsize.setValue(float(d.get("extrema_size", 9.0)))

    def _store_line(self, i: int) -> None:
        prev = self._line_styles[i] if i < len(self._line_styles) else {}
        self._line_styles[i] = {
            "label": self.ed_linelabel.text(),
            "color": self.btn_linecolor.color().name(),
            "linewidth": self.sp_linewidth.value(),
            "linestyle": self.cb_linestyle.currentText(),
            "drawstyle": self.cb_drawstyle.currentText(),
            "marker": self.cb_marker.currentText(),
            "markersize": self.sp_markersize.value(),
            "markerfacecolor": self.btn_mfc.color().name(),
            "markeredgecolor": self.btn_mec.color().name(),
            "markeredgewidth": self.sp_mew.value(),
            "fillstyle": self.cb_fillstyle.currentText(),
            "zorder": self.sp_zorder.value(),
            "alpha": self.sp_linealpha.value(),
            "glow": self.chk_lineglow.isChecked(),
            "glow_color": self.btn_lineglow.color().name(),
            "glow_width": self.sp_lineglowwidth.value(),
            "glow_alpha": self.sp_lineglowalpha.value(),
            "shadow": self.chk_lineshadow.isChecked(),
            "shadow_alpha": self.sp_lineshadowalpha.value(),
            "shadow_offset_x": prev.get("shadow_offset_x", 1.5),
            "shadow_offset_y": prev.get("shadow_offset_y", 1.5),
            "fill": self.cb_linefill.currentText(),
            "fill_color": (
                "" if self.chk_fillauto.isChecked()
                else self.btn_fillcolor.color().name()
            ),
            "fill_alpha": self.sp_fillalpha.value(),
            "fill_hatch": self.cb_fillhatch.currentText(),
            "fill_gradient": self.chk_fillgradient.isChecked(),
            "drop_lines": self.chk_droplines.isChecked(),
            "drop_line_color": (
                "" if self.chk_dropauto.isChecked()
                else self.btn_dropcolor.color().name()
            ),
            "drop_line_style": self.cb_dropstyle.currentText(),
            "drop_line_width": self.sp_dropwidth.value(),
            "errorbar_mode": self.cb_errmode.currentText(),
            "errorbar_value": self.sp_errvalue.value(),
            "errorbar_capsize": self.sp_errcap.value(),
            "errorbar_alpha": prev.get("errorbar_alpha", 0.9),
            "value_labels": self.chk_vlabels.isChecked(),
            "value_labels_fmt": self.ed_vfmt.text().strip() or "%.3g",
            "value_labels_every": self.sp_vevery.value(),
            "value_labels_size": self.sp_vsize.value(),
            "label_extrema": self.chk_extrema.isChecked(),
            "extrema_fmt": self.ed_extfmt.text().strip() or "%.3g",
            "extrema_size": self.sp_extsize.value(),
        }

    def _on_line_changed(self, i: int) -> None:
        # Switching which curve is shown just repopulates controls — it must not
        # trigger a live redraw (nothing on the graph actually changed).
        self._store_line(self._current_line)
        self._current_line = i
        self._loading = True
        try:
            self._load_line(i)
        finally:
            self._loading = False

    # ---------------------------------------------------------------- Figure
    def _build_figure_tab(self, f: Dict[str, Any], a: Dict[str, Any], effects: Dict[str, Any]) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.btn_axesbg = ColorButton(_hex_to_qcolor(f.get("facecolor", "#1e2126")))
        self.btn_figbg = ColorButton(_hex_to_qcolor(f.get("fig_facecolor", "#1e2126")))
        self.sp_figw = _dspin(f.get("width_in", 6.4), 0.5, 40.0, decimals=2, step=0.25)
        self.sp_figh = _dspin(f.get("height_in", 4.8), 0.5, 40.0, decimals=2, step=0.25)
        self.sp_figdpi = _spin(f.get("dpi", 100), 30, 1200)
        self.btn_spinecolor = ColorButton(_hex_to_qcolor(a.get("spine_color", "#3a3f44")))
        self.sp_spinewidth = _dspin(a.get("spine_width", 1.0), 0.0, 20.0, decimals=2, step=0.25)
        self.chk_axesshadow = QCheckBox("Axes drop shadow")
        self.chk_axesshadow.setChecked(bool(effects.get("axes_shadow", False)))
        self.btn_shadowcolor = ColorButton(_hex_to_qcolor(effects.get("shadow_color", "#000000")))
        self.sp_shadowalpha = _dspin(effects.get("shadow_alpha", 0.25), 0.0, 1.0, decimals=2, step=0.05)
        self.sp_shadowx = _dspin(effects.get("shadow_offset_x", 3.0), -30.0, 30.0, decimals=1, step=0.5)
        self.sp_shadowy = _dspin(effects.get("shadow_offset_y", 3.0), -30.0, 30.0, decimals=1, step=0.5)
        form.addRow("Axes background", self.btn_axesbg)
        form.addRow("Figure background", self.btn_figbg)
        form.addRow("Axes border", self.btn_spinecolor)
        form.addRow("Border width", self.sp_spinewidth)
        form.addRow("", self.chk_axesshadow)
        form.addRow("Shadow color", self.btn_shadowcolor)
        form.addRow("Shadow opacity", self.sp_shadowalpha)
        form.addRow("Shadow X offset", self.sp_shadowx)
        form.addRow("Shadow Y offset", self.sp_shadowy)
        form.addRow("Width (in)", self.sp_figw)
        form.addRow("Height (in)", self.sp_figh)
        form.addRow("DPI", self.sp_figdpi)
        return w

    # ------------------------------------------------------------------ read
    def get_style(self) -> Dict[str, Any]:
        return {
            "axes": {
                "title": self.ed_title.text(),
                "title_size": self.sp_title_size.value(),
                "title_color": self.btn_titlecolor.color().name(),
                "title_bold": self.chk_titlebold.isChecked(),
                "title_italic": self.chk_titleital.isChecked(),
                "xlabel": self.ed_xlabel.text(),
                "ylabel": self.ed_ylabel.text(),
                "label_size": self.sp_label_size.value(),
                "label_color": self.btn_labelcolor.color().name(),
                "label_bold": self.chk_labelbold.isChecked(),
                "font_family": self.cb_fontfamily.currentText(),
                "label_pad": self.sp_labelpad.value(),
                "tick_size": self.sp_tick_size.value(),
                "tick_direction": self.cb_tickdir.currentText(),
                "tick_length": self.sp_ticklength.value(),
                "tick_width": self.sp_tickwidth.value(),
                "tick_color": self.btn_tickcolor.color().name(),
                "tick_label_color": self.btn_ticklabelcolor.color().name(),
                "tick_x_rotation": self.sp_tickxrot.value(),
                "minor_ticks": self.chk_minorticks.isChecked(),
                "mirror_ticks": self.chk_mirrorticks.isChecked(),
                "sci_notation": self.chk_scinote.isChecked(),
                "x_autoscale": self.chk_xauto.isChecked(),
                "xmin": self.sp_xmin.value(), "xmax": self.sp_xmax.value(),
                "y_autoscale": self.chk_yauto.isChecked(),
                "ymin": self.sp_ymin.value(), "ymax": self.sp_ymax.value(),
                "xscale": self.cb_xscale.currentText(),
                "yscale": self.cb_yscale.currentText(),
                "invert_x": self.chk_invx.isChecked(),
                "invert_y": self.chk_invy.isChecked(),
                "x_major_spacing": self.sp_xmajor.value() or None,
                "x_minor_spacing": self.sp_xminor.value() or None,
                "y_major_spacing": self.sp_ymajor.value() or None,
                "y_minor_spacing": self.sp_yminor.value() or None,
                "x_anchor_tick": self.sp_xanchor.value() if self.chk_xanchor.isChecked() else None,
                "y_anchor_tick": self.sp_yanchor.value() if self.chk_yanchor.isChecked() else None,
                "x_minor_count": self.sp_xminorcount.value() or None,
                "y_minor_count": self.sp_yminorcount.value() or None,
                "x_rescale_margin": self.sp_xmargin.value(),
                "y_rescale_margin": self.sp_ymargin.value(),
                "spine_color": self.btn_spinecolor.color().name(),
                "spine_width": self.sp_spinewidth.value(),
                "spine_top": self.chk_spinetop.isChecked(),
                "spine_right": self.chk_spineright.isChecked(),
                "spine_left": self.chk_spineleft.isChecked(),
                "spine_bottom": self.chk_spinebottom.isChecked(),
                "refline_h": self.sp_reflineh.value() if self.chk_reflineh.isChecked() else None,
                "refline_v": self.sp_reflinev.value() if self.chk_reflinev.isChecked() else None,
                "refline_h_label": self.ed_reflinehlabel.text(),
                "refline_v_label": self.ed_reflinevlabel.text(),
                "refline_color": self.btn_reflinecolor.color().name(),
                "refline_style": self.cb_reflinestyle.currentText(),
                "refline_width": self.sp_reflinewidth.value(),
                "refline_alpha": self.sp_reflinealpha.value(),
            },
            "tick_labels": {
                "enabled": self.chk_ticklabeloverride.isChecked(),
                "axis": self.cb_ticklabelaxis.currentText(),
                "notation": self.cb_ticklabelnotation.currentText(),
                "decimals_enabled": self.chk_ticklabeldecimals.isChecked(),
                "decimals": self.sp_ticklabeldecimals.value(),
                "divide_by": self.sp_ticklabeldivide.value(),
                "formula": self.ed_ticklabelformula.text().strip(),
                "prefix": self.ed_ticklabelprefix.text(),
                "suffix": self.ed_ticklabelsuffix.text(),
                "plus_sign": self.chk_ticklabelplus.isChecked(),
                "minus_sign": self.chk_ticklabelminus.isChecked(),
                "thousands": self.chk_ticklabelthousands.isChecked(),
            },
            "grid": {
                "major": self.chk_grid.isChecked(),
                "minor": self.chk_gridminor.isChecked(),
                "axis": self.cb_gridaxis.currentText(),
                "color": self.btn_gridcolor.color().name(),
                "linestyle": self.cb_gridstyle.currentText(),
                "linewidth": self.sp_gridwidth.value(),
                "alpha": self.sp_gridalpha.value(),
                "minor_color": self.btn_gridmincolor.color().name(),
                "minor_linestyle": self.cb_gridminstyle.currentText(),
                "minor_linewidth": self.sp_gridminwidth.value(),
                "minor_alpha": self.sp_gridminalpha.value(),
            },
            "legend": {
                "visible": self.chk_legend.isChecked(),
                "loc": self.cb_legloc.currentText(),
                "fontsize": self.sp_legsize.value(),
                "ncol": self.sp_legcol.value(),
                "frame": self.chk_legframe.isChecked(),
                "facecolor": self.btn_legface.color().name(),
                "edgecolor": self.btn_legedge.color().name(),
                "alpha": self.sp_legalpha.value(),
                "shadow": self.chk_legshadow.isChecked(),
                "fancybox": self.chk_leground.isChecked(),
                "title": self.ed_legtitle.text(),
                "title_size": self.sp_legtitlesize.value(),
                "columnspacing": self.sp_legcolspacing.value(),
                "labelspacing": self.sp_leglabelspacing.value(),
                "markerscale": self.sp_legmarkerscale.value(),
                "borderpad": self.sp_legborderpad.value(),
                "handlelength": self.sp_leghandlelen.value(),
                "draggable": self.chk_legdraggable.isChecked(),
            },
            "figure": {
                "facecolor": self.btn_axesbg.color().name(),
                "fig_facecolor": self.btn_figbg.color().name(),
                "width_in": self.sp_figw.value(),
                "height_in": self.sp_figh.value(),
                "dpi": self.sp_figdpi.value(),
            },
            "effects": {
                "axes_shadow": self.chk_axesshadow.isChecked(),
                "shadow_color": self.btn_shadowcolor.color().name(),
                "shadow_alpha": self.sp_shadowalpha.value(),
                "shadow_offset_x": self.sp_shadowx.value(),
                "shadow_offset_y": self.sp_shadowy.value(),
            },
            # One-shot recolour action (not read back from the figure). Default
            # "keep" so an identity Apply diffs to a visual no-op.
            "palette": {
                "name": self.cb_palette.currentText(),
                "line_width": self._palette_line_width,
            },
            "inset": {
                "enabled": self.chk_inset.isChecked(),
                "loc": self.cb_insetloc.currentText(),
                "size": self.sp_insetsize.value(),
                "xmin": self.sp_insetxmin.value(),
                "xmax": self.sp_insetxmax.value(),
                "indicate": self.chk_insetbox.isChecked(),
            },
            "colorbar": {
                "enabled": self.chk_cbar.isChecked(),
                "cmap": (
                    "" if self.cb_cmap.currentText() == "(keep)"
                    else self.cb_cmap.currentText()
                ),
                "label": self.ed_cbarlabel.text(),
                "shrink": self.sp_cbarshrink.value(),
                "tick_size": self.sp_cbarticksize.value(),
            },
        }

    def get_line_styles(self) -> List[Dict[str, Any]]:
        if self._line_styles:
            self._store_line(self._current_line)
        return [dict(d) for d in self._line_styles]

    def _on_apply(self) -> None:
        self.applied.emit()


# --- tiny widget factories --------------------------------------------------
def _scrolled(inner: QWidget) -> QScrollArea:
    """Wrap a tall tab body in a vertical scroll area so it never overflows."""
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    sa.setWidget(inner)
    return sa


def _nz(value, default=0.0) -> float:
    """None → default; otherwise float(value)."""
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _flags_row(*checks) -> QWidget:
    """Lay several checkboxes out horizontally on one form row."""
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    for c in checks:
        h.addWidget(c)
    h.addStretch(1)
    return row


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


def _range_row(chk, sp_min, sp_max=None):
    """A checkbox + one or two spin boxes on a single row.

    With ``sp_max`` (X/Y range): the checkbox is an *Auto* toggle that DISABLES
    the min/max spins while checked. With only ``sp_min`` (reference line): the
    checkbox is an *Enable* toggle that ENABLES the spin while checked.
    """
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(chk)
    h.addWidget(sp_min)
    if sp_max is not None:
        h.addWidget(QLabel("→"))
        h.addWidget(sp_max)

        # disable min/max while auto is on
        def _sync(on):
            sp_min.setEnabled(not on)
            sp_max.setEnabled(not on)
    else:
        h.addStretch(1)

        # enable the value spin only while the toggle is on
        def _sync(on):
            sp_min.setEnabled(on)
    chk.toggled.connect(_sync)
    _sync(chk.isChecked())
    return row
