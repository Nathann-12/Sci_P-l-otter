from __future__ import annotations

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

from dialogs_spectrogram import SpectrogramDialog
from processors_spectrogram import compute_cwt, compute_spectrogram, export_spectrogram_data


class MainWindowSpectrogramMixin:
    """Reusable spectrogram actions extracted from MainWindow."""

    def _is_replace_plot_mode(self) -> bool:
        mode = getattr(self, "plot_mode", "overlay")
        return str(mode).lower().endswith("replace")

    def open_spectrogram_dialog(self):
        """เปิด dialog สำหรับ Spectrogram Analysis"""
        if self._df is None or self._df.empty:
            QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดเปิดไฟล์ข้อมูลก่อน")
            return

        dialog = SpectrogramDialog(self._df, self)
        dialog.preview_requested.connect(self.on_spectrogram_preview)
        dialog.export_image_requested.connect(self.on_spectrogram_export_image)
        dialog.export_csv_requested.connect(self.on_spectrogram_export_csv)
        dialog.send_to_fft_requested.connect(self.on_spectrogram_send_to_fft)
        dialog.send_to_curvefit_requested.connect(self.on_spectrogram_send_to_curvefit)

        try:
            dialog.setWindowModality(Qt.NonModal)
            dialog.setAttribute(Qt.WA_DeleteOnClose, True)
            dialog.resize(720, 480)
        except Exception:
            pass
        dialog.show()

    def on_spectrogram_preview(self, params):
        """แสดง preview ของ Spectrogram"""
        try:
            time_col = params["time_col"]
            signal_col = params["signal_col"]
            mode = params["mode"]
            to_db = params["to_db"]

            if time_col not in self._df.columns or signal_col not in self._df.columns:
                QMessageBox.warning(self, "ไม่พบคอลัมน์", "โปรดเลือกคอลัมน์ที่ถูกต้อง")
                return

            time_data = self._df[time_col]
            signal_data = self._df[signal_col]

            if time_data.empty or signal_data.empty:
                QMessageBox.warning(self, "ข้อมูลว่าง", "คอลัมน์ที่เลือกไม่มีข้อมูล")
                return

            valid_time = time_data.notna().sum()
            valid_signal = signal_data.notna().sum()
            if valid_time < 10 or valid_signal < 10:
                QMessageBox.warning(
                    self,
                    "ข้อมูลไม่เพียงพอ",
                    f"คอลัมน์เวลา: {valid_time} จุด, คอลัมน์สัญญาณ: {valid_signal} จุด\nต้องมีอย่างน้อย 10 จุด",
                )
                return

            if pd.api.types.is_datetime64_any_dtype(time_data) and not time_data.is_monotonic_increasing:
                QMessageBox.warning(
                    self,
                    "ข้อมูลเวลาไม่เรียงลำดับ",
                    "ข้อมูลเวลาต้องเรียงลำดับจากน้อยไปมาก",
                )
                return

            if "STFT" in mode:
                T, F, S, meta = compute_spectrogram(
                    self._df[time_col],
                    self._df[signal_col],
                    fs=None,
                    window=params["window"],
                    nperseg=params["nperseg"],
                    noverlap=params["noverlap"],
                    scaling=params["scaling"],
                    to_db=to_db,
                    detrend=params.get("detrend", True),
                    contrast_percentiles=params.get("contrast_percentiles", (5, 95)),
                )
            else:
                T, F, S, meta = compute_cwt(
                    self._df[time_col],
                    self._df[signal_col],
                    wavelet=params["wavelet"],
                    scales=params["scales"],
                    to_db=to_db,
                )

            try:
                if self._is_replace_plot_mode():
                    self.canvas.ax.clear()
            except Exception:
                pass

            if hasattr(self, "_last_cbar") and self._last_cbar is not None:
                try:
                    self._last_cbar.remove()
                except Exception:
                    pass
                self._last_cbar = None

            if meta["is_datetime"]:
                extent = [0, len(T), F.min(), F.max()]
                im = self.canvas.ax.imshow(S, origin="lower", aspect="auto", extent=extent, cmap="viridis")
                time_ticks = np.linspace(0, len(T), 5)
                time_labels = pd.date_range(start=meta["time_range"][0], end=meta["time_range"][1], periods=5)
                self.canvas.ax.set_xticks(time_ticks)
                self.canvas.ax.set_xticklabels([t.strftime("%H:%M:%S") for t in time_labels])
            else:
                extent = [T.min(), T.max(), F.min(), F.max()]
                im = self.canvas.ax.imshow(S, origin="lower", aspect="auto", extent=extent, cmap="viridis")

            if "vmin" in meta and "vmax" in meta:
                im.set_clim(meta["vmin"], meta["vmax"])

            if "max_frequency" in params:
                self.canvas.ax.set_ylim(0, params["max_frequency"])

            self._last_cbar = self.canvas.fig.colorbar(im, ax=self.canvas.ax)
            self._last_cbar.set_label("Power (dB)" if to_db else "Power")
            self.canvas.ax.set_xlabel("Time")
            self.canvas.ax.set_ylabel("Frequency (Hz)")
            method = "STFT" if "STFT" in mode else "CWT"
            self.canvas.ax.set_title(f"Spectrogram ({method}) - {signal_col}")
            self.canvas.ax.grid(True, alpha=0.3)
            self.canvas.draw()

            if hasattr(self, "_cid_motion") and self._cid_motion is not None:
                try:
                    self.canvas.mpl_disconnect(self._cid_motion)
                except Exception:
                    pass

            self._cid_motion = self.canvas.mpl_connect("motion_notify_event", self._on_spectrogram_mouse_move)
            self.statusBar().showMessage(f"Spectrogram preview เสร็จสิ้น: {method}")
            self._current_spectrogram = {"T": T, "F": F, "S": S, "meta": meta, "params": params}
        except ImportError as exc:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถใช้งานได้: {str(exc)}")
        except Exception as exc:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาดในการคำนวณ: {str(exc)}")
            print(f"Spectrogram error: {exc}")

    def on_spectrogram_export_image(self, params):
        """Export Spectrogram เป็นรูปภาพ PNG"""
        try:
            if not hasattr(self, "_current_spectrogram"):
                QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดทำ Preview ก่อน")
                return

            filename, _ = QFileDialog.getSaveFileName(
                self,
                "บันทึก Spectrogram",
                f"spectrogram_{params['mode'].split()[0].lower()}.png",
                "PNG Files (*.png)",
            )
            if filename:
                self.canvas.fig.savefig(filename, dpi=150, bbox_inches="tight")
                self.statusBar().showMessage(f"บันทึก Spectrogram เป็น {filename}")
        except Exception as exc:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาดในการบันทึก: {str(exc)}")

    def on_spectrogram_export_csv(self, params):
        """Export Spectrogram เป็นไฟล์ CSV"""
        try:
            if not hasattr(self, "_current_spectrogram"):
                QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดทำ Preview ก่อน")
                return

            filename, _ = QFileDialog.getSaveFileName(
                self,
                "บันทึก Spectrogram CSV",
                f"spectrogram_{params['mode'].split()[0].lower()}.csv",
                "CSV Files (*.csv)",
            )
            if filename:
                export_spectrogram_data(
                    self._current_spectrogram["T"],
                    self._current_spectrogram["F"],
                    self._current_spectrogram["S"],
                    self._current_spectrogram["meta"],
                    filename,
                )
                self.statusBar().showMessage(f"บันทึก Spectrogram CSV เป็น {filename}")
        except Exception as exc:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาดในการบันทึก: {str(exc)}")

    def on_spectrogram_send_to_fft(self, params):
        """ส่งข้อมูลจาก Spectrogram ไปยัง FFT"""
        try:
            if not hasattr(self, "_current_spectrogram"):
                QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดทำ Preview ก่อน")
                return

            time_col = params["time_col"]
            signal_col = params["signal_col"]
            if time_col in self._df.columns and signal_col in self._df.columns:
                self.run_fft_dialog()
                self.statusBar().showMessage("ส่งข้อมูลไปยัง FFT แล้ว")
            else:
                QMessageBox.warning(self, "ไม่พบคอลัมน์", "ไม่พบคอลัมน์ที่เลือกในข้อมูล")
        except Exception as exc:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาด: {str(exc)}")

    def on_spectrogram_send_to_curvefit(self, params):
        """ส่งข้อมูลจาก Spectrogram ไปยัง CurveFit"""
        try:
            if not hasattr(self, "_current_spectrogram"):
                QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดทำ Preview ก่อน")
                return

            time_col = params["time_col"]
            signal_col = params["signal_col"]
            if time_col in self._df.columns and signal_col in self._df.columns:
                self._open_fit_dialog()
                self.statusBar().showMessage("ส่งข้อมูลไปยัง CurveFit แล้ว")
            else:
                QMessageBox.warning(self, "ไม่พบคอลัมน์", "ไม่พบคอลัมน์ที่เลือกในข้อมูล")
        except Exception as exc:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาด: {str(exc)}")

    def _on_spectrogram_mouse_move(self, event):
        """Crosshair callback สำหรับ spectrogram"""
        if not hasattr(self, "_current_spectrogram") or event.inaxes != self.canvas.ax:
            return

        try:
            T = self._current_spectrogram["T"]
            S = self._current_spectrogram["S"]
            meta = self._current_spectrogram["meta"]
            x_data, y_data = event.xdata, event.ydata
            if x_data is None or y_data is None:
                return

            if meta["is_datetime"]:
                time_idx = int(x_data)
                if 0 <= time_idx < len(T):
                    time_str = T[time_idx].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    time_str = "N/A"
            else:
                time_str = f"{x_data:.3f}"

            freq_str = f"{y_data:.2f} Hz"
            if 0 <= int(x_data) < S.shape[0] and 0 <= int(y_data) < S.shape[1]:
                power_val = S[int(x_data), int(y_data)]
                unit = "dB" if meta.get("to_db", False) else ""
                power_str = f"{power_val:.2f} {unit}"
            else:
                power_str = "N/A"

            self.statusBar().showMessage(f"Time: {time_str} | Freq: {freq_str} | Power: {power_str}")
        except Exception:
            pass
