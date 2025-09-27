# 🤝 Contributing to SciPlotter

ขอบคุณที่สนใจมีส่วนร่วมในการพัฒนา SciPlotter! เรายินดีต้อนรับการมีส่วนร่วมจากทุกคน

## 🚀 วิธีเริ่มต้น

### 1. Fork และ Clone
```bash
# Fork โปรเจคใน GitHub
# จากนั้น clone fork ของคุณ
git clone https://github.com/Nathamn-12/sciplotter.git
cd sciplotter
```

### 2. ติดตั้ง Dependencies
```bash
# สร้าง virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# หรือ
venv\Scripts\activate     # Windows

# ติดตั้ง dependencies
pip install -r requirements.txt
```

### 3. สร้าง Branch
```bash
git checkout -b feature/your-feature-name
```

## 📝 การพัฒนา

### โครงสร้างโค้ด
- **main.py** - ไฟล์หลักของแอปพลิเคชัน
- **dialogs.py** - Dialog boxes หลัก
- **processors.py** - การประมวลผลข้อมูล
- **styles/** - ธีมและสไตล์
- **tests/** - ไฟล์ทดสอบ

### Coding Standards
- ใช้ **PEP 8** สำหรับ Python
- เขียน **docstrings** สำหรับฟังก์ชันและคลาส
- ใช้ **type hints** เมื่อเป็นไปได้
- เขียน **comments** เป็นภาษาไทยหรืออังกฤษ

### การทดสอบ
```bash
# รันการทดสอบทั้งหมด
python -m pytest tests/

# รันการทดสอบเฉพาะ
python tests/test_system.py
```

## 🐛 การรายงาน Bug

### ก่อนรายงาน
1. ตรวจสอบว่าเป็น bug จริงๆ
2. ค้นหาใน [Issues](https://github.com/Nathann-12/sciplotter/issues) ว่ามีคนรายงานแล้วหรือไม่
3. ทดสอบกับเวอร์ชันล่าสุด

### การรายงาน
ใช้ template นี้:
```markdown
**Bug Description**
อธิบาย bug อย่างชัดเจน

**Steps to Reproduce**
1. ไปที่ '...'
2. คลิก '...'
3. ลากไปที่ '...'
4. เห็น error

**Expected Behavior**
อธิบายสิ่งที่ควรเกิดขึ้น

**Screenshots**
แนบ screenshot ถ้ามี

**Environment**
- OS: [e.g. Windows 10]
- Python Version: [e.g. 3.9.0]
- SciPlotter Version: [e.g. 1.0.0]
```

## ✨ การเสนอ Feature

### ก่อนเสนอ
1. คิดให้ดีว่า feature ไว้ทำอะไร 
2. ตรวจสอบว่าไม่มี feature คล้ายกันอยู่แล้ว
3. อธิบาย use case ที่ชัดเจน

### การเสนอ
ใช้ template นี้:
```markdown
**Feature Request**
อธิบาย feature ที่ต้องการ

**Use Case**
อธิบายว่าทำไมต้องการ feature นี้

**Proposed Solution**
อธิบายวิธีแก้ไขที่เสนอ

**Alternatives**
อธิบายทางเลือกอื่นๆ ที่พิจารณา
```

## 🔄 Pull Request Process(เขียนๆมาเถอะไม่ต้องสนคำแนะนำมาก)

### 1. เตรียม PR
- เขียนโค้ดให้เสร็จสมบูรณ์
- เขียนการทดสอบ
- อัปเดตเอกสารถ้าจำเป็น
- รันการทดสอบให้ผ่าน

### 2. สร้าง PR
```bash
git add .
git commit -m "Add: คำอธิบายการเปลี่ยนแปลง"
git push origin feature/your-feature-name
```

### 3. Template สำหรับ PR
```markdown
## 📝 Description
อธิบายการเปลี่ยนแปลง

## 🔗 Related Issues
Closes #123

## 🧪 Testing
- [ ] รันการทดสอบผ่าน
- [ ] ทดสอบด้วยข้อมูลจริง
- [ ] ตรวจสอบ UI/UX

## 📸 Screenshots
แนบ screenshot ถ้ามีการเปลี่ยนแปลง UI

## 📋 Checklist
- [ ] โค้ดผ่าน linting
- [ ] เขียน docstring
- [ ] อัปเดตเอกสาร
- [ ] เขียนการทดสอบ
```

## 🎯 Areas ที่ต้องการความช่วยเหลือ

### 🐛 Bug Fixes
- แก้ไข bugs ที่มีอยู่
- ปรับปรุง error handling
- เพิ่มการตรวจสอบข้อมูล

### ✨ New Features
- เพิ่มฟีเจอร์ใหม่
- ปรับปรุง UI/UX
- เพิ่มการรองรับไฟล์ประเภทใหม่

### 📚 Documentation
- เขียนคู่มือการใช้งาน
- ปรับปรุง README
- เพิ่มตัวอย่างการใช้งาน

### 🧪 Testing
- เขียนการทดสอบ
- เพิ่ม test coverage
- ทดสอบกับข้อมูลจริง

## 💬 การสื่อสาร

- **GitHub Issues** - สำหรับ bug reports และ feature requests
- **GitHub Discussions** - สำหรับคำถามและการสนทนา
- **Pull Requests** - สำหรับการอภิปรายโค้ด

## 📜 Code of Conduct

### หลักการ
- **เคารพ** - เคารพความคิดเห็นของผู้อื่น
- **สร้างสรรค์** - มุ่งมั่นสร้างสรรค์สิ่งที่ดี
- **ร่วมมือ** - ทำงานร่วมกันอย่างมีประสิทธิภาพ

### การกระทำที่ไม่เหมาะสม
- ใช้ภาษาหยาบคาย
- การโจมตีส่วนตัว
- การส่ง spam
- การละเมิดลิขสิทธิ์

## 🏆 Recognition

ผู้มีส่วนร่วมจะได้รับการยอมรับใน:
- README.md
- Release notes
- Contributors page
- เอาเป็นว่าใครช่วยผมเอาชื่อชึ้นหมด



ขอบคุณที่สนใจมีส่วนร่วมในการพัฒนา SciPlotter! 
