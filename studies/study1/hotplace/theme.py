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
    hover: str
    series: tuple[str, str]


LIGHT = Theme(
    background="#f3f6fb", surface="#ffffff", muted="#f7f9fc",
    ink="#19273e", ink_soft="#64748b", border="#dfe6f0",
    grid="#edf1f7", axis="#dfe6f0", accent="#2563eb",
    accent_soft="#eaf1ff", hover="#eef3fb", series=("#2a78d6", "#eb6834"),
)
DARK = Theme(
    background="#101722", surface="#182231", muted="#1d2a3b",
    ink="#ecf2fa", ink_soft="#a5b4c9", border="#2d3b50",
    grid="#263448", axis="#35455d", accent="#7aabff",
    accent_soft="#243b60", hover="#243247", series=("#68aaff", "#ff9b67"),
)

_theme = LIGHT


def set_theme(dark: bool) -> None:
    global _theme
    _theme = DARK if dark else LIGHT


def theme() -> Theme:
    return _theme


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
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
}


def make_icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """외부 아이콘 패키지 없이 배율에 맞는 선형 SVG를 그린다."""
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


def apply_theme(app, dark: bool) -> None:
    """OS에 관계없이 일관된 컨트롤과 읽기 쉬운 밝은/어두운 팔레트."""
    set_theme(dark)
    t = theme()
    app.setStyle("Fusion")
    families = set(QFontDatabase().families())
    family = next((name for name in (
        "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans CJK KR", "NanumGothic",
    ) if name in families), app.font().family())
    font = QFont(family)
    font.setPixelSize(13)
    app.setFont(font)

    palette = QPalette()
    for role, color in (
        (QPalette.Window, t.background), (QPalette.WindowText, t.ink),
        (QPalette.Base, t.surface), (QPalette.AlternateBase, t.muted),
        (QPalette.Text, t.ink), (QPalette.Button, t.surface),
        (QPalette.ButtonText, t.ink), (QPalette.Highlight, t.accent),
        (QPalette.HighlightedText, t.background if dark else "#ffffff"),
        (QPalette.ToolTipBase, t.ink), (QPalette.ToolTipText, t.surface),
        (QPalette.PlaceholderText, t.ink_soft),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        palette.setColor(QPalette.Disabled, role, QColor(t.ink_soft))
    app.setPalette(palette)
    arrow = (Path(__file__).parent / "assets" / "chevron-down.svg").as_posix()
    app.setStyleSheet(f"""
        QWidget {{ color: {t.ink}; font-size: 13px; }}
        QWidget#mainWindow, QDialog {{ background: {t.background}; }}
        QLabel {{ background: transparent; border: none; }}
        QLabel[role="muted"] {{ color: {t.ink_soft}; font-size: 12px; }}
        QLabel[role="eyebrow"] {{ color: {t.accent}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
        QLabel[role="title"] {{ font-size: 27px; font-weight: 700; }}
        QLabel[role="heading"] {{ font-size: 17px; font-weight: 700; }}
        QLabel[role="section"] {{ font-size: 14px; font-weight: 700; }}
        QLabel[role="field"] {{ font-size: 12px; font-weight: 600; }}
        QLabel[role="badge"] {{ color: {t.accent}; background: {t.accent_soft}; border-radius: 6px; padding: 5px 9px; font-size: 11px; font-weight: 600; }}
        QLabel#brandMark {{ background: #2563eb; border-radius: 12px; }}
        QFrame#sidebar, QFrame#chartPanel, QFrame[role="metric"], QFrame[role="insight"] {{
            background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px;
        }}
        QFrame[role="metric"][featured="true"] {{ background: {t.accent_soft}; border-color: {t.accent_soft}; }}
        QLabel[role="metricValue"] {{ font-size: 28px; font-weight: 700; letter-spacing: -1px; }}
        QFrame[featured="true"] QLabel[role="metricValue"] {{ color: {t.accent}; }}
        QLabel[role="metricUnit"] {{ color: {t.ink_soft}; font-size: 12px; padding-bottom: 4px; }}
        QLabel[role="regionTag"] {{ color: {t.accent}; font-size: 11px; font-weight: 700; }}
        QLabel[role="regionTagB"] {{ color: {t.series[1]}; font-size: 11px; font-weight: 700; }}
        QFrame[role="separator"] {{ background: {t.border}; border: none; max-height: 1px; }}
        QPushButton {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 7px; padding: 8px 12px; font-weight: 600; }}
        QPushButton:hover {{ background: {t.hover}; border-color: {t.ink_soft}; }}
        QPushButton:pressed {{ background: {t.accent_soft}; }}
        QPushButton:focus {{ border-color: {t.accent}; }}
        QPushButton:disabled {{ background: {t.muted}; color: {t.ink_soft}; border-color: {t.border}; }}
        QPushButton[role="primary"] {{ background: #2563eb; color: white; border: 1px solid #2563eb; padding: 10px 12px; }}
        QPushButton[role="primary"]:hover {{ background: #1d4ed8; border-color: #1d4ed8; }}
        QPushButton[role="primary"]:pressed {{ background: #1e40af; }}
        QPushButton[role="primary"]:disabled {{ background: {t.muted}; color: {t.ink_soft}; border-color: {t.border}; }}
        QPushButton[role="quiet"] {{ background: transparent; border: 1px solid transparent; color: {t.ink_soft}; padding: 6px 8px; }}
        QPushButton[role="quiet"]:hover {{ background: {t.hover}; color: {t.ink}; }}
        QPushButton[role="quiet"]:focus {{ border-color: {t.accent}; }}
        QLineEdit, QComboBox {{ background: {t.muted}; border: 1px solid {t.border}; border-radius: 7px; padding: 9px 10px; selection-background-color: {t.accent}; }}
        QLineEdit:focus, QComboBox:focus {{ border: 1px solid {t.accent}; background: {t.surface}; }}
        QLineEdit:disabled, QComboBox:disabled {{ color: {t.ink_soft}; background: {t.muted}; }}
        QComboBox {{ padding-right: 26px; }}
        QComboBox::drop-down {{ border: none; width: 27px; }}
        QComboBox::down-arrow {{ image: url("{arrow}"); width: 12px; height: 12px; }}
        QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border}; padding: 4px; selection-background-color: {t.accent_soft}; selection-color: {t.ink}; outline: none; }}
        QTabWidget::pane {{ border: none; background: {t.surface}; }}
        QTabBar::tab {{ background: transparent; color: {t.ink_soft}; border: none; border-bottom: 2px solid transparent; padding: 12px 14px; font-weight: 600; }}
        QTabBar::tab:selected {{ color: {t.accent}; border-bottom-color: {t.accent}; }}
        QTabBar::tab:hover {{ background: {t.muted}; }}
        QToolBar {{ background: {t.surface}; border: none; spacing: 2px; padding: 0; }}
        QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 5px; padding: 5px; }}
        QToolButton:hover, QToolButton:checked {{ background: {t.accent_soft}; border-color: {t.border}; }}
        QToolButton:focus {{ border-color: {t.accent}; }}
        QProgressBar {{ background: {t.muted}; border: none; border-radius: 3px; max-height: 6px; }}
        QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
        QScrollArea {{ background: transparent; border: none; }}
        QWidget#scrollContents {{ background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 7px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 3px; min-height: 28px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QListWidget, QPlainTextEdit {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; padding: 10px; selection-background-color: {t.accent_soft}; selection-color: {t.ink}; }}
        QListWidget::item {{ padding: 10px 4px; border-radius: 5px; }}
        QListWidget::item:selected {{ background: {t.accent_soft}; color: {t.accent}; }}
        QToolTip {{ background: {t.ink}; color: {t.surface}; border: none; padding: 6px 9px; }}
    """)
