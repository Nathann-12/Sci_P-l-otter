# processors.py
import numpy as np
import pandas as pd
import re
import warnings

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
            
        except Exception as e:
            print(f"Debug: DateTime formatting failed: {e}")
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
    
    # Ensure tight layout and redraw with better error handling
    try:
        ax.figure.tight_layout()
    except Exception:
        pass  # Continue without tight layout
    
    try:
        # Try multiple redraw methods
        if hasattr(ax.figure, 'canvas') and hasattr(ax.figure.canvas, 'draw'):
            ax.figure.canvas.draw()
        elif hasattr(ax, 'figure') and hasattr(ax.figure, 'draw'):
            ax.figure.draw()
    except Exception:
        pass  # Continue without redraw

# ---- Derived Column Expression Evaluation ----
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
    allowed_functions = {'sqrt', 'abs', 'sin', 'cos', 'tan', 'log', 'exp', 'len', 'mean', 'sum', 'std', 'var', 'min', 'max', 'minimum', 'maximum'}
    
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