from __future__ import annotations

import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from styles.theme import (
    DARK_CUSTOM_COLORS,
    apply_qss,
    apply_mpl_from_config,
    build_theme_palette,
    refresh_application_icons,
    refresh_matplotlib_canvases,
    render_theme_qss,
    themed_icon,
)
from settings import MatplotlibConfig


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dominant_icon_color(icon: QIcon, mode=QIcon.Normal, state=QIcon.Off) -> str:
    image = icon.pixmap(QSize(24, 24), mode, state).toImage()
    counts = {}
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() <= 100:
                continue
            name = color.name().upper()
            counts[name] = counts.get(name, 0) + 1
    return max(counts, key=counts.get)


def _test_icon(*, multicolor: bool = False) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#FF0000" if multicolor else "#FFFFFF"))
    painter.drawRect(3, 3, 9, 18)
    painter.setBrush(QColor("#00AA00" if multicolor else "#FFFFFF"))
    painter.drawRect(12, 3, 9, 18)
    painter.end()
    return QIcon(pixmap)


def test_dark_custom_colors_drive_qdarktheme_stylesheet():
    """qdarktheme must accept our palette dict and bake the SciPlotter accent
    into the generated stylesheet, replacing its default light blue."""
    qdarktheme = pytest.importorskip("qdarktheme")

    qss = qdarktheme.load_stylesheet("dark", custom_colors=DARK_CUSTOM_COLORS).lower()
    assert "4f9cf9" in qss  # SciPlotter accent is in
    assert "8ab4f7" not in qss  # qdarktheme's default primary is gone


def test_dark_custom_colors_stay_in_family():
    """Guard the palette contract: accent + core surfaces must match the
    values the hand-written QSS files are built around."""
    assert DARK_CUSTOM_COLORS["primary"] == "#4F9CF9"
    assert DARK_CUSTOM_COLORS["background"] == "#1e2126"
    assert DARK_CUSTOM_COLORS["border"] == "#3a3f44"
    assert DARK_CUSTOM_COLORS["foreground"] == "#e6e6e6"


def test_palette_builder_supports_real_light_mode_and_custom_accent():
    palette = build_theme_palette("light", "#20b8a6")

    assert palette.mode == "light"
    assert palette.accent == "#20B8A6"
    assert palette.background == "#F4F6F8"
    assert palette.surface == "#FFFFFF"
    assert palette.text == "#1D2733"


def test_custom_background_derives_surfaces_and_contrast_independent_of_mode():
    warm = build_theme_palette("dark", "#B14DFF", "#F7E7CE")
    midnight = build_theme_palette("light", "#20B8A6", "#08111F")
    medium = build_theme_palette("light", "#20B8A6", "#777777")

    assert warm.mode == "light"
    assert warm.background == "#F7E7CE"
    assert warm.text == "#17202B"
    assert warm.surface != warm.background
    assert warm.border != warm.background
    assert midnight.mode == "dark"
    assert midnight.background == "#08111F"
    assert midnight.text == "#F2F5F8"
    assert midnight.surface != midnight.background
    assert medium.mode == "dark"
    assert medium.text == "#F2F5F8"


def test_icon_palette_has_contrast_and_explicit_checked_state(qapp):
    icon = themed_icon(
        _test_icon(),
        build_theme_palette("light", "#20B8A6"),
    )

    assert _dominant_icon_color(icon) == "#344252"
    assert _dominant_icon_color(icon, QIcon.Disabled) == "#98A2B0"
    assert _dominant_icon_color(icon, QIcon.Normal, QIcon.On) == "#20B8A6"


def test_icon_refresh_leaves_multicolor_assets_untouched(qapp):
    host = QWidget()
    monochrome = QAction(themed_icon(_test_icon(), build_theme_palette("dark")), "Mono", host)
    colored = QAction(_test_icon(multicolor=True), "Color", host)
    host.addActions([monochrome, colored])
    colored_before = colored.icon().pixmap(24, 24).toImage()

    refresh_application_icons(qapp, build_theme_palette("light", "#D768D7"))

    assert _dominant_icon_color(monochrome.icon()) == "#344252"
    assert _dominant_icon_color(monochrome.icon(), QIcon.Normal, QIcon.On) == "#D768D7"
    colored_after = colored.icon().pixmap(24, 24).toImage()
    assert colored_after.pixelColor(5, 10) == colored_before.pixelColor(5, 10)
    assert colored_after.pixelColor(18, 10) == colored_before.pixelColor(18, 10)


def test_qtawesome_factory_reads_current_theme(qapp):
    pytest.importorskip("qtawesome")
    from main import _qtawesome_icon

    try:
        apply_qss(
            qapp,
            theme_mode="light",
            accent_color="#20B8A6",
            font_family="TH Sarabun New",
            font_size=10,
        )
        icon = _qtawesome_icon("mdi.folder-open-outline")
        assert icon is not None
        assert _dominant_icon_color(icon) == "#344252"
        assert _dominant_icon_color(icon, QIcon.Disabled) == "#98A2B0"
        assert _dominant_icon_color(icon, QIcon.Normal, QIcon.On) == "#20B8A6"
    finally:
        apply_qss(
            qapp,
            theme_mode="dark",
            font_family="TH Sarabun New",
            font_size=10,
        )


def test_component_qss_tracks_theme_accent_and_font():
    source = """
    QWidget {
        background: #1e2126;
        color: #e6e6e6;
        border: 1px solid #4F9CF9;
        font-family: 'Segoe UI';
        font-size: 10pt;
    }
    """

    rendered = render_theme_qss(
        source,
        build_theme_palette("light", "#20B8A6"),
        "Arial",
        13,
    )

    assert "#F4F6F8" in rendered
    assert "#1D2733" in rendered
    assert "#20B8A6" in rendered
    assert 'font-family: "Arial"' in rendered
    assert "font-size: 13pt" in rendered


def test_light_theme_repairs_legacy_dark_dialog_contrast_and_primary_color():
    source = """
    QDialog { background: #2b2b2b; color: #ffffff; }
    QPushButton { background: #2f80ed; color: #ffffff; }
    """

    rendered = render_theme_qss(
        source,
        build_theme_palette("light", "#F06B5D"),
        "TH Sarabun New",
        10,
    )

    assert "background: #FFFFFF" in rendered
    assert "color: #17202B" in rendered
    assert "background: #F06B5D" in rendered


def test_matplotlib_configured_font_is_not_overwritten_by_auto_fallback():
    import matplotlib

    config = MatplotlibConfig(
        mpl_style_path="",
        font_family="DejaVu Sans",
        font_size=17,
    )

    apply_mpl_from_config(config)

    assert matplotlib.rcParams["font.family"][0] == "DejaVu Sans"
    assert matplotlib.rcParams["font.size"] == 17


def test_canvas_refresh_preserves_rcparams_and_updates_live_text(monkeypatch):
    import matplotlib
    from cycler import cycler
    from matplotlib._pylab_helpers import Gcf
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import to_hex
    from matplotlib.figure import Figure

    with matplotlib.rc_context():
        matplotlib.rcParams["font.family"] = ["DejaVu Sans"]
        matplotlib.rcParams["font.size"] = 17
        matplotlib.rcParams["axes.titlesize"] = 19
        matplotlib.rcParams["axes.labelsize"] = 14
        matplotlib.rcParams["figure.facecolor"] = "#102030"
        matplotlib.rcParams["axes.facecolor"] = "#203040"
        matplotlib.rcParams["axes.edgecolor"] = "#708090"
        matplotlib.rcParams["text.color"] = "#F0F2F5"
        matplotlib.rcParams["axes.titlecolor"] = "#F0F2F5"
        matplotlib.rcParams["axes.labelcolor"] = "#F0F2F5"
        matplotlib.rcParams["xtick.color"] = "#F0F2F5"
        matplotlib.rcParams["ytick.color"] = "#F0F2F5"
        matplotlib.rcParams["grid.color"] = "#506070"
        matplotlib.rcParams["grid.alpha"] = 0.4
        matplotlib.rcParams["grid.linewidth"] = 1.1
        matplotlib.rcParams["lines.linewidth"] = 3.0
        matplotlib.rcParams["lines.markersize"] = 8.0
        matplotlib.rcParams["axes.prop_cycle"] = cycler(color=["#E45756"])
        figure = Figure()
        canvas = FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.set_title("Title", fontfamily="serif", fontsize=8)
        axes.set_xlabel("X")
        line, = axes.plot([0, 1], [1, 2], label="signal")

        manager = type("Manager", (), {"canvas": canvas})()
        monkeypatch.setattr(Gcf, "get_all_fig_managers", lambda: [manager])

        refresh_matplotlib_canvases()

        assert matplotlib.rcParams["font.family"][0] == "DejaVu Sans"
        assert matplotlib.rcParams["font.size"] == 17
        assert axes.title.get_fontfamily()[0] == "DejaVu Sans"
        assert axes.title.get_fontsize() == 19
        assert axes.xaxis.label.get_fontsize() == 14
        assert to_hex(figure.get_facecolor()).upper() == "#102030"
        assert to_hex(axes.get_facecolor()).upper() == "#203040"
        assert to_hex(axes.spines["left"].get_edgecolor()).upper() == "#708090"
        assert line.get_linewidth() == 3.0
        assert line.get_markersize() == 8.0
        assert to_hex(line.get_color()).upper() == "#E45756"


def test_follow_app_theme_drives_matplotlib_light_canvas(qapp):
    import matplotlib

    with matplotlib.rc_context():
        apply_qss(
            qapp,
            theme_mode="light",
            accent_color="#20B8A6",
            font_family=qapp.font().family(),
            font_size=10,
        )
        config = MatplotlibConfig(mode="theme", mpl_style_path="")

        assert apply_mpl_from_config(config, app=qapp) is True
        assert matplotlib.rcParams["figure.facecolor"].upper() == qapp.palette().color(
            QPalette.Window
        ).name().upper()
        assert matplotlib.rcParams["axes.facecolor"].upper() == qapp.palette().color(
            QPalette.Base
        ).name().upper()
        assert matplotlib.rcParams["text.color"].upper() == qapp.palette().color(
            QPalette.Text
        ).name().upper()

    apply_qss(
        qapp,
        theme_mode="dark",
        accent_color="#4F9CF9",
        font_family=qapp.font().family(),
        font_size=10,
    )
