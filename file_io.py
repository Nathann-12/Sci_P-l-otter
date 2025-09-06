# file_io.py
from __future__ import annotations

from pathlib import Path
from typing import Tuple, Dict, Any, List
import numpy as np
import pandas as pd
import cdflib  # pip install cdflib

# นำเข้าตัวอ่าน MMS CDF ที่เราเขียนไว้
from read_mms_cdf import read_mms_fgm_cdf  # ไฟล์นี้ต้องอยู่โฟลเดอร์โปรเจกต์เดียวกัน

# ===========================
# Utils พื้นฐาน
# ===========================
def _b2s(x) -> str:
    if isinstance(x, (bytes, bytearray)):
        try:
            return x.decode("utf-8", "ignore")
        except Exception:
            return str(x)
    return str(x)

def _uniq(seq):
    seen = set(); out = []
    for x in seq:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

# ===========================
# CSV / TSV / TXT
# ===========================
def read_csv(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """อ่าน .csv/.tsv/.txt แบบพยายามเดา encoding และ delimiter พร้อมจัดการไฟล์ขนาดใหญ่"""
    sep_candidates = [None]  # None = ให้ pandas sniff
    if path.suffix.lower() == ".tsv":
        sep_candidates = ["\t", None]

    encodings = ("utf-8-sig", "utf-8", "cp874", "latin-1")

    # ตรวจสอบขนาดไฟล์ก่อนอ่าน
    file_size = path.stat().st_size
    large_file_threshold = 100 * 1024 * 1024  # 100 MB
    
    last_err = None
    for enc in encodings:
        for sep in sep_candidates:
            try:
                if file_size > large_file_threshold:
                    # สำหรับไฟล์ใหญ่ ใช้ chunking
                    print(f"ไฟล์ขนาดใหญ่ ({file_size / (1024*1024):.1f} MB) - กำลังอ่านแบบ chunking...")
                    df = _read_csv_chunked(path, sep, enc)
                else:
                    # สำหรับไฟล์เล็ก อ่านปกติ
                    if sep is None:
                        df = pd.read_csv(path, engine="python", sep=None, on_bad_lines="skip", encoding=enc)
                    else:
                        df = pd.read_csv(path, engine="python", sep=sep, on_bad_lines="skip", encoding=enc)
                
                return df, {"source": "csv", "path": str(path), "encoding": enc, "sep": sep or "auto", "file_size_mb": file_size / (1024*1024)}
            except Exception as e:
                last_err = e
                continue

    # ไม้ตาย
    try:
        if file_size > large_file_threshold:
            df = _read_csv_chunked(path, None, "utf-8")
        else:
            df = pd.read_csv(path, engine="python", on_bad_lines="skip")
        return df, {"source": "csv", "path": str(path), "encoding": "unknown", "sep": "auto", "file_size_mb": file_size / (1024*1024)}
    except Exception as e:
        raise RuntimeError(f"ไม่สามารถอ่านไฟล์ CSV ได้: {e}")

def _read_csv_chunked(path: Path, sep: str = None, encoding: str = "utf-8", chunk_size: int = 10000) -> pd.DataFrame:
    """อ่านไฟล์ CSV แบบ chunking สำหรับไฟล์ขนาดใหญ่"""
    chunks = []
    total_rows = 0
    
    try:
        # อ่าน chunk แรกเพื่อดูโครงสร้าง
        first_chunk = pd.read_csv(path, engine="python", sep=sep, encoding=encoding, 
                                nrows=chunk_size, on_bad_lines="skip")
        chunks.append(first_chunk)
        total_rows += len(first_chunk)
        
        # อ่าน chunks ที่เหลือ
        chunk_iter = pd.read_csv(path, engine="python", sep=sep, encoding=encoding, 
                               chunksize=chunk_size, on_bad_lines="skip")
        
        for chunk in chunk_iter:
            chunks.append(chunk)
            total_rows += len(chunk)
            print(f"อ่านแล้ว {total_rows:,} แถว...")
            
            # จำกัดจำนวนแถวสูงสุดเพื่อป้องกัน memory overflow
            max_rows = 1_000_000  # 1 ล้านแถว
            if total_rows >= max_rows:
                print(f"จำกัดข้อมูลที่ {max_rows:,} แถว เพื่อป้องกันหน่วยความจำเต็ม")
                break
        
        # รวม chunks
        if len(chunks) == 1:
            df = chunks[0]
        else:
            df = pd.concat(chunks, ignore_index=True)
            
        print(f"อ่านไฟล์เสร็จสิ้น: {len(df):,} แถว, {len(df.columns)} คอลัมน์")
        return df
        
    except Exception as e:
        raise RuntimeError(f"เกิดข้อผิดพลาดในการอ่านไฟล์แบบ chunking: {e}")

# ===========================
# Excel
# ===========================
def read_excel(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except TypeError:
        df = pd.read_excel(path)
    return df, {"source": "xlsx", "path": str(path)}

# ===========================
# NetCDF (quick/inspect/slice)
# ===========================
def read_netcdf_quick(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """เปิด dataset เป็น DataFrame แบบเร็ว (ดูรวม ๆ)
       ถ้าต้อง slice มิติ → ใช้ dialogs เลือก แล้วค่อยเรียก slice_netcdf()
    """
    import xarray as xr
    tried: List[str] = []
    for eng in (None, "netcdf4", "h5netcdf", "scipy"):
        try:
            ds = xr.open_dataset(str(path), engine=eng) if eng else xr.open_dataset(str(path))
            try:
                df = ds.to_dataframe().reset_index()
            finally:
                try:
                    ds.close()
                except Exception:
                    pass
            return df, {"source": "netcdf", "path": str(path), "engine": eng or "auto"}
        except Exception as e:
            tried.append(f"{eng or 'auto'}: {e}")
    raise RuntimeError("xarray เปิดไม่ได้ด้วยทุก backend ที่ลอง:\n" + "\n".join(f"- {t}" for t in tried))

def inspect_netcdf(path: Path) -> Dict[str, Any]:
    import xarray as xr
    ds = xr.open_dataset(str(path))
    try:
        var_shape = {name: tuple(map(int, ds[name].shape)) for name in ds.data_vars}
        coords = list(ds.coords)

        # candidates เวลา: ชื่อมี time/epoch/utc
        time_candidates = []
        for name in list(ds.data_vars) + list(ds.coords):
            low = str(name).lower()
            if any(k in low for k in ("time", "epoch", "utc")):
                time_candidates.append(name)

        time_candidates = _uniq(time_candidates) or coords or list(ds.data_vars)
        return {
            "data_vars": list(ds.data_vars),
            "coords": coords,
            "var_shape": var_shape,
            "time_candidates": _uniq(time_candidates),
            "deps_map": {},  # NetCDF ไม่ใช้ DEPEND_* แบบ ISTP (เก็บว่างไว้)
        }
    finally:
        try:
            ds.close()
        except Exception:
            pass

def slice_netcdf(path: Path, data_var: str, time_var: str, index_map: Dict[str, int]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    import xarray as xr
    ds = xr.open_dataset(str(path))
    try:
        da = ds[data_var]
        # map index_map → selection
        sel = {}
        dims = list(da.dims)
        for i, dim in enumerate(dims):
            if dim == time_var or dim == str(time_var):
                continue
            if f"DEPEND_{i+1}" in index_map:
                sel[dim] = int(index_map[f"DEPEND_{i+1}"])
            elif dim != time_var:
                sel[dim] = 0
        sliced = da.isel(**sel)

        # time coord
        if time_var in sliced.coords:
            t = pd.to_datetime(pd.Series(pd.Index(sliced.coords[time_var].values)))
        elif time_var in ds:
            t = pd.to_datetime(pd.Series(pd.Index(ds[time_var].values)))
        else:
            t = pd.Series(range(sliced.shape[0]))

        y = np.asarray(sliced.values).reshape(-1)
        n = min(len(t), len(y))
        df = pd.DataFrame({str(time_var): t.iloc[:n].values, str(data_var): y[:n]})
        meta = {
            "source": "netcdf",
            "path": str(path),
            "data_var": data_var,
            "time_var": time_var,
            "indices": index_map,
            "shape_raw": tuple(map(int, da.shape)),
            "length": len(df),
        }
        return df, meta
    finally:
        try:
            ds.close()
        except Exception:
            pass

# ===========================
# CDF helpers (เวลา/label)
# ===========================
def _is_tt2000(arr: np.ndarray) -> bool:
    return np.issubdtype(arr.dtype, np.integer) and arr.size > 0 and np.nanmax(arr.astype("float64")) > 1e14

def _is_epoch(arr: np.ndarray) -> bool:
    return np.issubdtype(arr.dtype, np.floating) and arr.size > 0 and np.nanmax(arr) > 1e9

def _is_epoch16(arr: np.ndarray) -> bool:
    return arr.ndim == 2 and arr.shape[1] == 2 and np.issubdtype(arr.dtype, np.floating)

def _to_datetime_series(name: str, arr: np.ndarray) -> pd.Series:
    """แปลง TT2000/EPOCH/EPOCH16 ของ CDF → pandas datetime (ถ้าใช่ชนิดเวลา)"""
    try:
        a = np.asarray(arr)
        if _is_tt2000(a) or _is_epoch(a) or _is_epoch16(a):
            dt = cdflib.cdfepoch.to_datetime(a, to_np=True)
            return pd.Series(pd.to_datetime(dt), name=name)
    except Exception:
        pass
    return pd.Series(arr, name=name)

def _decode_name_any(x) -> str:
    # รองรับ bytes/bytearray, numpy scalar, อื่น ๆ
    try:
        if isinstance(x, (bytes, bytearray)):
            return x.decode("utf-8", "ignore").strip()
        s = str(x)
        return s.strip()
    except Exception:
        return str(x)

def _names_from_info_or_iter(cdf, path: Path) -> List[str]:
    """
    ดึงรายชื่อตัวแปรให้ได้ 'ไม่ว่าอย่างไร':
      1) cdf.cdf_info(): รองรับทั้ง dict และออปเจ็กต์ (เช่น CDFInfo) ผ่านแอตทริบิวต์
      2) varinq ไล่ index 0..4095
      3) ไม้ตาย: cdflib.cdf_to_xarray(str(path)) แล้วหยิบชื่อ data_vars+coords
    """
    names: List[str] = []

    def _as_list(x):
        if x is None:
            return []
        if isinstance(x, (list, tuple)):
            return list(x)
        try:
            import numpy as _np
            if isinstance(x, _np.ndarray):
                return x.tolist()
        except Exception:
            pass
        return [x]

    # 1) จาก cdf_info() — รองรับได้ทั้ง dict และออปเจ็กต์
    try:
        info = cdf.cdf_info()
        candidates = {}
        if isinstance(info, dict):
            candidates = {
                "zVariables": info.get("zVariables", []),
                "rVariables": info.get("rVariables", []),
                "Variables": info.get("Variables", []),
                "vars": info.get("vars", []),
            }
        else:
            for k in ("zVariables", "rVariables", "Variables", "vars"):
                if hasattr(info, k):
                    candidates[k] = getattr(info, k)

        for _, vals in candidates.items():
            for v in _as_list(vals):
                s = _decode_name_any(v)
                if s and s not in names:
                    names.append(s)
    except Exception:
        pass

    # 2) ไล่ด้วย varinq index (บางเวอร์ชันเข้าถึงตัวแปรได้แบบนี้)
    if not names:
        seen = set()
        for i in range(0, 4096):
            try:
                q = cdf.varinq(i)
                nm = _decode_name_any(q.get("Variable", i))
                if nm and nm not in seen:
                    seen.add(nm); names.append(nm)
            except Exception:
                # พอเริ่ม throw ต่อเนื่องก็ปล่อยผ่าน
                continue

    # 3) ไม้ตาย: ใช้ xarray ที่แปลงจาก cdflib
    if not names:
        try:
            ds = cdflib.cdf_to_xarray(str(path))
            try:
                names = list(map(str, list(ds.data_vars) + list(ds.coords)))
            finally:
                try:
                    ds.close()
                except Exception:
                    pass
        except Exception:
            pass

    return names

def _safe_varattsget(cdf: cdflib.CDF, varname: str) -> Dict[str, Any]:
    """ดึงแอตทริบิวต์ตัวแปรแล้วแปลง bytes→str ให้เรียบร้อย (กันพัง)"""
    try:
        atts = cdf.varattsget(varname) or {}
        out = {}
        for k, v in atts.items():
            if isinstance(v, (list, tuple)):
                out[_b2s(k)] = [_b2s(x) for x in v]
            else:
                out[_b2s(k)] = _b2s(v)
        return out
    except Exception:
        return {}

def _extract_units_from_atts(atts: Dict[str, Any]) -> str | None:
    """
    พยายามอ่านหน่วยจากแอตทริบิวต์ยอดฮิตในไฟล์ CDF/ISTP/MMS
    รองรับ: UNITS/Units/units/Unit/unit และ SI_CONVERSION (เช่น '1.0>nT')
    """
    # 1) คีย์ตรง ๆ เรื่องหน่วย
    for key in ("UNITS", "Units", "units", "Unit", "unit"):
        u = atts.get(key)
        u = _b2s(u).strip() if u else ""
        if u:
            return u

    # 2) SI_CONVERSION มักอยู่ในรูป 'scale>unit'
    si = atts.get("SI_CONVERSION") or atts.get("SI_conversion") or atts.get("Si_Conversion") or ""
    si = _b2s(si)
    if ">" in si:
        unit = si.split(">")[-1].strip()
        if unit:
            return unit

    # 3) เผื่อหลงมาในฟิลด์ที่ขึ้นต้นด้วย 'UNIT'
    for k, v in atts.items():
        ks = _b2s(k).strip().lower()
        if ks.startswith("unit"):
            u = _b2s(v).strip()
            if u:
                return u

    return None

# ===========================
def read_cdf_quick(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """อ่าน CDF แบบพอเห็นภาพรวม:
       - หา time_var อัตโนมัติจาก DEPEND_0/ชื่อ
       - รวมตัวแปร 1D (ยาวเท่าเวลา) + ขยายเวกเตอร์ 2D (N,k<=16) เป็นหลายคอลัมน์
    """
    cdf = cdflib.CDF(str(path))

    names = _names_from_info_or_iter(cdf, path)
    if not names:
        raise RuntimeError("ไม่พบตัวแปรในไฟล์ CDF")

    # เก็บแอตทริบิวต์เพื่อใช้ label
    var_atts: Dict[str, Dict[str, Any]] = {}
    for nm in names:
        try:
            var_atts[nm] = cdf.varattsget(nm) or {}
        except Exception:
            var_atts[nm] = {}

    # หา time candidates
    time_candidates = []
    for nm in names:
        atts = var_atts.get(nm, {})
        dep0 = atts.get("DEPEND_0") or atts.get("depend_0") or atts.get("Depend_0")
        if isinstance(dep0, str):
            time_candidates.append(dep0)
    if not time_candidates:
        for nm in names:
            low = nm.lower()
            if any(k in low for k in ("epoch", "time", "utc")):
                time_candidates.append(nm)
    time_candidates = _uniq(time_candidates) or list(names)

    # เลือก time_var ตัวแรกที่แปลงเวลาได้จริง
    time_var = None
    t_arr = None
    for tv in time_candidates:
        try:
            t_try = np.asarray(cdf.varget(tv))
            t_series = _to_datetime_series(tv, t_try)
            t_dt = pd.to_datetime(t_series)
            if t_dt.notna().sum() >= max(1, int(0.5 * len(t_dt))):
                time_var = tv
                t_arr = t_try
                break
        except Exception:
            continue
    if time_var is None:
        # ถ้าหาไม่ได้ ใช้ตัวแรกที่ 1D ยาวสุดแทน
        best = None; best_len = 0
        for nm in names:
            try:
                arr = np.asarray(cdf.varget(nm))
            except Exception:
                continue
            if arr.ndim == 1 and arr.size > best_len:
                best = nm; best_len = arr.size
        if best is None:
            raise RuntimeError("หาแกนเวลาไม่ได้ใน CDF")
        time_var = best
        t_arr = np.asarray(cdf.varget(best))

    N = int(np.asarray(t_arr).shape[0])
    df_parts: Dict[str, pd.Series] = {str(time_var): _to_datetime_series(time_var, t_arr)}

    # รวมตัวแปร
    for nm in names:
        if nm == time_var:
            continue
        try:
            arr = np.asarray(cdf.varget(nm))
        except Exception:
            continue

        # (N,1) → (N,)
        if arr.ndim == 2 and 1 in arr.shape:
            arr = arr.reshape(-1)

        # 1D เท่ากับเวลา
        if arr.ndim == 1 and arr.shape[0] == N:
            df_parts[nm] = pd.Series(arr, name=nm)
            continue

        # เวกเตอร์ 2D
        if arr.ndim == 2:
            if arr.shape[0] == N:
                vec = arr
            elif arr.shape[1] == N:
                vec = arr.T
            else:
                continue
            N2, K = vec.shape
            if N2 != N or K > 16:
                continue

            atts = var_atts.get(nm, {})
            labels = None
            ptr = atts.get("LABL_PTR_1") or atts.get("LABLAXIS") or atts.get("LABL_PTR")
            if isinstance(ptr, str):
                try:
                    lab_arr = np.asarray(cdf.varget(ptr))
                    labels = [str(x).strip() for x in lab_arr.tolist()]
                except Exception:
                    labels = None
            if labels is None and K == 3 and nm.lower().startswith("b"):
                labels = ["x", "y", "z"]
            if labels is None or len(labels) != K:
                labels = [str(i) for i in range(K)]
            for j in range(K):
                col = f"{nm}[{labels[j]}]"
                df_parts[col] = pd.Series(vec[:, j], name=col)

    df = pd.DataFrame(df_parts)
    return df, {"source": "cdf", "path": str(path), "time_var": time_var, "vars": list(df.columns), "length": len(df)}

# ===========================
# อ่าน CDF: โหมด MMS-เจาะลึก + เมทาดาต้า
# ===========================
def read_cdf(path: str | Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    เปิดไฟล์ CDF แบบเน้น MMS FGM:
    - ใช้ read_mms_fgm_cdf() เพื่อได้ df ที่มี 'time' + คอลัมน์ข้อมูล (เช่น Bx GSE, By GSE, Bz GSE, Bt)
    - ดึง meta ที่ใช้ใน UI (หน่วย, source_var) เท่าที่หาได้
    """
    path = Path(path)
    df = read_mms_fgm_cdf(path)

    # เตรียม meta พื้นฐาน
    meta: Dict[str, Any] = {
        "source_path": str(path),
        "format": "CDF",
        "columns": list(df.columns),
        "time_column": "time",
        "note": "Parsed by read_mms_fgm_cdf()",
    }

    # ลองเปิดอีกครั้งเพื่อดูแอตทริบิวต์ของตัวแปรข้อมูลหลัก (เพื่อ units/labels)
    try:
        cdf = cdflib.CDF(str(path))
        try:
            info = cdf.cdf_info()
            varnames: List[str] = []
            if isinstance(info, dict) and "Variables" in info:
                varnames = [ _b2s(v).strip() for v in info.get("Variables", []) ]
            else:
                try:
                    for i in range(4096):
                        q = cdf.varinq(i)
                        vn = _b2s(q.get("Variable")).strip()
                        if vn: varnames.append(vn)
                except Exception:
                    pass
            varnames = list(dict.fromkeys(varnames))  # unique

            # – เก็บ meta ต่อคอลัมน์: units / source_var
            col_meta: Dict[str, Dict[str, Any]] = {}

            for vn in varnames:
                atts = _safe_varattsget(cdf, vn)
                units = _extract_units_from_atts(atts)
                # กรณีเวกเตอร์แม่เหล็ก → map ไป Bx/By/Bz/Bt ถ้ามี
                lower_vn = vn.lower()
                if lower_vn.startswith("b"):
                    for comp in ("Bx GSE", "By GSE", "Bz GSE", "Bt", "Bx", "By", "Bz"):
                        if comp in df.columns:
                            col_meta.setdefault(comp, {})
                            if units: col_meta[comp]["units"] = units
                            col_meta[comp].setdefault("source_var", vn)
                else:
                    # เผื่อกรณีเป็นสเกลาร์
                    if vn in df.columns:
                        col_meta.setdefault(vn, {})
                        if units: col_meta[vn]["units"] = units
                        col_meta[vn].setdefault("source_var", vn)
                                    # ถ้าไม่มีหน่วยโผล่มาเลยสำหรับคอลัมน์แม่เหล็ก → ตั้งเป็น nT แบบเดา (และติดธง)
            guessed_any = False
            for comp in ("Bx GSE", "By GSE", "Bz GSE", "Bt", "Bx", "By", "Bz"):
                if comp in df.columns:
                    col_meta.setdefault(comp, {})
                    if "units" not in col_meta[comp]:
                        col_meta[comp]["units"] = "nT"
                        col_meta[comp]["units_guessed"] = True
                        guessed_any = True

            if guessed_any:
                meta.setdefault("notes", [])
                meta["notes"].append("Units for magnetic field columns were guessed as nT.")

                            

            if col_meta:
                meta["columns_meta"] = col_meta
            
        finally:
            try:
                cdf.close()
            except Exception:
                pass

    except Exception:
        # ถ้าหา meta ไม่ได้ก็ปล่อย meta พื้นฐาน
        pass

    return df, meta

# ===========================
# Inspect/Slice CDF (ISTP-style)
# ===========================
def inspect_cdf_istp(path: Path) -> Dict[str, Any]:
    """ตรวจโครงสร้าง CDF แบบทนทายาด ใช้สำหรับ Dialog เลือก slice"""
    try:
        cdf = cdflib.CDF(str(path))
    except Exception as e:
        raise RuntimeError(f"เปิด CDF ไม่ได้: {e}")

    names = _names_from_info_or_iter(cdf, path)
    if not names:
        raise RuntimeError("ไม่พบตัวแปรใด ๆ ในไฟล์ CDF (cdf_info/varinq/cdf_to_xarray ว่าง)")

    all_vars = list(names)
    data_vars: List[str] = []
    deps_map: Dict[str, Dict[str, str]] = {}
    var_len: Dict[str, int] = {}
    var_shape: Dict[str, tuple] = {}
    time_candidates: List[str] = []

    for name in names:
        # attributes
        try:
            atts = cdf.varattsget(name) or {}
        except Exception:
            atts = {}

        # shape/length
        try:
            arr = np.asarray(cdf.varget(name))
            var_shape[name] = tuple(int(s) for s in arr.shape)
            if arr.ndim == 1:
                var_len[name] = int(arr.shape[0])
            elif arr.ndim == 2 and 1 in arr.shape:
                var_len[name] = int(arr.reshape(-1).shape[0])
        except Exception:
            pass

        # data var
        var_type = (atts.get("VAR_TYPE") or atts.get("Var_Type") or "").strip().lower()
        if var_type == "data":
            data_vars.append(name)

        # depends
        dep_map = {}
        for i in range(6):
            k = f"DEPEND_{i}"
            if k in atts:
                dep_map[k] = atts[k]
        if dep_map:
            deps_map[name] = dep_map
            if "DEPEND_0" in dep_map and dep_map["DEPEND_0"] not in time_candidates:
                time_candidates.append(dep_map["DEPEND_0"])

        # heuristic time by name
        low = name.lower()
        if any(key in low for key in ("epoch", "time", "utc")) and name not in time_candidates:
            time_candidates.append(name)

    if not data_vars:
        data_vars = list(all_vars)
    if not time_candidates:
        time_candidates = list(all_vars)

    return {
        "all_vars": _uniq(all_vars),
        "data_vars": _uniq(data_vars),
        "time_candidates": _uniq(time_candidates),
        "deps_map": deps_map,
        "var_len": var_len,
        "var_shape": var_shape,
    }

def slice_cdf_istp(path: Path, data_var: str, time_var: str, index_map: Dict[str, int]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """ตัด slice จากตัวแปรข้อมูลหลายมิติให้เป็นซีรีส์ 1D เทียบกับเวลา"""
    cdf = cdflib.CDF(str(path))

    # เวลา
    t_arr = np.asarray(cdf.varget(time_var))
    t = pd.to_datetime(_to_datetime_series(time_var, t_arr))

    # ข้อมูล
    data_raw = np.asarray(cdf.varget(data_var))
    if data_raw.ndim == 1:
        y = data_raw
    else:
        # สมมติ axis 0 = เวลา
        slc = [slice(None)] + [int(index_map.get(f"DEPEND_{i}", 0)) for i in range(1, data_raw.ndim)]
        y = np.asarray(data_raw[tuple(slc)]).reshape(-1)

        # ถ้าไม่ยาวเท่าเวลา ให้หาแกนที่ยาวเท่า len(t)
        if y.shape[0] != len(t):
            for ax, size in enumerate(data_raw.shape):
                if size == len(t):
                    take = [int(index_map.get(f"DEPEND_{i}", 0)) for i in range(data_raw.ndim)]
                    take[ax] = slice(None)
                    y2 = np.asarray(data_raw[tuple(take)]).reshape(-1)
                    if y2.shape[0] == len(t):
                        y = y2
                        break

    n = min(len(t), len(y))
    df = pd.DataFrame({str(time_var): t.iloc[:n].values, str(data_var): np.asarray(y[:n]).reshape(-1)})
    meta = {
        "source": "cdf",
        "path": str(path),
        "data_var": data_var,
        "time_var": time_var,
        "indices": index_map,
        "shape_raw": tuple(int(s) for s in np.shape(data_raw)),
        "length": len(df),
    }
    return df, meta

# ===========================
# หน้าบ้าน: เลือกวิธีอ่านตามนามสกุลไฟล์
# ===========================
def read_file(path: str | Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = Path(path)
    ext = path.suffix.lower()

    if ext in (".csv", ".txt", ".tsv"):
        return read_csv(path)
    if ext in (".xlsx", ".xls"):
        return read_excel(path)
    if ext == ".nc":
        # เปิดแบบ NetCDF เร็ว ๆ (ดูรวม) — ถ้าต้อง slice ให้ไปผ่าน Dialog
        return read_netcdf_quick(path)
    if ext == ".cdf":
    # ใช้ตัวอ่านแบบ MMS-aware ก่อน (ชื่อคอลัมน์/เวลาแม่นกว่า)
        try:
            return read_cdf(path)
        except Exception as e_mms:
        # ถ้าไฟล์ไม่ใช่สกุลที่เรารองรับแบบเจาะลึก ค่อย fallback ไป quick
            try:
                return read_cdf_quick(path)
            except Exception as e_quick:
            # เผื่อไฟล์นี้จริง ๆ คือ netCDF ที่ใช้ .cdf
                try:
                    df, meta = read_netcdf_quick(path)
                    meta["note"] = "Opened by xarray; extension was .cdf but looked like netCDF."
                    return df, meta
                except Exception as e_nc:
                    raise RuntimeError(
                        "เปิด .cdf ไม่ได้ทั้งสามวิธี:\n"
                        f"- MMS reader error: {e_mms}\n"
                        f"- cdflib quick error: {e_quick}\n"
                        f"- xarray error: {e_nc}"
                )
