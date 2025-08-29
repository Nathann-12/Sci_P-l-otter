from PySide6.QtWidgets import QPushButton, QColorDialog, QVBoxLayout, QWidget, QLabel
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPalette, QPainter, QPixmap

class ColorButton(QPushButton):
    """A button that shows a color swatch and opens a color dialog when clicked"""
    
    colorChanged = Signal(QColor)
    
    def __init__(self, color=QColor(0, 0, 0), parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(60, 30)
        self.clicked.connect(self._show_color_dialog)
        self._update_appearance()
        
    def color(self):
        """Get the current color"""
        return self._color
    
    def setColor(self, color):
        """Set the color and update appearance"""
        if self._color != color:
            self._color = color
            self._update_appearance()
            self.colorChanged.emit(color)
    
    def _show_color_dialog(self):
        """Show color dialog and update color if accepted"""
        color = QColorDialog.getColor(self._color, self, "เลือกสี")
        if color.isValid():
            self.setColor(color)
    
    def _update_appearance(self):
        """Update button appearance to show color swatch"""
        # Create a pixmap with the color
        pixmap = QPixmap(self.size())
        pixmap.fill(self._color)
        
        # Draw border
        painter = QPainter(pixmap)
        painter.setPen(Qt.black)
        painter.drawRect(0, 0, pixmap.width()-1, pixmap.height()-1)
        painter.end()
        
        # Set button icon
        self.setIcon(pixmap)
        self.setIconSize(self.size() - QSize(4, 4))
        
        # Set tooltip
        self.setToolTip(f"สี: RGB({self._color.red()}, {self._color.green()}, {self._color.blue()})")

class ColorButtonWithLabel(QWidget):
    """A color button with a label"""
    
    colorChanged = Signal(QColor)
    
    def __init__(self, label="", color=QColor(0, 0, 0), parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        # Label
        self.label = QLabel(label)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)
        
        # Color button
        self.color_button = ColorButton(color)
        self.color_button.colorChanged.connect(self.colorChanged)
        layout.addWidget(self.color_button)
    
    def color(self):
        """Get the current color"""
        return self.color_button.color()
    
    def setColor(self, color):
        """Set the color"""
        self.color_button.setColor(color)
    
    def setLabel(self, text):
        """Set the label text"""
        self.label.setText(text)
