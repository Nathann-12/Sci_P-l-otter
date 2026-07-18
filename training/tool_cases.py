"""Curated bilingual intent seeds grounded in SciPlotter's real tool contract.

All names, units and values are synthetic but scientifically plausible. No
customer or researcher dataset is used to create these examples.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable

PROMPT_VALUE = "__USER_TEXT__"


@dataclass(frozen=True)
class ToolSeed:
    tool: str
    language: str
    text: str
    arguments: Dict[str, Any]
    domain: str


@dataclass(frozen=True)
class AnswerSeed:
    language: str
    text: str
    answer: str
    category: str


def _tool(
    name: str,
    domain: str,
    en_a: tuple[str, Dict[str, Any]],
    en_b: tuple[str, Dict[str, Any]],
    th_a: tuple[str, Dict[str, Any]],
    th_b: tuple[str, Dict[str, Any]],
) -> list[ToolSeed]:
    return [
        ToolSeed(name, "en", en_a[0], en_a[1], domain),
        ToolSeed(name, "en", en_b[0], en_b[1], domain),
        ToolSeed(name, "th", th_a[0], th_a[1], domain),
        ToolSeed(name, "th", th_b[0], th_b[1], domain),
    ]


def tool_seeds() -> list[ToolSeed]:
    seeds: list[ToolSeed] = []
    seeds += _tool(
        "list_columns", "general",
        ("What columns are in the active dataset?", {}),
        ("List the column names and tell me the table dimensions.", {}),
        ("ชุดข้อมูลที่เปิดอยู่มีคอลัมน์อะไรบ้าง", {}),
        ("ขอรายชื่อคอลัมน์พร้อมจำนวนแถวและคอลัมน์", {}),
    )
    seeds += _tool(
        "describe_data", "general",
        ("Calculate descriptive statistics for voltage and current.", {"columns": ["voltage_V", "current_A"]}),
        ("Describe every numeric column in this Book.", {}),
        ("หาสถิติพรรณนาของคอลัมน์ temperature_C และ conductivity_S_m", {"columns": ["temperature_C", "conductivity_S_m"]}),
        ("แสดง count mean std min max ของข้อมูลตัวเลขทั้งหมด", {}),
    )
    seeds += _tool(
        "summarize_data", "general",
        ("Analyze the active scientific dataset and summarize the important findings.", {"language": "en"}),
        ("Summarize ranges, missing values, correlations and prominent peaks.", {"language": "en"}),
        ("วิเคราะห์ข้อมูลที่เปิดอยู่และสรุปสิ่งสำคัญให้หน่อย", {"language": "th"}),
        ("สรุปช่วงข้อมูล ค่าหาย ความสัมพันธ์ และพีคเด่นเป็นภาษาไทย", {"language": "th"}),
    )
    seeds += _tool(
        "plot_columns", "plotting",
        ("Plot voltage_V versus time_s as a scatter graph.", {"style": "scatter", "x_column": "time_s", "y_columns": ["voltage_V"], "instruction": PROMPT_VALUE, "new_graph": True}),
        ("Create a line graph of sensor_A and sensor_B against elapsed_s.", {"style": "line", "x_column": "elapsed_s", "y_columns": ["sensor_A", "sensor_B"], "instruction": PROMPT_VALUE, "new_graph": True}),
        ("พล็อต current_mA เทียบกับ potential_V แบบจุด", {"style": "scatter", "x_column": "potential_V", "y_columns": ["current_mA"], "instruction": PROMPT_VALUE, "new_graph": True}),
        ("สร้างกราฟเส้น intensity เทียบกับ two_theta_deg ในกราฟใหม่", {"style": "line", "x_column": "two_theta_deg", "y_columns": ["intensity"], "instruction": PROMPT_VALUE, "new_graph": True}),
    )
    seeds += _tool(
        "active_book", "general",
        ("Which Book is active right now?", {}),
        ("Tell me the name of the active dataset.", {}),
        ("ตอนนี้กำลังใช้บุ๊กไหนอยู่", {}),
        ("ชุดข้อมูลที่ active ชื่ออะไร", {}),
    )
    seeds += _tool(
        "gas_live_control", "gas_sensor",
        ("Show the current gas live acquisition status.", {"action": "status"}),
        ("Connect the gas sensor on COM7 at 115200 baud.", {"action": "connect", "transport": "serial", "port": "COM7", "baud": 115200}),
        ("ทำเครื่องหมายว่าตอนนี้เปิดก๊าซ ethanol", {"action": "mark_on", "label": "ethanol"}),
        ("ดูสถานะ flow ของระบบรับข้อมูลก๊าซ", {"action": "flow_status"}),
    )
    seeds += _tool(
        "list_fit_models", "fitting",
        ("What curve fitting models are available?", {}),
        ("List the equations I can use for a fit.", {}),
        ("มีโมเดลฟิตเส้นโค้งอะไรให้ใช้บ้าง", {}),
        ("ขอรายชื่อสมการสำหรับ curve fitting", {}),
    )
    seeds += _tool(
        "fit_curve", "fitting",
        ("Fit a linear model to current_A versus voltage_V.", {"model": "linear", "x_column": "voltage_V", "y_column": "current_A"}),
        ("Fit a Gaussian to intensity versus wavelength_nm.", {"model": "gaussian", "x_column": "wavelength_nm", "y_column": "intensity"}),
        ("ฟิต exponential ให้ signal เทียบกับ time_s", {"model": "exponential", "x_column": "time_s", "y_column": "signal"}),
        ("ฟิตเส้นตรงแบบถ่วงน้ำหนักโดยใช้ uncertainty เป็น sigma", {"model": "linear", "x_column": "x", "y_column": "y", "weight_column": "uncertainty", "weighting": "sigma"}),
    )
    seeds += _tool(
        "smooth_data", "signal",
        ("Smooth the voltage_V column with Savitzky-Golay using window 11.", {"method": "savitzky-golay", "column": "voltage_V", "window": 11}),
        ("Apply median smoothing to resistance_ohm with window 7.", {"method": "median", "column": "resistance_ohm", "window": 7}),
        ("ทำให้คอลัมน์ intensity เรียบด้วย gaussian window 9", {"method": "gaussian", "column": "intensity", "window": 9}),
        ("สมูท signal ด้วย Savitzky-Golay ขนาดหน้าต่าง 15", {"method": "savitzky-golay", "column": "signal", "window": 15}),
    )
    seeds += _tool(
        "filter_signal", "signal",
        ("Low-pass filter acceleration_g at 20 Hz with a 200 Hz sampling rate.", {"fs": 200, "kind": "lowpass", "cutoff": 20, "column": "acceleration_g"}),
        ("High-pass filter baseline_drift above 0.5 Hz; sampling is 100 Hz.", {"fs": 100, "kind": "highpass", "cutoff": 0.5, "column": "baseline_drift"}),
        ("กรอง signal แบบ lowpass ที่ 10 Hz โดย sampling 250 Hz", {"fs": 250, "kind": "lowpass", "cutoff": 10, "column": "signal"}),
        ("ใช้ Butterworth highpass 1 Hz กับ voltage โดย fs เท่ากับ 500 Hz", {"fs": 500, "kind": "highpass", "cutoff": 1, "column": "voltage"}),
    )
    seeds += _tool(
        "moving_average", "signal",
        ("Add a 25-point moving average of response_pct.", {"window": 25, "column": "response_pct"}),
        ("Compute a rolling mean of temperature_C with window 10.", {"window": 10, "column": "temperature_C"}),
        ("เพิ่มค่าเฉลี่ยเคลื่อนที่ 30 จุดให้ resistance_ohm", {"window": 30, "column": "resistance_ohm"}),
        ("ทำ rolling mean คอลัมน์ signal ด้วย window 5", {"window": 5, "column": "signal"}),
    )
    seeds += _tool(
        "fill_missing", "cleaning",
        ("Fill missing temperature_C values with the median.", {"method": "median", "column": "temperature_C"}),
        ("Replace NaN in concentration_ppm with 0.", {"method": "value", "value": 0, "column": "concentration_ppm"}),
        ("เติมค่าหายใน humidity_pct ด้วยค่าเฉลี่ย", {"method": "mean", "column": "humidity_pct"}),
        ("แทน NaN ใน signal ด้วยค่าก่อนหน้า", {"method": "ffill", "column": "signal"}),
    )
    seeds += _tool(
        "interpolate", "cleaning",
        ("Interpolate the missing points in voltage_V.", {"column": "voltage_V"}),
        ("Use interpolation to fill gaps in intensity.", {"column": "intensity"}),
        ("ประมาณค่าระหว่างจุดที่หายไปใน temperature_C", {"column": "temperature_C"}),
        ("อินเตอร์โพเลตค่าหายใน resistance_ohm", {"column": "resistance_ohm"}),
    )
    seeds += _tool(
        "normalize", "cleaning",
        ("Z-score normalize the absorbance column.", {"method": "zscore", "column": "absorbance"}),
        ("Scale intensity to the zero-to-one range.", {"method": "minmax", "column": "intensity"}),
        ("ทำ z-score ให้คอลัมน์ current_mA", {"method": "zscore", "column": "current_mA"}),
        ("ปรับสเกล signal เป็นช่วง 0 ถึง 1", {"method": "minmax", "column": "signal"}),
    )
    seeds += _tool(
        "detrend", "cleaning",
        ("Remove the linear trend from sensor_signal.", {"order": 1, "column": "sensor_signal"}),
        ("Remove a second-order baseline from intensity.", {"order": 2, "column": "intensity"}),
        ("ลบแนวโน้มเชิงเส้นออกจาก voltage_V", {"order": 1, "column": "voltage_V"}),
        ("ลบเบสไลน์พหุนามอันดับ 3 จาก spectrum", {"order": 3, "column": "spectrum"}),
    )
    seeds += _tool(
        "remove_outliers", "cleaning",
        ("Remove z-score outliers above 3 from resistance_ohm.", {"method": "zscore", "threshold": 3, "column": "resistance_ohm"}),
        ("Drop IQR outliers in current_mA using threshold 1.5.", {"method": "iqr", "threshold": 1.5, "column": "current_mA"}),
        ("ลบเอาต์ไลเออร์ z-score เกิน 2.5 ใน temperature_C", {"method": "zscore", "threshold": 2.5, "column": "temperature_C"}),
        ("ตัดค่าผิดปกติแบบ IQR จาก signal", {"method": "iqr", "threshold": 1.5, "column": "signal"}),
    )
    seeds += _tool(
        "find_anomalies", "cleaning",
        ("Report anomalies in pressure_kPa without changing the data.", {"method": "zscore", "threshold": 3, "column": "pressure_kPa"}),
        ("Find IQR outliers in response_pct but do not remove them.", {"method": "iqr", "threshold": 1.5, "column": "response_pct"}),
        ("หาค่าผิดปกติใน voltage_V โดยไม่แก้ข้อมูล", {"method": "zscore", "threshold": 3, "column": "voltage_V"}),
        ("รายงานเอาต์ไลเออร์แบบ IQR ใน intensity แต่อย่าลบ", {"method": "iqr", "threshold": 1.5, "column": "intensity"}),
    )
    seeds += _tool(
        "remove_duplicates", "cleaning",
        ("Remove duplicate rows from the active data.", {}),
        ("Deduplicate this Book.", {}),
        ("ลบแถวข้อมูลซ้ำออกจากบุ๊กนี้", {}),
        ("ช่วยเอาข้อมูลที่ซ้ำกันออก", {}),
    )
    seeds += _tool(
        "sort_data", "cleaning",
        ("Sort the data by time_s in ascending order.", {"column": "time_s", "ascending": True}),
        ("Sort temperature_C from highest to lowest.", {"column": "temperature_C", "ascending": False}),
        ("เรียงข้อมูลตาม potential_V จากน้อยไปมาก", {"column": "potential_V", "ascending": True}),
        ("เรียง intensity จากมากไปน้อย", {"column": "intensity", "ascending": False}),
    )
    seeds += _tool(
        "run_fft", "signal",
        ("Run an FFT on acceleration_g using time_s as the X column.", {"column": "acceleration_g", "x_column": "time_s"}),
        ("Compute the Fourier spectrum of microphone_V.", {"column": "microphone_V"}),
        ("ทำ FFT คอลัมน์ signal โดยใช้ time_s เป็นแกนเวลา", {"column": "signal", "x_column": "time_s"}),
        ("หาสเปกตรัมฟูเรียร์ของ vibration_g", {"column": "vibration_g"}),
    )
    seeds += _tool(
        "envelope", "signal",
        ("Calculate the Hilbert envelope of vibration_g.", {"column": "vibration_g"}),
        ("Add an amplitude envelope column for acoustic_V.", {"column": "acoustic_V"}),
        ("หาซองสัญญาณ Hilbert ของ signal", {"column": "signal"}),
        ("เพิ่มคอลัมน์ envelope ให้ acceleration_g", {"column": "acceleration_g"}),
    )
    seeds += _tool(
        "signal_quality", "signal",
        ("Report SNR and noise floor for signal sampled at 1000 Hz.", {"fs": 1000, "column": "signal"}),
        ("Assess the signal quality of photodiode_V.", {"column": "photodiode_V"}),
        ("รายงาน SNR ของ vibration_g ที่ sampling 500 Hz", {"fs": 500, "column": "vibration_g"}),
        ("ตรวจคุณภาพสัญญาณและ noise floor ของ voltage_V", {"column": "voltage_V"}),
    )
    seeds += _tool(
        "power_spectrum", "signal",
        ("Compute the PSD of acceleration_g at 256 Hz sampling.", {"fs": 256, "column": "acceleration_g"}),
        ("Create a power spectrum for acoustic_V.", {"column": "acoustic_V"}),
        ("หาสเปกตรัมกำลังของ signal ที่ fs 1000 Hz", {"fs": 1000, "column": "signal"}),
        ("สร้าง PSD ของ vibration_g", {"column": "vibration_g"}),
    )
    seeds += _tool(
        "autocorrelation", "signal",
        ("Compute the autocorrelation of temperature_C.", {"column": "temperature_C"}),
        ("Open an auto-correlation curve for vibration_g.", {"column": "vibration_g"}),
        ("หาออโตคอริเลชันของ signal", {"column": "signal"}),
        ("สร้างกราฟสหสัมพันธ์ตัวเองของ pressure_kPa", {"column": "pressure_kPa"}),
    )
    seeds += _tool(
        "instantaneous_frequency", "signal",
        ("Add instantaneous frequency for chirp_signal sampled at 2000 Hz.", {"fs": 2000, "column": "chirp_signal"}),
        ("Calculate the Hilbert instantaneous frequency of vibration_g.", {"column": "vibration_g"}),
        ("หาความถี่ทันทีของ signal ที่ sampling 500 Hz", {"fs": 500, "column": "signal"}),
        ("เพิ่มคอลัมน์ความถี่ชั่วขณะให้ acoustic_V", {"column": "acoustic_V"}),
    )
    seeds += _tool(
        "harmonic_analysis", "signal",
        ("Find harmonic components in motor_current_A sampled at 5000 Hz.", {"fs": 5000, "column": "motor_current_A"}),
        ("Run harmonic analysis on acoustic_V.", {"column": "acoustic_V"}),
        ("วิเคราะห์ฮาร์มอนิกของ signal ที่ fs 1000 Hz", {"fs": 1000, "column": "signal"}),
        ("หาองค์ประกอบฮาร์มอนิกที่แรงที่สุดใน vibration_g", {"column": "vibration_g"}),
    )
    seeds += _tool(
        "peak_metrics", "spectroscopy",
        ("Report peak height, position, area and FWHM for intensity.", {"column": "intensity"}),
        ("Calculate the main peak metrics of absorbance.", {"column": "absorbance"}),
        ("หาพารามิเตอร์พีคหลักและ FWHM ของ raman_intensity", {"column": "raman_intensity"}),
        ("รายงานตำแหน่ง พื้นที่ และความกว้างครึ่งสูงของ signal", {"column": "signal"}),
    )
    seeds += _tool(
        "detect_peaks", "spectroscopy",
        ("Detect peaks in intensity with prominence 100 and distance 8.", {"column": "intensity", "prominence": 100, "distance": 8, "language": "en"}),
        ("Automatically find peaks in absorbance.", {"column": "absorbance", "auto": True, "language": "en"}),
        ("หาพีคใน raman_intensity แบบอัตโนมัติ", {"column": "raman_intensity", "auto": True, "language": "th"}),
        ("ตรวจจับพีคใน signal โดย prominence 0.2 และระยะ 10", {"column": "signal", "prominence": 0.2, "distance": 10, "language": "th"}),
    )
    seeds += _tool(
        "cross_correlation", "signal",
        ("Cross-correlate sensor_A and sensor_B.", {"column_a": "sensor_A", "column_b": "sensor_B"}),
        ("Find the lag between reference_signal and measured_signal.", {"column_a": "reference_signal", "column_b": "measured_signal"}),
        ("หาสหสัมพันธ์ข้ามระหว่าง channel_1 กับ channel_2", {"column_a": "channel_1", "column_b": "channel_2"}),
        ("หาค่า lag ระหว่าง input_signal และ output_signal", {"column_a": "input_signal", "column_b": "output_signal"}),
    )
    seeds += _tool(
        "format_graph", "plotting",
        ("Set the graph title to Sensor response and label X as Time (s).", {"title": "Sensor response", "xlabel": "Time (s)"}),
        ("Turn on the grid and use a logarithmic Y axis.", {"grid": True, "logy": True}),
        ("ตั้งชื่อกราฟว่า Raman spectrum และแกน X เป็น Raman shift (cm⁻¹)", {"title": "Raman spectrum", "xlabel": "Raman shift (cm⁻¹)"}),
        ("เปิด legend และเปลี่ยนแกน X เป็น log", {"legend": True, "logx": True}),
    )
    seeds += _tool(
        "list_charts", "plotting",
        ("List the advanced chart types available.", {}),
        ("What charts can the Chart Gallery create?", {}),
        ("มีกราฟขั้นสูงชนิดไหนให้ใช้บ้าง", {}),
        ("ขอรายชื่อกราฟทั้งหมดใน Chart Gallery", {}),
    )
    seeds += _tool(
        "plot_chart", "plotting",
        ("Create a heatmap chart from the active data.", {"chart_type": "heatmap"}),
        ("Plot a 3D scatter chart.", {"chart_type": "scatter_3d"}),
        ("สร้างกราฟ contour จากข้อมูลที่เปิดอยู่", {"chart_type": "contour"}),
        ("พล็อตกราฟ surface 3 มิติ", {"chart_type": "surface_3d"}),
    )
    seeds += _tool(
        "list_books", "general",
        ("List all open Books and mark the active one.", {}),
        ("Which datasets are currently open?", {}),
        ("แสดงรายชื่อบุ๊กทั้งหมดและบอกบุ๊กที่ active", {}),
        ("ตอนนี้เปิดชุดข้อมูลอะไรไว้บ้าง", {}),
    )
    seeds += _tool(
        "open_file", "file_io",
        (r"Open C:\Research\sensor_run_07.csv.", {"path": r"C:\Research\sensor_run_07.csv"}),
        (r"Load D:\LabData\raman_sample.xlsx into a new Book.", {"path": r"D:\LabData\raman_sample.xlsx"}),
        (r"เปิดไฟล์ C:\Data\cv_cycle_03.csv", {"path": r"C:\Data\cv_cycle_03.csv"}),
        (r"โหลด D:\Experiment\temperature_log.xlsx เป็นบุ๊กใหม่", {"path": r"D:\Experiment\temperature_log.xlsx"}),
    )
    seeds += _tool(
        "gas_response", "gas_sensor",
        ("Calculate gas response from t_on 60 s to t_off 180 s using resistance_ohm.", {"t_on": 60, "t_off": 180, "time_column": "time_s", "column": "resistance_ohm"}),
        ("Find sensitivity and t90 for the gas pulse between 120 and 300 seconds.", {"t_on": 120, "t_off": 300, "time_column": "elapsed_s", "column": "response_pct"}),
        ("คำนวณการตอบสนองก๊าซช่วงเปิด 30 ถึงปิด 150 วินาทีจาก resistance_ohm", {"t_on": 30, "t_off": 150, "time_column": "time_s", "column": "resistance_ohm"}),
        ("หา response time และ recovery time ของพัลส์ก๊าซตั้งแต่ 200 ถึง 500 วินาที", {"t_on": 200, "t_off": 500, "time_column": "time_s", "column": "sensor_response"}),
    )
    seeds += _tool(
        "cv_peaks", "electrochemistry",
        ("Calculate cyclic-voltammetry oxidation and reduction peaks from potential_V and current_mA.", {"potential_column": "potential_V", "current_column": "current_mA"}),
        ("Report ΔEp and peak-current ratio for E_V versus I_A.", {"potential_column": "E_V", "current_column": "I_A"}),
        ("หาพีค CV จาก potential_V และ current_mA", {"potential_column": "potential_V", "current_column": "current_mA"}),
        ("คำนวณ ΔEp และอัตราส่วนกระแสพีคของ E กับ I", {"potential_column": "E", "current_column": "I"}),
    )
    seeds += _tool(
        "tafel_analysis", "electrochemistry",
        ("Run a Tafel analysis on overpotential_V versus current_A.", {"overpotential_column": "overpotential_V", "current_column": "current_A"}),
        ("Calculate Tafel slope and exchange current from eta_mV and i_mA.", {"overpotential_column": "eta_mV", "current_column": "i_mA"}),
        ("วิเคราะห์ Tafel จาก overpotential_V และ current_A", {"overpotential_column": "overpotential_V", "current_column": "current_A"}),
        ("หาความชันทาเฟลและกระแสแลกเปลี่ยนจาก eta กับ current_density", {"overpotential_column": "eta", "current_column": "current_density"}),
    )
    seeds += _tool(
        "raman_dg", "spectroscopy",
        ("Calculate the Raman D/G ratio from shift_cm1 and intensity.", {"x_column": "shift_cm1", "y_column": "intensity"}),
        ("Find I(D)/I(G) in raman_shift versus counts.", {"x_column": "raman_shift", "y_column": "counts"}),
        ("หาอัตราส่วน Raman D/G จาก shift_cm1 และ intensity", {"x_column": "shift_cm1", "y_column": "intensity"}),
        ("คำนวณ I(D)/I(G) ของ raman_shift เทียบกับ counts", {"x_column": "raman_shift", "y_column": "counts"}),
    )
    seeds += _tool(
        "normalize_spectrum", "spectroscopy",
        ("Normalize the absorbance spectrum by its maximum.", {"mode": "max", "column": "absorbance"}),
        ("Area-normalize raman_intensity.", {"mode": "area", "column": "raman_intensity"}),
        ("ปรับสเปกตรัม intensity ด้วยค่าสูงสุด", {"mode": "max", "column": "intensity"}),
        ("ทำ area normalization ให้ spectrum", {"mode": "area", "column": "spectrum"}),
    )
    seeds += _tool(
        "iv_conductivity", "materials",
        ("Calculate conductivity from voltage_V and current_A for length 0.01 m and area 1e-6 m².", {"length_m": 0.01, "area_m2": 1e-6, "voltage_column": "voltage_V", "current_column": "current_A"}),
        ("Find resistivity and sheet resistance for a 20 mm sample, area 2e-6 m², thickness 100 µm.", {"length_m": 0.02, "area_m2": 2e-6, "thickness_m": 0.0001, "voltage_column": "V", "current_column": "I"}),
        ("หาการนำไฟฟ้าจาก V กับ I เมื่อชิ้นงานยาว 0.015 m และพื้นที่ 5e-7 m²", {"length_m": 0.015, "area_m2": 5e-7, "voltage_column": "V", "current_column": "I"}),
        ("คำนวณสภาพต้านทานจาก voltage และ current สำหรับความยาว 0.01 m พื้นที่ 1e-6 m²", {"length_m": 0.01, "area_m2": 1e-6, "voltage_column": "voltage", "current_column": "current"}),
    )
    seeds += _tool(
        "arrhenius", "materials",
        ("Fit an Arrhenius model to temperature_K and conductivity_S_m.", {"temperature_column": "temperature_K", "conductivity_column": "conductivity_S_m"}),
        ("Calculate activation energy from T_K versus sigma_S_cm.", {"temperature_column": "T_K", "conductivity_column": "sigma_S_cm"}),
        ("วิเคราะห์ Arrhenius จาก temperature_K และ conductivity_S_m", {"temperature_column": "temperature_K", "conductivity_column": "conductivity_S_m"}),
        ("หาพลังงานกระตุ้นจาก T_K เทียบกับ sigma", {"temperature_column": "T_K", "conductivity_column": "sigma"}),
    )
    seeds += _tool(
        "ohms_law", "physics",
        ("Fit Ohm's law to current_A and voltage_V.", {"current_column": "current_A", "voltage_column": "voltage_V"}),
        ("Calculate resistance from I_mA versus V_V.", {"current_column": "I_mA", "voltage_column": "V_V"}),
        ("ใช้กฎของโอห์มหาความต้านทานจาก current_A และ voltage_V", {"current_column": "current_A", "voltage_column": "voltage_V"}),
        ("ฟิตความต้านทานจาก I เทียบกับ V", {"current_column": "I", "voltage_column": "V"}),
    )
    seeds += _tool(
        "rc_time_constant", "physics",
        ("Fit an RC charging time constant from time_s and voltage_V.", {"time_column": "time_s", "value_column": "voltage_V", "mode": "charge"}),
        ("Calculate the discharge tau from elapsed_ms and capacitor_V.", {"time_column": "elapsed_ms", "value_column": "capacitor_V", "mode": "discharge"}),
        ("หาค่าคงตัวเวลา RC ตอนชาร์จจาก time_s และ voltage_V", {"time_column": "time_s", "value_column": "voltage_V", "mode": "charge"}),
        ("ฟิต tau ตอนคายประจุจาก elapsed_s กับ capacitor_V", {"time_column": "elapsed_s", "value_column": "capacitor_V", "mode": "discharge"}),
    )
    seeds += _tool(
        "pendulum_gravity", "physics",
        ("Estimate gravity from pendulum length_m and period_s.", {"length_column": "length_m", "period_column": "period_s"}),
        ("Calculate g using L_m versus T_s measurements.", {"length_column": "L_m", "period_column": "T_s"}),
        ("หาค่า g จากความยาวลูกตุ้ม length_m และคาบ period_s", {"length_column": "length_m", "period_column": "period_s"}),
        ("คำนวณความเร่งโน้มถ่วงด้วยข้อมูล L กับ T", {"length_column": "L", "period_column": "T"}),
    )
    seeds += _tool(
        "run_statistics", "statistics",
        ("Run a Welch t-test comparing control_uV and treated_uV.", {"test": "independent_t_test", "columns": ["control_uV", "treated_uV"]}),
        ("Do a one-way ANOVA across batch_a, batch_b and batch_c.", {"test": "one_way_anova", "columns": ["batch_a", "batch_b", "batch_c"]}),
        ("ทดสอบ t-test เปรียบเทียบ control_uV กับ treated_uV", {"test": "independent_t_test", "columns": ["control_uV", "treated_uV"]}),
        ("ทำ ANOVA ทางเดียวระหว่าง batch_a batch_b และ batch_c", {"test": "one_way_anova", "columns": ["batch_a", "batch_b", "batch_c"]}),
    )
    seeds += _tool(
        "global_fit", "statistics",
        ("Global fit a Gaussian with shared center and sigma across run1 and run2.", {"x_column": "wavelength_nm", "y_columns": ["run1", "run2"], "model": "gaussian", "shared": ["center", "sigma"]}),
        ("Global fit trial_a and trial_b at once, sharing the peak center.", {"x_column": "energy_eV", "y_columns": ["trial_a", "trial_b"], "model": "gaussian", "shared": ["center"]}),
        ("ฟิตร่วมแบบเกาส์เซียนโดยแชร์ center และ sigma ระหว่าง run1 กับ run2", {"x_column": "wavelength_nm", "y_columns": ["run1", "run2"], "model": "gaussian", "shared": ["center", "sigma"]}),
        ("ฟิตร่วม trial_a และ trial_b พร้อมกันโดยแชร์ตำแหน่งพีค", {"x_column": "energy_eV", "y_columns": ["trial_a", "trial_b"], "model": "gaussian", "shared": ["center"]}),
    )
    seeds += _tool(
        "analyze_peaks", "spectroscopy",
        ("Fit peaks in intensity vs raman_shift after baseline correction.", {"x_column": "raman_shift", "y_column": "intensity", "model": "gaussian", "baseline": "linear"}),
        ("Run the peak analyzer with Voigt profiles on counts vs two_theta, prominence 50.", {"x_column": "two_theta", "y_column": "counts", "model": "voigt", "prominence": 50.0}),
        ("ฟิตพีคใน intensity เทียบ raman_shift หลังแก้เบสไลน์", {"x_column": "raman_shift", "y_column": "intensity", "model": "gaussian", "baseline": "linear"}),
        ("ฟิตพีคแบบ Voigt ใน counts เทียบ two_theta โดยตั้ง prominence 50", {"x_column": "two_theta", "y_column": "counts", "model": "voigt", "prominence": 50.0}),
    )
    seeds += _tool(
        "list_analysis_recipes", "statistics",
        ("List the saved analysis recipes and their status.", {}),
        ("Show all saved analysis recipes and their recalculation mode.", {}),
        ("แสดงรายการสูตรวิเคราะห์ที่บันทึกไว้พร้อมสถานะ", {}),
        ("ขอดูรายการสูตรวิเคราะห์ทั้งหมดในโปรเจกต์นี้", {}),
    )
    seeds += _tool(
        "grid_xyz", "matrix",
        ("Grid xyz columns pos_x, pos_y and intensity into a 60x40 matrix.", {"x_column": "pos_x", "y_column": "pos_y", "z_column": "intensity", "nx": 60, "ny": 40, "method": "linear"}),
        ("Convert xyz data east_m, north_m, elevation_m to a matrix with cubic gridding.", {"x_column": "east_m", "y_column": "north_m", "z_column": "elevation_m", "method": "cubic"}),
        ("ทำกริดคอลัมน์ pos_x pos_y และ intensity เป็นเมทริกซ์ 60x40", {"x_column": "pos_x", "y_column": "pos_y", "z_column": "intensity", "nx": 60, "ny": 40, "method": "linear"}),
        ("แปลง xyz เป็นเมทริกซ์จาก east_m north_m elevation_m แบบ cubic", {"x_column": "east_m", "y_column": "north_m", "z_column": "elevation_m", "method": "cubic"}),
    )
    seeds += _tool(
        "matrix_transform", "matrix",
        ("Smooth matrix data with a Gaussian of sigma 2.", {"op": "smooth_gaussian", "sigma": 2}),
        ("Subtract background from the matrix using a plane fit.", {"op": "subtract_background", "mode": "plane"}),
        ("ปรับเมทริกซ์ให้เรียบด้วย Gaussian sigma 2", {"op": "smooth_gaussian", "sigma": 2}),
        ("ลบพื้นหลังเมทริกซ์ด้วยการฟิตระนาบ", {"op": "subtract_background", "mode": "plane"}),
    )
    seeds += _tool(
        "plot_matrix", "matrix",
        ("Plot matrix data as a heatmap with real coordinates.", {"kind": "heatmap"}),
        ("Draw a 3D surface from matrix Book values.", {"kind": "surface"}),
        ("พล็อตเมทริกซ์เป็น heatmap ตามพิกัดจริง", {"kind": "heatmap"}),
        ("วาดพื้นผิวจากเมทริกซ์แบบสามมิติ", {"kind": "surface"}),
    )
    return seeds


def answer_seeds() -> list[AnswerSeed]:
    """Examples that teach the router not to invent work or over-call tools."""
    return [
        AnswerSeed("en", "Hello, what can you help me with?", "I can inspect, plot, clean, fit and analyse the active SciPlotter data using local tools.", "greeting"),
        AnswerSeed("th", "สวัสดี ช่วยอะไรได้บ้าง", "ฉันช่วยตรวจ พล็อต ทำความสะอาด ฟิต และวิเคราะห์ข้อมูลที่เปิดอยู่ใน SciPlotter ด้วยเครื่องมือภายในเครื่องได้", "greeting"),
        AnswerSeed("en", "What is a scatter plot? Do not create one yet.", "A scatter plot shows the relationship between two numeric variables as points. I have not created a graph.", "explanation"),
        AnswerSeed("th", "กราฟ scatter คืออะไร ยังไม่ต้องสร้าง", "กราฟ scatter แสดงความสัมพันธ์ของตัวแปรตัวเลขสองตัวด้วยจุด และฉันยังไม่ได้สร้างกราฟ", "explanation"),
        AnswerSeed("en", "Do not modify my data.", "Understood. I will not run data-changing tools unless you explicitly request and confirm them.", "safety"),
        AnswerSeed("th", "อย่าแก้ข้อมูลของฉัน", "รับทราบ ฉันจะไม่เรียกเครื่องมือที่แก้ข้อมูลจนกว่าคุณจะสั่งและยืนยันอย่างชัดเจน", "safety"),
        AnswerSeed("en", "Upload this dataset to the cloud.", "SciPlotter AI is local-only and does not upload research data to a cloud service.", "privacy"),
        AnswerSeed("th", "อัปโหลดข้อมูลนี้ขึ้นคลาวด์", "SciPlotter AI ทำงานภายในเครื่องและไม่อัปโหลดข้อมูลงานวิจัยไปยังบริการคลาวด์", "privacy"),
        AnswerSeed("en", "Tell me the mean voltage without reading the data.", "I cannot invent a mean. I need to inspect the active data with a SciPlotter tool first.", "grounding"),
        AnswerSeed("th", "เดาค่าเฉลี่ย voltage มาเลยโดยไม่ต้องดูข้อมูล", "ฉันไม่ควรเดาค่าเฉลี่ย ต้องอ่านข้อมูลที่เปิดอยู่ด้วยเครื่องมือ SciPlotter ก่อน", "grounding"),
        AnswerSeed("en", "Which analysis is scientifically best?", "That depends on the measurement goal, units, sampling and assumptions. Tell me the experiment and intended conclusion.", "clarification"),
        AnswerSeed("th", "ควรวิเคราะห์แบบไหนดีที่สุด", "ต้องพิจารณาเป้าหมายการวัด หน่วย อัตราสุ่ม และสมมติฐาน กรุณาบอกชนิดการทดลองและข้อสรุปที่ต้องการ", "clarification"),
    ]
