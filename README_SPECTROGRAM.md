# Spectrogram/Wavelet Analysis Feature

## 🎯 **ภาพรวม**
ฟีเจอร์ Spectrogram/Wavelet Analysis เพิ่มความสามารถในการวิเคราะห์สัญญาณในโดเมนเวลา-ความถี่ ให้กับ SciPlotter

## 📦 **Dependencies ที่จำเป็น**
- `scipy>=1.11.0` - สำหรับ STFT (Short-Time Fourier Transform)
- `PyWavelets>=1.5.0` - สำหรับ CWT (Continuous Wavelet Transform)

## 🚀 **การใช้งาน**

### **1. เปิด Spectrogram Dialog**
- **ปุ่ม "Spectrogram…"** ในแท็บ Plot
- **เมนู Process → Spectrogram…**

### **2. เลือกข้อมูล**
- **คอลัมน์เวลา**: คอลัมน์ที่เก็บข้อมูลเวลา (datetime หรือ float)
- **คอลัมน์สัญญาณ**: คอลัมน์ที่เก็บข้อมูลสัญญาณ

### **3. เลือกโหมดการวิเคราะห์**

#### **STFT (Spectrogram)**
- **Window**: hann, hamming, blackman, bartlett, triang
- **Points per segment**: 32-2048 (ค่าเริ่มต้น: 256)
- **Overlap**: 16-1024 (ค่าเริ่มต้น: 128)
- **Scaling**: density, spectrum

#### **CWT (Wavelet)**
- **Wavelet**: morl, gaus, cmor, shan, fbsp
- **จำนวน scales**: 16-256 (ค่าเริ่มต้น: 64)

### **4. ตัวเลือกการแสดงผล**
- **แปลงเป็น Decibels (dB)**: แปลงค่า power เป็น dB

## 🎨 **คุณสมบัติพิเศษ**

### **Crosshair Support**
- แสดงค่าเวลา, ความถี่, และ power บริเวณ pointer
- รองรับข้อมูล datetime และตัวเลข
- แสดงข้อมูลใน status bar

### **Export Options**
- **Preview**: แสดง spectrogram บนกราฟหลัก
- **Export Image (PNG)**: บันทึกเป็นรูปภาพ
- **Export CSV**: บันทึกข้อมูลเป็นตาราง

### **Integration Features**
- **Send to FFT**: ส่งข้อมูลไปยัง FFT dialog
- **Send to CurveFit**: ส่งข้อมูลไปยัง CurveFit dialog

## 🔧 **การตั้งค่าที่แนะนำ**

### **สำหรับข้อมูลสั้น (< 1000 จุด)**
- **STFT**: nperseg = 64, noverlap = 32
- **CWT**: scales = 32

### **สำหรับข้อมูลยาว (> 10000 จุด)**
- **STFT**: nperseg = 512, noverlap = 256
- **CWT**: scales = 128

### **สำหรับการวิเคราะห์ความถี่ต่ำ**
- **Window**: hann หรือ hamming
- **Scaling**: density

### **สำหรับการวิเคราะห์ความถี่สูง**
- **Window**: blackman
- **Scaling**: spectrum

## 📊 **การแสดงผล**

### **Colormap**
- ใช้ `viridis` เป็นค่าเริ่มต้น (เย็นตา)
- รองรับ colormap อื่นๆ ของ Matplotlib

### **Axes**
- **แกน X**: เวลา (datetime หรือ float)
- **แกน Y**: ความถี่ (Hz)
- **Colorbar**: Power (dB) หรือ Power

### **Grid และ Styling**
- Grid แบบ minor และ major
- สีและความโปร่งใสที่เหมาะสม

## ⚠️ **ข้อควรระวัง**

### **ข้อมูลที่เหมาะสม**
- ต้องมีข้อมูลอย่างน้อย 10 จุด
- ข้อมูลต้องไม่มี NaN มากเกินไป
- เวลาต้องเรียงลำดับจากน้อยไปมาก

### **Memory Usage**
- **STFT**: ใช้หน่วยความจำน้อยกว่า
- **CWT**: ใช้หน่วยความจำมากกว่า แต่ให้ความละเอียดดีกว่า

### **Performance**
- **STFT**: เร็วกว่า เหมาะสำหรับข้อมูลยาว
- **CWT**: ช้ากว่า แต่ให้ข้อมูลละเอียดกว่า

## 🐛 **การแก้ไขปัญหา**

### **Import Error**
```
scipy ไม่ได้ติดตั้ง กรุณาติดตั้งด้วย: pip install scipy>=1.11.0
```
**วิธีแก้**: `pip install scipy>=1.11.0`

### **PyWavelets Error**
```
PyWavelets ไม่ได้ติดตั้ง กรุณาติดตั้งด้วย: pip install PyWavelets>=1.5.0
```
**วิธีแก้**: `pip install PyWavelets>=1.5.0`

### **ข้อมูลน้อยเกินไป**
```
ข้อมูลที่มีค่าถูกต้องน้อยเกินไป (ต้องมีอย่างน้อย 10 จุด)
```
**วิธีแก้**: ตรวจสอบข้อมูลและลบ NaN values

## 📈 **ตัวอย่างการใช้งาน**

### **1. วิเคราะห์เสียง**
- ใช้ STFT เพื่อดู spectrogram ของเสียง
- ตั้งค่า window = "hann", nperseg = 512

### **2. วิเคราะห์สัญญาณชีวภาพ**
- ใช้ CWT เพื่อดู wavelet transform
- ตั้งค่า wavelet = "morl", scales = 64

### **3. วิเคราะห์ข้อมูลเซ็นเซอร์**
- ใช้ STFT เพื่อดูการเปลี่ยนแปลงความถี่
- ตั้งค่า scaling = "density", to_db = True

## 🔗 **การเชื่อมต่อกับฟีเจอร์อื่น**

### **FFT Integration**
- ใช้ข้อมูลจาก spectrogram เพื่อทำ FFT
- เลือกช่วงเวลาที่สนใจ

### **CurveFit Integration**
- ใช้ข้อมูลจาก spectrogram เพื่อทำ curve fitting
- วิเคราะห์แนวโน้มของ power spectrum

## 📝 **หมายเหตุ**
- ฟีเจอร์นี้ต้องการ Python 3.8+ และ Matplotlib 3.8+
- รองรับข้อมูลขนาดใหญ่ (มากกว่า 1 ล้านจุด)
- สามารถปรับแต่งพารามิเตอร์ได้ตามความต้องการ
