from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtWidgets import QApplication
import os
import logging
import matplotlib
from cycler import cycler
from typing import Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SciPlotter dark palette handed to qdarktheme so its generated theme (menus,
# buttons, combos, scrollbars, tabs, dialogs, status/toolbar strips) lands in
# the same blue-graphite family as our hand-written QSS. Keep in sync with:
# shell.qss / sidepanel.qss / toolbar.qss / widgets/workbook.py /
# UI/mdi_workspace.py (bg #1e2126, surface #23272e, border #3a3f44,
# accent #4F9CF9, text #e6e6e6).
DARK_CUSTOM_COLORS = {
    "primary": "#4F9CF9",
    "background": "#1e2126",
    "border": "#3a3f44",
    "foreground": "#e6e6e6",
    "input.background": "#262b33",
    "statusBar.background": "#181b20",
    "toolbar.background": "#1b1e23",
}


def _setup_qdarktheme(app: QApplication, extra_qss: str) -> None:
    """Apply qdarktheme with our palette; degrade gracefully on old versions."""
    import qdarktheme

    try:
        qdarktheme.setup_theme(
            "dark", custom_colors=DARK_CUSTOM_COLORS, additional_qss=extra_qss
        )
    except TypeError:
        # older signature without custom_colors/additional_qss
        try:
            qdarktheme.setup_theme("dark", additional_qss=extra_qss)
        except TypeError:
            qdarktheme.setup_theme("dark")
            app.setStyleSheet((app.styleSheet() or "") + "\n" + extra_qss)

def _setup_thai_fonts() -> Optional[str]:
    """Ensure Matplotlib can render Thai text consistently.
    Tries bundled fonts first, then common system fonts.

    Returns the selected family name if set, else None.
    """
    try:
        import matplotlib.font_manager as fm
        base = os.path.dirname(__file__)
        assets_fonts = os.path.join(os.path.dirname(base), "assets", "fonts")

        chosen = None

        # 1) Register bundled Sarabun if present
        candidates = [
            (os.path.join(assets_fonts, "THSarabunNew.ttf"), "TH Sarabun New"),
            (os.path.join(assets_fonts, "THSarabunNew Bold.ttf"), "TH Sarabun New"),
        ]
        for path, family in candidates:
            try:
                if os.path.isfile(path):
                    fm.fontManager.addfont(path)
                    chosen = chosen or family
            except Exception:
                pass

        # 2) Known Thai-capable system fonts in order of preference
        thai_pref = [
            "Noto Sans Thai",  # Google font
            "TH Sarabun New",  # Bundled
            "Sarabun",         # Alternative family name
            "Tahoma",          # Windows, has Thai glyphs
            "Segoe UI",        # Windows modern UI font
        ]

        # Rebuild the font manager to ensure newly added fonts are visible
        try:
            # Matplotlib >= 3.6
            fm._load_fontmanager(try_read_cache=False)  # type: ignore[attr-defined]
        except Exception:
            try:
                # Older Matplotlib
                fm._rebuild()  # type: ignore[attr-defined]
            except Exception:
                pass

        # Build fallback chains (family can be a list)
        chain = thai_pref + [
            "Microsoft YaHei", "Arial", "DejaVu Sans", "Liberation Sans", "Helvetica"
        ]
        matplotlib.rcParams["font.sans-serif"] = chain
        matplotlib.rcParams["font.family"] = chain

        # Pick the first available Thai-capable family for logging
        for fam in thai_pref:
            try:
                fp = fm.findfont(fm.FontProperties(family=fam), fallback_to_default=False)
                if fp and os.path.exists(fp):
                    return fam
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"Thai font setup skipped: {e}")
    return None

def _convert_linestyle_from_thai(thai_text: str) -> str:
    """Convert Thai description to matplotlib linestyle value"""
    if "เส้นทึบ" in thai_text:
        return "-"
    elif "เส้นประ" in thai_text:
        return "--"
    elif "เส้นจุด" in thai_text:
        return ":"
    elif "เส้นประ-จุด" in thai_text:
        return "-."
    else:
        return "-"

def _read_override_qss():
    """Read our component-specific QSS (rail/workbook/docks/sidepanel) to layer
    on top of the base theme. Returns the concatenated stylesheet string."""
    base_dir = os.path.dirname(__file__)
    parts = []
    for name in ("sidepanel.qss", "shell.qss"):
        p = os.path.join(base_dir, name)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    parts.append(f.read())
            except Exception as e:
                logger.warning(f"Override QSS skipped ({name}): {e}")
    return "\n".join(parts)


def apply_qss(app: QApplication, qss_path: str = None):
    """Apply the app theme.

    Prefers qdarktheme (modern flat dark, with a proper QPalette) as the base
    and layers our component overrides (sidepanel/shell) on top. Falls back to
    the legacy dark_modern.qss if qdarktheme is unavailable.
    """
    extra_qss = _read_override_qss()

    # Base theme: qdarktheme if installed
    try:
        _setup_qdarktheme(app, extra_qss)
        logger.info(f"Theme: qdarktheme dark + custom colors + overrides ({len(extra_qss)} chars)")
        return
    except Exception as e:
        logger.warning(f"qdarktheme unavailable, using dark_modern.qss: {e}")

    # Fallback: legacy hand-rolled dark theme
    try:
        base_dir = os.path.dirname(__file__)
        if qss_path and os.path.isfile(qss_path):
            path = qss_path
        else:
            modern = os.path.join(base_dir, "dark_modern.qss")
            legacy = os.path.join(base_dir, "qdark.qss")
            path = modern if os.path.isfile(modern) else legacy
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                qss_content = f.read()
            app.setStyleSheet(qss_content + "\n" + extra_qss)
            logger.info(f"QSS loaded: {path} (+overrides)")
        else:
            logger.warning("No QSS file found; skipping stylesheet application")
    except Exception as e:
        logger.error(f"Error applying QSS: {e}")

def apply_font(app: QApplication, font_family: str, font_size: int):
    """Apply font to application"""
    logger.info(f"Applying font: {font_family} {font_size}pt")
    
    try:
        font = QFont(font_family, font_size)
        if font.exactMatch():
            app.setFont(font)
            logger.info(f"Font applied successfully: {font.family()}")
        else:
            logger.warning(f"Font not found: {font_family}, using fallback")
            # Try fallback fonts
            fallback_fonts = ["Segoe UI", "Arial", "Tahoma"]
            for fallback in fallback_fonts:
                fallback_font = QFont(fallback, font_size)
                if fallback_font.exactMatch():
                    app.setFont(fallback_font)
                    logger.info(f"Fallback font applied: {fallback}")
                    break
    except Exception as e:
        logger.error(f"Error applying font: {e}")

def apply_mpl_style(style_path: str = None):
    """Apply matplotlib style file"""
    logger.info(f"Applying matplotlib style from: {style_path}")
    
    try:
        import matplotlib
        if style_path and os.path.isfile(style_path):
            matplotlib.style.use(style_path)
            logger.info(f"Matplotlib style applied successfully from: {style_path}")
        else:
            logger.warning(f"Matplotlib style file not found: {style_path}")
    except Exception as e:
        logger.error(f"Error applying matplotlib style: {e}")

def apply_mpl_overrides(grid_enabled: bool = True, grid_alpha: float = 0.3, 
                       grid_linestyle: str = "-", axes_color: str = "#000000", 
                       text_color: str = "#000000", color_cycle: list = None,
                       font_family: Optional[str] = None):
    """Apply matplotlib style overrides"""
    logger.info("Applying matplotlib style overrides")
    
    try:
        import matplotlib
        
        # Prefer Thai-capable fonts if available
        fam = None
        if font_family:
            # Explicit override from settings/dialog
            try:
                import matplotlib.font_manager as fm
                fm._load_fontmanager(try_read_cache=False)  # refresh
            except Exception:
                pass
            matplotlib.rcParams["font.family"] = [font_family,
                "Noto Sans Thai", "TH Sarabun New", "Sarabun", "Tahoma", "Segoe UI", "Arial", "DejaVu Sans"]
            fam = font_family
        else:
            # Auto choose Thai-capable fonts
            fam = _setup_thai_fonts()
        if fam:
            logger.info(f"Matplotlib font.family set to: {fam}")

        # Avoid TeX (Thai not supported there by default)
        matplotlib.rcParams["text.usetex"] = False

        # Dark canvas blending defaults
        matplotlib.rcParams["figure.facecolor"] = "#1e2126"
        matplotlib.rcParams["axes.facecolor"] = "#1e2126"
        matplotlib.rcParams["grid.color"] = "#3a3f44"
        matplotlib.rcParams["axes.edgecolor"] = axes_color
        matplotlib.rcParams["axes.labelcolor"] = text_color
        matplotlib.rcParams["xtick.color"] = text_color
        matplotlib.rcParams["ytick.color"] = text_color
        matplotlib.rcParams["text.color"] = text_color

        # Grid settings
        matplotlib.rcParams["axes.grid"] = grid_enabled
        matplotlib.rcParams["grid.alpha"] = grid_alpha
        matplotlib.rcParams["grid.linestyle"] = grid_linestyle
        
        
        # Color cycle
        if color_cycle:
            matplotlib.rcParams["axes.prop_cycle"] = cycler(color=color_cycle)
            logger.info(f"Color cycle set with {len(color_cycle)} colors")
        
        logger.info("Matplotlib overrides applied successfully")
        
    except Exception as e:
        logger.error(f"Error applying matplotlib overrides: {e}")

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
            # Try alternative QSS files
            alternative_qss_files = ["light.qss", "dark.qss"]
            for alt_file in alternative_qss_files:
                alt_path = os.path.join(os.path.dirname(__file__), alt_file)
                if os.path.isfile(alt_path):
                    with open(alt_path, "r", encoding="utf-8") as f:
                        qss_content = f.read()
                        app.setStyleSheet(qss_content)
                        logger.info(f"Alternative QSS loaded: {alt_file}")
                        break
    except Exception as e:
        logger.error(f"Error loading QSS: {e}")
        # Continue without QSS - palette will still work

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
            matplotlib.rcParams["figure.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.edgecolor"] = "#3a3f44"
            matplotlib.rcParams["axes.labelcolor"] = "#e6e6e6"
            matplotlib.rcParams["xtick.color"] = "#cfd3d6"
            matplotlib.rcParams["ytick.color"] = "#cfd3d6"
            matplotlib.rcParams["text.color"] = "#e6e6e6"
            matplotlib.rcParams["grid.color"] = "#3a3f44"
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
            matplotlib.rcParams["figure.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.edgecolor"] = "#3a3f44"
            matplotlib.rcParams["axes.labelcolor"] = "#e6e6e6"
            matplotlib.rcParams["xtick.color"] = "#cfd3d6"
            matplotlib.rcParams["ytick.color"] = "#cfd3d6"
            matplotlib.rcParams["text.color"] = "#e6e6e6"
            matplotlib.rcParams["grid.color"] = "#3a3f44"
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

    # Apply QSS (prefer modern dark if available)
    try:
        qss_path = getattr(config, 'qt_qss_path', None)
        if qss_path and os.path.isfile(qss_path):
            path = qss_path
        else:
            base = os.path.dirname(__file__)
            modern = os.path.join(base, "dark_modern.qss")
            legacy = os.path.join(base, "qdark.qss")
            path = modern if os.path.isfile(modern) else legacy

        # Base theme: qdarktheme (modern flat dark + QPalette) if available,
        # with our component overrides (sidepanel/shell) layered on top.
        extra_qss = _read_override_qss()
        applied = False
        try:
            _setup_qdarktheme(app, extra_qss)
            logger.info(f"Theme: qdarktheme dark + custom colors + overrides ({len(extra_qss)} chars)")
            applied = True
        except Exception as e:
            logger.warning(f"qdarktheme unavailable, using {os.path.basename(path)}: {e}")
        if not applied:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    qss_content = f.read()
                app.setStyleSheet(qss_content + "\n" + extra_qss)
                logger.info(f"QSS loaded: {path} (+overrides)")
            else:
                logger.warning("No QSS file found; skipping stylesheet application")
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
            matplotlib.rcParams["figure.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.edgecolor"] = "#3a3f44"
            matplotlib.rcParams["axes.labelcolor"] = "#e6e6e6"
            matplotlib.rcParams["xtick.color"] = "#cfd3d6"
            matplotlib.rcParams["ytick.color"] = "#cfd3d6"
            matplotlib.rcParams["text.color"] = "#e6e6e6"
            matplotlib.rcParams["grid.color"] = "#3a3f44"
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
        try:
            if hasattr(mpl_config, 'grid_enabled'):
                matplotlib.rcParams["axes.grid"] = bool(mpl_config.grid_enabled)
            if hasattr(mpl_config, 'grid_alpha'):
                matplotlib.rcParams["grid.alpha"] = float(mpl_config.grid_alpha)
            if hasattr(mpl_config, 'grid_linestyle'):
                # Convert Thai description to matplotlib linestyle value
                linestyle = _convert_linestyle_from_thai(str(mpl_config.grid_linestyle))
                matplotlib.rcParams["grid.linestyle"] = linestyle
                logger.info(f"Grid linestyle set to: {linestyle}")
        except Exception as e:
            logger.error(f"Error setting grid parameters: {e}")
            # Set safe defaults
            matplotlib.rcParams["axes.grid"] = True
            matplotlib.rcParams["grid.alpha"] = 0.3
            matplotlib.rcParams["grid.linestyle"] = "-"
        
        # Color settings and dark canvas blending
        try:
            matplotlib.rcParams["text.usetex"] = False
            if hasattr(mpl_config, 'axes_edgecolor'):
                matplotlib.rcParams["axes.edgecolor"] = str(mpl_config.axes_edgecolor)
            if hasattr(mpl_config, 'text_color'):
                matplotlib.rcParams["text.color"] = str(mpl_config.text_color)
            # Ensure canvas matches dark palette
            matplotlib.rcParams["figure.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.facecolor"] = "#1e2126"
            matplotlib.rcParams["grid.color"] = "#3a3f44"
            matplotlib.rcParams["xtick.color"] = matplotlib.rcParams["text.color"]
            matplotlib.rcParams["ytick.color"] = matplotlib.rcParams["text.color"]
            matplotlib.rcParams["axes.labelcolor"] = matplotlib.rcParams["text.color"]
            # Font from config if provided; otherwise auto Thai
            try:
                cfg_font = getattr(mpl_config, 'font_family', '') or ''
            except Exception:
                cfg_font = ''
            if cfg_font:
                try:
                    import matplotlib.font_manager as fm
                    fm._load_fontmanager(try_read_cache=False)
                except Exception:
                    pass
                matplotlib.rcParams["font.family"] = [cfg_font,
                    "Noto Sans Thai", "TH Sarabun New", "Sarabun", "Tahoma", "Segoe UI", "Arial", "DejaVu Sans"]
                logger.info(f"Matplotlib font.family set from config: {cfg_font}")
            else:
                fam = _setup_thai_fonts()
                if fam:
                    logger.info(f"Matplotlib font.family set to: {fam}")
        except Exception as e:
            logger.error(f"Error setting color parameters: {e}")
            # Set safe defaults
            matplotlib.rcParams["axes.edgecolor"] = "#3a3f44"
            matplotlib.rcParams["text.color"] = "#e6e6e6"
            matplotlib.rcParams["figure.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.facecolor"] = "#1e2126"
            matplotlib.rcParams["grid.color"] = "#3a3f44"
        
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
            matplotlib.rcParams["figure.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.facecolor"] = "#1e2126"
            matplotlib.rcParams["axes.edgecolor"] = "#3a3f44"
            matplotlib.rcParams["axes.labelcolor"] = "#e6e6e6"
            matplotlib.rcParams["xtick.color"] = "#cfd3d6"
            matplotlib.rcParams["ytick.color"] = "#cfd3d6"
            matplotlib.rcParams["text.color"] = "#e6e6e6"
            matplotlib.rcParams["grid.color"] = "#3a3f44"
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
