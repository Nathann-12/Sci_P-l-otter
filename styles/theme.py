from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication):
    # ธีมเข้มแบบเรียบ ๆ
    pal = QPalette()
    base = QColor(30, 30, 30)
    text = QColor(230, 230, 230)
    pal.setColor(QPalette.Window, base)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, QColor(20, 20, 20))
    pal.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, QColor(45, 45, 45))
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.Highlight, QColor(90, 120, 200))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(pal)