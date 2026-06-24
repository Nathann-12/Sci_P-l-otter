from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:  # shared MainWindow state this mixin relies on (set in MainWindow.__init__)
    _df: object
    crosscorr: object
    peaks: object
    ccDock: object
    pkDock: object
    tabs: object


class MainWindowAnalysisMixin:
    """Cross-correlation and peak-detection handlers extracted from MainWindow."""

    def _on_cc_compute(self, opts: dict):
        try:
            df = getattr(self, '_df', None)
            if df is None: return
            x_raw = df[opts['x']].to_numpy()
            y1 = df[opts['y1']].to_numpy(); y2 = df[opts['y2']].to_numpy()
            # Handle datetime x by converting to POSIX seconds and convert view limits likewise
            def _to_posix_seconds(arr):
                import numpy as _np
                import pandas as _pd
                if _np.issubdtype(arr.dtype, _np.datetime64):
                    return arr.astype('datetime64[ns]').astype('int64') / 1e9
                # object -> try pandas to_datetime
                if arr.dtype == object:
                    a = _pd.to_datetime(arr, errors='coerce').astype('datetime64[ns]').to_numpy()
                    return a.astype('int64') / 1e9
                return arr.astype(float)

            is_dt = np.issubdtype(x_raw.dtype, np.datetime64) or x_raw.dtype == object
            if is_dt:
                x_num = _to_posix_seconds(x_raw)
                import matplotlib.dates as _mdates
                ax = self.tabs.currentWidget().get_axes(); lim0, lim1 = ax.get_xlim()
                v0 = _mdates.num2date(lim0).timestamp(); v1 = _mdates.num2date(lim1).timestamp()
                lo, hi = (min(v0, v1), max(v0, v1))
                m1 = (x_num >= lo) & (x_num <= hi)
                xr = x_num[m1]
            else:
                ax = self.tabs.currentWidget().get_axes(); lim0, lim1 = ax.get_xlim()
                lo, hi = (min(lim0, lim1), max(lim0, lim1))
                m1 = (x_raw >= lo) & (x_raw <= hi)
                xr = x_raw[m1].astype(float)

            y1r = y1[m1]
            y2r = y2[m1]
            res = self.crosscorr.compute_crosscorr(xr, y1r, xr, y2r,
                                                   max_lag=float(opts['max_lag']), step=float(opts['dt']),
                                                   detrend=opts['detrend'], normalize=opts['normalize'])
            self.ccDock.show_result(res)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Cross-corr failed: {e}")

    def _collect_pk_params_from_menu(self) -> dict:
        # fallback gather from dock; if hidden, try default columns
        try:
            return {
                'x': self.pkDock.cbX.currentText(),
                'y': self.pkDock.cbY.currentText(),
                'polarity': self.pkDock.cbPolarity.currentText(),
                'prominence': float(self.pkDock.spinProm.value()),
                'height': float(self.pkDock.spinHeight.value()),
                'min_distance': int(self.pkDock.spinMinDist.value()),
                'min_width': int(self.pkDock.spinMinWidth.value()),
                'smooth_window': int(self.pkDock.spinSmooth.value()),
                'annotate': bool(self.pkDock.chkAnnotate.isChecked()),
            }
        except Exception:
            return {'x':'','y':'','polarity':'peaks','prominence':0.0,'height':0.0,'min_distance':5,'min_width':1,'smooth_window':0,'annotate':True}

    def _on_pk_detect(self, opts: dict):
        try:
            df = getattr(self, '_df', None)
            if df is None: return
            x_raw = df[opts['x']].to_numpy() if opts['x'] in df.columns else np.arange(len(df))
            y = df[opts['y']].to_numpy()
            ax = self.tabs.currentWidget().get_axes(); lim0, lim1 = ax.get_xlim()
            lo, hi = (min(lim0, lim1), max(lim0, lim1))
            # Convert datetime x to Matplotlib date numbers for consistent comparison
            try:
                import numpy as _np, pandas as _pd, matplotlib.dates as _mdates
                if _np.issubdtype(x_raw.dtype, _np.datetime64) or x_raw.dtype == object:
                    x_num = _mdates.date2num(_pd.to_datetime(x_raw, errors='coerce').to_pydatetime())
                else:
                    x_num = _np.asarray(x_raw, float)
            except Exception:
                x_num = np.asarray(x_raw, float)
            m = (x_num >= lo) & (x_num <= hi)
            from peaks import PeakParams
            p = PeakParams(polarity=opts['polarity'], prominence=opts['prominence'], height=opts['height'],
                           min_distance=opts['min_distance'], min_width=opts['min_width'], smooth_window=opts['smooth_window'],
                           annotate=opts.get('annotate', True))
            res = self.peaks.detect(x_num[m], y[m], p)
            self.pkDock.show_results(res)
            if opts.get('annotate', True):
                self.peaks.annotate(x_num[m], y[m], res)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Peak detect failed: {e}")

    def _on_pk_annotate(self, on: bool):
        try:
            if not on:
                self.peaks.clear()
                return
            table = self.pkDock.table
            rows = table.rowCount()
            if rows == 0:
                return
            header_map = {}
            for c in range(table.columnCount()):
                item = table.horizontalHeaderItem(c)
                if item is None:
                    continue
                header_map[item.text().strip().lower()] = c
            col_x = header_map.get('x_peak', 0)
            col_y = header_map.get('y_peak', 1)
            col_idx = header_map.get('index', 2)
            col_kind = header_map.get('type', header_map.get('kind'))
            xs = []
            ys = []
            idx_vals = []
            kinds = []
            for r in range(rows):
                item_x = table.item(r, col_x)
                item_y = table.item(r, col_y)
                item_idx = table.item(r, col_idx)
                if not item_x or not item_y or not item_idx:
                    continue
                try:
                    x_val = float(item_x.text())
                    y_val = float(item_y.text())
                    idx_val = int(float(item_idx.text()))
                except Exception:
                    continue
                xs.append(x_val)
                ys.append(y_val)
                idx_vals.append(idx_val)
                if col_kind is not None:
                    item_kind = table.item(r, col_kind)
                    txt = item_kind.text().strip().lower() if item_kind else ''
                    if 'trough' in txt:
                        kinds.append('trough')
                    elif 'peak' in txt:
                        kinds.append('peak')
                    else:
                        kinds.append(txt or 'peak')
            if not xs:
                return
            res = {'x_peak': xs, 'y_peak': ys, 'index': idx_vals}
            if col_kind is not None and len(kinds) == len(xs):
                res['kind'] = kinds
            df = getattr(self, '_df', None)
            if df is None or df.empty:
                self.peaks.annotate(np.asarray(xs, float), np.asarray(ys, float), res)
                return
            xcol = self.pkDock.cbX.currentText()
            ycol = self.pkDock.cbY.currentText()
            x_data = df[xcol].to_numpy() if xcol in df.columns else np.arange(len(df))
            y_data = df[ycol].to_numpy() if ycol in df.columns else np.asarray(ys, float)
            self.peaks.annotate(x_data, y_data, res)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Annotate failed: {e}")

    def _on_pk_export(self):
        try:
            import pandas as pd
        except Exception:
            pd = None
        try:
            from PySide6.QtWidgets import QFileDialog
            fn, _ = QFileDialog.getSaveFileName(self, "Export Peaks", "peaks.csv", "CSV (*.csv);;Excel (*.xlsx)")
            if not fn:
                return
            table = self.pkDock.table
            header_map = {}
            for c in range(table.columnCount()):
                item = table.horizontalHeaderItem(c)
                if item is None:
                    continue
                header_map[item.text().strip().lower()] = c
            col_x = header_map.get('x_peak')
            col_y = header_map.get('y_peak')
            col_idx = header_map.get('index')
            col_kind = header_map.get('type', header_map.get('kind'))
            if col_x is None or col_y is None or col_idx is None:
                QMessageBox.warning(self, "Export", "Peak table is missing required columns.")
                return
            def _cell_text(row, col):
                item = table.item(row, col)
                return item.text() if item else ''
            xs = [_cell_text(r, col_x) for r in range(table.rowCount())]
            ys = [_cell_text(r, col_y) for r in range(table.rowCount())]
            idx_vals = [_cell_text(r, col_idx) for r in range(table.rowCount())]
            kinds = [_cell_text(r, col_kind) for r in range(table.rowCount())] if col_kind is not None else []
            data = {'x_peak': xs, 'y_peak': ys, 'index': idx_vals}
            if col_kind is not None:
                data['type'] = kinds
            if pd is not None and fn.lower().endswith('.xlsx'):
                pd.DataFrame(data).to_excel(fn, index=False)
            else:
                import csv
                headers = ['x_peak', 'y_peak', 'index']
                if col_kind is not None:
                    headers.append('type')
                with open(fn, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    for row_idx in range(len(xs)):
                        row = [xs[row_idx], ys[row_idx], idx_vals[row_idx]]
                        if col_kind is not None:
                            row.append(kinds[row_idx])
                        writer.writerow(row)
            QMessageBox.information(self, "Export", f"Saved: {fn}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Export failed: {e}")
