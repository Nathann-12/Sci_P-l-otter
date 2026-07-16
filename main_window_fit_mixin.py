from __future__ import annotations

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from PySide6.QtWidgets import QDialog, QMessageBox

from processors import FitResult, _to_seconds_from_start, beautify_axes, fit_poly_datetime


class MainWindowFitMixin:
    """Reusable fitting actions extracted from MainWindow."""

    def open_nonlinear_fit_dialog(self):
        """Open NonlinearFitDialog with the current DataFrame."""
        df = self.get_current_dataframe()
        if df is None or df.empty:
            QMessageBox.information(self, "No data", "Load data before fitting.")
            return
        try:
            from dialogs_fit import NonlinearFitDialog

            dlg = NonlinearFitDialog(self, df)
            dlg.exec()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not open Nonlinear Curve Fit:\n{exc}")

    def plot_fit_result_on_active_tab(self, x: np.ndarray, res: FitResult):
        """Draw the fitted curve and confidence interval on the active graph."""
        tab = self.tabs.currentWidget() if hasattr(self, "tabs") else None
        if tab is None or not hasattr(tab, "get_axes"):
            return
        try:
            ax = tab.get_axes()
        except Exception:
            ax = None
        if ax is None:
            return
        x_arr = np.asarray(x, dtype=float)
        y_fit = np.asarray(res.yfit, dtype=float) if res.yfit is not None else np.array([])
        if x_arr.size == 0 or y_fit.size == 0:
            return
        if x_arr.size != y_fit.size:
            length = min(x_arr.size, y_fit.size)
            if length <= 0:
                return
            x_arr = x_arr[:length]
            y_fit = y_fit[:length]
        order = np.argsort(x_arr)
        xs = x_arr[order]
        ys = y_fit[order]
        line, = ax.plot(xs, ys, linewidth=2.0, label="Fit")
        band = None
        if res.ci95_lower is not None and res.ci95_upper is not None:
            lo = np.asarray(res.ci95_lower, dtype=float)
            hi = np.asarray(res.ci95_upper, dtype=float)
            if lo.size == xs.size and hi.size == xs.size:
                lo_ord = lo[order]
                hi_ord = hi[order]
                band = ax.fill_between(xs, lo_ord, hi_ord, alpha=0.2, label="95% CI")
        ax.legend(loc="best")
        ax.figure.canvas.draw_idle()
        try:
            artists = [line]
            if band is not None:
                artists.append(band)
            tab.register_layer(
                artists,
                "Nonlinear Fit",
                "line",
                meta={"kind": "nonlinear_fit", "success": res.success, "message": res.message},
            )
        except Exception:
            pass

    def _open_fit_dialog(self):
        # Origin-style graph-scoped binding: fit the series on the graph the user
        # has selected (or last selected while a Book is focused), not a stale
        # ``self.canvas``. Syncing here also makes the fit overlay (drawn later
        # via ``self.canvas.ax``) land on that same selected graph.
        canvas = self._active_canvas() if hasattr(self, "_active_canvas") else getattr(self, "canvas", None)
        if canvas is None:
            QMessageBox.information(self, "No graph", "Open a graph before fitting.")
            return
        axes = canvas.ax
        series_data = {}
        series_is_seconds: dict[str, bool] = {}
        labels = []
        try:
            for line in axes.get_lines():
                lbl = line.get_label() or "series"
                if lbl.startswith("_"):
                    continue
                # Viewport LOD changes only the visible Line2D samples. Fits
                # must always use the retained full source arrays.
                x = getattr(line, "_sciplotter_x_values", line.get_xdata())
                y = getattr(line, "_sciplotter_y_values", line.get_ydata())
                x_arr = np.asarray(x)
                y_arr = np.asarray(y)
                used_seconds = False
                try:
                    if self._df is not None and " vs " in lbl:
                        y_name, x_name = [s.strip() for s in lbl.split(" vs ", 1)]
                        if x_name in self._df.columns and y_name in self._df.columns:
                            x_ser = self._df[x_name]
                            y_ser = self._df[y_name]
                            try:
                                xs_dt = pd.to_datetime(x_ser, errors="coerce")
                                if xs_dt.notna().sum() >= 2:
                                    delta = (xs_dt - xs_dt.iloc[0]).dt.total_seconds()
                                    x_arr = delta.values
                                    y_arr = pd.to_numeric(y_ser, errors="coerce").values
                                    used_seconds = True
                                else:
                                    x_arr = pd.to_numeric(x_ser, errors="coerce").values
                                    y_arr = pd.to_numeric(y_ser, errors="coerce").values
                            except Exception:
                                x_arr = pd.to_numeric(x_ser, errors="coerce").values
                                y_arr = pd.to_numeric(y_ser, errors="coerce").values
                except Exception:
                    pass
                labels.append(lbl)
                series_data[lbl] = (x_arr, y_arr)
                series_is_seconds[lbl] = used_seconds
        except Exception:
            pass
        if not labels:
            QMessageBox.information(self, "No series", "No lines/points on graph to fit")
            return
        from dialogs import FitDialog

        dlg = FitDialog(self, labels, series_data)
        if dlg.exec() != QDialog.Accepted:
            return
        params = dlg.get_params()
        lbl = params.get("series_label")
        model = params.get("model")
        deg = params.get("degree")
        show_eq = bool(params.get("show_eq", True))
        show_resid = bool(params.get("show_resid", False))
        x, y = series_data.get(lbl, (None, None))
        if x is None or y is None:
            return
        try:
            used_seconds = bool(series_is_seconds.get(lbl, False))
            model_l = (model or "linear").lower()
            if used_seconds and model_l in ("linear", "polynomial"):
                x_name = None
                y_name = None
                try:
                    if " vs " in lbl:
                        y_name, x_name = [s.strip() for s in lbl.split(" vs ", 1)]
                except Exception:
                    pass

                if x_name and y_name and (x_name in self._df.columns) and (y_name in self._df.columns):
                    order = 1 if model_l == "linear" else max(2, int(deg or 2))
                    x_fit_dt, y_fit, meta = fit_poly_datetime(self._df[x_name], self._df[y_name], order=order)
                    t_sec, _t0 = _to_seconds_from_start(self._df[x_name])
                    scale = float(max(np.max(t_sec) - np.min(t_sec), 1.0))
                    t_scaled = (t_sec - float(np.mean(t_sec))) / scale
                    p = np.poly1d(meta.get("coeffs"))
                    y_arr = np.asarray(self._df[y_name], dtype=float)
                    y_pred = p(t_scaled)
                    resid = y_arr - y_pred
                    rmse = float(np.sqrt(np.mean(resid**2)))
                    ss_res = float(np.sum(resid**2))
                    ss_tot = float(np.sum((y_arr - float(np.mean(y_arr)))**2))
                    r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
                    metrics = {"r2": r2, "rmse": rmse}
                    self._plot_fit_overlay(
                        lbl,
                        x_fit_dt,
                        y_fit,
                        meta,
                        metrics,
                        show_eq=show_eq,
                        show_resid=show_resid,
                        x_seconds=False,
                    )
                    try:
                        self.canvas.ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M:%S"))
                        self.canvas.fig.autofmt_xdate()
                        self.canvas.draw()
                    except Exception:
                        pass
                    self.current_fit_result = {
                        "series": lbl,
                        "model": model,
                        "params": meta,
                        "metrics": metrics,
                        "xfit": x_fit_dt,
                        "yfit": y_fit,
                    }
                else:
                    xfit, yfit, fit_params, metrics = self._do_curve_fit(
                        np.asarray(x),
                        np.asarray(y),
                        model=model,
                        degree=deg,
                    )
                    self._plot_fit_overlay(
                        lbl,
                        xfit,
                        yfit,
                        fit_params,
                        metrics,
                        show_eq=show_eq,
                        show_resid=show_resid,
                        x_seconds=used_seconds,
                    )
                    self.current_fit_result = {
                        "series": lbl,
                        "model": model,
                        "params": fit_params,
                        "metrics": metrics,
                        "xfit": xfit,
                        "yfit": yfit,
                    }
            else:
                xfit, yfit, fit_params, metrics = self._do_curve_fit(
                    np.asarray(x),
                    np.asarray(y),
                    model=model,
                    degree=deg,
                )
                self._plot_fit_overlay(
                    lbl,
                    xfit,
                    yfit,
                    fit_params,
                    metrics,
                    show_eq=show_eq,
                    show_resid=show_resid,
                    x_seconds=used_seconds,
                )
                self.current_fit_result = {
                    "series": lbl,
                    "model": model,
                    "params": fit_params,
                    "metrics": metrics,
                    "xfit": xfit,
                    "yfit": yfit,
                }
        except Exception as e:
            QMessageBox.critical(self, "Fit failed", f"Reason: {e}")

    def _do_curve_fit(self, x: np.ndarray, y: np.ndarray, *, model: str, degree: int | None = None):
        import numpy as _np

        mask = _np.isfinite(x) & _np.isfinite(y)
        x = _np.asarray(x)[mask]
        y = _np.asarray(y)[mask]
        if x.size < 3:
            raise ValueError("Not enough data for fitting (at least 3 points required).")

        xs = _np.linspace(_np.nanmin(x), _np.nanmax(x), 400)

        def metrics(y_true, y_pred):
            resid = y_true - y_pred
            ss_res = float(_np.sum(resid**2))
            ss_tot = float(_np.sum((y_true - _np.mean(y_true))**2)) + 1e-12
            r2 = 1.0 - ss_res / ss_tot
            rmse = float(_np.sqrt(ss_res / max(1, y_true.size)))
            return {"r2": r2, "rmse": rmse}

        try:
            import scipy.optimize as opt  # type: ignore
        except Exception:
            opt = None

        model = (model or "linear").lower()

        if model == "linear":
            c = _np.polyfit(x, y, 1)
            p = _np.poly1d(c)
            yhat = p(x)  # metrics compare against the original samples, not the 400-pt curve
            yfit = p(xs)
            return xs, yfit, {"coeff": c.tolist()}, metrics(y, yhat)

        if model == "polynomial":
            d = max(2, int(degree or 2))
            c = _np.polyfit(x, y, d)
            p = _np.poly1d(c)
            yhat = p(x)  # metrics compare against the original samples, not the 400-pt curve
            yfit = p(xs)
            return xs, yfit, {"coeff": c.tolist(), "degree": d}, metrics(y, yhat)

        if model == "exponential":
            def f(xv, a, b, c0):
                return a * _np.exp(b * xv) + c0

            if opt is not None:
                p0 = [max(1e-6, float(_np.nanmax(y))), 0.0, float(_np.nanmin(y))]
                popt, _ = opt.curve_fit(f, x, y, p0=p0, maxfev=10000)
                yhat = f(x, *popt)
                yfit = f(xs, *popt)
                return xs, yfit, {"a": float(popt[0]), "b": float(popt[1]), "c": float(popt[2])}, metrics(y, yhat)
            c0 = float(_np.nanmin(y))
            y1 = _np.clip(y - c0, 1e-9, _np.inf)
            b, a0 = _np.polyfit(x, _np.log(y1), 1)
            a = float(_np.exp(a0))
            yhat = a * _np.exp(b * x) + c0
            yfit = a * _np.exp(b * xs) + c0
            return xs, yfit, {"a": a, "b": float(b), "c": c0}, metrics(y, yhat)

        if model == "power":
            m = (x > 0) & (y > 0)
            if m.sum() < 2:
                raise ValueError("Power-law fit requires at least two points with x,y > 0.")
            if opt is not None:
                def f(xv, a, b):
                    return a * (xv**b)

                p0 = [float(_np.nanmax(y)), 1.0]
                popt, _ = opt.curve_fit(f, x[m], y[m], p0=p0, maxfev=10000)
                yhat = f(x, *popt)
                yfit = f(xs, *popt)
                return xs, yfit, {"a": float(popt[0]), "b": float(popt[1])}, metrics(y, yhat)
            b, a0 = _np.polyfit(_np.log(x[m]), _np.log(y[m]), 1)
            a = float(_np.exp(a0))
            yhat = a * (x**b)
            yfit = a * (xs**b)
            return xs, yfit, {"a": a, "b": float(b)}, metrics(y, yhat)

        if model == "gaussian":
            def g(xv, A, mu, sig, C0):
                return A * _np.exp(-0.5 * ((xv - mu) / sig) ** 2) + C0

            if opt is not None:
                mu0 = float(x[_np.argmax(y)])
                sig0 = float(max(1e-6, (_np.percentile(x, 95) - _np.percentile(x, 5)) / 4.0))
                p0 = [float(_np.nanmax(y)), mu0, sig0, float(_np.nanmin(y))]
                popt, _ = opt.curve_fit(g, x, y, p0=p0, maxfev=20000)
                yhat = g(x, *popt)
                yfit = g(xs, *popt)
                return xs, yfit, {
                    "A": float(popt[0]),
                    "mu": float(popt[1]),
                    "sigma": float(popt[2]),
                    "C": float(popt[3]),
                }, metrics(y, yhat)
            mu = float(x[_np.argmax(y)])
            sig = float(max(1e-6, (_np.percentile(x, 95) - _np.percentile(x, 5)) / 4.0))
            G = _np.exp(-0.5 * ((x - mu) / sig) ** 2)
            X = _np.vstack([G, _np.ones_like(G)]).T
            sol, *_ = _np.linalg.lstsq(X, y, rcond=None)
            A, C0 = float(sol[0]), float(sol[1])
            yhat = A * _np.exp(-0.5 * ((x - mu) / sig) ** 2) + C0
            yfit = A * _np.exp(-0.5 * ((xs - mu) / sig) ** 2) + C0
            return xs, yfit, {"A": A, "mu": mu, "sigma": sig, "C": C0}, metrics(y, yhat)

        xnum = x
        dt = _np.median(_np.diff(_np.sort(xnum)))
        if not _np.isfinite(dt) or dt <= 0:
            dt = 1.0
        Y = _np.fft.rfft(y - _np.mean(y))
        freq = _np.fft.rfftfreq(y.size, d=dt)
        if freq.size > 1:
            k = int(_np.argmax(_np.abs(Y[1:])) + 1)
            f0 = float(freq[k])
        else:
            f0 = 1.0
        w = 2 * _np.pi * f0
        S = _np.sin(w * x)
        Cc = _np.cos(w * x)
        A_mat = _np.vstack([S, Cc, _np.ones_like(S)]).T
        beta, *_ = _np.linalg.lstsq(A_mat, y, rcond=None)
        s, c, c0 = beta
        A = float(_np.sqrt(s**2 + c**2))
        phi = float(_np.arctan2(c, s))
        C0 = float(c0)
        yhat = A * _np.sin(w * x + phi) + C0
        yfit = A * _np.sin(w * xs + phi) + C0
        return xs, yfit, {"A": A, "f": f0, "phi": phi, "C": C0}, metrics(y, yhat)

    def _plot_fit_overlay(
        self,
        series_label: str,
        xfit: np.ndarray,
        yfit: np.ndarray,
        params: dict,
        metrics: dict,
        *,
        show_eq: bool,
        show_resid: bool,
        x_seconds: bool = False,
    ):
        ax = self.canvas.ax
        ax.plot(xfit, yfit, "-", linewidth=2, color="#E67E22", label=f"fit: {series_label}")
        beautify_axes(ax, x_is_datetime=x_seconds)
        if show_eq:
            try:
                text = ", ".join([f"{k}={float(v):.3g}" for k, v in params.items() if isinstance(v, (int, float))])
                text += f" | R²={metrics.get('r2', float('nan')):.3f}, RMSE={metrics.get('rmse', float('nan')):.3g}"
                if x_seconds:
                    text += " | x (seconds from start)"
                ax.text(
                    0.01,
                    0.99,
                    text,
                    transform=ax.transAxes,
                    va="top",
                    ha="left",
                    fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.2", fc="#222", ec="#666", alpha=0.8),
                )
            except Exception:
                pass
        self.statusBar().showMessage(
            f"Fit completed. R^2={metrics.get('r2', float('nan')):.3f}  RMSE={metrics.get('rmse', float('nan')):.3g}"
        )

