# UX Blueprint — SciPlotter (โมเดล OriginPro)

> กติกาการออกแบบ UI/UX ของทั้งโปรเจค — ยึด **OriginPro เป็นต้นแบบเต็มรูปแบบ**
> เพราะ workflow ของมันพิสูจน์แล้วว่าใช้ง่าย ฟีเจอร์ใหม่ทุกตัวต้องเข้าโมเดลนี้

## Loop หลัก (แบบ Origin — จำง่าย ทำซ้ำได้)

```
เปิดไฟล์ / พิมพ์ข้อมูลใน Book  →  เลือกคอลัมน์บนชีต  →  คลิกไอคอนพล็อต  →  Graph ใหม่เด้งขึ้น
```

- **Worksheet (Book) คือศูนย์กลาง** — ข้อมูลทุกชุดคือ Book window หนึ่งบาน
  (**1 ไฟล์ = 1 Book** ชื่อตามไฟล์; พิมพ์เองใน Book1 ก็ได้)
- **คลิกหน้าต่าง Book ไหน = ใช้ข้อมูลชุดนั้น** (สลับได้จาก Project Explorer ด้วย)
- **กดพล็อต = Graph window ใหม่เสมอ**; "เพิ่มลงกราฟปัจจุบัน" เป็นคำสั่งแยก (คลิกขวา/เมนู Plot)
- **หัวคอลัมน์ถือ designation แบบ Origin**: `A(X)`, `B(Y)`, `C` (Disregard)
  คลิกขวาที่หัวคอลัมน์ → Set As X / Y / ไม่ใช้; โหลดไฟล์แล้วคอลัมน์เวลาถูกตั้งเป็น X อัตโนมัติ

## ที่อยู่ของแต่ละอย่าง

| สิ่งที่ผู้ใช้ต้องการ | อยู่ที่ไหน |
|---|---|
| เปิดไฟล์ข้อมูล | ปุ่ม Open บน toolbar / เมนู File / ลากไฟล์วาง → **ได้ Book ใหม่** |
| พิมพ์ข้อมูลเอง | Book1 + แถบเครื่องมือบนชีต (+แถว +คอลัมน์ / ใช้ข้อมูลนี้) |
| สลับชุดข้อมูล | คลิกหน้าต่าง Book หรือดับเบิลคลิกใน Project Explorer |
| กำหนดแกน X/Y | คลิกขวาที่**หัวคอลัมน์** → Set As X / Y / ไม่ใช้ |
| จัดการข้อมูล/คอลัมน์ของชีต | เมนู **Data** → Active Book / Columns / Units + Metadata / Quick Transforms / Clean Data |
| พล็อต | **function bar สองแถวด้านบน** (Line/Scatter/Line+Symbol/Column/Histogram/Gallery) หรือปุ่มบนชีต หรือคลิกขวา หรือเมนู Plot — ทั้งหมด = Graph ใหม่ |
| เลือกชนิดกราฟจากแคตตาล็อก | เมนู **Charts** ด้านบน → sidebar หมวด + thumbnail grid แบบ Origin; registry/basic advanced plots ให้เลือก mapping ข้อมูลก่อน แล้วเปิด Graph ใหม่ |
| เพิ่มเส้นลงกราฟเดิม | คลิกขวาบนชีต → "เพิ่มเส้นลงกราฟปัจจุบัน" / เมนู Plot → overlay |
| เครื่องมือกราฟ (crosshair / box zoom) | ปุ่มบน toolbar หลัก |
| จัดการหน้าต่าง Book/Graph | Project Explorer (parked side tab ซ้าย) + เมนู Window (Cascade/Tile) |
| การแปลง/ทำความสะอาดข้อมูล | เมนู Process (Data Cleaning / Filters / FFT / PSD) |
| สถิติ/วิเคราะห์/fit | เมนู **Analysis** → Statistics / Mathematics / Data Manipulation / Fitting / Signal Processing / Peaks and Baseline |
| รับข้อมูล Gas Sensor จาก ESP32/NI USB DAQ | **Modules → Gas Sensor → Live** → เลือก Serial (COM/baud) หรือ NI-DAQmx (device/AI channels หลายช่อง/rate/range/terminal) แล้ว Connect; ได้ Live Book + Graph ใหม่อัตโนมัติ |
| สร้าง pipeline รับข้อมูลแบบ LabVIEW | **Modules → Gas Sensor → Visual Acquisition Flow…** → เลือก preset/ตั้ง Voltage Divider และ Moving Average; ถ้ามีหลายตัวให้เพิ่ม Sensor Channel พร้อมชื่อและสูตรของแต่ละช่อง → กลับไป Live แล้ว Connect; raw + derived columns ลง Book จริง |
| จัดการ Layers ของกราฟ | Inspector ขวา (ของเสริม — toggle จาก toolbar/View) |

## กติกาสำหรับฟีเจอร์ใหม่ (บังคับ)

1. **Worksheet เป็นศูนย์กลาง** — ฟีเจอร์ที่กินข้อมูลเข้า/คายข้อมูลออก ต้องอ่าน-เขียนผ่าน
   Book ที่ active (`self._df` ตาม `bookActivated`) และผลลัพธ์ที่เป็นตารางควรเป็นคอลัมน์ใหม่/Book ใหม่
2. **ห้ามซ่อนขั้นตอนหลักใน panel ที่ปิดอยู่** — Inspector ใส่ได้เฉพาะของเสริม (layers/style)
3. **คำสั่งพล็อตใหม่ = Graph window ใหม่** เว้นแต่ผู้ใช้เลือก overlay เอง
4. การแปลงข้อมูล = เมนู Process, การวิเคราะห์ = เมนู Analysis — เพิ่มเป็น submenu ตามหมวด
5. **เลือกคอลัมน์เดียวต้อง plot คอลัมน์นั้นจริง** — ไม่ว่าจะเป็น `X` หรือ `Y` ให้ใช้แกน X เป็น `Row` 1..N แบบ Excel; ถ้าต้องการ X/Y ให้เลือกหลายคอลัมน์หรือใช้ designation โดยไม่เลือกคอลัมน์เดี่ยว
6. **โมดูลเฉพาะทาง (Gas Sensor ฯลฯ)** = activity ใหม่ใน activity rail แบบ module dock
   (`SP` header, `MODULES`, scrollable module cards, future slot); rail/context ต้องซ่อนตอน startup แม้มี context ลงทะเบียนแล้ว และเปิดแบบ explicit ผ่าน `AppShell.show_activity_context(...)`
7. **Project Explorer / Messages Log / AI Assistant** = parked side tabs ซ้ายสุดแบบเก็บข้างได้ ไม่ใช่ bottom dock; collapsed width = 24px; tab ใหม่ที่เป็น utility/future AI panel ให้ลงผ่าน `AppShell.add_side_panel(...)`
8. **Gas Sensor Live** = เลือก source เป็น Serial JSON Lines/CSV header หรือ NI-DAQmx analog input; ทุก sample ลง Live Book, เลือกหลายสัญญาณด้วย Ctrl-click เพื่อดู rolling Graph ร่วมกันได้สูงสุด 8 เส้น และ Gas ON/OFF marker เป็น annotation ในแอป ไม่ใช่คำสั่งควบคุมอุปกรณ์
9. **Visual Acquisition Flow** = config/wiring ต้อง valid ก่อน Connect; ลากจาก port ขวาไป port ซ้ายเพื่อ rewire, double-click สายเพื่อลบ, Auto Wire คืนเส้นทางมาตรฐาน; Sensor Channels ตั้ง alias, divider และ smoothing แยกต่อ input โดยไม่ลบคอลัมน์ดิบ; ระหว่าง acquisition ลาก/ดู node ได้แต่แก้ processor/wiring ไม่ได้ เพื่อรักษา schema ของ Live Book

## หมายเหตุทางเทคนิค (สำหรับคนแก้โค้ด)

- แผงซ้ายเดิม (`_panel_left`) และ `CompactPlotPanel` ยังถูกสร้างแบบ **ซ่อน** เพื่อ
  compatibility ของ column selection (`cbX/cbY`) และ legacy actions ที่
  analysis/session ยังใช้; plot style/histogram/export state ย้ายไป immutable
  request/options models แล้ว และ style aliases เดิมถูกถอดออก
- คำสั่ง line/scatter/overlay/histogram/bar รับ request models; visible-range
  export ใช้ pure request extractor จึงห้ามเพิ่ม dependency กลับไปที่ hidden widgets
- `plot_from_workbook()` ต้องเคารพ selection ก่อน designation fallback: single selected column ทุกชนิดใช้ row index request (`Row` 1..N) เพื่อไม่ plot คอลัมน์ข้าง ๆ โดยไม่ตั้งใจ; designated X ใช้กับ multi-column selection หรือไม่มี selection
- Toolbar ต้องเป็น function bar สองแถวด้านบน (`FunctionToolbarPrimary` + `FunctionToolbarSecondary`) แบบ Origin; icon-only ขนาด 16px, ทุก action ที่ไม่ใช่ separator
  ต้องมี `toolbarIconKey` ไม่ซ้ำกัน และต้องลง `toolbar_actions` เพื่อให้เทสต์กดปุ่มจริงได้; `plot_bar_actions` เป็น compatibility alias ของปุ่ม plot บน toolbar ด้านบน ไม่ใช่ bottom toolbar แยก
- คำสั่ง toolbar ที่แตะกราฟต้อง target Graph window ที่เลือกอยู่ หรือ Graph ล่าสุดที่ผู้ใช้เลือกเมื่อ Book โฟกัสอยู่
  (`MdiWorkspace` เก็บ last-selected Graph); ห้าม fallback ไป Graph 1 ตามตำแหน่ง เพราะทำให้ export/format/zoom/FFT ผิดกราฟ
- Format Graph / Plot Details live apply ต้องไม่เปลี่ยน live figure size หรือ DPI; preset ขนาดสิ่งพิมพ์ให้เก็บไว้สำหรับ export เท่านั้น และ graph effects เช่น shadow/glow ต้อง apply เป็น Matplotlib path effects บน artist จริง; tick-label display override และ reference-line label/width/opacity ต้อง apply ผ่าน `core.plot_style` schema
- เมนูฟังก์ชัน (`Process`, `Analysis`, `Plot`, `Export`, `Tools`/Workflow, `Annotation`, `Gas Sensor`) ต้องถูกทดสอบผ่าน `QAction.trigger()` กับ Book/Graph จริง:
  action ที่แตะข้อมูลใช้ active Book/worksheet, action ที่แตะกราฟใช้ selected/last-selected Graph และห้ามพึ่ง state panel/`self.canvas` ที่ค้างจากยุคกราฟเดี่ยว
- เมนู `Analysis` ต้องมี hierarchy แบบ Origin: `Statistics`, `Mathematics`, `Data Manipulation`, `Fitting`, `Signal Processing`, `Peaks and Baseline`; รายการในนี้ต้อง mirror ฟังก์ชันที่มี backend จริงเท่านั้น และ signal actions เช่น Decimation ต้องเปิดผลลัพธ์เป็น Book ใหม่เมื่อความยาวข้อมูลเปลี่ยน
- English UI contract: all new user-visible actions, dialogs, status messages, placeholders, and generated reports must be English-first. Legacy Thai/mojibake strings may pass through `core.english_ui.to_english()` at the view-access seam, but new code should not rely on runtime translation as a substitute for clear English labels.
- App-wide Qt event filters must be installed once per `QApplication`, not once per `MainWindow`; otherwise user-flow tests that create many windows and the Plot Gallery thumbnail flow slow down progressively.
- Activity rail (`widgets/activity_rail.py`) เป็นพื้นที่สำหรับ specialty module contexts เท่านั้น ไม่ใช่ที่ซ่อนคำสั่ง worksheet/plot หลัก; module ใหม่ต้องเพิ่มผ่าน `AppShell.register_context(...)` เพื่อได้ icon+label card/context page แต่ห้ามโชว์เองตอน startup, ให้เปิดด้วย `AppShell.show_activity_context(...)`
- MainWindow ต้องเริ่มแบบ sheet-first: `MdiWorkspace(start_with_graph=False)` ทำให้มี Book1 เท่านั้นและไม่มี Graph1 เปล่า; กราฟถูกสร้างเมื่อผู้ใช้สั่ง plot
- Parked side panels (`widgets/side_panel_tabs.py`) เป็นพื้นที่ utility ด้านซ้ายสุดสำหรับ Project Explorer, Messages Log และ AI Assistant; default ต้อง collapsed 24px, คลิก tab เพื่อเปิด/คลิกซ้ำเพื่อเก็บ, ส่วน bottom dock tabs ต้องซ่อนจนกว่าจะมี caller ใช้ `AppShell.add_dock(...)`
- Settings dialog ต้องเป็น compact utility ไม่ใช่ workspace: ขนาดเปิด `900x620`, แต่ละ tab scroll ได้, และทุก option ต้องผูกกับ runtime/persistence จริง เช่น theme QSS, Matplotlib font/style และ default plot mode
- เมนู `Data` ต้องเป็น workflow menu สำหรับ active Book/worksheet ไม่ใช่ legacy flat menu: `Active Book`, `Columns`, `Units + Metadata`, `Quick Transforms`, `Clean Data`; action ที่แตะชีตต้อง resolve ไปที่ Book ที่ active และต้องมี user-flow test ผ่าน `QAction.trigger()` เหมือน Process/Analysis
- เมนู Export มี `Batch Export Graphs...` สำหรับเซฟ Graph windows หลายอันพร้อมกัน;
  default ต้องข้าม Graph เปล่า, ใช้ options เดียวกับ Export Figure และตั้งชื่อไฟล์จาก title
  ของ Graph แบบ Windows-safe
- เมนู `Charts` ใช้ `widgets/chart_mega_menu.py` และ catalog จาก `plots.registry`;
  thumbnail ต้อง lazy render จาก example data ตอนเปิดเมนูเพื่อไม่เพิ่ม startup cost
  และต้องไม่ใช้ข้อมูลตัวอย่างตอนพล็อตจริง (พล็อตจริงอ่าน active Book เท่านั้น)
- Registry/basic advanced plots จาก `Charts` ต้องเปิด `PlotDataMappingDialog` ก่อนสร้าง Graph เพื่อให้ผู้ใช้เลือก Primary/X, Y series, Z และ Group ได้; ถ้า dialog ถูก cancel ต้องไม่สร้าง Graph เปล่า
- หมวด `Contour, Heatmap`: contour อ่าน XYZ จาก 3 numeric columns แรก;
  heatmap อ่าน numeric worksheet เป็น matrix และทั้งคู่เปิด Graph ใหม่ผ่าน Gallery seam
- หมวด `Multi-Column`: Stacked Lines/3D Waterfall ใช้ numeric column แรกเป็น X
  และคอลัมน์ถัดไปเป็นแต่ละ Y series; กราฟ 3D ต้องเปิด Graph ใหม่ด้วยแกน 3D
- หมวด `Multi-Panel, Multi-Axis`: Subplot Grid ใช้ numeric column แรกเป็น X และแยกทุก Y
  series เป็น panel ของตัวเอง; หลัง `fig.clf()` ต้องตั้ง `canvas.ax` กลับไปที่ axes ใหม่ตัวแรก
- หมวด `Specialized`: Polar Line/Polar Scatter/Wind Rose ใช้ `projection="polar"` ใน registry
  เพื่อให้ thumbnail และ Graph จริงสร้าง polar axes เหมือนกัน
- หมวด `Signal & Frequency`: Phase Plot, Nyquist และ Bode อยู่ใน Charts menu เดียวกับ Origin-style
  gallery; Frequency plots อ่าน alias มาตรฐาน (`frequency/freq`, `real/re`, `imag/im`,
  `magnitude/mag`, `phase`) แต่ยัง fallback เป็น numeric columns ลำดับแรกสำหรับ worksheet ทั่วไป
- เมนู `Process → Signal Transforms` เป็นที่อยู่ของ Hilbert, Envelope, Instantaneous Frequency,
  Auto-correlation, Convolution, Deconvolution, IFFT, STFT และ Zero Padding; output ที่ยาวเท่า
  Book ปัจจุบันต้องเพิ่มเป็นคอลัมน์ใหม่ใน Book เดิมและรักษา designation X/Y เดิมไว้, output
  ที่ยาวเปลี่ยนหรือเป็น matrix/long-form ต้องเปิด Book ผลลัพธ์ใหม่แทนการยัด NaN ลงชีตเดิมแบบไม่ชัดเจน
- Plot registry ที่ต้องใช้ axes พิเศษต้องประกาศ `projection` หรือ `is3d=True`; ห้ามให้ plotter
  แอบสร้าง axes เองโดยไม่อัปเดต `canvas.ax` เพราะ context menu/inspector จะจับ axes เก่า
- เมนู Plot → `Broken Axis...` ทำงานกับ active line graph และแก้กราฟปัจจุบัน ไม่เปิด Graph ใหม่;
  หลัง split axes ต้องอัปเดต `canvas.ax` ไปยัง axes ใหม่ตัวแรกเหมือน multi-panel
- เส้นทางพล็อตจากชีตทั้งหมดรวมที่ `plot_from_workbook(style, new_graph)` ใน
  `main_window_plot_mixin.py`
- การสลับข้อมูลตาม Book: `MdiWorkspace.bookActivated` → `_on_book_activated`
  (`main_window_data_mixin.py`); ข้อมูลของแต่ละ Book อยู่ที่ `WorkbookWidget.source_df`
  (ชีตแก้แล้ว dirty → พล็อตครั้งถัดไป sync จากชีตก่อน)

## ประวัติ

- 2026-07 (ต้นเดือน): แผงซ้าย 3 ขั้น + staging list (ถูกแทนที่แล้ว)
- 2026-07-04: รีดีไซน์เป็นโมเดล OriginPro เต็มรูปแบบ (P1–P4): แถบไอคอนพล็อต +
  Graph ใหม่ต่อคำสั่ง, multi-book, Set As X/Y, ตัดแผงซ้าย/ซ่อน rail
