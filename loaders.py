# loaders.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import numpy as np
import pandas as pd

from file_io import read_excel

# ---------------- Text/Excel ----------------
def load_tabular(path: str | Path, ext: str | None = None) -> tuple[pd.DataFrame, str]:
    path = str(path); ext = ext or os.path.splitext(path)[1].lower()
    
    # ตรวจสอบขนาดไฟล์
    file_size = os.path.getsize(path)
    large_file_threshold = 100 * 1024 * 1024  # 100 MB
    
    if ext in (".xlsx", ".xls"):
        df, meta = read_excel(path)
        note = meta.get("note")
        if not note:
            tables = meta.get("tables") or []
            idx = meta.get("table_index", 0)
            table = tables[idx] if tables and 0 <= idx < len(tables) else (tables[0] if tables else None)
            if table:
                sheet_name = table.get("sheet") or meta.get("sheet")
                rng = table.get("range") or ""
                rows = table.get("rows")
                cols = table.get("cols")
                dim = f" ({rows}x{cols})" if rows is not None and cols is not None else ""
                parts = ["excel"]
                if sheet_name:
                    parts.append(str(sheet_name).strip())
                if rng:
                    parts.append(rng)
                note = " ".join(parts).strip() + dim
            else:
                sheet_name = meta.get("sheet")
                if not sheet_name:
                    sheet_names = meta.get("sheetnames") or []
                    if sheet_names:
                        sheet_name = sheet_names[0]
                part = str(sheet_name).strip() if sheet_name else ""
                note = f"excel {part}".strip() if part else "excel"
        size_mb = meta.get("file_size_mb")
        if size_mb is None:
            size_mb = file_size / (1024 * 1024)
        note = f"{note} ({size_mb:.1f} MB)" if note else f"excel ({size_mb:.1f} MB)"
        return df, note
    seps = [None] if ext != ".tsv" else ["\t", None]
    encs = ("utf-8-sig","utf-8","cp874","latin-1")
    
    for enc in encs:
        for sep in seps:
            try:
                if file_size > large_file_threshold:
                    # สำหรับไฟล์ใหญ่ ใช้ chunking
                    print(f"ไฟล์ CSV ขนาดใหญ่ ({file_size / (1024*1024):.1f} MB) - กำลังอ่านแบบ chunking...")
                    df = _read_csv_chunked_simple(path, sep, enc)
                else:
                    # สำหรับไฟล์เล็ก อ่านปกติ
                    df = pd.read_csv(path, engine="python", sep=sep, on_bad_lines="skip", encoding=enc)
                return df, f"csv ({enc}, {'auto' if sep is None else sep}, {file_size / (1024*1024):.1f} MB)"
            except Exception:
                continue
    
    # Fallback
    try:
        if file_size > large_file_threshold:
            df = _read_csv_chunked_simple(path, None, "utf-8")
        else:
            df = pd.read_csv(path, engine="python", on_bad_lines="skip")
        return df, f"csv (fallback, {file_size / (1024*1024):.1f} MB)"
    except Exception as e:
        raise RuntimeError(f"ไม่สามารถอ่านไฟล์ตารางได้: {e}")

def _read_csv_chunked_simple(path: str, sep: str = None, encoding: str = "utf-8", chunk_size: int = 10000) -> pd.DataFrame:
    """อ่านไฟล์ CSV แบบ chunking สำหรับไฟล์ขนาดใหญ่ (เวอร์ชันง่าย)"""
    chunks = []
    total_rows = 0
    max_rows = 1_000_000
    
    try:
        # อ่านทุก chunk จาก iterator เดียว เพื่อไม่ให้ chunk แรกถูกอ่านซ้ำ
        chunk_iter = pd.read_csv(path, engine="python", sep=sep, encoding=encoding, 
                               chunksize=chunk_size, on_bad_lines="skip")
        
        for chunk in chunk_iter:
            remaining_rows = max_rows - total_rows
            if remaining_rows <= 0:
                break
            if len(chunk) > remaining_rows:
                chunk = chunk.iloc[:remaining_rows].copy()

            chunks.append(chunk)
            total_rows += len(chunk)
            print(f"อ่านแล้ว {total_rows:,} แถว...")
            
            # จำกัดจำนวนแถวสูงสุดเพื่อป้องกัน memory overflow
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

# ---------------- Utils ----------------
def _b2s(x: Any) -> str:
    if isinstance(x,(bytes,bytearray)):
        try: return x.decode("utf-8","ignore")
        except Exception: return str(x)
    return str(x)

def _to_list(x: Any) -> List[Any]:
    if x is None: return []
    if isinstance(x,(list,tuple,np.ndarray)): return list(x)
    return [x]

def _is_time_like_name(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in ("epoch","time","utc"))

def _labels_from_atts(cdf, atts: Dict[str, Any], names: List[str]) -> Optional[List[str]]:
    for key in ("LABL_PTR_1","LABL_PTR","LABLAXIS","LABL_AXIS","LABL_PTR_2"):
        ptr = atts.get(key); ptr = _b2s(ptr).strip() if ptr is not None else None
        if ptr and ptr in names:
            try:
                raw = cdf.varget(ptr)
                return [_b2s(x).strip() for x in _to_list(raw)]
            except Exception:
                pass
    return None

def _list_cdf_variables(cdf) -> List[str]:
    names: List[str] = []
    try:
        info = cdf.cdf_info() or {}
        for k in ("zVariables","rVariables","Variables","vars"):
            for v in _to_list(info.get(k, []) or []):
                s = _b2s(v).strip()
                if s and s not in names: names.append(s)
    except Exception:
        pass
    if not names:
        for i in range(0,4096):
            try:
                q = cdf.varinq(i); nm = _b2s(q.get("Variable")).strip()
                if nm and nm not in names: names.append(nm)
            except Exception:
                break
    return names

def _to_datetime_series_if_possible(name: str, arr: np.ndarray) -> Optional[pd.Series]:
    import cdflib
    a = np.asarray(arr)
    # TT2000/EPOCH/EPOCH16 via cdflib
    try:
        dt = cdflib.cdfepoch.to_datetime(a, to_np=True)
        return pd.Series(pd.to_datetime(dt), name=name)
    except Exception:
        pass
    # try pandas parsing
    try:
        s = pd.to_datetime(a, errors="coerce")
        if s.notna().sum() >= max(1, int(0.5*len(s))):
            return pd.Series(s, name=name)
    except Exception:
        pass
    return None

# ---------------- CDF Reader (A) Heuristic ----------------
def _read_cdf_as_dataframe_A(path: str | Path) -> pd.DataFrame:
    import cdflib
    cdf = None
    try:
        cdf = cdflib.CDF(str(path))
        names = _list_cdf_variables(cdf)
        if not names:
            raise RuntimeError("ไม่พบตัวแปรใน CDF (รายชื่อว่าง)")

        # หา time_var
        time_cands = []
        for nm in names:
            try:
                atts = cdf.varattsget(nm) or {}
                dep0 = _b2s(atts.get("DEPEND_0")).strip() if atts.get("DEPEND_0") is not None else None
                if dep0: time_cands.append(dep0)
            except Exception:
                pass
        if not time_cands:
            time_cands = [nm for nm in names if _is_time_like_name(nm)]
        if not time_cands:
            time_cands = names[:]

        time_var = None; t_series = None
        for tv in dict.fromkeys(time_cands):  # uniq order
            try:
                arr = cdf.varget(tv)
                s = _to_datetime_series_if_possible(tv, arr)
                if s is not None and s.notna().sum() >= max(1, int(0.5*len(s))):
                    time_var = tv; t_series = pd.to_datetime(s); break
            except Exception:
                continue
        if time_var is None or t_series is None:
            raise RuntimeError("หาแกนเวลาไม่เจอใน CDF")

        N = len(t_series)

        # คัด data var
        picks: List[tuple[str, tuple, Dict[str, Any]]] = []
        for nm in names:
            if nm == time_var: continue
            try:
                atts = cdf.varattsget(nm) or {}
            except Exception:
                atts = {}
            var_type = _b2s(atts.get("VAR_TYPE","")).strip().lower()
            dep0 = _b2s(atts.get("DEPEND_0","")).strip()
            try:
                arr = np.asarray(cdf.varget(nm)); shape = arr.shape
            except Exception:
                continue
            if var_type == "data" and dep0 == str(time_var):
                picks.append((nm, shape, atts))
        if not picks:
            # fallback: numeric และมีแกนใด = N
            for nm in names:
                if nm == time_var: continue
                try:
                    arr = np.asarray(cdf.varget(nm))
                except Exception:
                    continue
                if arr.size == 0 or not np.issubdtype(arr.dtype, np.number): continue
                if (arr.ndim == 1 and arr.shape[0] == N) or (arr.ndim >=2 and any(sz==N for sz in arr.shape)):
                    picks.append((nm, arr.shape, {}))

        if not picks:
            raise RuntimeError("ไม่พบตัวแปรข้อมูลที่ผูกกับเวลา")

        def score(shape: tuple) -> int:
            if len(shape)==2 and shape[0]==N and shape[1]==3: return 0
            if len(shape)==2 and shape[1]==N and shape[0]==3: return 1
            if len(shape)==1 and shape[0]==N: return 2
            return 9

        picks.sort(key=lambda x: score(x[1]))
        data_var, shape, atts = picks[0]

        # ดึงข้อมูลและเรียงแกน
        Y = np.asarray(cdf.varget(data_var))
        if Y.ndim == 2 and Y.shape[1]==N: Y = Y.T
        if Y.ndim >= 2 and Y.shape[0] != N:
            for ax, sz in enumerate(Y.shape):
                if sz == N:
                    Y = np.moveaxis(Y, ax, 0); break

        # ตั้งชื่อคอลัมน์
        labels = _labels_from_atts(cdf, atts, names)
        cols: Dict[str, np.ndarray] = {}
        if Y.ndim == 1:
            cols[_b2s(data_var)] = Y
        else:
            m = Y.shape[1]
            for k in range(m):
                if labels and k < len(labels) and labels[k]:
                    cname = labels[k]
                else:
                    if m==3 and _b2s(data_var).lower().startswith("b"):
                        cname = ["Bx GSE","By GSE","Bz GSE"][k]
                    else:
                        cname = f"{_b2s(data_var)}[{k}]"
                cols[cname] = Y[:,k]
            if m==3 and any(c.startswith("B") for c in cols.keys()):
                bx, by, bz = list(cols.values())[:3]
                cols["Bt"] = np.sqrt(np.asarray(bx)**2 + np.asarray(by)**2 + np.asarray(bz)**2)

        df = pd.DataFrame({"time": t_series})
        for k,v in cols.items(): df[k] = v
        return df
    except Exception as e:
        raise RuntimeError(f"อ่าน CDF แบบ Heuristic ไม่สำเร็จ: {e}")
    finally:
        if cdf is not None:
            try: cdf.close()
            except Exception: pass

# ---------------- CDF Reader (B) cdflib → xarray fallback ----------------
def _read_cdf_as_dataframe_B(path: str | Path) -> pd.DataFrame:
    import cdflib
    ds = None
    try:
        ds = cdflib.cdf_to_xarray(str(path))
        df = ds.to_dataframe().reset_index()
        # เดา time column
        time_candidates = [c for c in df.columns if str(c).lower() in ("time","epoch") or ("epoch" in str(c).lower())]
        tcol = time_candidates[0] if time_candidates else None
        if tcol is None:
            # หาตัวที่ parse เป็น datetime ได้เยอะสุด
            best = None; best_score = -1
            for c in df.columns:
                try:
                    s = pd.to_datetime(df[c], errors="coerce")
                    sc = int(s.notna().sum())
                    if sc > best_score:
                        best, best_score = c, sc
                except Exception:
                    continue
            tcol = best
        if tcol is None:
            return df  # ผู้ใช้เลือกเองใน UI
        # ดึง numeric คอลัมน์เล็ก ๆ เป็นตัวอย่าง
        num_cols = [c for c in df.columns if c!=tcol and pd.api.types.is_numeric_dtype(df[c])]
        if not num_cols:
            return df
        # คืนทั้งตาราง (ให้ UI เลือก X/Y)
        return df
    except Exception as e:
        raise RuntimeError(f"อ่าน CDF แบบ xarray ไม่สำเร็จ: {e}")
    finally:
        if ds is not None:
            try: ds.close()
            except Exception: pass

# ---------------- CDF Reader (C) Simple fallback ----------------
def _read_cdf_as_dataframe_C(path: str | Path) -> pd.DataFrame:
    """อ่าน CDF แบบง่ายที่สุด - ใช้เฉพาะ cdflib พื้นฐาน"""
    import cdflib
    cdf = None
    try:
        cdf = cdflib.CDF(str(path))
        
        # ลองหาตัวแปรทั้งหมด (แปลงเป็นสตริงให้เรียบร้อย)
        names: List[str] = []
        try:
            info = cdf.cdf_info()
            if info:
                for key in ("zVariables", "rVariables", "Variables", "vars"):
                    try:
                        vals = info.get(key) if isinstance(info, dict) else getattr(info, key, None)
                    except Exception:
                        vals = None
                    if vals:
                        for v in _to_list(vals):
                            s = _b2s(v).strip()
                            if s and s not in names:
                                names.append(s)
        except Exception:
            pass
        
        if not names:
            # ลองไล่หาตัวแปรแบบ index (เผื่อบางไฟล์ไม่รายงานผ่าน cdf_info)
            for i in range(0, 4096):
                try:
                    var_info = cdf.varinq(i)
                    if var_info and "Variable" in var_info:
                        nm = _b2s(var_info["Variable"]).strip()
                        if nm and nm not in names:
                            names.append(nm)
                except Exception:
                    # เมื่อเริ่ม throw ต่อเนื่อง ให้หยุด
                    break
        
        if not names:
            raise RuntimeError("ไม่พบตัวแปรใดๆ ในไฟล์ CDF")
        
        # หาตัวแปรเวลา
        time_var = None
        for name in names:
            nm = _b2s(name).lower()
            if any(keyword in nm for keyword in ("epoch", "time", "utc")):
                time_var = name
                break
        
        if not time_var and names:
            time_var = names[0]  # ใช้ตัวแรกถ้าไม่มีตัวแปรเวลา
        
        # อ่านข้อมูล
        data = {}
        for name in names:
            try:
                arr = cdf.varget(_b2s(name))
                if arr is not None and arr.size > 0:
                    # แปลงเวลาเป็น datetime ถ้าเป็นตัวแปรเวลา
                    if _b2s(name) == _b2s(time_var):
                        try:
                            dt = cdflib.cdfepoch.to_datetime(arr, to_np=True)
                            data["time"] = pd.to_datetime(dt)
                        except:
                            data["time"] = pd.to_datetime(arr, errors="coerce")
                    else:
                        # ตรวจสอบว่าเป็นตัวเลขหรือไม่
                        if np.issubdtype(arr.dtype, np.number):
                            data[_b2s(name)] = arr
            except Exception as e:
                print(f"Warning: ไม่สามารถอ่านตัวแปร {name}: {e}")
                continue
        
        if not data:
            raise RuntimeError("ไม่สามารถอ่านข้อมูลใดๆ จากไฟล์ CDF")
        
        # สร้าง DataFrame
        df = pd.DataFrame(data)
        
        # ถ้าไม่มีคอลัมน์เวลา ให้สร้าง index เป็นเวลา
        if "time" not in df.columns:
            df.index = pd.to_datetime(range(len(df)), unit="s")
            df = df.reset_index().rename(columns={"index": "time"})
        
        return df
        
    except Exception as e:
        raise RuntimeError(f"อ่าน CDF แบบ Simple ไม่สำเร็จ: {e}")
    finally:
        if cdf is not None:
            try: cdf.close()
            except Exception: pass

# ---------------- NetCDF quick ----------------
def _read_netcdf_as_dataframe(path: str | Path) -> pd.DataFrame:
    import xarray as xr
    ds = xr.open_dataset(str(path))
    try:
        return ds.to_dataframe().reset_index()
    finally:
        try: ds.close()
        except Exception: pass

# ---------------- Public API ----------------
def load_cdf_nc_on_demand(parent, path: str | Path) -> Optional[pd.DataFrame]:
    path = Path(path); ext = path.suffix.lower()
    try:
        # ถ้ามี parent (อยู่ในโหมด GUI) ให้เปิด Dialog ให้ผู้ใช้เลือกตัวแปรก่อน
        if parent is not None and ext in (".cdf", ".nc"):
            try:
                from PySide6.QtWidgets import QDialog
                from dialogs_cdf import CDFSliceDialog
                kind = "cdf" if ext == ".cdf" else "nc"
                dlg = CDFSliceDialog(path, kind=kind, parent=parent)
                if dlg.exec() == QDialog.Accepted:
                    df, _meta = dlg.get_slice()
                    return df
                # ผู้ใช้กดยกเลิก → ตกไปใช้วิธีอัตโนมัติ (หรือให้ UI จัดการข้อความต่อ)
            except Exception:
                # ถ้า Dialog ใช้ไม่ได้ ให้ fallback อัตโนมัติ
                pass

        if ext == ".cdf":
            # A → B → C fallback (3 วิธี)
            errors = []
            
            # วิธีที่ 1: Heuristic
            try:
                return _read_cdf_as_dataframe_A(path)
            except Exception as eA:
                errors.append(f"วิธีที่ 1 (Heuristic): {eA}")
            
            # วิธีที่ 2: cdf_to_xarray
            try:
                return _read_cdf_as_dataframe_B(path)
            except Exception as eB:
                errors.append(f"วิธีที่ 2 (xarray): {eB}")
            
            # วิธีที่ 3: Simple fallback (ชื่อถูก decode แล้ว)
            try:
                return _read_cdf_as_dataframe_C(path)
            except Exception as eC:
                errors.append(f"วิธีที่ 3 (Simple): {eC}")
            
            # ถ้าทั้ง 3 วิธีไม่สำเร็จ
            error_msg = "CDF อ่านไม่สำเร็จทั้ง 3 วิธี:\n" + "\n".join(errors)
            raise RuntimeError(error_msg)
            
        if ext == ".nc":
            return _read_netcdf_as_dataframe(path)
        raise ValueError(f"นามสกุลไม่รองรับ: {ext}")
    except Exception as e:
        # โยน error ที่อ่านง่ายขึ้นให้ UI
        raise RuntimeError(f"เปิดไฟล์ไม่สำเร็จ: {e}") from e
