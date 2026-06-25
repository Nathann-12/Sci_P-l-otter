# CLAUDE.md — คู่มือสำหรับ AI ที่ทำงานกับโปรเจคนี้

> อ่านไฟล์นี้ก่อนเริ่มงานทุกครั้ง แล้วทำตามกติกาในนี้อย่างเคร่งครัด

## โปรเจคนี้คืออะไร
**SciPlotter** = เครื่องมือเดสก์ท็อปวิเคราะห์/พล็อตข้อมูลวิทยาศาสตร์ (PySide6 + Matplotlib + pandas/numpy/scipy)
เป้าหมายระยะยาว: เป็น **Research OS สำหรับนักวิจัยไทย** — เปิดข้อมูล → วิเคราะห์ → ทำกราฟ → โมดูลเฉพาะทาง → เขียนรายงาน → reproduce ได้
ขอบเขตฟีเจอร์ทั้งหมด + สถานะปัจจุบัน อยู่ใน **[ROADMAP.md](ROADMAP.md)** (แหล่งความจริงเดียว)

## วิธีรันและทดสอบ (สำคัญ — ใช้ interpreter ตัวนี้เท่านั้น)
- venv ของโปรเจคคือ `.venv/Scripts/python.exe` (Python 3.11.9) — **อย่าใช้ `py`/`python` ระบบ** (เคยพังเพราะ venv เก่าชี้ interpreter ที่ถูกลบ; ดู `memory/env-and-run.md` ฝั่งผู้ใช้)
- **รันเทสต์ (headless):**
  ```bash
  QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/ -q
  ```
  Baseline ปัจจุบัน: **97 passed, 3 skipped**
- **เปิดแอป (GUI):** `.venv/Scripts/pythonw.exe main.py` (หรือ `python main.py`)
- **smoke import:** `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "import main; main.MainWindow"`
- ถ้า dependency หาย: `.venv/Scripts/python.exe -m pip install -r requirements.txt`

## สถาปัตยกรรม
`main.py` (~570 บรรทัด) เป็น **thin shell** เท่านั้น: imports/setup, `MainWindow.__init__`, การ wire สัญญาณ, helper เล็ก (`_show_status`/`_icon`/`show_about`/`resizeEvent`), `main()`
`MainWindow` ประกอบจาก **mixin 16 ตัว** (logic อยู่ใน mixin ไม่ใช่ใน main.py):

| Mixin | หน้าที่ |
|---|---|
| `main_window_data_mixin` | โหลดไฟล์, คอลัมน์, datetime/numeric, `_get_xy` |
| `main_window_plot_mixin` | คำสั่งพล็อต (line/scatter/histogram/bar/overlay) |
| `main_window_plotcore_mixin` | เครื่องวาด: `apply_plot`, axes/canvas, theme, `change_plot_style`, `refresh_plot` |
| `main_window_fit_mixin` | curve fitting |
| `main_window_export_mixin` | export CSV/PNG/FFT |
| `main_window_session_mixin` | staging, save/restore session, closeEvent |
| `main_window_spectrogram_mixin` | spectrogram dialog + handlers |
| `main_window_view_mixin` | zoom/crosshair/clear/tab view |
| `main_window_menu_mixin` | สร้างเมนู (`_init_menu`) + docks/managers |
| `main_window_toolbar_mixin` | สร้าง toolbar + styling + responsive |
| `main_window_panels_mixin` | left panel + inspector tabs + layer manager |
| `main_window_analysis_mixin` | cross-correlation + peak detection |
| `main_window_equation_mixin` | พล็อตจากสมการ |
| `main_window_settings_mixin` | config load/save + Settings dialog |
| `main_window_features_mixin` | feature_add_*, FFT, report, units, derived column |
| `main_window_actions_mixin` | dispatcher (on_action_*), dataframe accessors, drag&drop |

**โมดูล/แพ็กเกจอื่น**
- `core/` — `plot_data` (เตรียมข้อมูลพล็อต), `plot_mode` (enum PlotMode), `session`, `units`, `logging_setup`
- `widgets/` — `plot_tabs` (PlotCanvas/GraphTab/TabManager/CompactPlotPanel), `layer_manager`, `color_button`, `mpl_preview`
- `dialogs/` + `dialogs_*.py` — กล่องโต้ตอบต่าง ๆ
- `processors.py` (สัญญาณ/feature), `loaders.py` + `file_io.py` (อ่านไฟล์), `analysis/fitting.py` (โมเดล fit)
- `read_mms_cdf.py` (อวกาศ/CDF), `peaks.py`, `crosscorr.py`, `eqplot.py`/`eqplot3d.py`, `annotations.py`, `report_generator.py`, `three_d_view.py`, `charts_gallery.py`

## กติกาการทำงาน (บังคับ)
1. **เสร็จแล้วต้องอัปเดต 2 ที่เสมอ:** (ก) ติ๊กสถานะใน [ROADMAP.md](ROADMAP.md) เป็น `✅` (ข) เพิ่ม/อัปเดตเทสต์ใน `tests/`
2. **เทสต์ต้องเขียวก่อนถือว่าเสร็จ** — รันชุด headless ข้างบน อย่าทิ้งให้แดง
3. **อย่าทำให้ main.py อ้วนอีก** — logic ใหม่ไปอยู่ mixin/โมดูลที่เหมาะสม; main.py เป็น shell เท่านั้น
4. **ห้าม bare `except:`** และเลี่ยง `except Exception: pass` แบบเงียบ — ให้ `logger.debug(..., exc_info=True)` อย่างน้อย
5. **refactor = pure move** — ห้ามแก้พฤติกรรมเงียบ ๆ ระหว่างย้ายโค้ด
6. เทสต์ปัจจุบันส่วนใหญ่เป็น **structure test** (เช็คการต่อสาย) — ฟีเจอร์ใหม่ต้องมี **behavioral test** (เช็คผลลัพธ์จริง) ด้วย
7. commit ทีละหน่วยงานที่มีความหมาย; **อย่า push** เองเว้นแต่ผู้ใช้สั่งชัดเจน (push เข้า `main` ถูก guard ไว้)

## สูตรเพิ่มฟีเจอร์ (ทำตามแพทเทิร์นเดิม)
ฟีเจอร์ใหม่ปกติ = 4 ชิ้น:
1. **logic** — ฟังก์ชันคำนวณบริสุทธิ์ใน `processors.py`/`analysis/`/`core/` (unit-test ได้)
2. **dialog** (ถ้ามี UI input) ใน `dialogs/`
3. **method ใน mixin** ที่เหมาะ (หรือสร้าง mixin ใหม่ถ้าเป็นโดเมนใหม่ เช่นโมดูลเฉพาะทาง) — ทำหน้าที่ต่อ UI เข้ากับ logic
4. **wire action** ในเมนู/toolbar (`main_window_menu_mixin` / `main_window_toolbar_mixin`)
5. **test** ใน `tests/` + ติ๊ก ROADMAP

> โมดูลเฉพาะทางใหม่ (Gas Sensor, Electrochemistry, ฯลฯ) ควรเป็น mixin/แพ็กเกจของตัวเอง + logic แยกเป็นโมดูลบริสุทธิ์เพื่อ test ง่าย

## หนี้ทางเทคนิคที่ควรรู้ (ก่อนรื้อใหญ่)
- logic ยังผูกกับ Qt widget โดยตรง (เช่น `self.cbX.currentText()`, `QInputDialog`, `self.statusBar()`) → ถ้าจะ "เขียน UI ใหม่" ต้อง **decouple logic ออกจาก widget** ก่อน
- behavioral test ยังบาง — เป็นความเสี่ยงหลักเวลารื้อใหญ่
- `except Exception: pass` ยังเหลือเยอะนอกโซน data-loading
- บั๊กแฝง: `_cg_get_fig` ใน `main_window_menu_mixin` อ้าง `ax` ที่ไม่ได้นิยาม (เส้นทาง Charts Gallery)
