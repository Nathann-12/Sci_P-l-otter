# core/logging_setup.py
from __future__ import annotations
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal, QDateTime, Qt

LOG_DIR = os.path.join("Generated Files", "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# --------- Qt bridge: ส่งบันทึก log เข้า UI ผ่านสัญญาณ ---------
class QtLogEmitter(QObject):
    log_record = Signal(object)  # ส่ง logging.LogRecord

qt_log_emitter = QtLogEmitter()

class QtSignalHandler(logging.Handler):
    """logging.Handler ที่ยิงสัญญาณไปยัง Qt UI"""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            qt_log_emitter.log_record.emit(record)
        except Exception:
            # ห้ามโยนซ้ำไม่งั้นวน
            pass

# --------- ตั้งค่า logging กลางให้ทั้งแอปใช้ร่วมกัน ---------
def ensure_log_dir():
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception:
        pass

def build_file_handler(level=logging.INFO) -> logging.Handler:
    ensure_log_dir()
    fh = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(fmt)
    fh.setLevel(level)
    return fh

def build_console_handler(level=logging.WARNING) -> logging.Handler:
    ch = logging.StreamHandler(stream=sys.stderr)
    fmt = logging.Formatter("%(levelname)s | %(name)s | %(message)s")
    ch.setFormatter(fmt)
    ch.setLevel(level)
    return ch

def build_qt_handler(level=logging.DEBUG) -> logging.Handler:
    qh = QtSignalHandler()
    qh.setLevel(level)
    return qh

def setup_logging(root_level=logging.INFO) -> logging.Logger:
    """เรียกครั้งเดียวจาก main.py หลังสร้าง QApplication"""
    logger = logging.getLogger()  # root
    if getattr(logger, "_sciplotter_configured", False):
        return logger

    logger.setLevel(root_level)
    logger.addHandler(build_file_handler(level=logging.INFO))
    logger.addHandler(build_console_handler(level=logging.WARNING))
    logger.addHandler(build_qt_handler(level=logging.DEBUG))
    logger._sciplotter_configured = True  # type: ignore[attr-defined]

    # จับ Unhandled Exceptions ให้ลง log + โผล่ใน Error Panel
    def excepthook(exc_type, exc_value, exc_tb):
        logging.getLogger("Unhandled").exception("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = excepthook

    logging.getLogger(__name__).info("Logging initialized. Log file at: %s", LOG_FILE)
    return logger
