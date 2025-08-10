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

# processors.py (ต่อท้ายไฟล์)
import pandas as pd
import numpy as np

def apply_column_types(df: pd.DataFrame, mapping: dict):
    """
    แปลงชนิดข้อมูลคอลัมน์ตาม mapping เช่น {"id":"String","score":"Integer","time":"Datetime","x":"Float","y":"Auto"}
    - String: แปลงเป็น string (รักษาศูนย์นำหน้า เช่น รหัสนิสิต)
    - Integer: แปลงเป็นตัวเลขจำนวนเต็ม (ค่าที่แปลงไม่ได้จะเป็น NaN)
    - Float: แปลงเป็นทศนิยม
    - Datetime: แปลงเป็น datetime (พยายามเดา format)
    - Auto: ไม่แตะ
    """
    for col, typ in (mapping or {}).items():
        if col not in df.columns:
            continue
        s = df[col]

        if typ == "String":
            # แปลงทุกค่าเป็น string โดยไม่ทำวิทยาศาสตร์
            df[col] = s.astype("string").fillna(pd.NA)

        elif typ == "Integer":
            # แปลงเป็นจำนวนเต็มแบบ nullable (Int64) เพื่อรองรับ NaN
            df[col] = pd.to_numeric(s, errors="coerce").astype("Int64")

        elif typ == "Float":
            df[col] = pd.to_numeric(s, errors="coerce").astype(float)

        elif typ == "Datetime":
            # พยายาม localize/convert ทีหลังในฟีเจอร์เวลา
            df[col] = pd.to_datetime(s, errors="coerce", infer_datetime_format=True)

        else:
            # Auto: ไม่ทำอะไร
            pass

    return df

def _infer_sampling_rate(x):
    """เดาอัตราสุ่มจากแกน X: ถ้าเป็นเวลา → วินาที; ถ้าเป็นตัวเลข → ใช้ median(diff)"""
    x = pd.Series(x)
    # เวลา
    try:
        xdt = pd.to_datetime(x, errors="coerce")
        if xdt.notna().sum() > 1:
            dt = (xdt.astype("int64").diff().dropna().median())  # นาโนวินาที
            if pd.notna(dt) and dt > 0:
                return 1.0 / (dt / 1e9)  # Hz
    except Exception:
        pass
    # ตัวเลข
    xnum = pd.to_numeric(x, errors="coerce")
    dx = xnum.diff().dropna().median()
    if pd.notna(dx) and dx > 0:
        return 1.0 / dx
    raise ValueError("เดาอัตราสุ่ม (sampling rate) ไม่ได้")

def compute_fft(df: pd.DataFrame, x_col: str, y_col: str, detrend=True, window="hanning"):
    """
    คำนวณ FFT แบบหนึ่งแกน (real signal):
    คืน df_fft: columns = ['freq_Hz', 'amplitude', 'power']
    """
    y = pd.to_numeric(df[y_col], errors="coerce").dropna().values
    if y.size < 4:
        raise ValueError("ข้อมูลน้อยเกินไปสำหรับ FFT")

    fs = _infer_sampling_rate(df[x_col].values)  # Hz

    # เอาแนวโน้มออกเล็กน้อย (optional)
    if detrend:
        y = y - np.mean(y)

    # windowing
    if window in ("hanning", "hann"):
        w = np.hanning(y.size)
    elif window in ("hamming",):
        w = np.hamming(y.size)
    else:
        w = np.ones_like(y)
    yw = y * w

    # FFT ข้างเดียว (rfft)
    Y = np.fft.rfft(yw)
    freq = np.fft.rfftfreq(yw.size, d=1.0/fs)
    amp = np.abs(Y) / (yw.size/2.0)
    power = (np.abs(Y)**2) / (yw.size)

    df_fft = pd.DataFrame({
        "freq_Hz": freq,
        "amplitude": amp,
        "power": power
    })
    return df_fft, fs
