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
- ✅ Publication journal presets — complete one-click styling, not just font sizes (IEEE/Nature/Science/ACS/Thesis: open spines, tick direction, minor ticks, font family, CB-safe palette + line width — Format Graph → Presets)
- ✅ Scientific color palettes — 8 curated (5 colorblind-safe: Okabe-Ito, Tol Bright/Muted/Vibrant, Viridis) one-click recolour of all series (Format Graph → Color palette; AI `format_graph palette/colorblind`)
- ✅ Save figure template (Format Graph → Presets && Templates)
- ✅ Area fill / band (under curve หรือ between curves), value labels บนจุดข้อมูล (auto-thin), error bars แบบ constant/percent ต่อ curve (Lines tab; AI `format_graph fill/value_labels/errorbars`)
- ✅ Zoom inset panel พร้อม region indicator (Inset && Colorbar tab; AI `format_graph inset`)
- ✅ Colormap + colorbar styling สำหรับ heatmap/image (curated CVD-safe colormaps; AI `format_graph colormap/colorbar`)
- ✅ Pick-to-edit: Ctrl+ดับเบิลคลิกบนเส้น → เปิด Plot Details ที่ curve นั้นทันที
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
- ✅ One-sample / Welch / pooled / paired t-tests
- ✅ One-way and Type II/III two-way ANOVA
- ✅ Mann-Whitney / Wilcoxon / Kruskal-Wallis nonparametric tests
- ✅ Shapiro-Wilk and Levene assumption checks
- ✅ Effect sizes, confidence intervals, and multiple-testing correction
- ✅ Multiple linear regression with influence and residual diagnostics
- ✅ Linear regression
- ✅ Polynomial regression
- ✅ Exponential fit
- 🟡 Power law fit
- ✅ Gaussian fit
- 🟡 Lorentzian fit
- ✅ Voigt fit
- ✅ Sine fit
- 🟡 Damped sine fit
- 🟡 Logistic fit
- ✅ Custom equation fit
- ✅ Multi-peak fitting (Gaussian/Lorentzian/Voigt, simultaneous fit, bounds, CI, residuals)
- ✅ Global fitting (shared/local/fixed/bounded parameters, weights, covariance, CI, residual diagnostics)
- ✅ Fit constraints (shared, dataset-local, fixed, bounded, and initial values)
- ✅ Fit bounds
- ✅ Weighted fitting (absolute uncertainty σ or inverse-variance weight 1/σ²)
- 🟡 Residual plot
- ✅ R²
- ✅ RMSE
- ✅ Chi-square (reduced χ²)
- ✅ Confidence interval (95% fitted-curve band + parameter standard errors)

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
- ✅ Analysis Recipe dependency graph (Auto / Manual / Frozen recalculation)
- ✅ Last-good result rollback + source/result checksum + node provenance
- ✅ Recipe persistence in schema-v2 projects and Project Explorer
- ✅ Batch Analysis (recipe → many files → CSV/JSON/XLSX/HTML summary)
- ✅ Project snapshot
- ✅ Undo/redo (annotations)
- ✅ Compare versions
- ✅ Audit trail (history + checksum + op log; session-level, not immutable)

## G. AI Assistant — 🟡 local tool-using assistant ทำงานแล้ว (Ollama; ตัวสร้างความต่างหลัก)
- ✅ Local AI backend (`ai/` — tool registry + agent loop + Ollama client, no extra deps)
- ✅ Tool-using agent (JSON protocol + `format:json`, ทำงานบนโมเดลเบา 2B ได้)
- ✅ ต่อเข้า AI dock จริง (threaded, ไม่ freeze UI) + config เปลี่ยนโมเดลได้
- 🟡 สั่งงานด้วยภาษาไทย (plot/analyze/columns/peaks ใช้ deterministic fast path; งานปลายเปิดผ่านโมเดล)
- 🟡 สั่งงานด้วยอังกฤษ
- ✅ "ทำกราฟให้หน่อย" (tool `plot_columns` — deterministic ไทย/อังกฤษ, explicit X/Y, verified Graph creation)
- ✅ แปลผล/สรุปข้อมูลจริง (tool `summarize_data` + `list_columns` + `describe_data` — shape/missing/statistics/max/correlation/prominent peaks และ XRD caveat โดยไม่พึ่งโมเดล)
- ✅ Fit/Smooth/Filter ผ่าน AI (tools `fit_curve`—รวม weighted fit + χ²/CI metrics—`list_fit_models` + `smooth_data` + `filter_signal`)
- ✅ Transform/Clean ผ่าน AI (tools `moving_average` + `fill_missing` + `interpolate` + `normalize` + `detrend` + `remove_outliers` + `remove_duplicates` + `sort_data`)
- ✅ Signal analysis ผ่าน AI ครบชุด (tools `run_fft` + `power_spectrum` + `autocorrelation` + `instantaneous_frequency` + `harmonic_analysis` + `envelope` + `signal_quality`)
- ✅ โมดูลเฉพาะทางผ่าน AI (tools `gas_response` + `cv_peaks` + `tafel_analysis` + `raman_dg` + `normalize_spectrum` + `iv_conductivity` + `arrhenius` + `ohms_law` + `rc_time_constant` + `pendulum_gravity` — logic ใน `ai/module_tools.py`)
- ✅ Peak/Cross-correlation ผ่าน AI (tools `peak_metrics` + `detect_peaks` + `cross_correlation`)
- ✅ Graph decoration + advanced charts ผ่าน AI (tool `format_graph` — title/labels/grid/legend/log + **journal_preset/palette/colorblind/line_width** สั่ง "ทำให้พร้อมตีพิมพ์ Nature + colorblind-safe" ได้; `list_charts` + `plot_chart` — 45 chart types)
- ✅ Multi-book awareness (tool `list_books` — AI รู้จัก Books ที่เปิดอยู่ + ตัว active)
- ✅ เปิดไฟล์ผ่าน AI (tool `open_file`) + ควบคุม Gas Live (tool `gas_live_control`)
- ✅ Scientific Suite ผ่าน AI (tools `run_statistics` [t-test/ANOVA/nonparametric/regression] + `global_fit` + `analyze_peaks` + `list_analysis_recipes` — logic ใน `ai/scientific_tools.py`, เรียก adapter เดียวกับ UI/recipe/batch) — รวม **48 AI tools**
- ✅ Chat กับ dataset (หลาย tool ต่อเนื่องบน active Book ได้จริง)
- ✅ "Fit peak นี้" (tool `analyze_peaks` — baseline + multi-peak Gaussian/Lorentzian/Voigt, รายงาน peak count/R²/convergence)
- ✅ "หา anomaly" (tool `find_anomalies` — deterministic z-score/IQR, รายงาน count + ตำแหน่ง/ค่า/z-score แบบ read-only ไม่แก้ข้อมูล; logic `analysis/cleaning.summarize_anomalies`)
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
- ✅ Chat กับ dataset (21 tools ต่อเนื่องบน active Book; เหลือขยาย tool signal/dataset ต่อ)

## H. Gas Sensor Module — 🟡 live acquisition + แกนวิเคราะห์พร้อมใช้ ⭐ (Modules → Gas Sensor)
- ✅ Real-time serial data จาก ESP32 (receive-only JSON Lines / CSV header)
- ✅ NI USB DAQ live analog input ผ่าน NI-DAQmx (device/channel discovery, RSE/Differential/NRSE, 1–20 Hz, selectable voltage range)
- ✅ Visual Acquisition Flow แบบ LabVIEW-inspired (ลากสาย output→input ได้จริง, replace/delete wire, DAG/loop/schema validation, node palette + bypass, presets/inspector; Voltage Divider และ Moving Average ประมวลผลทุก sample จริงก่อนเข้า Live Book/Graph)
- ✅ NI-DAQ multi-channel selection (เลือก `ai0..aiN` หลายช่องพร้อมกันและสร้าง voltage column แยกต่อ channel)
- ✅ Full multi-sensor live workflow (alias ต่อช่อง, Voltage Divider/Moving Average แยกรายเซ็นเซอร์, multi-select rolling Graph สูงสุด 8 เส้น และเก็บ raw + derived columns ครบ)
- ✅ Serial port monitor (QtSerialPort + raw 200-line view)
- ✅ Live resistance plot
- ✅ Live voltage plot
- ✅ Live temperature plot
- ✅ Live humidity plot
- ✅ Gas exposure marker (บันทึกใน Book/Graph ไม่ส่งคำสั่งกลับ ESP32)
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
- ✅ Peak fitting workflow (baseline, detection, simultaneous fit, summary, curves, batch recipe)
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
- 🟡 Command palette (Ctrl+K — deduplicated + menu-context tagged)
- ✅ Keyboard shortcuts
- ✅ Scalable activity rail / module dock
- ✅ Parked side tabs for Project Explorer / Messages Log / AI Assistant
- ✅ Clean sheet-first startup (no default Graph1, modules hidden by default)
- ✅ Compact Settings dialog with real theme/font/plot-mode persistence
- ✅ Origin-style action enablement (toolbar commands dim until data/graph is ready)
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
- 2026-07-18: Decoration suite completed — area fill (under / between curves, auto or custom colour), data value labels (format + every-Nth + auto-thin ≤200), constant/percent Y error bars (single gid-tagged container, replace-not-stack), a zoomed **inset panel** with `indicate_inset_zoom` region marker (handles the matplotlib ≥3.10 `InsetIndicator` API), and colormap/colorbar styling for heatmap-like plots (curated CVD-safe `COLORMAPS`). All state is remembered on the artists/axes (`_ps_deco` / `_ps_inset_cfg` / `_ps_colorbar_cfg`) so `read_style`/`read_line_style` report reality — the dialog reopens showing it and **Cancel reverts it**; `list_line_artists` now excludes `_ps_`-tagged decoration artists so palettes/Lines tab never touch error-bar caps or reference lines. New Plot Details groups (Area fill / Error bars / Value labels on Lines; new Inset && Colorbar tab) ride the existing live-preview + diff-apply contracts, and **Ctrl+double-click on a curve opens Plot Details focused on that curve** (pick-to-edit). AI `format_graph` gains `fill/fill_alpha/value_labels/label_format/errorbars/inset/inset_xmin/inset_xmax/colormap/colorbar/colorbar_label` — still one tool, registry stays 48, no corpus re-seal. New `tests/test_plot_decorations.py` (12) + dialog/AI/pick-to-edit/revert tests; consolidated decoration+AI suite `251 passed`; visual 3-panel demo verified.
- 2026-07-18: Live preview for Plot Details — edits redraw the graph instantly, no Apply button. Every control (text/spin/checkbox/colour/palette) feeds a 180 ms debounce that reuses the existing diff-apply path, so only what changed restyles and identity edits stay no-ops; the "which curve" / preset / template pickers are excluded (they only repopulate), programmatic loads are guarded against feedback loops, and a pending redraw is cancelled when the dialog closes. Because live preview commits as you type, **Cancel now restores the pre-edit snapshot** (`_restore_plot_details`). A "Live preview" checkbox (default on) lets power users fall back to manual Apply. New dialog/mixin behavioral tests; verified end-to-end on a real MainWindow (edit + live palette recolour + revert). Origin still needs Apply/OK round-trips for the same edits.
- 2026-07-18: Graph decoration pushed past OriginPro. Added a scientific colour-palette system to `core/plot_style.py` — 8 curated qualitative palettes (5 verified colorblind-safe: Okabe-Ito, Tol Bright/Muted/Vibrant, Viridis) with `apply_palette()` recolouring every series in order, tinting markers and keeping the legend in sync. Rebuilt the journal presets from font-sizes-only into complete one-click publication styles (open top/right spines, tick direction, minor ticks, font family, grid off, a CB-safe palette + line width). Wired through the Plot Details **Presets** tab (palette picker, presets carry their palette) respecting the diff-apply no-op contract, and — the part Origin cannot do — extended the AI `format_graph` tool with `journal_preset` / `palette` / `colorblind` / `line_width`, so "make this Nature-ready and colorblind-safe" works from one chat command (no new tool → registry stays 48, no corpus re-seal). New `tests/test_plot_palettes.py` + dialog/mixin/AI behavioral tests; visual before/after verified.
- 2026-07-18: Scientific Suite exposed to the local AI assistant (CLAUDE.md rule 8). New `ai/scientific_tools.py` adds `run_statistics` (t-test / ANOVA / nonparametric / multiple regression), `global_fit`, `analyze_peaks` and `list_analysis_recipes`, each calling the same `analysis/scientific_operations` adapter the GUI/recipe/batch use — defensive, non-modal, opening result/curve Books and reporting significance or convergence. Registry now has **48 tools**; catalog routing gains a `science` group + Thai/English aliases. Because the tool registry changed, the local router's **sealed fine-tuning corpus was regenerated and re-sealed** end to end: curated seeds + release/router-v2 acceptance cases extended to cover the 4 new tools, the 11 committed JSONL artifacts regenerated, and the release-v3 (`190059aa…`), router-v2 acceptance-v4 (`59a716f8…`) and source-file hashes re-sealed (immutable consumed-v1/final-v2 gates preserved). New behavioral tests in `tests/test_ai_assistant.py`; `tests/test_training_pipeline.py` counts updated. Full suite: `1281 passed, 3 skipped` (only pre-existing broken-axis/peak-widths warnings).
- 2026-07-18: Dependency-aware Scientific Suite completed as one system (Statistics / Global Fit / Peak Analyzer → versioned Analysis Recipe → result Books + fit Graph → Batch). Pure engine in `core/analysis_recipe.py`, numerical cores in `analysis/{statistics,global_fitting,peak_analysis}.py`, one shared adapter in `analysis/scientific_operations.py` (UI, recipe, batch, and future AI all call the same ABI), batch runner in `analysis/batch.py`, and `main_window_scientific_suite_mixin.py` wiring the Analysis menu, Recipe Manager, Recalculate, and Batch dialogs; recipes persist in schema-v2 `.sciproj` and show in Project Explorer. **Deep-review fixes over the happy path:** (1) the recipe commit path called an **undefined `_output_warning`**, so every stats/fit run raised `AttributeError` → a modal error dialog in the GUI and a headless test *hang* (modal `exec()` under offscreen); defined it so a non-converged optimiser is marked **Warning**, not silently Clean. (2) `global_fit_report` now persists an explicit **Convergence** (success/message/level) section. (3) fit-curve CI columns carry the **real** confidence level (`ci_90_*` … not a hardcoded `ci95_*`). (4) locked the peak physical-width (sigma/gamma/tau bounds) and detection-width non-negativity guards with tests. Full 100-file suite: `1274 passed, 3 skipped` (only the existing broken-axis `tight_layout` warnings).
- 2026-07-15: UX pass — Origin-style action enablement + supporting fixes. Toolbar commands now **dim (disabled) instead of popping a reject dialog** when they can't run: data commands (plot/process/analysis/dataset) enable once the active Book has data — including data typed straight into the worksheet before "Use Active Data" (via `workbook.has_data_cells()` + `table.itemChanged` refresh) — and graph tools (format/crosshair/box-zoom/reset/export/annotate) enable once a Graph window exists; the shared QAction dims on every surface (top bar + docks) and keeps a "why" tooltip. State tracks live through `_wire_action_state_updates` (tab/book/itemChanged signals) and `_refresh_action_states` hooks. FFT/PSD now **auto-create a Graph on demand** (`_ensure_graph_canvas`) instead of rejecting when data is ready but no graph is open. Command Palette (Ctrl+K) is **deduplicated and menu-context tagged** (`FFT · Process › Frequency & Spectrum`, 407→349 entries), keeping a strong ref to every action so lifetime is unchanged. Worksheet columns **auto-size to their content** (bounded) so long names/values aren't clipped to `...`; the module context panel widened 200→320px so the Gas Sensor panel isn't truncated; and Set X/Y/Ignore/Delete with no selection now emit a **status-bar hint** instead of silently doing nothing. The Equation Plotter dialog was also reworked for usability: concise placeholder + **quick-insert example chips** + a function/variable reference line, grouped **Domain** (X min/max/Points on one row) and **Options** boxes, **Plot** as the primary/default button with **Ctrl+Enter** to plot, and Plot disabled until an expression is entered (`get_values()` contract unchanged). New `tests/test_action_enablement.py`, `tests/test_equation_dialog.py` + workbook tests. Full 92-file suite: `925 passed, 3 skipped` (only existing broken-axis `tight_layout` warnings).
- 2026-07-15: Full multi-sensor Gas Live workflow completed without hardware access. Each Serial/NI-DAQ field can now be mapped to a unique sensor display name with independent voltage-divider topology/reference/supply and moving-average window; raw inputs remain intact and all named/derived values are appended to the Live Book. The Live monitor uses an 8-signal checklist and the dedicated rolling Graph keeps one stable line per selected sensor. NI channel discovery exposes the future Book field names to the Flow Designer before Connect, settings round-trip through QSettings, and AI `configure_flow` accepts `sensor_channels`. Focused multi-sensor/controller/UI/MainWindow/AI coverage: `103 passed`; full 90-file suite: `911 passed, 3 skipped` (only existing broken-axis `tight_layout` warnings).
- 2026-07-14: Visual Acquisition Flow v2 free wiring + NI-DAQ multi-channel completed without hardware access. The canvas now creates wires by dragging an output port onto an input port, atomically replaces a target's existing wire, deletes wires on double-click, supports processor palette add/remove plus Auto Wire/Clear, and surfaces invalid wiring. Pure validation rejects unknown/self/multi-input/loop graphs and requires the source to reach both Book and Graph; acquisition is blocked while the visible canvas is invalid. Execution is topology-aware and runs only enabled processors on the productive source→Graph path, so bypassed/dead-end nodes do not alter records. Valid wiring persists and is controllable through AI `configure_wiring`. NI-DAQ UI now multi-selects discovered AI channels, persists comma-separated channel sets, and produces one voltage column per channel; controller multi-channel batching remains lossless. Windows visual QA and full 90-file suite: `906 passed, 3 skipped`.
- 2026-07-14: LabVIEW-inspired Visual Acquisition Flow completed for Gas Sensor Live. Added a non-modal dark node canvas with draggable input/Voltage Divider/Moving Average/Live Book/Rolling Graph nodes, live Bézier wires, grid/zoom/fit/reset, presets, field-aware inspector, and running-state lock. The canvas is executable: pure `GasFlowProcessor` converts voltage-divider samples for sensor high/low-side circuits, keeps invalid rail/missing samples as `None` without dropping rows, maintains moving-average state across controller batches, appends derived columns to every Live Book row, and selects the smoothed output for the rolling graph. Config persists without auto-running; both Serial and NI-DAQ use the same pipeline; AI `gas_live_control` supports `flow_status` and `configure_flow`. Windows visual QA plus behavioral coverage for math, canvas interactions, menu, MainWindow, settings/schema lock, Book/Graph, and AI. Full 90-file suite: `899 passed, 3 skipped`.
- 2026-07-14: NI USB DAQ live acquisition added to Gas Sensor Live. The shared Live panel now switches between ESP32 Serial and NI-DAQmx analog input, discovers devices/AI channels, configures 1–20 Hz hardware-timed continuous sampling, voltage range, and RSE/Differential/NRSE terminal mode, drains every available sample into the existing all-sample Live Book/rolling Graph pipeline, preserves app-only Gas markers, and handles missing Python package/driver, unplug, disconnect, and window-close cleanup without affecting Serial mode. `gas_live_control` now connects/statuses either transport non-modally. Validated against the installed nidaqmx 1.5 API (`DIFFERENTIAL` UI maps to the API's `DIFF` enum) plus fake USB-6008 behavioral coverage. Full 88-file suite: `888 passed, 3 skipped`.
- 2026-07-14: Gas Sensor Live Acquisition v1 completed. Added receive-only ESP32 serial acquisition through `QSerialPort`, fragmented-stream JSON Lines/CSV-with-header auto-detection with a session-locked schema, 200 ms controller batching, all-sample Live Books, dedicated rolling 2,000-point Graphs at no more than 5 FPS, Gas ON/OFF app-only markers, latest sensor readouts, a 200-line raw monitor, persisted port/baud without auto-connect, safe disconnect/error/window-close flushing, and non-modal AI `gas_live_control` actions. Parser, controller, panel, MainWindow session lifecycle, worksheet streaming append/lock, markers, reconnect, and AI behavior are covered. Full 87-file suite: `880 passed, 3 skipped`.
- 2026-07-14: Weighted nonlinear fitting + scientific metrics completed. `Nonlinear Curve Fit` now has an explicit uncertainty/weight contract: either absolute uncertainty `σ` or inverse-variance weights `1/σ²`; unweighted mode truly ignores the auxiliary column instead of silently dropping its NaN rows. Fixed the inverted `1/σ²` conversion, aligned reduced χ² with the effective uncertainty, kept absolute covariance/parameter standard errors, persisted the exact weighting mode/column in fit reports, and exposed weighted fitting non-interactively through the existing AI `fit_curve` tool. Verified Voigt + bounds + 95% confidence bands and dialog wiring with behavioral tests. Full 85-file suite: `863 passed, 3 skipped`.
- 2026-07-13: Can now discard the first/only graph. `MdiWorkspace` inherited a TabManager "keep at least one tab" veto — `_detach_graph`/`_remove_tab_by_id` refused to close the last graph, so a wrong first plot was stuck on screen. Since the app is sheet-first (0 graphs is the startup state), the veto is removed: any graph, including the only one, can be closed via the title-bar X; `count()` goes to 0 and the next plot re-creates a graph. Verified end-to-end (plot → close only graph → count 0, no crash → re-plot works); updated the MDI workspace test to assert the discard.
- 2026-07-13: Smooth "did nothing" fixed — every column-adding transform (Smooth, Moving Average, Butterworth, Fill Missing, Interpolate, Normalize, Detrend, Apply Window, and the AI column tools) committed the new column only to the hidden DataFrame/cbY combo; the visible Origin Book never updated, so on screen nothing happened. Fixed at the view-access seam: `add_y_column_option` now also runs `_sync_dataframe_after_column_edit()` (worksheet follows every new column, designations preserved) — one fix covers all current and future callers. Verified end-to-end on a real MainWindow (menu QAction → new column visible on the sheet + actually smoother); behavioral regression test added.
- 2026-07-13: Analysis UX audit pass — built an exploratory harness that triggers all Analysis-menu actions on a real MainWindow with modals captured (72 actions initially). Found + fixed: (1) plot commands died with a Thai "ไม่มีแท็บ" warning when no Graph window existed (sheet-first startup!) — `_get_current_plot_tab_ids` now auto-creates the Graph per the Origin loop; (2) Merge by Timestamp crashed on pandas 2.x mixed datetime64 resolutions (ns vs s) — keys normalized to [ns]; (3) menu duplication removed — Descriptive/Covariance ×2, Peak Metrics ×2, Signal Quality ×3, Nonlinear Fit ×2, whole "Peak Detection" submenu duplicating "Peaks and Baseline", and fake "1/2/3 <default>" recent items; every command now has exactly one home in the categorized submenus (72 → 58 actions), `actPk*`/`actNonlinearFit` attributes preserved for toolbar/tests. Re-audit: 58 actions, 0 problems. Regression tests added (auto-create graph, mixed-resolution merge, dedup structure).
- 2026-07-13: Origin-style Analysis fitting fixed. Two real bugs made "Fit" unusable: (1) `_do_curve_fit` computed R²/RMSE from the 400-point fit curve but compared it to the original samples → `operands could not be broadcast` on every model → a modal "Fit failed" box popped and no curve drew; (2) `_open_fit_dialog` read a stale `self.canvas` instead of resolving the selected graph, so the fit targeted the wrong graph. Now the fit metrics use the sample-length prediction and the dialog syncs to the selected/last-selected graph via `_active_canvas()` (same graph-scoped contract as FFT/PSD/Format Graph); the fitted curve draws on the graph you selected. Added graph-scoped + metrics regression tests in `test_toolbar_mdi_targets.py`. Full suite `854 passed, 3 skipped`, 0 crash frames.
- 2026-07-13: AI anomaly detection ("หา anomaly") added as tool `find_anomalies` (43 AI tools total): pure `analysis/cleaning.summarize_anomalies` reuses `detect_outliers` (z-score/IQR) and reports count + most-extreme points (row index/value/z-score) read-only without changing data. Added pure-logic tests (`test_cleaning.py`) + behavioural AI-tool tests (`test_ai_assistant.py`). Full suite green.
- 2026-07-09: Spectroscopy module first production workflow pass added under Modules Gallery: baseline correction + normalization, peak table/FWHM/area, Raman D/G ratio, Tauc band gap, and XRD Scherrer size. Added pure analysis tests and MainWindow QAction/menu user-flow tests through real result Books/Graphs. Full suite: `715 passed, 3 skipped` with `-W error`.
- 2026-07-09: Materials Science module first production workflow pass added under Modules Gallery: I-V conductivity/resistivity/sheet resistance, Arrhenius activation energy, TGA/DSC thermal metrics, and sample ranking. Added pure analysis tests and MainWindow QAction/menu user-flow tests through result Books/Graphs. Full suite: `721 passed, 3 skipped` with `-W error`.
- 2026-07-09: Physics / General Lab module first production workflow pass added under Modules Gallery: Ohm's law fit, RC time constant, pendulum gravity fit, and power-product uncertainty propagation. Added pure analysis tests and MainWindow QAction/menu user-flow tests. Full suite: `727 passed, 3 skipped` with `-W error`.
- 2026-07-08: Electrochemistry module first production workflow pass added: rail context + top menu, pure analysis helpers for CV peaks, Randles-Sevcik/ECSA, Tafel, GCD supercapacitor metrics, and EIS Rs/Rct/Nyquist/Bode result data. Added MainWindow user-flow tests through real QAction/menu paths. Focused suite: `98 passed` with `-W error`.
- 2026-07-08: core module pass completed for dataset management, cleaning, harmonic analysis, reproducibility report/snapshot/compare/audit, English UI normalization, and Process menu workflow redesign. Added startup/test-suite optimization for Settings diff-apply, Qt test cleanup, cached toolbar icons, cached shell QSS, and quiet debug logging. Full suite: `687 passed, 8 skipped` in `224.36s / 0:03:44` with `-W error`.

---

## ลำดับความสำคัญที่แนะนำ (ปรับได้)
1. **ปูฐานก่อนรื้อใหญ่:** เพิ่ม behavioral tests คลุม flow หลัก + decouple logic↔Qt widget (ดู CLAUDE.md)
2. **Gas Sensor Module (H)** ⭐ — โมดูลขายจริง, รองรับทั้ง ESP32 serial และ NI-DAQmx
3. **Reproducibility (F)** + **AI Assistant (G)** — ตัวสร้างความต่างจากคู่แข่ง
4. เติมแกนกลางที่ขาด (filters ใน E, dataset management ใน A, สถิติใน D)
5. โมดูลเฉพาะทางอื่นตามสายงานวิจัย (J Spectroscopy, I Electrochemistry, K Microscopy, M Materials)
