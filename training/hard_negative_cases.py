"""Thai contrastive repair cases for the 14 router failures found in v2.

These prompts are training-only. Each group contains paired intents so the
model learns both the requested tool/argument and the tempting wrong choice.
All scientific names and values are synthetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from training.tool_cases import PROMPT_VALUE


@dataclass(frozen=True)
class ContrastSeed:
    group: str
    tool: str
    text: str
    arguments: Dict[str, Any]
    domain: str
    language: str = "th"


def hard_negative_seeds() -> list[ContrastSeed]:
    return [
        # 01: all numeric columns means omit columns; named columns means include them.
        ContrastSeed("describe_scope", "describe_data", "ขอสถิติ count mean std min max ของตัวเลขทุกคอลัมน์ โดยไม่ต้องเลือกชื่อคอลัมน์", {}, "general"),
        ContrastSeed("describe_scope", "describe_data", "แสดงสถิติเชิงพรรณนาเฉพาะ voltage_V กับ current_mA", {"columns": ["voltage_V", "current_mA"]}, "general"),
        ContrastSeed("describe_scope", "describe_data", "ไม่ต้องสรุปแนวโน้ม ขอแค่ตารางสถิติของคอลัมน์ตัวเลขทั้งหมด", {}, "general"),
        ContrastSeed("describe_scope", "describe_data", "คำนวณค่าเฉลี่ยและส่วนเบี่ยงเบนมาตรฐานของ resistance_kohm", {"columns": ["resistance_kohm"]}, "general"),

        # 02: a Thai narrative summary is not descriptive-statistics output.
        ContrastSeed("summary_language", "summarize_data", "ช่วยวิเคราะห์ภาพรวมของข้อมูลและตอบข้อค้นพบเป็นภาษาไทย", {"language": "th"}, "general"),
        ContrastSeed("summary_language", "summarize_data", "สรุปแนวโน้ม ค่าหาย ความสัมพันธ์ และพีคสำคัญให้ฉันเป็นภาษาไทย", {"language": "th"}, "general"),
        ContrastSeed("summary_language", "describe_data", "ขอเฉพาะ count mean std min max ของ temperature_C ไม่ต้องเขียนบทสรุป", {"columns": ["temperature_C"]}, "general"),
        ContrastSeed("summary_language", "summarize_data", "อ่านบุ๊กที่เปิดอยู่แล้วเล่า insight สำคัญแบบสั้น ๆ เป็นภาษาไทย", {"language": "th"}, "general"),

        # 03: named X/Y columns use plot_columns; gallery keys use plot_chart.
        ContrastSeed("plot_route", "plot_columns", "วาดกราฟเส้น absorbance เทียบกับ wavelength_nm ในกราฟใหม่", {"style": "line", "x_column": "wavelength_nm", "y_columns": ["absorbance"], "instruction": PROMPT_VALUE, "new_graph": True}, "plotting"),
        ContrastSeed("plot_route", "plot_columns", "พล็อตจุด current_uA เทียบ potential_V และสร้างกราฟใหม่", {"style": "scatter", "x_column": "potential_V", "y_columns": ["current_uA"], "instruction": PROMPT_VALUE, "new_graph": True}, "plotting"),
        ContrastSeed("plot_route", "plot_chart", "สร้าง advanced chart แบบ surface_3d จากข้อมูลที่เปิดอยู่", {"chart_type": "surface_3d"}, "plotting"),
        ContrastSeed("plot_route", "plot_chart", "เปิดกราฟแกลเลอรีชนิด matrix_heatmap ให้ข้อมูลชุดนี้", {"chart_type": "matrix_heatmap"}, "plotting"),

        # 04: optional device fields must not be invented.
        ContrastSeed("gas_optional", "gas_live_control", "เชื่อมต่อเซนเซอร์ก๊าซทาง serial ที่ COM9 ด้วย baud 57600", {"action": "connect", "transport": "serial", "port": "COM9", "baud": 57600}, "gas_sensor"),
        ContrastSeed("gas_optional", "gas_live_control", "เช็กสถานะการรับข้อมูลก๊าซสดตอนนี้", {"action": "status"}, "gas_sensor"),
        ContrastSeed("gas_optional", "gas_live_control", "ทำเครื่องหมายเริ่มปล่อยก๊าซ hydrogen", {"action": "mark_on", "label": "hydrogen"}, "gas_sensor"),
        ContrastSeed("gas_optional", "gas_live_control", "ตัดการเชื่อมต่อระบบรับข้อมูลก๊าซ", {"action": "disconnect"}, "gas_sensor"),

        # 05: listing models is read-only and takes no fit arguments.
        ContrastSeed("fit_list_vs_run", "list_fit_models", "ขอดูรายชื่อโมเดลทั้งหมดที่ใช้ฟิตกราฟได้ ยังไม่ต้องฟิต", {}, "fitting"),
        ContrastSeed("fit_list_vs_run", "list_fit_models", "มีสมการ curve fitting อะไรให้เลือกบ้าง", {}, "fitting"),
        ContrastSeed("fit_list_vs_run", "fit_curve", "ใช้โมเดล linear ฟิต current_A เทียบกับ voltage_V", {"model": "linear", "x_column": "voltage_V", "y_column": "current_A"}, "fitting"),
        ContrastSeed("fit_list_vs_run", "fit_curve", "ฟิต gaussian ให้ intensity เทียบกับ energy_eV", {"model": "gaussian", "x_column": "energy_eV", "y_column": "intensity"}, "fitting"),

        # 06: weighting describes the uncertainty interpretation, not a model/column name.
        ContrastSeed("weighted_fit", "fit_curve", "ฟิตเส้นตรง y_signal เทียบ x_value โดยใช้ sigma_y เป็นค่าความไม่แน่นอน sigma", {"model": "linear", "x_column": "x_value", "y_column": "y_signal", "weight_column": "sigma_y", "weighting": "sigma"}, "fitting"),
        ContrastSeed("weighted_fit", "fit_curve", "ฟิต linear ของ conductivity เทียบ temperature_K และให้น้ำหนักจาก inv_variance แบบ 1/sigma^2", {"model": "linear", "x_column": "temperature_K", "y_column": "conductivity", "weight_column": "inv_variance", "weighting": "1/sigma^2"}, "fitting"),
        ContrastSeed("weighted_fit", "fit_curve", "ฟิต exponential ของ decay_V เทียบ time_ms โดยไม่ถ่วงน้ำหนัก", {"model": "exponential", "x_column": "time_ms", "y_column": "decay_V"}, "fitting"),
        ContrastSeed("weighted_fit", "fit_curve", "ใช้ error_bar เป็น sigma เพื่อฟิต gaussian ของ counts เทียบ channel", {"model": "gaussian", "x_column": "channel", "y_column": "counts", "weight_column": "error_bar", "weighting": "sigma"}, "fitting"),

        # 07: value is legal only when method=value.
        ContrastSeed("fill_optional_value", "fill_missing", "เติม NaN ใน humidity_pct ด้วยค่าก่อนหน้า", {"method": "ffill", "column": "humidity_pct"}, "cleaning"),
        ContrastSeed("fill_optional_value", "fill_missing", "แทนค่าหายใน pressure_kPa ด้วยค่าถัดไป", {"method": "bfill", "column": "pressure_kPa"}, "cleaning"),
        ContrastSeed("fill_optional_value", "fill_missing", "แทน NaN ของ concentration_ppm ด้วยเลข -1", {"method": "value", "value": -1, "column": "concentration_ppm"}, "cleaning"),
        ContrastSeed("fill_optional_value", "fill_missing", "เติมค่าหายใน temperature_C ด้วยมัธยฐาน", {"method": "median", "column": "temperature_C"}, "cleaning"),

        # 08: report anomalies without mutation; preserve the stated threshold.
        ContrastSeed("anomaly_threshold", "find_anomalies", "รายงาน anomaly ของ flow_sccm ด้วย z-score เกิน 3 โดยไม่แก้ข้อมูล", {"method": "zscore", "threshold": 3, "column": "flow_sccm"}, "cleaning"),
        ContrastSeed("anomaly_threshold", "find_anomalies", "หา outlier แบบ IQR เกณฑ์ 1.5 ใน response_pct แต่อย่าลบ", {"method": "iqr", "threshold": 1.5, "column": "response_pct"}, "cleaning"),
        ContrastSeed("anomaly_threshold", "remove_outliers", "ลบค่าผิดปกติ z-score เกิน 2.5 ออกจาก pressure_kPa", {"method": "zscore", "threshold": 2.5, "column": "pressure_kPa"}, "cleaning"),
        ContrastSeed("anomaly_threshold", "find_anomalies", "ตรวจหาค่าผิดปกติใน current_uA ด้วย z-score threshold 4 เท่านั้น", {"method": "zscore", "threshold": 4, "column": "current_uA"}, "cleaning"),

        # 09: Thai direction words map deterministically to ascending.
        ContrastSeed("sort_direction", "sort_data", "เรียง time_ms จากน้อยไปมาก", {"column": "time_ms", "ascending": True}, "cleaning"),
        ContrastSeed("sort_direction", "sort_data", "เรียง resistance_ohm จากมากไปน้อย", {"column": "resistance_ohm", "ascending": False}, "cleaning"),
        ContrastSeed("sort_direction", "sort_data", "จัดลำดับ wavelength_nm แบบต่ำสุดขึ้นก่อน", {"column": "wavelength_nm", "ascending": True}, "cleaning"),
        ContrastSeed("sort_direction", "sort_data", "จัดข้อมูลตาม intensity ให้ค่าสูงสุดอยู่บนสุด", {"column": "intensity", "ascending": False}, "cleaning"),

        # 10: Fourier amplitude/FFT and PSD are distinct tools.
        ContrastSeed("fft_vs_psd", "run_fft", "คำนวณ FFT ของ accelerometer_g โดยใช้ time_s เป็นแกนเวลา", {"column": "accelerometer_g", "x_column": "time_s"}, "signal"),
        ContrastSeed("fft_vs_psd", "run_fft", "หาสเปกตรัมฟูเรียร์ของ acoustic_V", {"column": "acoustic_V"}, "signal"),
        ContrastSeed("fft_vs_psd", "power_spectrum", "คำนวณ PSD ของ accelerometer_g ที่ sampling 512 Hz", {"fs": 512, "column": "accelerometer_g"}, "signal"),
        ContrastSeed("fft_vs_psd", "power_spectrum", "สร้าง power spectral density ของ acoustic_V", {"column": "acoustic_V"}, "signal"),

        # 11: do not emit the opposite axis flag when it was not requested.
        ContrastSeed("format_only_named", "format_graph", "เปิดเส้นกริดและเปลี่ยนเฉพาะแกน Y เป็น log", {"grid": True, "logy": True}, "plotting"),
        ContrastSeed("format_only_named", "format_graph", "ซ่อน legend แล้วตั้งชื่อกราฟว่า Calibration", {"legend": False, "title": "Calibration"}, "plotting"),
        ContrastSeed("format_only_named", "format_graph", "ตั้งแกน X เป็นสเกล log โดยไม่เปลี่ยนแกน Y", {"logx": True}, "plotting"),
        ContrastSeed("format_only_named", "format_graph", "ตั้งชื่อแกน X ว่า Frequency (Hz) และแกน Y ว่า Amplitude", {"xlabel": "Frequency (Hz)", "ylabel": "Amplitude"}, "plotting"),

        # 12: advanced chart keys must be exact registry keys.
        ContrastSeed("advanced_chart_key", "plot_chart", "พล็อต advanced chart แบบ surface_3d", {"chart_type": "surface_3d"}, "plotting"),
        ContrastSeed("advanced_chart_key", "plot_chart", "สร้างกราฟสามมิติชนิด scatter_3d", {"chart_type": "scatter_3d"}, "plotting"),
        ContrastSeed("advanced_chart_key", "plot_chart", "ทำกราฟ wireframe_3d จากบุ๊กนี้", {"chart_type": "wireframe_3d"}, "plotting"),
        ContrastSeed("advanced_chart_key", "plot_chart", "สร้าง heatmap ชนิด matrix_heatmap", {"chart_type": "matrix_heatmap"}, "plotting"),

        # 13: gas ON precedes OFF and named columns are copied exactly.
        ContrastSeed("gas_on_off", "gas_response", "วิเคราะห์การตอบสนองก๊าซ เปิดที่ 20 วินาที ปิดที่ 140 วินาที จาก sensor_R โดยเวลาอยู่ใน elapsed_s", {"t_on": 20, "t_off": 140, "time_column": "elapsed_s", "column": "sensor_R"}, "gas_sensor"),
        ContrastSeed("gas_on_off", "gas_response", "คำนวณ response cycle ของ voltage_V ช่วง gas on 45 ถึง gas off 210 วินาที ใช้ time_s", {"t_on": 45, "t_off": 210, "time_column": "time_s", "column": "voltage_V"}, "gas_sensor"),
        ContrastSeed("gas_on_off", "gas_response", "หา response และ recovery เมื่อเปิดก๊าซเวลา 10 และปิดเวลา 90 จาก conductance_mS", {"t_on": 10, "t_off": 90, "column": "conductance_mS"}, "gas_sensor"),
        ContrastSeed("gas_on_off", "gas_response", "ใช้ t_on 75 กับ t_off 300 วิเคราะห์ resistance_kohm ตาม timestamp_s", {"t_on": 75, "t_off": 300, "time_column": "timestamp_s", "column": "resistance_kohm"}, "gas_sensor"),

        # 14: charge/discharge mode follows the explicit physical direction.
        ContrastSeed("rc_mode", "rc_time_constant", "ฟิตค่าคงตัวเวลา RC ตอนชาร์จจาก elapsed_s กับ capacitor_V", {"time_column": "elapsed_s", "value_column": "capacitor_V", "mode": "charge"}, "physics"),
        ContrastSeed("rc_mode", "rc_time_constant", "หาค่า tau ตอนคายประจุจาก time_ms และ voltage_V", {"time_column": "time_ms", "value_column": "voltage_V", "mode": "discharge"}, "physics"),
        ContrastSeed("rc_mode", "rc_time_constant", "วงจรกำลังชาร์จ ให้คำนวณ RC time constant จาก time_s กับ current_mA", {"time_column": "time_s", "value_column": "current_mA", "mode": "charge"}, "physics"),
        ContrastSeed("rc_mode", "rc_time_constant", "ฟิตเส้นคายประจุเพื่อหา tau โดยใช้ seconds และ capacitor_voltage", {"time_column": "seconds", "value_column": "capacitor_voltage", "mode": "discharge"}, "physics"),
    ]


HARD_NEGATIVE_GROUPS = tuple(dict.fromkeys(seed.group for seed in hard_negative_seeds()))
