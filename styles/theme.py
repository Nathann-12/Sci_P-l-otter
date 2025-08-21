from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtWidgets import QApplication
import os


def apply_theme(app: QApplication):
    # CHANGE: ตั้งฟอนต์เริ่มต้นพร้อม fallback
    try:
        font = QFont("Noto Sans Thai", 11)
        if not font.exactMatch():
            font = QFont("Sarabun", 11)
        if not font.exactMatch():
            font = QFont("Segoe UI", 11)
        app.setFont(font)
    except Exception:
        pass

    # CHANGE: ปรับพาเลตหลักให้เข้ากับธีมมืด
    pal = QPalette()
    base = QColor(18, 18, 18)
    text = QColor(234, 234, 234)
    pal.setColor(QPalette.Window, base)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, QColor(16, 16, 16))
    pal.setColor(QPalette.AlternateBase, QColor(26, 26, 26))
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, QColor(35, 35, 35))
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.Highlight, QColor(0x4F, 0x9C, 0xF9))  # #4F9CF9
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(pal)

    # CHANGE: โหลด QSS จากไฟล์ styles/qdark.qss
    try:
        qss_path = os.path.join(os.path.dirname(__file__), "qdark.qss")
        if os.path.isfile(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
    except Exception:
        pass

    # CHANGE: โหลด Matplotlib style ให้เข้ากับธีม
    try:
        import matplotlib
        mpl_path = os.path.join(os.path.dirname(__file__), "mpl_style_dark.mplstyle")
        if os.path.isfile(mpl_path):
            matplotlib.style.use(mpl_path)
        matplotlib.rcParams["font.sans-serif"] = ["Noto Sans Thai", "Sarabun", "Segoe UI", "Tahoma", "Arial", "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass