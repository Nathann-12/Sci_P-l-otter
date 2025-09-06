#!/usr/bin/env python3
"""
ทดสอบฟีเจอร์ Create Derived Column
สร้างข้อมูลตัวอย่างและทดสอบนิพจน์ต่างๆ
"""

import sys
import pandas as pd
import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox
from dialogs import DerivedColumnDialog

def create_sample_data():
    """สร้างข้อมูลตัวอย่างสำหรับทดสอบ"""
    np.random.seed(42)  # เพื่อให้ผลลัพธ์สม่ำเสมอ
    
    # สร้างข้อมูลตัวอย่าง
    n_points = 100
    data = {
        'Bx': np.random.normal(0, 1, n_points),  # สนามแม่เหล็ก X
        'By': np.random.normal(0, 1, n_points),  # สนามแม่เหล็ก Y  
        'Bz': np.random.normal(0, 1, n_points),  # สนามแม่เหล็ก Z
        'Speed': np.random.uniform(10, 50, n_points),  # ความเร็ว m/s
        'Temperature': np.random.uniform(20, 30, n_points),  # อุณหภูมิ °C
        'Pressure': np.random.uniform(1000, 1100, n_points),  # ความดัน Pa
        'Mag Field': np.random.uniform(0.1, 1.0, n_points),  # ชื่อที่มีช่องว่าง
        'Signal': np.random.normal(0, 0.5, n_points),  # สัญญาณ
        'Count': np.random.poisson(5, n_points),  # จำนวนนับ
    }
    
    df = pd.DataFrame(data)
    return df

def test_expressions():
    """ทดสอบนิพจน์ตัวอย่าง"""
    expressions = [
        # นิพจน์พื้นฐาน
        "`Bx` * `By`",
        "`Bx` * `By` * `Bz`",
        
        # คำนวณขนาดเวกเตอร์
        "sqrt(`Bx`**2 + `By`**2 + `Bz`**2)",
        
        # แปลงหน่วย
        "`Speed` * 3.6",  # m/s เป็น km/h
        
        # ฟังก์ชันคณิตศาสตร์
        "abs(`Signal`)",
        "log(`Count` + 1)",
        "sin(`Bx`)",
        "cos(`By`)",
        
        # ฟังก์ชันสถิติ
        "maximum(`Bx`, `By`)",
        "minimum(`Temperature`, `Pressure` / 100)",
        
        # นิพจน์ซับซ้อน
        "sqrt(`Bx`**2 + `By`**2) * `Speed`",
        "`Temperature` * `Pressure` / 1000",
        
        # ทดสอบชื่อคอลัมน์ที่มีช่องว่าง
        "`Mag Field` * 2",
    ]
    
    return expressions

def run_test():
    """รันการทดสอบ"""
    print("🧪 ทดสอบฟีเจอร์ Create Derived Column")
    print("=" * 50)
    
    # สร้างข้อมูลตัวอย่าง
    df = create_sample_data()
    print(f"📊 สร้างข้อมูลตัวอย่าง: {len(df)} แถว, {len(df.columns)} คอลัมน์")
    print(f"คอลัมน์: {list(df.columns)}")
    print()
    
    # ทดสอบนิพจน์ต่างๆ
    expressions = test_expressions()
    print("🔍 ทดสอบนิพจน์ตัวอย่าง:")
    
    from processors import evaluate_expression
    
    for i, expr in enumerate(expressions, 1):
        try:
            result = evaluate_expression(df, expr)
            print(f"{i:2d}. {expr}")
            print(f"    ✅ สำเร็จ: {len(result)} ค่า, เฉลี่ย = {result.mean():.4f}")
        except Exception as e:
            print(f"{i:2d}. {expr}")
            print(f"    ❌ ผิดพลาด: {str(e)}")
        print()
    
    print("🎯 การทดสอบเสร็จสิ้น!")
    return df

def run_gui_test():
    """ทดสอบ GUI"""
    app = QApplication(sys.argv)
    
    # สร้างข้อมูลตัวอย่าง
    df = create_sample_data()
    
    # เปิด dialog
    dialog = DerivedColumnDialog(None, df)
    
    # แสดงข้อความแนะนำ
    QMessageBox.information(
        dialog, "ทดสอบฟีเจอร์", 
        "ทดสอบฟีเจอร์ Create Derived Column\n\n"
        "ลองใช้นิพจน์เหล่านี้:\n"
        "• sqrt(`Bx`**2 + `By`**2 + `Bz`**2)\n"
        "• `Speed` * 3.6\n"
        "• abs(`Signal`)\n"
        "• `Mag Field` * 2"
    )
    
    # แสดง dialog
    result = dialog.exec()
    
    if result == dialog.Accepted:
        print("✅ Dialog ปิดด้วย Apply")
    else:
        print("❌ Dialog ปิดด้วย Cancel")
    
    return result

if __name__ == "__main__":
    print("🚀 เริ่มทดสอบฟีเจอร์ Create Derived Column")
    print()
    
    # ทดสอบฟังก์ชันประเมินนิพจน์
    df = run_test()
    
    # ถามว่าต้องการทดสอบ GUI หรือไม่
    response = input("\nต้องการทดสอบ GUI หรือไม่? (y/n): ").lower().strip()
    
    if response in ['y', 'yes', 'ใช่']:
        print("\n🖥️  เริ่มทดสอบ GUI...")
        run_gui_test()
    else:
        print("\n✅ การทดสอบเสร็จสิ้น (เฉพาะฟังก์ชัน)")
    
    print("\n🎉 ทดสอบเสร็จสิ้น!")
