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
| พล็อต | **แถบไอคอนพล็อตด้านล่าง** (เส้น/จุด/เส้น+จุด/แท่ง/Histogram) หรือปุ่มบนชีต หรือคลิกขวา หรือเมนู Plot — ทั้งหมด = Graph ใหม่ |
| เพิ่มเส้นลงกราฟเดิม | คลิกขวาบนชีต → "เพิ่มเส้นลงกราฟปัจจุบัน" / เมนู Plot → overlay |
| เครื่องมือกราฟ (crosshair / box zoom) | ปุ่มบน toolbar หลัก |
| จัดการหน้าต่าง Book/Graph | Project Explorer (dock ซ้าย) + เมนู Window (Cascade/Tile) |
| การแปลง/ทำความสะอาดข้อมูล | เมนู Process (Data Cleaning / Filters / FFT / PSD) |
| สถิติ/วิเคราะห์/fit | เมนู Analysis |
| จัดการ Layers ของกราฟ | Inspector ขวา (ของเสริม — toggle จาก toolbar/View) |

## กติกาสำหรับฟีเจอร์ใหม่ (บังคับ)

1. **Worksheet เป็นศูนย์กลาง** — ฟีเจอร์ที่กินข้อมูลเข้า/คายข้อมูลออก ต้องอ่าน-เขียนผ่าน
   Book ที่ active (`self._df` ตาม `bookActivated`) และผลลัพธ์ที่เป็นตารางควรเป็นคอลัมน์ใหม่/Book ใหม่
2. **ห้ามซ่อนขั้นตอนหลักใน panel ที่ปิดอยู่** — Inspector ใส่ได้เฉพาะของเสริม (layers/style)
3. **คำสั่งพล็อตใหม่ = Graph window ใหม่** เว้นแต่ผู้ใช้เลือก overlay เอง
4. การแปลงข้อมูล = เมนู Process, การวิเคราะห์ = เมนู Analysis — เพิ่มเป็น submenu ตามหมวด
5. **โมดูลเฉพาะทาง (Gas Sensor ฯลฯ)** = activity ใหม่ใน activity rail
   (rail ซ่อนอยู่ตอนนี้ และจะโผล่เองเมื่อมี context ลงทะเบียน — ดู `AppShell.register_context`)

## หมายเหตุทางเทคนิค (สำหรับคนแก้โค้ด)

- แผงซ้ายเดิม (`_panel_left`) และ `CompactPlotPanel` ยังถูกสร้างแบบ **ซ่อน** เป็น
  state-holder ของ aliases (`cbX/cbY/spLineWidth/chkMarker/btnLine/...`, `lblFile`,
  `chkCross`, `btnBoxZoom`) ที่ mixin/session ใช้ — หนี้เทคนิค: ถอด logic ออกจาก
  widget พวกนี้แล้วลบทิ้ง
- เส้นทางพล็อตจากชีตทั้งหมดรวมที่ `plot_from_workbook(style, new_graph)` ใน
  `main_window_plot_mixin.py`
- การสลับข้อมูลตาม Book: `MdiWorkspace.bookActivated` → `_on_book_activated`
  (`main_window_data_mixin.py`); ข้อมูลของแต่ละ Book อยู่ที่ `WorkbookWidget.source_df`
  (ชีตแก้แล้ว dirty → พล็อตครั้งถัดไป sync จากชีตก่อน)

## ประวัติ

- 2026-07 (ต้นเดือน): แผงซ้าย 3 ขั้น + staging list (ถูกแทนที่แล้ว)
- 2026-07-04: รีดีไซน์เป็นโมเดล OriginPro เต็มรูปแบบ (P1–P4): แถบไอคอนพล็อต +
  Graph ใหม่ต่อคำสั่ง, multi-book, Set As X/Y, ตัดแผงซ้าย/ซ่อน rail
