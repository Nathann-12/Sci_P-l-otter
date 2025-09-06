
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
