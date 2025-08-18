from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication):
    # UI-REFINE: ปรับธีมแบบอ่านง่ายด้วย Palette + QSS (spacing, font, focus highlight)
    pal = QPalette()
    base = QColor(30, 30, 30)
    text = QColor(230, 230, 230)
    pal.setColor(QPalette.Window, base)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, QColor(22, 22, 22))
    pal.setColor(QPalette.AlternateBase, QColor(38, 38, 38))
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, QColor(45, 45, 45))
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.Highlight, QColor(90, 120, 200))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(pal)

    # UI-REFINE: QSS เน้นช่องไฟ ตัวอักษร และ highlight โฟกัสให้อ่านง่าย
    app.setStyleSheet(
        """
        * { font-family: 'Noto Sans Thai', 'Tahoma', 'Segoe UI', Arial; font-size: 11pt; }
        QWidget { background: #1E1E1E; color: #E6E6E6; }
        QToolBar { spacing: 6px; padding: 4px; }
        QStatusBar QLabel { padding: 0 8px; }
        QPushButton { padding: 6px 10px; border: 1px solid #3A3A3A; border-radius: 4px; }
        QPushButton:hover { border-color: #5A5A5A; }
        QComboBox, QSpinBox, QLineEdit { padding: 4px 6px; border: 1px solid #3A3A3A; border-radius: 4px; background: #202020; }
        QTabBar::tab { padding: 8px 12px; }
        QTreeView, QListWidget { border: 1px solid #333; }
        *:focus { outline: none; border: 1px solid #5A78D0; }
        QSplitter::handle { background: #333; }
        QGroupBox { border: 1px solid #333; border-radius: 6px; margin-top: 12px; }
        QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        """
    )