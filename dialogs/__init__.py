# -*- coding: utf-8 -*-
# ไฟล์นี้ทำให้โฟลเดอร์ `dialogs` เป็น Python package
# เพื่อให้ import แบบ `dialogs.dialogs_charts_adv` ทำงานได้

# Import all dialog classes from all_dialogs.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from all_dialogs import (
    MultiDimSliceDialog,
    ColumnTypeDialog, 
    AggregateDialog,
    FitDialog,
    DerivedColumnDialog,
    FFTDialog
)

__all__ = [
    "dialogs_charts_adv",
    "MultiDimSliceDialog",
    "ColumnTypeDialog", 
    "AggregateDialog",
    "FitDialog",
    "DerivedColumnDialog",
    "FFTDialog"
]
