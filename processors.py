# processors.py
import logging
import numpy as np
import pandas as pd
import re
import warnings

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple
import numexpr as ne
from scipy.optimize import curve_fit
from scipy.stats import t

def add_time_bangkok(df: pd.DataFrame, time_col: str, new_col: str = None):
    """เพิ่มคอลัมน์เวลา +7 ชั่วโมง (Asia/Bangkok)"""
    if new_col is None:
        new_col = f"{time_col}_BKK"
    s = pd.to_datetime(df[time_col], errors="coerce")
    s = s.dt.tz_localize("UTC", nonexistent="shift_forward", ambiguous="NaT").dt.tz_convert("Asia/Bangkok")
    df[new_col] = s
    return new_col

def add_magnitude(df: pd.DataFrame, col_x: str, col_y: str, col_z: str, new_col: str = "B_mag"):
    """เพิ่มคอลัมน์ |B| = sqrt(Bx^2 + By^2 + Bz^2)"""
    bx = pd.to_numeric(df[col_x], errors="coerce")
    by = pd.to_numeric(df[col_y], errors="coerce")
    bz = pd.to_numeric(df[col_z], errors="coerce")
    df[new_col] = np.sqrt(bx**2 + by**2 + bz**2)
    return new_col

def add_moving_average(df: pd.DataFrame, col: str, window: int = 25, new_col: str = None):
    """เพิ่มคอลัมน์ค่าถัวเฉลี่ยเคลื่อนที่ของคอลัมน์ที่เลือก"""
    if new_col is None:
        new_col = f"{col}_MA{window}"
    s = pd.to_numeric(df[col], errors="coerce")
    df[new_col] = s.rolling(window=window, min_periods=max(1, window//3)).mean()
    return new_col

# ---- จัดชนิดคอลัมน์แบบรวดเร็ว ----
def apply_column_types(df: pd.DataFrame, mapping: dict):
    """
    mapping เช่น {"id":"String","score":"Integer","time":"Datetime","x":"Float","y":"Auto"}
    """
    for col, typ in (mapping or {}).items():
        if col not in df.columns:
            continue
        s = df[col]

        if typ == "String":
            df[col] = s.astype("string").fillna(pd.NA)

        elif typ == "Integer":
            df[col] = pd.to_numeric(s, errors="coerce").astype("Int64")

        elif typ == "Float":
            df[col] = pd.to_numeric(s, errors="coerce").astype(float)

        elif typ == "Datetime":
            df[col] = pd.to_datetime(s, errors="coerce", infer_datetime_format=True)

        else:
            pass
    return df

# ---- FFT ----
def _infer_sampling_rate(x):
    """เดาอัตราสุ่มจากแกน X: ถ้าเป็นเวลา → วินาที; ถ้าเป็นตัวเลข → ใช้ median(diff)"""
    x = pd.Series(x)
    try:
        xdt = pd.to_datetime(x, errors="coerce")
        if xdt.notna().sum() > 1:
            # ใช้วิธีเดียวกับ spectrogram: คำนวณ time differences เป็นวินาที
            time_diffs = xdt.diff().dropna()
            time_diffs_sec = time_diffs.dt.total_seconds()
            median_diff = time_diffs_sec.median()
            if pd.notna(median_diff) and median_diff > 0:
                return 1.0 / median_diff  # Hz
    except Exception:
        pass
    xnum = pd.to_numeric(x, errors="coerce")
    dx = xnum.diff().dropna().median()
    if pd.notna(dx) and dx > 0:
        return 1.0 / dx
    raise ValueError("เดาอัตราสุ่ม (sampling rate) ไม่ได้")

def compute_fft(df: pd.DataFrame, x_col: str, y_col: str, detrend=True, window="hanning"):
    """
    คำนวณ FFT แบบหนึ่งแกน (real signal) → คืน (df_fft, fs)
    df_fft columns = ['freq_Hz', 'amplitude', 'power']
    """
    y = pd.to_numeric(df[y_col], errors="coerce").dropna().values
    if y.size < 4:
        raise ValueError("ข้อมูลน้อยเกินไปสำหรับ FFT")

    fs = _infer_sampling_rate(df[x_col].values)  # Hz

    if detrend:
        y = y - np.mean(y)

    if window in ("hanning", "hann"):
        w = np.hanning(y.size)
    elif window in ("hamming",):
        w = np.hamming(y.size)
    else:
        w = np.ones_like(y)
    yw = y * w

    Y = np.fft.rfft(yw)
    freq = np.fft.rfftfreq(yw.size, d=1.0/fs)
    amp = np.abs(Y) / (yw.size/2.0)
    power = (np.abs(Y)**2) / (yw.size)

    df_fft = pd.DataFrame({
        "freq_Hz": freq,
        "amplitude": amp,
        "power": power
    })
    # คืนทั้งผลลัพธ์ FFT และอัตราสุ่ม เพื่อให้ฝั่ง UI/unpack ใช้งานได้ถูกต้อง
    return df_fft, fs

# CHANGE: Utilities for curve fitting with datetime X
def _to_seconds_from_start(x_dt):
    """รับ pandas Series/Index แบบ datetime64 คืนเป็น (t_sec, t0)
    ที่ t_sec คือวินาทีจากจุดเริ่มต้น และ t0 คือเวลาเริ่ม (Timestamp)
    """
    x_dt = pd.to_datetime(x_dt)
    t0 = x_dt.iloc[0] if hasattr(x_dt, "iloc") else x_dt[0]
    # บางเวอร์ชันต้องใช้ .dt.total_seconds()
    if hasattr(x_dt, "dt"):
        t_sec = (x_dt - t0).dt.total_seconds()
    else:
        t_sec = (x_dt - t0).total_seconds()  # type: ignore
    return t_sec.to_numpy(dtype=float), pd.to_datetime(t0)

def fit_poly_datetime(x_dt, y, order: int = 1, n_points: int = 400):
    """
    ฟิต y = P(t) โดย t คือ 'วินาทีจากจุดเริ่ม', แล้วแปลงกลับเป็น datetime สำหรับพล็อต
    คืนค่า: x_fit_datetime (Series of Timestamp), y_fit (ndarray), meta (dict)
    """
    t_sec, t0 = _to_seconds_from_start(x_dt)
    scale = float(max(np.max(t_sec) - np.min(t_sec), 1.0))
    t_scaled = (t_sec - float(np.mean(t_sec))) / scale
    
    # แก้ไข: จัดการ NaN values ก่อนการฟิต
    y_clean = np.asarray(y, dtype=float)
    mask = np.isfinite(y_clean) & np.isfinite(t_scaled)
    if mask.sum() < order + 1:
        raise ValueError(f"ข้อมูลที่ใช้ได้น้อยเกินไปสำหรับการฟิตพอลิโนเมียลระดับ {order}")
    
    t_clean = t_scaled[mask]
    y_clean = y_clean[mask]
    
    coeffs = np.polyfit(t_clean, y_clean, order)
    p = np.poly1d(coeffs)
    t_scaled_fit = np.linspace(float(np.min(t_scaled)), float(np.max(t_scaled)), int(n_points))
    y_fit = p(t_scaled_fit)
    t_fit_sec = t_scaled_fit * scale + float(np.mean(t_sec))
    x_fit_dt = pd.to_datetime(t0) + pd.to_timedelta(t_fit_sec, unit="s")
    meta = {"coeffs": coeffs, "t0": t0, "scale": scale}
    return x_fit_dt, y_fit, meta

# ---- Plot Beautification ----
def beautify_axes(ax, title=None, x_is_datetime=False):
    """
    Beautify matplotlib axes with consistent styling:
    - Enable minor ticks and light minor grid
    - Set datetime formatting if x_is_datetime=True
    - Set optional left-aligned title
    - Configure legend with transparency
    - Call tight_layout and redraw
    """
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    
    # Enable minor ticks and grid
    ax.minorticks_on()
    ax.grid(True, which='major', alpha=0.3, linestyle='-', linewidth=0.5)
    ax.grid(True, which='minor', alpha=0.1, linestyle=':', linewidth=0.3)
    
    # ปรับแต่งการแสดงผลให้ดูดีขึ้น
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(0.8)
    ax.spines['bottom'].set_linewidth(0.8)
    
    # ปรับแต่งขนาดตัวอักษร
    ax.tick_params(axis='both', which='major', labelsize=9)
    ax.tick_params(axis='both', which='minor', labelsize=7)
    
    # Set datetime formatting if needed
    if x_is_datetime:
        try:
            # ใช้ AutoDateLocator และ ConciseDateFormatter สำหรับ datetime
            locator = mdates.AutoDateLocator(maxticks=8)
            formatter = mdates.ConciseDateFormatter(locator)
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(formatter)
            
            # หมุนป้ายกำกับแกน X เพื่อให้อ่านง่าย
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
            
            # ปรับแต่งระยะห่างของป้ายกำกับ
            ax.tick_params(axis='x', which='major', labelsize=9)
            
        except Exception:
            logger.debug("DateTime formatting failed", exc_info=True)
            # Fallback to basic datetime formatting
            try:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
            except Exception:
                pass
    
    # Set optional title - ensure it's displayable
    if title:
        try:
            # Try to set title with original text
            ax.set_title(title, loc='left', pad=10)
        except Exception:
            # If title contains problematic characters, use a safe fallback
            try:
                safe_title = str(title).encode('ascii', 'ignore').decode('ascii')
                if safe_title.strip():
                    ax.set_title(safe_title, loc='left', pad=10)
                else:
                    ax.set_title("Chart", loc='left', pad=10)
            except Exception:
                ax.set_title("Chart", loc='left', pad=10)
    
    # Configure legend - use safer methods that work across matplotlib versions
    if ax.get_legend():
        legend = ax.get_legend()
        try:
            # Try multiple methods to set legend properties
            if hasattr(legend, 'set_frame_alpha'):
                legend.set_frame_alpha(0.15)
            elif hasattr(legend, 'get_frame') and hasattr(legend.get_frame(), 'set_alpha'):
                legend.get_frame().set_alpha(0.15)
            
            if hasattr(legend, 'set_edgecolor'):
                legend.set_edgecolor('#3b3f46')
            elif hasattr(legend, 'get_frame') and hasattr(legend.get_frame(), 'set_edgecolor'):
                legend.get_frame().set_edgecolor('#3b3f46')
        except Exception:
            # If all methods fail, just continue without legend styling
            pass
    
    # NOTE: no tight_layout() or canvas.draw() here. The canvas figure uses the
    # 'tight' layout engine, so layout happens inside the caller's single draw —
    # calling tight_layout()+draw() here rendered every plot 2–3× (slow).

# ---- Derived Column Expression Evaluation ----
def _coerce_numeric_series(value, length=None, name="value"):
    """Convert Series/array-like to numeric pandas Series or scalar float."""
    if value is None:
        return None
    if np.isscalar(value):
        return float(value)
    if isinstance(value, pd.Series):
        series = pd.to_numeric(value, errors='coerce')
        if length is not None and len(series) != length:
            raise ValueError(f"{name} ต้องมีจำนวนแถวเท่ากับข้อมูลต้นฉบับ")
        return series
    series = pd.Series(value)
    series = pd.to_numeric(series, errors='coerce')
    if length is not None and len(series) != length:
        raise ValueError(f"{name} ต้องมีจำนวนแถวเท่ากับข้อมูลต้นฉบับ")
    return series


def _diff_series(y, dt=None, x=None, method='central'):
    """Numerical derivative of y with respect to x or dt."""
    if y is None:
        raise ValueError("ต้องระบุคอลัมน์สำหรับอนุพันธ์ (diff)")
    y_series = _coerce_numeric_series(y)
    if y_series.isna().all():
        raise ValueError("คอลัมน์ที่เลือกไม่มีข้อมูลตัวเลขเพียงพอสำหรับอนุพันธ์")
    arr = y_series.to_numpy(dtype=float)
    if arr.size < 2:
        return pd.Series(np.zeros_like(arr), index=y_series.index)

    spacing = None
    if x is not None:
        x_series = _coerce_numeric_series(x, length=len(arr), name="x")
        if isinstance(x_series, pd.Series):
            if x_series.isna().all():
                raise ValueError("คอลัมน์เวลา/ตำแหน่งมีค่า NaN ทั้งหมด")
            spacing = x_series.to_numpy(dtype=float)
        else:
            spacing = float(x_series)
    elif dt is not None:
        dt_value = _coerce_numeric_series(dt, length=len(arr), name="dt")
        if isinstance(dt_value, pd.Series):
            if dt_value.isna().all():
                raise ValueError("dt ที่ระบุไม่มีข้อมูลตัวเลข")
            spacing = dt_value.to_numpy(dtype=float)
        else:
            spacing = float(dt_value)
    else:
        spacing = 1.0

    try:
        gradient = np.gradient(arr, spacing)
    except Exception as exc:
        raise ValueError(f"ไม่สามารถคำนวณอนุพันธ์ได้: {exc}")
    return pd.Series(gradient, index=y_series.index)


def _integrate_series(y, dt=None, x=None, initial=0.0, method='trapezoid'):
    """Cumulative integral of y with respect to x or dt."""
    if y is None:
        raise ValueError("ต้องระบุคอลัมน์สำหรับอินทิกรัล (integrate)")
    y_series = _coerce_numeric_series(y)
    if y_series.isna().all():
        raise ValueError("คอลัมน์ที่เลือกไม่มีข้อมูลตัวเลขเพียงพอสำหรับอินทิกรัล")
    arr = y_series.to_numpy(dtype=float)
    n = arr.size
    if n == 0:
        return y_series.astype(float)

    def _prepare_spacing_from_series(series, label):
        series = _coerce_numeric_series(series, length=n, name=label)
        if isinstance(series, pd.Series):
            if series.isna().all():
                raise ValueError(f"{label} ที่ระบุไม่มีข้อมูลตัวเลข")
            return series.to_numpy(dtype=float)
        return float(series)

    spacing_values = None
    if x is not None:
        spacing_values = _prepare_spacing_from_series(x, "x")
        if np.isscalar(spacing_values):
            dx = float(spacing_values)
        else:
            dx = np.diff(spacing_values)
    elif dt is not None:
        spacing_values = _prepare_spacing_from_series(dt, "dt")
        if np.isscalar(spacing_values):
            dx = float(spacing_values)
        else:
            arr_dt = np.asarray(spacing_values, dtype=float)
            if arr_dt.size == n:
                dx = np.diff(arr_dt)
            elif arr_dt.size == n - 1:
                dx = arr_dt
            else:
                raise ValueError("ความยาว dt ต้องเท่ากับข้อมูลหรือสั้นกว่า 1 ตำแหน่ง")
    else:
        dx = 1.0

    cumulative = np.zeros_like(arr, dtype=float)
    if n > 1:
        if np.isscalar(dx):
            increments = 0.5 * (arr[1:] + arr[:-1]) * float(dx)
        else:
            dx = np.asarray(dx, dtype=float)
            if dx.size != n - 1:
                raise ValueError("จำนวนช่วงเวลาไม่ตรงกับข้อมูลสำหรับการอินทิกรัล")
            increments = 0.5 * (arr[1:] + arr[:-1]) * dx
        cumulative[1:] = np.cumsum(increments)
    cumulative = cumulative + float(initial)
    return pd.Series(cumulative, index=y_series.index)

def evaluate_expression(df: pd.DataFrame, expression: str, engine: str = "auto") -> pd.Series:
    """
    ประเมินนิพจน์ทางคณิตศาสตร์จากคอลัมน์ที่มีอยู่ใน DataFrame
    
    Args:
        df: DataFrame ที่มีข้อมูล
        expression: นิพจน์ที่ต้องการประเมิน (เช่น `Bx * By`, `sqrt(Bx**2 + By**2)`)
        engine: เครื่องมือประเมิน ("auto", "numexpr", "python")
    
    Returns:
        pd.Series: ผลลัพธ์การประเมินนิพจน์
        
    Raises:
        ValueError: หากนิพจน์ไม่ถูกต้องหรือมีข้อผิดพลาด
        KeyError: หากคอลัมน์ที่อ้างอิงไม่มีอยู่ใน DataFrame
    """
    if not expression or not expression.strip():
        raise ValueError("นิพจน์ไม่สามารถเป็นค่าว่างได้")
    
    # ทำความสะอาดนิพจน์ - ลบช่องว่างส่วนเกิน
    expression = expression.strip()
    
    # แปลงชื่อคอลัมน์ที่ครอบด้วย backtick ให้เป็นชื่อตัวแปรที่ถูกต้องสำหรับการประเมิน
    # รองรับทั้ง `Bx` และ `Mag Field` (ชื่อที่มีช่องว่าง)
    def replace_backtick_columns(match):
        """แทนที่ `column_name` ด้วยชื่อตัวแปรที่ถูกต้องสำหรับการประเมิน"""
        col_name = match.group(1)  # เอาเฉพาะส่วนใน backtick
        if col_name not in df.columns:
            raise KeyError(f"ไม่พบคอลัมน์ '{col_name}' ในข้อมูล")
        # ถ้าชื่อคอลัมน์มีช่องว่าง ให้แทนที่ด้วยชื่อตัวแปรที่ถูกต้อง
        # ใช้ underscore แทนช่องว่าง
        var_name = col_name.replace(' ', '_')
        return var_name
    
    # ใช้ regex หาชื่อคอลัมน์ที่ครอบด้วย backtick
    expression_clean = re.sub(r'`([^`]+)`', replace_backtick_columns, expression)
    
    # ตรวจสอบว่าคอลัมน์ที่อ้างอิงมีอยู่ใน DataFrame หรือไม่
    # หาชื่อตัวแปรในนิพจน์ (ตัวอักษร, ตัวเลข, underscore, ช่องว่าง)
    # แยกการตรวจสอบออกเป็น 2 ส่วน: ชื่อคอลัมน์ที่ครอบด้วย backtick และตัวแปรอื่นๆ
    backtick_vars = re.findall(r'`([^`]+)`', expression)  # หาชื่อคอลัมน์ใน backtick
    
    # หาตัวแปรอื่นๆ ในนิพจน์ที่ทำความสะอาดแล้ว (หลังจากการแทนที่ backtick)
    # แต่ต้องไม่รวมฟังก์ชันที่อนุญาต
    other_vars = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', expression_clean)
    
    # รวมตัวแปรทั้งหมดและกรองฟังก์ชันที่อนุญาต
    all_vars = set(backtick_vars + other_vars)
    allowed_functions = {'sqrt', 'abs', 'sin', 'cos', 'tan', 'log', 'exp', 'len', 'mean', 'sum', 'std', 'var', 'min', 'max', 'minimum', 'maximum', 'diff', 'integrate'}
    
    # ตรวจสอบเฉพาะตัวแปรที่ไม่ได้อยู่ในคอลัมน์และไม่ใช่ฟังก์ชันที่อนุญาต
    # แต่ต้องไม่ตรวจสอบตัวแปรที่มาจาก backtick เพราะมันถูกแทนที่แล้ว
    missing_cols = []
    for var in other_vars:  # ตรวจสอบเฉพาะตัวแปรที่ไม่ใช่จาก backtick
        if var not in df.columns and var not in allowed_functions:
            # ตรวจสอบเพิ่มเติม: ถ้าตัวแปรนี้เป็นชื่อที่แปลงจากคอลัมน์ที่มีช่องว่าง
            # ให้ข้ามการตรวจสอบ
            is_converted_column = any(var == col.replace(' ', '_') for col in df.columns if ' ' in col)
            if not is_converted_column:
                missing_cols.append(var)
    
    if missing_cols:
        raise KeyError(f"ไม่พบคอลัมน์: {', '.join(missing_cols)}")
    
    # เตรียมตัวแปรสำหรับการประเมิน
    # สร้าง dictionary ของคอลัมน์ที่ใช้ในนิพจน์
    local_vars = {}
    
    # หาคอลัมน์ที่ใช้ในนิพจน์ (ทั้งจาก backtick และตัวแปรอื่นๆ)
    used_columns = set()
    
    # เพิ่มคอลัมน์จาก backtick
    for col_name in backtick_vars:
        used_columns.add(col_name)
    
    # เพิ่มคอลัมน์จากตัวแปรอื่นๆ ที่มีอยู่ใน DataFrame
    for var in other_vars:
        if var in df.columns:
            used_columns.add(var)
    
    # สร้างตัวแปรสำหรับการประเมิน
    for col in used_columns:
        # แปลงคอลัมน์เป็น numeric และจัดการ NaN/inf
        series = pd.to_numeric(df[col], errors='coerce')
        # แทนที่ inf/-inf ด้วย NaN
        series = series.replace([np.inf, -np.inf], np.nan)
        
        # ใช้ชื่อตัวแปรที่ถูกต้องสำหรับการประเมิน
        var_name = col.replace(' ', '_')
        local_vars[var_name] = series
    
    # Helper function for aggregation operations that return scalars
    def _agg_to_scalar(series, fn):
        """Convert aggregation function result to scalar"""
        a = np.asarray(series, dtype=float)
        return {
            "mean": np.nanmean(a),
            "sum":  np.nansum(a),
            "std":  np.nanstd(a, ddof=0),
            "var":  np.nanvar(a, ddof=0),
            "min":  np.nanmin(a),
            "max":  np.nanmax(a),
        }[fn]

    # เพิ่มฟังก์ชัน numpy ที่ปลอดภัย
    safe_functions = {
        'sqrt': np.sqrt,
        'abs': np.abs,
        'sin': np.sin,
        'cos': np.cos,
        'tan': np.tan,
        'log': np.log,
        'exp': np.exp,
        'minimum': np.minimum,
        'maximum': np.maximum,
        # Helper functions
        'len': lambda s: float(len(s)),
        # Aggregation functions that return scalars (will be broadcasted)
        'mean': lambda s: float(_agg_to_scalar(s, "mean")),
        'sum':  lambda s: float(_agg_to_scalar(s, "sum")),
        'std':  lambda s: float(_agg_to_scalar(s, "std")),
        'var':  lambda s: float(_agg_to_scalar(s, "var")),
        'min':  lambda s: float(_agg_to_scalar(s, "min")),
        'max':  lambda s: float(_agg_to_scalar(s, "max")),
        'diff': lambda series, dt=None, x=None, method='central': _diff_series(series, dt=dt, x=x, method=method),
        'integrate': lambda series, dt=None, x=None, initial=0.0, method='trapezoid': _integrate_series(series, dt=dt, x=x, initial=initial, method=method),
    }
    
    # รวมตัวแปรและฟังก์ชันเข้าด้วยกัน
    eval_vars = {**local_vars, **safe_functions}
    
    try:
        # ลองใช้ numexpr ก่อน (เร็วกว่า) ถ้าไม่มีให้ใช้ python
        if engine == "auto":
            try:
                import numexpr
                engine = "numexpr"
            except ImportError:
                engine = "python"
        
        if engine == "numexpr":
            # numexpr รองรับเฉพาะการดำเนินการพื้นฐาน
            # ถ้านิพจน์ซับซ้อนเกินไป ให้ใช้ python แทน
            if any(func in expression_clean for func in ['sqrt', 'abs', 'sin', 'cos', 'tan', 'log', 'exp']):
                engine = "python"
        
        if engine == "numexpr":
            # ใช้ pandas.eval กับ numexpr engine
            result = df.eval(expression_clean, engine='numexpr')
        else:
            # ใช้ eval() กับตัวแปรที่เตรียมไว้
            result = eval(expression_clean, {"__builtins__": {}}, eval_vars)
        
        # แปลงผลลัพธ์เป็น Series ถ้ายังไม่ใช่
        if not isinstance(result, pd.Series):
            if isinstance(result, (int, float)) or np.isscalar(result):
                # ถ้าเป็นค่าคงที่ ให้สร้าง Series ที่มีค่าเดียวกันทุกแถว
                result = np.full(len(df), result, dtype=float)
                result = pd.Series(result, index=df.index)
            else:
                result = pd.Series(result, index=df.index)
        
        # จัดการ NaN และ inf ในผลลัพธ์
        result = pd.to_numeric(result, errors='coerce')
        result = result.replace([np.inf, -np.inf], np.nan)
        
        # ตรวจสอบการหารศูนย์ (NaN ที่เกิดจากการหารศูนย์)
        if result.isna().any():
            nan_count = result.isna().sum()
            total_count = len(result)
            if nan_count > 0:
                warnings.warn(f"พบค่า NaN {nan_count}/{total_count} แถว (อาจเกิดจากการหารศูนย์หรือค่าที่ไม่ถูกต้อง)")
        
        return result
        
    except Exception as e:
        # แปลงข้อผิดพลาดให้เป็นข้อความที่เข้าใจง่าย
        error_msg = str(e)
        if "unsupported operand type" in error_msg:
            raise ValueError("นิพจน์มีประเภทข้อมูลที่ไม่เข้ากัน")
        elif "name" in error_msg and "is not defined" in error_msg:
            raise ValueError("พบตัวแปรหรือฟังก์ชันที่ไม่รู้จักในนิพจน์")
        elif "syntax" in error_msg.lower():
            raise ValueError("นิพจน์มีไวยากรณ์ไม่ถูกต้อง")
        else:
            raise ValueError(f"ไม่สามารถประเมินนิพจน์ได้: {error_msg}")


def _coerce_numeric_array(values, *, name: str) -> tuple[np.ndarray, np.ndarray]:
    series = pd.Series(values)
    # Try numeric conversion first
    numeric = pd.to_numeric(series, errors='coerce')
    numeric_mask = numeric.notna()
    if numeric_mask.sum() >= max(2, len(series) // 2):
        arr = numeric.to_numpy(dtype=float)
        mask = np.isfinite(arr) & numeric_mask.to_numpy()
        return arr, mask
    # Try datetime conversion
    dt = pd.to_datetime(series, errors='coerce')
    dt_mask = dt.notna()
    if dt_mask.sum() >= 2:
        try:
            t0 = dt[dt_mask].iloc[0]
            seconds = (dt - t0).dt.total_seconds()
            arr = seconds.to_numpy(dtype=float)
            mask = ~np.isnan(arr)
            return arr, mask
        except Exception:
            pass
    # Fallback to numeric even if few valid points
    arr = numeric.to_numpy(dtype=float)
    mask = np.isfinite(arr) & numeric_mask.to_numpy()
    return arr, mask

# === Nonlinear curve fitting ===
# หมายเหตุ: เตรียมรองรับ QThread ภายหลัง (TODO)


def model_gaussian(x: np.ndarray, A: float, x0: float, sigma: float, C: float) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    sigma_pos = np.clip(np.abs(sigma), 1e-12, None)
    return A * np.exp(-((x_arr - x0) ** 2) / (2.0 * sigma_pos ** 2)) + C


def model_lorentzian(x: np.ndarray, A: float, x0: float, gamma: float, C: float) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    gamma_pos = np.clip(np.abs(gamma), 1e-12, None)
    return A * (gamma_pos ** 2 / ((x_arr - x0) ** 2 + gamma_pos ** 2)) + C


def model_voigt(x: np.ndarray, A: float, x0: float, sigma: float, gamma: float, C: float) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    sigma_pos = np.clip(np.abs(sigma), 1e-12, None)
    gamma_pos = np.clip(np.abs(gamma), 1e-12, None)
    gauss = np.exp(-((x_arr - x0) ** 2) / (2.0 * sigma_pos ** 2))
    lorentz = gamma_pos ** 2 / ((x_arr - x0) ** 2 + gamma_pos ** 2)
    f_g = 2.0 * sigma_pos * np.sqrt(2.0 * np.log(2.0))
    f_l = 2.0 * gamma_pos
    ratio = f_l / (f_g + 1e-12)
    eta = 1.36603 * ratio - 0.47719 * ratio ** 2 + 0.11116 * ratio ** 3
    eta = np.clip(eta, 0.0, 1.0)
    return A * (eta * lorentz + (1.0 - eta) * gauss) + C


def model_logistic(x: np.ndarray, L: float, k: float, x0: float, C: float) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    z = np.clip(k * (x_arr - x0), -700.0, 700.0)
    return L / (1.0 + np.exp(-z)) + C


def model_exp1(x: np.ndarray, A: float, tau: float, C: float) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    tau_pos = np.clip(np.abs(tau), 1e-12, None)
    return A * np.exp(-x_arr / tau_pos) + C


def model_exp2(x: np.ndarray, A1: float, tau1: float, A2: float, tau2: float, C: float) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    tau1_pos = np.clip(np.abs(tau1), 1e-12, None)
    tau2_pos = np.clip(np.abs(tau2), 1e-12, None)
    return A1 * np.exp(-x_arr / tau1_pos) + A2 * np.exp(-x_arr / tau2_pos) + C


def model_power(x: np.ndarray, A: float, n: float, C: float) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    with np.errstate(invalid='ignore', divide='ignore', over='ignore'):
        result = A * np.power(x_arr, n)
    return result + C


def model_sine(x: np.ndarray, A: float, omega: float, phi: float, C: float) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    return A * np.sin(omega * x_arr + phi) + C


_ALLOWED_FUNCS = {
    'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2', 'sinh', 'cosh', 'tanh',
    'log', 'log10', 'exp', 'sqrt', 'abs', 'where', 'minimum', 'maximum', 'clip',
    'sign', 'floor', 'ceil', 'round', 'power', 'arcsin', 'arccos', 'arctan',
    'arctan2', 'log1p', 'expm1'
}


@dataclass
class FitResult:
    params: Dict[str, float]
    stderr: Dict[str, float]
    cov: np.ndarray
    success: bool
    message: str
    r2: float
    rmse: float
    chi2_red: float
    aic: float
    bic: float
    yfit: np.ndarray
    ci95_lower: Optional[np.ndarray]
    ci95_upper: Optional[np.ndarray]


def build_custom_callable(expr: str, param_names: List[str]) -> Callable[..., np.ndarray]:
    if not expr:
        raise ValueError('นิพจน์ว่างเปล่า')
    raw = expr.strip()
    if raw.lower().startswith('y='):
        raw = raw.split('=', 1)[1].strip()
    names = [p.strip() for p in (param_names or []) if p.strip()]
    if not names:
        raise ValueError('ต้องระบุชื่อพารามิเตอร์อย่างน้อย 1 ตัว')
    if len(set(names)) != len(names):
        raise ValueError('ชื่อพารามิเตอร์ซ้ำกัน')
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw))
    allowed = set(names) | _ALLOWED_FUNCS | {'x', 'pi', 'e'}
    illegal = sorted(token for token in tokens if token not in allowed)
    if illegal:
        raise ValueError(f"พบตัวแปรที่ไม่รองรับ: {', '.join(illegal)}")

    def _call(x: np.ndarray, *params: float) -> np.ndarray:
        if len(params) != len(names):
            raise ValueError('จำนวนพารามิเตอร์ไม่ตรงกับรายชื่อที่กำหนด')
        x_arr = np.asarray(x, dtype=float)
        local = {'x': x_arr, 'pi': np.pi, 'e': np.e}
        for key, value in zip(names, params):
            local[key] = value
        try:
            result = ne.evaluate(raw, local_dict=local, global_dict={}, truediv=True)
        except Exception as exc:  # pragma: no cover - ควรแจ้งผู้ใช้
            raise ValueError(f'คำนวณนิพจน์ไม่สำเร็จ: {exc}') from exc
        return np.asarray(result, dtype=float)

    return _call


def _calc_metrics(y_obs: np.ndarray, y_fit: np.ndarray, param_count: int, sigma: Optional[np.ndarray] = None) -> Tuple[float, float, float, float, float]:
    y_obs = np.asarray(y_obs, dtype=float)
    y_fit = np.asarray(y_fit, dtype=float)
    resid = y_obs - y_fit
    n = max(1, y_obs.size)
    k = max(1, int(param_count))
    rss = float(np.sum(resid ** 2))
    mean_y = float(np.mean(y_obs))
    tss = float(np.sum((y_obs - mean_y) ** 2))
    r2 = 1.0 - rss / tss if tss > 0 else np.nan
    rmse = np.sqrt(rss / n)
    if sigma is not None:
        sigma_arr = np.asarray(sigma, dtype=float)
        sigma_arr = np.where(sigma_arr > 0, sigma_arr, np.nan)
        chi_sq = float(np.nansum(((resid) / sigma_arr) ** 2))
    else:
        chi_sq = rss
    dof = max(1, n - k)
    chi2_red = chi_sq / dof
    rss_safe = rss if rss > 0 else np.finfo(float).tiny
    aic = n * np.log(rss_safe / n) + 2 * k
    bic = n * np.log(rss_safe / n) + k * np.log(n)
    return r2, rmse, chi2_red, aic, bic


def _predict_ci(x: np.ndarray, func: Callable[..., np.ndarray], popt: Sequence[float], pcov: np.ndarray, alpha: float = 0.05) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    if pcov is None:
        return None, None
    pcov = np.asarray(pcov, dtype=float)
    if pcov.ndim != 2 or pcov.shape[0] != pcov.shape[1]:
        return None, None
    if not np.all(np.isfinite(pcov)):
        return None, None
    if np.any(np.diag(pcov) < 0):
        return None, None
    x_arr = np.asarray(x, dtype=float)
    popt_arr = np.asarray(popt, dtype=float)
    try:
        y_pred = func(x_arr, *popt_arr)
    except Exception:
        return None, None
    eps = np.maximum(1e-8, 1e-8 * np.abs(popt_arr))
    jac_rows: List[np.ndarray] = []
    for idx, h in enumerate(eps):
        step = np.zeros_like(popt_arr)
        step[idx] = h
        try:
            y_plus = func(x_arr, *(popt_arr + step))
            y_minus = func(x_arr, *(popt_arr - step))
        except Exception:
            return None, None
        grad = (y_plus - y_minus) / (2.0 * h)
        jac_rows.append(np.asarray(grad, dtype=float))
    jac = np.column_stack(jac_rows)
    try:
        pred_var = np.einsum('ij,jk,ik->i', jac, pcov, jac, optimize=True)
    except Exception:
        return None, None
    pred_var = np.maximum(pred_var, 0.0)
    se = np.sqrt(pred_var)
    dof = max(1, x_arr.size - popt_arr.size)
    try:
        crit = float(t.ppf(1.0 - alpha / 2.0, dof))
    except Exception:
        crit = 1.96
    if not np.isfinite(crit) or crit <= 0:
        crit = 1.96
    delta = crit * se
    return y_pred - delta, y_pred + delta


_MODEL_REGISTRY: Dict[str, Tuple[Callable[..., np.ndarray], List[str]]] = {
    'gaussian': (model_gaussian, ['A', 'x0', 'sigma', 'C']),
    'lorentzian': (model_lorentzian, ['A', 'x0', 'gamma', 'C']),
    'voigt': (model_voigt, ['A', 'x0', 'sigma', 'gamma', 'C']),
    'logistic': (model_logistic, ['L', 'k', 'x0', 'C']),
    'exp1': (model_exp1, ['A', 'tau', 'C']),
    'exp2': (model_exp2, ['A1', 'tau1', 'A2', 'tau2', 'C']),
    'power': (model_power, ['A', 'n', 'C']),
    'sine': (model_sine, ['A', 'omega', 'phi', 'C'])
}


def nonlinear_fit(
    x: np.ndarray,
    y: np.ndarray,
    model_name: str,
    init_params: Optional[Dict[str, float]],
    bounds: Optional[Dict[str, Tuple[float, float]]] = None,
    sigma: Optional[np.ndarray] = None,
    weighting: str = 'none',
    custom_expr: Optional[str] = None,
    custom_params: Optional[List[str]] = None,
    calc_ci: bool = True
) -> FitResult:
    model_key = (model_name or '').strip().lower()
    registry = dict(_MODEL_REGISTRY)
    if model_key == 'custom':
        if not custom_expr or not custom_params:
            raise ValueError('ต้องระบุสมการและพารามิเตอร์สำหรับโมเดล Custom')
        func = build_custom_callable(custom_expr, custom_params)
        param_names = [p.strip() for p in custom_params if p.strip()]
    else:
        if model_key not in registry:
            raise ValueError(f'ไม่พบโมเดล {model_name}')
        func, param_names = registry[model_key]
    init_params = init_params or {}
    x_raw = np.asarray(x).ravel()
    y_raw = np.asarray(y).ravel()
    if x_raw.size != y_raw.size:
        raise ValueError('ขนาดของ X และ Y ไม่ตรงกัน')

    x_arr, mask_x = _coerce_numeric_array(x_raw, name='X')
    y_arr, mask_y = _coerce_numeric_array(y_raw, name='Y')
    if x_arr.size != x_raw.size or y_arr.size != y_raw.size:
        # Ensure arrays align even if pandas converted internally
        x_arr = np.asarray(x_arr).reshape(-1)
        y_arr = np.asarray(y_arr).reshape(-1)
    mask = mask_x & mask_y
    sigma_arr = None
    if sigma is not None:
        sigma_raw = np.asarray(sigma).ravel()
        if sigma_raw.size != x_raw.size:
            raise ValueError('จำนวนค่าความคลาดเคลื่อนไม่ตรงกับข้อมูล')
        sigma_arr, mask_sigma = _coerce_numeric_array(sigma_raw, name='sigma')
        mask &= mask_sigma
    mask &= np.isfinite(x_arr) & np.isfinite(y_arr)
    if sigma_arr is not None:
        if weighting in ('sigma', '1/sigma^2'):
            mask &= sigma_arr > 0
        mask &= np.isfinite(sigma_arr)

    x_valid = x_arr[mask]
    y_valid = y_arr[mask]
    sigma_valid = sigma_arr[mask] if sigma_arr is not None else None
    if x_valid.size < len(param_names) + 1:
        raise ValueError('ข้อมูลไม่พอสำหรับการฟิตพารามิเตอร์')
    default_guess = {
        'A': float(np.nanmax(y_valid) - np.nanmin(y_valid)) if y_valid.size else 1.0,
        'A1': 1.0,
        'A2': 0.5,
        'x0': float(np.nanmean(x_valid)) if x_valid.size else 0.0,
        'sigma': max(float(np.nanstd(x_valid)), 1.0),
        'gamma': 1.0,
        'tau': 1.0,
        'tau1': 1.0,
        'tau2': 5.0,
        'n': 1.0,
        'omega': 1.0,
        'phi': 0.0,
        'C': float(np.nanmin(y_valid)) if y_valid.size else 0.0,
        'L': float(np.nanmax(y_valid)) if y_valid.size else 1.0,
        'k': 1.0
    }
    p0: List[float] = []
    lower_bounds: List[float] = []
    upper_bounds: List[float] = []
    for name in param_names:
        guess = init_params.get(name, default_guess.get(name, 1.0))
        if not np.isfinite(guess):
            guess = default_guess.get(name, 1.0)
        lower, upper = (-np.inf, np.inf)
        if bounds and name in bounds:
            lower, upper = bounds[name]
        if name.lower().startswith(('sigma', 'gamma', 'tau')) or name.lower() in {'tau1', 'tau2'}:
            lower = max(lower, 1e-12)
            guess = max(guess, 1e-6)
        if np.isfinite(lower) and guess < lower:
            guess = lower + abs(lower) * 0.1 if lower != 0 else 1e-6
        if np.isfinite(upper) and guess > upper:
            guess = upper - abs(upper) * 0.1 if upper != 0 else upper - 1e-6
        p0.append(float(guess))
        lower_bounds.append(float(lower))
        upper_bounds.append(float(upper))
    sigma_curve = None
    sigma_for_metrics = None
    absolute_sigma = False
    if sigma_valid is not None and sigma_valid.size:
        sigma_for_metrics = sigma_valid
        if weighting == 'sigma':
            sigma_curve = sigma_valid
            absolute_sigma = True
        elif weighting == '1/sigma^2':
            sigma_curve = np.sqrt(1.0 / np.clip(sigma_valid, 1e-12, None))
        else:
            sigma_curve = None
    bounds_tuple = (np.array(lower_bounds, dtype=float), np.array(upper_bounds, dtype=float))
    y_init = func(x_valid, *p0)
    try:
        popt, pcov = curve_fit(
            func,
            x_valid,
            y_valid,
            p0=np.asarray(p0, dtype=float),
            bounds=bounds_tuple,
            sigma=sigma_curve,
            absolute_sigma=absolute_sigma,
            maxfev=20000
        )
        success = True
        message = 'OK'
    except Exception as exc:
        pcov = np.full((len(param_names), len(param_names)), np.nan, dtype=float)
        params = {name: float(val) for name, val in zip(param_names, p0)}
        stderr = {name: np.nan for name in param_names}
        return FitResult(
            params=params,
            stderr=stderr,
            cov=pcov,
            success=False,
            message=str(exc),
            r2=np.nan,
            rmse=np.nan,
            chi2_red=np.nan,
            aic=np.nan,
            bic=np.nan,
            yfit=y_init,
            ci95_lower=None,
            ci95_upper=None
        )
    params = {name: float(val) for name, val in zip(param_names, popt)}
    if pcov is None:
        pcov = np.full((len(param_names), len(param_names)), np.nan, dtype=float)
    stderr = {}
    diag = np.diag(pcov) if pcov.size else np.array([])
    for idx, name in enumerate(param_names):
        if idx < diag.size and diag[idx] >= 0:
            stderr[name] = float(np.sqrt(diag[idx]))
        else:
            stderr[name] = np.nan
    y_fit = func(x_valid, *popt)
    metrics = _calc_metrics(y_valid, y_fit, len(param_names), sigma_for_metrics)
    ci_lower = ci_upper = None
    if calc_ci:
        ci_lower, ci_upper = _predict_ci(x_valid, func, popt, pcov)
    return FitResult(
        params=params,
        stderr=stderr,
        cov=np.asarray(pcov, dtype=float),
        success=success,
        message=message,
        r2=metrics[0],
        rmse=metrics[1],
        chi2_red=metrics[2],
        aic=metrics[3],
        bic=metrics[4],
        yfit=y_fit,
        ci95_lower=ci_lower,
        ci95_upper=ci_upper
    )
