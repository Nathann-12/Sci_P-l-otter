#!/usr/bin/env python3
"""
ทดสอบการพล็อตกราฟแบบง่าย
สร้างข้อมูลทดสอบที่แน่นอนว่าทำงานได้
"""

import pandas as pd
import numpy as np

def create_minimal_test_data():
    """สร้างข้อมูลทดสอบแบบง่ายที่สุด"""
    
    # สร้างข้อมูลทดสอบแบบง่าย
    data = {
        'x': [1, 2, 3, 4, 5],
        'y': [2, 4, 6, 8, 10],
    }
    
    df = pd.DataFrame(data)
    
    # บันทึกไฟล์ทดสอบ
    test_file = "minimal_test.csv"
    df.to_csv(test_file, index=False)
    
    print(f"สร้างไฟล์ทดสอบแบบง่ายที่สุด: {test_file}")
    print(f"ข้อมูล:")
    print(df)
    
    return test_file, df

def create_debug_test_data():
    """สร้างข้อมูลทดสอบสำหรับ debug"""
    
    # สร้างข้อมูลทดสอบที่มี debug information
    data = {
        'index': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        'value': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        'squared': [1.0, 4.0, 9.0, 16.0, 25.0, 36.0, 49.0, 64.0, 81.0, 100.0],
        'cubed': [1.0, 8.0, 27.0, 64.0, 125.0, 216.0, 343.0, 512.0, 729.0, 1000.0],
    }
    
    df = pd.DataFrame(data)
    
    # บันทึกไฟล์ทดสอบ
    test_file = "debug_test.csv"
    df.to_csv(test_file, index=False)
    
    print(f"สร้างไฟล์ทดสอบ debug: {test_file}")
    print(f"ข้อมูล:")
    print(df)
    
    return test_file, df

if __name__ == "__main__":
    print("=== สร้างข้อมูลทดสอบแบบง่าย ===")
    
    # สร้างข้อมูลทดสอบ
    minimal_file, minimal_df = create_minimal_test_data()
    debug_file, debug_df = create_debug_test_data()
    
    print(f"\nไฟล์ทดสอบที่สร้าง:")
    print(f"1. {minimal_file} - ข้อมูลทดสอบแบบง่ายที่สุด")
    print(f"2. {debug_file} - ข้อมูลทดสอบสำหรับ debug")
    
    print(f"\nคำแนะนำการทดสอบ:")
    print(f"1. เปิดไฟล์ {minimal_file}")
    print(f"2. กด 'โหลดคอลัมน์'")
    print(f"3. เลือก X: x, Y: y")
    print(f"4. กด 'Line Plot'")
    print(f"5. ดู console output")
    
    print(f"\nหากยังไม่ทำงาน:")
    print(f"1. ลองใช้ไฟล์ {debug_file}")
    print(f"2. เลือก X: index, Y: value")
    print(f"3. ดู debug messages ใน console")
