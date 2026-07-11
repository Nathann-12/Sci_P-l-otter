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

## A. Core Data System — 🟢 import ครบทุกฟอร์แมตหลัก (ขาด dataset management ขั้นสูง)
- ✅ Import CSV
- ✅ Import TXT
- ✅ Import TSV
- ✅ Import Excel (multi-sheet)
- ✅ Import JSON
- ✅ Import HDF5
- ✅ Import NetCDF
- ✅ Import CDF
- ✅ Import MAT file
- ✅ Import XML
- ✅ Drag & drop
- ✅ Batch import (File → เปิดหลายไฟล์ — Book ต่อไฟล์)
- 🟡 Auto delimiter detection
- 🟡 Encoding detection
- 🟡 Missing value detection
- 🟡 Header detection
- 🟡 Multi-sheet Excel reader
- 🟡 Data preview
- ✅ Data workflow menu (Active Book / Columns / Units + Metadata / Quick Transforms / Clean Data)
- ✅ Column type detection
- ✅ Time column detection
- 🟡 Unit detection
- 🟡 Metadata reader
- ✅ Dataset tree (Origin multi-book: 1 ไฟล์ = 1 Book + Project Explorer)
- ✅ Dataset grouping
- ✅ Dataset rename
- ✅ Dataset duplicate
- ✅ Dataset merge
- ✅ Dataset split
- ✅ Dataset filter
- ✅ Dataset search

## B. Data Cleaning — 🟢 ชุดทำความสะอาดมาตรฐานครบ (เมนู Process → Clean & Prepare Data)
- ✅ Remove NaN
- ✅ Fill missing value
- ✅ Interpolate missing value
- ✅ Remove duplicates
- ✅ Outlier detection
- ✅ Outlier removal
- ✅ Normalize
- ✅ Standardize
- ✅ Min-max scale
- ✅ Baseline subtraction
- ✅ Detrend linear
- ✅ Detrend polynomial
- ✅ Smooth data (moving average)
- ✅ Resample
- ✅ Sort data
- ✅ Crop range (export visible range)
- ✅ Convert units
- 🟡 Time alignment (add Bangkok time +7h)
- ✅ Merge by timestamp
- ✅ Formula column (derived column)

## C. Plotting — 🟢 แกนครบ ขาดชนิดเฉพาะ + export หลายฟอร์แมต
- ✅ Origin-style request/options seam (worksheet designation → immutable plot/export request → Graph ใหม่หรือ overlay)
- ✅ Smart single-column worksheet plot (any single selected column → Y vs Row แบบ Excel)
- ✅ Origin-style Charts mega menu บน menubar (sidebar หมวด + thumbnail grid + Recently Used)
- ✅ Charts/Gallery data mapping dialog (เลือก Primary/X, Y series, Z, Group ก่อน registry/basic advanced plots)
- ✅ Plot/export robustness audit (no-data gallery, duplicate-X export, invalid-plot graph guard, warning-free suite)
- ✅ Graph-scoped toolbar actions target selected/last-selected Graph instead of Graph 1
- ✅ Two-row Origin-style function toolbar (top icon bar + unique Material icons + QAction registry)
- ✅ Function-menu QAction user-flow coverage (Process, Analysis, Plot, Export, Tools/Workflow, Annotation, Gas Sensor)
- ✅ Origin-like Analysis menu categories (Statistics / Mathematics / Data Manipulation / Fitting / Signal Processing / Peaks and Baseline)
- ✅ Process workflow menu grouped for real use (Quick Actions / Frequency & Spectrum / Smoothing & Filters / Signal Transforms / Correlation & Convolution / Clean & Prepare Data / Summarize & Aggregate)
- ✅ Line plot
- ✅ Scatter plot
- ✅ Bar chart
- ✅ Histogram
- ✅ Box plot
- ✅ Violin plot (Plot Gallery → Distribution)
- ✅ Heatmap (numeric worksheet matrix + correlation heatmap)
- ✅ Contour plot (filled contour + labeled contour lines จาก XYZ)
- ✅ Surface plot (3D)
- ✅ Waterfall plot (3D Waterfall + Stacked Lines by Y Offset)
- ✅ Spectrogram
- ✅ Polar plot
- ✅ Phase plot
- ✅ Nyquist plot
- ✅ Bode plot
- ✅ Error bar (Plot → Error Bar Plot)
- ✅ Fill between / band (Plot → Fill Between)
- ✅ Multi-axis plot (Plot → Add Secondary Y Axis)
- ✅ Subplot grid
- ✅ Log X (View → Format Graph → Axes → X scale)
- ✅ Log Y (View → Format Graph → Axes → Y scale)
- ✅ Broken axis
- ✅ Reverse axis (Format Graph → Axes → Reverse X/Y)
- ✅ Date axis
- ✅ Custom ticks (size/direction ใน Ticks && Spines; major/minor increment + Anchor Tick + minor By Counts + rescale margin ใน Format Graph → Scale)
- ✅ Tick label formula/display (Format Graph → Tick Labels: notation/decimals/divide/formula `2*x`/prefix/suffix)
- ✅ Tick-label display editor (decimal/scientific/engineering/percent, divide factor, prefix/suffix, signs)
- ✅ Reference line labels/width/opacity (Format Graph → Reference Lines)
- ✅ Legend editor (Format Graph → Grid & Legend)
- ✅ Label editor (Format Graph → Axes: title/x/y + font sizes)
- ✅ Font editor (title/label/tick/legend sizes ใน Format Graph)
- ✅ Color editor (per-curve color/style/marker ใน Format Graph → Lines)
- ✅ Advanced graph effects (axes shadow/border, legend fill/shadow/rounded, line glow/shadow)
- ✅ Theme preset (dark/default)
- ✅ Compact useful Settings dialog (Appearance + Matplotlib + Plot Behavior, validated QSS/mplstyle paths)
- ✅ Journal figure preset (IEEE/Nature/Science/ACS/Thesis — Format Graph → Presets)
- ✅ Save figure template (Format Graph → Presets && Templates)
- ✅ Export PNG
- ✅ Export SVG (Export → Export Figure)
- ✅ Export PDF
- ✅ Export TIFF (Export → Export Figure)
- ✅ Export EPS (Export → Export Figure)
- ✅ Transparent background (Export Figure option)
- ✅ High DPI export (Export Figure — DPI up to 2400)
- ✅ Copy to clipboard (Export → Copy Graph / Ctrl+Shift+C)
- ✅ Batch export

## D. Analysis Engine — 🟢 fitting แข็ง + สถิติเชิงพรรณนาครบ (เมนู Analysis → Descriptive Statistics)
- ✅ Origin-like Analysis menu hierarchy
- ✅ Mean
- ✅ Median
- ✅ Mode
- ✅ Standard deviation
- ✅ Variance
- ✅ Skewness
- ✅ Kurtosis
- ✅ Correlation (cross-correlation)
- ✅ Covariance
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

## E. Signal Processing — 🟢 FFT/PSD/filters + signal transforms ครบชุดหลัก (เมนู Process)
- ✅ FFT
- ✅ IFFT (Process → Frequency & Spectrum → IFFT)
- ✅ PSD
- ✅ Welch PSD
- ✅ STFT (Process → Frequency & Spectrum → STFT)
- ✅ Spectrogram
- ✅ Wavelet transform
- ✅ Hilbert transform (Process → Signal Transforms → Hilbert Transform)
- ✅ Envelope detection (Process → Signal Transforms → Envelope Detection)
- ✅ Cross-correlation
- ✅ Auto-correlation (Process → Correlation & Convolution → Auto-correlation)
- ✅ Convolution (Process → Correlation & Convolution → Convolution)
- ✅ Deconvolution (Process → Correlation & Convolution → Deconvolution)
- ✅ Low-pass filter
- ✅ High-pass filter
- ✅ Band-pass filter
- ✅ Band-stop filter
- ✅ Butterworth filter
- ✅ Savitzky-Golay
- ✅ Moving average
- ✅ Median filter
- ✅ Gaussian filter
- ✅ Window function (Process → Smoothing & Filters → Apply Window)
- ✅ Hann window
- ✅ Hamming window
- ✅ Blackman window
- ✅ Kaiser window
- ✅ Zero padding (Process → Signal Transforms → Zero Padding)
- ✅ Peak detection
- ✅ Peak area (Analysis → Peak Metrics)
- ✅ FWHM (Analysis → Peak Metrics)
- ✅ Noise floor (Analysis → Signal Quality)
- ✅ SNR (Analysis → Signal Quality)
- ✅ Harmonic analysis
- ✅ Frequency tracking / instantaneous frequency (Process → Signal Transforms → Instantaneous Frequency)

## F. Reproducibility System — 🟢 workflow ครบวงจร (เมนู Tools; core/history.py)
- ✅ Analysis history
- ✅ Operation log
- ✅ Parameter log
- ✅ Version stamp
- ✅ Dataset checksum
- ✅ Export workflow
- ✅ Import workflow
- ✅ Re-run analysis
- ✅ Auto-generate Python script
- ✅ Auto-generate report
- ✅ Save project file (*.sciproj — File → Save/Open Project, ฝังข้อมูลในตัว)
- ✅ Project snapshot
- ✅ Undo/redo (annotations)
- ✅ Compare versions
- ✅ Audit trail (history + checksum + op log; session-level, not immutable)

## G. AI Assistant — 🟡 local tool-using assistant ทำงานแล้ว (Ollama; ตัวสร้างความต่างหลัก)
- ✅ Local AI backend (`ai/` — tool registry + agent loop + Ollama client, no extra deps)
- ✅ Tool-using agent (JSON protocol + `format:json`, ทำงานบนโมเดลเบา 2B ได้)
- ✅ ต่อเข้า AI dock จริง (threaded, ไม่ freeze UI) + config เปลี่ยนโมเดลได้
- 🟡 สั่งงานด้วยภาษาไทย (ผ่านโมเดล; แม่นขึ้นตามขนาดโมเดล)
- 🟡 สั่งงานด้วยอังกฤษ
- 🟡 "ทำกราฟให้หน่อย" (tool `plot_columns`)
- ✅ แปลผล/สรุปข้อมูล (tool `list_columns` + `describe_data`)
- ✅ Fit/Smooth/Filter ผ่าน AI (tools `fit_curve` + `list_fit_models` + `smooth_data` + `filter_signal`)
- ✅ Transform/Clean ผ่าน AI (tools `moving_average` + `fill_missing` + `interpolate` + `normalize` + `detrend` + `remove_outliers` + `remove_duplicates` + `sort_data`)
- ✅ FFT ผ่าน AI (tool `run_fft` → result Book + dominant frequency)
- ✅ เปิดไฟล์ผ่าน AI (tool `open_file`) — รวม 18 AI tools
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
- ☐ สรุปไฟล์ข้อมูล (เต็มรูปแบบ)
- ☐ สรุปรายงานอัตโนมัติ
- ☐ Generate Python code
- ☐ Generate MATLAB code
- ☐ Generate Origin-like workflow
- ☐ Chat กับ dataset (หลาย tool ต่อเนื่อง — มีโครงแล้ว เหลือขยาย tool)

## H. Gas Sensor Module — 🟡 แกนวิเคราะห์เสร็จ ⭐ (เมนู/rail "Gas Sensor"; เหลือฝั่ง real-time ESP32)
- ☐ Real-time serial data จาก ESP32
- ☐ Serial port monitor
- ☐ Live resistance plot
- ☐ Live voltage plot
- ☐ Live temperature plot
- ☐ Live humidity plot
- ☐ Gas exposure marker
- ✅ Baseline selection
- ☐ Baseline correction
- ✅ Response calculation
- ✅ Response %
- ✅ Sensitivity
- 🟡 Recovery %
- ✅ Response time
- ✅ Recovery time
- 🟡 Rise time (t90 = response time)
- 🟡 Decay time (t90 = recovery time)
- ☐ Repeatability analysis
- ☐ Reproducibility analysis
- ☐ Stability analysis
- ☐ Selectivity chart
- ☐ Multi-gas comparison
- ✅ Concentration calibration
- ✅ Calibration curve
- ✅ Limit of detection
- ✅ Limit of quantification
- ✅ Signal-to-noise ratio (Analysis → Signal Quality)
- ☐ Drift correction
- ☐ Humidity compensation
- ☐ Temperature compensation
- ☐ Sensor aging analysis
- ✅ Cycle detection
- ✅ Auto detect gas ON/OFF
- ☐ Baseline drift warning
- ☐ Abnormal sensor warning
- ☐ Resistance range checker
- ☐ Heater temperature log
- ☐ Test chamber volume calculator
- ✅ Gas dilution calculator
- ✅ ppm conversion
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

## I. Electrochemistry Module — 🟡 first production workflow pass (menu/rail + result Books/Graphs)
- ☐ Cyclic voltammetry import
- ✅ CV peak current
- ✅ CV peak potential
- ✅ Oxidation peak detection
- ✅ Reduction peak detection
- ✅ ΔEp calculation
- ✅ Scan rate analysis
- ✅ Randles-Sevcik plot
- ✅ ECSA calculation
- ✅ Tafel plot
- ☐ Linear sweep voltammetry
- ☐ Chronoamperometry
- ☐ Chronopotentiometry
- ✅ Charge/discharge curve
- ✅ Specific capacitance
- ☐ Coulombic efficiency
- ✅ Energy density
- ✅ Power density
- ☐ GCD cycle stability
- ☐ Battery capacity analysis
- ✅ EIS Nyquist plot
- ✅ EIS Bode plot
- ☐ Equivalent circuit fitting
- ✅ Rs calculation
- ✅ Rct calculation
- ☐ Warburg element fitting
- ☐ Double-layer capacitance
- 🟡 Impedance report (basic Rs/Rct + Bode result Book; no circuit fitting yet)
- 🟡 Supercapacitor module (GCD capacitance/energy/power; no cycle stability yet)
- ☐ Battery degradation module

## J. Spectroscopy Module — 🟡 first production workflow pass
- ✅ Raman spectrum viewer
- ☐ FTIR spectrum viewer
- ☐ UV-Vis spectrum viewer
- ☐ PL spectrum viewer
- ☐ XPS spectrum viewer
- ✅ XRD pattern viewer
- ✅ Spectrum baseline correction
- ☐ Spectrum smoothing
- ✅ Peak detection
- ☐ Peak fitting
- ✅ Raman D/G ratio
- ☐ Raman 2D peak analysis
- ☐ FTIR functional group marker
- ✅ UV-Vis absorbance peak
- ✅ Band gap from Tauc plot
- ☐ PL intensity comparison
- ☐ XPS peak deconvolution
- ☐ XRD peak indexing
- ✅ Scherrer crystallite size
- ✅ FWHM calculation
- ✅ Background subtraction
- ✅ Normalize spectrum
- ☐ Compare spectra
- ☐ Stack spectra
- ☐ Waterfall spectra
- ☐ Peak assignment notes
- ✅ Export peak table
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

## M. Materials Science Module — 🟡 first production workflow pass
- ☐ Sample database / Composition table
- ☐ Synthesis condition log / Annealing temp / pH / Solvent / Precursor ratio
- ☐ Drop-casting condition / Film thickness record / Substrate record
- ✅ Conductivity / Resistivity / Sheet resistance calculation
- ✅ Activation energy / Arrhenius plot
- ☐ Tauc plot
- ☐ BET surface area import / Pore volume analysis
- ✅ Thermal analysis import (TGA / DSC) / Phase transition point
- ✅ Composite ratio comparison / Material property table
- ✅ Sample-to-sample comparison / Batch ranking / Best sample finder
- ☐ AI material summary / Paper-ready material table / Experimental condition report

## N. Physics / General Lab Module — 🟡 first production workflow pass
- ✅ Error propagation
- ✅ Least squares lab report
- ✅ Linearization helper
- ✅ Uncertainty table
- ☐ Significant figures checker
- ✅ Unit conversion
- ☐ Dimensional analysis
- ✅ Pendulum analysis
- ☐ Hooke's law analysis
- ✅ Ohm's law analysis
- ✅ RC / RL / RLC fitting
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
- ✅ Customizable theme (accent + background สีใดก็ได้, auto light/dark contrast, app-wide runtime retint)
- 🟡 Thai language
- ✅ English language (UI normalization + visible shell/dialog text)
- ☐ Plugin system
- ☐ Python scripting
- ☐ Macro recorder
- ☐ Command palette
- ✅ Keyboard shortcuts
- ✅ Scalable activity rail / module dock
- ✅ Parked side tabs for Project Explorer / Messages Log / Smart Hint Log
- ✅ Clean sheet-first startup (no default Graph1, modules hidden by default)
- ✅ Compact Settings dialog with real theme/font/plot-mode persistence
- 🟡 Custom workspace (docks/inspector)
- 🟡 Auto-save
- 🟡 Crash recovery (session restore prompt)
- 🟡 Portable mode
- 🟡 Offline mode
- ✅ Local AI mode (Ollama, lightest = gemma2:2b; model configurable in `config.json` `ai`)
- ☐ Cloud AI mode (BYO API key)
- ☐ License manager
- ☐ Student license
- ☐ Lab license
- ☐ Update checker

---

## Latest verification
- 2026-07-09: Spectroscopy module first production workflow pass added under Modules Gallery: baseline correction + normalization, peak table/FWHM/area, Raman D/G ratio, Tauc band gap, and XRD Scherrer size. Added pure analysis tests and MainWindow QAction/menu user-flow tests through real result Books/Graphs. Full suite: `715 passed, 3 skipped` with `-W error`.
- 2026-07-09: Materials Science module first production workflow pass added under Modules Gallery: I-V conductivity/resistivity/sheet resistance, Arrhenius activation energy, TGA/DSC thermal metrics, and sample ranking. Added pure analysis tests and MainWindow QAction/menu user-flow tests through result Books/Graphs. Full suite: `721 passed, 3 skipped` with `-W error`.
- 2026-07-09: Physics / General Lab module first production workflow pass added under Modules Gallery: Ohm's law fit, RC time constant, pendulum gravity fit, and power-product uncertainty propagation. Added pure analysis tests and MainWindow QAction/menu user-flow tests. Full suite: `727 passed, 3 skipped` with `-W error`.
- 2026-07-08: Electrochemistry module first production workflow pass added: rail context + top menu, pure analysis helpers for CV peaks, Randles-Sevcik/ECSA, Tafel, GCD supercapacitor metrics, and EIS Rs/Rct/Nyquist/Bode result data. Added MainWindow user-flow tests through real QAction/menu paths. Focused suite: `98 passed` with `-W error`.
- 2026-07-08: core module pass completed for dataset management, cleaning, harmonic analysis, reproducibility report/snapshot/compare/audit, English UI normalization, and Process menu workflow redesign. Added startup/test-suite optimization for Settings diff-apply, Qt test cleanup, cached toolbar icons, cached shell QSS, and quiet debug logging. Full suite: `687 passed, 8 skipped` in `224.36s / 0:03:44` with `-W error`.

---

## ลำดับความสำคัญที่แนะนำ (ปรับได้)
1. **ปูฐานก่อนรื้อใหญ่:** เพิ่ม behavioral tests คลุม flow หลัก + decouple logic↔Qt widget (ดู CLAUDE.md)
2. **Gas Sensor Module (H)** ⭐ — โมดูลขายจริง, มี ESP32 serial เป็นจุดต่าง
3. **Reproducibility (F)** + **AI Assistant (G)** — ตัวสร้างความต่างจากคู่แข่ง
4. เติมแกนกลางที่ขาด (filters ใน E, dataset management ใน A, สถิติใน D)
5. โมดูลเฉพาะทางอื่นตามสายงานวิจัย (J Spectroscopy, I Electrochemistry, K Microscopy, M Materials)
