#!/usr/bin/env python3
"""
ทดสอบการจัดการข้อมูลเวลา (datetime) ใน SciPlotter
สร้างไฟล์ CSV ที่มีข้อมูลเวลาหลากหลายรูปแบบเพื่อทดสอบ
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

def create_datetime_test_data():
    """สร้างข้อมูลทดสอบที่มีข้อมูลเวลาหลากหลายรูปแบบ"""
    
    # สร้างข้อมูลทดสอบ
    data = {
        # ข้อมูลเวลาในรูปแบบ datetime
        'datetime_good': pd.date_range('2023-01-01', periods=1000, freq='1min'),
        
        # ข้อมูลเวลาในรูปแบบสตริง
        'datetime_strings': [f"2023-01-01 {i//60:02d}:{i%60:02d}:00" for i in range(1000)],
        
        # ข้อมูลเวลาในรูปแบบ Unix timestamp
        'unix_timestamp': [1672531200 + i*60 for i in range(1000)],  # Unix timestamp
        
        # ข้อมูลเวลาในรูปแบบ epoch (milliseconds)
        'epoch_ms': [1672531200000 + i*60000 for i in range(1000)],  # milliseconds
        
        # ข้อมูลเวลาในรูปแบบที่หลากหลาย
        'mixed_datetime': [
            f"2023-01-01 {i//60:02d}:{i%60:02d}:00" if i % 2 == 0 
            else f"01/01/2023 {i//60:02d}:{i%60:02d}" 
            for i in range(1000)
        ],
        
        # ข้อมูลตัวเลขปกติ
        'numeric_data': np.random.randn(1000) * 100,
        
        # ข้อมูลตัวเลขในรูปสตริง
        'numeric_strings': [str(i) for i in range(1000)],
        
        # ข้อมูลข้อความ
        'text_data': [f"text_{i}" for i in range(1000)],
        
        # ข้อมูลผสม
        'mixed_data': [f"{i}.5" if i % 2 == 0 else "invalid" for i in range(1000)],
    }
    
    df = pd.DataFrame(data)
    
    # บันทึกไฟล์ทดสอบ
    test_file = "test_datetime_validation.csv"
    df.to_csv(test_file, index=False)
    
    print(f"สร้างไฟล์ทดสอบข้อมูลเวลาเสร็จสิ้น: {test_file}")
    print(f"จำนวนแถว: {len(df):,}")
    print(f"จำนวนคอลัมน์: {len(df.columns)}")
    print("\nข้อมูลตัวอย่าง:")
    print(df.head())
    
    # แสดงข้อมูลประเภทของแต่ละคอลัมน์
    print("\nประเภทข้อมูลของแต่ละคอลัมน์:")
    for col in df.columns:
        print(f"• {col}: {df[col].dtype}")
    
    return test_file, df

def create_real_world_datetime_data():
    """สร้างข้อมูลเวลาที่คล้ายกับข้อมูลจริง"""
    
    # สร้างข้อมูลที่คล้ายกับข้อมูลจริง
    real_data = {
        # เวลาหลัก
        'timestamp': pd.date_range('2023-01-01', periods=5000, freq='1s'),
        
        # เวลาในรูปแบบอื่น
        'epoch': [1672531200 + i for i in range(5000)],  # Unix timestamp
        'datetime_string': [f"2023-01-01 {i//3600:02d}:{(i%3600)//60:02d}:{i%60:02d}" for i in range(5000)],
        
        # ข้อมูลตัวเลข
        'temperature': np.random.normal(25, 5, 5000),
        'humidity': np.random.uniform(30, 90, 5000),
        'pressure': np.random.uniform(1000, 1100, 5000),
        
        # ข้อมูลอื่นๆ
        'status': ['OK' if i % 10 != 0 else 'ERROR' for i in range(5000)],
        'value_with_nulls': [i if i % 100 != 0 else np.nan for i in range(5000)],
    }
    
    df_real = pd.DataFrame(real_data)
    
    # บันทึกไฟล์
    real_file = "test_real_datetime_data.csv"
    df_real.to_csv(real_file, index=False)
    
    print(f"\nสร้างไฟล์ข้อมูลเวลาจริงเสร็จสิ้น: {real_file}")
    print(f"จำนวนแถว: {len(df_real):,}")
    print(f"จำนวนคอลัมน์: {len(df_real.columns)}")
    
    # แสดงข้อมูลประเภทของแต่ละคอลัมน์
    print("\nประเภทข้อมูลของแต่ละคอลัมน์:")
    for col in df_real.columns:
        print(f"• {col}: {df_real[col].dtype}")
    
    return real_file, df_real

def test_datetime_conversion():
    """ทดสอบการแปลงข้อมูลเวลา"""
    pytest.skip("Legacy data-generator smoke test writes files; regression coverage below asserts datetime preparation behavior.")
    print("\n=== ทดสอบการแปลงข้อมูลเวลา ===")
    
    # สร้างข้อมูลทดสอบ
    test_file, df = create_datetime_test_data()
    
    # ทดสอบการแปลงเป็น datetime
    datetime_columns = ['datetime_strings', 'unix_timestamp', 'epoch_ms', 'mixed_datetime']
    
    for col in datetime_columns:
        if col in df.columns:
            try:
                # ลองแปลงเป็น datetime
                converted = pd.to_datetime(df[col], errors="coerce")
                valid_count = converted.notna().sum()
                total_count = len(df[col])
                
                print(f"✅ {col}: แปลงได้ {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)")
                
                if valid_count > 0:
                    print(f"   ตัวอย่าง: {converted.iloc[0]} -> {converted.iloc[0]}")
                    
            except Exception as e:
                print(f"❌ {col}: ไม่สามารถแปลงได้ - {e}")

def test_prepare_plot_data_filters_nat_and_invalid_datetime_strings():
    helpers = _plot_helpers()

    x_values = [
        "2024-01-01 00:00:00",
        "not a datetime",
        pd.NaT,
        "2024-01-01 00:03:00",
        "2024-01-01 00:04:00",
    ]
    y_values = [10.0, 20.0, 30.0, np.nan, 50.0]

    x_prepared, y_prepared, x_is_datetime = helpers.prepare_plot_data(x_values, y_values)

    assert x_is_datetime is True
    assert y_prepared == [10.0, 50.0]

    import matplotlib.dates as mdates

    prepared_dates = mdates.num2date(x_prepared)
    assert [dt.replace(tzinfo=None) for dt in prepared_dates] == [
        datetime(2024, 1, 1, 0, 0),
        datetime(2024, 1, 1, 0, 4),
    ]


def test_clamp_date_limits_rejects_out_of_range_datetime_bounds():
    helpers = _plot_helpers()
    import matplotlib.dates as mdates
    from matplotlib.dates import AutoDateLocator
    from matplotlib.figure import Figure

    fig = Figure()
    ax = fig.add_subplot(111)
    ax.xaxis.set_major_locator(AutoDateLocator())
    ax.set_xlim(
        mdates.date2num(datetime(1, 1, 1)) - 1000,
        mdates.date2num(datetime(9999, 12, 31)) + 1000,
    )

    helpers.clamp_date_limits(ax)

    lo, hi = ax.get_xlim()
    assert lo >= mdates.date2num(datetime(1, 1, 1))
    assert hi <= mdates.date2num(datetime(9999, 12, 31))
    assert lo < hi


def create_instructions():
    """สร้างคำแนะนำการใช้งาน"""
    instructions = """
=== คำแนะนำการทดสอบข้อมูลเวลาใน SciPlotter ===

1. เปิดไฟล์ทดสอบ:
   - test_datetime_validation.csv (ข้อมูลเวลาหลากหลายรูปแบบ)
   - test_real_datetime_data.csv (ข้อมูลเวลาจริง)

2. ทดสอบการโหลดคอลัมน์:
   - กดปุ่ม "โหลดคอลัมน์จากข้อมูล"
   - ดูว่าคอลัมน์ไหนแสดงข้อความ "เป็นข้อมูลเวลา (datetime) - ใช้ได้สำหรับแกน X"

3. ทดสอบการพล็อต:
   - เลือกคอลัมน์เวลาเป็นแกน X (เช่น timestamp, datetime_strings)
   - เลือกคอลัมน์ตัวเลขเป็นแกน Y (เช่น temperature, humidity)
   - กดปุ่ม "Line Plot" หรือ "Scatter Plot"

4. ทดสอบข้อผิดพลาด:
   - ลองเลือกคอลัมน์ที่ไม่เหมาะสม
   - ดูข้อความแจ้งเตือนที่ละเอียดขึ้น

5. ใช้ฟีเจอร์ "กำหนดชนิดคอลัมน์":
   - หากคอลัมน์เวลาไม่ถูกจดจำ
   - เลือกคอลัมน์และกำหนดเป็น "Datetime"

=== ตัวอย่างการใช้งาน ===

กรณีที่ 1: ข้อมูลเวลาเป็น datetime
- X: timestamp (datetime)
- Y: temperature (float)
- ผลลัพธ์: ✅ ใช้ได้

กรณีที่ 2: ข้อมูลเวลาเป็นสตริง
- X: datetime_strings (object)
- Y: temperature (float)
- ผลลัพธ์: ✅ ใช้ได้ (โปรแกรมจะแปลงอัตโนมัติ)

กรณีที่ 3: ข้อมูลเวลาไม่ถูกต้อง
- X: text_data (object)
- Y: temperature (float)
- ผลลัพธ์: ❌ ข้อความแจ้งเตือนจะแนะนำให้ใช้ "กำหนดชนิดคอลัมน์"

=== Debug Information ===
เมื่อเกิดปัญหา โปรแกรมจะแสดง debug messages ใน console:
- ประเภทข้อมูลของแต่ละคอลัมน์
- จำนวนข้อมูลที่แปลงได้/ไม่ได้
- ขั้นตอนการประมวลผลข้อมูล
"""
    
    print(instructions)
    
    # บันทึกคำแนะนำลงไฟล์
    with open("DATETIME_TESTING_GUIDE.md", "w", encoding="utf-8") as f:
        f.write(instructions)
    
    print("คำแนะนำถูกบันทึกลงไฟล์: DATETIME_TESTING_GUIDE.md")

if __name__ == "__main__":
    print("=== ทดสอบการจัดการข้อมูลเวลาใน SciPlotter ===")
    
    # สร้างข้อมูลทดสอบ
    test_file, test_df = create_datetime_test_data()
    real_file, real_df = create_real_world_datetime_data()
    
    # ทดสอบการแปลงข้อมูลเวลา
    test_datetime_conversion()
    
    # สร้างคำแนะนำ
    create_instructions()
    
    print(f"\nไฟล์ทดสอบที่สร้าง:")
    print(f"1. {test_file} - ข้อมูลเวลาหลากหลายรูปแบบ")
    print(f"2. {real_file} - ข้อมูลเวลาจริง")
    print(f"3. DATETIME_TESTING_GUIDE.md - คำแนะนำการทดสอบ")
    
    print(f"\nคุณสามารถทดสอบในโปรแกรม SciPlotter ได้โดย:")
    print(f"1. เปิดไฟล์ {test_file}")
    print(f"2. กด 'โหลดคอลัมน์'")
    print(f"3. ลองเลือกคอลัมน์ต่างๆ เพื่อดูข้อความแจ้งเตือนที่ละเอียดขึ้น")
    print(f"4. ตรวจสอบ console output เพื่อดู debug messages")
