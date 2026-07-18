"""Versioned, compact catalogue used to route tiny local models.

The application exposes dozens of tools. Sending every schema on every turn
wastes most of a sub-2B model's useful context, so this module selects a small,
auditable group based on the user's request. Selection only affects what the
model sees; all calculations still run in SciPlotter itself.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List

TOOL_SCHEMA_VERSION = "1.4"
ROUTER_PROTOCOL_VERSION = "2.0"
MAX_PROMPT_TOOLS = 8

GROUPS: Dict[str, tuple[str, ...]] = {
    "inspect": (
        "active_book", "list_books", "list_columns", "describe_data",
        "summarize_data",
    ),
    "plot": (
        "plot_columns", "list_charts", "plot_chart", "format_graph",
    ),
    "fit": (
        "list_fit_models", "fit_curve", "detect_peaks", "peak_metrics",
        "cross_correlation",
    ),
    "clean": (
        "smooth_data", "filter_signal", "moving_average", "fill_missing",
        "interpolate", "normalize", "detrend", "remove_outliers",
        "find_anomalies", "remove_duplicates", "sort_data",
    ),
    "signal": (
        "run_fft", "envelope", "signal_quality", "power_spectrum",
        "autocorrelation", "instantaneous_frequency", "harmonic_analysis",
    ),
    "science": (
        "run_statistics", "global_fit", "analyze_peaks", "list_analysis_recipes",
    ),
    "matrix": ("grid_xyz", "matrix_transform", "plot_matrix"),
    "gas": ("gas_live_control", "gas_response"),
    "specialty": (
        "cv_peaks", "tafel_analysis", "raman_dg", "normalize_spectrum",
        "iv_conductivity", "arrhenius", "ohms_law", "rc_time_constant",
        "pendulum_gravity",
    ),
    "file": ("open_file",),
}

KEYWORDS: Dict[str, tuple[str, ...]] = {
    "inspect": (
        "column", "data", "summary", "summar", "describe", "statistic",
        "book", "คอลัมน์", "ข้อมูล", "สรุป", "วิเคราะห์",
    ),
    "plot": (
        "plot", "graph", "chart", "scatter", "line", "bar", "axis",
        "กราฟ", "พล็อต", "พลอต", "แผนภูมิ", "แกน",
    ),
    "fit": (
        "fit", "regression", "curve", "peak", "correlation", "พีค",
        "ฟิต", "ถดถอย", "สหสัมพันธ์",
    ),
    "clean": (
        "clean", "smooth", "filter", "missing", "interpol", "normaliz",
        "outlier", "anomal", "duplicate", "sort", "moving average",
        "ทำความสะอาด", "กรอง", "ค่าหาย", "เอาต์ไลเออร์", "เรียง",
    ),
    "signal": (
        "fft", "frequency", "spectrum", "spectral", "harmonic", "envelope",
        "snr", "autocorrelation", "ความถี่", "สเปกตรัม", "ฮาร์มอนิก",
    ),
    "science": (
        "t-test", "t test", "anova", "hypothesis", "p-value",
        "p value", "nonparametric", "mann-whitney", "wilcoxon", "kruskal",
        "global fit", "shared parameter", "peak fit", "peak analyzer",
        "analysis recipe",
        "ทดสอบสมมติฐาน", "ค่าพี", "ฟิตร่วม", "ฟิตพีค", "สูตรวิเคราะห์", "ที-เทสต์",
    ),
    "matrix": (
        "matrix", "gridding", "grid xyz", "xyz to matrix", "surface plot",
        "image matrix", "เมทริกซ์", "กริด", "พื้นผิวสามมิติ",
    ),
    "gas": ("gas", "sensor", "daq", "serial", "com", "ก๊าซ", "เซนเซอร์"),
    "specialty": (
        "cv", "cyclic volt", "tafel", "raman", "conductivity", "arrhenius",
        "ohm", "pendulum", "electrochem", "รามาน", "การนำไฟฟ้า", "ลูกตุ้ม",
    ),
    "file": ("open file", "load file", "csv", "xlsx", "เปิดไฟล์"),
}

# Specific aliases rank the requested capability ahead of the rest of a broad
# group. This matters for tiny models: the clean/specialty groups are larger
# than the ten-tool prompt budget, and Thai requests cannot be ranked reliably
# from the English function name alone.
TOOL_ALIASES: Dict[str, tuple[str, ...]] = {
    "list_columns": ("what columns", "list columns", "column names", "คอลัมน์อะไร", "รายชื่อคอลัมน์"),
    "describe_data": ("descriptive statistics", "describe data", "สถิติพรรณนา", "ค่าเฉลี่ยและส่วนเบี่ยงเบน"),
    "summarize_data": ("summarize", "analyse", "analyze", "สรุปข้อมูล", "วิเคราะห์ข้อมูล"),
    "plot_columns": ("plot", "graph", "scatter", "พล็อต", "พลอต", "สร้างกราฟ"),
    "active_book": ("active book", "active dataset", "บุ๊กที่ใช้งาน", "ชุดข้อมูลที่ใช้งาน"),
    "gas_live_control": ("gas live", "connect com", "ni-daq", "mark gas", "รับข้อมูลก๊าซ", "ต่อ com", "ทำเครื่องหมายก๊าซ", "ทำ marker", "เริ่มเปิด ammonia"),
    "list_fit_models": ("fit models", "fitting models", "โมเดลฟิต", "สมการฟิต"),
    "fit_curve": ("fit curve", "linear fit", "gaussian fit", "ฟิตเส้นโค้ง", "ฟิตแบบ"),
    "smooth_data": ("smooth", "smoothing", "savitzky", "gaussian smoothing", "ทำให้เรียบ", "เรียบด้วย", "สมูท"),
    "filter_signal": ("butterworth", "lowpass", "highpass", "bandpass", "กรองสัญญาณ", "โลว์พาส"),
    "moving_average": ("moving average", "rolling mean", "ค่าเฉลี่ยเคลื่อนที่"),
    "fill_missing": ("fill missing", "fill nan", "replace nan", "เติมค่าหาย", "เติม nan", "เติมช่องว่าง", "แทนค่า nan", "แทน nan"),
    "interpolate": ("interpolate", "interpolation", "ประมาณค่าระหว่าง", "อินเตอร์โพเลต"),
    "normalize": ("z-score", "zscore", "min-max", "zero-to-one", "normalize data", "ทำมาตรฐาน", "ปรับสเกล", "ช่วง 0 ถึง 1"),
    "detrend": ("detrend", "remove trend", "trend from", "remove baseline", "order baseline", "ลบแนวโน้ม", "ลบเบสไลน์"),
    "remove_outliers": ("remove outlier", "z-score outliers", "drop outlier", "drop iqr outliers", "ลบเอาต์ไลเออร์", "ลบค่าผิดปกติ", "ตัดค่าผิดปกติ"),
    "find_anomalies": ("find anomal", "report anomal", "report anomalies", "report outlier", "find iqr outliers", "หา anomaly", "หา outlier", "ตรวจ anomaly", "หาค่าผิดปกติ", "รายงาน anomaly", "รายงาน outlier", "รายงานเอาต์ไลเออร์"),
    "remove_duplicates": ("remove duplicate", "deduplicate", "ลบข้อมูลซ้ำ", "ลบแถวซ้ำ", "แถวข้อมูลซ้ำ", "ข้อมูลที่ซ้ำกัน"),
    "sort_data": ("sort data", "sort the data", "sort by", "sort temperature", "เรียงข้อมูล", "เรียงตาม", "เรียง intensity", "จากน้อยไปมาก", "จากมากไปน้อย", "ต่ำสุดขึ้นก่อน", "สูงสุดอยู่บนสุด", "ค่าต่ำไปค่าสูง", "สูงสุดลงมาต่ำสุด"),
    "run_fft": ("fft", "fourier", "ฟูเรียร์"),
    "envelope": ("envelope", "hilbert envelope", "ซองสัญญาณ", "เอนเวโลป"),
    "signal_quality": ("signal quality", "snr", "noise floor", "คุณภาพสัญญาณ", "สัญญาณต่อสัญญาณรบกวน"),
    "power_spectrum": ("power spectrum", "power spectral density", "psd", "สเปกตรัมกำลัง", "ความหนาแน่นสเปกตรัม"),
    "autocorrelation": ("autocorrelation", "auto-correlation", "ออโตคอริเลชัน", "สหสัมพันธ์ตัวเอง"),
    "instantaneous_frequency": ("instantaneous frequency", "ความถี่ทันที", "ความถี่ชั่วขณะ"),
    "harmonic_analysis": ("harmonic analysis", "harmonic components", "วิเคราะห์ฮาร์มอนิก", "องค์ประกอบฮาร์มอนิก"),
    "peak_metrics": ("peak metrics", "fwhm", "peak area", "พารามิเตอร์พีค", "ความกว้างครึ่งสูง"),
    "detect_peaks": ("detect peaks", "find peaks", "หา peak", "หาพีค", "ตรวจจับพีค"),
    "cross_correlation": ("cross correlation", "cross-correlate", "find the lag", "สหสัมพันธ์ข้าม", "ครอสคอริเลชัน", "หาค่า lag"),
    "format_graph": ("format graph", "graph title", "axis label", "log axis", "จัดรูปแบบกราฟ", "ตั้งชื่อกราฟ", "ตั้งชื่อแกน", "แกนล็อก"),
    "list_charts": ("list charts", "chart types", "ชนิดกราฟ", "กราฟที่มี"),
    "plot_chart": ("advanced chart", "plot chart", "heatmap chart", "กราฟขั้นสูง", "สร้างแผนภูมิ", "surface_3d", "scatter_3d", "wireframe_3d", "matrix_heatmap", "contour_3d", "trisurface_3d", "bar_3d"),
    "list_books": ("list books", "open books", "บุ๊กทั้งหมด", "รายชื่อบุ๊ก"),
    "open_file": ("open file", "load csv", "load excel", "เปิดไฟล์", "โหลดไฟล์"),
    "grid_xyz": ("grid xyz", "xyz to matrix", "gridding", "convert xyz", "ทำกริด", "แปลง xyz เป็นเมทริกซ์"),
    "matrix_transform": ("matrix transform", "transpose matrix", "smooth matrix", "subtract background", "rotate matrix", "หมุนเมทริกซ์", "ลบพื้นหลังเมทริกซ์", "ปรับเมทริกซ์"),
    "plot_matrix": ("plot matrix", "matrix heatmap", "matrix surface", "surface from matrix", "พล็อตเมทริกซ์", "ฮีตแมปเมทริกซ์", "พื้นผิวจากเมทริกซ์"),
    "run_statistics": ("t-test", "t test", "anova", "regression", "hypothesis test", "p-value", "mann-whitney", "wilcoxon", "kruskal", "ทดสอบสมมติฐาน", "ที-เทสต์", "การถดถอย", "หาค่าพี"),
    "global_fit": ("global fit", "shared parameter", "fit multiple datasets", "ฟิตร่วม", "พารามิเตอร์ร่วม", "ฟิตหลายชุด"),
    "analyze_peaks": ("peak analyzer", "fit peaks", "multi-peak fit", "baseline and peaks", "ฟิตพีค", "วิเคราะห์พีค", "ฟิตหลายพีค"),
    "list_analysis_recipes": ("list recipes", "analysis recipe", "analysis recipes", "รายการสูตรวิเคราะห์", "สูตรวิเคราะห์ที่มี", "สูตรวิเคราะห์ใด", "มีสูตรวิเคราะห์"),
    "gas_response": ("gas response", "response time", "recovery time", "การตอบสนองก๊าซ", "เวลาฟื้นตัว", "t_on", "t_off", "รอบตอบสนอง"),
    "cv_peaks": ("cv peaks", "cyclic voltammetry", "cyclic-voltammetry", "oxidation peak", "δep", "peak-current ratio", "พีค cv", "ไซคลิกโวลแทมเมทรี", "อัตราส่วนกระแสพีค"),
    "tafel_analysis": ("tafel", "exchange current", "ทาเฟล", "กระแสแลกเปลี่ยน"),
    "raman_dg": ("raman d/g", "d/g ratio", "raman ratio", "รามาน d/g", "อัตราส่วนดีจี"),
    "normalize_spectrum": ("normalize spectrum", "absorbance spectrum", "area-normalize", "area normalization", "spectrum normalization", "ปรับสเปกตรัม", "ทำสเปกตรัมเป็นมาตรฐาน"),
    "iv_conductivity": ("iv conductivity", "calculate conductivity", "conductivity from i-v", "resistivity from i-v", "find resistivity", "การนำไฟฟ้าจาก iv", "หาการนำไฟฟ้า", "สภาพต้านทานจาก iv", "คำนวณสภาพต้านทาน"),
    "arrhenius": ("arrhenius", "activation energy", "อาร์เรเนียส", "พลังงานกระตุ้น"),
    "ohms_law": ("ohm's law", "ohms law", "resistance from iv", "calculate resistance", "กฎของโอห์ม", "หาความต้านทาน", "ฟิตความต้านทาน"),
    "rc_time_constant": ("rc time constant", "time constant", "discharge tau", "ค่าคงตัวเวลา rc", "ไทม์คอนสแตนต์", "ฟิต tau", "หา tau", "คายประจุ", "กำลังชาร์จ"),
    "pendulum_gravity": ("pendulum gravity", "gravity from pendulum", "calculate g using", "ลูกตุ้มหาค่า g", "ลูกตุ้ม", "ความเร่งโน้มถ่วง"),
}

MUTATING_TOOLS = {
    "smooth_data", "filter_signal", "moving_average", "fill_missing",
    "interpolate", "normalize", "detrend", "remove_outliers",
    "remove_duplicates", "sort_data", "normalize_spectrum",
}
DEVICE_TOOLS = {"gas_live_control"}
CREATE_TOOLS = {
    "plot_columns", "plot_chart", "fit_curve", "run_fft", "envelope",
    "power_spectrum", "autocorrelation", "instantaneous_frequency",
    "harmonic_analysis", "detect_peaks", "cross_correlation", "open_file",
    "cv_peaks", "tafel_analysis", "raman_dg", "iv_conductivity",
    "arrhenius", "ohms_law", "rc_time_constant", "pendulum_gravity",
    "run_statistics", "global_fit", "analyze_peaks",
    "grid_xyz", "matrix_transform", "plot_matrix",
}


_EXPLANATION_OR_NEGATION_CUES = (
    "explain", "what is", "how does", "do not", "don't", "not yet",
    "without plotting", "without fitting", "อธิบาย", "คืออะไร", "ทำงานยังไง",
    "อย่า", "ไม่ต้อง", "ยังไม่ต้อง",
)


def select_high_confidence_tool(
    user_text: str,
    available: Iterable[str],
) -> str | None:
    """Return a tool only for narrow intents that are safe to classify exactly.

    This is the deterministic half of the hybrid router.  It deliberately
    handles only command-shaped phrases with strong semantic markers; all
    ambiguous requests still go to the local model.  Arguments remain the
    responsibility of the Safe Router resolver.
    """
    folded = " ".join(str(user_text or "").casefold().split())
    available_names = set(available)
    if not folded or any(cue in folded for cue in _EXPLANATION_OR_NEGATION_CUES):
        return None

    if "list_fit_models" in available_names:
        fit_subject = any(
            cue in folded
            for cue in (
                "fit model", "fitting model", "curve model", "regression model",
                "โมเดลฟิต", "สมการฟิต", "ฟิตเส้นโค้ง",
            )
        )
        english_list = any(
            cue in folded
            for cue in (
                "list", "available", "catalog", "catalogue", "options",
                "which models", "what models", "models can i", "kinds of",
            )
        )
        thai_list = (
            "รายชื่อ" in folded
            or "รายการ" in folded
            or "ให้เลือก" in folded
            or ("มี" in folded and "อะไร" in folded and "บ้าง" in folded)
            or ("แบบไหน" in folded and "บ้าง" in folded)
        )
        if fit_subject and (english_list or thai_list):
            return "list_fit_models"

    if "plot_chart" in available_names:
        advanced_chart = any(
            cue in folded
            for cue in (
                "surface 3d", "3d surface", "surface_3d", "surface 3 มิติ",
                "wireframe", "wireframe 3 มิติ", "scatter 3d", "3d scatter",
                "scatter_3d", "scatter 3 มิติ", "bar 3d", "3d bar",
                "bar_3d", "trisurface", "contour 3d", "3d contour",
                "contour_3d", "matrix heatmap",
            )
        )
        plot_command = any(
            cue in folded
            for cue in (
                "plot", "create", "make a", "draw", "show a", "show the",
                "พล็อต", "พลอต", "สร้างกราฟ", "วาดกราฟ", "แสดงกราฟ",
            )
        )
        if advanced_chart and plot_command:
            return "plot_chart"

    return None


def metadata_for(name: str) -> Dict[str, str]:
    category = next(
        (group for group, names in GROUPS.items() if name in names), "general"
    )
    if name in DEVICE_TOOLS:
        risk = "device"
    elif name in MUTATING_TOOLS:
        risk = "mutate"
    elif name in CREATE_TOOLS:
        risk = "create"
    else:
        risk = "read"
    return {"category": category, "risk": risk}


def _alias_matches(alias: str, folded_text: str) -> bool:
    alias = alias.casefold()
    # Word boundaries avoid treating "plot" as a match inside "SciPlotter".
    if alias.isascii():
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        return re.search(pattern, folded_text) is not None
    return alias in folded_text


def select_tool_names(
    user_text: str,
    available: Iterable[str],
    *,
    limit: int = MAX_PROMPT_TOOLS,
) -> List[str]:
    """Select the smallest useful tool set while preserving registry order."""
    available_names = list(available)
    if len(available_names) <= limit:
        return available_names

    folded = str(user_text or "").casefold()
    matched_groups = [
        group
        for group, words in KEYWORDS.items()
        if any(_alias_matches(word, folded) for word in words)
    ]
    if not matched_groups:
        matched_groups = ["inspect"]

    registry_order = {name: index for index, name in enumerate(available_names)}
    specific: list[tuple[int, int, str]] = []
    for name in available_names:
        aliases = (name.replace("_", " "), *TOOL_ALIASES.get(name, ()))
        scores = [len(alias) for alias in aliases if alias and _alias_matches(alias, folded)]
        if scores:
            specific.append((-max(scores), registry_order[name], name))
    specific_names = [name for _score, _index, name in sorted(specific)]

    wanted = set(GROUPS["inspect"][:3])
    for group in matched_groups:
        wanted.update(GROUPS[group])
    ordered = list(specific_names)
    ordered.extend(
        name for name in available_names if name in wanted and name not in ordered
    )
    if len(ordered) < min(4, limit):
        ordered.extend(
            name for name in available_names if name not in ordered
        )
    return ordered[: max(1, int(limit))]
