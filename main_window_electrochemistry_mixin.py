from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QStyle

from analysis.electrochemistry import (
    cv_peak_metrics,
    ecsa_from_randles_slope,
    eis_basic_metrics,
    gcd_discharge_metrics,
    randles_sevcik_fit,
    tafel_fit,
)
from processors import beautify_axes

logger = logging.getLogger(__name__)


class MainWindowElectrochemistryMixin:
    """Electrochemistry specialty module.

    The math is pure in ``analysis.electrochemistry``; this mixin owns the
    worksheet prompts, result Books, Graph windows, menu, and activity panel.
    """

    def init_electrochemistry_module(self):
        from UI.electrochemistry_panel import ElectrochemistryPanel

        panel = ElectrochemistryPanel(self)
        panel.cv_requested.connect(self.ec_cv_peak_metrics)
        panel.randles_requested.connect(self.ec_randles_ecsa)
        panel.tafel_requested.connect(self.ec_tafel_analysis)
        panel.gcd_requested.connect(self.ec_gcd_metrics)
        panel.eis_requested.connect(self.ec_eis_analysis)
        self.electrochemistry_panel = panel

        self.register_specialty_module(
            module_id="electrochemistry",
            title="Electrochemistry",
            subtitle="CV, Randles-Sevcik, Tafel, GCD, EIS",
            panel=panel,
            icon_key="electrochemistry",
            fallback_icon=QStyle.StandardPixmap.SP_DriveNetIcon,
            actions=(
                ("CV Peak Metrics...", self.ec_cv_peak_metrics),
                ("Randles-Sevcik + ECSA...", self.ec_randles_ecsa),
                ("Tafel Analysis...", self.ec_tafel_analysis),
                ("GCD / Supercapacitor Metrics...", self.ec_gcd_metrics),
                ("EIS Nyquist / Bode...", self.ec_eis_analysis),
            ),
        )
        return

        try:
            icon = self._icon("electrochemistry", QStyle.StandardPixmap.SP_DriveNetIcon)
        except Exception:
            icon = None
        self.shell.register_context("electrochemistry", "EC", panel, icon=icon)

        menu = self.menuBar().addMenu("&Electrochemistry")
        menu.addAction("CV Peak Metrics...").triggered.connect(self.ec_cv_peak_metrics)
        menu.addAction("Randles-Sevcik + ECSA...").triggered.connect(self.ec_randles_ecsa)
        menu.addAction("Tafel Analysis...").triggered.connect(self.ec_tafel_analysis)
        menu.addAction("GCD / Supercapacitor Metrics...").triggered.connect(self.ec_gcd_metrics)
        menu.addAction("EIS Nyquist / Bode...").triggered.connect(self.ec_eis_analysis)

    def _ec_numeric_cols(self) -> list[str]:
        if self._df is None:
            return []
        return [str(c) for c in self._df.columns if pd.api.types.is_numeric_dtype(self._df[c])]

    def _ec_require_data(self) -> bool:
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("No data", "Open or select a Book with electrochemistry data first.")
            return False
        if len(self._ec_numeric_cols()) < 2:
            self.inform("Not enough numeric data", "Need at least two numeric columns in the active Book.")
            return False
        return True

    def _ec_values(self, col: str) -> np.ndarray:
        return pd.to_numeric(self._df[col], errors="coerce").to_numpy(dtype=float)

    def _ec_open_result(self, name: str, rows: list[dict]) -> str:
        return self._open_signal_result_book(name, pd.DataFrame(rows))

    def _ec_plot_xy(self, title: str, x, y, *, xlabel: str, ylabel: str, label: str = ""):
        self.tabs.add_tab()
        tab = self.tabs.currentWidget()
        ax = tab.get_axes()
        ax.plot(x, y, marker="o", linewidth=1.8, label=label or title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if label:
            ax.legend(loc="best")
        beautify_axes(ax, title=title)
        tab.draw()
        self._show_plot_view()
        return tab

    def ec_cv_peak_metrics(self):
        if not self._ec_require_data():
            return
        cols = self._ec_numeric_cols()
        res = self.ask_form("CV Peak Metrics", [
            {"name": "potential_col", "label": "Potential column (V)", "kind": "choice",
             "options": cols, "default": cols[0]},
            {"name": "current_col", "label": "Current column (A)", "kind": "choice",
             "options": cols, "default": cols[1] if len(cols) > 1 else cols[0]},
        ], description="Find oxidation/reduction peak current, peak potential, delta Ep, and peak ratio.")
        if res is None:
            return
        try:
            potential = self._ec_values(res["potential_col"])
            current = self._ec_values(res["current_col"])
            metrics = cv_peak_metrics(potential, current)
            rows = [{
                "metric": "oxidation_peak_current_A",
                "value": metrics.oxidation_peak_current,
                "potential_V": metrics.oxidation_peak_potential,
            }, {
                "metric": "reduction_peak_current_A",
                "value": metrics.reduction_peak_current,
                "potential_V": metrics.reduction_peak_potential,
            }, {
                "metric": "delta_ep_V",
                "value": metrics.delta_ep,
                "potential_V": np.nan,
            }, {
                "metric": "peak_current_ratio_abs_ipa_ipc",
                "value": metrics.peak_current_ratio,
                "potential_V": np.nan,
            }]
            target = self._ec_open_result("CV Peak Metrics", rows)
            self._ec_plot_xy(
                "CV Peak Metrics",
                potential,
                current,
                xlabel=res["potential_col"],
                ylabel=res["current_col"],
                label="CV",
            )
            self.inform(
                "CV Peak Metrics",
                "\n".join([
                    f"Oxidation: {metrics.oxidation_peak_current:.6g} A at {metrics.oxidation_peak_potential:.6g} V",
                    f"Reduction: {metrics.reduction_peak_current:.6g} A at {metrics.reduction_peak_potential:.6g} V",
                    f"Delta Ep: {metrics.delta_ep:.6g} V",
                    f"Result Book: {target}",
                ]),
            )
        except Exception as e:
            self.error_box("CV analysis failed", f"Reason: {e}")

    def ec_randles_ecsa(self):
        if not self._ec_require_data():
            return
        cols = self._ec_numeric_cols()
        res = self.ask_form("Randles-Sevcik + ECSA", [
            {"name": "scan_rate_col", "label": "Scan rate column (V/s)", "kind": "choice",
             "options": cols, "default": cols[0]},
            {"name": "peak_current_col", "label": "Peak current column (A)", "kind": "choice",
             "options": cols, "default": cols[1] if len(cols) > 1 else cols[0]},
            {"name": "n", "label": "Electron count n", "kind": "float", "default": 1.0,
             "min": 1e-9, "max": 100.0, "decimals": 4},
            {"name": "diffusion", "label": "Diffusion D (cm^2/s)", "kind": "float",
             "default": 1e-5, "min": 1e-20, "max": 1e6, "decimals": 12},
            {"name": "concentration", "label": "Concentration C (mol/cm^3)", "kind": "float",
             "default": 1e-6, "min": 1e-20, "max": 1e6, "decimals": 12},
        ], description="Fit ip vs sqrt(scan rate). ECSA uses the 298 K Randles-Sevcik equation.")
        if res is None:
            return
        try:
            scan_rate = self._ec_values(res["scan_rate_col"])
            peak_current = self._ec_values(res["peak_current_col"])
            fit = randles_sevcik_fit(scan_rate, peak_current)
            ecsa = ecsa_from_randles_slope(
                fit["slope"],
                n=float(res["n"]),
                diffusion_cm2_s=float(res["diffusion"]),
                concentration_mol_cm3=float(res["concentration"]),
            )
            rows = [{
                "slope_A_per_sqrt_V_s": fit["slope"],
                "intercept_A": fit["intercept"],
                "r_squared": fit["r_squared"],
                "ecsa_cm2": ecsa,
            }]
            target = self._ec_open_result("Randles ECSA", rows)
            self._ec_plot_xy(
                "Randles-Sevcik Fit",
                fit["x_sqrt_scan_rate"],
                peak_current[np.isfinite(scan_rate) & np.isfinite(peak_current)][: len(fit["x_sqrt_scan_rate"])],
                xlabel=f"sqrt({res['scan_rate_col']})",
                ylabel=res["peak_current_col"],
                label="data",
            )
            ax = self.tabs.currentWidget().get_axes()
            ax.plot(fit["x_sqrt_scan_rate"], fit["fit"], linewidth=2.2, label=f"fit R2={fit['r_squared']:.4g}")
            ax.legend(loc="best")
            self.tabs.currentWidget().draw()
            self.inform("Randles-Sevcik + ECSA", f"ECSA: {ecsa:.6g} cm^2\nR^2: {fit['r_squared']:.6g}\nResult Book: {target}")
        except Exception as e:
            self.error_box("Randles-Sevcik failed", f"Reason: {e}")

    def ec_tafel_analysis(self):
        if not self._ec_require_data():
            return
        cols = self._ec_numeric_cols()
        res = self.ask_form("Tafel Analysis", [
            {"name": "eta_col", "label": "Overpotential column (V)", "kind": "choice",
             "options": cols, "default": cols[0]},
            {"name": "current_col", "label": "Current column (A)", "kind": "choice",
             "options": cols, "default": cols[1] if len(cols) > 1 else cols[0]},
        ], description="Fit overpotential against log10(abs(current)).")
        if res is None:
            return
        try:
            eta = self._ec_values(res["eta_col"])
            current = self._ec_values(res["current_col"])
            fit = tafel_fit(eta, current)
            target = self._ec_open_result("Tafel Analysis", [{
                "tafel_slope_mV_dec": fit["slope_mv_dec"],
                "intercept_V": fit["intercept_v"],
                "exchange_current_A": fit["exchange_current_a"],
                "r_squared": fit["r_squared"],
            }])
            self._ec_plot_xy(
                "Tafel Analysis",
                fit["log_current"],
                eta[np.isfinite(eta) & np.isfinite(current) & (np.abs(current) > 0)][: len(fit["log_current"])],
                xlabel=f"log10(abs({res['current_col']}))",
                ylabel=res["eta_col"],
                label="data",
            )
            ax = self.tabs.currentWidget().get_axes()
            ax.plot(fit["log_current"], fit["fit"], linewidth=2.2, label=f"fit {fit['slope_mv_dec']:.4g} mV/dec")
            ax.legend(loc="best")
            self.tabs.currentWidget().draw()
            self.inform("Tafel Analysis", f"Slope: {fit['slope_mv_dec']:.6g} mV/dec\nR^2: {fit['r_squared']:.6g}\nResult Book: {target}")
        except Exception as e:
            self.error_box("Tafel analysis failed", f"Reason: {e}")

    def ec_gcd_metrics(self):
        if not self._ec_require_data():
            return
        cols = self._ec_numeric_cols()
        res = self.ask_form("GCD / Supercapacitor Metrics", [
            {"name": "time_col", "label": "Time column (s)", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "voltage_col", "label": "Voltage column (V)", "kind": "choice",
             "options": cols, "default": cols[1] if len(cols) > 1 else cols[0]},
            {"name": "current_a", "label": "Discharge current (A)", "kind": "float",
             "default": 0.001, "min": -1e12, "max": 1e12, "decimals": 9},
            {"name": "mass_g", "label": "Active mass (g, 0 = skip gravimetric)", "kind": "float",
             "default": 0.0, "min": 0.0, "max": 1e12, "decimals": 9},
        ], description="Use the segment after maximum voltage as discharge.")
        if res is None:
            return
        try:
            mass = float(res["mass_g"]) or None
            time = self._ec_values(res["time_col"])
            voltage = self._ec_values(res["voltage_col"])
            metrics = gcd_discharge_metrics(
                time,
                voltage,
                current_a=float(res["current_a"]),
                mass_g=mass,
            )
            target = self._ec_open_result("GCD Metrics", [{
                "discharge_time_s": metrics.discharge_time_s,
                "voltage_window_V": metrics.voltage_window_v,
                "capacitance_F": metrics.capacitance_f,
                "specific_capacitance_F_g": metrics.specific_capacitance_f_g,
                "energy_Wh_kg": metrics.energy_wh_kg,
                "power_W_kg": metrics.power_w_kg,
            }])
            self._ec_plot_xy(
                "GCD Curve",
                time,
                voltage,
                xlabel=res["time_col"],
                ylabel=res["voltage_col"],
                label="GCD",
            )
            self.inform("GCD Metrics", f"Capacitance: {metrics.capacitance_f:.6g} F\nResult Book: {target}")
        except Exception as e:
            self.error_box("GCD analysis failed", f"Reason: {e}")

    def ec_eis_analysis(self):
        if not self._ec_require_data():
            return
        cols = self._ec_numeric_cols()
        res = self.ask_form("EIS Nyquist / Bode", [
            {"name": "freq_col", "label": "Frequency column (Hz)", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "zreal_col", "label": "Z real column (ohm)", "kind": "choice",
             "options": cols, "default": cols[1] if len(cols) > 1 else cols[0]},
            {"name": "zimag_col", "label": "Z imaginary column (ohm)", "kind": "choice",
             "options": cols, "default": cols[2] if len(cols) > 2 else cols[-1]},
        ], description="Estimate Rs/Rct and create Nyquist plus Bode result columns.")
        if res is None:
            return
        try:
            freq = self._ec_values(res["freq_col"])
            zr = self._ec_values(res["zreal_col"])
            zi = self._ec_values(res["zimag_col"])
            metrics = eis_basic_metrics(freq, zr, zi)
            zmod = np.sqrt(zr ** 2 + zi ** 2)
            phase = np.degrees(np.arctan2(zi, zr))
            result_df = pd.DataFrame({
                "frequency_Hz": freq,
                "zreal_ohm": zr,
                "zimag_ohm": zi,
                "minus_zimag_ohm": -zi,
                "zmod_ohm": zmod,
                "phase_deg": phase,
            })
            result_df.attrs["metrics"] = {
                "rs_ohm": metrics.rs_ohm,
                "rct_ohm": metrics.rct_ohm,
                "zreal_at_low_freq_ohm": metrics.zreal_at_low_freq_ohm,
            }
            target = self._open_signal_result_book("EIS Bode Data", result_df)
            self._ec_plot_xy("EIS Nyquist", zr, -zi, xlabel=res["zreal_col"], ylabel=f"-{res['zimag_col']}", label="Nyquist")
            self.inform(
                "EIS Metrics",
                f"Rs: {metrics.rs_ohm:.6g} ohm\nRct: {metrics.rct_ohm:.6g} ohm\nResult Book: {target}",
            )
        except Exception as e:
            self.error_box("EIS analysis failed", f"Reason: {e}")
