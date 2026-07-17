"""Fresh, sealed acceptance cases for the post-v3 balanced candidate.

The cases cover the 14 critical tool-call behaviours plus direct answers in
Thai and English. They are not part of any training or validation assembly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from training.tool_cases import PROMPT_VALUE


@dataclass(frozen=True)
class FinalToolSeed:
    group: str
    tool: str
    language: str
    text: str
    arguments: Dict[str, Any]
    domain: str


@dataclass(frozen=True)
class FinalAnswerSeed:
    language: str
    text: str
    answer: str
    category: str


def final_tool_seeds() -> list[FinalToolSeed]:
    return [
        FinalToolSeed("describe_scope", "describe_data", "th", "ขอตาราง count mean std และช่วงของคอลัมน์ตัวเลขทั้งหมด โดยไม่ต้องเลือกชื่อ", {}, "general"),
        FinalToolSeed("summary_language", "summarize_data", "th", "วิเคราะห์บุ๊กนี้แล้วเล่าข้อค้นพบสำคัญเป็นภาษาไทย", {"language": "th"}, "general"),
        FinalToolSeed("plot_route", "plot_columns", "en", "Create a new line graph of sample_temp_C and chamber_temp_C against runtime_min.", {"style": "line", "x_column": "runtime_min", "y_columns": ["sample_temp_C", "chamber_temp_C"], "instruction": PROMPT_VALUE, "new_graph": True}, "plotting"),
        FinalToolSeed("gas_optional", "gas_live_control", "en", "Connect the gas logger over serial on COM15 at 19200 baud.", {"action": "connect", "transport": "serial", "port": "COM15", "baud": 19200}, "gas_sensor"),
        FinalToolSeed("fit_list_vs_run", "list_fit_models", "th", "แสดงเฉพาะรายชื่อโมเดลฟิตที่มีให้เลือก ยังไม่ต้องคำนวณ", {}, "fitting"),
        FinalToolSeed("weighted_fit", "fit_curve", "en", "Fit response_mV versus dose_ppm with a linear model, using response_sigma as absolute sigma.", {"model": "linear", "x_column": "dose_ppm", "y_column": "response_mV", "weight_column": "response_sigma", "weighting": "sigma"}, "fitting"),
        FinalToolSeed("fill_optional_value", "fill_missing", "th", "เติมค่าหายใน mass_mg ด้วยค่าถัดไป", {"method": "bfill", "column": "mass_mg"}, "cleaning"),
        FinalToolSeed("anomaly_threshold", "find_anomalies", "en", "Find IQR outliers in particle_nm at threshold 2.2 without removing rows.", {"method": "iqr", "threshold": 2.2, "column": "particle_nm"}, "cleaning"),
        FinalToolSeed("sort_direction", "sort_data", "th", "เรียงข้อมูลตาม cycle_number จากน้อยไปมาก", {"column": "cycle_number", "ascending": True}, "cleaning"),
        FinalToolSeed("fft_vs_psd_fft", "run_fft", "en", "Compute the Fourier transform of pickup_coil_V using elapsed_us as time.", {"column": "pickup_coil_V", "x_column": "elapsed_us"}, "signal"),
        FinalToolSeed("fft_vs_psd_psd", "power_spectrum", "th", "คำนวณ power spectral density ของ ambient_noise ที่ sampling rate 4096 Hz", {"fs": 4096, "column": "ambient_noise"}, "signal"),
        FinalToolSeed("format_only_named", "format_graph", "en", "Hide the grid and label only the X axis as Strain (%).", {"grid": False, "xlabel": "Strain (%)"}, "plotting"),
        FinalToolSeed("gas_on_off", "gas_response", "th", "วิเคราะห์ response ของ sensor_voltage เมื่อเปิดก๊าซที่ 25 วินาทีและปิดที่ 185 วินาที ใช้ experiment_time_s", {"t_on": 25, "t_off": 185, "time_column": "experiment_time_s", "column": "sensor_voltage"}, "gas_sensor"),
        FinalToolSeed("rc_mode", "rc_time_constant", "en", "Fit the RC charging time constant from capture_s and capacitor_charge_V.", {"time_column": "capture_s", "value_column": "capacitor_charge_V", "mode": "charge"}, "physics"),
    ]


def final_answer_seeds() -> list[FinalAnswerSeed]:
    return [
        FinalAnswerSeed("en", "Hi. Explain what SciPlotter Mini does in one sentence.", "SciPlotter Mini is a private local assistant that helps operate SciPlotter tools without uploading research data.", "greeting"),
        FinalAnswerSeed("th", "แนะนำตัวสั้น ๆ ว่าช่วยงานอะไรได้บ้าง", "ฉันเป็นผู้ช่วยภายในเครื่องสำหรับตรวจ พล็อต ทำความสะอาด ฟิต และวิเคราะห์ข้อมูลใน SciPlotter", "greeting"),
        FinalAnswerSeed("en", "What does a logarithmic axis mean? Do not alter the graph.", "A logarithmic axis spaces values by ratios or powers rather than equal differences; I have not changed the graph.", "explanation"),
        FinalAnswerSeed("th", "กราฟเส้นต่างจากกราฟกระจายอย่างไร ยังไม่ต้องพล็อต", "กราฟเส้นเชื่อมจุดเพื่อเน้นลำดับหรือแนวโน้ม ส่วนกราฟกระจายใช้จุดเพื่อดูความสัมพันธ์ และยังไม่มีการสร้างกราฟ", "explanation"),
        FinalAnswerSeed("en", "Never send my measurements to any online service.", "Understood. SciPlotter Mini is local-only and will not upload your measurements.", "privacy"),
        FinalAnswerSeed("th", "ข้อมูลนี้เป็นความลับ ห้ามส่งออกอินเทอร์เน็ต", "รับทราบ ผู้ช่วยทำงานภายในเครื่องและจะไม่ส่งข้อมูลนี้ไปยังบริการออนไลน์", "privacy"),
        FinalAnswerSeed("en", "Guess the standard deviation without opening the data.", "I cannot invent a standard deviation; I would need to inspect the active data first.", "grounding"),
        FinalAnswerSeed("th", "บอกค่าสูงสุดแบบเดา ๆ โดยไม่ต้องอ่านบุ๊ก", "ฉันไม่ควรเดาค่าสูงสุด ต้องอ่านข้อมูลในบุ๊กก่อนจึงจะตอบอย่างมีหลักฐานได้", "grounding"),
        FinalAnswerSeed("en", "Do not connect to any sensor.", "Understood. I will not connect to or control any sensor.", "safety"),
        FinalAnswerSeed("th", "ห้ามเปลี่ยนแปลงหรือลบแถวข้อมูล", "รับทราบ ฉันจะไม่เรียกเครื่องมือที่เปลี่ยนแปลงหรือลบข้อมูล", "safety"),
        FinalAnswerSeed("en", "Should I use FFT or PSD? Ask for context instead of running either one.", "That depends on whether you need spectral components or power distribution; please provide the sampling and analysis goal.", "clarification"),
        FinalAnswerSeed("th", "ควรฟิต linear หรือ exponential ดี ยังไม่ต้องฟิต", "ต้องดูสมมติฐานและรูปแบบข้อมูลก่อน กรุณาบอกกลไกที่คาดและช่วงข้อมูล โดยยังไม่มีการฟิต", "clarification"),
    ]
