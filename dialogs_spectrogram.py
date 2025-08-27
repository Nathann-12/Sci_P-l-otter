from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QComboBox, QSpinBox, QCheckBox, QPushButton, QGroupBox,
    QFormLayout, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

class SpectrogramDialog(QDialog):
    # Signals for callbacks
    preview_requested = Signal(dict)  # Emit parameters for preview
    export_image_requested = Signal(dict)  # Emit parameters for image export
    export_csv_requested = Signal(dict)  # Emit parameters for CSV export
    send_to_fft_requested = Signal(dict)  # Emit parameters for FFT
    send_to_curvefit_requested = Signal(dict)  # Emit parameters for CurveFit
    
    def __init__(self, df, parent=None):
        super().__init__(parent)
        self.df = df
        self.setup_ui()
        self.populate_columns()
        
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("Spectrogram Analysis")
        self.setMinimumSize(500, 600)
        self.setModal(True)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Column selection section
        column_group = QGroupBox("เลือกคอลัมน์ข้อมูล")
        column_layout = QFormLayout(column_group)
        
        self.time_col_combo = QComboBox()
        self.signal_col_combo = QComboBox()
        
        column_layout.addRow("คอลัมน์เวลา:", self.time_col_combo)
        column_layout.addRow("คอลัมน์สัญญาณ:", self.signal_col_combo)
        
        main_layout.addWidget(column_group)
        
        # Analysis mode section
        mode_group = QGroupBox("โหมดการวิเคราะห์")
        mode_layout = QFormLayout(mode_group)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["STFT (Spectrogram)", "CWT (Wavelet)"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        
        mode_layout.addRow("โหมด:", self.mode_combo)
        
        main_layout.addWidget(mode_group)
        
        # STFT parameters section
        self.stft_group = QGroupBox("พารามิเตอร์ STFT")
        stft_layout = QFormLayout(self.stft_group)
        
        self.window_combo = QComboBox()
        self.window_combo.addItems(["hann", "hamming", "blackman", "bartlett", "triang"])
        
        self.nperseg_spin = QSpinBox()
        self.nperseg_spin.setRange(32, 2048)
        self.nperseg_spin.setValue(256)
        self.nperseg_spin.setSingleStep(32)
        
        self.noverlap_spin = QSpinBox()
        self.noverlap_spin.setRange(16, 1024)
        self.noverlap_spin.setValue(128)
        self.noverlap_spin.setSingleStep(16)
        
        self.scaling_combo = QComboBox()
        self.scaling_combo.addItems(["density", "spectrum"])
        
        self.detrend_checkbox = QCheckBox("Detrend signal")
        self.detrend_checkbox.setChecked(True)
        
        self.contrast_p1_spin = QSpinBox()
        self.contrast_p1_spin.setRange(1, 50)
        self.contrast_p1_spin.setValue(5)
        self.contrast_p1_spin.setSuffix("%")
        
        self.contrast_p2_spin = QSpinBox()
        self.contrast_p2_spin.setRange(50, 99)
        self.contrast_p2_spin.setValue(95)
        self.contrast_p2_spin.setSuffix("%")
        
        self.max_freq_spin = QSpinBox()
        self.max_freq_spin.setRange(10, 10000)
        self.max_freq_spin.setValue(80)
        self.max_freq_spin.setSuffix(" Hz")
        
        stft_layout.addRow("Window:", self.window_combo)
        stft_layout.addRow("Points per segment:", self.nperseg_spin)
        stft_layout.addRow("Overlap:", self.noverlap_spin)
        stft_layout.addRow("Scaling:", self.scaling_combo)
        stft_layout.addRow("Detrend:", self.detrend_checkbox)
        stft_layout.addRow("Contrast P1:", self.contrast_p1_spin)
        stft_layout.addRow("Contrast P2:", self.contrast_p2_spin)
        stft_layout.addRow("Max Frequency:", self.max_freq_spin)
        
        main_layout.addWidget(self.stft_group)
        
        # CWT parameters section
        self.cwt_group = QGroupBox("พารามิเตอร์ CWT")
        cwt_layout = QFormLayout(self.cwt_group)
        
        self.wavelet_combo = QComboBox()
        self.wavelet_combo.addItems(["morl", "gaus", "cmor", "shan", "fbsp"])
        
        self.scales_spin = QSpinBox()
        self.scales_spin.setRange(16, 256)
        self.scales_spin.setValue(64)
        self.scales_spin.setSingleStep(8)
        
        cwt_layout.addRow("Wavelet:", self.wavelet_combo)
        cwt_layout.addRow("จำนวน scales:", self.scales_spin)
        
        main_layout.addWidget(self.cwt_group)
        
        # Display options section
        display_group = QGroupBox("ตัวเลือกการแสดงผล")
        display_layout = QVBoxLayout(display_group)
        
        self.dB_checkbox = QCheckBox("แปลงเป็น Decibels (dB)")
        self.dB_checkbox.setChecked(True)
        
        display_layout.addWidget(self.dB_checkbox)
        
        main_layout.addWidget(display_group)
        
        # Buttons section
        buttons_layout = QHBoxLayout()
        
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.clicked.connect(self.on_preview)
        self.preview_btn.setMinimumWidth(80)
        
        self.export_img_btn = QPushButton("Export Image (PNG)")
        self.export_img_btn.clicked.connect(self.on_export_image)
        self.export_img_btn.setMinimumWidth(120)
        
        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.clicked.connect(self.on_export_csv)
        self.export_csv_btn.setMinimumWidth(80)
        
        self.send_to_fft_btn = QPushButton("Send to FFT")
        self.send_to_fft_btn.clicked.connect(self.on_send_to_fft)
        self.send_to_fft_btn.setMinimumWidth(100)
        
        self.send_to_curvefit_btn = QPushButton("Send to CurveFit")
        self.send_to_curvefit_btn.clicked.connect(self.on_send_to_curvefit)
        self.send_to_curvefit_btn.setMinimumWidth(120)
        
        buttons_layout.addWidget(self.preview_btn)
        buttons_layout.addWidget(self.export_img_btn)
        buttons_layout.addWidget(self.export_csv_btn)
        buttons_layout.addWidget(self.send_to_fft_btn)
        buttons_layout.addWidget(self.send_to_curvefit_btn)
        buttons_layout.addStretch()
        
        # Cancel/OK buttons
        self.cancel_btn = QPushButton("ยกเลิก")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setMinimumWidth(80)
        
        self.ok_btn = QPushButton("ตกลง")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setMinimumWidth(80)
        self.ok_btn.setDefault(True)
        
        buttons_layout.addWidget(self.cancel_btn)
        buttons_layout.addWidget(self.ok_btn)
        
        main_layout.addLayout(buttons_layout)
        
        # Initialize mode-dependent visibility
        self.on_mode_changed()
        
    def populate_columns(self):
        """Populate column comboboxes with DataFrame columns"""
        if self.df is not None:
            for col in self.df.columns:
                self.time_col_combo.addItem(str(col))
                self.signal_col_combo.addItem(str(col))
            
            # Set default selections if possible
            if self.df.columns.size >= 2:
                self.time_col_combo.setCurrentIndex(0)
                self.signal_col_combo.setCurrentIndex(1)
    
    def on_mode_changed(self):
        """Handle mode change to show/hide relevant parameter groups"""
        mode = self.mode_combo.currentText()
        if "STFT" in mode:
            self.stft_group.setVisible(True)
            self.cwt_group.setVisible(False)
        else:
            self.stft_group.setVisible(False)
            self.cwt_group.setVisible(True)
    
    def get_parameters(self):
        """Get all parameters as a dictionary"""
        mode = self.mode_combo.currentText()
        
        params = {
            "time_col": self.time_col_combo.currentText(),
            "signal_col": self.signal_col_combo.currentText(),
            "mode": mode,
            "to_db": self.dB_checkbox.isChecked()
        }
        
        if "STFT" in mode:
            params.update({
                "window": self.window_combo.currentText(),
                "nperseg": self.nperseg_spin.value(),
                "noverlap": self.noverlap_spin.value(),
                "scaling": self.scaling_combo.currentText(),
                "detrend": self.detrend_checkbox.isChecked(),
                "contrast_percentiles": (self.contrast_p1_spin.value(), self.contrast_p2_spin.value()),
                "max_frequency": self.max_freq_spin.value()
            })
        else:  # CWT
            params.update({
                "wavelet": self.wavelet_combo.currentText(),
                "scales": self.scales_spin.value()
            })
        
        return params
    
    def validate_parameters(self):
        """Validate that all parameters are valid"""
        params = self.get_parameters()
        
        if not params["time_col"] or not params["signal_col"]:
            QMessageBox.warning(self, "ข้อมูลไม่ครบ", "โปรดเลือกคอลัมน์เวลาและสัญญาณ")
            return False
        
        if params["time_col"] == params["signal_col"]:
            QMessageBox.warning(self, "ข้อมูลซ้ำ", "คอลัมน์เวลาและสัญญาณต้องไม่ใช่คอลัมน์เดียวกัน")
            return False
        
        return True
    
    def on_preview(self):
        """Handle preview button click"""
        if not self.validate_parameters():
            return
        
        params = self.get_parameters()
        self.preview_requested.emit(params)
    
    def on_export_image(self):
        """Handle export image button click"""
        if not self.validate_parameters():
            return
        
        params = self.get_parameters()
        self.export_image_requested.emit(params)
    
    def on_export_csv(self):
        """Handle export CSV button click"""
        if not self.validate_parameters():
            return
        
        params = self.get_parameters()
        self.export_csv_requested.emit(params)
    
    def on_send_to_fft(self):
        """Handle send to FFT button click"""
        if not self.validate_parameters():
            return
        
        params = self.get_parameters()
        self.send_to_fft_requested.emit(params)
    
    def on_send_to_curvefit(self):
        """Handle send to CurveFit button click"""
        if not self.validate_parameters():
            return
        
        params = self.get_parameters()
        self.send_to_curvefit_requested.emit(params)
