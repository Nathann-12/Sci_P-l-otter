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
  Baseline ปัจจุบัน: **159 passed, 3 skipped**
- **เปิดแอป (GUI):** `.venv/Scripts/pythonw.exe main.py` (หรือ `python main.py`)
- **smoke import:** `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "import main; main.MainWindow"`
- ถ้า dependency หาย: `.venv/Scripts/python.exe -m pip install -r requirements.txt`

## สถาปัตยกรรม
`main.py` (~675 บรรทัด) เป็น **thin shell**: imports/setup, `MainWindow.__init__` (ประกอบ UI: shell + MDI workspace + Project Explorer + docks), การ wire สัญญาณ, helper เล็ก (`_show_status`/`_icon`/`show_about`/`resizeEvent`/`_refresh_workbook`), `main()`
`MainWindow` ประกอบจาก **mixin 18 ตัว** (logic อยู่ใน mixin ไม่ใช่ใน main.py) — รวม `main_window_view_access_mixin` (view seam: `notify`/`ask_choice`/`selected_x_column`/`active_axes`):

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
| `main_window_gassensor_mixin` | โมดูล Gas Sensor (rail context + เมนู): response/t90, ตรวจรอบแก๊ส, calibration+LOD, dilution — logic ใน `analysis/gas_sensor.py` |

**ชั้น UI (โมเดล OriginPro เต็มรูปแบบ — สำคัญ)**
- **UX ทั้งแอปยึด loop แบบ Origin** (ดู [docs/UX_FLOW.md](docs/UX_FLOW.md) — บังคับสำหรับฟีเจอร์ใหม่): เปิดไฟล์/พิมพ์ใน Book → เลือกคอลัมน์บนชีต → คลิกไอคอนพล็อต (แถบล่าง) → **Graph window ใหม่เสมอ**; ไม่มีแผงซ้าย — Worksheet + Plot toolbar + Project Explorer + เมนู เท่านั้น; **ห้ามซ่อนความสามารถหลักไว้ใน dock/panel ที่ปิดอยู่**
- **Multi-book แบบ Origin**: 1 ไฟล์ = 1 Book (เปิด/ลากไฟล์ → `_stage_insert` → `_open_book_for_dataset`); คลิกหน้าต่าง Book = สลับข้อมูล (`MdiWorkspace.bookActivated` → `_on_book_activated` ตั้ง `self.workbook`/`self._df`); DataFrame ของแต่ละ Book อยู่ที่ `WorkbookWidget.source_df` + registry `_datasets` (session ใช้ตัวนี้)
- **workspace กลาง = MDI** ([UI/mdi_workspace.py](UI/mdi_workspace.py) `MdiWorkspace`) — Book/Graph เป็น QMdiSubWindow ลอยได้แบบ Origin. `MdiWorkspace` **เลียนแบบ API ของ TabManager** และถูกตั้งเป็น `self.tabs` → โค้ดพล็อต (plot/plotcore/view mixin) reuse ได้โดยไม่ต้องแก้. กราฟใหม่ = `self.tabs.add_tab()`; worksheet = `add_book()`. **อย่าเขียนโค้ดพล็อตให้ผูกกับ QTabWidget** — ใช้ API ของ `self.tabs`
- **worksheet แบบ Excel** ([widgets/workbook.py](widgets/workbook.py) `WorkbookWidget`) — แถว Long Name/Units/Comments/F(x)=; **หัวคอลัมน์ถือ designation แบบ Origin** (`A(X)`/`B(Y)`/`C`=Disregard, คลิกขวาหัวคอลัมน์ → Set As, โหลดไฟล์แล้วคอลัมน์เวลาเป็น X อัตโนมัติ); แถบเครื่องมือ/คลิกขวาบนชีต emit `use_data_requested`/`plot_requested`/`overlay_requested` → `adopt_workbook_data` (data mixin) / `plot_from_workbook(style, new_graph)` (plot mixin — เส้นทางพล็อตจากชีตทั้งหมดรวมที่นี่)
- **hidden state-holders (หนี้เทคนิค)**: `_panel_left` + `CompactPlotPanel` ถูกสร้างแบบซ่อนเพื่อรักษา aliases (`cbX/cbY/spLineWidth/chkMarker/btnLine/...`, `lblFile`, `chkCross`, `btnBoxZoom`) ที่ logic เก่ายังอ่าน/เขียน — อย่าลบจนกว่าจะ decouple logic ออกจาก widget เสร็จ; activity rail ซ่อนอยู่จนกว่าจะมี context ลงทะเบียน (โมดูลเฉพาะทางในอนาคต)
- **Project Explorer** ([UI/project_explorer.py](UI/project_explorer.py)) — dock ซ้าย ต้นไม้ Book/Graph, sync ผ่าน signal `subWindowAdded/Removed/Renamed` ของ `MdiWorkspace`
- **shell/docks** — `UI/shell/app_shell.py` (activity rail + command palette Ctrl+K), `UI/docks/` (AI/Log), `UI/welcome.py`, `widgets/activity_rail.py`, `widgets/command_palette.py`
- **ธีม** — ฐานคือ **qdarktheme** (ตั้งใน `styles/theme.py::apply_theme_from_config`) + override `shell.qss`/`sidepanel.qss`/`toolbar.qss`; ไอคอนใช้ **qtawesome** ผ่าน `_icon()` (map ที่ `_QTA_ICON_MAP` ใน main.py). **สีทั้งแอปมี source of truth เดียว** = `styles/theme.py::DARK_CUSTOM_COLORS` (accent `#4F9CF9`, bg `#1e2126`, border `#3a3f44`) — QSS ทุกไฟล์/สีฝังใน widget ต้องอยู่ family นี้; title bar ของ QMdiSubWindow คุมด้วย `selection-background-color` ใน `_MDI_STYLESHEET` (ไม่ใช่ QPalette เพราะ QStyleSheetStyle ทับ)
- **view-access seam** ([main_window_view_access_mixin.py](main_window_view_access_mixin.py)) — logic เรียก `self.notify/ask_choice/selected_x_column/active_axes` แทนแตะ widget ตรง (ทำให้สลับ UI ได้)

**โมดูล/แพ็กเกจอื่น**
- `core/` — `plot_data` (เตรียมข้อมูลพล็อต), `plot_mode` (enum PlotMode), `session`, `units`, `logging_setup`
- `widgets/` — `plot_tabs` (PlotCanvas/GraphTab/TabManager/CompactPlotPanel), `workbook`, `layer_manager`, `color_button`, `mpl_preview`, `activity_rail`, `command_palette`
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
