SciPlotter – Annotation, Analysis, and Right‑Click Context Menu



1) Annotation Tool
- เมนู: Annotation
  - Enable Annotation Mode (ติ๊กเพื่อเข้าโหมด)
  - Add Text / Arrow / Line / Rectangle / Ellipse / Callout
  - Style Dock… (ปรับสีเส้น/สีเติม/alpha/ความหนาเส้น/ฟอนต์/ขนาด/หนา/เอียง/ลูกศร/z‑order)
- วิธีใช้: เปิดโหมด → เลือกชนิด → คลิก/ลากบนกราฟ → ดับเบิลคลิกแก้ข้อความ → ใช้ Style Dock เพื่อปรับสไตล์
- บันทึก/ส่งออก: Annotation ติดไปกับ PNG อัตโนมัติ; `to_json()` / `from_json()` ใช้เซฟ/โหลดสถานะได้
- ช็อตคัต: T/W/L/R/E/C และ Ctrl+Z / Ctrl+Y

2) Analysis – Cross‑Correlation
- เมนู: Analysis > Cross‑Correlation
  - Enable Multi‑Cursor [Ctrl+Shift+X]
  - Window… (ตั้ง X, Y A, Y B, Detrend, Normalize, Δt, Max lag)
  - Link Axes by X‑Time / Compute in Range / Clear Results
- Panel: ปุ่ม Compute in Range, Copy Summary, Clear; แสดง r(lag), lag ที่ดีที่สุด, Spearman ρ, p‑value (ถ้ามี SciPy)

3) Analysis – Peak Detection
- เมนู: Analysis > Peak Detection
  - Enable [Ctrl+Shift+P], Settings…, Detect in Range [Ctrl+D], Annotate Peaks, Export Peak Table [Ctrl+E], Clear
- Panel: ปุ่ม Detect/Annotate/Clear/Export และตารางผล x_peak, y_peak, index

4) Right‑Click Context Menu (คลิกขวาในพื้นที่กราฟ)
- View: Reset View, Autoscale, Toggle Grid/Minor Ticks/Legend
- Zoom & Pan: Zoom In/Out, Box Zoom, Pan, Zoom Back
- Axes & Scales: Set Axis Limits…, X/Y Linear/Log, Invert X/Y
- Cursors & Measures: Add V/H Line, Measure Distance, Copy Coordinates
- Annotation: Enable/เพิ่มรูปแบบ/Style Dock (ถ้ามี)
- Analysis (Visible Range): Peak Detection (Detect/Annotate/Settings/Clear), Cross‑Correlation (Compute/Link/Panel)
- Export / Copy: Save Figure (PNG), Copy Figure, Export Visible CSV
- Utilities: Snapshot View, Recall Snapshot, Clear Overlays

5) หมายเหตุ
- รองรับแกน X แบบเวลา; ธีมเริ่มต้น `styles/dark_modern.qss`; ฟอนต์ไทยแนะนำ TH Sarabun New

6) ช็อตคัตสรุป
- Annotation: T/W/L/R/E/C, Double‑Click, Ctrl+Z / Ctrl+Y
- Analysis: Ctrl+Shift+X, Ctrl+Shift+P, Ctrl+D, Ctrl+E
- View: Home, +/‑, B, P
