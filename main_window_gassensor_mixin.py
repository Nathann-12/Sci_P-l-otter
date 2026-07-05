from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QStyle

from analysis.gas_sensor import (
    analyze_response,
    calibration_curve,
    detect_gas_cycles,
    dilution_ppm,
    format_response_report,
    limit_of_detection,
)
from processors import beautify_axes

logger = logging.getLogger(__name__)


class MainWindowGasSensorMixin:
    """Gas Sensor specialty module (ROADMAP H) — first activity-rail module.

    UI flows only; the math lives in analysis/gas_sensor.py. Talks to the UI
    through the view seam (ask_choice/ask_number/inform/notify) so everything
    is testable headless.
    """

    # ------------------------------------------------------------------ setup
    def init_gas_sensor_module(self):
        """Register the Gas Sensor context in the activity rail + its menu."""
        from UI.gas_sensor_panel import GasSensorPanel

        panel = GasSensorPanel(self)
        panel.analyze_requested.connect(self.gs_analyze_response)
        panel.cycles_requested.connect(self.gs_detect_cycles)
        panel.calibration_requested.connect(self.gs_calibration)
        panel.dilution_requested.connect(self.gs_dilution)
        self.gas_sensor_panel = panel

        try:
            icon = self._icon("gas", QStyle.StandardPixmap.SP_DriveHDIcon)
        except Exception:
            icon = None
        self.shell.register_context("gas_sensor", "Gas", panel, icon=icon)

        menu = self.menuBar().addMenu("&Gas Sensor")
        menu.addAction("วิเคราะห์ Response (t90)…").triggered.connect(self.gs_analyze_response)
        menu.addAction("ตรวจจับรอบเปิด-ปิดแก๊ส…").triggered.connect(self.gs_detect_cycles)
        menu.addAction("Calibration Curve + LOD…").triggered.connect(self.gs_calibration)
        menu.addAction("คำนวณการเจือจางแก๊ส (ppm)…").triggered.connect(self.gs_dilution)

    # ---------------------------------------------------------------- helpers
    def _gs_time_seconds(self, col: str) -> np.ndarray:
        """Column as seconds: datetime → seconds from start, else numeric."""
        ser = self._df[col]
        if pd.api.types.is_datetime64_any_dtype(ser):
            return (ser - ser.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        return pd.to_numeric(ser, errors="coerce").to_numpy(dtype=float)

    def _gs_pick_txy(self) -> Optional[Tuple[np.ndarray, np.ndarray, str, str]]:
        """Resolve (t, y, x_name, y_name) from the active Book, prompting for Y."""
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล", "เปิดไฟล์หรือคลิก Book ที่มีข้อมูลก่อน")
            return None
        cols = [str(c) for c in self._df.columns]
        x_name = self.selected_x_column()
        if x_name not in cols:
            x_name, ok = self.ask_choice("เลือกคอลัมน์เวลา", "เวลา/X:", cols, 0)
            if not ok:
                return None
        y_options = [c for c in cols if c != x_name]
        if not y_options:
            self.inform("ข้อมูลไม่พอ", "ต้องมีคอลัมน์สัญญาณ (เช่น resistance) นอกจากคอลัมน์เวลา")
            return None
        y_default = self.selected_y_column()
        y_idx = y_options.index(y_default) if y_default in y_options else 0
        y_name, ok = self.ask_choice("เลือกคอลัมน์สัญญาณ", "สัญญาณ/Y:", y_options, y_idx)
        if not ok:
            return None
        t = self._gs_time_seconds(x_name)
        y = pd.to_numeric(self._df[y_name], errors="coerce").to_numpy(dtype=float)
        return t, y, x_name, y_name

    def _gs_log(self, text: str) -> None:
        try:
            dock = getattr(self, "op_log_dock", None)
            if dock is not None:
                dock.add_entry(text)
        except Exception:
            logger.debug("gas log entry skipped", exc_info=True)

    # ------------------------------------------------------------------ flows
    def gs_analyze_response(self):
        picked = self._gs_pick_txy()
        if picked is None:
            return
        t, y, _x_name, y_name = picked
        finite_t = t[np.isfinite(t)]
        if finite_t.size < 3:
            self.inform("ข้อมูลไม่พอ", "คอลัมน์เวลาไม่มีค่าที่ใช้ได้")
            return
        t0, t1 = float(finite_t.min()), float(finite_t.max())
        span = t1 - t0
        t_on, ok = self.ask_number("เวลาเปิดแก๊ส", "t_on (วินาที):",
                                   t0 + 0.25 * span, t0, t1, 4)
        if not ok:
            return
        t_off, ok = self.ask_number("เวลาปิดแก๊ส", "t_off (วินาที):",
                                    t0 + 0.75 * span, t0, t1, 4)
        if not ok:
            return
        try:
            res = analyze_response(t, y, float(t_on), float(t_off))
        except Exception as e:
            self.error_box("วิเคราะห์ไม่สำเร็จ", f"สาเหตุ: {e}")
            return
        report = format_response_report(res)
        self.inform(f"Gas Response — {y_name}", report)
        self._gs_log(f"Gas response ({y_name}): {res.response_percent:.4g}% "
                     f"t90={res.response_time if res.response_time is not None else '-'}")
        self.notify(f"Response ของ {y_name}: {res.response_percent:.4g}% "
                    f"(sensitivity {res.sensitivity:.4g})")

    def gs_detect_cycles(self):
        picked = self._gs_pick_txy()
        if picked is None:
            return
        t, y, _x_name, y_name = picked
        threshold_pct, ok = self.ask_number(
            "ตรวจจับรอบแก๊ส", "เกณฑ์การเบี่ยงเบนจาก baseline (%):", 5.0, 0.1, 500.0, 2)
        if not ok:
            return
        try:
            cycles = detect_gas_cycles(t, y, rel_threshold=float(threshold_pct) / 100.0)
        except Exception as e:
            self.error_box("ตรวจจับไม่สำเร็จ", f"สาเหตุ: {e}")
            return
        if not cycles:
            self.inform("ไม่พบรอบแก๊ส",
                        "ไม่พบช่วงที่สัญญาณเบี่ยงเบนเกินเกณฑ์ — ลองลดเกณฑ์ %")
            return
        lines = [f"พบ {len(cycles)} รอบ (เกณฑ์ {threshold_pct:g}%):", ""]
        for i, (t_on, t_off) in enumerate(cycles, start=1):
            try:
                res = analyze_response(t, y, t_on, t_off)
                lines.append(
                    f"รอบ {i}: {t_on:.6g}→{t_off:.6g}  "
                    f"response {res.response_percent:.4g}%  "
                    f"t90 {res.response_time if res.response_time is not None else '-'}")
            except Exception:
                lines.append(f"รอบ {i}: {t_on:.6g}→{t_off:.6g} (คำนวณ response ไม่ได้)")
        self.inform(f"รอบเปิด-ปิดแก๊ส — {y_name}", "\n".join(lines))
        self._gs_log(f"Gas cycles ({y_name}): {len(cycles)} รอบ")

    def gs_calibration(self):
        if self._df is None or getattr(self._df, "empty", True):
            self.inform("ยังไม่มีข้อมูล", "เปิดตารางความเข้มข้น-response ใน Book ก่อน")
            return
        cols = [str(c) for c in self._df.columns]
        if len(cols) < 2:
            self.inform("ข้อมูลไม่พอ", "ต้องมีคอลัมน์ความเข้มข้นและคอลัมน์ response")
            return
        conc_col, ok = self.ask_choice("Calibration", "คอลัมน์ความเข้มข้น:", cols, 0)
        if not ok:
            return
        resp_options = [c for c in cols if c != conc_col]
        resp_col, ok = self.ask_choice("Calibration", "คอลัมน์ response:", resp_options, 0)
        if not ok:
            return
        model, ok = self.ask_choice("Calibration", "โมเดล:", ["linear", "power"], 0)
        if not ok:
            return
        noise_std, ok = self.ask_number(
            "Limit of Detection", "σ ของ noise (0 = ข้าม LOD):", 0.0, 0.0, 1e12, 6)
        if not ok:
            return
        conc = pd.to_numeric(self._df[conc_col], errors="coerce").to_numpy(dtype=float)
        resp = pd.to_numeric(self._df[resp_col], errors="coerce").to_numpy(dtype=float)
        try:
            fit = calibration_curve(conc, resp, model=model)
        except Exception as e:
            self.error_box("Fit ไม่สำเร็จ", f"สาเหตุ: {e}")
            return

        lines = [f"โมเดล: {fit['model']}"]
        if fit["model"] == "linear":
            slope = fit["slope"]
            lines.append(f"slope: {slope:.6g}   intercept: {fit['intercept']:.6g}")
        else:
            slope = None
            lines.append(f"response = {fit['a']:.6g} × conc^{fit['b']:.4g}")
        lines.append(f"R²: {fit['r_squared']:.6g}")
        if noise_std > 0:
            if fit["model"] == "linear" and slope:
                lod, loq = limit_of_detection(slope, float(noise_std))
                lines.append(f"LOD (3σ/slope): {lod:.6g}   LOQ (10σ/slope): {loq:.6g}")
            else:
                lines.append("LOD/LOQ: รองรับเฉพาะโมเดล linear")

        # กราฟ calibration: จุดข้อมูล + เส้น fit บน Graph ใหม่ (แบบ Origin)
        try:
            self.tabs.add_tab()
            tab = self.tabs.currentWidget()
            ax = tab.get_axes()
            good = np.isfinite(conc) & np.isfinite(resp)
            ax.scatter(conc[good], resp[good], s=28, label="data")
            xs = np.linspace(np.nanmin(conc[good]), np.nanmax(conc[good]), 200)
            ax.plot(xs, fit["predict"](xs), linewidth=2,
                    label=f"{fit['model']} fit (R²={fit['r_squared']:.4g})")
            ax.set_xlabel(conc_col)
            ax.set_ylabel(resp_col)
            ax.legend(loc="best")
            beautify_axes(ax, title=f"Calibration: {resp_col} vs {conc_col}")
            tab.draw()
            self._show_plot_view()
        except Exception:
            logger.debug("calibration plot skipped", exc_info=True)

        self.inform("Calibration Curve", "\n".join(lines))
        self._gs_log(f"Calibration {resp_col} vs {conc_col}: R²={fit['r_squared']:.4g}")

    def gs_dilution(self):
        source_ppm, ok = self.ask_number(
            "การเจือจางแก๊ส", "ความเข้มข้นถังต้นทาง (ppm):", 1000.0, 0.0, 1e12, 4)
        if not ok:
            return
        flow_gas, ok = self.ask_number(
            "การเจือจางแก๊ส", "อัตราไหลแก๊ส (sccm):", 10.0, 1e-9, 1e12, 4)
        if not ok:
            return
        flow_total, ok = self.ask_number(
            "การเจือจางแก๊ส", "อัตราไหลรวมทั้งหมด (sccm):", 100.0, 1e-9, 1e12, 4)
        if not ok:
            return
        try:
            ppm = dilution_ppm(float(source_ppm), float(flow_gas), float(flow_total))
        except Exception as e:
            self.error_box("คำนวณไม่สำเร็จ", f"สาเหตุ: {e}")
            return
        self.inform(
            "ผลการเจือจางแก๊ส",
            f"{source_ppm:g} ppm × ({flow_gas:g} / {flow_total:g}) = {ppm:.6g} ppm")
        self._gs_log(f"Gas dilution: {ppm:.6g} ppm")
