from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QStyle

from analysis.materials import (
    arrhenius_activation_energy,
    conductivity_from_iv,
    rank_materials,
    thermal_transition_metrics,
)
from processors import beautify_axes

logger = logging.getLogger(__name__)


class MainWindowMaterialsMixin:
    """Materials Science specialty module."""

    def init_materials_module(self):
        from UI.materials_panel import MaterialsPanel

        panel = MaterialsPanel(self)
        panel.conductivity_requested.connect(self.mat_conductivity_resistivity)
        panel.arrhenius_requested.connect(self.mat_arrhenius_activation)
        panel.thermal_requested.connect(self.mat_thermal_metrics)
        panel.ranking_requested.connect(self.mat_rank_samples)
        self.materials_panel = panel

        self.register_specialty_module(
            module_id="materials",
            title="Materials Science",
            subtitle="Transport, Arrhenius, thermal, ranking",
            panel=panel,
            icon_key="materials",
            fallback_icon=QStyle.StandardPixmap.SP_DriveFDIcon,
            actions=(
                ("Conductivity / Resistivity...", self.mat_conductivity_resistivity),
                ("Arrhenius Activation Energy...", self.mat_arrhenius_activation),
                ("TGA / DSC Thermal Metrics...", self.mat_thermal_metrics),
                ("Rank Samples...", self.mat_rank_samples),
            ),
        )

    def _mat_numeric_cols(self) -> list[str]:
        if self._df is None:
            return []
        return [str(c) for c in self._df.columns if pd.api.types.is_numeric_dtype(self._df[c])]

    def _mat_require_data(self, min_numeric: int = 2) -> bool:
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("No data", "Open or select a Book with materials data first.")
            return False
        if len(self._mat_numeric_cols()) < min_numeric:
            self.inform("Not enough numeric data", f"Need at least {min_numeric} numeric columns in the active Book.")
            return False
        return True

    def _mat_values(self, col: str) -> np.ndarray:
        return pd.to_numeric(self._df[col], errors="coerce").to_numpy(dtype=float)

    def _mat_plot_xy(self, title: str, series: list[tuple[np.ndarray, np.ndarray, str]], *, xlabel: str, ylabel: str):
        self.tabs.add_tab()
        tab = self.tabs.currentWidget()
        ax = tab.get_axes()
        for x, y, label in series:
            ax.plot(x, y, marker="o", linewidth=1.8, label=label)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if series:
            ax.legend(loc="best")
        beautify_axes(ax, title=title)
        tab.draw()
        self._show_plot_view()
        return tab

    def mat_conductivity_resistivity(self):
        if not self._mat_require_data(2):
            return
        cols = self._mat_numeric_cols()
        res = self.ask_form("Conductivity / Resistivity", [
            {"name": "voltage_col", "label": "Voltage column (V)", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "current_col", "label": "Current column (A)", "kind": "choice", "options": cols, "default": cols[1]},
            {"name": "length_m", "label": "Length L (m)", "kind": "float", "default": 0.01, "min": 1e-12, "max": 1e12, "decimals": 9},
            {"name": "area_m2", "label": "Cross-section area A (m^2)", "kind": "float", "default": 1e-6, "min": 1e-18, "max": 1e12, "decimals": 12},
            {"name": "thickness_m", "label": "Film thickness (m, 0 = skip sheet R)", "kind": "float", "default": 0.0, "min": 0.0, "max": 1e12, "decimals": 12},
        ], description="Fit V = R I, then compute rho = R A / L and sigma = 1/rho.")
        if res is None:
            return
        try:
            voltage = self._mat_values(res["voltage_col"])
            current = self._mat_values(res["current_col"])
            thickness = float(res["thickness_m"]) or None
            metrics = conductivity_from_iv(
                voltage,
                current,
                length_m=float(res["length_m"]),
                area_m2=float(res["area_m2"]),
                thickness_m=thickness,
            )
            target = self._open_signal_result_book("Materials Conductivity", pd.DataFrame([{
                "resistance_ohm": metrics.resistance_ohm,
                "resistivity_ohm_m": metrics.resistivity_ohm_m,
                "conductivity_S_m": metrics.conductivity_s_m,
                "sheet_resistance_ohm_sq": metrics.sheet_resistance_ohm_sq,
                "r_squared": metrics.r_squared,
            }]))
            self._mat_plot_xy("I-V Conductivity Fit", [(current, voltage, "I-V")], xlabel=res["current_col"], ylabel=res["voltage_col"])
            self.inform("Conductivity / Resistivity", f"Conductivity: {metrics.conductivity_s_m:.6g} S/m\nResult Book: {target}")
        except Exception as e:
            self.error_box("Conductivity calculation failed", f"Reason: {e}")

    def mat_arrhenius_activation(self):
        if not self._mat_require_data(2):
            return
        cols = self._mat_numeric_cols()
        res = self.ask_form("Arrhenius Activation Energy", [
            {"name": "temperature_col", "label": "Temperature column (K)", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "conductivity_col", "label": "Conductivity column (S/m)", "kind": "choice", "options": cols, "default": cols[1]},
        ], description="Fit ln(sigma) = ln(sigma0) - Ea/(kB T).")
        if res is None:
            return
        try:
            temp = self._mat_values(res["temperature_col"])
            sigma = self._mat_values(res["conductivity_col"])
            fit = arrhenius_activation_energy(temp, sigma)
            target = self._open_signal_result_book("Arrhenius Activation", pd.DataFrame([{
                "activation_energy_eV": fit.activation_energy_ev,
                "prefactor_S_m": fit.prefactor,
                "slope": fit.slope,
                "intercept": fit.intercept,
                "r_squared": fit.r_squared,
            }]))
            mask = (np.isfinite(temp) & np.isfinite(sigma) & (temp > 0) & (sigma > 0))
            inv_t = 1.0 / temp[mask]
            ln_sigma = np.log(sigma[mask])
            self._mat_plot_xy("Arrhenius Activation Energy", [(inv_t, ln_sigma, "data"), (fit.inv_temperature, fit.fit_ln_conductivity, "fit")], xlabel=f"1/{res['temperature_col']}", ylabel=f"ln({res['conductivity_col']})")
            self.inform("Arrhenius Activation Energy", f"Ea: {fit.activation_energy_ev:.6g} eV\nR^2: {fit.r_squared:.6g}\nResult Book: {target}")
        except Exception as e:
            self.error_box("Arrhenius fit failed", f"Reason: {e}")

    def mat_thermal_metrics(self):
        if not self._mat_require_data(2):
            return
        cols = self._mat_numeric_cols()
        res = self.ask_form("TGA / DSC Thermal Metrics", [
            {"name": "temperature_col", "label": "Temperature column", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "value_col", "label": "Mass/heat-flow column", "kind": "choice", "options": cols, "default": cols[1]},
            {"name": "mode", "label": "Mode", "kind": "choice", "options": ["tga_loss", "dsc_peak"], "default": "tga_loss"},
            {"name": "onset_fraction", "label": "Onset fraction", "kind": "float", "default": 0.05, "min": 0.001, "max": 0.999, "decimals": 3},
        ], description="Estimate onset and derivative peak temperature.")
        if res is None:
            return
        try:
            temp = self._mat_values(res["temperature_col"])
            val = self._mat_values(res["value_col"])
            metrics = thermal_transition_metrics(temp, val, mode=res["mode"], onset_fraction=float(res["onset_fraction"]))
            target = self._open_signal_result_book("Thermal Metrics", pd.DataFrame([{
                "onset_temperature": metrics.onset_temperature,
                "peak_temperature": metrics.peak_temperature,
                "peak_rate": metrics.peak_rate,
                "final_value": metrics.final_value,
            }]))
            self._mat_plot_xy("Thermal Metrics", [(temp, val, res["mode"])], xlabel=res["temperature_col"], ylabel=res["value_col"])
            self.inform("TGA / DSC Thermal Metrics", f"Onset: {metrics.onset_temperature:.6g}\nPeak: {metrics.peak_temperature:.6g}\nResult Book: {target}")
        except Exception as e:
            self.error_box("Thermal analysis failed", f"Reason: {e}")

    def mat_rank_samples(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("No data", "Open or select a Book with materials data first.")
            return
        cols = [str(c) for c in self._df.columns]
        numeric = self._mat_numeric_cols()
        if not numeric:
            self.inform("Not enough numeric data", "Need at least one numeric metric column.")
            return
        res = self.ask_form("Rank Material Samples", [
            {"name": "sample_col", "label": "Sample column", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "metric_col", "label": "Metric column", "kind": "choice", "options": numeric, "default": numeric[0]},
            {"name": "group_col", "label": "Group column", "kind": "choice", "options": ["(none)"] + cols, "default": "(none)"},
            {"name": "direction", "label": "Direction", "kind": "choice", "options": ["higher is better", "lower is better"], "default": "higher is better"},
        ], description="Rank samples globally or within each composition/group.")
        if res is None:
            return
        try:
            group_col = None if res["group_col"] == "(none)" else res["group_col"]
            ranked = rank_materials(
                self._df,
                sample_col=res["sample_col"],
                metric_col=res["metric_col"],
                group_col=group_col,
                higher_is_better=res["direction"] == "higher is better",
            )
            target = self._open_signal_result_book("Materials Ranking", ranked)
            self.inform("Rank Material Samples", f"Ranked samples: {len(ranked)}\nResult Book: {target}")
        except Exception as e:
            self.error_box("Sample ranking failed", f"Reason: {e}")
