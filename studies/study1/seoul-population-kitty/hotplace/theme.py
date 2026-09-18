"""화면과 차트가 공유하는 색상, Qt 스타일, 벡터 아이콘."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PyQt5.QtSvg import QSvgRenderer


@dataclass(frozen=True)
class Theme:
    background: str
    surface: str
    muted: str
    ink: str
    ink_soft: str
    border: str
    grid: str
    axis: str
    accent: str
    accent_soft: str
    accent_hover: str
    accent_pressed: str
    on_accent: str
    hover: str
    series: tuple[str, str]
    series_soft: tuple[str, str]
    heat: tuple[str, str, str]


# Loading.io HelloKitty 팔레트. 원본의 위젯 스타일은 유지하고 색상만 적용한다.
# https://loading.io/color/feature/HelloKitty/
KITTY_RED = "#f90013"
KITTY_YELLOW = "#ffe700"
KITTY_WHITE = "#ffffff"
KITTY_BLUE = "#0054ae"
KITTY_BROWN = "#251815"

LIGHT = Theme(
    background="#fff9f9", surface=KITTY_WHITE, muted="#fffbe6",
    ink=KITTY_BROWN, ink_soft="#75615a", border="#e9dcda",
    grid="#f0e5e3", axis="#cbbcb5", accent=KITTY_RED,
    accent_soft="#ffebec", accent_hover="#dc0011", accent_pressed="#bd000e",
    on_accent=KITTY_WHITE, hover="#fff0f1", series=(KITTY_RED, KITTY_BLUE),
    series_soft=("#ffebec", "#e5eef7"), heat=(KITTY_WHITE, "#80a9d7", KITTY_BLUE),
)
DARK = Theme(
    background=KITTY_BROWN, surface="#30221e", muted="#3a2e23",
    ink=KITTY_WHITE, ink_soft="#cdbab1", border="#594139",
    grid="#46332b", axis="#805f54", accent=KITTY_YELLOW,
    accent_soft="#463b1f", accent_hover="#fff06b", accent_pressed="#e0cb00",
    on_accent=KITTY_BROWN, hover="#403125", series=("#ff626d", "#78afe9"),
    series_soft=("#542a29", "#233d5b"), heat=("#263242", KITTY_BLUE, "#c4e0ff"),
)

_theme = LIGHT


def set_theme(dark: bool) -> None:
    global _theme
    _theme = DARK if dark else LIGHT


def theme() -> Theme:
    return _theme


_KITTY_ASSET = Path(__file__).resolve().parent / "assets" / "hello-kitty.svg"


_ICONS = {
    "pulse": '<path d="M3 16V10M9 19V5M15 16V8M21 19V3"/>',
    "folder": '<path d="M3 7V5h6l2 2h10v13H3Z"/><path d="M3 10h18"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "arrow": '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    "export": '<path d="M14 3H5v18h14V10M14 3l5 7h-5ZM8 14h8M8 17h8"/>',
    "moon": '<path d="M20 15.5A9 9 0 0 1 8.5 4 9 9 0 1 0 20 15.5Z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    "rank": '<path d="M4 21V11h5v10m0 0V4h6v17m0 0V8h5v13M2 21h20"/>',
    "compare": '<path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2"/>',
    "spark": '<path d="m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3Z"/>',
    "home": '<path d="m3 10 9-7 9 7M5 9v12h5v-7h4v7h5V9"/>',
    "back": '<path d="M19 12H5m6-6-6 6 6 6"/>',
    "pan": '<path d="M12 3v18M3 12h18m-12-6 3-3 3 3m-6 12 3 3 3-3M6 9l-3 3 3 3m12-6 3 3-3 3"/>',
    "zoom": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6m-3-3v6"/>',
    "settings": '<path d="M3 6h4m4 0h10M3 12h10m4 0h4M3 18h4m4 0h10"/><circle cx="9" cy="6" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="9" cy="18" r="2"/>',
    "chart": '<path d="M4 3v17h17M7 14l4-5 4 3 6-7"/>',
}


def make_icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """외부 아이콘 패키지 없이 배율에 맞는 선형 SVG를 그린다."""
    if name == "kitty":
        return QIcon(str(_KITTY_ASSET))
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color or theme().ink_soft}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>'
    )
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def kitty_pixmap(width: int, height: int) -> QPixmap:
    """키티 SVG를 원래 비율로 width × height 안에 맞춰 그린다.

    Qt 5 의 QIcon.pixmap() 은 고해상도 화면 배율을 반영하지 않아 그림이 흐려진다.
    기능 아이콘과 같은 방식으로 2배 크기로 그린 뒤 배율을 2로 표시한다.
    """
    renderer = QSvgRenderer(str(_KITTY_ASSET))
    size = renderer.defaultSize().scaled(width, height, Qt.KeepAspectRatio)
    pixmap = QPixmap(size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


def apply_theme(app, dark: bool) -> None:
    """Fluent 컴포넌트와 분석 화면을 하나의 팔레트로 갱신한다."""
    from qfluentwidgets import Theme as FluentTheme, setTheme, setThemeColor

    set_theme(dark)
    t = theme()
    setTheme(FluentTheme.DARK if dark else FluentTheme.LIGHT)
    setThemeColor(t.accent)
    app.setStyle("Fusion")
    families = set(QFontDatabase().families())
    family = next((name for name in (
        "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans CJK KR", "NanumGothic",
    ) if name in families), app.font().family())
    font = QFont(family)
    font.setPixelSize(14)
    app.setFont(font)
    palette = QPalette()
    for role, color in (
        (QPalette.Window, t.background), (QPalette.WindowText, t.ink),
        (QPalette.Base, t.surface), (QPalette.AlternateBase, t.muted),
        (QPalette.Text, t.ink), (QPalette.Button, t.surface),
        (QPalette.ButtonText, t.ink), (QPalette.Highlight, t.accent),
        (QPalette.HighlightedText, t.on_accent),
        (QPalette.ToolTipBase, t.surface), (QPalette.ToolTipText, t.ink),
        (QPalette.PlaceholderText, t.ink_soft),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        palette.setColor(QPalette.Disabled, role, QColor(t.ink_soft))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QWidget {{ color: {t.ink}; }}
        QWidget#mainWindow, QWidget#workspacePage, QDialog {{ background: {t.background}; }}
        QWidget#pageContents {{ background: transparent; }}
        QFrame#appHeader {{ background: {t.background}; border-bottom: 1px solid {t.border}; }}
        QFrame#pageHeader {{ background: {t.background}; }}
        QFrame#invitation, QFrame#searchStation, QFrame#reportSummary,
        QFrame#fileBoard, QFrame[role="stepCard"], QFrame[role="noteCard"] {{
            background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px;
        }}
        QFrame#kittyStamp {{ background: transparent; border: none; }}
        QFrame[role="chartControls"] {{ background: {t.muted}; border: none; border-radius: 8px; }}
        QFrame[role="noteA"], QFrame[role="noteB"] {{ background: {t.surface}; border: none; }}
        QLabel[role="chartTitle"] {{ font-size: 15px; font-weight: 600; }}
        QLabel[role="welcomeCopy"] {{ color: {t.ink_soft}; font-size: 14px; }}
        QLabel[role="noteNumber"] {{ color: {t.ink_soft}; font-size: 13px; font-weight: 600; }}
        QFrame#navigationRail {{ background: {t.background}; border-right: 1px solid {t.border}; }}
        QFrame#topBar {{ background: {t.background}; border-bottom: 1px solid {t.border}; }}
        QFrame#chartPanel, QFrame[role="fileCard"], QFrame#rankingPanel,
        QFrame#insightStrip, QFrame[role="panel"] {{
            background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px;
        }}
        QFrame[role="regionSelector"], QFrame#metricsTable {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px; }}
        QFrame[role="separator"] {{ background: {t.border}; border: none; }}
        QFrame[role="tableHead"] {{ background: {t.muted}; border: none; border-top-left-radius: 11px; border-top-right-radius: 11px; }}
        QLabel {{ color: {t.ink}; background: transparent; border: none; }}
        QLabel[role="brand"] {{ font-size: 17px; font-weight: 700; }}
        QLabel[role="pageTitle"] {{ font-size: 19px; font-weight: 700; }}
        QLabel[role="emptyTitle"] {{ font-size: 24px; font-weight: 700; }}
        QLabel[role="heading"] {{ font-size: 20px; font-weight: 700; }}
        QLabel[role="section"] {{ font-size: 15px; font-weight: 600; }}
        QLabel[role="field"] {{ font-size: 13px; font-weight: 600; }}
        QLabel[role="muted"] {{ color: {t.ink_soft}; font-size: 13px; }}
        QLabel[role="caption"] {{ color: {t.ink_soft}; font-size: 12px; }}
        QLabel[role="columnHead"] {{ color: {t.ink_soft}; font-size: 12px; font-weight: 600; }}
        QLabel[role="metricValue"] {{ font-size: 14px; font-weight: 600; }}
        QLabel[role="statValue"] {{ font-size: 20px; font-weight: 600; }}
        QLabel[role="cellValue"] {{ font-size: 15px; font-weight: 600; }}
        QLabel[role="regionTag"] {{ color: {t.series[0]}; font-size: 12px; font-weight: 700; }}
        QLabel[role="regionTagB"] {{ color: {t.series[1]}; font-size: 12px; font-weight: 700; }}
        QLabel[role="regionBadge"], QLabel[role="regionBadgeB"] {{ color: {t.series[0]}; background: {t.series_soft[0]}; border-radius: 6px; font-size: 12px; font-weight: 700; }}
        QLabel[role="regionBadgeB"] {{ color: {t.series[1]}; background: {t.series_soft[1]}; }}
        QLabel[role="badge"] {{ color: {t.ink_soft}; background: {t.muted}; border-radius: 6px; padding: 4px 9px; font-size: 12px; }}
        QLabel[role="notice"] {{ color: {t.ink}; background: {t.muted}; border-radius: 8px; padding: 8px 12px; font-size: 13px; }}
        QLabel#chartReadout {{ color: {t.ink_soft}; font-size: 12px; }}
        QToolBar {{ background: {t.surface}; border: none; spacing: 2px; padding: 0; }}
        QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 5px; padding: 5px; }}
        QToolButton:hover, QToolButton:checked {{ background: {t.accent_soft}; border-color: {t.border}; }}
        QToolButton:focus {{ border-color: {t.accent}; }}
        QScrollArea {{ background: transparent; border: none; }}
        QListWidget, QPlainTextEdit {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; padding: 8px; selection-background-color: {t.accent_soft}; selection-color: {t.ink}; }}
        QListWidget::item {{ padding: 14px 10px; border-radius: 6px; }}
        QListWidget::item:selected {{ background: {t.accent_soft}; color: {t.ink}; }}
        QToolTip {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.border}; padding: 6px 9px; }}
    """)
