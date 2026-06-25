# 🧭 SciPlotter Roadmap — Research OS สำหรับนักวิจัยไทย

> **วิสัยทัศน์:** ไม่ใช่แค่ Origin clone แต่เป็น **Research OS** ครบวงจรสำหรับนักวิจัยไทย
> **เปิดข้อมูล → วิเคราะห์ → ทำกราฟ → ใช้โมดูลเฉพาะทาง → เขียนรายงาน → reproduce ได้**

**จุดยืน 3 ชั้น**
- **แกนกลาง** = Origin + Excel + Python GUI (Core Data / Cleaning / Plotting / Analysis / Signal)
- **โมดูลเฉพาะทาง** = Gas Sensor · Electrochemistry · Spectroscopy · Microscopy · Space Physics · Materials Science
- **ตัวสร้างความต่าง** = AI Assistant + Reproducibility + ภาษาไทย + workflow ของนักวิจัยจริง

---

## วิธีใช้ไฟล์นี้ (สำคัญ — สำหรับคนและ AI ทุกตัว)
- ไฟล์นี้คือ **แหล่งความจริงเดียว (single source of truth)** ของ scope ทั้งโปรเจค
- **สถานะ:** `✅ done` · `🟡 partial` (มีบางส่วน/ทำผ่านทางอ้อมได้) · `☐ planned`
- **กติกาเมื่อทำอะไรเสร็จ (บังคับ):**
  1. เปลี่ยนสถานะรายการนั้นใน roadmap นี้ → `✅`
  2. เพิ่ม/อัปเดต **เทสต์** ใน `tests/` ให้ครอบฟีเจอร์นั้น (อย่าปล่อยให้มีแต่ structure test)
  3. รัน `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/ -q` ให้เขียวก่อนถือว่าเสร็จ
  4. ถ้าโครงสร้าง/วิธีรันเปลี่ยน → อัปเดต [CLAUDE.md](CLAUDE.md) ด้วย
- รายละเอียดสถาปัตยกรรม วิธีรัน และ "สูตรเพิ่มฟีเจอร์" อยู่ใน [CLAUDE.md](CLAUDE.md)

---

## A. Core Data System — 🟢 ฐานแข็ง (ขาด JSON/HDF5/MAT/XML + dataset management)
- ✅ Import CSV
- ✅ Import TXT
- ✅ Import TSV
- ✅ Import Excel (multi-sheet)
- ☐ Import JSON
- ☐ Import HDF5
- ✅ Import NetCDF
- ✅ Import CDF
- ☐ Import MAT file
- ☐ Import XML
- ✅ Drag & drop
- ☐ Batch import
- 🟡 Auto delimiter detection
- 🟡 Encoding detection
- 🟡 Missing value detection
- 🟡 Header detection
- 🟡 Multi-sheet Excel reader
- 🟡 Data preview
- ✅ Column type detection
- ✅ Time column detection
- 🟡 Unit detection
- 🟡 Metadata reader
- 🟡 Dataset tree (ตอนนี้เป็น staging list แบน)
- ☐ Dataset grouping
- 🟡 Dataset rename
- ☐ Dataset duplicate
- ☐ Dataset merge
- ☐ Dataset split
- ☐ Dataset filter
- ☐ Dataset search

## B. Data Cleaning — 🟡 มีพื้นฐาน ขาดชุดทำความสะอาดมาตรฐาน
- 🟡 Remove NaN
- ☐ Fill missing value
- ☐ Interpolate missing value
- ☐ Remove duplicates
- ☐ Outlier detection
- ☐ Outlier removal
- ☐ Normalize
- ☐ Standardize
- ☐ Min-max scale
- ☐ Baseline subtraction
- 🟡 Detrend linear
- ☐ Detrend polynomial
- ✅ Smooth data (moving average)
- ☐ Resample
- ☐ Sort data
- 🟡 Crop range (export visible range)
- ✅ Convert units
- 🟡 Time alignment (add Bangkok time +7h)
- ☐ Merge by timestamp
- ✅ Formula column (derived column)

## C. Plotting — 🟢 แกนครบ ขาดชนิดเฉพาะ + export หลายฟอร์แมต
- ✅ Line plot
- ✅ Scatter plot
- ✅ Bar chart
- ✅ Histogram
- ✅ Box plot
- ☐ Violin plot
- ☐ Heatmap
- ☐ Contour plot
- ✅ Surface plot (3D)
- ☐ Waterfall plot
- ✅ Spectrogram
- ☐ Polar plot
- ☐ Phase plot
- ☐ Nyquist plot
- ☐ Bode plot
- ☐ Error bar
- ☐ Multi-axis plot
- ☐ Subplot grid
- 🟡 Log X
- 🟡 Log Y
- ☐ Broken axis
- ☐ Reverse axis
- ✅ Date axis
- 🟡 Custom ticks
- 🟡 Legend editor
- 🟡 Label editor
- 🟡 Font editor
- 🟡 Color editor (color cycle)
- ✅ Theme preset (dark/default)
- ☐ Journal figure preset
- ✅ Export PNG
- 🟡 Export SVG
- ✅ Export PDF
- ☐ Export TIFF
- ☐ Export EPS
- ☐ Transparent background
- ☐ High DPI export
- ☐ Copy to clipboard
- ☐ Batch export
- ☐ Save figure template

## D. Analysis Engine — 🟢 fitting แข็ง ขาดสถิติเชิงพรรณนา/ขั้นสูง
- 🟡 Mean
- 🟡 Median
- ☐ Mode
- 🟡 Standard deviation
- 🟡 Variance
- ☐ Skewness
- ☐ Kurtosis
- ✅ Correlation (cross-correlation)
- ☐ Covariance
- ✅ Linear regression
- ✅ Polynomial regression
- ✅ Exponential fit
- 🟡 Power law fit
- ✅ Gaussian fit
- 🟡 Lorentzian fit
- ☐ Voigt fit
- ✅ Sine fit
- 🟡 Damped sine fit
- 🟡 Logistic fit
- ✅ Custom equation fit
- 🟡 Multi-peak fitting
- ☐ Global fitting
- 🟡 Fit constraints
- 🟡 Fit bounds
- ☐ Weighted fitting
- 🟡 Residual plot
- ✅ R²
- ✅ RMSE
- 🟡 Chi-square
- 🟡 Confidence interval

## E. Signal Processing — 🟢 FFT/peak/wavelet มี ขาดชุด filter
- ✅ FFT
- ☐ IFFT
- ☐ PSD
- ☐ Welch PSD
- 🟡 STFT
- ✅ Spectrogram
- ✅ Wavelet transform
- ☐ Hilbert transform
- ☐ Envelope detection
- ✅ Cross-correlation
- 🟡 Auto-correlation
- ☐ Convolution
- ☐ Deconvolution
- ☐ Low-pass filter
- ☐ High-pass filter
- ☐ Band-pass filter
- ☐ Band-stop filter
- ☐ Butterworth filter
- ☐ Savitzky-Golay
- ✅ Moving average
- ☐ Median filter
- ☐ Gaussian filter
- 🟡 Window function
- 🟡 Hann window
- 🟡 Hamming window
- ☐ Blackman window
- ☐ Kaiser window
- ☐ Zero padding
- ✅ Peak detection
- ☐ Peak area
- ☐ FWHM
- ☐ Noise floor
- ☐ SNR
- ☐ Harmonic analysis
- ☐ Frequency tracking

## F. Reproducibility System — 🟡 มี session/undo ขาด workflow/script gen
- ☐ Analysis history
- 🟡 Operation log
- 🟡 Parameter log
- ☐ Version stamp
- ☐ Dataset checksum
- ☐ Export workflow
- ☐ Import workflow
- ☐ Re-run analysis
- ☐ Auto-generate Python script
- 🟡 Auto-generate report
- 🟡 Save project file (session save/restore)
- 🟡 Project snapshot
- ✅ Undo/redo (annotations)
- ☐ Compare versions
- ☐ Audit trail

## G. AI Assistant — ☐ ยังไม่เริ่ม (ตัวสร้างความต่างหลัก)
- ☐ สั่งงานด้วยภาษาไทย
- ☐ สั่งงานด้วยอังกฤษ
- ☐ "ทำกราฟให้หน่อย"
- ☐ "Fit peak นี้"
- ☐ "หา anomaly"
- ☐ "อธิบายกราฟนี้"
- ☐ "เขียน caption"
- ☐ "เขียน result section"
- ☐ "เขียน discussion"
- ☐ "ตรวจกราฟพร้อมตีพิมพ์ไหม"
- ☐ แนะนำ plot ที่เหมาะกับข้อมูล
- ☐ แนะนำ fit model
- ☐ แนะนำ preprocessing
- ☐ แปลผลสถิติ
- ☐ สรุปไฟล์ข้อมูล
- ☐ สรุปรายงานอัตโนมัติ
- ☐ Generate Python code
- ☐ Generate MATLAB code
- ☐ Generate Origin-like workflow
- ☐ Chat กับ dataset

## H. Gas Sensor Module — ☐ ยังไม่เริ่ม ⭐ (โมดูลขายจริง — ให้ priority สูง)
- ☐ Real-time serial data จาก ESP32
- ☐ Serial port monitor
- ☐ Live resistance plot
- ☐ Live voltage plot
- ☐ Live temperature plot
- ☐ Live humidity plot
- ☐ Gas exposure marker
- ☐ Baseline selection
- ☐ Baseline correction
- ☐ Response calculation
- ☐ Response %
- ☐ Sensitivity
- ☐ Recovery %
- ☐ Response time
- ☐ Recovery time
- ☐ Rise time
- ☐ Decay time
- ☐ Repeatability analysis
- ☐ Reproducibility analysis
- ☐ Stability analysis
- ☐ Selectivity chart
- ☐ Multi-gas comparison
- ☐ Concentration calibration
- ☐ Calibration curve
- ☐ Limit of detection
- ☐ Limit of quantification
- ☐ Signal-to-noise ratio
- ☐ Drift correction
- ☐ Humidity compensation
- ☐ Temperature compensation
- ☐ Sensor aging analysis
- ☐ Cycle detection
- ☐ Auto detect gas ON/OFF
- ☐ Baseline drift warning
- ☐ Abnormal sensor warning
- ☐ Resistance range checker
- ☐ Heater temperature log
- ☐ Test chamber volume calculator
- ☐ Gas dilution calculator
- ☐ ppm conversion
- ☐ Response table export
- ☐ Sensor performance report
- ☐ Gas sensor paper figure template
- ☐ Selectivity radar chart
- ☐ Long-term stability plot
- ☐ Dynamic response plot
- ☐ Static response plot
- ☐ Sensor array comparison
- ☐ PCA gas classification
- ☐ AI gas pattern recognition

## I. Electrochemistry Module — ☐ ยังไม่เริ่ม
- ☐ Cyclic voltammetry import
- ☐ CV peak current
- ☐ CV peak potential
- ☐ Oxidation peak detection
- ☐ Reduction peak detection
- ☐ ΔEp calculation
- ☐ Scan rate analysis
- ☐ Randles-Sevcik plot
- ☐ ECSA calculation
- ☐ Tafel plot
- ☐ Linear sweep voltammetry
- ☐ Chronoamperometry
- ☐ Chronopotentiometry
- ☐ Charge/discharge curve
- ☐ Specific capacitance
- ☐ Coulombic efficiency
- ☐ Energy density
- ☐ Power density
- ☐ GCD cycle stability
- ☐ Battery capacity analysis
- ☐ EIS Nyquist plot
- ☐ EIS Bode plot
- ☐ Equivalent circuit fitting
- ☐ Rs calculation
- ☐ Rct calculation
- ☐ Warburg element fitting
- ☐ Double-layer capacitance
- ☐ Impedance report
- ☐ Supercapacitor module
- ☐ Battery degradation module

## J. Spectroscopy Module — ☐ ยังไม่เริ่ม
- ☐ Raman spectrum viewer
- ☐ FTIR spectrum viewer
- ☐ UV-Vis spectrum viewer
- ☐ PL spectrum viewer
- ☐ XPS spectrum viewer
- ☐ XRD pattern viewer
- ☐ Spectrum baseline correction
- ☐ Spectrum smoothing
- ☐ Peak detection
- ☐ Peak fitting
- ☐ Raman D/G ratio
- ☐ Raman 2D peak analysis
- ☐ FTIR functional group marker
- ☐ UV-Vis absorbance peak
- ☐ Band gap from Tauc plot
- ☐ PL intensity comparison
- ☐ XPS peak deconvolution
- ☐ XRD peak indexing
- ☐ Scherrer crystallite size
- ☐ FWHM calculation
- ☐ Background subtraction
- ☐ Normalize spectrum
- ☐ Compare spectra
- ☐ Stack spectra
- ☐ Waterfall spectra
- ☐ Peak assignment notes
- ☐ Export peak table
- ☐ Auto spectrum report
- ☐ AI functional group suggestion
- ☐ AI material interpretation

## K. Microscopy / Image Analysis Module — ☐ ยังไม่เริ่ม
- ☐ Import TEM / SEM / AFM / optical microscope image
- ☐ Scale bar calibration / Add scale bar
- ☐ Crop / Rotate / Brightness / Contrast
- ☐ Thresholding / Edge detection
- ☐ Particle detection / counting / size distribution
- ☐ Average particle size / Diameter histogram
- ☐ Area / Perimeter / Circularity / Aspect ratio
- ☐ Agglomeration index
- ☐ Porosity analysis / Pore size distribution
- ☐ Grain size analysis
- ☐ Fiber diameter analysis
- ☐ Film thickness measurement
- ☐ Surface crack detection / Burn/damage detection
- ☐ Noise removal
- ☐ EDS map viewer / element table / spectrum viewer
- ☐ Element ratio calculation / overlay
- ☐ SEM/TEM annotation
- ☐ Before-after comparison
- ☐ Batch image analysis
- ☐ AI morphology description
- ☐ Microscopy report export

## L. Space Physics / CDF Module — 🟡 มีฐาน CDF/MMS แล้ว ต่อยอดได้เร็ว
- ✅ NASA CDF reader
- ✅ MMS data reader
- ☐ Parker Solar Probe reader
- ☐ THEMIS reader
- ☐ Cluster data reader
- ✅ Auto time variable detection
- ✅ TT2000 conversion
- ✅ Epoch conversion
- ✅ Multi-dimensional variable slicer
- 🟡 Magnetic field plot
- 🟡 Bx By Bz Bt plot
- 🟡 Plasma density plot
- 🟡 Velocity plot
- 🟡 Temperature plot
- 🟡 Spectrogram for particle data
- 🟡 Time range selector
- 🟡 Event marker
- ☐ Spacecraft coordinate label
- ☐ GSM/GSE coordinate support
- ☐ Space weather event viewer
- ☐ Magnetic reconnection marker
- ☐ Shock crossing marker
- ☐ Wave activity analysis
- ☐ Field fluctuation analysis
- ✅ FFT magnetic field
- ✅ Wavelet magnetic field
- ✅ Cross-correlation between components
- ☐ Multi-spacecraft comparison
- ☐ Export event interval
- ☐ Space physics report template

## M. Materials Science Module — ☐ ยังไม่เริ่ม
- ☐ Sample database / Composition table
- ☐ Synthesis condition log / Annealing temp / pH / Solvent / Precursor ratio
- ☐ Drop-casting condition / Film thickness record / Substrate record
- ☐ Conductivity / Resistivity / Sheet resistance calculation
- ☐ Activation energy / Arrhenius plot
- ☐ Tauc plot
- ☐ BET surface area import / Pore volume analysis
- ☐ Thermal analysis import (TGA / DSC) / Phase transition point
- ☐ Composite ratio comparison / Material property table
- ☐ Sample-to-sample comparison / Batch ranking / Best sample finder
- ☐ AI material summary / Paper-ready material table / Experimental condition report

## N. Physics / General Lab Module — ☐ ส่วนใหญ่ยังไม่เริ่ม (unit conversion มีแล้ว)
- ☐ Error propagation
- ☐ Least squares lab report
- ☐ Linearization helper
- ☐ Uncertainty table
- ☐ Significant figures checker
- ✅ Unit conversion
- ☐ Dimensional analysis
- ☐ Pendulum analysis
- ☐ Hooke's law analysis
- ☐ Ohm's law analysis
- ☐ RC / RL / RLC fitting
- ☐ Op-amp experiment plot
- ☐ Diode IV curve / Transistor IV curve
- ☐ Hall effect analysis
- ☐ Thermal experiment analysis
- ☐ Blackbody curve fitting
- ☐ Photoelectric effect fitting

## O. Report / Publication Module — 🟡 มี PDF report ขาด captions/หลายฟอร์แมต
- ☐ Auto figure caption
- ☐ Auto table caption
- ☐ Auto methods section
- ☐ Auto result section
- ☐ Auto discussion draft
- ☐ Export Word
- ✅ Export PDF
- ☐ Export LaTeX
- ☐ Export Markdown
- ☐ Export HTML
- ☐ Journal figure size preset
- ☐ IEEE / ACS / Nature / Thesis style figure
- ☐ Reference text generator
- ☐ Citation for software
- ☐ Analysis appendix
- ☐ Supplementary data export
- ☐ Full reproducibility package

## P. App System — 🟡 พื้นฐานมี ขาด plugin/scripting/AI mode
- ✅ Dark mode
- ✅ Light mode
- 🟡 Thai language
- 🟡 English language
- ☐ Plugin system
- ☐ Python scripting
- ☐ Macro recorder
- ☐ Command palette
- ✅ Keyboard shortcuts
- 🟡 Custom workspace (docks/inspector)
- 🟡 Auto-save
- 🟡 Crash recovery (session restore prompt)
- 🟡 Portable mode
- 🟡 Offline mode
- ☐ Local AI mode
- ☐ Cloud AI mode
- ☐ License manager
- ☐ Student license
- ☐ Lab license
- ☐ Update checker

---

## ลำดับความสำคัญที่แนะนำ (ปรับได้)
1. **ปูฐานก่อนรื้อใหญ่:** เพิ่ม behavioral tests คลุม flow หลัก + decouple logic↔Qt widget (ดู CLAUDE.md)
2. **Gas Sensor Module (H)** ⭐ — โมดูลขายจริง, มี ESP32 serial เป็นจุดต่าง
3. **Reproducibility (F)** + **AI Assistant (G)** — ตัวสร้างความต่างจากคู่แข่ง
4. เติมแกนกลางที่ขาด (filters ใน E, dataset management ใน A, สถิติใน D)
5. โมดูลเฉพาะทางอื่นตามสายงานวิจัย (J Spectroscopy, I Electrochemistry, K Microscopy, M Materials)
