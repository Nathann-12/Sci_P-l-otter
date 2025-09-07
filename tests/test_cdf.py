import numpy as np
import cdflib

# ใส่พาธไฟล์ .cdf ของคุณ
p = r"D:\Only work\Nasadata\mms1_fgm_brst_l2_20150908104814_v4.18.0.cdf"

cdf = cdflib.CDF(p)
info = cdf.cdf_info()

# รองรับทั้งแบบ object (CDFInfo) และ dict
if hasattr(info, "zVariables") or hasattr(info, "rVariables"):
    zvars = getattr(info, "zVariables", []) or []
    rvars = getattr(info, "rVariables", []) or []
else:
    # เผื่อบางเวอร์ชันคืน dict-like
    try:
        zvars = info.get("zVariables", []) or []
        rvars = info.get("rVariables", []) or []
    except Exception:
        zvars, rvars = [], []

vars_ = list(dict.fromkeys(zvars + rvars))  # รวมและตัดซ้ำ
print("variables:", vars_)

if not vars_:
    print("NO VARS")
    raise SystemExit

# ทดลองอ่านตัวแปรแรก
v = vars_[0]
arr = np.array(cdf.varget(v))
print(f"first var: {v}  shape: {arr.shape}  ndim: {arr.ndim}  dtype: {arr.dtype}")
