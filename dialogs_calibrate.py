"""
2-Point Calibration Dialog
Provides interface for calibrating raw values to true values
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, 
    QDoubleSpinBox, QPushButton, QGroupBox, QFrame
)
from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QFont

class CalibrateDialog(QDialog):
    """Dialog for 2-point calibration"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Force English locale for Arabic numerals
        self.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        
        self.setWindowTitle("สอบเทียบ 2 จุด (Calibrate 2-point)")
        self.setModal(True)
        self.resize(400, 300)
        
        # Calibration coefficients
        self.a = 1.0
        self.b = 0.0
        
        self.setup_ui()
        self.setup_connections()
    
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # Title
        title_label = QLabel("ป้อนค่าสองจุดเพื่อคำนวณสัมประสิทธิ์การสอบเทียบ")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 8px;")
        layout.addWidget(title_label)
        
        # Calibration inputs
        calib_group = QGroupBox("จุดสอบเทียบ (Calibration Points)")
        calib_layout = QFormLayout(calib_group)
        calib_layout.setSpacing(12)
        
        # Raw values
        self.raw1_spin = QDoubleSpinBox()
        self.raw1_spin.setRange(-1e9, 1e9)
        self.raw1_spin.setDecimals(6)
        self.raw1_spin.setValue(0.0)
        self.raw1_spin.setSuffix(" (raw)")
        
        self.raw2_spin = QDoubleSpinBox()
        self.raw2_spin.setRange(-1e9, 1e9)
        self.raw2_spin.setDecimals(6)
        self.raw2_spin.setValue(100.0)
        self.raw2_spin.setSuffix(" (raw)")
        
        # True values
        self.true1_spin = QDoubleSpinBox()
        self.true1_spin.setRange(-1e9, 1e9)
        self.true1_spin.setDecimals(6)
        self.true1_spin.setValue(0.0)
        self.true1_spin.setSuffix(" (true)")
        
        self.true2_spin = QDoubleSpinBox()
        self.true2_spin.setRange(-1e9, 1e9)
        self.true2_spin.setDecimals(6)
        self.true2_spin.setValue(100.0)
        self.true2_spin.setSuffix(" (true)")
        
        calib_layout.addRow("Raw #1:", self.raw1_spin)
        calib_layout.addRow("True #1:", self.true1_spin)
        calib_layout.addRow("Raw #2:", self.raw2_spin)
        calib_layout.addRow("True #2:", self.true2_spin)
        
        layout.addWidget(calib_group)
        
        # Compute button
        self.compute_btn = QPushButton("คำนวณ a, b (Compute)")
        self.compute_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        layout.addWidget(self.compute_btn)
        
        # Results display
        results_group = QGroupBox("ผลลัพธ์ (Results)")
        results_layout = QFormLayout(results_group)
        results_layout.setSpacing(12)
        
        self.a_label = QLabel("1.000000")
        self.a_label.setFrameStyle(QFrame.Box)
        self.a_label.setStyleSheet("padding: 8px; background-color: #f0f0f0; font-family: monospace;")
        
        self.b_label = QLabel("0.000000")
        self.b_label.setFrameStyle(QFrame.Box)
        self.b_label.setStyleSheet("padding: 8px; background-color: #f0f0f0; font-family: monospace;")
        
        self.equation_label = QLabel("y_true = a × y_raw + b")
        self.equation_label.setAlignment(Qt.AlignCenter)
        self.equation_label.setStyleSheet("font-style: italic; color: #666;")
        
        results_layout.addRow("สัมประสิทธิ์ a:", self.a_label)
        results_layout.addRow("สัมประสิทธิ์ b:", self.b_label)
        results_layout.addRow("", self.equation_label)
        
        layout.addWidget(results_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setDefault(True)
        self.ok_btn.setEnabled(False)  # Disabled until computed
        
        self.cancel_btn = QPushButton("Cancel")
        
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
    
    def setup_connections(self):
        """Setup signal connections"""
        self.compute_btn.clicked.connect(self.compute_calibration)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
        # Update results when values change
        self.raw1_spin.valueChanged.connect(self.update_preview)
        self.raw2_spin.valueChanged.connect(self.update_preview)
        self.true1_spin.valueChanged.connect(self.update_preview)
        self.true2_spin.valueChanged.connect(self.update_preview)
    
    def compute_calibration(self):
        """Compute calibration coefficients"""
        try:
            raw1 = self.raw1_spin.value()
            true1 = self.true1_spin.value()
            raw2 = self.raw2_spin.value()
            true2 = self.true2_spin.value()
            
            if raw1 == raw2:
                self.show_error("Raw values must be different for calibration")
                return
            
            # Calculate a and b for y_true = a * y_raw + b
            self.a = (true2 - true1) / (raw2 - raw1)
            self.b = true1 - self.a * raw1
            
            # Update display
            self.a_label.setText(f"{self.a:.6f}")
            self.b_label.setText(f"{self.b:.6f}")
            
            # Update equation
            if self.b >= 0:
                eq_text = f"y_true = {self.a:.4f} × y_raw + {self.b:.4f}"
            else:
                eq_text = f"y_true = {self.a:.4f} × y_raw - {abs(self.b):.4f}"
            self.equation_label.setText(eq_text)
            
            # Enable OK button
            self.ok_btn.setEnabled(True)
            
            # Visual feedback
            self.compute_btn.setText("✓ คำนวณแล้ว (Computed)")
            self.compute_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    font-weight: bold;
                    border-radius: 4px;
                }
            """)
            
        except Exception as e:
            self.show_error(f"Error computing calibration: {str(e)}")
    
    def update_preview(self):
        """Update preview when values change"""
        # Reset compute button
        self.compute_btn.setText("คำนวณ a, b (Compute)")
        self.compute_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        
        # Disable OK button until recomputed
        self.ok_btn.setEnabled(False)
    
    def show_error(self, message: str):
        """Show error message"""
        self.equation_label.setText(f"❌ {message}")
        self.equation_label.setStyleSheet("font-style: italic; color: #f44336;")
    
    def get_calibration(self) -> tuple:
        """Get calibration coefficients (a, b)"""
        return self.a, self.b

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    dialog = CalibrateDialog()
    dialog.show()
    sys.exit(app.exec())
