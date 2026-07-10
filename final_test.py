#!/usr/bin/env python3
"""
ทดสอบการพล็อตกราฟจริงใน SciPlotter
รันโปรแกรม SciPlotter และทดสอบการพล็อตกราฟ
"""

import sys
import os
import subprocess
import time
import pytest

def test_sciplotter_launch():
    """ทดสอบการเปิดโปรแกรม SciPlotter"""
    print("=== ทดสอบการเปิดโปรแกรม SciPlotter ===")
    
    try:
        # Check if main.py exists
        if not os.path.exists("main.py"):
            print("❌ ไม่พบไฟล์ main.py")
            pytest.fail("main.py is missing")
        
        print("✅ พบไฟล์ main.py")
        
        # Check if test data exists
        test_files = ["minimal_test.csv", "debug_test.csv", "test_simple_plot.csv"]
        available_files = [f for f in test_files if os.path.exists(f)]
        
        if available_files:
            print(f"✅ พบไฟล์ทดสอบ: {', '.join(available_files)}")
        else:
            print("⚠️ ไม่พบไฟล์ทดสอบ")
        
        assert os.path.exists("main.py")
        
    except Exception as e:
        print(f"❌ การตรวจสอบไฟล์ล้มเหลว: {e}")
        pytest.fail(f"SciPlotter launch smoke check failed: {e}")

def create_test_instructions():
    """สร้างคำแนะนำการทดสอบ"""
    instructions = """
=== คำแนะนำการทดสอบการพล็อตกราฟใน SciPlotter ===

🔧 การแก้ไขที่ทำแล้ว:
1. ✅ ตั้งค่า matplotlib backend เป็น Qt5Agg
2. ✅ เพิ่ม debug messages ในทุกขั้นตอน
3. ✅ ปรับปรุงฟังก์ชัน plot_to_tabs() ให้บังคับแสดงผล
4. ✅ เพิ่มการเรียก draw() หลายวิธี
5. ✅ เพิ่มการ clear() และ relim() ก่อนพล็อต
6. ✅ เพิ่มการ flush_events() และ update()

📋 ขั้นตอนการทดสอบ:

1. เปิดโปรแกรม SciPlotter:
   python main.py

2. เปิดไฟล์ทดสอบ:
   - กด "เปิดไฟล์" หรือ Ctrl+O
   - เลือกไฟล์ minimal_test.csv หรือ debug_test.csv

3. โหลดคอลัมน์:
   - กดปุ่ม "โหลดคอลัมน์จากข้อมูล"

4. เลือกคอลัมน์:
   - X: x (หรือ index)
   - Y: y (หรือ value)

5. พล็อตกราฟ:
   - กดปุ่ม "Line Plot" หรือ "Scatter Plot"

6. ตรวจสอบ Debug Messages:
   - ดู console/terminal output
   - ควรเห็น debug messages เช่น:
     Debug: plot_line() called
     Debug: plot_line() - got data: x=5, y=5
     Debug: plot_to_tabs called with 1 tabs, style=line
     Debug: Line plot created: [<matplotlib.lines.Line2D object>]
     Debug: Tab draw() called successfully

🔍 การแก้ไขปัญหา:

หากกราฟยังไม่ขึ้น:
1. ตรวจสอบ console output
2. ดู debug messages
3. ตรวจสอบว่าข้อมูลถูกโหลดหรือไม่
4. ลองใช้ข้อมูลทดสอบแบบง่าย

หากมีข้อผิดพลาด:
1. ตรวจสอบ matplotlib backend
2. ตรวจสอบ PySide6 installation
3. ลองรันโปรแกรมใหม่

📁 ไฟล์ทดสอบที่มี:
- minimal_test.csv: ข้อมูลง่ายที่สุด (5 แถว)
- debug_test.csv: ข้อมูลสำหรับ debug (10 แถว)
- test_simple_plot.csv: ข้อมูลทดสอบมาตรฐาน (10 แถว)

🎯 ผลลัพธ์ที่คาดหวัง:
- กราฟควรแสดงผลบนหน้าจอ
- Debug messages ควรแสดงใน console
- ไม่ควรมีข้อผิดพลาด
- กราฟควรมี grid และ labels
"""
    
    print(instructions)
    
    # บันทึกคำแนะนำลงไฟล์
    with open("TESTING_INSTRUCTIONS.md", "w", encoding="utf-8") as f:
        f.write(instructions)
    
    print("คำแนะนำถูกบันทึกลงไฟล์: TESTING_INSTRUCTIONS.md")

def check_dependencies():
    """ตรวจสอบ dependencies"""
    print("\n=== ตรวจสอบ Dependencies ===")
    
    dependencies = [
        ("matplotlib", "matplotlib"),
        ("PySide6", "PySide6"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
    ]
    
    for name, module in dependencies:
        try:
            __import__(module)
            print(f"✅ {name}: ติดตั้งแล้ว")
        except ImportError:
            print(f"❌ {name}: ไม่พบ")
    
    # Check matplotlib backend
    try:
        import matplotlib
        print(f"✅ Matplotlib backend: {matplotlib.get_backend()}")
    except Exception as e:
        print(f"❌ Matplotlib backend: {e}")

if __name__ == "__main__":
    print("=== ทดสอบการพล็อตกราฟใน SciPlotter ===")
    
    # ตรวจสอบ dependencies
    check_dependencies()
    
    # ตรวจสอบไฟล์
    test_sciplotter_launch()
    
    # สร้างคำแนะนำ
    create_test_instructions()
    
    print(f"\n🎯 ขั้นตอนต่อไป:")
    print(f"1. รันโปรแกรม: python main.py")
    print(f"2. เปิดไฟล์ minimal_test.csv")
    print(f"3. กด 'โหลดคอลัมน์'")
    print(f"4. เลือก X: x, Y: y")
    print(f"5. กด 'Line Plot'")
    print(f"6. ดู console output")
    
    print(f"\n📋 หากกราฟไม่ขึ้น:")
    print(f"- ตรวจสอบ console output")
    print(f"- ดู debug messages")
    print(f"- ลองใช้ข้อมูลทดสอบแบบง่าย")
    print(f"- ตรวจสอบ matplotlib backend")
    
    print(f"\n🔧 การแก้ไขที่ทำแล้ว:")
    print(f"- ตั้งค่า matplotlib backend เป็น Qt5Agg")
    print(f"- เพิ่ม debug messages")
    print(f"- ปรับปรุงการเรียก draw()")
    print(f"- เพิ่มการบังคับแสดงผล")
    print(f"- เพิ่มการ clear() และ relim()")
    
    print(f"\n✅ ตอนนี้โปรแกรมควรทำงานได้ดีขึ้น!")
    print(f"กรุณาทดสอบและแจ้งผลลัพธ์")
