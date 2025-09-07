# SciPlotter Project Structure

## 📁 โครงสร้างไฟล์ที่จัดระเบียบแล้ว

```
SciPlotter/
├── 📁 assets/                    # ทรัพยากรต่างๆ
│   ├── 📁 fonts/                 # ฟอนต์ภาษาไทย
│   │   ├── THSarabunNew Bold.ttf
│   │   └── THSarabunNew.ttf
│   ├── 📁 icons/                 # ไอคอนและโลโก้
│   │   ├── clear.png
│   │   ├── export.png
│   │   ├── fft.png
│   │   ├── inspector.png
│   │   ├── open.png
│   │   ├── Plot.png
│   │   └── settings.png
│   └── 📁 images/                # รูปภาพและกราฟ
│       ├── excel_histogram.png
│       ├── test_histogram_cleared.png
│       ├── test_histogram.png
│       └── test_plot.png
│
├── 📁 config/                    # ไฟล์การตั้งค่า
│   └── config.json
│
├── 📁 core/                      # โค้ดหลักของระบบ
│   ├── __init__.py
│   ├── logging_setup.py
│   └── units.py
│
├── 📁 data/                      # ข้อมูลตัวอย่างและผลลัพธ์
│   ├── debug_test.csv
│   ├── minimal_test.csv
│   ├── sciplotter_report6.pdf
│   ├── test_plot_data.csv
│   └── test_simple_plot.csv
│
├── 📁 docs/                      # เอกสารและคู่มือ
│   ├── ACADEMIC_CLEAN_TEMPLATE.md
│   ├── DATETIME_VALIDATION_FIX.md
│   ├── LARGE_FILE_FIX.md
│   ├── NUMERIC_VALIDATION_FIX.md
│   ├── PLOT_DISPLAY_FIX.md
│   ├── PLOT_TESTING_GUIDE.md
│   ├── README_DERIVED_COLUMN.md
│   ├── README_SPECTROGRAM.md
│   ├── README.md
│   ├── SETTINGS_IMPROVEMENTS.md
│   ├── SIDE_BY_SIDE_LAYOUT.md
│   └── TESTING_INSTRUCTIONS.md
│
├── 📁 logs/                      # ไฟล์ log
│   └── app.log
│
├── 📁 samples/                   # ข้อมูลตัวอย่าง
│   ├── sample_data.csv
│   └── test_data.xlsx
│
├── 📁 styles/                    # ธีมและสไตล์
│   ├── __init__.py
│   ├── dark.qss
│   ├── light.qss
│   ├── mpl_style_dark_pro.mplstyle
│   ├── mpl_style_dark.mplstyle
│   ├── mpl_style_light.mplstyle
│   ├── qdark.qss
│   ├── theme.py
│   └── toolbar.qss
│
├── 📁 temp/                      # ไฟล์ชั่วคราว
│
├── 📁 tests/                     # ไฟล์ทดสอบ
│   ├── test_cdf.py
│   ├── test_datetime_validation.py
│   ├── test_derived_column.py
│   ├── test_large_file.py
│   ├── test_numeric_validation.py
│   ├── test_plot_display.py
│   └── test_system.py
│
├── 📁 UI/                        # ส่วนติดต่อผู้ใช้
│   ├── __init__.py
│   └── widgets/
│       ├── __init__.py
│       └── error_panel.py
│
├── 📁 widgets/                   # Widgets เพิ่มเติม
│   ├── __init__.py
│   ├── color_button.py
│   └── mpl_preview.py
│
├── 📄 main.py                    # ไฟล์หลักของโปรแกรม
├── 📄 requirements.txt           # Dependencies
│
├── 📄 dialogs.py                 # Dialog boxes หลัก
├── 📄 dialogs_calibrate.py       # Dialog การสอบเทียบ
├── 📄 dialogs_cdf.py             # Dialog สำหรับ CDF
├── 📄 dialogs_report.py          # Dialog สร้างรายงาน
├── 📄 dialogs_settings.py        # Dialog การตั้งค่า
├── 📄 dialogs_spectrogram.py    # Dialog Spectrogram
├── 📄 dialogs_tabs.py            # Dialog จัดการแท็บ
├── 📄 dialogs_units.py           # Dialog หน่วยและการแปลง
│
├── 📄 file_io.py                # การอ่าน/เขียนไฟล์
├── 📄 loaders.py                # โหลดข้อมูลประเภทต่างๆ
├── 📄 processors.py             # ประมวลผลข้อมูล
├── 📄 processors_spectrogram.py # ประมวลผล Spectrogram
├── 📄 read_mms_cdf.py           # อ่านไฟล์ MMS CDF
├── 📄 report_generator.py       # สร้างรายงาน PDF
├── 📄 settings.py               # การจัดการการตั้งค่า
│
├── 📄 create_simple_test.py     # สร้างข้อมูลทดสอบ
├── 📄 final_test.py             # ทดสอบสุดท้าย
└── 📄 PROJECT_STRUCTURE.md      # ไฟล์นี้
```

## 🎯 ประโยชน์ของการจัดระเบียบ

### 📋 **การจัดกลุ่มตามหน้าที่:**
- **assets/**: ทรัพยากรทั้งหมด (ฟอนต์, ไอคอน, รูปภาพ)
- **config/**: ไฟล์การตั้งค่า
- **core/**: โค้ดหลักของระบบ
- **data/**: ข้อมูลตัวอย่างและผลลัพธ์
- **docs/**: เอกสารและคู่มือ
- **logs/**: ไฟล์ log
- **samples/**: ข้อมูลตัวอย่างสำหรับทดสอบ
- **styles/**: ธีมและสไตล์
- **temp/**: ไฟล์ชั่วคราว
- **tests/**: ไฟล์ทดสอบทั้งหมด
- **UI/**: ส่วนติดต่อผู้ใช้
- **widgets/**: Widgets เพิ่มเติม

### 🚀 **ข้อดี:**
1. **🔍 หาไฟล์ง่าย** - จัดกลุ่มตามหน้าที่การใช้งาน
2. **🧹 สะอาดตา** - โฟลเดอร์หลักไม่รก
3. **📚 จัดการง่าย** - แยกไฟล์ตามประเภท
4. **🔧 บำรุงรักษา** - โครงสร้างชัดเจน
5. **👥 ทีมงาน** - เข้าใจโครงสร้างได้ง่าย

### 📝 **หมายเหตุ:**
- โครงสร้างนี้ไม่กระทบต่อการทำงานของโค้ด
- ไฟล์หลักยังคงอยู่ในตำแหน่งเดิม
- เพียงแค่ย้ายไฟล์เสริมไปยังโฟลเดอร์ที่เหมาะสม
- สามารถปรับแต่งเพิ่มเติมได้ตามความต้องการ
