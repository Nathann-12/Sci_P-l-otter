"""Untuned Thai acceptance cases for the 14 v2 failure groups.

This module is consumed only to build ``acceptance_test.jsonl``. Its records
must never contribute to a training-data output.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from training.tool_cases import PROMPT_VALUE


@dataclass(frozen=True)
class AcceptanceSeed:
    group: str
    tool: str
    text: str
    arguments: Dict[str, Any]
    domain: str
    language: str = "th"


def acceptance_seeds() -> list[AcceptanceSeed]:
    return [
        AcceptanceSeed("describe_scope", "describe_data", "ดูสถิติพื้นฐานของข้อมูลเชิงตัวเลขทุกช่องให้หน่อย ไม่ต้องระบุคอลัมน์", {}, "general"),
        AcceptanceSeed("describe_scope", "describe_data", "หา mean std และช่วงของ density_g_cm3 กับ porosity_pct", {"columns": ["density_g_cm3", "porosity_pct"]}, "general"),
        AcceptanceSeed("summary_language", "summarize_data", "ช่วยอ่านข้อมูลชุดนี้แล้วสรุปประเด็นที่นักวิจัยควรรู้เป็นภาษาไทย", {"language": "th"}, "general"),
        AcceptanceSeed("summary_language", "summarize_data", "ขอภาพรวมแนวโน้มและความผิดปกติของบุ๊กนี้ ตอบไทยแบบกระชับ", {"language": "th"}, "general"),
        AcceptanceSeed("plot_route", "plot_columns", "สร้างกราฟเส้น emission_count เทียบกับ wavelength_nm เป็นกราฟใหม่", {"style": "line", "x_column": "wavelength_nm", "y_columns": ["emission_count"], "instruction": PROMPT_VALUE, "new_graph": True}, "plotting"),
        AcceptanceSeed("plot_route", "plot_chart", "สร้างกราฟขั้นสูงชนิด contour_3d จากข้อมูลปัจจุบัน", {"chart_type": "contour_3d"}, "plotting"),
        AcceptanceSeed("gas_optional", "gas_live_control", "ต่อเครื่องวัดก๊าซที่ COM12 ความเร็ว 38400 ผ่าน serial", {"action": "connect", "transport": "serial", "port": "COM12", "baud": 38400}, "gas_sensor"),
        AcceptanceSeed("gas_optional", "gas_live_control", "ทำ marker ว่าเริ่มเปิด ammonia", {"action": "mark_on", "label": "ammonia"}, "gas_sensor"),
        AcceptanceSeed("fit_list_vs_run", "list_fit_models", "ก่อนทำอะไรขอรายชื่อสมการฟิตที่โปรแกรมรองรับทั้งหมด", {}, "fitting"),
        AcceptanceSeed("fit_list_vs_run", "fit_curve", "ฟิต linear ให้ force_N เทียบ displacement_mm", {"model": "linear", "x_column": "displacement_mm", "y_column": "force_N"}, "fitting"),
        AcceptanceSeed("weighted_fit", "fit_curve", "ฟิตเส้นตรง signal_V เทียบ concentration_ppm โดย sigma_signal คือความไม่แน่นอน", {"model": "linear", "x_column": "concentration_ppm", "y_column": "signal_V", "weight_column": "sigma_signal", "weighting": "sigma"}, "fitting"),
        AcceptanceSeed("weighted_fit", "fit_curve", "ฟิต gaussian ของ counts เทียบ energy_keV ใช้ weight_inv แบบ 1/sigma^2", {"model": "gaussian", "x_column": "energy_keV", "y_column": "counts", "weight_column": "weight_inv", "weighting": "1/sigma^2"}, "fitting"),
        AcceptanceSeed("fill_optional_value", "fill_missing", "เติมช่องว่างใน oxygen_pct ด้วยค่าก่อนหน้า", {"method": "ffill", "column": "oxygen_pct"}, "cleaning"),
        AcceptanceSeed("fill_optional_value", "fill_missing", "แทน NaN ใน baseline_V ด้วย 0.25", {"method": "value", "value": 0.25, "column": "baseline_V"}, "cleaning"),
        AcceptanceSeed("anomaly_threshold", "find_anomalies", "ตรวจ anomaly ใน torque_Nm ด้วย z-score เกิน 3.5 แต่ห้ามลบแถว", {"method": "zscore", "threshold": 3.5, "column": "torque_Nm"}, "cleaning"),
        AcceptanceSeed("anomaly_threshold", "find_anomalies", "รายงาน outlier แบบ IQR threshold 2 ใน grain_size_um โดยไม่แก้ข้อมูล", {"method": "iqr", "threshold": 2, "column": "grain_size_um"}, "cleaning"),
        AcceptanceSeed("sort_direction", "sort_data", "เรียง sample_id จากค่าต่ำไปค่าสูง", {"column": "sample_id", "ascending": True}, "cleaning"),
        AcceptanceSeed("sort_direction", "sort_data", "จัด hardness_HV จากสูงสุดลงมาต่ำสุด", {"column": "hardness_HV", "ascending": False}, "cleaning"),
        AcceptanceSeed("fft_vs_psd", "run_fft", "ทำ Fourier transform ของ gyro_z โดยอ้างอิงเวลา timestamp_s", {"column": "gyro_z", "x_column": "timestamp_s"}, "signal"),
        AcceptanceSeed("fft_vs_psd", "power_spectrum", "หา PSD ของ noise_V ที่อัตราสุ่ม 2048 Hz", {"fs": 2048, "column": "noise_V"}, "signal"),
        AcceptanceSeed("format_only_named", "format_graph", "เปิด legend และใช้ log เฉพาะแกน X", {"legend": True, "logx": True}, "plotting"),
        AcceptanceSeed("format_only_named", "format_graph", "ปิด grid แล้วตั้งชื่อแกน Y เป็น Conductivity (S/m)", {"grid": False, "ylabel": "Conductivity (S/m)"}, "plotting"),
        AcceptanceSeed("advanced_chart_key", "plot_chart", "วาดกราฟสามมิติแบบ trisurface_3d", {"chart_type": "trisurface_3d"}, "plotting"),
        AcceptanceSeed("advanced_chart_key", "plot_chart", "ใช้กราฟขั้นสูงชนิด bar_3d กับบุ๊กนี้", {"chart_type": "bar_3d"}, "plotting"),
        AcceptanceSeed("gas_on_off", "gas_response", "วัด gas response จาก signal_mV โดยเริ่มเปิดที่ 35 และปิดที่ 175 วินาที เวลาอยู่คอลัมน์ runtime_s", {"t_on": 35, "t_off": 175, "time_column": "runtime_s", "column": "signal_mV"}, "gas_sensor"),
        AcceptanceSeed("gas_on_off", "gas_response", "คำนวณรอบตอบสนองของ sensor_current_uA ช่วง ON 60 ถึง OFF 240", {"t_on": 60, "t_off": 240, "column": "sensor_current_uA"}, "gas_sensor"),
        AcceptanceSeed("rc_mode", "rc_time_constant", "หา tau ช่วงตัวเก็บประจุกำลังชาร์จจาก clock_s และ charge_voltage_V", {"time_column": "clock_s", "value_column": "charge_voltage_V", "mode": "charge"}, "physics"),
        AcceptanceSeed("rc_mode", "rc_time_constant", "คำนวณ RC time constant ตอนคายประจุจาก elapsed_ms กับ discharge_current_mA", {"time_column": "elapsed_ms", "value_column": "discharge_current_mA", "mode": "discharge"}, "physics"),
    ]
