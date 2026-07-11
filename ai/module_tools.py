"""AI tools for the specialized science modules.

Each tool wraps the pure analysis functions in ``analysis/*`` (Gas Sensor,
Electrochemistry, Spectroscopy, Materials, Physics) so the assistant can run a
domain analysis on the active data non-interactively. Registered by
:func:`ai.app_tools.build_app_registry` via :func:`register_module_tools`.

Handlers are defensive: they resolve columns (explicit arg → first/second
numeric), never raise, and return a short text summary for the model.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from ai.app_tools import _active_df, _numeric_columns, _resolve_y_column, _sync_new_column

logger = logging.getLogger(__name__)


def _two_numeric(df, args: Dict[str, Any], a_key: str, b_key: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve two columns: explicit args first, else the first two numeric ones."""
    numeric = _numeric_columns(df)
    a = args.get(a_key)
    if a not in getattr(df, "columns", []):
        a = numeric[0] if len(numeric) >= 1 else None
    b = args.get(b_key)
    if b not in getattr(df, "columns", []):
        b = next((c for c in numeric if c != a), None)
    return a, b


def _f(args: Dict[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
    try:
        value = args.get(key, default)
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ Gas Sensor
def _tool_gas_response(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    t_on, t_off = _f(args, "t_on"), _f(args, "t_off")
    if t_on is None or t_off is None:
        return "Provide 't_on' and 't_off' (gas ON/OFF times on the X axis)."
    t_col, y_col = _two_numeric(df, args, "time_column", "column")
    if t_col is None or y_col is None:
        return "Need a time column and a signal column."
    try:
        from analysis.gas_sensor import analyze_response

        r = analyze_response(df[t_col].to_numpy(float), df[y_col].to_numpy(float), t_on, t_off)
        resp_t = f"{r.response_time:.4g}s" if r.response_time is not None else "n/a"
        rec_t = f"{r.recovery_time:.4g}s" if r.recovery_time is not None else "n/a"
        return (
            f"Gas response of '{y_col}': {r.response_percent:.2f}% "
            f"(Ra={r.baseline:.4g}, Rg={r.steady:.4g}, sensitivity {r.sensitivity:.3g}); "
            f"response t90 {resp_t}, recovery t90 {rec_t}."
        )
    except Exception as exc:
        logger.debug("gas_response tool failed", exc_info=True)
        return f"Could not analyze gas response: {exc}"


# ------------------------------------------------------------- Electrochemistry
def _tool_cv_peaks(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    v_col, i_col = _two_numeric(df, args, "potential_column", "current_column")
    if v_col is None or i_col is None:
        return "Need a potential column and a current column."
    try:
        from analysis.electrochemistry import cv_peak_metrics

        m = cv_peak_metrics(df[v_col].to_numpy(float), df[i_col].to_numpy(float))
        return (
            f"CV peaks: oxidation {m.oxidation_peak_current:.4g} A at "
            f"{m.oxidation_peak_potential:.4g} V, reduction {m.reduction_peak_current:.4g} A at "
            f"{m.reduction_peak_potential:.4g} V; ΔEp {m.delta_ep:.4g} V, "
            f"ip ratio {m.peak_current_ratio:.3g}."
        )
    except Exception as exc:
        logger.debug("cv_peaks tool failed", exc_info=True)
        return f"Could not compute CV peak metrics: {exc}"


def _tool_tafel(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    eta_col, i_col = _two_numeric(df, args, "overpotential_column", "current_column")
    if eta_col is None or i_col is None:
        return "Need an overpotential column and a current column."
    try:
        from analysis.electrochemistry import tafel_fit

        r = tafel_fit(df[eta_col].to_numpy(float), df[i_col].to_numpy(float))
        return (
            f"Tafel fit: slope {r['slope_mv_dec']:.2f} mV/dec, exchange current "
            f"{r['exchange_current_a']:.3g} A (R²={r['r_squared']:.4f})."
        )
    except Exception as exc:
        logger.debug("tafel tool failed", exc_info=True)
        return f"Could not run Tafel analysis: {exc}"


# ------------------------------------------------------------------ Spectroscopy
def _tool_raman_dg(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    x_col, y_col = _two_numeric(df, args, "x_column", "y_column")
    if x_col is None or y_col is None:
        return "Need a Raman shift (X) column and an intensity (Y) column."
    try:
        from analysis.spectroscopy import raman_d_g_ratio

        r = raman_d_g_ratio(df[x_col].to_numpy(float), df[y_col].to_numpy(float))
        return (
            f"Raman D/G: I(D)/I(G) = {r['id_ig']:.3f} "
            f"(D at {r['d_position']:.4g}, G at {r['g_position']:.4g})."
        )
    except Exception as exc:
        logger.debug("raman_dg tool failed", exc_info=True)
        return f"Could not compute Raman D/G ratio: {exc}"


def _tool_normalize_spectrum(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    col = _resolve_y_column(window, df, args)
    if col is None:
        return "Need a numeric intensity column."
    mode = str(args.get("mode", "max")).strip().lower()
    try:
        from analysis.spectroscopy import normalize_spectrum

        new_col = f"{col}_norm"
        df[new_col] = normalize_spectrum(df[col].to_numpy(float), mode=mode)
        _sync_new_column(window, new_col)
        return f"Normalized spectrum '{col}' ({mode}) into '{new_col}'."
    except Exception as exc:
        logger.debug("normalize_spectrum tool failed", exc_info=True)
        return f"Could not normalize spectrum: {exc}"


# --------------------------------------------------------------- Materials Sci.
def _tool_iv_conductivity(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    length_m, area_m2 = _f(args, "length_m"), _f(args, "area_m2")
    if length_m is None or area_m2 is None:
        return "Provide sample geometry: 'length_m' and 'area_m2'."
    v_col, i_col = _two_numeric(df, args, "voltage_column", "current_column")
    if v_col is None or i_col is None:
        return "Need a voltage column and a current column."
    try:
        from analysis.materials import conductivity_from_iv

        m = conductivity_from_iv(
            df[v_col].to_numpy(float), df[i_col].to_numpy(float),
            length_m=length_m, area_m2=area_m2, thickness_m=_f(args, "thickness_m"),
        )
        sheet = f", sheet {m.sheet_resistance_ohm_sq:.4g} Ω/sq" if m.sheet_resistance_ohm_sq else ""
        return (
            f"I-V conductivity: R {m.resistance_ohm:.4g} Ω, resistivity "
            f"{m.resistivity_ohm_m:.4g} Ω·m, conductivity {m.conductivity_s_m:.4g} S/m{sheet}."
        )
    except Exception as exc:
        logger.debug("iv_conductivity tool failed", exc_info=True)
        return f"Could not compute conductivity: {exc}"


def _tool_arrhenius(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    t_col, s_col = _two_numeric(df, args, "temperature_column", "conductivity_column")
    if t_col is None or s_col is None:
        return "Need a temperature (K) column and a conductivity column."
    try:
        from analysis.materials import arrhenius_activation_energy

        m = arrhenius_activation_energy(df[t_col].to_numpy(float), df[s_col].to_numpy(float))
        return f"Arrhenius activation energy Ea ≈ {m.activation_energy_ev:.4g} eV (R²={m.r_squared:.4f})."
    except Exception as exc:
        logger.debug("arrhenius tool failed", exc_info=True)
        return f"Could not compute activation energy: {exc}"


# --------------------------------------------------------------- Physics / Lab
def _tool_ohms_law(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    i_col, v_col = _two_numeric(df, args, "current_column", "voltage_column")
    if i_col is None or v_col is None:
        return "Need a current column and a voltage column."
    try:
        from analysis.physics_lab import ohms_law_fit

        r = ohms_law_fit(df[i_col].to_numpy(float), df[v_col].to_numpy(float))
        return f"Ohm's law fit: R = {r.resistance_ohm:.4g} Ω (conductance {r.conductance_s:.4g} S, R²={r.r_squared:.4f})."
    except Exception as exc:
        logger.debug("ohms_law tool failed", exc_info=True)
        return f"Could not fit Ohm's law: {exc}"


def _tool_rc_time_constant(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    t_col, v_col = _two_numeric(df, args, "time_column", "value_column")
    if t_col is None or v_col is None:
        return "Need a time column and a value column."
    mode = str(args.get("mode", "charge")).strip().lower()
    try:
        from analysis.physics_lab import rc_time_constant

        r = rc_time_constant(df[t_col].to_numpy(float), df[v_col].to_numpy(float), mode=mode)
        return f"RC time constant τ ≈ {r.tau_s:.4g} s ({mode}, R²={r.r_squared:.4f})."
    except Exception as exc:
        logger.debug("rc_time_constant tool failed", exc_info=True)
        return f"Could not fit RC time constant: {exc}"


def _tool_pendulum_gravity(window, args: Dict[str, Any]) -> str:
    df = _active_df(window)
    if df is None or getattr(df, "empty", True):
        return "No active data."
    l_col, p_col = _two_numeric(df, args, "length_column", "period_column")
    if l_col is None or p_col is None:
        return "Need a pendulum length column and a period column."
    try:
        from analysis.physics_lab import pendulum_gravity

        r = pendulum_gravity(df[l_col].to_numpy(float), df[p_col].to_numpy(float))
        return f"Pendulum gravity g ≈ {r.gravity_m_s2:.4g} m/s² (R²={r.r_squared:.4f})."
    except Exception as exc:
        logger.debug("pendulum_gravity tool failed", exc_info=True)
        return f"Could not estimate gravity: {exc}"


def register_module_tools(registry, window) -> None:
    """Register the specialized-module tools on *registry*, bound to *window*."""
    registry.add(
        "gas_response",
        "Gas-sensor response of one ON/OFF cycle: response %, sensitivity, "
        "response/recovery t90. Requires 't_on' and 't_off' (X-axis times).",
        {
            "t_on": {"type": "number", "description": "gas ON time", "required": True},
            "t_off": {"type": "number", "description": "gas OFF time", "required": True},
            "time_column": {"type": "string", "description": "time column", "required": False},
            "column": {"type": "string", "description": "sensor signal column", "required": False},
        },
        lambda args: _tool_gas_response(window, args),
    )
    registry.add(
        "cv_peaks",
        "Cyclic-voltammetry peak metrics: oxidation/reduction peak current & "
        "potential, ΔEp and peak-current ratio.",
        {
            "potential_column": {"type": "string", "description": "potential (V)", "required": False},
            "current_column": {"type": "string", "description": "current (A)", "required": False},
        },
        lambda args: _tool_cv_peaks(window, args),
    )
    registry.add(
        "tafel_analysis",
        "Tafel fit: slope (mV/dec) and exchange current from overpotential vs current.",
        {
            "overpotential_column": {"type": "string", "description": "overpotential (V)", "required": False},
            "current_column": {"type": "string", "description": "current (A)", "required": False},
        },
        lambda args: _tool_tafel(window, args),
    )
    registry.add(
        "raman_dg",
        "Raman D/G intensity ratio (I(D)/I(G)) from a Raman-shift/intensity spectrum.",
        {
            "x_column": {"type": "string", "description": "Raman shift", "required": False},
            "y_column": {"type": "string", "description": "intensity", "required": False},
        },
        lambda args: _tool_raman_dg(window, args),
    )
    registry.add(
        "normalize_spectrum",
        "Normalize a spectrum column into a new column. mode: max | area | minmax.",
        {
            "mode": {"type": "string", "description": "max|area|minmax", "required": False},
            "column": {"type": "string", "description": "intensity column", "required": False},
        },
        lambda args: _tool_normalize_spectrum(window, args),
    )
    registry.add(
        "iv_conductivity",
        "Electrical conductivity/resistivity from an I-V sweep. Requires 'length_m' "
        "and 'area_m2' (and optional 'thickness_m' for sheet resistance).",
        {
            "length_m": {"type": "number", "description": "sample length (m)", "required": True},
            "area_m2": {"type": "number", "description": "cross-section area (m²)", "required": True},
            "thickness_m": {"type": "number", "description": "film thickness (m)", "required": False},
            "voltage_column": {"type": "string", "description": "voltage (V)", "required": False},
            "current_column": {"type": "string", "description": "current (A)", "required": False},
        },
        lambda args: _tool_iv_conductivity(window, args),
    )
    registry.add(
        "arrhenius",
        "Arrhenius activation energy (eV) from temperature (K) vs conductivity.",
        {
            "temperature_column": {"type": "string", "description": "temperature (K)", "required": False},
            "conductivity_column": {"type": "string", "description": "conductivity", "required": False},
        },
        lambda args: _tool_arrhenius(window, args),
    )
    registry.add(
        "ohms_law",
        "Fit Ohm's law (resistance) from a current vs voltage table.",
        {
            "current_column": {"type": "string", "description": "current (A)", "required": False},
            "voltage_column": {"type": "string", "description": "voltage (V)", "required": False},
        },
        lambda args: _tool_ohms_law(window, args),
    )
    registry.add(
        "rc_time_constant",
        "Fit an RC time constant (tau) from a time vs value curve. mode: charge | discharge.",
        {
            "time_column": {"type": "string", "description": "time (s)", "required": False},
            "value_column": {"type": "string", "description": "voltage/current", "required": False},
            "mode": {"type": "string", "description": "charge|discharge", "required": False},
        },
        lambda args: _tool_rc_time_constant(window, args),
    )
    registry.add(
        "pendulum_gravity",
        "Estimate g from pendulum length vs period² (least squares).",
        {
            "length_column": {"type": "string", "description": "length (m)", "required": False},
            "period_column": {"type": "string", "description": "period (s)", "required": False},
        },
        lambda args: _tool_pendulum_gravity(window, args),
    )
