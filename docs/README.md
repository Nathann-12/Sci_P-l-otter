# SciPlotter - เครื่องมือวิเคราะห์และพล็อตข้อมูลทางวิทยาศาสตร์

![SciPlotter Logo](../assets/icons/Plot.png)

## ภาพรวม

SciPlotter เป็นแอปเดสก์ท็อปที่พัฒนาโดย Python, PySide6 และ Matplotlib สำหรับงานวิเคราะห์และนำเสนอข้อมูลเชิงวิทยาศาสตร์ รองรับไฟล์ข้อมูลทั่วไป (CSV, Excel, NetCDF, CDF) พร้อมเครื่องมือเตรียมข้อมูล การพล็อตกราฟ และโมดูลวิเคราะห์พิเศษในแอปเดียว

## ไฮไลต์ฟีเจอร์

### การพล็อตและการวิเคราะห์
- กราฟมาตรฐาน: Line, Scatter, Bar, Area, Box, Pie, Histogram, 3D Scatter พร้อมหน้าต่าง Chart Options ที่ปรับสไตล์และแกนได้ละเอียด
- Histogram dialog รุ่นใหม่: เลือกคอลัมน์เดียว, ปรับจำนวน bin หรือ bin strategy (auto, fd, scott ฯลฯ) และเลือกแสดง Normal fit ได้ทันที
- Spectrogram และ FFT Analysis สำหรับสัญญาณเวลา
- Peak Detection, Cross-Correlation, Multi-cursor และการวิเคราะห์ในช่วง (visible range) ผ่าน context menu

### การเตรียมและจัดการข้อมูล
- Derived Columns Builder (`Ctrl+D`) สำหรับสร้างคอลัมน์ด้วยสูตร NumPy/Pandas
- Processors สำหรับคำนวณสถิติพื้นฐาน, rolling, smoothing, unit conversion และ calibration
- ตัวเลือกจัดการข้อมูลในแต่ละกราฟ: กรอง NaN, sort ตามแกน X, downsample สูงสุด 200k จุด

### อินเทอร์เฟซและการใช้งาน
- Multi-tab canvas, Inspector panel และ Chart gallery ให้เลือกตัวอย่างพล็อตได้รวดเร็ว
- Annotation Tool (Text/Arrow/Shape/Callout) พร้อม Style Dock, undo/redo และบันทึก overlay เป็น JSON
- Context menu แบบคลิกขวา: ซูม/แพน, ตั้งค่าช่วงแกน, snapshot, copy figure, export visible CSV
- ธีมให้เลือก (Light, Dark, Dark Modern) หรือโหลด QSS เอง รวมถึงกำหนดฟอนต์และ Matplotlib overrides ผ่าน Settings dialog

### การนำเข้า/ส่งออก
- รองรับไฟล์ข้อมูล CSV, TSV, Excel (.xlsx), NetCDF, CDF และไฟล์ข้อความที่คั่นด้วยช่องว่างหรือแท็บ
- Export figure เป็น PNG/PDF, Copy to clipboard และสร้างรายงาน PDF พร้อมรูปและสรุปค่าทางสถิติ
- เก็บค่าตั้งต้นและธีมด้วย `config/` และไฟล์ JSON

## โครงสร้างโปรเจ็กต์ที่สำคัญ
- `main.py` – จุดเริ่มต้นของแอปและการจัดการหน้าต่างหลัก
- `dialogs/` – กล่องโต้ตอบสำหรับ Settings, Histogram, Spectrogram, Advanced Charts, Annotations ฯลฯ
- `assets/icons/` – โลโก้และไอคอน (รวม `Plot.png` ที่ใช้บน README)
- `styles/` – QSS ธีมและสคริปต์ปรับ Matplotlib
- `docs/` – เอกสารประกอบหัวข้อย่อย (เช่น Derived Column, Annotation Context Menu)

## การติดตั้ง (โคลนผ่าน Git)

1. ติดตั้ง Git และ Python 3.8 ขึ้นไปให้พร้อมใช้งาน
2. โคลนโปรเจ็กต์และเข้าไดเรกทอรี

```bash
git clone https://github.com/yourusername/SciPlotter.git
cd SciPlotter
```

3. (แนะนำ) สร้าง virtual environment แล้วติดตั้งไลบรารี

```bash
python -m venv .venv
.venv\Scripts\activate  # บน Windows
source .venv/bin/activate   # บน macOS / Linux
pip install -r requirements.txt
```

4. รันแอปพลิเคชัน

```bash
python main.py
```

> หมายเหตุ: ตรวจสอบให้แน่ใจว่าโฟลเดอร์ `assets/` ถูก commit/push ไปยังรีโมตก่อนให้ผู้อื่นโคลน เพื่อให้โลโก้และไอคอนแสดงถูกต้อง

## เริ่มต้นใช้งานอย่างรวดเร็ว
1. เปิดไฟล์ข้อมูลจากเมนู **File > Open** หรือปุ่มใน toolbar (`Ctrl+O`)
2. เลือกคอลัมน์ X/Y จาก Inspector แล้วพล็อตผ่านปุ่ม **Plot** หรือเมนู **Charts > Advanced** เพื่อเปิด Chart Options dialog
3. ใช้แท็บ **Analysis** สำหรับ Histogram, FFT, Spectrogram, Peak Detection หรือ Cross-Correlation ตามต้องการ
4. เพิ่ม Annotation เพื่ออธิบายจุดสำคัญ แล้วบันทึกหรือคัดลอกรูปไปใช้งานต่อ
5. ส่งออกกราฟหรือรายงานผ่านเมนู **Export**

## ฟีเจอร์เสริมและทิป
- `Ctrl+Shift+X` เปิด Multi-cursor / Cross-Correlation, `Ctrl+Shift+P` เปิด Peak Detection
- ปุ่ม **Snapshot View** ใน context menu ใช้บันทึกมุมมองแล้วเรียกกลับได้รวดเร็ว
- Settings dialog ช่วยสลับธีม, ตั้งฟอนต์, ตั้งค่า Matplotlib grid/linestyle ได้แบบเรียลไทม์
- ใช้ `samples/` และ `data/` สำหรับตัวอย่างชุดข้อมูลทดลอง

## การทดสอบ

```bash
python -m pytest tests/
```

## เอกสารเพิ่มเติม
- [Derived Column Guide](README_DERIVED_COLUMN.md)
- [Spectrogram Guide](README_SPECTROGRAM.md)
- [Annotation, Analysis & Context Menu](README_ANNOTATION_ANALYSIS_CONTEXT_MENU.md)
- [โครงสร้างโปรเจ็กต์](../PROJECT_STRUCTURE.md)

## การมีส่วนร่วม
1. Fork โปรเจ็กต์และสร้าง branch ใหม่ (`git checkout -b feature/my-feature`)
2. พัฒนาและรันทดสอบที่เกี่ยวข้อง
3. Commit ข้อความสั้นชัดเจน (`git commit -m "Add my feature"`)
4. Push branch (`git push origin feature/my-feature`)
5. เปิด Pull Request พร้อมรายละเอียดการเปลี่ยนแปลง

## License

โปรเจ็กต์นี้อยู่ภายใต้ MIT License ดูรายละเอียดที่ไฟล์ [LICENSE](../LICENSE)

## ติดต่อ

- Email: your.email@example.com
- GitHub Issues: https://github.com/yourusername/SciPlotter/issues
