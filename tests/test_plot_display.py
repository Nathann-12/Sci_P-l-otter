#!/usr/bin/env python3
"""
ทดสอบการพล็อตกราฟใน SciPlotter
สร้างไฟล์ CSV ที่มีข้อมูลสำหรับทดสอบการพล็อต
"""

import pandas as pd
import numpy as np
import os
import pytest
from pathlib import Path
from datetime import datetime


def _plot_helpers():
    import sys

    sys.dont_write_bytecode = True
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from core import plot_data
    return plot_data

def create_plot_test_data():
    """สร้างข้อมูลทดสอบสำหรับการพล็อตกราฟ"""
    
    # สร้างข้อมูลทดสอบ
    n_points = 1000
    
    data = {
        # ข้อมูลเวลา
        'time': pd.date_range('2023-01-01', periods=n_points, freq='1min'),
        'timestamp': [f"2023-01-01 {i//60:02d}:{i%60:02d}:00" for i in range(n_points)],
        
        # ข้อมูลตัวเลขปกติ
        'x_values': np.linspace(0, 10, n_points),
        'y_values': np.sin(np.linspace(0, 4*np.pi, n_points)) + np.random.normal(0, 0.1, n_points),
        
        # ข้อมูลตัวเลขในรูปสตริง
        'x_strings': [str(i) for i in range(n_points)],
        'y_strings': [str(np.sin(i/100) + np.random.normal(0, 0.1)) for i in range(n_points)],
        
        # ข้อมูลตัวเลขแบบอื่น
        'temperature': np.random.normal(25, 5, n_points),
        'humidity': np.random.uniform(30, 90, n_points),
        'pressure': np.random.uniform(1000, 1100, n_points),
        
        # ข้อมูลที่มี NaN บางส่วน
        'data_with_nulls': [i if i % 10 != 0 else np.nan for i in range(n_points)],
        
        # ข้อมูลที่มีค่าสูงมาก
        'large_values': np.random.uniform(1e6, 1e7, n_points),
        
        # ข้อมูลที่มีค่าต่ำมาก
        'small_values': np.random.uniform(1e-6, 1e-5, n_points),
    }
    
    df = pd.DataFrame(data)
    
    # บันทึกไฟล์ทดสอบ
    test_file = "test_plot_data.csv"
    df.to_csv(test_file, index=False)
    
    print(f"สร้างไฟล์ทดสอบการพล็อตเสร็จสิ้น: {test_file}")
    print(f"จำนวนแถว: {len(df):,}")
    print(f"จำนวนคอลัมน์: {len(df.columns)}")
    print("\nข้อมูลตัวอย่าง:")
    print(df.head())
    
    # แสดงข้อมูลประเภทของแต่ละคอลัมน์
    print("\nประเภทข้อมูลของแต่ละคอลัมน์:")
    for col in df.columns:
        print(f"• {col}: {df[col].dtype}")
    
    return test_file, df

def create_simple_test_data():
    """สร้างข้อมูลทดสอบแบบง่าย"""
    
    # สร้างข้อมูลทดสอบแบบง่าย
    data = {
        'x': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        'y': [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
        'y2': [1, 4, 9, 16, 25, 36, 49, 64, 81, 100],
        'y3': [1, 1, 2, 3, 5, 8, 13, 21, 34, 55],
    }
    
    df = pd.DataFrame(data)
    
    # บันทึกไฟล์ทดสอบ
    test_file = "test_simple_plot.csv"
    df.to_csv(test_file, index=False)
    
    print(f"\nสร้างไฟล์ทดสอบแบบง่ายเสร็จสิ้น: {test_file}")
    print(f"จำนวนแถว: {len(df)}")
    print(f"จำนวนคอลัมน์: {len(df.columns)}")
    print("\nข้อมูลตัวอย่าง:")
    print(df)
    
    return test_file, df

def test_prepare_plot_data_filters_nan_pairs_without_gui():
    helpers = _plot_helpers()

    x_values = [0, 1, np.nan, 3, 4]
    y_values = [10.0, np.nan, 30.0, 40.0, float("inf")]

    x_prepared, y_prepared, x_is_datetime = helpers.prepare_plot_data(x_values, y_values)

    assert x_is_datetime is False
    assert x_prepared == [0, 3]
    assert y_prepared == [10.0, 40.0]


def test_reset_numeric_axis_clears_date_axis_state_without_gui():
    helpers = _plot_helpers()
    import matplotlib.ticker as mticker
    from matplotlib.figure import Figure

    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([datetime(2024, 1, 1), datetime(2024, 1, 2)], [1, 2])

    assert helpers.axis_uses_dates(ax.xaxis)

    x_prepared, y_prepared, x_is_datetime = helpers.prepare_plot_data([1, 2, 3], [10, 20, 30])
    ax.plot(x_prepared, y_prepared)
    ax.relim()
    ax.autoscale_view()
    if not x_is_datetime and helpers.axis_uses_dates(ax.xaxis):
        helpers.reset_numeric_axis(ax)

    assert x_is_datetime is False
    assert not helpers.axis_uses_dates(ax.xaxis)
    assert ax.xaxis.get_converter() is None
    assert isinstance(ax.xaxis.get_major_locator(), mticker.AutoLocator)
    assert isinstance(ax.xaxis.get_major_formatter(), mticker.ScalarFormatter)


def create_instructions():
    """สร้างคำแนะนำการทดสอบ"""
    instructions = """
=== คำแนะนำการทดสอบการพล็อตกราฟใน SciPlotter ===

1. เปิดไฟล์ทดสอบ:
   - test_plot_data.csv (ข้อมูลทดสอบครบถ้วน)
   - test_simple_plot.csv (ข้อมูลทดสอบแบบง่าย)

2. ทดสอบการพล็อตกราฟ:
   - กดปุ่ม "โหลดคอลัมน์จากข้อมูล"
   - เลือกคอลัมน์ X และ Y
   - กดปุ่ม "Line Plot" หรือ "Scatter Plot"

3. ตรวจสอบ Debug Messages:
   - ดู console output เพื่อดู debug messages
   - ตรวจสอบว่าข้อมูลถูกโหลดและพล็อตได้หรือไม่

4. ทดสอบกรณีต่างๆ:
   - ข้อมูลเวลา vs ข้อมูลตัวเลข
   - ข้อมูลตัวเลข vs ข้อมูลตัวเลข
   - ข้อมูลที่มี NaN
   - ข้อมูลที่มีค่าสูง/ต่ำมาก

=== ตัวอย่างการทดสอบ ===

กรณีที่ 1: ข้อมูลง่าย
- X: x (int64)
- Y: y (int64)
- ผลลัพธ์: ✅ ควรพล็อตได้

กรณีที่ 2: ข้อมูลเวลา
- X: time (datetime64[ns])
- Y: temperature (float64)
- ผลลัพธ์: ✅ ควรพล็อตได้

กรณีที่ 3: ข้อมูลสตริง
- X: x_strings (object)
- Y: y_strings (object)
- ผลลัพธ์: ✅ ควรพล็อตได้ (แปลงเป็นตัวเลขอัตโนมัติ)

กรณีที่ 4: ข้อมูลที่มี NaN
- X: x_values (float64)
- Y: data_with_nulls (float64)
- ผลลัพธ์: ✅ ควรพล็อตได้ (กรอง NaN อัตโนมัติ)

=== Debug Information ===
เมื่อพล็อตกราฟ โปรแกรมจะแสดง debug messages:
- ข้อมูลที่ได้รับ
- ขั้นตอนการพล็อต
- การเรียก draw()
- ผลลัพธ์การพล็อต

=== การแก้ไขปัญหา ===
หากกราฟไม่ขึ้น:
1. ตรวจสอบ console output
2. ดู debug messages
3. ตรวจสอบว่าข้อมูลถูกต้อง
4. ลองใช้ข้อมูลทดสอบแบบง่ายก่อน
"""
    
    print(instructions)
    
    # บันทึกคำแนะนำลงไฟล์
    with open("PLOT_TESTING_GUIDE.md", "w", encoding="utf-8") as f:
        f.write(instructions)
    
    print("คำแนะนำถูกบันทึกลงไฟล์: PLOT_TESTING_GUIDE.md")

if __name__ == "__main__":
    print("=== ทดสอบการพล็อตกราฟใน SciPlotter ===")
    
    # สร้างข้อมูลทดสอบ
    test_file, test_df = create_plot_test_data()
    simple_file, simple_df = create_simple_test_data()
    
    # สร้างคำแนะนำ
    create_instructions()
    
    print(f"\nไฟล์ทดสอบที่สร้าง:")
    print(f"1. {test_file} - ข้อมูลทดสอบครบถ้วน")
    print(f"2. {simple_file} - ข้อมูลทดสอบแบบง่าย")
    print(f"3. PLOT_TESTING_GUIDE.md - คำแนะนำการทดสอบ")
    
    print(f"\nคุณสามารถทดสอบในโปรแกรม SciPlotter ได้โดย:")
    print(f"1. เปิดไฟล์ {simple_file} (เริ่มจากข้อมูลง่าย)")
    print(f"2. กด 'โหลดคอลัมน์'")
    print(f"3. เลือก X: x, Y: y")
    print(f"4. กด 'Line Plot'")
    print(f"5. ตรวจสอบ console output เพื่อดู debug messages")
    print(f"6. หากกราฟไม่ขึ้น ให้ดู debug messages เพื่อหาสาเหตุ")
