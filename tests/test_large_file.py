#!/usr/bin/env python3
"""
ทดสอบการอ่านไฟล์ขนาดใหญ่
สร้างไฟล์ CSV ขนาดใหญ่เพื่อทดสอบการทำงานของ chunking
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path

def create_large_test_file(filename="large_test.csv", rows=100000):
    """สร้างไฟล์ CSV ขนาดใหญ่สำหรับทดสอบ"""
    print(f"กำลังสร้างไฟล์ทดสอบ: {filename} ({rows:,} แถว)")
    
    # สร้างข้อมูลทดสอบ
    data = {
        'time': pd.date_range('2023-01-01', periods=rows, freq='1min'),
        'value1': np.random.randn(rows) * 100,
        'value2': np.random.randn(rows) * 50 + 1000,
        'value3': np.random.randn(rows) * 25 + 500,
        'category': np.random.choice(['A', 'B', 'C', 'D'], rows),
        'temperature': np.random.uniform(20, 30, rows),
        'pressure': np.random.uniform(1000, 1100, rows),
    }
    
    df = pd.DataFrame(data)
    
    # บันทึกไฟล์
    df.to_csv(filename, index=False)
    
    # ตรวจสอบขนาดไฟล์
    file_size = os.path.getsize(filename)
    print(f"สร้างไฟล์เสร็จสิ้น: {filename}")
    print(f"ขนาดไฟล์: {file_size / (1024*1024):.2f} MB")
    print(f"จำนวนแถว: {len(df):,}")
    print(f"จำนวนคอลัมน์: {len(df.columns)}")
    
    return filename

def test_file_reading():
    """ทดสอบการอ่านไฟล์ด้วยฟังก์ชันที่แก้ไขแล้ว"""
    try:
        # Import ฟังก์ชันที่แก้ไขแล้ว
        from file_io import read_csv
        from loaders import load_tabular
        
        # สร้างไฟล์ทดสอบขนาดเล็ก
        print("=== ทดสอบไฟล์ขนาดเล็ก ===")
        small_file = create_large_test_file("small_test.csv", 1000)
        
        # ทดสอบการอ่านด้วย file_io
        print("\n--- ทดสอบด้วย file_io.read_csv ---")
        df1, meta1 = read_csv(Path(small_file))
        print(f"ผลลัพธ์: {len(df1):,} แถว, {len(df1.columns)} คอลัมน์")
        print(f"Metadata: {meta1}")
        
        # ทดสอบการอ่านด้วย loaders
        print("\n--- ทดสอบด้วย loaders.load_tabular ---")
        df2, note2 = load_tabular(small_file)
        print(f"ผลลัพธ์: {len(df2):,} แถว, {len(df2.columns)} คอลัมน์")
        print(f"Note: {note2}")
        
        # สร้างไฟล์ทดสอบขนาดใหญ่
        print("\n=== ทดสอบไฟล์ขนาดใหญ่ ===")
        large_file = create_large_test_file("large_test.csv", 50000)
        
        # ทดสอบการอ่านไฟล์ใหญ่
        print("\n--- ทดสอบไฟล์ใหญ่ด้วย file_io.read_csv ---")
        df3, meta3 = read_csv(Path(large_file))
        print(f"ผลลัพธ์: {len(df3):,} แถว, {len(df3.columns)} คอลัมน์")
        print(f"Metadata: {meta3}")
        
        print("\n--- ทดสอบไฟล์ใหญ่ด้วย loaders.load_tabular ---")
        df4, note4 = load_tabular(large_file)
        print(f"ผลลัพธ์: {len(df4):,} แถว, {len(df4.columns)} คอลัมน์")
        print(f"Note: {note4}")
        
        print("\n✅ การทดสอบสำเร็จ!")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการทดสอบ: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_file_reading()
