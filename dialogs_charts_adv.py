from __future__ import annotations
from typing import Callable, List, Optional, Dict
import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QFormLayout, QGridLayout,
    QLabel, QComboBox, QListWidget, QListWidgetItem, QAbstractItemView, QCheckBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QPushButton, QMessageBox
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

# ---- ยูทิลิตี้เดาแกน ----
TIME_KEYS = ("time", "t", "timestamp", "datetime")


def _numeric_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _guess_x_col(df: pd.DataFrame) -> Optional[str]:
    cands = [c for c in df.columns if any(k in str(c).lower() for k in TIME_KEYS)]
    if cands:
        return cands[0]
    nums = _numeric_cols(df)
    return nums[0] if nums else None


def _down_idx(n: int, max_n: int) -> np.ndarray:
    if n <= max_n:
        return np.arange(n)
    return np.linspace(0, n - 1, max_n).astype(int)


class _MplArea(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig = Figure(tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.canvas)


class ChartOptionsDialogPro(QDialog):
    """
    ใช้กับ Analysis เมนู: เปิด overlay ปรับละเอียดก่อนพล็อต
    kind: "line"|"scatter"|"bar"|"area"|"box"|"pie"|"hist"|"3d_scatter"|"spectrogram"
    get_df(): -> DataFrame ปัจจุบัน
    apply_to_main(draw_fn): ให้แคนวาสหลักเคลียร์ + เรียก draw_fn(ax/ax3d)
    """

    def __init__(self, kind: str,
                 get_df: Callable[[], pd.DataFrame],
                 apply_to_main: Callable[[Callable], None],
                 parent=None):
        super().__init__(parent)
        self.kind = kind
        self.get_df = get_df
        self.apply_to_main = apply_to_main
        self._col_lookup = {}  # display text -> original column value
        self._col_signature = None

        self.setWindowTitle(f"{kind.capitalize()} — Options")
        self.setWindowFlag(Qt.Window)
        self.resize(720, 520)

        self.tabs = QTabWidget()
        self.data_tab = self._build_data_tab()
        self.style_tab = self._build_style_tab()
        self.axes_tab = self._build_axes_tab()
        self.tabs.addTab(self.data_tab, "Data")
        self.tabs.addTab(self.style_tab, "Style")
        self.tabs.addTab(self.axes_tab, "Axes & Legend")

        self.mpl = _MplArea(self)

        # buttons
        btns = QHBoxLayout()
        self.btn_preview = QPushButton("Preview")
        self.btn_apply = QPushButton("Plot to Canvas")
        self.btn_close = QPushButton("Close")
        btns.addWidget(self.btn_preview)
        btns.addStretch(1)
        btns.addWidget(self.btn_apply)
        btns.addWidget(self.btn_close)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(self.tabs)
        lay.addLayout(btns)
        lay.addWidget(self.mpl)

        self.btn_preview.clicked.connect(self._on_preview)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_close.clicked.connect(self.close)

        # เตรียมรายการคอลัมน์
        self._populate_columns()

        # พรีวิวแรก
        self._on_preview()

        QTimer.singleShot(0, lambda: self._populate_columns(preserve=True))

    # -------------------- Data Tab --------------------
    def _build_data_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(6)
        form.setContentsMargins(8, 8, 8, 8)
        self.cbo_x = QComboBox()

        self.lst_y = QListWidget()
        self.lst_y.setSelectionMode(QAbstractItemView.NoSelection)  # ใช้เช็กบ็อกซ์แทน
        self.chk_dropna = QCheckBox("Drop NaN")
        self.chk_sortx = QCheckBox("Sort by X")
        self.spin_maxpts = QSpinBox()
        self.spin_maxpts.setRange(100, 200000)
        self.spin_maxpts.setValue(5000)

        self.btn_refresh = QPushButton("Refresh Columns")
        self.btn_refresh.clicked.connect(lambda: self._populate_columns(preserve=True))

        form.addRow("X column", self.cbo_x)
        form.addRow("Y columns", self.lst_y)
        form.addRow("", self.chk_dropna)
        form.addRow("", self.chk_sortx)
        form.addRow("Downsample max points", self.spin_maxpts)
        form.addRow("", self.btn_refresh)
        return w

    # -------------------- Style Tab --------------------
    def _build_style_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(6)
        form.setContentsMargins(8, 8, 8, 8)

        # ร่วม
        self.alpha = QDoubleSpinBox()
        self.alpha.setRange(0.1, 1.0)
        self.alpha.setSingleStep(0.1)
        self.alpha.setValue(1.0)

        # line/area/bar/box
        self.linew = QDoubleSpinBox()
        self.linew.setRange(0.5, 12.0)
        self.linew.setSingleStep(0.5)
        self.linew.setValue(2.0)
        self.linestyle = QComboBox()
        self.linestyle.addItems(["-", "--", "-.", ":", "solid", "dashed", "dashdot", "dotted"])
        # scatter/3d
        self.markersize = QDoubleSpinBox()
        self.markersize.setRange(1, 40)
        self.markersize.setSingleStep(1)
        self.markersize.setValue(8)
        self.marker = QComboBox()
        self.marker.addItems(["o", "s", "^", "v", "D", "x", "+", ".", ","])

        # bar
        self.bar_mode = QComboBox()
        self.bar_mode.addItems(["grouped", "stacked"])
        self.bar_orient = QComboBox()
        self.bar_orient.addItems(["vertical", "horizontal"])
        self.bar_width = QDoubleSpinBox()
        self.bar_width.setRange(0.05, 1.0)
        self.bar_width.setValue(0.8)

        # area
        self.area_normalize = QCheckBox("Normalize to 100%")

        # hist
        self.hist_bins = QSpinBox()
        self.hist_bins.setRange(5, 500)
        self.hist_bins.setValue(20)
        self.hist_strategy = QComboBox()
        self.hist_strategy.addItems(["(fixed)", "auto", "sqrt", "sturges", "doane", "fd", "scott", "rice"])
        self.hist_density = QCheckBox("Density (PDF)")
        self.hist_cum = QCheckBox("Cumulative")
        self.hist_orient = QComboBox()
        self.hist_orient.addItems(["vertical", "horizontal"])
        self.hist_fitnorm = QCheckBox("Fit normal curve")

        # pie
        self.pie_start = QSpinBox()
        self.pie_start.setRange(0, 360)
        self.pie_start.setValue(90)
        self.pie_explode = QCheckBox("Explode largest slice")
        self.pie_autopct = QCheckBox("Show percent")

        # box
        self.box_notch = QCheckBox("Notch")
        self.box_means = QCheckBox("Show means")

        # 3d
        self.elev = QDoubleSpinBox()
        self.elev.setRange(-90, 90)
        self.elev.setValue(20)
        self.azim = QDoubleSpinBox()
        self.azim.setRange(-180, 180)
        self.azim.setValue(-60)

        form.addRow("Alpha", self.alpha)

        if self.kind in ("line", "area", "bar", "box"):
            form.addRow("Line width", self.linew)
            form.addRow("Line style", self.linestyle)
        if self.kind in ("scatter", "3d_scatter"):
            form.addRow("Marker", self.marker)
            form.addRow("Marker size", self.markersize)
        if self.kind == "bar":
            form.addRow("Mode", self.bar_mode)
            form.addRow("Orientation", self.bar_orient)
            form.addRow("Bar width", self.bar_width)
        if self.kind == "area":
            form.addRow("", self.area_normalize)
        if self.kind == "hist":
            form.addRow("Bins", self.hist_bins)
            form.addRow("Strategy", self.hist_strategy)
            form.addRow("", self.hist_density)
            form.addRow("", self.hist_cum)
            form.addRow("Orientation", self.hist_orient)
            form.addRow("", self.hist_fitnorm)
        if self.kind == "pie":
            form.addRow("Start angle", self.pie_start)
            form.addRow("", self.pie_explode)
            form.addRow("", self.pie_autopct)
        if self.kind == "box":
            form.addRow("", self.box_notch)
            form.addRow("", self.box_means)
        if self.kind == "3d_scatter":
            form.addRow("Elev", self.elev)
            form.addRow("Azim", self.azim)

        return w

    # -------------------- Axes Tab --------------------
    def _build_axes_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(6)
        form.setContentsMargins(8, 8, 8, 8)

        self.title = QLineEdit()
        self.xlabel = QLineEdit()
        self.ylabel = QLineEdit()
        self.zlabel = QLineEdit()

        self.show_grid = QCheckBox("Show grid")
        self.show_legend = QCheckBox("Show legend"); self.show_legend.setChecked(True)
        self.legend_loc = QComboBox(); self.legend_loc.addItems([
            "best", "upper right", "upper left", "lower left", "lower right", "right",
            "center left", "center right", "lower center", "upper center", "center"
        ])

        self.logx = QCheckBox("log-x"); self.logy = QCheckBox("log-y"); self.logz = QCheckBox("log-z")

        # limits
        self.use_xlim = QCheckBox("set xlim"); self.xmin = QDoubleSpinBox(); self.xmax = QDoubleSpinBox()
        self.xmin.setRange(-1e15, 1e15); self.xmax.setRange(-1e15, 1e15)
        self.use_ylim = QCheckBox("set ylim"); self.ymin = QDoubleSpinBox(); self.ymax = QDoubleSpinBox()
        self.ymin.setRange(-1e15, 1e15); self.ymax.setRange(-1e15, 1e15)
        self.use_zlim = QCheckBox("set zlim"); self.zmin = QDoubleSpinBox(); self.zmax = QDoubleSpinBox()
        self.zmin.setRange(-1e15, 1e15); self.zmax.setRange(-1e15, 1e15)

        form.addRow("Title", self.title)
        form.addRow("X label", self.xlabel)
        form.addRow("Y label", self.ylabel)
        if self.kind == "3d_scatter":
            form.addRow("Z label", self.zlabel)

        form.addRow("", self.show_grid)
        row = QHBoxLayout(); row.addWidget(self.show_legend); row.addWidget(QLabel("loc")); row.addWidget(self.legend_loc); row.addStretch(1)
        form.addRow("", self._wrap(row))

        row2 = QHBoxLayout(); row2.addWidget(self.logx); row2.addWidget(self.logy)
        if self.kind == "3d_scatter":
            row2.addWidget(self.logz)
        row2.addStretch(1)
        form.addRow("", self._wrap(row2))

        # limits grid
        g = QGridLayout()
        g.addWidget(self.use_xlim, 0, 0); g.addWidget(QLabel("xmin"), 0, 1); g.addWidget(self.xmin, 0, 2); g.addWidget(QLabel("xmax"), 0, 3); g.addWidget(self.xmax, 0, 4)
        g.addWidget(self.use_ylim, 1, 0); g.addWidget(QLabel("ymin"), 1, 1); g.addWidget(self.ymin, 1, 2); g.addWidget(QLabel("ymax"), 1, 3); g.addWidget(self.ymax, 1, 4)
        if self.kind == "3d_scatter":
            g.addWidget(self.use_zlim, 2, 0); g.addWidget(QLabel("zmin"), 2, 1); g.addWidget(self.zmin, 2, 2); g.addWidget(QLabel("zmax"), 2, 3); g.addWidget(self.zmax, 2, 4)
        form.addRow("Limits", self._wrap(g))
        return w

    @staticmethod
    def _wrap(layout) -> QWidget:
        w = QWidget(); w.setLayout(layout); return w

    # -------------------- Populate columns --------------------
    def _populate_columns(self, preserve=False):
        prev_x = None
        prev_x_label = None
        prev_ys = set()
        if preserve:
            prev_x = self.cbo_x.currentData()
            prev_x_label = self.cbo_x.currentText()
            for i in range(self.lst_y.count()):
                item = self.lst_y.item(i)
                if item.checkState() == Qt.Checked:
                    val = item.data(Qt.UserRole)
                    if val is None:
                        val = item.text()
                    prev_ys.add(val)

        try:
            df = self.get_df()
        except Exception:
            df = None

        cols = list(df.columns) if (df is not None and hasattr(df, 'columns')) else []
        signature = tuple(cols)
        if preserve and signature == getattr(self, '_col_signature', None):
            return

        display_cols = [str(c) for c in cols]
        self._col_lookup = {label: col for label, col in zip(display_cols, cols)}
        self._col_signature = signature

        self.cbo_x.clear()
        self.cbo_x.addItem('<auto>', None)
        # y list with checkboxes
        self.lst_y.clear()
        for col, label in zip(cols, display_cols):
            self.cbo_x.addItem(label, col)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, col)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.lst_y.addItem(item)

        # auto preselect
        xg = _guess_x_col(df) if df is not None else None
        if preserve and prev_x is not None:
            idx = self.cbo_x.findData(prev_x)
            if idx == -1 and isinstance(prev_x_label, str):
                idx = self.cbo_x.findText(prev_x_label)
            if idx != -1:
                self.cbo_x.setCurrentIndex(idx)
        elif xg is not None:
            idx = self.cbo_x.findData(xg)
            if idx != -1:
                self.cbo_x.setCurrentIndex(idx)

        nums = _numeric_cols(df) if df is not None else []
        auto_selected = 0
        for c in nums:
            if xg is not None and c == xg:
                continue
            try:
                i = cols.index(c)
            except ValueError:
                continue
            item = self.lst_y.item(i)
            if item is not None:
                item.setCheckState(Qt.Checked)
                auto_selected += 1
                if auto_selected >= 6:
                    break

        if preserve and prev_ys:
            for i in range(self.lst_y.count()):
                item = self.lst_y.item(i)
                val = item.data(Qt.UserRole)
                if val is None:
                    val = item.text()
                if val in prev_ys:
                    item.setCheckState(Qt.Checked)

        if not cols:
            placeholder = QListWidgetItem('<no columns detected - load data then press Refresh>')
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsEnabled)
            self.lst_y.addItem(placeholder)
            return

    def showEvent(self, event):
        super().showEvent(event)
        try:
            self._populate_columns(preserve=True)
        except Exception:
            pass


    # -------------------- Collect options --------------------
    def _collect(self) -> Dict:
        opts: Dict = dict(kind=self.kind)
        opts["alpha"] = self.alpha.value()
        opts["linew"] = self.linew.value()
        opts["linestyle"] = self.linestyle.currentText()
        opts["markersize"] = self.markersize.value()
        opts["marker"] = self.marker.currentText()
        opts["bar_mode"] = self.bar_mode.currentText() if self.kind == "bar" else None
        opts["bar_orient"] = self.bar_orient.currentText() if self.kind == "bar" else None
        opts["bar_width"] = self.bar_width.value() if self.kind == "bar" else None
        opts["area_norm"] = self.area_normalize.isChecked() if self.kind == "area" else None
        if self.kind == "hist":
            opts["bins"] = self.hist_bins.value()
            strat = self.hist_strategy.currentText()
            opts["bin_strategy"] = None if strat == "(fixed)" else strat
            opts["density"] = self.hist_density.isChecked()
            opts["cumulative"] = self.hist_cum.isChecked()
            opts["orient"] = self.hist_orient.currentText()
            opts["fitnorm"] = self.hist_fitnorm.isChecked()
        if self.kind == "pie":
            opts["startangle"] = self.pie_start.value()
            opts["explode"] = self.pie_explode.isChecked()
            opts["autopct"] = self.pie_autopct.isChecked()
        if self.kind == "box":
            opts["notch"] = self.box_notch.isChecked()
            opts["means"] = self.box_means.isChecked()
        if self.kind == "3d_scatter":
            opts["elev"] = self.elev.value(); opts["azim"] = self.azim.value()

        # data options
        x_label = self.cbo_x.currentText()
        x_data = self.cbo_x.currentData()
        opts["x"] = x_data if x_data is not None else x_label
        ys = []
        for i in range(self.lst_y.count()):
            item = self.lst_y.item(i)
            if item.checkState() == Qt.Checked:
                val = item.data(Qt.UserRole)
                if val is None:
                    val = item.text()
                ys.append(val)
        opts["ys"] = ys
        opts["dropna"] = self.chk_dropna.isChecked()
        opts["sortx"] = self.chk_sortx.isChecked()
        opts["maxpts"] = self.spin_maxpts.value()

        # axes
        opts["title"] = self.title.text().strip()
        opts["xlabel"] = self.xlabel.text().strip()
        opts["ylabel"] = self.ylabel.text().strip()
        opts["zlabel"] = self.zlabel.text().strip()
        opts["grid"] = self.show_grid.isChecked()
        opts["legend"] = self.show_legend.isChecked()
        opts["legend_loc"] = self.legend_loc.currentText()
        opts["logx"] = self.logx.isChecked(); opts["logy"] = self.logy.isChecked(); opts["logz"] = self.logz.isChecked()
        opts["use_xlim"] = self.use_xlim.isChecked(); opts["xmin"] = self.xmin.value(); opts["xmax"] = self.xmax.value()
        opts["use_ylim"] = self.use_ylim.isChecked(); opts["ymin"] = self.ymin.value(); opts["ymax"] = self.ymax.value()
        opts["use_zlim"] = self.use_zlim.isChecked(); opts["zmin"] = self.zmin.value(); opts["zmax"] = self.zmax.value()
        return opts

    # -------------------- Core draw --------------------
    def _plot_with_opts(self, ax, df: pd.DataFrame, o: Dict):
        xcol = None if o['x'] in ('<auto>', '') else o['x']
        if xcol is None:
            xcol = _guess_x_col(df)
        xs = df[xcol].to_numpy() if (xcol and xcol in df.columns) else np.arange(len(df))
        ycols = o['ys'] or [c for c in _numeric_cols(df) if c != xcol][:1]
        kind = o['kind']

        if kind != 'hist' and not ycols:
            raise ValueError('Select at least one numeric Y column on the Data tab.')
        if kind == '3d_scatter' and len(ycols) < 2:
            raise ValueError('Select at least two Y columns for a 3D scatter plot.')

        used = [xs] + [df[c].to_numpy() for c in ycols]
        try:
            arrays = [np.asarray(a, float) for a in used]
        except ValueError as exc:
            raise ValueError('Selected columns must contain numeric data.') from exc
        if not arrays or arrays[0].size == 0:
            raise ValueError('No data available for plotting.')
        M = np.column_stack(arrays)

        if o['dropna']:
            M = M[~np.any(np.isnan(M), axis=1)]
        if M.size == 0:
            raise ValueError('No data left after removing NaN rows.')

        if o['sortx']:
            M = M[np.argsort(M[:, 0])]
        idx = _down_idx(M.shape[0], o['maxpts'])
        M = M[idx]
        if M.size == 0:
            raise ValueError('No data left to plot after downsampling.')

        X = M[:, 0]
        YS = [M[:, i + 1] for i in range(len(ycols))]
        if YS:
            valid = np.isfinite(X)
            for arr in YS:
                valid &= np.isfinite(arr)
            if not np.any(valid):
                raise ValueError('Selected columns do not contain finite numeric data.')
            X = X[valid]
            YS = [arr[valid] for arr in YS]
        else:
            if not np.isfinite(X).any():
                raise ValueError('Selected column does not contain numeric data to plot.')

        if kind in ('line', 'scatter', 'bar', 'area', 'box') and any(arr.size == 0 for arr in YS):
            raise ValueError('Not enough data points to plot the selected series.')
        if kind == '3d_scatter' and len(YS) < 2:
            raise ValueError('Select at least two Y columns for a 3D scatter plot.')

        if kind == 'line':
            for y, name in zip(YS, ycols):
                ax.plot(X, y, label=str(name), linestyle=o['linestyle'], linewidth=o['linew'], alpha=o['alpha'])
        elif kind == 'scatter':
            for y, name in zip(YS, ycols):
                ax.scatter(X, y, label=str(name), marker=o['marker'], s=o['markersize'] ** 2, alpha=o['alpha'])
        elif kind == 'bar':
            k = len(YS); w = float(o['bar_width']) if o['bar_width'] else 0.8
            if k == 0:
                raise ValueError('Select at least one Y column for a bar chart.')
            if o['bar_mode'] == 'stacked':
                base = np.zeros_like(YS[0]); xi = np.arange(len(X))
                for y, name in zip(YS, ycols):
                    if o['bar_orient'] == 'vertical':
                        ax.bar(xi, y, width=w, bottom=base, label=str(name), alpha=o['alpha'])
                    else:
                        ax.barh(xi, y, height=w, left=base, label=str(name), alpha=o['alpha'])
                    base = base + y
                ax.set_xticks(xi)
            else:
                xi = np.arange(len(X))
                step = w / max(k, 1)
                for i, (y, name) in enumerate(zip(YS, ycols)):
                    shift = (i - (k - 1) / 2.0) * step
                    if o['bar_orient'] == 'vertical':
                        ax.bar(xi + shift, y, width=step, label=str(name), alpha=o['alpha'])
                    else:
                        ax.barh(xi + shift, y, height=step, label=str(name), alpha=o['alpha'])
                ax.set_xticks(xi)
        elif kind == 'area':
            if not YS:
                raise ValueError('Select at least one Y column for an area chart.')
            Y = np.vstack(YS)
            if o['area_norm']:
                s = np.sum(Y, axis=0); s[s == 0] = 1.0; Y = Y / s
            ax.stackplot(X, Y, labels=[str(n) for n in ycols], alpha=o['alpha'])
        elif kind == 'box':
            if not YS:
                raise ValueError('Select at least one Y column for a box plot.')
            ax.boxplot(YS, labels=[str(n) for n in ycols], notch=o.get('notch', False), showmeans=o.get('means', False))
        elif kind == 'pie':
            vals = np.abs(YS[0]) if YS else np.abs(np.asarray(X, float))
            if vals.size == 0:
                raise ValueError('Select a column with numeric data for a pie chart.')
            labels = [f"{ycols[0]}[{i}]" for i in range(min(8, len(vals)))] if YS else [f"{i}" for i in range(min(8, len(vals)))]
            vals = vals[:len(labels)]
            explode = np.zeros_like(vals, dtype=float)
            if o.get('explode') and len(vals) > 0:
                explode[np.argmax(vals)] = 0.08
            autopct = '%1.0f%%' if o.get('autopct') else None
            ax.pie(vals, labels=labels, startangle=o.get('startangle', 90), explode=explode, autopct=autopct)
            ax.axis('equal')
        elif kind == 'hist':
            bins = o['bin_strategy'] if o['bin_strategy'] else o['bins']
            data = YS[0] if YS else X
            if data.size == 0:
                raise ValueError('Select a column with numeric data for a histogram.')
            kwargs = dict(bins=bins, density=o['density'], cumulative=o['cumulative'], alpha=o['alpha'], orientation='vertical' if o['orient'] == 'vertical' else 'horizontal')
            ax.hist(data, **kwargs)
            if o['fitnorm'] and data.size > 0:
                mu, sigma = np.nanmean(data), np.nanstd(data)
                xs = np.linspace(np.nanmin(data), np.nanmax(data), 400)
                if sigma == 0 or not np.isfinite(sigma):
                    sigma = 1.0
                pdf = 1 / (sigma * np.sqrt(2 * np.pi)) * np.exp(- (xs - mu) ** 2 / (2 * sigma ** 2))
                if o['density']:
                    ax.plot(xs, pdf)
                else:
                    rng = np.nanmax(data) - np.nanmin(data)
                    bw = (rng / (o['bins'] if isinstance(bins, int) else 20)) if rng > 0 else 1
                    ax.plot(xs, pdf * max(len(data), 1) * bw)
        elif kind == '3d_scatter':
            if len(YS) < 2:
                raise ValueError('Select at least two Y columns for a 3D scatter plot.')
            try:
                is_3d = getattr(ax, 'name', '') == '3d'
            except Exception:
                is_3d = False
            if not is_3d:
                fig = ax.figure
                try:
                    ax.remove()
                except Exception:
                    pass
                ax = fig.add_subplot(111, projection='3d')
            ax.scatter(X, YS[0], YS[1] if len(YS) > 1 else np.zeros_like(X),
                       marker=o['marker'], s=o['markersize'] ** 2, alpha=o['alpha'])
            ax.view_init(elev=o['elev'], azim=o['azim'])
        # ---- axes / legend / labels ----
        if o["title"]:
            ax.set_title(o["title"])
        if o["xlabel"]:
            ax.set_xlabel(o["xlabel"])
        if o["ylabel"]:
            ax.set_ylabel(o["ylabel"])
        if self.kind == "3d_scatter" and o["zlabel"]:
            ax.set_zlabel(o["zlabel"])

        if o["grid"]:
            ax.grid(True, which="both", alpha=0.3)
        if o["legend"] and kind not in ("hist", "pie"):
            ax.legend(loc=o["legend_loc"])

        if o["logx"]:
            ax.set_xscale("log")
        if o["logy"]:
            ax.set_yscale("log")
        if self.kind == "3d_scatter" and o["logz"]:
            try:
                ax.set_zscale("log")
            except Exception:
                pass

        if o["use_xlim"]:
            ax.set_xlim(o["xmin"], o["xmax"])
        if o["use_ylim"]:
            ax.set_ylim(o["ymin"], o["ymax"])
        if self.kind == "3d_scatter" and o["use_zlim"]:
            try:
                ax.set_zlim(o["zmin"], o["zmax"])
            except Exception:
                pass

    # -------------------- Preview & Apply --------------------
    def _on_preview(self):
        df = self.get_df()
        self.mpl.fig.clear()
        ax = self.mpl.fig.add_subplot(111, projection="3d") if self.kind == "3d_scatter" else self.mpl.fig.add_subplot(111)
        try:
            self._plot_with_opts(ax, df, self._collect())
        except Exception as e:
            ax.clear(); ax.text(0.5, 0.5, f"Preview error:\n{e}", ha="center", va="center", transform=ax.transAxes)
        self.mpl.canvas.draw_idle()

    def _on_apply(self):
        opts = self._collect()
        need3d = (self.kind == "3d_scatter")

        def drawer(ax):
            self._plot_with_opts(ax, self.get_df(), opts)

        try:
            try:
                self.apply_to_main(drawer, prefer_3d=need3d)
            except TypeError:
                self.apply_to_main(drawer)
        except ValueError as exc:
            QMessageBox.warning(self, "Plot Error", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Plot Error", str(exc))
            return
        self.close()
