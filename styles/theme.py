from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtWidgets import QApplication
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def apply_theme(app: QApplication):
    logger.info("Applying theme to application...")
    
    # CHANGE: ตั้งฟอนต์เริ่มต้นพร้อม fallback
    try:
        font = QFont("Noto Sans Thai", 11)
        if not font.exactMatch():
            font = QFont("Sarabun", 11)
        if not font.exactMatch():
            font = QFont("Segoe UI", 11)
        app.setFont(font)
        logger.info(f"Font set to: {font.family()}")
    except Exception as e:
        logger.error(f"Error setting font: {e}")

    # CHANGE: ปรับพาเลตหลักให้เข้ากับธีมมืด
    try:
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
        logger.info("Palette applied successfully")
    except Exception as e:
        logger.error(f"Error applying palette: {e}")

    # CHANGE: โหลด QSS จากไฟล์ styles/qdark.qss
    try:
        qss_path = os.path.join(os.path.dirname(__file__), "qdark.qss")
        logger.info(f"Looking for QSS file at: {qss_path}")
        if os.path.isfile(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                qss_content = f.read()
                app.setStyleSheet(qss_content)
                logger.info(f"QSS loaded successfully, length: {len(qss_content)}")
        else:
            logger.warning(f"QSS file not found at: {qss_path}")
    except Exception as e:
        logger.error(f"Error loading QSS: {e}")

    # CHANGE: โหลด Matplotlib style ให้เข้ากับธีม
    try:
        import matplotlib
        mpl_path = os.path.join(os.path.dirname(__file__), "mpl_style_dark.mplstyle")
        logger.info(f"Looking for matplotlib style at: {mpl_path}")
        if os.path.isfile(mpl_path):
            matplotlib.style.use(mpl_path)
            logger.info("Matplotlib style applied successfully")
        else:
            logger.warning(f"Matplotlib style file not found at: {mpl_path}")
        matplotlib.rcParams["font.sans-serif"] = ["Noto Sans Thai", "Sarabun", "Segoe UI", "Tahoma", "Arial", "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
        logger.info("Matplotlib font settings applied")
    except Exception as e:
        logger.error(f"Error applying matplotlib style: {e}")
    
    logger.info("Theme application completed")