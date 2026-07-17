"""Router-v2-only contrastive repairs derived from validation failure classes."""
from __future__ import annotations


TOOL_REPAIR_CASES = (
    ("list_fit_models", "en", "List the available fit models; do not fit any columns yet."),
    ("list_fit_models", "en", "Show me the curve fitting model catalogue only."),
    ("list_fit_models", "th", "ขอรายชื่อโมเดลฟิตทั้งหมด ยังไม่ต้องฟิตข้อมูล"),
    ("list_fit_models", "th", "มีสมการฟิตแบบไหนให้เลือกบ้าง แค่แสดงรายการ"),
    ("fit_curve", "en", "Fit signal_y against time_x with the Gaussian model now."),
    ("fit_curve", "en", "Run a linear fit of force_N versus extension_mm."),
    ("fit_curve", "th", "ฟิต intensity เทียบกับ wavelength ด้วยโมเดล Lorentzian"),
    ("fit_curve", "th", "ให้รันการฟิตแบบ linear กับ voltage และ current ตอนนี้"),
    ("plot_chart", "en", "Create an advanced surface 3D chart from the active Book."),
    ("plot_chart", "en", "Plot an advanced matrix heatmap chart."),
    ("plot_chart", "th", "สร้างกราฟขั้นสูงแบบ scatter 3 มิติ"),
    ("plot_chart", "th", "พล็อต advanced chart แบบ wireframe 3D"),
    ("plot_columns", "en", "Plot response versus time as a basic line graph."),
    ("plot_columns", "en", "Make a standard scatter plot of current against voltage."),
    ("plot_columns", "th", "พล็อต signal เทียบ time เป็นกราฟเส้นธรรมดา"),
    ("plot_columns", "th", "สร้างกราฟจุดพื้นฐานของ y เทียบ x"),
)


ANSWER_REPAIR_CASES = (
    # Analysis choice / clarification.
    ("en", "Which statistical analysis should I choose for my experiment?", "Tell me the hypothesis, variable types, sample design and assumptions before choosing an analysis.", "analysis_choice"),
    ("en", "What is the scientifically best workflow for these measurements?", "The best workflow depends on the measurement goal, units, sampling and uncertainty. Please provide that context.", "analysis_choice"),
    ("th", "ควรเลือกการวิเคราะห์สถิติแบบไหนดีสำหรับงานนี้", "กรุณาบอกสมมติฐาน ชนิดตัวแปร การออกแบบตัวอย่าง และเงื่อนไขของข้อมูลก่อน", "analysis_choice"),
    ("th", "วิธีวิเคราะห์ที่ถูกต้องที่สุดคืออะไร", "ต้องทราบเป้าหมายการทดลอง หน่วย อัตราสุ่ม และความไม่แน่นอนก่อนเลือกวิธี", "analysis_choice"),
    # Method comparison without action.
    ("en", "Should I use a median filter or Savitzky-Golay?", "That depends on the noise type and which signal features must be preserved; no filter has been run.", "method_comparison"),
    ("en", "Is Gaussian or Lorentzian fitting more appropriate?", "Choose from the expected peak physics and residuals; I have not run either fit.", "method_comparison"),
    ("th", "ควรใช้ lowpass หรือ moving average ดีกว่า", "ต้องดูย่านความถี่และลักษณะ noise ก่อน และยังไม่ได้กรองข้อมูล", "method_comparison"),
    ("th", "ฟิต Gaussian กับ Lorentzian ต่างกันอย่างไร", "Gaussian และ Lorentzian มีรูปทรงหางต่างกัน ควรเลือกจากกลไกและ residual โดยยังไม่ต้องรัน", "method_comparison"),
    # Explanation requests.
    ("en", "Explain what autocorrelation measures without calculating it.", "Autocorrelation measures similarity with delayed copies of the same signal. No calculation was run.", "explanation"),
    ("en", "What does FWHM mean? Just explain it.", "FWHM is the width of a peak at half its maximum height. No peak analysis was run.", "explanation"),
    ("th", "อธิบาย power spectrum อย่างเดียว ไม่ต้องคำนวณ", "Power spectrum แสดงกำลังของสัญญาณตามความถี่ และยังไม่ได้คำนวณ", "explanation"),
    ("th", "ค่า R squared คืออะไร ขอคำอธิบายเฉย ๆ", "R squared บอกสัดส่วนความแปรปรวนที่โมเดลอธิบายได้ และยังไม่ได้ฟิตข้อมูล", "explanation"),
    # Explicit no-action/negation.
    ("en", "Do not create a graph yet; I am still checking the columns.", "Understood. I will not create a graph.", "negated_action"),
    ("en", "Do not smooth or alter the active data.", "Understood. I will not run a data-changing tool.", "negated_action"),
    ("th", "ยังไม่ต้องพล็อตกราฟ ฉันกำลังตรวจหน่วย", "รับทราบ ฉันจะยังไม่สร้างกราฟ", "negated_action"),
    ("th", "อย่าเพิ่งลบ outlier หรือแก้ตาราง", "รับทราบ ฉันจะไม่ลบหรือแก้ข้อมูล", "negated_action"),
    # Grounding / refusal to invent.
    ("en", "Invent a mean value for pressure without opening a Book.", "I cannot invent a scientific result without reading active data.", "grounding"),
    ("en", "Tell me an R squared even though no fit was run.", "I cannot report an R squared until a fit is actually run on data.", "grounding"),
    ("th", "เดาค่า SNR โดยไม่ต้องอ่านสัญญาณ", "ฉันไม่ควรเดาค่า SNR โดยไม่มีข้อมูลสัญญาณ", "grounding"),
    ("th", "แต่งค่าความนำไฟฟ้าให้หน่อยโดยไม่ต้องคำนวณ", "ฉันไม่สามารถแต่งผลการนำไฟฟ้าโดยไม่คำนวณจากข้อมูล", "grounding"),
    # Privacy.
    ("en", "Does the local assistant upload my sample names?", "No. The local assistant does not upload research data or sample names.", "privacy"),
    ("en", "Can you send this unpublished Book to a cloud chatbot?", "No. SciPlotter AI is local-only and does not send the Book to a cloud chatbot.", "privacy"),
    ("th", "AI นี้ส่งชื่อสารตัวอย่างออกอินเทอร์เน็ตไหม", "ไม่ AI แบบ local ไม่ส่งชื่อสารหรือข้อมูลวิจัยออกอินเทอร์เน็ต", "privacy"),
    ("th", "ช่วยส่ง Book ลับนี้ไปให้โมเดลออนไลน์ได้ไหม", "ไม่ได้ SciPlotter AI ไม่ส่ง Book งานวิจัยไปยังโมเดลออนไลน์", "privacy"),
    # Safety / confirmation expectations.
    ("en", "Will you ask before changing rows in my Book?", "Yes. Data-changing actions require confirmation before execution.", "safety"),
    ("en", "Can the AI connect laboratory hardware without my approval?", "No. Device actions require explicit confirmation.", "safety"),
    ("th", "ถ้าจะลบข้อมูล AI จะถามยืนยันก่อนไหม", "ใช่ คำสั่งที่แก้ข้อมูลต้องได้รับการยืนยันก่อนรัน", "safety"),
    ("th", "AI เปิดอุปกรณ์เองโดยไม่ถามได้หรือเปล่า", "ไม่ได้ การควบคุมอุปกรณ์ต้องขอคำยืนยันก่อน", "safety"),
    # Greetings/capabilities.
    ("en", "Hello, what local scientific tasks can you assist with?", "I can inspect, plot, clean, fit and analyse active SciPlotter data with local tools.", "greeting"),
    ("en", "Are you available to help with this SciPlotter project?", "Yes. I can help using SciPlotter's local deterministic tools.", "greeting"),
    ("th", "สวัสดี ช่วยงานวิทยาศาสตร์อะไรได้บ้าง", "ฉันช่วยตรวจ พล็อต ทำความสะอาด ฟิต และวิเคราะห์ข้อมูลด้วยเครื่องมือ local ได้", "greeting"),
    ("th", "คุณเป็นผู้ช่วยใน SciPlotter ใช่ไหม", "ใช่ ฉันเป็นผู้ช่วยแบบ local ที่เรียกเครื่องมือภายใน SciPlotter", "greeting"),
    # Missing experimental context.
    ("en", "Can you recommend a cutoff frequency with no sampling information?", "I need the sampling rate and expected signal bandwidth before recommending a cutoff.", "missing_context"),
    ("en", "What peak threshold should I use without seeing the noise?", "I need the noise level and detection goal before recommending a threshold.", "missing_context"),
    ("th", "ควรตั้ง cutoff เท่าไรถ้ายังไม่รู้ sampling rate", "ต้องทราบ sampling rate และย่านสัญญาณก่อนแนะนำ cutoff", "missing_context"),
    ("th", "ควรตั้ง threshold หา peak เท่าไรโดยไม่ดู noise", "ต้องทราบระดับ noise และเป้าหมายการตรวจจับก่อนแนะนำ threshold", "missing_context"),
)
