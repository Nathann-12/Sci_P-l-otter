from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtWidgets import QApplication
import os
import logging
import matplotlib
from cycler import cycler

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
        # Try to load dark style file
        mpl_path = os.path.join(os.path.dirname(__file__), "mpl_style_dark.mplstyle")
        logger.info(f"Looking for matplotlib style at: {mpl_path}")
        if os.path.isfile(mpl_path):
            matplotlib.style.use(mpl_path)
            logger.info("Matplotlib style applied successfully")
        else:
            logger.warning(f"Matplotlib style file not found at: {mpl_path}")
            # Apply fallback dark theme
            matplotlib.rcParams["figure.facecolor"] = "#1e1e1e"
            matplotlib.rcParams["axes.facecolor"] = "#1e1e1e"
            matplotlib.rcParams["axes.edgecolor"] = "#404040"
            matplotlib.rcParams["axes.labelcolor"] = "#ffffff"
            matplotlib.rcParams["xtick.color"] = "#ffffff"
            matplotlib.rcParams["ytick.color"] = "#ffffff"
            matplotlib.rcParams["text.color"] = "#ffffff"
            matplotlib.rcParams["grid.color"] = "#404040"
            matplotlib.rcParams["grid.alpha"] = 0.3
            logger.info("Fallback matplotlib dark theme applied")
        
        # Font settings - use fonts that are commonly available on Windows
        matplotlib.rcParams["font.sans-serif"] = [
            "Segoe UI", "Microsoft YaHei", "Tahoma", "Arial", 
            "DejaVu Sans", "Liberation Sans", "Helvetica"
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False
        matplotlib.rcParams["axes.formatter.use_locale"] = False  # ไม่ใช้ locale
        matplotlib.rcParams["axes.formatter.use_mathtext"] = False  # ไม่ใช้ math text
        
        # Set default font to one that supports Thai - use available fonts
        try:
            import matplotlib.font_manager as fm
            # Use fonts that are commonly available on Windows
            available_fonts = ["Segoe UI", "Microsoft YaHei", "Tahoma", "Arial"]
            for font_name in available_fonts:
                try:
                    font_path = fm.findfont(fm.FontProperties(family=font_name))
                    if font_path and "DejaVuSans" not in font_path:  # Avoid fallback
                        matplotlib.rcParams["font.family"] = font_name
                        logger.info(f"Font set to: {font_name}")
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not set font: {e}")
            matplotlib.rcParams["font.family"] = "Segoe UI"  # Fallback
        
        logger.info("Matplotlib font settings and locale settings applied")
    except Exception as e:
        logger.error(f"Error applying matplotlib style: {e}")
        # Emergency fallback
        try:
            import matplotlib
            matplotlib.rcParams["figure.facecolor"] = "#1e1e1e"
            matplotlib.rcParams["axes.facecolor"] = "#1e1e1e"
            matplotlib.rcParams["axes.edgecolor"] = "#404040"
            matplotlib.rcParams["axes.labelcolor"] = "#ffffff"
            matplotlib.rcParams["xtick.color"] = "#ffffff"
            matplotlib.rcParams["ytick.color"] = "#ffffff"
            matplotlib.rcParams["text.color"] = "#ffffff"
            matplotlib.rcParams["grid.color"] = "#404040"
            matplotlib.rcParams["grid.alpha"] = 0.3
            logger.info("Emergency fallback matplotlib dark theme applied")
        except Exception as fallback_error:
            logger.error(f"Emergency fallback failed: {fallback_error}")
    
    logger.info("Theme application completed")

def apply_theme_from_config(app: QApplication, config):
    """Apply theme from configuration object"""
    logger.info("Applying theme from configuration...")
    
    try:
        # Apply font with safe size access
        font = QFont(config.font_family, config.font_size)
        app.setFont(font)
        # Use safe method to get font size
        try:
            font_size = font.pointSize() if font.pointSize() > 0 else font.pixelSize()
            logger.info(f"Font set to: {font.family()} size {font_size}")
        except Exception:
            logger.info(f"Font set to: {font.family()}")
    except Exception as e:
        logger.error(f"Error setting font: {e}")
        # Fallback to default font
        try:
            fallback_font = QFont("Segoe UI", 11)
            app.setFont(fallback_font)
            logger.info("Fallback font applied")
        except Exception:
            logger.error("Failed to apply fallback font")

    # Apply QSS
    try:
        qss_path = config.qt_qss_path
        logger.info(f"Looking for QSS file at: {qss_path}")
        if os.path.isfile(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                qss_content = f.read()
                app.setStyleSheet(qss_content)
                logger.info(f"QSS loaded successfully, length: {len(qss_content)}")
        else:
            logger.warning(f"QSS file not found at: {qss_path}")
            # Fallback to default
            default_qss_path = os.path.join(os.path.dirname(__file__), "qdark.qss")
            if os.path.isfile(default_qss_path):
                with open(default_qss_path, "r", encoding="utf-8") as f:
                    qss_content = f.read()
                    app.setStyleSheet(qss_content)
                    logger.info("Fallback QSS loaded")
    except Exception as e:
        logger.error(f"Error loading QSS: {e}")
    
    # Apply matplotlib settings from config
    try:
        apply_mpl_from_config(config)
    except Exception as e:
        logger.error(f"Error applying matplotlib settings: {e}")
        # Fallback to default matplotlib settings
        try:
            import matplotlib
            # Set basic dark theme colors
            matplotlib.rcParams["figure.facecolor"] = "#1e1e1e"
            matplotlib.rcParams["axes.facecolor"] = "#1e1e1e"
            matplotlib.rcParams["axes.edgecolor"] = "#404040"
            matplotlib.rcParams["axes.labelcolor"] = "#ffffff"
            matplotlib.rcParams["xtick.color"] = "#ffffff"
            matplotlib.rcParams["ytick.color"] = "#ffffff"
            matplotlib.rcParams["text.color"] = "#ffffff"
            matplotlib.rcParams["grid.color"] = "#404040"
            matplotlib.rcParams["grid.alpha"] = 0.3
            logger.info("Fallback matplotlib dark theme applied")
        except Exception as fallback_error:
            logger.error(f"Fallback matplotlib theme failed: {fallback_error}")

def apply_mpl_from_config(config):
    """Apply matplotlib settings from configuration"""
    logger.info("Applying matplotlib settings from configuration...")
    
    try:
        import matplotlib
        # Load style file if exists
        if hasattr(config, 'mpl_style_path') and config.mpl_style_path and os.path.isfile(config.mpl_style_path):
            matplotlib.style.use(config.mpl_style_path)
            logger.info(f"Matplotlib style loaded from: {config.mpl_style_path}")
        
        # Override with config values
        mpl_config = config
        
        # Grid settings
        if hasattr(mpl_config, 'grid_enabled'):
            matplotlib.rcParams["axes.grid"] = bool(mpl_config.grid_enabled)
        if hasattr(mpl_config, 'grid_alpha'):
            matplotlib.rcParams["grid.alpha"] = float(mpl_config.grid_alpha)
        if hasattr(mpl_config, 'grid_linestyle'):
            matplotlib.rcParams["grid.linestyle"] = str(mpl_config.grid_linestyle)
        
        # Color settings
        if hasattr(mpl_config, 'axes_edgecolor'):
            matplotlib.rcParams["axes.edgecolor"] = str(mpl_config.axes_edgecolor)
        if hasattr(mpl_config, 'text_color'):
            matplotlib.rcParams["text.color"] = str(mpl_config.text_color)
        
        # Color cycle
        if hasattr(mpl_config, 'color_cycle') and mpl_config.color_cycle:
            try:
                matplotlib.rcParams["axes.prop_cycle"] = cycler(color=list(mpl_config.color_cycle))
                logger.info(f"Color cycle set with {len(mpl_config.color_cycle)} colors")
            except Exception as e:
                logger.error(f"Error setting color cycle: {e}")
        
        # Font settings - use fonts that are commonly available on Windows
        matplotlib.rcParams["font.sans-serif"] = [
            "Segoe UI", "Microsoft YaHei", "Tahoma", "Arial", 
            "DejaVu Sans", "Liberation Sans", "Helvetica"
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False
        
        # Set default font to one that is available
        try:
            import matplotlib.font_manager as fm
            # Use fonts that are commonly available on Windows
            available_fonts = ["Segoe UI", "Microsoft YaHei", "Tahoma", "Arial"]
            for font_name in available_fonts:
                try:
                    font_path = fm.findfont(fm.FontProperties(family=font_name))
                    if font_path and "DejaVuSans" not in font_path:  # Avoid fallback
                        matplotlib.rcParams["font.family"] = font_name
                        logger.info(f"Font set to: {font_name}")
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not set font: {e}")
            matplotlib.rcParams["font.family"] = "Segoe UI"  # Fallback
        
        # บังคับให้ Matplotlib ไม่ใช้ locale และแสดงเลขอารบิก
        matplotlib.rcParams["axes.formatter.use_locale"] = False  # ไม่ใช้ locale
        matplotlib.rcParams["axes.formatter.use_mathtext"] = False  # ไม่ใช้ math text
        
        logger.info("Matplotlib settings applied successfully")
        
    except Exception as e:
        logger.error(f"Error applying matplotlib settings: {e}")
        # Fallback to basic dark theme
        try:
            import matplotlib
            matplotlib.rcParams["figure.facecolor"] = "#1e1e1e"
            matplotlib.rcParams["axes.facecolor"] = "#1e1e1e"
            matplotlib.rcParams["axes.edgecolor"] = "#404040"
            matplotlib.rcParams["axes.labelcolor"] = "#ffffff"
            matplotlib.rcParams["xtick.color"] = "#ffffff"
            matplotlib.rcParams["ytick.color"] = "#ffffff"
            matplotlib.rcParams["text.color"] = "#ffffff"
            matplotlib.rcParams["grid.color"] = "#404040"
            matplotlib.rcParams["grid.alpha"] = 0.3
            logger.info("Fallback matplotlib dark theme applied")
        except Exception as fallback_error:
            logger.error(f"Fallback matplotlib theme failed: {fallback_error}")

def refresh_matplotlib_canvases():
    """Refresh all matplotlib canvases to apply new settings"""
    try:
        import matplotlib.pyplot as plt
        plt.rcdefaults()  # Reset to defaults
        logger.info("Matplotlib canvases refreshed")
    except Exception as e:
        logger.error(f"Error refreshing matplotlib: {e}")