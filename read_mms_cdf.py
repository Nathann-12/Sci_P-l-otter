# read_mms_cdf.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple, List, Any
import numpy as np
import pandas as pd
import cdflib

def _b2s(x: Any) -> str:
    """แปลง bytes/bytearray → str แบบปลอดภัย"""
    if isinstance(x, (bytes, bytearray)):
        try:
            return x.decode("utf-8", "ignore")
        except Exception:
            return str(x)
    return str(x)


def _to_list(x: Any) -> List[Any]:
    """
    บังคับให้เป็น list
    - None → []
    - list/tuple → list
    - numpy.ndarray (รวมถึง chararray) → tolist()
    - อื่น ๆ → [x]
    """
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return list(x)
    try:
        import numpy as _np  # เผื่อกรณี import ข้างบนถูกแก้ไขในอนาคต
        if isinstance(x, _np.ndarray):
            return x.tolist()
    except Exception:
        pass
    return [x]


def _to_datetime_any(a: Any) -> pd.Series:
    """แปลง TT2000/EPOCH/EPOCH16 → pandas datetime; ถ้าไม่ใช่ก็ลอง to_datetime ปกติ"""
    try:
        return pd.to_datetime(cdflib.cdfepoch.to_datetime(a, to_np=True))
    except Exception:
        return pd.to_datetime(a, errors="coerce")


def _is_time_var(cdf: cdflib.CDF, name: str) -> bool:
    """เดาว่าตัวแปรไหนคือเวลา โดยดูชื่อ และลองแปลง epoch ตัวอย่าง"""
    nm = (name or "").lower()
    if any(k in nm for k in ("epoch", "time", "utc")):
        return True
    try:
        arr = cdf.varget(name)[:10]
        _ = cdflib.cdfepoch.to_datetime(arr, to_np=True)
        return True
    except Exception:
        return False


def _names_from_cdf_info(info: Any) -> List[str]:
    """
    ดึงรายชื่อตัวแปรจากผลลัพธ์ cdf.cdf_info()
    - บางเวอร์ชันคืน dict
    - บางทีอาจเป็น object อื่นที่มีแอตทริบิวต์คล้าย ๆ กัน
    """
    out: List[str] = []

    candidates: Dict[str, Any] = {}
    if isinstance(info, dict):
        candidates = {
            "rVariables": info.get("rVariables", []),
            "zVariables": info.get("zVariables", []),
            "Variables": info.get("Variables", []),
            "vars": info.get("vars", []),
        }
    else:
        # เผื่อเป็น object ที่มีแอตทริบิวต์ชื่อเดียวกัน
        for k in ("rVariables", "zVariables", "Variables", "vars"):
            if hasattr(info, k):
                candidates[k] = getattr(info, k)

    for _, vals in candidates.items():
        for v in _to_list(vals):
            s = _b2s(v).strip()
            if s and s not in out:
                out.append(s)
    return out


def _cand_vars(cdf: cdflib.CDF) -> List[str]:
    """
    รวมรายชื่อตัวแปรทั้งหมดแบบทนทาน:
    1) จาก cdf_info()
    2) ถ้ายังไม่ได้ → ลองไล่ varinq(index)
    3) กันกรณีสุดท้าย: key "Variables" โดยตรง
    """
    names: List[str] = []

    # ทางหลัก: ใช้ cdf_info()
    try:
        info = cdf.cdf_info()
    except Exception:
        info = None

    names.extend(_names_from_cdf_info(info) if info is not None else [])

    # fallback: บางไฟล์/เวอร์ชัน ไม่มีรายชื่อครบ → ลองไล่ varinq(index)
    if not names:
        for i in range(0, 4096):  # เพดานสูงหน่อย
            try:
                q = cdf.varinq(i)  # บางเวอร์ชันรองรับ index
                nm = _b2s(q.get("Variable"))
                s = nm.strip()
                if s and s not in names:
                    names.append(s)
            except Exception:
                break  # เลยขอบเขตแล้ว

    # กันกรณีสุดท้าย: ลองอ่าน key "Variables" โดยตรงถ้าเป็น dict
    if not names:
        try:
            info = cdf.cdf_info()
            if isinstance(info, dict):
                for v in _to_list(info.get("Variables", [])):
                    s = _b2s(v).strip()
                    if s and s not in names:
                        names.append(s)
        except Exception:
            pass

    return names


# =========================
# ตัวอ่านไฟล์ MMS FGM CDF
# =========================

def read_mms_fgm_cdf(path: str | Path) -> pd.DataFrame:
    """
    อ่านไฟล์ CDF (เช่น MMS FGM) → คืน DataFrame ที่มีคอลัมน์ 'time' และข้อมูลเวกเตอร์/สเกลาร์
    เลือกตัวแปรเวลาอัตโนมัติ และคัดเลือกตัวแปรข้อมูลที่เป็นฟังก์ชันของเวลา
    """
    cdf = cdflib.CDF(str(path))
    try:
        names = _cand_vars(cdf)
        if not names:
            raise RuntimeError("ไม่พบตัวแปรใด ๆ ในไฟล์ CDF (cdf_info()/varinq ว่าง)")

        # 1) หา time variable
        time_vars = [n for n in names if _is_time_var(cdf, n)]
        time_var = None
        # ให้สิทธิ์ชื่อ 'Epoch' ก่อน เพราะพบได้บ่อยใน MMS
        for cand in time_vars:
            if cand.lower() == "epoch":
                time_var = cand
                break
        if time_var is None and time_vars:
            time_var = time_vars[0]
        if time_var is None:
            raise RuntimeError("ไม่พบตัวแปรเวลา (เช่น Epoch/time/utc/TT2000)")

        # แปลงเวลา
        t = _to_datetime_any(cdf.varget(time_var))
        if t.isna().all():
            raise RuntimeError(f"ตัวแปรเวลา '{time_var}' แปลงเป็น datetime ไม่ได้")
        N = len(t)

        # 2) คัดตัวแปรข้อมูล: เอา VAR_TYPE=='data' และ DEPEND_0 ชี้ time_var ก่อน
        data_picks: List[Tuple[str, tuple, Dict[str, Any]]] = []
        for n in names:
            if n == time_var:
                continue
            try:
                atts = cdf.varattsget(n) or {}
            except Exception:
                atts = {}
            var_type = _b2s(atts.get("VAR_TYPE", "")).strip().lower()
            dep0 = atts.get("DEPEND_0")
            dep0 = _b2s(dep0).strip() if dep0 is not None else None

            # รูปทรงข้อมูล
            try:
                arr = np.asarray(cdf.varget(n))
                shape = arr.shape
            except Exception:
                continue

            if var_type == "data" and dep0 == str(time_var):
                data_picks.append((n, shape, atts))

        # ถ้าไม่มีตามเกณฑ์ → fallback: เลือกตัวเลขที่มีแกนใดแกนหนึ่งเท่ากับ N
        if not data_picks:
            for n in names:
                if n == time_var:
                    continue
                try:
                    arr = np.asarray(cdf.varget(n))
                except Exception:
                    continue
                if arr.size == 0 or not np.issubdtype(arr.dtype, np.number):
                    continue
                if arr.ndim == 1 and arr.shape[0] == N:
                    data_picks.append((n, arr.shape, {}))
                elif arr.ndim >= 2 and any(sz == N for sz in arr.shape):
                    data_picks.append((n, arr.shape, {}))

        if not data_picks:
            raise RuntimeError("ไม่พบตัวแปรข้อมูลที่เป็นฟังก์ชันของเวลา")

        # 3) ให้คะแนนเลือกตัวแปรเหมาะสุด:
        #    ชอบ Nx3 (Bx,By,Bz) มากสุด → รองลงมา Nx4 (Bx,By,Bz,Bt) → รองลงมา Nx1
        def score(shape: tuple) -> int:
            if len(shape) == 2 and shape[0] == N and shape[1] == 3:
                return 0
            if len(shape) == 2 and shape[0] == N and shape[1] == 4:
                return 1
            if len(shape) == 2 and shape[1] == N and shape[0] == 3:
                return 2
            if len(shape) == 2 and shape[1] == N and shape[0] == 4:
                return 3
            if len(shape) == 1 and shape[0] == N:
                return 4
            return 9

        data_picks.sort(key=lambda x: score(x[1]))
        data_var, shape, atts = data_picks[0]

        # 4) ดึงข้อมูล และจัดแกนเวลาให้อยู่แกน 0
        Y = np.asarray(cdf.varget(data_var))
        # ให้เป็นรูป (N, m)
        if Y.ndim == 2 and Y.shape[1] == N:
            Y = Y.T
        if Y.ndim >= 2 and Y.shape[0] != N:
            # ย้ายแกนที่เท่ากับ N มาเป็นแกน 0
            for ax, sz in enumerate(Y.shape):
                if sz == N:
                    Y = np.moveaxis(Y, ax, 0)
                    break

        # 5) ตั้งชื่อคอลัมน์: ใช้ LABL_PTR_* ถ้ามี
        labels = None
        for key in ("LABL_PTR_1", "LABL_PTR", "LABLAXIS", "LABL_AXIS", "LABL_PTR_2"):
            lbl = atts.get(key)
            lbl = _b2s(lbl).strip() if lbl is not None else None
            if lbl and lbl in names:
                try:
                    labels_raw = cdf.varget(lbl)          # มักเป็น numpy array ของสตริง
                    labels_list = _to_list(labels_raw)    # แตกเป็น list จริง
                    labels = [_b2s(s).strip() for s in labels_list]
                    labels = [s for s in labels if s]     # ลบค่าว่าง
                except Exception:
                    labels = None
            if labels:
                break

        # 6) ประกอบ DataFrame
        df = pd.DataFrame({"time": t})

        if Y.ndim == 1:
            df[_b2s(data_var)] = Y
        else:
            m = Y.shape[1]

            # ถ้า label มี ให้ตัดช่องว่างส่วนเกิน และ normalize ช่องว่างภายใน
            def _clean_label(s: str) -> str:
                s = s.strip()
                # ลบช่องว่างหาง ("Bx GSE    " → "Bx GSE")
                s = " ".join(s.split())
                return s

            use_labels = None
            if labels and len(labels) >= m:
                use_labels = [_clean_label(s) for s in labels[:m]]

            # เดาชื่อกรณีพบบ่อย: เวกเตอร์แม่เหล็ก (Bx,By,Bz[,Bt])
            if use_labels is None:
                base = _b2s(data_var).lower()
                if base.startswith("b"):
                    if m == 3:
                        use_labels = ["Bx", "By", "Bz"]
                    elif m == 4:
                        use_labels = ["Bx", "By", "Bz", "Bt"]

            # ถ้ายังไม่มี ให้ใช้ data_var[k]
            if use_labels is None:
                use_labels = [f"{_b2s(data_var)}[{k}]" for k in range(m)]

            for k in range(m):
                df[use_labels[k]] = Y[:, k]

        return df

    finally:
        try:
            cdf.close()
        except Exception:
            pass


# =========================
# CLI สำหรับทดสอบเร็ว ๆ
# =========================
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python read_mms_cdf.py <path_to_cdf>")
        sys.exit(1)

    p = sys.argv[1]
    df = read_mms_fgm_cdf(p)
    print(df.head())
    print("Columns:", list(df.columns))
    print("Rows:", len(df))
