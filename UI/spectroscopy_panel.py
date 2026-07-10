"""Spectroscopy module context panel."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class SpectroscopyPanel(QWidget):
    preprocess_requested = Signal()
    peaks_requested = Signal()
    raman_requested = Signal()
    tauc_requested = Signal()
    xrd_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SpectroscopyPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Spectroscopy", self)
        title.setObjectName("SpectroscopyTitle")
        layout.addWidget(title)

        hint = QLabel("Use the active Book: wavelength/wavenumber/2theta/energy in X, intensity or absorbance in Y.", self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.btn_preprocess = QPushButton("Baseline + Normalize...", self)
        self.btn_preprocess.setToolTip("Polynomial baseline correction and spectrum normalization")
        self.btn_peaks = QPushButton("Peak Table...", self)
        self.btn_peaks.setToolTip("Detect peaks, FWHM, and peak area")
        self.btn_raman = QPushButton("Raman D/G Ratio...", self)
        self.btn_raman.setToolTip("Find D and G peak intensities and ID/IG")
        self.btn_tauc = QPushButton("Tauc Band Gap...", self)
        self.btn_tauc.setToolTip("Fit a Tauc line and estimate optical band gap")
        self.btn_xrd = QPushButton("XRD Scherrer Size...", self)
        self.btn_xrd.setToolTip("Estimate crystallite size from XRD peak FWHM")

        for btn in (self.btn_preprocess, self.btn_peaks, self.btn_raman, self.btn_tauc, self.btn_xrd):
            btn.setMinimumHeight(34)
            layout.addWidget(btn)
        layout.addStretch(1)

        self.btn_preprocess.clicked.connect(self.preprocess_requested.emit)
        self.btn_peaks.clicked.connect(self.peaks_requested.emit)
        self.btn_raman.clicked.connect(self.raman_requested.emit)
        self.btn_tauc.clicked.connect(self.tauc_requested.emit)
        self.btn_xrd.clicked.connect(self.xrd_requested.emit)

        self.setStyleSheet(
            """
            #SpectroscopyTitle { font-size: 13pt; font-weight: 600; color: #e6e6e6; }
            #SpectroscopyPanel QLabel { color: #aab0b6; }
            #SpectroscopyPanel QPushButton {
                text-align: left; padding: 6px 10px; border-radius: 8px;
                background: #262b33; border: 1px solid rgba(255,255,255,0.08);
                color: #e6e6e6;
            }
            #SpectroscopyPanel QPushButton:hover {
                background: #2f3540; border-color: #FBBF24;
            }
            """
        )
