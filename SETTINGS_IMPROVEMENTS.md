# Settings Interface Improvements

## ภาพรวม

การปรับปรุง Settings Interface ของ SciPlotter ให้ใช้งานง่ายขึ้น พร้อม live preview และการจัดระเบียบที่ดีขึ้น

## คุณสมบัติใหม่

### 1. Widgets ใหม่

#### ColorButton (`widgets/color_button.py`)
- ปุ่มเลือกสีพร้อม swatch แสดงสีปัจจุบัน
- เปิด Color Dialog เมื่อคลิก
- รองรับการเปลี่ยนแปลงสีแบบ real-time
- มี tooltip แสดงค่า RGB

#### ColorButtonWithLabel (`widgets/color_button.py`)
- ColorButton พร้อมป้ายกำกับด้านบน
- เหมาะสำหรับใช้ในฟอร์มและตาราง

#### MatplotlibPreview (`widgets/mpl_preview.py`)
- ตัวอย่างกราฟ Matplotlib แบบ live preview
- แสดงข้อมูลตัวอย่าง (Sine, Cosine, Double Sine)
- อัปเดตทันทีเมื่อมีการเปลี่ยนแปลงการตั้งค่า
- รองรับการใช้งาน .mplstyle file

### 2. การปรับปรุง dialogs_settings.py

#### Tab Appearance
- **Theme Section**:
  - Built-in Dark/Light/Custom QSS
  - Browse button สำหรับ Custom QSS
  - Preview แสดงผลธีมที่เลือก

- **Fonts Section**:
  - QFontComboBox สำหรับเลือกฟอนต์
  - Font Size spinner
  - Checkbox "Apply to Matplotlib"
  - Preview แสดงฟอนต์ที่เลือก

- **Preview Section**:
  - Font preview แบบ real-time
  - Theme preview พร้อมคำอธิบาย

#### Tab Matplotlib
- **Mode Section**:
  - "Use .mplstyle file" หรือ "Custom overrides"
  - Browse button สำหรับไฟล์ .mplstyle
  - ถ้าเลือก .mplstyle → Overrides ถูก disable

- **Custom Overrides Section**:
  - Grid: checkbox, alpha %, linestyle
  - Colors: Axes Color, Text Color (ColorButton)
  - Color Cycle: list + Add/Edit/Remove/↑/↓

- **Matplotlib Preview**:
  - แสดงตัวอย่างกราฟด้านล่าง
  - อัปเดตทันทีเมื่อค่าบนเปลี่ยน

#### ปุ่มควบคุม
- **Restore Defaults**: คืนค่าการตั้งค่าเริ่มต้น
- **Apply**: นำการตั้งค่าไปใช้ทันที
- **OK**: บันทึกและปิด dialog
- **Cancel**: ยกเลิกการเปลี่ยนแปลง

### 3. การเชื่อมต่อและการจัดการข้อมูล

#### การเชื่อมต่อ
- ใช้ `self.collect()` เพื่อรวบรวมการตั้งค่าทั้งหมด
- เชื่อมต่อกับ SettingsManager ของโปรเจกต์
- รองรับการโหลด/บันทึกค่าใน QSettings

#### การจัดการข้อมูล
- **Deduplication**: ลบคอลัมน์ซ้ำแบบรักษาลำดับ
- **Default Values**: ค่าเริ่มต้นสำหรับทุกการตั้งค่า
- **Validation**: ตรวจสอบความถูกต้องของข้อมูล

### 4. การบังคับ Locale

#### English Locale
- `self.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))`
- บังคับให้ใช้เลขอารบิกใน dialog
- แก้ปัญหาการแสดงผลตัวเลข

## การใช้งาน

### การเปิด Settings Dialog
```python
from dialogs_settings import SettingsDialog
from settings import SettingsManager

settings_manager = SettingsManager()
dialog = SettingsDialog(settings_manager, parent)
dialog.exec()
```

### การใช้งาน ColorButton
```python
from widgets.color_button import ColorButton

color_btn = ColorButton(QColor(255, 0, 0))
color_btn.colorChanged.connect(lambda c: print(f"Color: {c.name()}"))
```

### การใช้งาน MatplotlibPreview
```python
from widgets.mpl_preview import MatplotlibPreview

preview = MatplotlibPreview()
preview.update_style({
    'grid': {'enabled': True, 'alpha': 0.5, 'linestyle': '--'},
    'axes_color': '#FF0000',
    'text_color': '#0000FF',
    'color_cycle': ['#FF0000', '#00FF00', '#0000FF']
})
```

## การทดสอบ

### การทดสอบ Widgets
- ✅ ColorButton: เลือกสีและแสดง swatch
- ✅ ColorButtonWithLabel: แสดงป้ายกำกับและสี
- ✅ MatplotlibPreview: แสดงกราฟตัวอย่างและอัปเดต style

### การทดสอบ Settings Dialog
- ✅ Tab Appearance: เปลี่ยนธีม/ฟอนต์ และดู preview
- ✅ Tab Matplotlib: สลับระหว่าง .mplstyle และ Custom overrides
- ✅ Live Preview: เปลี่ยนค่าต่างๆ แล้วดูกราฟเปลี่ยนทันที
- ✅ การจัดการข้อมูล: deduplication, default values

### การทดสอบการเชื่อมต่อ
- ✅ การโหลดการตั้งค่าปัจจุบัน
- ✅ การบันทึกการตั้งค่าใหม่
- ✅ การคืนค่าการตั้งค่าเริ่มต้น

## ผลลัพธ์

### ความสะดวกในการใช้งาน
- **Live Preview**: เห็นผลลัพธ์ทันทีเมื่อเปลี่ยนการตั้งค่า
- **การจัดระเบียบ**: แบ่งเป็น tabs และ sections ที่ชัดเจน
- **การจัดการสี**: ใช้ ColorButton แทนการพิมพ์ hex code

### ความยืดหยุ่น
- **โหมดผสม**: รองรับทั้ง .mplstyle file และ custom overrides
- **การปรับแต่ง**: ควบคุมได้ละเอียดทุกส่วนของกราฟ
- **การบันทึก**: รองรับการบันทึกและโหลดการตั้งค่า

### ความเสถียร
- **การตรวจสอบ**: validate ข้อมูลก่อนบันทึก
- **การจัดการข้อผิดพลาด**: แสดงข้อความ error ที่ชัดเจน
- **การ fallback**: ใช้ค่าเริ่มต้นเมื่อเกิดปัญหา

## การพัฒนาต่อ

### ความสามารถที่อาจเพิ่มในอนาคต
- **Theme Editor**: สร้างธีมใหม่ในตัว
- **Style Templates**: เทมเพลตการตั้งค่าสำเร็จรูป
- **Import/Export**: นำเข้า/ส่งออกการตั้งค่า
- **Cloud Sync**: ซิงค์การตั้งค่าผ่าน cloud

### การปรับปรุงประสิทธิภาพ
- **Lazy Loading**: โหลด preview เมื่อจำเป็น
- **Caching**: เก็บ cache การตั้งค่าที่ใช้บ่อย
- **Background Updates**: อัปเดต preview ในพื้นหลัง
