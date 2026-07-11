from dataclasses import dataclass
import re

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPalette, QPixmap, QColor, QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget
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


DEFAULT_ACCENT = "#4F9CF9"
_QT_FONTS_REGISTERED = False
_MONOCHROME_ICON_KEYS: set[int] = set()


@dataclass(frozen=True)
class ThemePalette:
    mode: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    background: str
    surface: str
    surface_alt: str
    input_background: str
    border: str
    text: str
    muted: str
    disabled: str
    status_background: str
    toolbar_background: str

    def qdarktheme_colors(self) -> dict[str, str]:
        return {
            "primary": self.accent,
            "background": self.background,
            "border": self.border,
            "foreground": self.text,
            "input.background": self.input_background,
            "statusBar.background": self.status_background,
            "toolbar.background": self.toolbar_background,
        }


def _valid_hex_color(value: str, fallback: str = DEFAULT_ACCENT) -> str:
    color = QColor(str(value or "").strip())
    if not color.isValid():
        color = QColor(fallback)
    return color.name().upper()


def register_bundled_qt_fonts() -> None:
    """Register bundled Thai-capable fonts for the Qt UI once per process."""
    global _QT_FONTS_REGISTERED
    if _QT_FONTS_REGISTERED:
        return
    fonts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
    for filename in ("THSarabunNew.ttf", "THSarabunNew Bold.ttf"):
        path = os.path.join(fonts_dir, filename)
        if os.path.isfile(path):
            QFontDatabase.addApplicationFont(path)
    _QT_FONTS_REGISTERED = True


def _shift_color(value: str, target: str, amount: float) -> str:
    source = QColor(value)
    destination = QColor(target)
    amount = max(0.0, min(1.0, float(amount)))
    red = round(source.red() + (destination.red() - source.red()) * amount)
    green = round(source.green() + (destination.green() - source.green()) * amount)
    blue = round(source.blue() + (destination.blue() - source.blue()) * amount)
    return QColor(red, green, blue).name().upper()


def _relative_luminance(value: str) -> float:
    color = QColor(value)

    def linear(channel: int) -> float:
        component = channel / 255.0
        return component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(color.red()) + 0.7152 * linear(color.green()) + 0.0722 * linear(color.blue())


def _contrast_text(value: str, *, dark: str = "#17202B", light: str = "#FFFFFF") -> str:
    background_luminance = _relative_luminance(value)

    def ratio(candidate: str) -> float:
        candidate_luminance = _relative_luminance(candidate)
        high = max(background_luminance, candidate_luminance)
        low = min(background_luminance, candidate_luminance)
        return (high + 0.05) / (low + 0.05)

    return dark if ratio(dark) >= ratio(light) else light


def build_theme_palette(
    mode: str = "dark",
    accent_color: str = DEFAULT_ACCENT,
    background_color: str = "",
) -> ThemePalette:
    """Return the complete palette used by Qt, QSS, and late-created popups."""
    mode = "light" if str(mode).lower() == "light" else "dark"
    accent = _valid_hex_color(accent_color)
    accent_text = _contrast_text(accent)

    custom_background = QColor(str(background_color or "").strip())
    if custom_background.isValid():
        background = custom_background.name().upper()
        mode = "light" if _contrast_text(background) == "#17202B" else "dark"
        if mode == "light":
            text = "#17202B"
            return ThemePalette(
                mode=mode,
                accent=accent,
                accent_hover=_shift_color(accent, "#000000", 0.10),
                accent_pressed=_shift_color(accent, "#000000", 0.20),
                accent_text=accent_text,
                background=background,
                surface=_shift_color(background, "#FFFFFF", 0.16),
                surface_alt=_shift_color(background, "#000000", 0.05),
                input_background=_shift_color(background, "#FFFFFF", 0.20),
                border=_shift_color(background, "#000000", 0.20),
                text=text,
                muted=_shift_color(text, background, 0.42),
                disabled=_shift_color(text, background, 0.60),
                status_background=_shift_color(background, "#000000", 0.04),
                toolbar_background=_shift_color(background, "#000000", 0.06),
            )

        text = "#F2F5F8"
        return ThemePalette(
            mode=mode,
            accent=accent,
            accent_hover=_shift_color(accent, "#FFFFFF", 0.12),
            accent_pressed=_shift_color(accent, "#000000", 0.16),
            accent_text=accent_text,
            background=background,
            surface=_shift_color(background, "#FFFFFF", 0.06),
            surface_alt=_shift_color(background, "#FFFFFF", 0.10),
            input_background=_shift_color(background, "#FFFFFF", 0.10),
            border=_shift_color(background, "#FFFFFF", 0.20),
            text=text,
            muted=_shift_color(text, background, 0.40),
            disabled=_shift_color(text, background, 0.60),
            status_background=_shift_color(background, "#000000", 0.14),
            toolbar_background=_shift_color(background, "#000000", 0.08),
        )

    if mode == "light":
        return ThemePalette(
            mode=mode,
            accent=accent,
            accent_hover=_shift_color(accent, "#000000", 0.10),
            accent_pressed=_shift_color(accent, "#000000", 0.20),
            accent_text=accent_text,
            background="#F4F6F8",
            surface="#FFFFFF",
            surface_alt="#EEF2F6",
            input_background="#FFFFFF",
            border="#CDD5DF",
            text="#1D2733",
            muted="#657080",
            disabled="#98A2B0",
            status_background="#E9EDF2",
            toolbar_background="#EEF2F6",
        )

    return ThemePalette(
        mode=mode,
        accent=accent,
        accent_hover=_shift_color(accent, "#FFFFFF", 0.12),
        accent_pressed=_shift_color(accent, "#000000", 0.16),
        accent_text=accent_text,
        background="#1E2126",
        surface="#23272E",
        surface_alt="#262B33",
        input_background="#262B33",
        border="#3A3F44",
        text="#E6E6E6",
        muted="#AAB0B6",
        disabled="#747B84",
        status_background="#181B20",
        toolbar_background="#1B1E23",
    )


def _setup_qdarktheme(
    app: QApplication,
    mode: str,
    custom_colors: dict[str, str],
    extra_qss: str,
) -> None:
    """Apply qdarktheme with our palette; degrade gracefully on old versions."""
    import qdarktheme

    try:
        qdarktheme.setup_theme(
            mode, custom_colors=custom_colors, additional_qss=extra_qss
        )
    except TypeError:
        # older signature without custom_colors/additional_qss
        try:
            qdarktheme.setup_theme(mode, additional_qss=extra_qss)
        except TypeError:
            qdarktheme.setup_theme(mode)
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


_DARK_BACKGROUND_ALIASES = {
    "#121212", "#15181d", "#17191c", "#171a1f", "#181b20", "#1b1e23",
    "#1b1f25", "#1b2027", "#1d2023", "#1e1e1e", "#1e2126", "#202225",
    "#202326", "#20242a",
}
_DARK_SURFACE_ALIASES = {
    "#22262d", "#222833", "#222a35", "#23272e", "#252525", "#2b2b2b",
}
_DARK_SURFACE_ALT_ALIASES = {
    "#262b33", "#262c34", "#283446", "#29313a", "#2a2f36", "#2a3038",
    "#2b2f36", "#2b313a", "#2d333b", "#303640", "#333333", "#3c3c3c",
}
_BORDER_ALIASES = {
    "#2b323c", "#2f343b", "#2f3540", "#30343a", "#303a47", "#31363c",
    "#323844", "#33373d", "#343941", "#354153", "#384250", "#3a3f44",
    "#3a4553", "#3c424a", "#404040", "#4a5666", "#555555", "#e5e5e5",
    "#dee2e6", "#dddddd",
}
_TEXT_ALIASES = {
    "#1a1a1a", "#111827", "#17202a", "#d7d7d7", "#dcdcdc",
    "#d7dde4", "#dce3eb", "#dfe7f0", "#e6e6e6", "#e8eef7", "#eaeaea",
    "#eef2f7", "#eef5ff", "#eef6ff", "#f0f2f4", "#f0f3f7", "#f3f6fa",
}
_MUTED_ALIASES = {
    "#495057", "#647080", "#657080", "#666666", "#66717f", "#6b7178",
    "#747b84", "#808080", "#8b929c", "#8b95a3", "#94a3b8", "#98a2b0",
    "#9aa0a6", "#9aa3af", "#9aa4b2", "#9aa5b2", "#9fb3cc", "#aab0b6",
    "#8f9aa8", "#adb5bd", "#b8bec6", "#c7ced8", "#c8cdd3", "#cfd3d6",
}
_LIGHT_SURFACE_ALIASES = {
    "#e8f4fd", "#ededed", "#eef2f7", "#f0f0f0", "#f1f1f1", "#f6f7f9",
    "#f8f9fa", "#fafafa",
}
_ACCENT_ALIASES = {
    "#007acc", "#007bff", "#0066cc", "#0e639c", "#2196f3", "#228be6",
    "#2563eb", "#2f80ed", "#4f9cf9", "#e5f0ff",
}
_ACCENT_HOVER_ALIASES = {"#0088dd", "#1177bb", "#3da1ff", "#5fa8fb"}
_ACCENT_PRESSED_ALIASES = {
    "#004085", "#0056b3", "#0066aa", "#0a4d7a", "#0f5f9f", "#14598b",
    "#174f7d", "#264f78", "#2b4066", "#3f86e0",
}
_ACCENT_TEXT_ALIASES = {"#0f1620", "#1c1c1c"}


def render_theme_qss(
    source: str,
    palette: ThemePalette,
    font_family: str = "",
    font_size: int = 10,
) -> str:
    """Retint component QSS and scale authored typography from a 10pt base."""
    if not source:
        return ""

    aliases = {}
    aliases.update({value: palette.background for value in _DARK_BACKGROUND_ALIASES})
    aliases.update({value: palette.surface for value in _DARK_SURFACE_ALIASES})
    aliases.update({value: palette.surface_alt for value in _DARK_SURFACE_ALT_ALIASES})
    aliases.update({value: palette.border for value in _BORDER_ALIASES})
    aliases.update({value: palette.text for value in _TEXT_ALIASES})
    aliases.update({value: palette.muted for value in _MUTED_ALIASES})
    aliases.update({value: palette.surface_alt for value in _LIGHT_SURFACE_ALIASES})
    aliases.update({value: palette.accent for value in _ACCENT_ALIASES})
    aliases.update({value: palette.accent_hover for value in _ACCENT_HOVER_ALIASES})
    aliases.update({value: palette.accent_pressed for value in _ACCENT_PRESSED_ALIASES})
    aliases.update({value: palette.accent_text for value in _ACCENT_TEXT_ALIASES})

    light_backgrounds = {
        "#ffffff": palette.surface,
        "#fff": palette.surface,
        "#e5f0ff": palette.accent,
        "#e8f4fd": palette.surface_alt,
        "#ededed": palette.surface_alt,
        "#eef2f7": palette.surface_alt,
        "#f0f0f0": palette.surface_alt,
        "#f1f1f1": palette.surface_alt,
        "#f6f7f9": palette.surface_alt,
        "#f8f9fa": palette.surface_alt,
        "#fafafa": palette.surface_alt,
    }

    def replace_background(match: re.Match) -> str:
        value = match.group(2).lower()
        return match.group(1) + light_backgrounds.get(value, match.group(2))

    rendered = re.sub(
        r"(?i)(background(?:-color)?\s*:\s*)(#[0-9a-f]{3,6})(?![0-9a-f])",
        replace_background,
        source,
    )

    def replace_hex(match: re.Match) -> str:
        value = match.group(0).lower()
        return aliases.get(value, match.group(0))

    rendered = re.sub(r"#[0-9a-fA-F]{6}(?![0-9a-fA-F])", replace_hex, rendered)

    accent = QColor(palette.accent)
    rendered = re.sub(
        r"(?i)rgba\(\s*79\s*,\s*156\s*,\s*249\s*,\s*([0-9.]+)\s*\)",
        lambda match: f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, {match.group(1)})",
        rendered,
    )
    if palette.mode == "light":
        rendered = re.sub(
            r"(?i)rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*([0-9.]+)\s*\)",
            lambda match: f"rgba(29, 39, 51, {match.group(1)})",
            rendered,
        )

    rendered = re.sub(
        r"(?i)(selection-color\s*:\s*)#(?:fff|ffffff)(?![0-9a-f])",
        lambda match: match.group(1) + palette.accent_text,
        rendered,
    )

    def adapt_white_text(match: re.Match) -> str:
        selector, body = match.group(1), match.group(2)
        background_matches = re.findall(
            r"(?i)background(?:-color)?\s*:\s*(#[0-9a-f]{6})",
            body,
        )
        text_color = palette.text
        if background_matches:
            background = QColor(background_matches[-1])
            if background.isValid():
                text_color = "#FFFFFF" if background.lightness() < 145 else "#17202B"
        body = re.sub(
            r"(?i)(?<![-\w])(color\s*:\s*)#(?:fff|ffffff)(?![0-9a-f])",
            lambda color_match: color_match.group(1) + text_color,
            body,
        )
        return selector + "{" + body + "}"

    rendered = re.sub(r"([^{}]+)\{([^{}]*)\}", adapt_white_text, rendered)

    if font_family:
        escaped_family = font_family.replace('"', '\\"')

        def replace_family(match: re.Match) -> str:
            current = match.group(1).lower()
            if any(name in current for name in ("monospace", "consolas", "monaco", "courier")):
                return match.group(0)
            return f'font-family: "{escaped_family}";'

        rendered = re.sub(r"(?i)font-family\s*:\s*([^;]+);", replace_family, rendered)

    scale = max(0.8, min(2.4, int(font_size) / 10.0))

    def scale_size(match: re.Match) -> str:
        value = float(match.group(1)) * scale
        formatted = f"{value:.2f}".rstrip("0").rstrip(".")
        return f"font-size: {formatted}{match.group(2)};"

    rendered = re.sub(
        r"(?i)font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*(pt|px)\s*;",
        scale_size,
        rendered,
    )
    return rendered


def _font_and_popup_qss(palette: ThemePalette, font_family: str, font_size: int) -> str:
    family = (font_family or "Segoe UI").replace('"', '\\"')
    return f"""
* {{ font-family: "{family}"; font-size: {int(font_size)}pt; }}
QDialog, QMessageBox, QInputDialog, QFileDialog, QColorDialog {{
    background-color: {palette.background};
    color: {palette.text};
}}
QToolTip {{
    background-color: {palette.surface};
    color: {palette.text};
    border: 1px solid {palette.border};
    padding: 4px 6px;
}}
QAbstractItemView {{
    selection-background-color: {palette.accent};
    selection-color: {palette.accent_text};
}}
"""


def _apply_qpalette(app: QApplication, palette: ThemePalette) -> None:
    qt_palette = QPalette()
    qt_palette.setColor(QPalette.Window, QColor(palette.background))
    qt_palette.setColor(QPalette.WindowText, QColor(palette.text))
    qt_palette.setColor(QPalette.Base, QColor(palette.input_background))
    qt_palette.setColor(QPalette.AlternateBase, QColor(palette.surface_alt))
    qt_palette.setColor(QPalette.ToolTipBase, QColor(palette.surface))
    qt_palette.setColor(QPalette.ToolTipText, QColor(palette.text))
    qt_palette.setColor(QPalette.Text, QColor(palette.text))
    qt_palette.setColor(QPalette.Button, QColor(palette.surface_alt))
    qt_palette.setColor(QPalette.ButtonText, QColor(palette.text))
    qt_palette.setColor(QPalette.BrightText, QColor(palette.accent_text))
    qt_palette.setColor(QPalette.Link, QColor(palette.accent))
    qt_palette.setColor(QPalette.Highlight, QColor(palette.accent))
    qt_palette.setColor(QPalette.HighlightedText, QColor(palette.accent_text))
    qt_palette.setColor(QPalette.PlaceholderText, QColor(palette.muted))
    qt_palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(palette.disabled))
    qt_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(palette.disabled))
    qt_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(palette.disabled))
    app.setPalette(qt_palette)


def icon_theme_colors(palette: ThemePalette) -> dict[str, str]:
    """High-contrast icon colors for every QIcon mode and checked state."""
    if palette.mode == "light":
        normal = "#344252"
        disabled = "#98A2B0"
    else:
        normal = "#C7CDD5"
        disabled = "#68727E"
    return {
        "normal": normal,
        "disabled": disabled,
        "active": palette.accent,
        "selected": palette.accent,
        "checked": palette.accent,
    }


def _tint_pixmap(source: QPixmap, color: str) -> QPixmap:
    result = QPixmap(source.size())
    result.setDevicePixelRatio(source.devicePixelRatio())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), QColor(color))
    painter.end()
    return result


def themed_icon(source_icon: QIcon, palette: ThemePalette) -> QIcon:
    """Create a crisp monochrome icon with explicit Qt mode/state colors."""
    if source_icon.isNull():
        return QIcon()
    colors = icon_theme_colors(palette)
    # active / selected / checked all resolve to the accent color, so tint it
    # once and reuse. Rendering three fewer pixmaps per size roughly halves the
    # per-icon cost (icon creation was the single biggest build hotspot).
    icon = QIcon()
    rendered = False
    for extent in (16, 20, 24, 32):
        source = source_icon.pixmap(QSize(extent, extent), QIcon.Normal, QIcon.Off)
        if source.isNull():
            continue
        rendered = True
        normal = _tint_pixmap(source, colors["normal"])
        disabled = _tint_pixmap(source, colors["disabled"])
        accent = _tint_pixmap(source, colors["active"])
        icon.addPixmap(normal, QIcon.Normal, QIcon.Off)
        icon.addPixmap(accent, QIcon.Normal, QIcon.On)
        icon.addPixmap(disabled, QIcon.Disabled, QIcon.Off)
        icon.addPixmap(disabled, QIcon.Disabled, QIcon.On)
        icon.addPixmap(accent, QIcon.Active, QIcon.Off)
        icon.addPixmap(accent, QIcon.Active, QIcon.On)
        icon.addPixmap(accent, QIcon.Selected, QIcon.Off)
        icon.addPixmap(accent, QIcon.Selected, QIcon.On)
    result = icon if rendered else QIcon(source_icon)
    if not result.isNull():
        _MONOCHROME_ICON_KEYS.add(result.cacheKey())
    return result


def is_monochrome_icon(icon: QIcon) -> bool:
    return not icon.isNull() and icon.cacheKey() in _MONOCHROME_ICON_KEYS


def _refresh_icon_owner(owner, getter, setter, palette: ThemePalette) -> bool:
    current = getter()
    if current is None or current.isNull():
        return False
    current_key = current.cacheKey()
    previous_themed_key = getattr(owner, "_sciplotter_themed_icon_key", None)
    original = getattr(owner, "_sciplotter_original_icon", None)
    if original is None or current_key != previous_themed_key:
        original = QIcon(current)
        owner._sciplotter_original_icon = original
    icon = themed_icon(original, palette)
    setter(icon)
    owner._sciplotter_themed_icon_key = icon.cacheKey()
    return True


def refresh_application_icons(app: QApplication, palette: ThemePalette) -> None:
    """Recolor existing action/button icons without touching image thumbnails."""
    if app is None:
        return
    colors = icon_theme_colors(palette)
    app.setProperty("sciplotterIconNormalColor", colors["normal"])
    app.setProperty("sciplotterIconDisabledColor", colors["disabled"])

    actions = set()
    widgets = list(app.allWidgets())
    for widget in widgets:
        actions.update(widget.actions())
        actions.update(widget.findChildren(QAction))
    for action in actions:
        if not is_monochrome_icon(action.icon()) and not bool(
            action.property("sciplotterMonochromeIcon")
        ):
            continue
        _refresh_icon_owner(action, action.icon, action.setIcon, palette)

    for widget in widgets:
        if not isinstance(widget, QAbstractButton):
            continue
        if bool(widget.property("preserveIconColors")):
            continue
        if widget.__class__.__name__ == "ColorButton":
            continue
        default_action = getattr(widget, "defaultAction", lambda: None)()
        if default_action is not None:
            continue
        icon_size = widget.iconSize()
        if icon_size.width() > 48 or icon_size.height() > 48:
            continue
        if not is_monochrome_icon(widget.icon()) and not bool(
            widget.property("sciplotterMonochromeIcon")
        ):
            continue
        if _refresh_icon_owner(widget, widget.icon, widget.setIcon, palette):
            widget.update()


class _ApplicationThemeRuntime(QObject):
    """Keeps late-created dialogs and local component QSS on the active theme."""

    # Rebuilt once, not per event: this app-level filter sees every event for
    # every object, so a fresh set literal per call was pure overhead.
    _THEME_EVENTS = frozenset({QEvent.Type.Show, QEvent.Type.Polish, QEvent.Type.StyleChange})

    def __init__(self, app: QApplication):
        super().__init__(app)
        self.app = app
        self.palette = build_theme_palette()
        self.font_family = app.font().family() or "Segoe UI"
        self.font_size = app.font().pointSize() if app.font().pointSize() > 0 else 10
        self.suspended = False
        self._guard = set()
        # Bumped on every theme/font change. Widgets already themed at the
        # current generation (with unchanged QSS) short-circuit apply_widget.
        self.generation = 1

    def configure(self, palette: ThemePalette, font_family: str, font_size: int) -> None:
        self.palette = palette
        self.font_family = font_family or self.font_family
        self.font_size = max(8, min(24, int(font_size)))
        self.generation += 1

    def eventFilter(self, watched, event):
        # Cheapest checks first so the vast majority of events fall through fast.
        if (
            not self.suspended
            and event.type() in self._THEME_EVENTS
            and isinstance(watched, QWidget)
        ):
            self.apply_widget(watched)
        return False

    def _is_monospace(self, widget: QWidget, source_qss: str) -> bool:
        if str(widget.property("sciplotterFontRole") or "").lower() == "monospace":
            return True
        family = widget.font().family().lower()
        return any(name in family for name in ("consolas", "monaco", "courier", "monospace")) or (
            "font-family" in source_qss.lower()
            and any(name in source_qss.lower() for name in ("consolas", "monaco", "courier", "monospace"))
        )

    def apply_widget(self, widget: QWidget) -> None:
        if bool(widget.property("sciplotterThemeBypass")):
            return
        identity = id(widget)
        if identity in self._guard:
            return
        # Skip only the expensive QSS work when nothing changed since we last
        # themed this widget at the current generation. Palette + font are still
        # re-asserted below because Qt's QStyleSheetStyle re-derives them from the
        # app stylesheet on every polish and would otherwise clobber our accent
        # (that clobber is exactly why the redundant re-applies were load-bearing).
        current_qss = widget.styleSheet() or ""
        needs_qss_work = not (
            widget.property("_sciplotterThemeGen") == self.generation
            and current_qss == widget.property("_sciplotterThemeRenderedQss")
        )
        self._guard.add(identity)
        try:
            source_qss = widget.property("_sciplotterThemeSourceQss")
            if needs_qss_work:
                previous_render = widget.property("_sciplotterThemeRenderedQss")
                if previous_render is None or current_qss != previous_render:
                    source_qss = current_qss
                    widget.setProperty("_sciplotterThemeSourceQss", source_qss)
                source_qss = str(source_qss or "")

                rendered_qss = render_theme_qss(
                    source_qss,
                    self.palette,
                    self.font_family,
                    self.font_size,
                )
                if current_qss != rendered_qss:
                    widget.setStyleSheet(rendered_qss)
                widget.setProperty("_sciplotterThemeRenderedQss", rendered_qss)

                theme_hook = getattr(widget, "apply_application_theme", None)
                if callable(theme_hook):
                    theme_hook()

                widget.setProperty("_sciplotterThemeGen", self.generation)
            source_qss = str(source_qss or "")

            # Always re-assert: Qt re-derives these from the stylesheet on polish.
            # Explicit palettes were used by a few legacy dialogs to force a light
            # surface; rebasing on the app palette keeps every control on theme.
            widget.setPalette(self.app.palette())
            if not self._is_monospace(widget, source_qss):
                font = QFont(widget.font())
                font.setFamily(self.font_family)
                font.setPointSize(self.font_size)
                widget.setFont(font)
        finally:
            self._guard.discard(identity)

    def refresh(self) -> None:
        for widget in list(self.app.allWidgets()):
            self.apply_widget(widget)


def _theme_runtime(app: QApplication) -> _ApplicationThemeRuntime:
    runtime = getattr(app, "_sciplotter_theme_runtime", None)
    if runtime is None:
        runtime = _ApplicationThemeRuntime(app)
        app._sciplotter_theme_runtime = runtime
        app.installEventFilter(runtime)
    return runtime


def apply_qss(
    app: QApplication,
    qss_path: str = None,
    *,
    theme_mode: str = None,
    accent_color: str = DEFAULT_ACCENT,
    background_color: str = "",
    font_family: str = "",
    font_size: int = 10,
):
    """Apply one coherent theme to the app, existing widgets, and future popups."""
    if app is None:
        return None

    qss_name = os.path.basename(qss_path or "").lower()
    if theme_mode not in {"dark", "light", "custom"}:
        if qss_name == "light.qss":
            theme_mode = "light"
        elif qss_path and qss_name not in {"dark.qss", "dark_modern.qss", "qdark.qss"}:
            theme_mode = "custom"
        else:
            theme_mode = "dark"
    if theme_mode == "custom" and (not qss_path or not os.path.isfile(qss_path)):
        logger.warning("Custom QSS is unavailable; falling back to the built-in dark theme")
        theme_mode = "dark"

    palette = build_theme_palette(theme_mode, accent_color, background_color)
    register_bundled_qt_fonts()
    resolved_family = font_family or app.font().family() or "Segoe UI"
    available_families = {family.casefold(): family for family in QFontDatabase.families()}
    if available_families and resolved_family.casefold() not in available_families:
        app_family = app.font().family()
        resolved_family = available_families.get(app_family.casefold(), next(iter(available_families.values())))
    resolved_size = max(8, min(24, int(font_size or 10)))
    runtime = _theme_runtime(app)
    runtime.suspended = True
    try:
        if theme_mode == "custom":
            with open(qss_path, "r", encoding="utf-8") as handle:
                custom_qss = handle.read()
            app.setStyleSheet(
                render_theme_qss(custom_qss, palette, resolved_family, resolved_size)
                + _font_and_popup_qss(palette, resolved_family, resolved_size)
            )
            logger.info("Custom QSS loaded: %s", qss_path)
        else:
            extra_qss = render_theme_qss(
                _read_override_qss(), palette, resolved_family, resolved_size
            ) + _font_and_popup_qss(palette, resolved_family, resolved_size)
            try:
                _setup_qdarktheme(
                    app,
                    palette.mode,
                    palette.qdarktheme_colors(),
                    extra_qss,
                )
                logger.info(
                    "Theme: qdarktheme %s, accent %s, global component overrides",
                    palette.mode,
                    palette.accent,
                )
            except Exception as error:
                logger.warning("qdarktheme unavailable, using bundled QSS: %s", error)
                fallback_name = "light.qss" if palette.mode == "light" else "dark_modern.qss"
                fallback_path = os.path.join(os.path.dirname(__file__), fallback_name)
                with open(fallback_path, "r", encoding="utf-8") as handle:
                    fallback_qss = handle.read()
                app.setStyleSheet(
                    render_theme_qss(fallback_qss, palette, resolved_family, resolved_size)
                    + extra_qss
                )

        _apply_qpalette(app, palette)
        app.setProperty("sciplotterThemeMode", theme_mode)
        app.setProperty("sciplotterEffectiveThemeMode", palette.mode)
        app.setProperty("sciplotterAccentColor", palette.accent)
        app.setProperty(
            "sciplotterBackgroundColor",
            _valid_hex_color(background_color) if QColor(str(background_color or "")).isValid() else "",
        )
        runtime.configure(palette, resolved_family, resolved_size)
    finally:
        runtime.suspended = False
    runtime.refresh()
    refresh_application_icons(app, palette)
    return palette


def apply_font(
    app: QApplication,
    font_family: str,
    font_size: int,
    *,
    refresh_widgets: bool = True,
):
    """Resolve and apply the requested font without rejecting Qt substitutions."""
    if app is None:
        return ""
    font_size = max(8, min(24, int(font_size or 10)))
    requested = str(font_family or "").strip()
    register_bundled_qt_fonts()
    available = {family.casefold(): family for family in QFontDatabase.families()}
    selected = available.get(requested.casefold())
    if not selected:
        for fallback in (
            "Segoe UI",
            "Tahoma",
            "Arial",
            "TH Sarabun New",
            app.font().family(),
        ):
            if fallback and fallback.casefold() in available:
                selected = available[fallback.casefold()]
                break
    selected = selected or requested or app.font().family() or "Sans Serif"
    font = QFont(selected, font_size)
    app.setFont(font)
    resolved = QFontInfo(font).family() or selected
    logger.info("Application font applied: %s %spt", resolved, font_size)

    runtime = getattr(app, "_sciplotter_theme_runtime", None)
    if runtime is not None and refresh_widgets:
        runtime.configure(runtime.palette, resolved, font_size)
        runtime.refresh()
    return resolved

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
                       font_family: Optional[str] = None,
                       font_size: Optional[int] = None):
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
        if font_size:
            matplotlib.rcParams["font.size"] = int(font_size)

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

def _legacy_apply_theme(app: QApplication):
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
    
    logger.info("Legacy theme application completed")


def apply_theme(app: QApplication):
    """Apply production defaults through the same runtime as user settings."""
    resolved_family = apply_font(app, "Segoe UI", 10)
    palette = apply_qss(
        app,
        theme_mode="dark",
        accent_color=DEFAULT_ACCENT,
        font_family=resolved_family,
        font_size=10,
    )
    try:
        default_mpl_style = os.path.join(os.path.dirname(__file__), "mpl_style_dark_pro.mplstyle")
        apply_mpl_style(default_mpl_style)
        apply_mpl_overrides(
            axes_color="#3A3F44",
            text_color="#E6E6E6",
            font_family=resolved_family,
            font_size=10,
        )
    except Exception:
        logger.exception("Could not apply default Matplotlib appearance")
    return palette

def apply_theme_from_config(app: QApplication, config):
    """Apply persisted Qt appearance settings as one atomic operation."""
    if app is None:
        return None
    font_size = int(getattr(config, "font_size", 10) or 10)
    resolved_family = apply_font(
        app,
        getattr(config, "font_family", "Segoe UI"),
        font_size,
        refresh_widgets=False,
    )
    return apply_qss(
        app,
        getattr(config, "qt_qss_path", "") or None,
        theme_mode=getattr(config, "theme_mode", "dark"),
        accent_color=getattr(config, "accent_color", DEFAULT_ACCENT),
        background_color=getattr(config, "background_color", ""),
        font_family=resolved_family,
        font_size=font_size,
    )

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
            cfg_font_size = int(getattr(mpl_config, 'font_size', 10) or 10)
            matplotlib.rcParams["font.size"] = cfg_font_size
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
        
        # Only auto-select when the user did not request a family. Older code
        # always ran this block and silently overwrote the saved font.
        if not cfg_font:
            try:
                import matplotlib.font_manager as fm
                available_fonts = ["Segoe UI", "Microsoft YaHei", "Tahoma", "Arial"]
                for font_name in available_fonts:
                    try:
                        font_path = fm.findfont(fm.FontProperties(family=font_name))
                        if font_path and "DejaVuSans" not in font_path:
                            matplotlib.rcParams["font.family"] = font_name
                            logger.info(f"Font set to: {font_name}")
                            break
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"Could not set font: {e}")
        
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
    """Apply current font defaults to live figures and redraw without resets."""
    try:
        from matplotlib._pylab_helpers import Gcf
        from matplotlib.text import Text

        figures = {}
        for manager in Gcf.get_all_fig_managers():
            figure = getattr(getattr(manager, "canvas", None), "figure", None)
            if figure is not None:
                figures[id(figure)] = figure

        app = QApplication.instance()
        if app is not None:
            for widget in app.allWidgets():
                figure = getattr(widget, "figure", None)
                if figure is not None and hasattr(figure, "axes"):
                    figures[id(figure)] = figure

        family = matplotlib.rcParams.get("font.family", ["sans-serif"])
        for figure in figures.values():
            for text in figure.findobj(match=Text):
                text.set_fontfamily(family)

            for axes in figure.axes:
                axes.title.set_fontsize(matplotlib.rcParams["axes.titlesize"])
                axes.xaxis.label.set_fontsize(matplotlib.rcParams["axes.labelsize"])
                axes.yaxis.label.set_fontsize(matplotlib.rcParams["axes.labelsize"])
                for label in axes.get_xticklabels():
                    label.set_fontsize(matplotlib.rcParams["xtick.labelsize"])
                for label in axes.get_yticklabels():
                    label.set_fontsize(matplotlib.rcParams["ytick.labelsize"])
                legend = axes.get_legend()
                if legend is not None:
                    for text in legend.get_texts():
                        text.set_fontsize(matplotlib.rcParams["legend.fontsize"])

            if getattr(figure, "_suptitle", None) is not None:
                figure._suptitle.set_fontsize(matplotlib.rcParams["figure.titlesize"])
            canvas = getattr(figure, "canvas", None)
            if canvas is not None:
                canvas.draw_idle()
        logger.info("Matplotlib canvases refreshed without resetting rcParams")
    except Exception as e:
        logger.error(f"Error refreshing matplotlib: {e}")
