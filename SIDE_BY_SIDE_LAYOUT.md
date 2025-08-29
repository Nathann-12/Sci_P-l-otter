# Side-by-Side Layout Improvements

## ภาพรวม

การปรับปรุง layout ของ Matplotlib Tab ใน Settings Dialog ให้แสดงพรีวิวกราฟด้านข้างแทนการแสดงด้านล่าง เพื่อให้มองเห็นได้ชัดเจนขึ้น

## ปัญหาที่แก้ไข

### ก่อนการปรับปรุง
- พรีวิวกราฟ Matplotlib อยู่ด้านล่างของ dialog
- ขนาด dialog เล็กเกินไป (800x600)
- พรีวิวกราฟเล็กเกินไป (300x200)
- มองเห็นพรีวิวยาก ต้องเลื่อนลงไปดู

### หลังการปรับปรุง
- พรีวิวกราฟอยู่ด้านขวาของ dialog
- ขนาด dialog เพิ่มขึ้น (1000x700)
- พรีวิวกราฟใหญ่ขึ้น (350x250)
- มองเห็นพรีวิวได้ทันทีโดยไม่ต้องเลื่อน

## การเปลี่ยนแปลงในโค้ด

### 1. dialogs_settings.py

#### การเปลี่ยนแปลง Layout
```python
# ก่อน: แสดงผลแบบแนวตั้ง
def _create_matplotlib_tab(self) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)  # Vertical layout
    
# หลัง: แสดงผลแบบแนวนอน
def _create_matplotlib_tab(self) -> QWidget:
    tab = QWidget()
    layout = QHBoxLayout(tab)  # Horizontal layout
```

#### การแบ่งส่วน
```python
# Left side - Settings
left_layout = QVBoxLayout()
left_layout.addWidget(mode_group)
left_layout.addWidget(overrides_group)

# Right side - Preview
right_layout = QVBoxLayout()
right_layout.addWidget(preview_group)

# Add layouts to main layout
layout.addLayout(left_layout, 1)   # Settings take 1 part
layout.addLayout(right_layout, 1)  # Preview takes 1 part
```

#### การปรับขนาด Dialog
```python
# ก่อน
self.resize(800, 600)

# หลัง
self.resize(1000, 700)  # Increased size for side-by-side layout
```

### 2. widgets/mpl_preview.py

#### การปรับขนาด Preview
```python
# ก่อน
self.preview_frame.setMinimumSize(300, 200)
self.figure = Figure(figsize=(4, 2.5), dpi=100)

# หลัง
self.preview_frame.setMinimumSize(350, 250)  # Increased size
self.figure = Figure(figsize=(5, 3), dpi=100)  # Increased figure size
```

## โครงสร้าง Layout ใหม่

```
┌─────────────────────────────────────────────────────────────┐
│                    Settings Dialog                          │
├─────────────────────────────────────────────────────────────┤
│  [Appearance] [Matplotlib]                                 │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────────────────────┐ │
│  │   Mode          │  │      Matplotlib Preview         │ │
│  │   ┌─────────┐   │  │  ┌─────────────────────────────┐ │ │
│  │   │ Mode   │   │  │  │    ตัวอย่างกราฟ Matplotlib   │ │ │
│  │   └─────────┘   │  │  │                             │ │ │
│  │                 │  │  │  ┌─────────────────────────┐ │ │ │
│  │   Style File    │  │  │  │                         │ │ │ │
│  │   ┌─────────┐   │  │  │  │      กราฟตัวอย่าง      │ │ │ │
│  │   │ Path   │   │  │  │  │                         │ │ │ │
│  │   └─────────┘   │  │  │  │                         │ │ │ │
│  │                 │  │  │  └─────────────────────────┘ │ │ │
│  │   Custom        │  │  └─────────────────────────────┘ │ │
│  │   Overrides     │  └─────────────────────────────────┘ │
│  │   ┌─────────┐   │                                     │
│  │   │ Grid    │   │                                     │
│  │   │ Colors  │   │                                     │
│  │   │ Cycle   │   │                                     │
│  │   └─────────┘   │                                     │
│  └─────────────────┘                                     │
└─────────────────────────────────────────────────────────────┘
```

## ประโยชน์ของการปรับปรุง

### 1. การมองเห็นที่ดีขึ้น
- พรีวิวกราฟมองเห็นได้ทันที
- ไม่ต้องเลื่อนหน้าจอลงไปดู
- ขนาดใหญ่ขึ้นทำให้เห็นรายละเอียดชัดเจน

### 2. การใช้งานที่สะดวกขึ้น
- เปลี่ยนการตั้งค่าแล้วเห็นผลทันที
- เปรียบเทียบการตั้งค่าและผลลัพธ์ได้ง่าย
- การทำงานแบบ side-by-side เหมาะสำหรับการปรับแต่ง

### 3. การจัดระเบียบที่ดีขึ้น
- แบ่งส่วนชัดเจน: การตั้งค่าด้านซ้าย, พรีวิวด้านขวา
- ใช้พื้นที่หน้าจออย่างมีประสิทธิภาพ
- Layout สมดุลและสวยงาม

## การทดสอบ

### การทดสอบ Layout
- ✅ Dialog เปิดได้ปกติ
- ✅ Matplotlib Tab แสดงผลแบบ side-by-side
- ✅ พรีวิวกราฟอยู่ด้านขวา
- ✅ การตั้งค่าอยู่ด้านซ้าย
- ✅ ขนาด dialog เพิ่มขึ้นเป็น 1000x700

### การทดสอบการทำงาน
- ✅ การเปลี่ยนการตั้งค่าแล้วพรีวิวอัปเดต
- ✅ การสลับระหว่าง .mplstyle และ Custom overrides
- ✅ การปรับแต่งสี, grid, color cycle
- ✅ การแสดงผลพรีวิวแบบ real-time

## การพัฒนาต่อ

### ความสามารถที่อาจเพิ่มในอนาคต
- **Resizable Splitter**: ให้ผู้ใช้ปรับขนาดส่วนต่างๆ ได้
- **Collapsible Sections**: ซ่อน/แสดงส่วนที่ไม่ต้องการ
- **Multiple Preview Tabs**: แสดงพรีวิวหลายแบบ
- **Custom Layout Presets**: บันทึกการจัดวางที่ชอบ

### การปรับปรุงประสิทธิภาพ
- **Lazy Loading**: โหลดพรีวิวเมื่อจำเป็น
- **Preview Caching**: เก็บ cache พรีวิวที่ใช้บ่อย
- **Background Updates**: อัปเดตพรีวิวในพื้นหลัง
- **Responsive Layout**: ปรับตัวตามขนาดหน้าจอ

## สรุป

การปรับปรุง layout เป็น side-by-side ทำให้ Settings Dialog ของ SciPlotter ใช้งานง่ายขึ้นมาก:

- **พรีวิวกราฟมองเห็นได้ทันที** โดยไม่ต้องเลื่อนหน้าจอ
- **การจัดระเบียบที่ดีขึ้น** แบ่งส่วนชัดเจน
- **การใช้งานที่สะดวกขึ้น** เห็นผลการเปลี่ยนแปลงทันที
- **การใช้พื้นที่อย่างมีประสิทธิภาพ** ขนาดเหมาะสมกับการทำงาน

การปรับปรุงนี้ตอบสนองความต้องการของผู้ใช้ที่ต้องการเห็นพรีวิวกราฟได้ชัดเจนและใช้งานได้สะดวกขึ้น
