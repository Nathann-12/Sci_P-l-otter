#!/usr/bin/env python3
"""
ทดสอบการแก้ไขปัญหาการตรวจสอบข้อมูลตัวเลข
สร้างไฟล์ CSV ที่มีข้อมูลหลากหลายประเภทเพื่อทดสอบ
"""

import pandas as pd
import numpy as np
import os
import pytest
from pathlib import Path


def _plot_helpers():
    import sys

    sys.dont_write_bytecode = True
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from core import plot_data
    return plot_data

def create_test_data():
    """สร้างข้อมูลทดสอบที่มีข้อมูลหลากหลายประเภท"""
    
    # สร้างข้อมูลทดสอบ
    data = {
        'time': pd.date_range('2023-01-01', periods=1000, freq='1min'),
        'numeric_good': np.random.randn(1000) * 100,  # ข้อมูลตัวเลขดี
        'numeric_mixed': [f"{i}.5" if i % 2 == 0 else "invalid" for i in range(1000)],  # ข้อมูลผสม
        'numeric_strings': [str(i) for i in range(1000)],  # ตัวเลขในรูปสตริง
        'text_data': [f"text_{i}" for i in range(1000)],  # ข้อมูลข้อความ
        'empty_column': [np.nan] * 1000,  # คอลัมน์ว่าง
        'partial_numeric': [i if i % 3 == 0 else np.nan for i in range(1000)],  # ข้อมูลบางส่วนเป็นตัวเลข
        'boolean_data': [i % 2 == 0 for i in range(1000)],  # ข้อมูล boolean
    }
    
    df = pd.DataFrame(data)
    
    # บันทึกไฟล์ทดสอบ
    test_file = "test_numeric_validation.csv"
    df.to_csv(test_file, index=False)
    
    print(f"สร้างไฟล์ทดสอบเสร็จสิ้น: {test_file}")
    print(f"จำนวนแถว: {len(df):,}")
    print(f"จำนวนคอลัมน์: {len(df.columns)}")
    print("\nข้อมูลตัวอย่าง:")
    print(df.head())
    
    return test_file, df

def test_column_validation():
    pytest.skip("Legacy MainWindow smoke test is not headless-safe; helper-level regression tests cover validation behavior.")
    """ทดสอบการตรวจสอบคอลัมน์"""
    try:
        # Import ฟังก์ชันที่แก้ไขแล้ว
        from main import MainWindow
        from PySide6.QtWidgets import QApplication
        
        # สร้างข้อมูลทดสอบ
        test_file, df = create_test_data()
        
        # สร้างแอปพลิเคชัน Qt (จำเป็นสำหรับ MainWindow)
        app = QApplication([])
        
        # สร้าง MainWindow instance
        main_window = MainWindow()
        
        # โหลดข้อมูลทดสอบ
        main_window._df = df
        
        print("\n=== ทดสอบการตรวจสอบคอลัมน์ ===")
        
        # ทดสอบคอลัมน์ต่างๆ
        test_columns = [
            'numeric_good',
            'numeric_mixed', 
            'numeric_strings',
            'text_data',
            'empty_column',
            'partial_numeric',
            'boolean_data'
        ]
        
        for col in test_columns:
            if col in df.columns:
                is_valid, message = main_window._check_column_numeric(col)
                status = "✅ ใช้ได้" if is_valid else "❌ ไม่ใช้ได้"
                print(f"{status} {col}: {message}")
        
        print("\n=== ทดสอบการพล็อตข้อมูล ===")
        
        # ทดสอบการพล็อตข้อมูลที่ดี
        print("ทดสอบพล็อตข้อมูลที่ดี...")
        x, y = main_window._get_xy()
        if x is not None and y is not None:
            print(f"✅ พล็อตสำเร็จ: X={len(x)}, Y={len(y)}")
        else:
            print("❌ พล็อตไม่สำเร็จ")
        
        # ปิดแอปพลิเคชัน
        app.quit()
        
        print("\n✅ การทดสอบเสร็จสิ้น!")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการทดสอบ: {e}")
        import traceback
        traceback.print_exc()

def test_prepare_plot_data_keeps_numeric_strings_off_datetime_path():
    helpers = _plot_helpers()

    x_values = ["1", "2", "3", "4"]
    y_values = [10.0, 20.0, 30.0, 40.0]

    x_prepared, y_prepared, x_is_datetime = helpers.prepare_plot_data(x_values, y_values)

    assert x_is_datetime is False
    assert x_prepared == x_values
    assert y_prepared == y_values


def test_mostly_numeric_string_axis_is_not_parsed_as_datetime():
    helpers = _plot_helpers()

    x_values = ["1", "2", "3", "4", "sample"]
    y_values = [1, 2, 3, 4, 5]

    x_prepared, y_prepared, x_is_datetime = helpers.prepare_plot_data(x_values, y_values)

    assert x_is_datetime is False
    assert x_prepared == x_values
    assert y_prepared == y_values


def test_with_real_data():
    """ทดสอบกับข้อมูลจริง"""
    pytest.skip("Legacy data-generator smoke test writes files; regression coverage above asserts numeric preparation behavior.")
    print("\n=== ทดสอบกับข้อมูลจริง ===")
    
    # สร้างข้อมูลที่คล้ายกับข้อมูลจริง
    real_data = {
        'timestamp': pd.date_range('2023-01-01', periods=5000, freq='1s'),
        'temperature': np.random.normal(25, 5, 5000),
        'humidity': np.random.uniform(30, 90, 5000),
        'pressure': np.random.uniform(1000, 1100, 5000),
        'status': ['OK' if i % 10 != 0 else 'ERROR' for i in range(5000)],
        'value_with_nulls': [i if i % 100 != 0 else np.nan for i in range(5000)],
    }
    
    df_real = pd.DataFrame(real_data)
    
    # บันทึกไฟล์
    real_file = "test_real_data.csv"
    df_real.to_csv(real_file, index=False)
    
    print(f"สร้างไฟล์ข้อมูลจริงเสร็จสิ้น: {real_file}")
    print(f"จำนวนแถว: {len(df_real):,}")
    print(f"จำนวนคอลัมน์: {len(df_real.columns)}")
    
    # แสดงสถิติข้อมูล
    print("\nสถิติข้อมูล:")
    print(df_real.describe())
    
    return real_file, df_real

if __name__ == "__main__":
    print("=== ทดสอบการแก้ไขปัญหาการตรวจสอบข้อมูลตัวเลข ===")
    
    # ทดสอบการสร้างข้อมูล
    test_file, test_df = create_test_data()
    real_file, real_df = test_with_real_data()
    
    print(f"\nไฟล์ทดสอบที่สร้าง:")
    print(f"1. {test_file} - ข้อมูลทดสอบหลากหลายประเภท")
    print(f"2. {real_file} - ข้อมูลจริง")
    
    print(f"\nคุณสามารถทดสอบในโปรแกรม SciPlotter ได้โดย:")
    print(f"1. เปิดไฟล์ {test_file}")
    print(f"2. กด 'โหลดคอลัมน์'")
    print(f"3. ลองเลือกคอลัมน์ต่างๆ เพื่อดูข้อความแจ้งเตือนที่ละเอียดขึ้น")
    print(f"4. ตรวจสอบ console output เพื่อดู debug messages")
