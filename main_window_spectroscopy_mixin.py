from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QStyle

from analysis.spectroscopy import (
    baseline_correct,
    detect_spectrum_peaks,
    normalize_spectrum,
    raman_d_g_ratio,
    scherrer_crystallite_size,
    tauc_band_gap,
)
from processors import beautify_axes

logger = logging.getLogger(__name__)


class MainWindowSpectroscopyMixin:
    """Spectroscopy specialty module: spectrum preprocessing, peaks, Raman, Tauc, and XRD."""

    def init_spectroscopy_module(self):
        from UI.spectroscopy_panel import SpectroscopyPanel

        panel = SpectroscopyPanel(self)
        panel.preprocess_requested.connect(self.sp_preprocess_spectrum)
        panel.peaks_requested.connect(self.sp_peak_table)
        panel.raman_requested.connect(self.sp_raman_dg_ratio)
        panel.tauc_requested.connect(self.sp_tauc_band_gap)
        panel.xrd_requested.connect(self.sp_xrd_scherrer)
        self.spectroscopy_panel = panel

        self.register_specialty_module(
            module_id="spectroscopy",
            title="Spectroscopy",
            subtitle="Baseline, peaks, Raman, Tauc, XRD",
            panel=panel,
            icon_key="spectroscopy",
            fallback_icon=QStyle.StandardPixmap.SP_FileDialogDetailedView,
            actions=(
                ("Baseline + Normalize...", self.sp_preprocess_spectrum),
                ("Peak Table...", self.sp_peak_table),
                ("Raman D/G Ratio...", self.sp_raman_dg_ratio),
                ("Tauc Band Gap...", self.sp_tauc_band_gap),
                ("XRD Scherrer Size...", self.sp_xrd_scherrer),
            ),
        )

    def _sp_numeric_cols(self) -> list[str]:
        if self._df is None:
            return []
        return [str(c) for c in self._df.columns if pd.api.types.is_numeric_dtype(self._df[c])]

    def _sp_require_data(self) -> bool:
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("No data", "Open or select a Book with spectroscopy data first.")
            return False
        if len(self._sp_numeric_cols()) < 2:
            self.inform("Not enough numeric data", "Need at least two numeric columns in the active Book.")
            return False
        return True

    def _sp_values(self, col: str) -> np.ndarray:
        return pd.to_numeric(self._df[col], errors="coerce").to_numpy(dtype=float)

    def _sp_plot_xy(self, title: str, series: list[tuple[np.ndarray, np.ndarray, str]], *, xlabel: str, ylabel: str):
        self.tabs.add_tab()
        tab = self.tabs.currentWidget()
        ax = tab.get_axes()
        for x, y, label in series:
            ax.plot(x, y, linewidth=1.8, label=label)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if len(series) > 1 or series[0][2]:
            ax.legend(loc="best")
        beautify_axes(ax, title=title)
        tab.draw()
        self._show_plot_view()
        return tab

    def sp_preprocess_spectrum(self):
        if not self._sp_require_data():
            return
        cols = self._sp_numeric_cols()
        res = self.ask_form("Spectrum Baseline + Normalize", [
            {"name": "x_col", "label": "X column", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "y_col", "label": "Intensity column", "kind": "choice", "options": cols, "default": cols[1]},
            {"name": "degree", "label": "Baseline polynomial degree", "kind": "int", "default": 2, "min": 0, "max": 5},
            {"name": "quantile", "label": "Baseline lower quantile", "kind": "float", "default": 0.2, "min": 0.01, "max": 1.0, "decimals": 3},
            {"name": "normalize", "label": "Normalize", "kind": "choice", "options": ["max", "minmax", "area"], "default": "max"},
        ], description="Create a corrected/normalized spectrum result Book and plot raw vs corrected.")
        if res is None:
            return
        try:
            x = self._sp_values(res["x_col"])
            y = self._sp_values(res["y_col"])
            corrected = baseline_correct(x, y, degree=int(res["degree"]), quantile=float(res["quantile"]))
            norm = normalize_spectrum(corrected["corrected"], mode=res["normalize"])
            df = pd.DataFrame({
                res["x_col"]: corrected["x"],
                "raw_intensity": corrected["raw"],
                "baseline": corrected["baseline"],
                "corrected": corrected["corrected"],
                f"normalized_{res['normalize']}": norm,
            })
            target = self._open_signal_result_book("Spectrum Preprocess", df)
            self._sp_plot_xy(
                "Spectrum Baseline Correction",
                [
                    (corrected["x"], corrected["raw"], "raw"),
                    (corrected["x"], corrected["baseline"], "baseline"),
                    (corrected["x"], corrected["corrected"], "corrected"),
                ],
                xlabel=res["x_col"],
                ylabel=res["y_col"],
            )
            self.inform("Spectrum Preprocess", f"Result Book: {target}")
        except Exception as e:
            self.error_box("Spectrum preprocessing failed", f"Reason: {e}")

    def sp_peak_table(self):
        if not self._sp_require_data():
            return
        cols = self._sp_numeric_cols()
        res = self.ask_form("Spectrum Peak Table", [
            {"name": "x_col", "label": "X column", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "y_col", "label": "Intensity column", "kind": "choice", "options": cols, "default": cols[1]},
            {"name": "threshold_rel", "label": "Relative threshold", "kind": "float", "default": 0.2, "min": 0.0, "max": 1.0, "decimals": 3},
            {"name": "min_distance", "label": "Minimum distance (points)", "kind": "int", "default": 3, "min": 1, "max": 100000},
        ], description="Detect local maxima and estimate FWHM/area.")
        if res is None:
            return
        try:
            x = self._sp_values(res["x_col"])
            y = self._sp_values(res["y_col"])
            peaks = detect_spectrum_peaks(x, y, threshold_rel=float(res["threshold_rel"]), min_distance=int(res["min_distance"]))
            rows = [{"peak_x": p.x, "peak_y": p.y, "fwhm": p.fwhm, "area": p.area} for p in peaks]
            target = self._open_signal_result_book("Spectrum Peaks", pd.DataFrame(rows))
            self._sp_plot_xy("Spectrum Peaks", [(x, y, "spectrum")], xlabel=res["x_col"], ylabel=res["y_col"])
            ax = self.tabs.currentWidget().get_axes()
            if peaks:
                ax.scatter([p.x for p in peaks], [p.y for p in peaks], s=36, label="peaks", zorder=5)
                ax.legend(loc="best")
                self.tabs.currentWidget().draw()
            self.inform("Spectrum Peak Table", f"Peaks: {len(peaks)}\nResult Book: {target}")
        except Exception as e:
            self.error_box("Peak detection failed", f"Reason: {e}")

    def sp_raman_dg_ratio(self):
        if not self._sp_require_data():
            return
        cols = self._sp_numeric_cols()
        res = self.ask_form("Raman D/G Ratio", [
            {"name": "x_col", "label": "Raman shift column (cm^-1)", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "y_col", "label": "Intensity column", "kind": "choice", "options": cols, "default": cols[1]},
            {"name": "d_min", "label": "D min", "kind": "float", "default": 1200.0, "min": -1e9, "max": 1e9, "decimals": 2},
            {"name": "d_max", "label": "D max", "kind": "float", "default": 1450.0, "min": -1e9, "max": 1e9, "decimals": 2},
            {"name": "g_min", "label": "G min", "kind": "float", "default": 1500.0, "min": -1e9, "max": 1e9, "decimals": 2},
            {"name": "g_max", "label": "G max", "kind": "float", "default": 1700.0, "min": -1e9, "max": 1e9, "decimals": 2},
        ], description="Find D/G peak intensities and compute ID/IG.")
        if res is None:
            return
        try:
            x = self._sp_values(res["x_col"])
            y = self._sp_values(res["y_col"])
            metrics = raman_d_g_ratio(x, y, d_range=(res["d_min"], res["d_max"]), g_range=(res["g_min"], res["g_max"]))
            target = self._open_signal_result_book("Raman DG Ratio", pd.DataFrame([metrics]))
            self._sp_plot_xy("Raman D/G Ratio", [(x, y, "Raman")], xlabel=res["x_col"], ylabel=res["y_col"])
            ax = self.tabs.currentWidget().get_axes()
            ax.scatter([metrics["d_position"], metrics["g_position"]], [metrics["d_intensity"], metrics["g_intensity"]], s=48, label="D/G peaks", zorder=5)
            ax.legend(loc="best")
            self.tabs.currentWidget().draw()
            self.inform("Raman D/G Ratio", f"ID/IG: {metrics['id_ig']:.6g}\nResult Book: {target}")
        except Exception as e:
            self.error_box("Raman D/G failed", f"Reason: {e}")

    def sp_tauc_band_gap(self):
        if not self._sp_require_data():
            return
        cols = self._sp_numeric_cols()
        res = self.ask_form("Tauc Band Gap", [
            {"name": "energy_col", "label": "Photon energy column (eV)", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "abs_col", "label": "Absorbance/alpha column", "kind": "choice", "options": cols, "default": cols[1]},
            {"name": "exponent", "label": "Tauc exponent", "kind": "choice", "options": ["2.0", "0.5"], "default": "2.0"},
            {"name": "fit_fraction", "label": "Fit top fraction", "kind": "float", "default": 0.35, "min": 0.05, "max": 1.0, "decimals": 3},
        ], description="Direct allowed usually uses exponent 2; indirect often uses 0.5.")
        if res is None:
            return
        try:
            energy = self._sp_values(res["energy_col"])
            absorbance = self._sp_values(res["abs_col"])
            fit = tauc_band_gap(energy, absorbance, exponent=float(res["exponent"]), fit_fraction=float(res["fit_fraction"]))
            target = self._open_signal_result_book("Tauc Band Gap", pd.DataFrame([{
                "band_gap_eV": fit.band_gap_ev,
                "slope": fit.slope,
                "intercept": fit.intercept,
                "r_squared": fit.r_squared,
            }]))
            tauc_y = np.power(np.clip(energy * absorbance, 0, None), float(res["exponent"]))
            self._sp_plot_xy("Tauc Plot", [(energy, tauc_y, "Tauc data"), (fit.fit_x, fit.fit_y, "linear fit")], xlabel=res["energy_col"], ylabel="(alpha hnu)^n")
            self.inform("Tauc Band Gap", f"Eg: {fit.band_gap_ev:.6g} eV\nR^2: {fit.r_squared:.6g}\nResult Book: {target}")
        except Exception as e:
            self.error_box("Tauc fit failed", f"Reason: {e}")

    def sp_xrd_scherrer(self):
        res = self.ask_form("XRD Scherrer Size", [
            {"name": "two_theta", "label": "Peak 2theta (deg)", "kind": "float", "default": 26.5, "min": 0.0, "max": 180.0, "decimals": 4},
            {"name": "fwhm", "label": "FWHM beta (deg)", "kind": "float", "default": 0.2, "min": 1e-9, "max": 180.0, "decimals": 6},
            {"name": "wavelength", "label": "X-ray wavelength (Angstrom)", "kind": "float", "default": 1.5406, "min": 1e-9, "max": 100.0, "decimals": 6},
            {"name": "shape_factor", "label": "Shape factor K", "kind": "float", "default": 0.9, "min": 1e-9, "max": 10.0, "decimals": 4},
        ], description="Scherrer size D = K lambda / (beta cos theta).")
        if res is None:
            return
        try:
            size_a = scherrer_crystallite_size(res["two_theta"], res["fwhm"], res["wavelength"], res["shape_factor"])
            rows = [{
                "two_theta_deg": res["two_theta"],
                "fwhm_deg": res["fwhm"],
                "wavelength_A": res["wavelength"],
                "shape_factor": res["shape_factor"],
                "crystallite_size_A": size_a,
                "crystallite_size_nm": size_a / 10.0,
            }]
            target = self._open_signal_result_book("XRD Scherrer Size", pd.DataFrame(rows))
            self.inform("XRD Scherrer Size", f"Crystallite size: {size_a / 10.0:.6g} nm\nResult Book: {target}")
        except Exception as e:
            self.error_box("Scherrer calculation failed", f"Reason: {e}")
