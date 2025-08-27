import numpy as np
import pandas as pd
from typing import Tuple, Optional, Union
import warnings

def _validate_and_clean_data(time_col, sig_col):
    """
    Validate and clean time and signal columns
    
    Returns:
        tuple: (time_clean, sig_clean, fs, meta)
    """
    # Convert to numpy arrays
    time = np.asarray(time_col)
    sig = np.asarray(sig_col)
    
    # Remove NaN values
    mask = np.isfinite(time) & np.isfinite(sig)
    if mask.sum() < 10:
        raise ValueError("ข้อมูลที่มีค่าถูกต้องน้อยเกินไป (ต้องมีอย่างน้อย 10 จุด)")
    
    time_clean = time[mask]
    sig_clean = sig[mask]
    
    # Additional validation
    if len(time_clean) == 0:
        raise ValueError("ไม่มีข้อมูลที่ใช้ได้หลังจากลบ NaN")
    
    if np.all(sig_clean == sig_clean[0]):
        raise ValueError("ข้อมูลสัญญาณมีค่าเดียวกันทั้งหมด ไม่สามารถวิเคราะห์ได้")
    
    # Check for extreme values that might cause issues
    if np.any(np.abs(sig_clean) > 1e10):
        raise ValueError("ข้อมูลสัญญาณมีค่าสูงเกินไป (มากกว่า 1e10)")
    
    # Calculate sampling frequency
    if len(time_clean) > 1:
        if pd.api.types.is_datetime64_any_dtype(time_clean):
            # For datetime, calculate fs from time differences
            time_diffs = np.diff(time_clean)
            time_diffs_sec = time_diffs.astype('timedelta64[s]').astype(float)
            
            # Validate time differences
            if np.any(time_diffs_sec <= 0):
                raise ValueError("ข้อมูลเวลาต้องเรียงลำดับจากน้อยไปมาก")
            
            median_diff = np.median(time_diffs_sec)
            if not np.isfinite(median_diff) or median_diff <= 0:
                raise ValueError("ไม่สามารถคำนวณ sampling frequency จากข้อมูลเวลาได้")
            
            fs = 1.0 / median_diff
        else:
            # For numeric time, assume uniform sampling
            time_diffs = np.diff(time_clean)
            
            # Validate time differences
            if np.any(time_diffs <= 0):
                raise ValueError("ข้อมูลเวลาต้องเรียงลำดับจากน้อยไปมาก")
            
            median_diff = np.median(time_diffs)
            if not np.isfinite(median_diff) or median_diff <= 0:
                raise ValueError("ไม่สามารถคำนวณ sampling frequency จากข้อมูลเวลาได้")
            
            fs = 1.0 / median_diff
    else:
        fs = 1.0
    
    # Validate sampling frequency
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError(f"Sampling frequency ที่คำนวณได้ไม่ถูกต้อง: {fs}")
    
    if fs > 1e6:  # More than 1 MHz
        raise ValueError(f"Sampling frequency สูงเกินไป: {fs:.2e} Hz")
    
    meta = {
        "fs": fs,
        "n_points": len(time_clean),
        "time_range": (time_clean.min(), time_clean.max()),
        "signal_range": (sig_clean.min(), sig_clean.max()),
        "is_datetime": pd.api.types.is_datetime64_any_dtype(time_clean)
    }
    
    return time_clean, sig_clean, fs, meta

def compute_spectrogram(time_col, sig_col, fs=None, window="hann", nperseg=256, 
                       noverlap=128, scaling="density", to_db=True, detrend=True, 
                       contrast_percentiles=(5, 95)):
    """
    Compute spectrogram using Short-Time Fourier Transform (STFT)
    
    Args:
        time_col: Time column (datetime or float)
        sig_col: Signal column
        fs: Sampling frequency (if None, will be calculated)
        window: Window function ("hann", "hamming", "blackman", etc.)
        nperseg: Number of points per segment
        noverlap: Number of points to overlap between segments
        scaling: Scaling type ("density" or "spectrum")
        to_db: Convert to decibels
    
    Returns:
        tuple: (T, F, S, meta)
            T: Time array
            F: Frequency array  
            S: Spectrogram array (2D)
            meta: Metadata dictionary
    """
    try:
        from scipy import signal
    except ImportError:
        raise ImportError("scipy ไม่ได้ติดตั้ง กรุณาติดตั้งด้วย: pip install scipy>=1.11.0")
    
    # Validate and clean data
    time_clean, sig_clean, fs_calc, meta = _validate_and_clean_data(time_col, sig_col)
    
    # Use provided fs or calculated fs
    if fs is None:
        fs = fs_calc
    
    # Apply detrending if requested
    if detrend:
        sig_clean = signal.detrend(sig_clean)
    
    # Ensure nperseg is not larger than signal length
    if nperseg > len(sig_clean):
        nperseg = len(sig_clean) // 2
        if nperseg < 32:
            nperseg = 32
        warnings.warn(f"nperseg ถูกปรับเป็น {nperseg} เนื่องจากข้อมูลสั้นเกินไป")
    
    # Ensure noverlap is not larger than nperseg
    if noverlap >= nperseg:
        noverlap = nperseg // 2
        warnings.warn(f"noverlap ถูกปรับเป็น {noverlap}")
    
    # Compute spectrogram
    f, t, S = signal.spectrogram(sig_clean, fs=fs, window=window, 
                                 nperseg=nperseg, noverlap=noverlap, 
                                 scaling=scaling, mode='complex')
    
    # Convert to power spectrum
    S = np.abs(S) ** 2
    
    # Convert to dB if requested
    if to_db:
        # Avoid log(0) by adding small value
        S = 10 * np.log10(S + 1e-10)
        power_unit = "dB"
    else:
        power_unit = "Power"
    
    # Calculate contrast limits from percentiles
    if contrast_percentiles and len(contrast_percentiles) == 2:
        p1, p2 = contrast_percentiles
        vmin = np.percentile(S, p1)
        vmax = np.percentile(S, p2)
    else:
        vmin = S.min()
        vmax = S.max()
    
    # Ensure vmin < vmax
    if vmin >= vmax:
        vmin = S.min()
        vmax = S.max()
    
    # Convert time indices back to actual time values
    if meta["is_datetime"]:
        time_start = meta["time_range"][0]
        time_end = meta["time_range"][1]
        T = pd.date_range(start=time_start, end=time_end, periods=len(t))
    else:
        T = t
    
    # Validate that T, f, and S are finite
    if not np.all(np.isfinite(T)) or not np.all(np.isfinite(f)) or not np.all(np.isfinite(S)):
        raise ValueError("ผลลัพธ์จากการคำนวณมีค่า NaN หรือ Inf")
    
    # Update meta
    meta.update({
        "window": window,
        "nperseg": nperseg,
        "noverlap": noverlap,
        "scaling": scaling,
        "to_db": to_db,
        "power_unit": power_unit,
        "freq_range": (f.min(), f.max()),
        "method": "STFT",
        "detrend": detrend,
        "contrast_percentiles": contrast_percentiles,
        "vmin": vmin,
        "vmax": vmax
    })
    
    return T, f, S, meta

def compute_cwt(time_col, sig_col, wavelet="morl", scales=None, to_db=False):
    """
    Compute Continuous Wavelet Transform (CWT)
    
    Args:
        time_col: Time column (datetime or float)
        sig_col: Signal column
        wavelet: Wavelet type ("morl", "gaus", "cmor", etc.)
        scales: Scale array (if None, will be auto-generated)
        to_db: Convert to decibels
    
    Returns:
        tuple: (T, Freqs, Power, meta)
            T: Time array
            Freqs: Frequency array
            Power: Power array (2D)
            meta: Metadata dictionary
    """
    try:
        import pywt
    except ImportError:
        raise ImportError("PyWavelets ไม่ได้ติดตั้ง กรุณาติดตั้งด้วย: pip install PyWavelets>=1.5.0")
    
    # Validate and clean data
    time_clean, sig_clean, fs, meta = _validate_and_clean_data(time_col, sig_col)
    
    # Generate scales if not provided
    if scales is None:
        # Auto-generate scales based on signal length and frequency
        min_scale = 2
        max_scale = len(sig_clean) // 4
        num_scales = 64
        scales = np.logspace(np.log10(min_scale), np.log10(max_scale), num_scales)
    
    # Compute CWT
    try:
        coeffs, freqs = pywt.cwt(sig_clean, scales, wavelet, sampling_period=1/fs)
    except Exception as e:
        raise ValueError(f"ไม่สามารถคำนวณ CWT ได้: {e}")
    
    # Convert to power
    Power = np.abs(coeffs) ** 2
    
    # Convert to dB if requested
    if to_db:
        Power = 10 * np.log10(Power + 1e-10)
        power_unit = "dB"
    else:
        power_unit = "Power"
    
    # Convert time indices back to actual time values
    if meta["is_datetime"]:
        time_start = meta["time_range"][0]
        time_end = meta["time_range"][1]
        T = pd.date_range(start=time_start, end=time_end, periods=len(sig_clean))
    else:
        T = np.linspace(meta["time_range"][0], meta["time_range"][1], len(sig_clean))
    
    # Validate that T, freqs, and Power are finite
    if not np.all(np.isfinite(T)) or not np.all(np.isfinite(freqs)) or not np.all(np.isfinite(Power)):
        raise ValueError("ผลลัพธ์จากการคำนวณ CWT มีค่า NaN หรือ Inf")
    
    # Update meta
    meta.update({
        "wavelet": wavelet,
        "scales": scales,
        "to_db": to_db,
        "power_unit": power_unit,
        "freq_range": (freqs.min(), freqs.max()),
        "method": "CWT"
    })
    
    return T, freqs, Power, meta

def export_spectrogram_data(T, F, S, meta, filename=None):
    """
    Export spectrogram data to CSV format
    
    Args:
        T: Time array
        F: Frequency array
        S: Spectrogram array
        meta: Metadata dictionary
        filename: Output filename
    
    Returns:
        str: Filename of saved CSV
    """
    if filename is None:
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        filename = f"spectrogram_{meta['method']}_{timestamp}.csv"
    
    # Create meshgrid for time and frequency
    T_mesh, F_mesh = np.meshgrid(T, F, indexing='ij')
    
    # Flatten arrays
    time_flat = T_mesh.flatten()
    freq_flat = F_mesh.flatten()
    power_flat = S.flatten()
    
    # Create DataFrame
    df = pd.DataFrame({
        'Time': time_flat,
        'Frequency': freq_flat,
        'Power': power_flat
    })
    
    # Save to CSV
    df.to_csv(filename, index=False)
    
    return filename
