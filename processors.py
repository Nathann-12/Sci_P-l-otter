# processors.py
import numpy as np
import pandas as pd

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
            dt = (xdt.astype("int64").diff().dropna().median())  # นาโนวินาที
            if pd.notna(dt) and dt > 0:
                return 1.0 / (dt / 1e9)  # Hz
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
    ax.grid(True, which='major', alpha=0.3)
    ax.grid(True, which='minor', alpha=0.1)
    
    # Set datetime formatting if needed
    if x_is_datetime:
        try:
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.AutoDateLocator()))
        except Exception:
            pass  # Fallback to default if datetime formatting fails
    
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