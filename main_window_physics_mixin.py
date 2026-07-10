from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QStyle

from analysis.physics_lab import (
    ohms_law_fit,
    pendulum_gravity,
    propagate_power_product,
    rc_time_constant,
)
from processors import beautify_axes

logger = logging.getLogger(__name__)


class MainWindowPhysicsMixin:
    """Physics / General Lab specialty module."""

    def init_physics_module(self):
        from UI.physics_panel import PhysicsPanel

        panel = PhysicsPanel(self)
        panel.ohm_requested.connect(self.ph_ohms_law)
        panel.rc_requested.connect(self.ph_rc_time_constant)
        panel.pendulum_requested.connect(self.ph_pendulum_gravity)
        panel.uncertainty_requested.connect(self.ph_uncertainty_propagation)
        self.physics_panel = panel

        self.register_specialty_module(
            module_id="physics_lab",
            title="Physics / General Lab",
            subtitle="Ohm, RC, pendulum, uncertainty",
            panel=panel,
            icon_key="physics_lab",
            fallback_icon=QStyle.StandardPixmap.SP_ComputerIcon,
            actions=(
                ("Ohm's Law Fit...", self.ph_ohms_law),
                ("RC Time Constant...", self.ph_rc_time_constant),
                ("Pendulum g Fit...", self.ph_pendulum_gravity),
                ("Uncertainty Propagation...", self.ph_uncertainty_propagation),
            ),
        )

    def _ph_numeric_cols(self) -> list[str]:
        if self._df is None:
            return []
        return [str(c) for c in self._df.columns if pd.api.types.is_numeric_dtype(self._df[c])]

    def _ph_require_data(self, min_numeric: int = 2) -> bool:
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("No data", "Open or select a Book with physics lab data first.")
            return False
        if len(self._ph_numeric_cols()) < min_numeric:
            self.inform("Not enough numeric data", f"Need at least {min_numeric} numeric columns in the active Book.")
            return False
        return True

    def _ph_values(self, col: str) -> np.ndarray:
        return pd.to_numeric(self._df[col], errors="coerce").to_numpy(dtype=float)

    def _ph_plot_xy(self, title: str, series: list[tuple[np.ndarray, np.ndarray, str]], *, xlabel: str, ylabel: str):
        self.tabs.add_tab()
        tab = self.tabs.currentWidget()
        ax = tab.get_axes()
        for x, y, label in series:
            ax.plot(x, y, marker="o", linewidth=1.8, label=label)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.legend(loc="best")
        beautify_axes(ax, title=title)
        tab.draw()
        self._show_plot_view()
        return tab

    def ph_ohms_law(self):
        if not self._ph_require_data(2):
            return
        cols = self._ph_numeric_cols()
        res = self.ask_form("Ohm's Law Fit", [
            {"name": "current_col", "label": "Current column (A)", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "voltage_col", "label": "Voltage column (V)", "kind": "choice", "options": cols, "default": cols[1]},
        ], description="Fit V = R I and report resistance plus conductance.")
        if res is None:
            return
        try:
            current = self._ph_values(res["current_col"])
            voltage = self._ph_values(res["voltage_col"])
            fit = ohms_law_fit(current, voltage)
            target = self._open_signal_result_book("Ohm Law Fit", pd.DataFrame([{
                "resistance_ohm": fit.resistance_ohm,
                "conductance_S": fit.conductance_s,
                "intercept_V": fit.intercept_v,
                "r_squared": fit.r_squared,
            }]))
            self._ph_plot_xy("Ohm's Law Fit", [(current, voltage, "data"), (current[np.argsort(current)], fit.fit_voltage[np.argsort(current)], "fit")], xlabel=res["current_col"], ylabel=res["voltage_col"])
            self.inform("Ohm's Law Fit", f"R: {fit.resistance_ohm:.6g} ohm\nResult Book: {target}")
        except Exception as e:
            self.error_box("Ohm's law fit failed", f"Reason: {e}")

    def ph_rc_time_constant(self):
        if not self._ph_require_data(2):
            return
        cols = self._ph_numeric_cols()
        res = self.ask_form("RC Time Constant", [
            {"name": "time_col", "label": "Time column (s)", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "value_col", "label": "Voltage/value column", "kind": "choice", "options": cols, "default": cols[1]},
            {"name": "mode", "label": "Mode", "kind": "choice", "options": ["charge", "discharge"], "default": "charge"},
        ], description="Linearize the exponential region and estimate tau.")
        if res is None:
            return
        try:
            t = self._ph_values(res["time_col"])
            y = self._ph_values(res["value_col"])
            fit = rc_time_constant(t, y, mode=res["mode"])
            target = self._open_signal_result_book("RC Time Constant", pd.DataFrame([{
                "tau_s": fit.tau_s,
                "initial_value": fit.initial_value,
                "final_value": fit.final_value,
                "r_squared": fit.r_squared,
            }]))
            order = np.argsort(t)
            self._ph_plot_xy("RC Time Constant", [(t[order], y[order], "data"), (t[order], fit.fit_y[order], "fit")], xlabel=res["time_col"], ylabel=res["value_col"])
            self.inform("RC Time Constant", f"tau: {fit.tau_s:.6g} s\nResult Book: {target}")
        except Exception as e:
            self.error_box("RC analysis failed", f"Reason: {e}")

    def ph_pendulum_gravity(self):
        if not self._ph_require_data(2):
            return
        cols = self._ph_numeric_cols()
        res = self.ask_form("Pendulum g Fit", [
            {"name": "length_col", "label": "Length column (m)", "kind": "choice", "options": cols, "default": cols[0]},
            {"name": "period_col", "label": "Period column (s)", "kind": "choice", "options": cols, "default": cols[1]},
        ], description="Fit T^2 = (4 pi^2 / g) L + intercept.")
        if res is None:
            return
        try:
            length = self._ph_values(res["length_col"])
            period = self._ph_values(res["period_col"])
            fit = pendulum_gravity(length, period)
            target = self._open_signal_result_book("Pendulum Gravity", pd.DataFrame([{
                "gravity_m_s2": fit.gravity_m_s2,
                "slope_s2_m": fit.slope_s2_m,
                "intercept_s2": fit.intercept_s2,
                "r_squared": fit.r_squared,
            }]))
            self._ph_plot_xy("Pendulum g Fit", [(length, period ** 2, "T^2"), (length[np.argsort(length)], fit.fit_period_squared[np.argsort(length)], "fit")], xlabel=res["length_col"], ylabel=f"{res['period_col']}^2")
            self.inform("Pendulum g Fit", f"g: {fit.gravity_m_s2:.6g} m/s^2\nResult Book: {target}")
        except Exception as e:
            self.error_box("Pendulum fit failed", f"Reason: {e}")

    def ph_uncertainty_propagation(self):
        res = self.ask_form("Uncertainty Propagation", [
            {"name": "coefficient", "label": "Coefficient c", "kind": "float", "default": 1.0, "min": -1e12, "max": 1e12, "decimals": 6},
            {"name": "a_value", "label": "A value", "kind": "float", "default": 1.0, "min": -1e12, "max": 1e12, "decimals": 6},
            {"name": "a_unc", "label": "A uncertainty", "kind": "float", "default": 0.01, "min": 0.0, "max": 1e12, "decimals": 6},
            {"name": "a_power", "label": "A power", "kind": "float", "default": 1.0, "min": -10.0, "max": 10.0, "decimals": 4},
            {"name": "b_value", "label": "B value", "kind": "float", "default": 1.0, "min": -1e12, "max": 1e12, "decimals": 6},
            {"name": "b_unc", "label": "B uncertainty", "kind": "float", "default": 0.0, "min": 0.0, "max": 1e12, "decimals": 6},
            {"name": "b_power", "label": "B power", "kind": "float", "default": 0.0, "min": -10.0, "max": 10.0, "decimals": 4},
            {"name": "c_value", "label": "C value", "kind": "float", "default": 1.0, "min": -1e12, "max": 1e12, "decimals": 6},
            {"name": "c_unc", "label": "C uncertainty", "kind": "float", "default": 0.0, "min": 0.0, "max": 1e12, "decimals": 6},
            {"name": "c_power", "label": "C power", "kind": "float", "default": 0.0, "min": -10.0, "max": 10.0, "decimals": 4},
        ], description="Q = c A^a B^b C^c, independent uncertainties.")
        if res is None:
            return
        try:
            out = propagate_power_product(
                [res["a_value"], res["b_value"], res["c_value"]],
                [res["a_unc"], res["b_unc"], res["c_unc"]],
                [res["a_power"], res["b_power"], res["c_power"]],
                coefficient=res["coefficient"],
            )
            target = self._open_signal_result_book("Uncertainty Propagation", pd.DataFrame([{
                "value": out.value,
                "uncertainty": out.uncertainty,
                "relative_uncertainty": out.relative_uncertainty,
            }]))
            self.inform("Uncertainty Propagation", f"Q: {out.value:.6g} ± {out.uncertainty:.6g}\nResult Book: {target}")
        except Exception as e:
            self.error_box("Uncertainty propagation failed", f"Reason: {e}")
