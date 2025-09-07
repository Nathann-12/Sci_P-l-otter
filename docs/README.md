# 📊 SciPlotter - Scientific Data Visualization Tool

![SciPlotter Logo](assets/icons/Plot.png)

## 🎯 เกี่ยวกับโปรเจค

**SciPlotter** เป็นเครื่องมือสำหรับการวิเคราะห์และแสดงผลข้อมูลทางวิทยาศาสตร์ที่พัฒนาด้วย Python, PySide6 และ Matplotlib โดยออกแบบมาให้ใช้งานง่ายและมีประสิทธิภาพสูง

## ✨ ฟีเจอร์หลัก

### 📈 **การสร้างกราฟ**
- **Line Plot** - กราฟเส้นสำหรับข้อมูลต่อเนื่อง
- **Scatter Plot** - กราฟกระจายสำหรับข้อมูลจุด
- **Histogram** - กราฟแท่งสำหรับการแจกแจงข้อมูล
- **Spectrogram** - การวิเคราะห์ความถี่-เวลา
- **FFT Analysis** - การวิเคราะห์ฟูริเยร์

### 🔧 **การประมวลผลข้อมูล**
- **Derived Columns** - สร้างคอลัมน์ใหม่ด้วยนิพจน์ทางคณิตศาสตร์
- **Aggregation Functions** - mean, sum, std, var, min, max
- **Data Filtering** - กรองข้อมูลตามเงื่อนไข
- **Unit Conversion** - แปลงหน่วยการวัด
- **Calibration** - การสอบเทียบข้อมูล

### 📁 **การจัดการไฟล์**
- **CSV/TSV** - ไฟล์ข้อมูลแยกด้วยจุลภาค/แท็บ
- **Excel** - ไฟล์ .xlsx
- **NetCDF** - ไฟล์ข้อมูลวิทยาศาสตร์
- **CDF** - ไฟล์ข้อมูลอวกาศ
- **Text Files** - ไฟล์ข้อความทั่วไป

### 🎨 **การแสดงผล**
- **Dark/Light Theme** - ธีมมืดและสว่าง
- **Multiple Tabs** - จัดการหลายกราฟพร้อมกัน
- **Export Options** - ส่งออกเป็น PNG, PDF
- **Report Generation** - สร้างรายงาน PDF อัตโนมัติ

## 🚀 การติดตั้ง

### ข้อกำหนดระบบ
- Python 3.8+
- PySide6
- Matplotlib
- Pandas
- NumPy

### การติดตั้ง
```bash
# Clone repository
git clone <repository-url>
cd SciPlotter

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py
```

## 📖 การใช้งาน

### 1. เปิดไฟล์ข้อมูล
- คลิก **Open** ใน toolbar หรือใช้ `Ctrl+O`
- เลือกไฟล์ข้อมูลที่ต้องการ

### 2. สร้างกราฟ
- เลือกคอลัมน์ X และ Y ใน Inspector Panel
- คลิก **Plot** เพื่อสร้างกราฟ

### 3. การประมวลผลข้อมูล
- ใช้ **Derived Column** (`Ctrl+D`) เพื่อสร้างคอลัมน์ใหม่
- ใช้ **Processors** สำหรับการประมวลผลขั้นสูง

### 4. การส่งออก
- **Export Figure** - ส่งออกกราฟเป็น PNG
- **Export Data** - ส่งออกข้อมูลเป็น CSV
- **Export Report** - สร้างรายงาน PDF

## 🎨 ธีมและการตั้งค่า

### Dark Theme
- พื้นหลังสีเข้ม
- ข้อความสีขาว
- เหมาะสำหรับการใช้งานในที่มืด

### Light Theme
- พื้นหลังสีสว่าง
- ข้อความสีเข้ม
- เหมาะสำหรับการใช้งานในที่สว่าง

## 🔧 การตั้งค่า

เข้าถึงการตั้งค่าผ่าน:
- **Tools → Settings** หรือ
- คลิกปุ่ม **Settings** ใน toolbar

## 📚 เอกสารเพิ่มเติม

- [คู่มือการใช้งาน Derived Column](docs/README_DERIVED_COLUMN.md)
- [คู่มือการใช้งาน Spectrogram](docs/README_SPECTROGRAM.md)
- [โครงสร้างโปรเจค](PROJECT_STRUCTURE.md)

## 🧪 การทดสอบ

```bash
# รันการทดสอบทั้งหมด
python -m pytest tests/

# รันการทดสอบเฉพาะ
python tests/test_system.py
```

## 🤝 การมีส่วนร่วม

1. Fork โปรเจค
2. สร้าง feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit การเปลี่ยนแปลง (`git commit -m 'Add some AmazingFeature'`)
4. Push ไปยัง branch (`git push origin feature/AmazingFeature`)
5. เปิด Pull Request

## 📄 License

โปรเจคนี้อยู่ภายใต้ MIT License - ดูรายละเอียดใน [LICENSE](LICENSE) file

## 👥 ผู้พัฒนา

- **Main Developer**: [Your Name]
- **Contributors**: [Contributor List]

## 📞 การติดต่อ

- **Email**: [your.email@example.com]
- **GitHub**: [github.com/yourusername]
- **Issues**: [GitHub Issues](https://github.com/yourusername/sciplotter/issues)

## 🙏 การขอบคุณ

- **Matplotlib** - สำหรับการสร้างกราฟ
- **Pandas** - สำหรับการจัดการข้อมูล
- **PySide6** - สำหรับ GUI
- **NumPy** - สำหรับการคำนวณทางคณิตศาสตร์

---

⭐ **หากโปรเจคนี้มีประโยชน์ กรุณาให้ดาวน์โหวต!** ⭐
