"""matplotlib 렌더링 - 한글 폰트 설정, Qt 캔버스, 그래프 그리기.

분석 결과(:mod:`hotplace.hotplace` 의 LineSeries / AgePyramid 등)를 받아
그림으로만 옮긴다. 계산은 하지 않는다.

차트는 앱의 다른 화면과 같은 시각 언어를 쓴다. 1pt = 1px(72 dpi)로 그려
Qt 스타일시트와 같은 글자 크기를 쓰고, 실선 헤어라인 눈금, 값 쪽 끝이 둥근 막대,
아래로 옅어지는 영역, 오른쪽 값 축, 차트 아래 범례를 기본으로 한다.
마우스 판독은 커서 옆에 뜨는 Qt 말풍선으로 보여준다.
"""

from __future__ import annotations

from html import escape
import math

import matplotlib
import matplotlib.patheffects as path_effects
import numpy as np
from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout
from matplotlib.backend_bases import MouseButton
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.colors import LinearSegmentedColormap, to_hex, to_rgb
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.path import Path
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullLocator
from matplotlib.transforms import Bbox, IdentityTransform, ScaledTranslation

from .hotplace import (
    OFFICE_DAY_NIGHT, RESIDENTIAL_DAY_NIGHT, WEEKDAY_BUSY, WEEKEND_BUSY,
    AgePyramid, AgeShares, CityScatter, Heatmap, HourlyGap, LineSeries, PairedAnalysis,
)

from .theme import DARK, LIGHT, Theme, set_theme, theme

# 72 dpi 에서는 1pt 가 논리 픽셀 1개다. 글자·선 굵기를 Qt 화면과 같은 px 값으로 쓴다.
DPI = 72
EXPORT_DPI = DPI * 2     # PNG 는 화면 크기의 2배 해상도로 저장한다.
FIGSIZE = (820 / DPI, 500 / DPI)

TICK = 11        # 눈금 글자
LABEL = 12       # 범례 · 직접 라벨 · 축 설명
TITLE = 14       # 지역 제목
HEADING = 17     # 단독 그림(--check)의 제목
LINE = 2.4       # 꺾은선 굵기
DASH = (0, (2.5, 3))
BAR = 0.64       # 막대 폭 (한 칸 = 1)
RADIUS = 4       # 막대 끝 둥글기(px)

HOUR_STEPS = [1, 2, 3, 6, 10]
VALUE_STEPS = [1, 2, 2.5, 5, 10]
MAX_ZOOM = 12


def _halo():
    """직접 라벨이 선·막대 위에 겹쳐도 읽히도록 배경색 테두리를 두른다."""
    return [path_effects.withStroke(linewidth=3, foreground=theme().surface)]


_KOREAN_FONTS = (
    "Apple SD Gothic Neo",   # macOS
    "AppleGothic",           # macOS (구형)
    "Malgun Gothic",         # Windows
    "NanumGothic",           # Linux
    "Noto Sans CJK KR",
    "Noto Sans KR",
)

_configured = False


def configure_matplotlib() -> str:
    """설치된 한글 폰트를 찾아 matplotlib 전역 설정에 반영한다."""
    global _configured
    if _configured:
        return matplotlib.rcParams["font.family"][0]

    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((name for name in _KOREAN_FONTS if name in available), None)

    if chosen:
        matplotlib.rcParams["font.family"] = [chosen, "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False   # 한글 폰트의 마이너스 깨짐 방지
    _configured = True
    return chosen or "DejaVu Sans"


def _thousands(value, _pos=None) -> str:
    return f"{value:,.0f}"


def _short(value: float, signed: bool = False) -> str:
    """축 눈금용 짧은 수. 1만 이상은 ‘16만’처럼 적는다. 정확한 값은 말풍선에서 읽는다."""
    if not round(value):
        return "0"
    sign = "-" if value < 0 else "+" if signed else ""
    value = abs(value)
    return sign + (f"{value / 10_000:.4g}만" if value >= 10_000 else f"{value:,.0f}")


def _number(value: float, unit: str = "명", signed: bool = False) -> str:
    """판독·라벨에 쓰는 값 표기. 관측이 없으면 그렇게 적는다."""
    if not math.isfinite(value):
        return "관측 없음"
    sign = "+" if signed else ""
    if unit == "%":
        return f"{value:{sign}.1f}%"
    return f"{value:{sign},.0f}{unit}"


def _tick(series, index: int) -> str:
    """x축 한 칸의 이름: 날짜, 요일 또는 시간."""
    if series.xlabels is not None:
        day = series.xlabels[index]
        return f"{day[4:6]}/{day[6:]}"
    if series.categories is not None:
        return f"{series.categories[index]}요일"
    return f"{index}시"


def _band(band: str) -> str:
    """연령대 눈금: ‘25-29세’, ‘70세+’."""
    return f"{band[:-1]}세+" if band.endswith("+") else f"{band}세"


def _interactive(canvas, method: str, *args, **kwargs) -> None:
    # --check 에서 쓰는 Figure 껍데기에는 마우스 판독·확대가 없다.
    if hasattr(canvas, method):
        getattr(canvas, method)(*args, **kwargs)


# ── 화면 픽셀 기준 도형 ────────────────────────────────────────────────
def _rounded_bar_path(across0, across1, base, end, radius, horizontal) -> Path:
    lo, hi = sorted((across0, across1))
    direction = 1 if end >= base else -1
    r = max(0.0, min(radius, (hi - lo) / 2, abs(end - base)))
    turn = end - direction * r
    points = [(lo, base), (lo, turn), (lo, end), (lo + r, end), (hi - r, end),
              (hi, end), (hi, turn), (hi, base), (lo, base)]
    codes = [Path.MOVETO, Path.LINETO, Path.CURVE3, Path.CURVE3, Path.LINETO,
             Path.CURVE3, Path.CURVE3, Path.LINETO, Path.CLOSEPOLY]
    if horizontal:
        points = [(along, across) for across, along in points]
    return Path(points, codes)


class RoundedBar(Rectangle):
    """값 쪽 끝의 두 모서리만 둥근 막대.

    반경을 화면 픽셀로 계산하므로 확대하거나 창 크기가 바뀌어도 모양이 같다.
    ``xy`` 쪽 변이 기준선(0), 반대쪽 변이 값이다.
    """

    def __init__(self, xy, width, height, *, horizontal: bool = False, radius: float = RADIUS, **kwargs):
        super().__init__(xy, width, height, **kwargs)
        self._horizontal = horizontal
        self._radius = radius

    def get_transform(self):
        return IdentityTransform()

    def get_path(self):
        (x0, y0), (x1, y1) = super().get_transform().transform([(0, 0), (1, 1)])
        radius = self._radius * (self.figure.dpi / DPI if self.figure else 1)
        if self._horizontal:
            return _rounded_bar_path(y0, y1, x0, x1, radius, True)
        return _rounded_bar_path(x0, x1, y0, y1, radius, False)


# ── Qt 캔버스 ─────────────────────────────────────────────────────────
class HoverCallout(QFrame):
    """커서 옆에 뜨는 판독 말풍선. 마우스 이벤트는 아래 캔버스로 그대로 보낸다."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setObjectName("chartCallout")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.body = QLabel(self)
        self.body.setObjectName("chartCalloutText")
        self.body.setTextFormat(Qt.RichText)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 8, 13, 9)
        layout.addWidget(self.body)
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(22)
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)
        self.hide()

    def set_content(self, title: str, rows) -> None:
        t = theme()
        lines = [f'<div style="color:{t.ink_soft}; font-size:12px; margin-bottom:3px;">{escape(title)}</div>']
        for color, text in rows:
            dot = f'<span style="color:{color};">●</span>&nbsp;' if color else ""
            lines.append(f'<div style="color:{t.ink}; font-size:13px;">{dot}{escape(text)}</div>')
        self.body.setText("".join(lines))
        self.shadow.setColor(QColor(0, 0, 0, 110 if theme() is DARK else 38))
        self.adjustSize()

    def point_at(self, x: float, y: float) -> None:
        """(x, y) 논리 픽셀 오른쪽 위에 두고, 넘치면 반대쪽으로 뒤집는다."""
        parent = self.parentWidget()
        width, height = self.width(), self.height()
        left = x + 16 if x + 16 + width <= parent.width() - 4 else x - 16 - width
        top = y - height - 12 if y - height - 12 >= 4 else y + 18
        self.move(int(max(4, min(left, parent.width() - width - 4))),
                  int(max(4, min(top, parent.height() - height - 4))))
        if not self.isVisible():
            self.show()
            self.raise_()


def _scaled_limits(ax, name: str) -> tuple[float, float]:
    """축 범위를 눈금 공간(로그 축이면 log10)으로 돌려준다."""
    axis = ax.xaxis if name == "x" else ax.yaxis
    limits = ax.get_xlim() if name == "x" else ax.get_ylim()
    lo, hi = axis.get_transform().transform(np.array(limits, dtype=float))
    return float(lo), float(hi)


def _set_scaled_limits(ax, name: str, lo: float, hi: float) -> None:
    axis = ax.xaxis if name == "x" else ax.yaxis
    lo, hi = axis.get_transform().inverted().transform(np.array([lo, hi], dtype=float))
    (ax.set_xlim if name == "x" else ax.set_ylim)(lo, hi)


class PlotCanvas(FigureCanvasQTAgg):
    """Qt 위젯으로 쓰는 matplotlib 캔버스.

    마우스를 올리면 말풍선으로 값을 읽고, 확대·이동은 운영체제 방식을 따른다:
    핀치 또는 ⌘(Ctrl) + 스크롤로 확대, 드래그로 이동, 두 번 클릭하면 원래 범위.
    그냥 스크롤하면 차트가 아니라 페이지가 움직인다.
    """

    zoomChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        configure_matplotlib()
        self.figure = Figure(figsize=FIGSIZE, dpi=DPI, facecolor=theme().surface)
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(250)
        self.callout = HoverCallout(self)
        self._zoomed = False
        self._reset_hover()
        self._reset_navigation()
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("figure_leave_event", lambda _event: self.clear_hover())
        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("button_release_event", self._on_release)

    def sizeHint(self) -> QSize:
        # FigureCanvas의 기본 힌트는 현재 크기를 반환한다. 스크롤 영역에서는
        # 창을 줄여도 예전 높이를 요구하므로 안정된 선호 크기를 제공한다.
        return QSize(800, 320)

    def _reset_hover(self) -> None:
        self._hover_data = []
        self._hover_lines = []
        self._hover_marks = []
        self._hover_axes = []
        self._hover_lookup = None
        self._hover_key = None

    def _reset_navigation(self) -> None:
        self._navigation = []
        self._home = {}
        self._drag = None
        self._set_zoomed(False)

    @property
    def navigable(self) -> bool:
        return bool(self._navigation)

    def clear(self) -> None:
        self.callout.hide()
        self._reset_hover()
        self._reset_navigation()
        self.figure.clear()
        self.figure.set_facecolor(theme().surface)   # 테마가 바뀌었을 수 있다

    # ── 마우스 판독 ──────────────────────────────────────────────
    def set_hover_series(self, entries, *, band: bool = False) -> None:
        """양쪽 그래프에서 같은 시간의 실제 값을 함께 읽는다.

        entries: (축, 결과, 지역 이름, 계열 색) 목록. ``band`` 면 기준선 대신
        그 칸 전체를 옅게 칠한다(막대 차트).
        """
        t = theme()
        self._hover_data = []
        self._hover_axes = [ax for ax, *_rest in entries]
        self._hover_lines = []
        self._hover_marks = []
        for ax, series, name, colors in entries:
            dots = []
            if band:
                shade = Rectangle((0, 0), 1, 1, transform=ax.get_xaxis_transform(), facecolor=t.ink,
                                  alpha=0.07, linewidth=0, zorder=1, visible=False)
                ax.add_artist(shade)
                self._hover_marks.append(shade)
            else:
                self._hover_lines.append(ax.axvline(0, color=t.ink_soft, linewidth=1, alpha=0.7,
                                                    visible=False, zorder=8))
                for color in colors:
                    dot, = ax.plot([], [], linestyle="", marker="o", markersize=9, markerfacecolor=color,
                                   markeredgecolor=t.surface, markeredgewidth=2, visible=False, zorder=9)
                    dots.append(dot)
                self._hover_marks.extend(dots)
            self._hover_data.append((ax, series, name, colors, dots))
        self._hover_lookup = self._series_readout

    def set_hover_lookup(self, axes, lookup, marks=()) -> None:
        """lookup(event) 가 (구분 키, 말풍선 제목, [(색, 문구)]) 또는 None 을 돌려준다.

        ``marks`` 는 lookup 이 위치를 옮기는 강조 표시로, 판독이 끝나면 숨긴다.
        """
        self._hover_axes = list(axes)
        self._hover_lookup = lookup
        self._hover_marks = list(marks)

    def _series_readout(self, event):
        first = self._hover_data[0][1]
        count = len(first.values[0])
        if not count:
            return None
        hour = max(0, min(count - 1, round(event.xdata)))
        rows = []
        for _ax, series, name, colors, dots in self._hover_data:
            for index, (caption, numbers) in enumerate(zip(series.labels, series.values)):
                parts = [name] if name else []
                if len(series.values) > 1 or not name:
                    parts.append(caption)
                color = colors[index] if index < len(colors) else None
                rows.append((color, f"{' '.join(parts)} {_number(numbers[hour], series.unit, caption == '차이')}"))
                if index < len(dots):
                    dots[index].set_data([hour], [numbers[hour]])
                    dots[index].set_visible(math.isfinite(numbers[hour]))
        for line in self._hover_lines:
            line.set_xdata([hour, hour])
            line.set_visible(True)
        for mark in self._hover_marks:
            if isinstance(mark, Rectangle):
                mark.set_x(hour - 0.5)
                mark.set_visible(True)
        return hour, _tick(first, hour), rows

    def _on_motion(self, event) -> None:
        if self._drag is not None:
            self._pan(event)
            return
        if self._hover_lookup is None or event.inaxes not in self._hover_axes:
            self.clear_hover()
            return
        if event.xdata is None or event.ydata is None:
            return
        found = self._hover_lookup(event)
        if found is None:
            self.clear_hover()
            return
        key, title, rows = found
        if key != self._hover_key:
            self._hover_key = key
            self.callout.set_content(title, rows)
            self.draw_idle()
        ratio = self.device_pixel_ratio or 1
        self.callout.point_at(event.x / ratio, self.get_width_height()[1] - event.y / ratio)

    def clear_hover(self) -> None:
        self.callout.hide()
        if self._hover_key is None:
            return
        self._hover_key = None
        for artist in (*self._hover_lines, *self._hover_marks):
            artist.set_visible(False)
        self.draw_idle()

    # ── 확대 · 이동 ──────────────────────────────────────────────
    def set_navigation(self, axes, *, y: bool = False) -> None:
        """확대·이동할 축. 그리기가 끝나 범위가 정해진 뒤 부르며, 그 범위가 ‘원래 크기’다."""
        names = ("x", "y") if y else ("x",)
        self._navigation = [(ax, names) for ax in axes]
        self._home = {(ax, name): _scaled_limits(ax, name) for ax in axes for name in names}

    def _navigation_at(self, x: float, y: float):
        return next(((ax, names) for ax, names in self._navigation if ax.bbox.contains(x, y)), None)

    def _limit(self, ax, name: str, lo: float, hi: float) -> None:
        """원래 범위 밖으로 나가거나 너무 깊이 확대하지 않게 맞춘다."""
        home_lo, home_hi = self._home[(ax, name)]
        span = home_hi - home_lo
        if hi - lo >= span:
            lo, hi = home_lo, home_hi
        elif hi - lo < span / MAX_ZOOM:
            return
        else:
            shift = max(0.0, home_lo - lo) - max(0.0, hi - home_hi)
            lo, hi = lo + shift, hi + shift
        _set_scaled_limits(ax, name, lo, hi)

    def zoom(self, factor: float, x: float, y: float) -> None:
        """표시 좌표 (x, y)를 중심으로 factor 배 범위로 바꾼다. 1보다 작으면 확대."""
        target = self._navigation_at(x, y)
        if target is None:
            return
        ax, names = target
        self.clear_hover()
        for name in names:
            lo, hi = _scaled_limits(ax, name)
            fraction = (x - ax.bbox.x0) / ax.bbox.width if name == "x" else (y - ax.bbox.y0) / ax.bbox.height
            anchor = lo + (hi - lo) * fraction
            self._limit(ax, name, anchor + (lo - anchor) * factor, anchor + (hi - anchor) * factor)
        self._navigated()

    def reset_view(self) -> None:
        for (ax, name), (lo, hi) in self._home.items():
            _set_scaled_limits(ax, name, lo, hi)
        self._navigated()

    def _pan(self, event) -> None:
        ax, names, x0, y0, start = self._drag
        for name in names:
            lo, hi = start[name]
            moved = (event.x - x0) / ax.bbox.width if name == "x" else (event.y - y0) / ax.bbox.height
            self._limit(ax, name, lo - (hi - lo) * moved, hi - (hi - lo) * moved)
        self._navigated()

    def _navigated(self) -> None:
        self._set_zoomed(any(not np.allclose(_scaled_limits(ax, name), home)
                             for (ax, name), home in self._home.items()))
        self.draw_idle()

    def _set_zoomed(self, zoomed: bool) -> None:
        if zoomed != self._zoomed:
            self._zoomed = zoomed
            self.zoomChanged.emit(zoomed)
        if self._drag is not None and zoomed:
            self.setCursor(Qt.ClosedHandCursor)
        elif zoomed:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()

    def _on_press(self, event) -> None:
        if event.button != MouseButton.LEFT:
            return
        target = self._navigation_at(event.x, event.y)
        if target is None:
            return
        if event.dblclick:
            self._drag = None
            self.reset_view()
            return
        ax, names = target
        self._drag = (ax, names, event.x, event.y, {name: _scaled_limits(ax, name) for name in names})
        self.clear_hover()
        self._set_zoomed(self._zoomed)

    def _on_release(self, _event) -> None:
        if self._drag is not None:
            self._drag = None
            self._set_zoomed(self._zoomed)

    def wheelEvent(self, event) -> None:
        # 그냥 스크롤은 페이지로 넘기고, ⌘(Ctrl)을 누른 채 굴릴 때만 확대한다.
        steps = event.angleDelta().y() / 120
        if not (event.modifiers() & Qt.ControlModifier) or not self._navigation or not steps:
            event.ignore()
            return
        self.zoom(0.85 ** steps, *self.mouseEventCoords(event))
        event.accept()

    def event(self, event) -> bool:
        if event.type() == QEvent.NativeGesture and self._navigation:
            if event.gestureType() == Qt.ZoomNativeGesture:
                self.zoom(1 / (1 + event.value()), *self.mouseEventCoords(event.position()))
                return True
            if event.gestureType() == Qt.SmartZoomNativeGesture:
                self.reset_view()
                return True
        return super().event(event)

    def message(self, text: str, detail: str = "") -> None:
        """그래프 대신 안내 문구만 보여준다."""
        self.clear()
        self.figure.set_layout_engine(None)
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(theme().surface)
        ax.axis("off")
        # 빈 화면도 분석 화면과 같은 시각 언어를 사용한다. 실제 데이터와
        # 혼동할 수 있는 샘플 그래프 대신 작은 추상 막대 아이콘을 그린다.
        ax.add_patch(FancyBboxPatch(
            (0.422, 0.58), 0.156, 0.28,
            boxstyle="round,pad=0.012,rounding_size=0.04",
            transform=ax.transAxes, facecolor=theme().muted, edgecolor="none",
        ))
        for x, height in ((0.452, 0.07), (0.484, 0.13), (0.516, 0.10), (0.548, 0.17)):
            ax.add_patch(FancyBboxPatch(
                (x - 0.01, 0.62), 0.018, height,
                boxstyle="round,pad=0.001,rounding_size=0.008",
                transform=ax.transAxes, facecolor=theme().ink_soft, alpha=0.7,
                edgecolor="none",
            ))
        ax.text(0.5, 0.45, text, ha="center", va="center",
                color=theme().ink, fontsize=19, fontweight="bold", wrap=True)
        if detail:
            ax.text(0.5, 0.36, detail, ha="center", va="center",
                    color=theme().ink_soft, fontsize=13, wrap=True)
        self.draw_idle()


# ── 공통 스타일 ───────────────────────────────────────────────────────
def _style_axes(ax, grid_axis: str = "y", baseline: bool = True) -> None:
    t = theme()
    ax.set_facecolor(t.surface)
    ax.grid(True, axis=grid_axis, color=t.grid, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    if baseline:
        ax.spines["bottom"].set_visible(True)
        ax.spines["bottom"].set_color(t.axis)
        ax.spines["bottom"].set_linewidth(1)
    ax.tick_params(colors=t.ink_soft, labelsize=TICK, length=0, pad=8)


def _trailing_values(ax) -> None:
    """값 축 눈금을 오른쪽에 둔다."""
    ax.yaxis.tick_right()
    ax.tick_params(axis="y", labelleft=False, labelright=True, length=0, pad=10)


def _heading(ax, title: str, note: str = "") -> None:
    ax.set_title(title, fontsize=HEADING, fontweight="bold", color=theme().ink, pad=40, loc="left")
    if note:
        ax.annotate(note, xy=(0, 1), xycoords="axes fraction", xytext=(0, 14), textcoords="offset points",
                    fontsize=LABEL, color=theme().ink_soft, va="bottom")


def _region_title(ax, index: int, name: str) -> None:
    """화면의 지역 배지와 같은 모양으로 ‘A 강남구 역삼1동’을 차트 위에 적는다."""
    t = theme()
    badge = ax.annotate(
        "AB"[index], xy=(0, 1), xycoords="axes fraction", xytext=(4, 16), textcoords="offset points",
        ha="left", va="bottom", fontsize=LABEL, fontweight="bold", color=t.series_ink[index],
        bbox=dict(boxstyle="round,pad=0.4,rounding_size=0.45", facecolor=t.series_soft[index], edgecolor="none"),
    )
    ax.annotate(name, xy=(1, 0.5), xycoords=badge, xytext=(10, 0), textcoords="offset points",
                ha="left", va="center", fontsize=TITLE, fontweight="bold", color=t.ink)


def _caption(ax, text: str, corner: str = "top") -> None:
    """축 설명을 회전하지 않고 모서리에 적는다. top: 값 축 위, bottom: 가로축 끝 아래."""
    t = theme()
    style = dict(fontsize=LABEL, color=t.ink_soft, ha="right")
    if corner == "top":
        def anchor(renderer):
            # 오른쪽 눈금 글자의 끝에 맞춘다.
            labels = ax.yaxis.get_tightbbox(renderer) or ax.bbox
            return Bbox.from_extents(ax.bbox.x0, ax.bbox.y0, max(ax.bbox.x1, labels.x1), ax.bbox.y1)
        ax.annotate(text, xy=(1, 1), xycoords=anchor, xytext=(0, 12), textcoords="offset points",
                    va="bottom", **style)
    else:
        ax.annotate(text, xy=(1, 0), xycoords="axes fraction", xytext=(0, -(TICK + 20)),
                    textcoords="offset points", va="top", **style)


def _tint(color: str, amount: float = 0.5) -> str:
    """색에 흰색을 섞은 파스텔 톤. 같은 지역 안의 두 번째 계열에 쓴다."""
    return to_hex([c + (1 - c) * amount for c in to_rgb(color)])


def _stroke(color: str, label: str, dashed: bool = False) -> Line2D:
    return Line2D([], [], color=color, linewidth=LINE, label=label,
                  linestyle=DASH if dashed else "-", solid_capstyle="round", dash_capstyle="round")


def _dot(color: str, label: str) -> Line2D:
    return Line2D([], [], color=color, linestyle="", marker="o", markersize=9, label=label)


def _legend(ax, handles) -> None:
    """범례를 차트 아래 왼쪽에 한 줄로 둔다."""
    below = ScaledTranslation(0, -(TICK + 26) / DPI, ax.figure.dpi_scale_trans)
    legend = ax.legend(
        handles=handles, loc="upper left", bbox_to_anchor=(0, 0), bbox_transform=ax.transAxes + below,
        ncol=len(handles), frameon=False, fontsize=LABEL, handlelength=1.3, handletextpad=0.6,
        columnspacing=1.8, borderpad=0, borderaxespad=0,
    )
    for text in legend.get_texts():
        text.set_color(theme().ink_soft)


def _index_axis(axis, labels, steps) -> None:
    """정수 위치(시간·날짜)를 이름으로 적는다. 확대하면 눈금이 촘촘해진다."""
    axis.set_major_locator(MaxNLocator(nbins=8, integer=True, steps=steps, min_n_ticks=2))

    def name(value, _pos=None):
        index = round(value)
        return labels[index] if abs(value - index) < 1e-6 and 0 <= index < len(labels) else ""

    axis.set_major_formatter(FuncFormatter(name))


def _hour_axis(axis, count: int = 24) -> None:
    _index_axis(axis, [f"{hour}시" for hour in range(count)], HOUR_STEPS)


def _nice_ticks(top: float, bottom: float = 0.0, bins: int = 5) -> list[float]:
    return [float(v) for v in MaxNLocator(nbins=bins, steps=VALUE_STEPS).tick_values(bottom, top)]


def _value_axis(ax, series_list) -> None:
    """세로축 범위와 눈금. 비율(%)은 기준선을 가운데에, 나머지는 0부터 맨 위 눈금까지."""
    finite = [v for series in series_list for values in series.values for v in values if math.isfinite(v)]
    first = series_list[0]
    if first.reference is not None and first.unit == "%":
        spread = max(5.0, max((abs(v - first.reference) for v in finite), default=0) * 1.4)
        ax.set_ylim(max(0.0, first.reference - spread), min(100.0, first.reference + spread))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5, steps=VALUE_STEPS))
    else:
        ticks = _nice_ticks(max(1.0, max(finite, default=1.0) * 1.12))
        ax.set_ylim(0.0, ticks[-1])
        ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.yaxis.set_major_formatter(FuncFormatter(
        (lambda v, _p: f"{v:.0f}%") if first.unit == "%" else
        (lambda v, _p: _short(v)) if first.unit == "명" else _thousands))


def _area(ax, positions, values, color: str) -> None:
    """선 아래를 위에서 아래로 옅어지는 색으로 채운다."""
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return
    outline = ax.fill_between(positions, values, 0, facecolor="none", edgecolor="none")
    paths = outline.get_paths()
    outline.remove()
    if not paths:
        return
    gradient = np.zeros((64, 1, 4))
    gradient[..., :3] = to_rgb(color)
    gradient[..., 3] = np.linspace(0.2, 0.02, 64)[:, None]
    image = ax.imshow(gradient, extent=(positions[0], positions[-1], 0, max(finite)), origin="upper",
                      aspect="auto", interpolation="bilinear", zorder=2)
    image.set_clip_path(Path.make_compound_path(*paths), ax.transData)


# ── 차트 ─────────────────────────────────────────────────────────────
def draw_line_series(canvas: PlotCanvas, series: LineSeries, *, ax=None,
                     title: str | None = None, compact: bool = False,
                     single_color: str | None = None, show_heading: bool = True,
                     region: int | None = None) -> None:
    """시간대·날짜·요일을 x축으로 하는 꺾은선 그래프. 계열은 최대 2개를 전제로 한다.

    ``region`` 을 주면 제목을 지역 배지로 적는다(두 지역 나란히 보기).
    """
    t = theme()
    standalone = ax is None
    if standalone:
        canvas.clear()
        ax = canvas.figure.add_subplot(111)
    _style_axes(ax)
    _trailing_values(ax)

    positions = list(range(len(series.values[0])))
    colors, handles = [], []
    for i, (label, values) in enumerate(zip(series.labels, series.values)):
        # 지역 A/B 비교에서는 한 차트 안의 모든 선이 그 지역 색을 쓰고, 선 모양과 옅은 톤으로 구분한다.
        color = single_color or t.series[i % len(t.series)]
        if single_color and i:
            color = _tint(single_color, 0.3)
        ax.plot(positions, values, color=color, linewidth=LINE,
                linestyle="-" if i == 0 else DASH,
                marker="o" if series.categories is not None else None, markersize=7,
                markeredgecolor=t.surface, markeredgewidth=1.5,
                solid_capstyle="round", solid_joinstyle="round", dash_capstyle="round", zorder=3 + i)
        colors.append(color)
        handles.append(_stroke(color, label, dashed=i > 0))

        # 계열마다 정점 한 곳만 직접 라벨링한다 (모든 점에 값을 붙이지 않는다).
        available = [p for p in positions if math.isfinite(values[p])]
        if not available:
            continue
        peak = max(available, key=lambda p: values[p])
        ax.plot([peak], [values[peak]], marker="o", markersize=8, color=color,
                markeredgecolor=t.surface, markeredgewidth=2, zorder=6)
        when = _tick(series, peak)
        peak_text = f"{label} 최대 {when} · {_number(values[peak], series.unit)}"
        if compact:
            peak_text = f"{when} {_number(values[peak], series.unit)}"
            if len(series.values) > 1:
                peak_text = f"{label} {peak_text}"
        edge = len(positions) // 4
        ax.annotate(
            peak_text,
            xy=(peak, values[peak]),
            xytext=(0, 12 if i == 0 else -22),
            textcoords="offset points",
            ha="left" if peak < edge else "right" if peak >= len(positions) - edge else "center",
            fontsize=TICK if compact else LABEL, color=t.ink_soft, zorder=7,
            path_effects=_halo(),
        )

    if len(series.values) == 1 and series.reference is None:
        _area(ax, positions, series.values[0], colors[0])

    if region is not None:
        _region_title(ax, region, title or series.title)
    elif show_heading:
        _heading(ax, title or series.title, series.note)

    ax.set_xlim(-0.5, max(0.5, len(positions) - 0.5))
    if not any(math.isfinite(v) for values in series.values for v in values):
        ax.text(0.5, 0.5, "이 분석에 필요한 관측이 없습니다", transform=ax.transAxes,
                ha="center", fontsize=LABEL, color=t.ink_soft)
    _value_axis(ax, [series])
    if series.xlabels is not None:
        _index_axis(ax.xaxis, [_tick(series, p) for p in positions], [1, 2, 7, 10])
    elif series.categories is not None:
        ax.xaxis.set_major_locator(FixedLocator(positions))
        ax.xaxis.set_major_formatter(FuncFormatter(
            lambda v, _p: series.categories[round(v)] if 0 <= round(v) < len(positions) else ""))
    else:
        _hour_axis(ax.xaxis, len(positions))
    if series.reference is not None:
        ax.axhline(series.reference, color=t.ink_soft, linewidth=1, linestyle=(0, (3, 3)), zorder=2)

    # 계열이 2개 이상일 때만 범례를 둔다. 1개면 제목이 이미 이름을 말해 준다.
    if len(series.labels) > 1:
        _legend(ax, handles)

    if standalone:
        _caption(ax, series.ylabel)
        _interactive(canvas, "set_hover_series", [(ax, series, "", colors)])
        _interactive(canvas, "set_navigation", [ax])
        canvas.figure.set_layout_engine("tight", pad=0.8)
        canvas.draw_idle()


def draw_age_pyramid(canvas: PlotCanvas, pyramid: AgePyramid, *, ax=None,
                     title: str | None = None, compact: bool = False,
                     color: str | None = None, region: int | None = None) -> None:
    """연령대별 남/녀 인구 피라미드 (남자는 왼쪽으로 눕힌 가로 막대).

    ``color`` 를 주면 지역 색 하나로 그리고, 여자 막대는 흰색을 섞은 옅은 톤으로 칠한다.
    투명도 대신 섞은 색을 쓰므로 어두운 테마에서도 탁해지지 않는다.
    """
    t = theme()
    male_color, female_color = (color, _tint(color)) if color else t.series
    standalone = ax is None
    if standalone:
        canvas.clear()
        ax = canvas.figure.add_subplot(111)
    _style_axes(ax, "x", baseline=False)
    ax.tick_params(axis="y", pad=6)

    positions = list(range(len(pyramid.bands)))
    height = 0.68
    for row, male, female in zip(positions, pyramid.male, pyramid.female):
        ax.add_patch(RoundedBar((0, row - height / 2), -male, height, horizontal=True,
                                facecolor=male_color, linewidth=0, zorder=3))
        ax.add_patch(RoundedBar((0, row - height / 2), female, height, horizontal=True,
                                facecolor=female_color, linewidth=0, zorder=3))
    ax.axvline(0, color=t.surface, linewidth=2, zorder=4)   # 두 막대 사이 2px 여백
    ax.set_yticks(positions, [_band(band) for band in pyramid.bands])
    ax.set_ylim(-0.6, len(positions) - 0.4)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: _short(abs(v))))

    if region is not None:
        _region_title(ax, region, title or pyramid.title)
    elif compact:
        ax.set_title(title or pyramid.title, fontsize=TITLE, fontweight="bold",
                     color=t.ink, pad=18, loc="left")
    else:
        _heading(ax, title or pyramid.title, pyramid.note)

    # 범례 대신 가운데 기준으로 양쪽 방향을 적는다.
    below = -(TICK + 22)
    for sign, name in ((-1, "← 남자"), (1, "여자 →")):
        ax.annotate(name, xy=(0, 0), xycoords=("data", "axes fraction"), xytext=(sign * 8, below),
                    textcoords="offset points", ha="right" if sign < 0 else "left", va="top",
                    fontsize=LABEL, color=t.ink_soft)

    # 가장 인구가 많은 연령대만 직접 라벨링한다.
    for values, sign, name in ((pyramid.male, -1, "남자"), (pyramid.female, 1, "여자")):
        if compact or not values or max(values) <= 0:
            continue
        top = max(positions, key=lambda i: values[i])
        ax.annotate(
            f"{name} 최다\n{_band(pyramid.bands[top])} · {values[top]:,.0f}명",
            xy=(sign * values[top], top),
            xytext=(sign * 8, 0), textcoords="offset points",
            ha="left" if sign > 0 else "right", va="center",
            fontsize=LABEL, color=t.ink_soft, linespacing=1.35, zorder=6,
            path_effects=_halo(),
        )

    # 인구 피라미드는 좌우 대칭 축이 기본. 여유폭은 직접 라벨이 들어갈 자리다.
    limit = max(max(pyramid.male, default=0), max(pyramid.female, default=0)) or 1.0
    ax.set_xlim(-limit * 1.5, limit * 1.5)

    if standalone:
        canvas.figure.set_layout_engine("tight", pad=0.8)
        canvas.draw_idle()


def draw_paired_analysis(canvas: PlotCanvas, comparison: PairedAnalysis, *, show_caption: bool = True) -> None:
    """동일한 크기와 공통 축으로 두 지역을 비교한다."""
    t = theme()
    canvas.clear()
    if isinstance(comparison.analyses[0], Heatmap):
        draw_heatmaps(canvas, comparison)
        return
    axes = canvas.figure.subplots(1, 2, sharex=True, sharey=True)
    caption = comparison.analyses[0].title.removeprefix(comparison.regions[0]).strip()
    if show_caption:
        canvas.figure.suptitle(f"{caption} · {comparison.note}", fontsize=LABEL, color=t.ink_soft)
    is_age = isinstance(comparison.analyses[0], AgePyramid)
    for index, (ax, region, result) in enumerate(zip(axes, comparison.regions, comparison.analyses)):
        if is_age:
            draw_age_pyramid(canvas, result, ax=ax, title=region, compact=True,
                             color=t.series[index], region=index)
            # 공유 축이어도 양쪽에 같은 눈금을 표시한다.
            ax.tick_params(axis="y", labelleft=True)
        else:
            draw_line_series(canvas, result, ax=ax, title=region, compact=True,
                             single_color=t.series[index], region=index)

    if is_age:
        limit = max(max(result.male + result.female, default=0)
                    for result in comparison.analyses) or 1.0
        axes[0].set_xlim(-limit * 1.2, limit * 1.2)
        axes[0].xaxis.set_major_locator(MaxNLocator(nbins=4, symmetric=True))
    else:
        _value_axis(axes[0], comparison.analyses)
        _caption(axes[1], comparison.analyses[1].ylabel)
        _interactive(canvas, "set_hover_series", [
            (ax, result, "AB"[index], [t.series[index]] * len(result.values))
            for index, (ax, result) in enumerate(zip(axes, comparison.analyses))])
        _interactive(canvas, "set_navigation", list(axes))

    canvas.figure.set_layout_engine("tight", pad=0.8, w_pad=3.2)
    canvas.draw_idle()


def draw_heatmaps(canvas, comparison: PairedAnalysis) -> None:
    """두 지역의 히트맵을 위아래로, 같은 색 범위로 그린다. 칸 사이에 2px 틈을 둔다."""
    t = theme()
    canvas.clear()
    canvas.figure.set_layout_engine("constrained", h_pad=10 / DPI, w_pad=6 / DPI)
    axes = canvas.figure.subplots(2, 1, sharex=True, sharey=True)
    first = comparison.analyses[0]
    rows, columns = len(first.rows), len(first.values[0])
    peak = max((v for result in comparison.analyses for row in result.values for v in row
                if math.isfinite(v)), default=1) or 1
    cmap = LinearSegmentedColormap.from_list("hotplace", list(t.heat)).with_extremes(bad=t.muted)
    is_age = first.row_label == "연령대"
    marks = []
    for i, (ax, region, result) in enumerate(zip(axes, comparison.regions, comparison.analyses)):
        _style_axes(ax, baseline=False)
        ax.grid(False)
        im = ax.imshow(np.ma.masked_invalid(result.values), aspect="auto", cmap=cmap, vmin=0, vmax=peak,
                       interpolation="nearest")
        ax.set_xticks(np.arange(-0.5, columns, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, rows, 1), minor=True)
        ax.grid(True, which="minor", color=t.surface, linewidth=2)
        ax.set_axisbelow(False)
        ax.tick_params(which="minor", length=0)
        _region_title(ax, i, region)
        ax.set_yticks(range(rows), [_band(row) for row in result.rows] if is_age else result.rows)
        _hour_axis(ax.xaxis, columns)
        ax.tick_params(labelbottom=True, pad=6, labelsize=TICK - 1 if rows > 7 else TICK)
        cell = Rectangle((0, 0), 1, 1, fill=False, edgecolor=t.ink, linewidth=1.5, zorder=5, visible=False)
        ax.add_artist(cell)
        marks.append(cell)
    fmt = (lambda v, _p=None: f"{v:.0f}%") if first.percent else (lambda v, _p=None: _short(v))
    bar = canvas.figure.colorbar(im, ax=list(axes), aspect=40, pad=0.015, format=FuncFormatter(fmt))
    # 색 막대 설명은 위쪽 지역 제목과 같은 줄에 오른쪽 정렬로 둔다. 레이아웃 폭에는 넣지 않는다.
    title = bar.ax.set_title(first.value_label, fontsize=TICK, color=t.ink_soft, loc="right", pad=16)
    title.set_in_layout(False)
    bar.ax.tick_params(colors=t.ink_soft, labelsize=TICK, length=0, pad=6)
    bar.outline.set_visible(False)
    bar.ax.yaxis.set_minor_locator(NullLocator())

    suffix = "요일"

    def lookup(event):
        row, hour = round(event.ydata), round(event.xdata)
        if not (0 <= row < rows and 0 <= hour < columns):
            return None
        for cell in marks:
            cell.set_xy((hour - 0.5, row - 0.5))
            cell.set_visible(True)
        unit = "%" if first.percent else "명"
        cells = [(t.series[i], f"{'AB'[i]} {_number(result.values[row][hour], unit)}")
                 for i, result in enumerate(comparison.analyses)]
        name = _band(first.rows[row]) if is_age else f"{first.rows[row]}{suffix}"
        return (row, hour), f"{name} {hour}시", cells

    _interactive(canvas, "set_hover_lookup", axes, lookup, marks)
    _interactive(canvas, "set_navigation", [axes[0], axes[1]])
    canvas.draw_idle()


def draw_gap(canvas, gap: HourlyGap, *, show_heading: bool = True) -> None:
    """시간대별 A − B. 0선 위는 A, 아래는 B가 더 많은 시간이다."""
    t = theme()
    canvas.clear()
    ax = canvas.figure.add_subplot(111)
    _style_axes(ax, baseline=False)
    _trailing_values(ax)
    diffs = gap.gap
    hours = list(range(len(diffs)))
    finite = [d for d in diffs if math.isfinite(d)]
    for hour, diff in zip(hours, diffs):
        if math.isfinite(diff) and diff:
            ax.add_patch(RoundedBar((hour - BAR / 2, 0), BAR, diff, linewidth=0, zorder=3,
                                    facecolor=t.series[0] if diff > 0 else t.series[1]))
    ax.axhline(0, color=t.axis, linewidth=1, zorder=4)
    # 한쪽이 계속 많아도 반대편을 조금 남겨 두어 0선의 의미가 보이게 한다.
    limit = max((abs(d) for d in finite), default=1) or 1
    ax.set_ylim(min(min(finite, default=0), -0.3 * limit) * 1.2, max(max(finite, default=0), 0.3 * limit) * 1.2)
    ax.set_xlim(-0.5, len(hours) - 0.5)
    _hour_axis(ax.xaxis, len(hours))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=VALUE_STEPS))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: _short(v, signed=True)))

    if finite:
        hour = max((h for h in hours if math.isfinite(diffs[h])), key=lambda h: abs(diffs[h]))
        value = diffs[hour]
        ax.annotate(f"{hour}시 {'A' if value > 0 else 'B'}가 {abs(value):,.0f}명 더 많음",
                    xy=(hour, value), xytext=(0, 8 if value > 0 else -10), textcoords="offset points",
                    ha="left" if hour < 6 else "right" if hour > 17 else "center",
                    va="bottom" if value > 0 else "top",
                    fontsize=LABEL, color=t.ink_soft, zorder=6, path_effects=_halo())
    else:
        ax.text(0.5, 0.5, "두 지역에 함께 관측된 시간이 없습니다", transform=ax.transAxes,
                ha="center", fontsize=LABEL, color=t.ink_soft)

    if show_heading:
        _heading(ax, gap.title, gap.note)
    _caption(ax, "A − B (명)")
    _legend(ax, [_dot(t.series[0], f"A가 더 많음 · {gap.regions[0]}"),
                 _dot(t.series[1], f"B가 더 많음 · {gap.regions[1]}")])
    _interactive(canvas, "set_hover_series", [(ax, gap, "", [t.series[0], t.series[1]])], band=True)
    _interactive(canvas, "set_navigation", [ax])
    canvas.figure.set_layout_engine("tight", pad=0.8)
    canvas.draw_idle()


def draw_age_shares(canvas, shares: AgeShares, *, show_heading: bool = True) -> None:
    """연령대마다 A와 B의 비중을 두 점과 연결선으로 비교한다."""
    t = theme()
    canvas.clear()
    ax = canvas.figure.add_subplot(111)
    _style_axes(ax, "x", baseline=False)
    ax.tick_params(axis="y", pad=6)
    positions = list(range(len(shares.bands)))
    a, b = shares.shares
    for y, x1, x2 in zip(positions, a, b):
        if math.isfinite(x1) and math.isfinite(x2):
            ax.plot([x1, x2], [y, y], color=t.axis, linewidth=4, solid_capstyle="round", zorder=2)
    for index, values in enumerate((a, b)):
        ax.scatter(values, positions, s=12 ** 2, color=t.series[index], edgecolors=t.surface, linewidths=2,
                   zorder=4 + index)
    ax.set_yticks(positions, [_band(band) for band in shares.bands])
    ax.set_ylim(-0.7, len(positions) - 0.3)
    finite = [v for v in (*a, *b) if math.isfinite(v)]
    ax.set_xlim(0, _nice_ticks(max(1.0, max(finite, default=1.0) * 1.15), bins=6)[-1])
    ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}%"))

    gaps = [(y, x1 - x2) for y, x1, x2 in zip(positions, a, b) if math.isfinite(x1 - x2)]
    if gaps:
        y, diff = max(gaps, key=lambda item: abs(item[1]))
        if abs(diff) >= 0.05:
            ax.annotate(f"{'A' if diff > 0 else 'B'}가 {abs(diff):.1f}%p 높음",
                        xy=(max(a[y], b[y]), y), xytext=(12, 0), textcoords="offset points",
                        va="center", fontsize=LABEL, color=t.ink_soft, zorder=6, path_effects=_halo())
    else:
        ax.text(0.5, 0.5, "이 분석에 필요한 관측이 없습니다", transform=ax.transAxes,
                ha="center", fontsize=LABEL, color=t.ink_soft)

    if show_heading:
        _heading(ax, shares.title, shares.note)
    _legend(ax, [_dot(t.series[index], f"{'AB'[index]} · {shares.regions[index]}") for index in range(2)])

    shade = Rectangle((0, 0), 1, 1, transform=ax.get_yaxis_transform(), facecolor=t.ink, alpha=0.05,
                      linewidth=0, zorder=1, visible=False)
    ax.add_artist(shade)

    def lookup(event):
        row = round(event.ydata)
        if not 0 <= row < len(positions):
            return None
        shade.set_y(row - 0.5)
        shade.set_visible(True)
        diff = a[row] - b[row]
        rows = [(t.series[0], f"A {_number(a[row], '%')}"), (t.series[1], f"B {_number(b[row], '%')}")]
        if math.isfinite(diff):
            rows.append((None, f"차이 {diff:+.1f}%p"))
        return row, _band(shares.bands[row]), rows

    _interactive(canvas, "set_hover_lookup", [ax], lookup, [shade])
    canvas.figure.set_layout_engine("tight", pad=0.8)
    canvas.draw_idle()


def draw_city_scatter(canvas, scatter: CityScatter, *, show_heading: bool = True) -> None:
    """서울 행정동 전체를 회색 점으로, 비교 중인 두 지역을 색 점으로 그린다."""
    t = theme()
    canvas.clear()
    ax = canvas.figure.add_subplot(111)
    _style_axes(ax, "both")
    _trailing_values(ax)
    xs, ys = np.array(scatter.day_night, dtype=float), np.array(scatter.weekend, dtype=float)
    if not len(xs):
        ax.text(0.5, 0.5, "배율을 계산할 수 있는 행정동이 없습니다", transform=ax.transAxes,
                ha="center", fontsize=LABEL, color=t.ink_soft)
        canvas.draw_idle()
        return

    others = [i for i, mark in enumerate(scatter.marks) if not mark]
    ax.scatter(xs[others], ys[others], s=6 ** 2, color=t.ink_soft, alpha=0.3, linewidths=0, zorder=2)

    # 낮 ÷ 밤 배율은 오른쪽으로 길게 치우쳐 있어 로그 눈금으로 그린다.
    ax.set_xscale("log")
    x_lo = min(xs.min(), 0.5) / 1.1
    x_hi = max(xs.max(), OFFICE_DAY_NIGHT) * 1.2
    y_lo = min(ys.min(), WEEKDAY_BUSY) - 0.05
    y_hi = max(ys.max(), WEEKEND_BUSY) + 0.05
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ticks = [v for v in (0.25, 0.5, 1, 2, 4, 8, 16) if x_lo <= v <= x_hi]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}배"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.1f}배"))
    _caption(ax, "주말 ÷ 평일 인구")
    _caption(ax, "낮 ÷ 밤 인구 · 로그 눈금", "bottom")

    guide = dict(color=t.ink_soft, alpha=0.55, linewidth=1, linestyle=(0, (3, 3)), zorder=1)
    for x in (RESIDENTIAL_DAY_NIGHT, OFFICE_DAY_NIGHT):
        ax.axvline(x, **guide)
    for y in (WEEKDAY_BUSY, WEEKEND_BUSY):
        ax.axhline(y, **guide)
    zone = dict(fontsize=TICK, color=t.ink_soft, zorder=3, path_effects=_halo())
    ax.text(x_lo * 1.06, WEEKEND_BUSY + 0.012, "주말 상권형 ↑", ha="left", va="bottom", **zone)
    ax.text(x_hi / 1.06, WEEKDAY_BUSY - 0.012, "업무지구형 ↘", ha="right", va="top", **zone)
    ax.text(RESIDENTIAL_DAY_NIGHT / 1.04, y_lo + 0.012, "← 주거지형", ha="right", va="bottom", **zone)

    for i, mark in enumerate(scatter.marks):
        if not mark:
            continue
        index = 0 if mark.startswith("A") else 1
        ax.scatter([xs[i]], [ys[i]], s=13 ** 2, color=t.series[index], edgecolors=t.surface,
                   linewidths=2.5, zorder=5)
        ax.annotate(f"{mark} · {scatter.names[i]}", xy=(xs[i], ys[i]),
                    xytext=(10, 8 if index == 0 else -10), textcoords="offset points",
                    va="bottom" if index == 0 else "top", fontsize=LABEL, fontweight="bold",
                    color=t.ink, zorder=6, path_effects=_halo())

    if show_heading:
        _heading(ax, scatter.title, scatter.note)

    ring, = ax.plot([], [], linestyle="", marker="o", markersize=17, markerfacecolor="none",
                    markeredgecolor=t.ink, markeredgewidth=1.5, zorder=7, visible=False)

    def lookup(event):
        points = ax.transData.transform(np.column_stack([xs, ys]))
        distance = np.hypot(points[:, 0] - event.x, points[:, 1] - event.y)
        nearest = int(distance.argmin())
        if distance[nearest] > 12 * (canvas.figure.dpi / DPI):
            return None
        ring.set_data([xs[nearest]], [ys[nearest]])
        ring.set_visible(True)
        mark = scatter.marks[nearest]
        color = t.series[0 if mark.startswith("A") else 1] if mark else None
        return nearest, f"{mark} · {scatter.names[nearest]}" if mark else scatter.names[nearest], [
            (color, f"낮 ÷ 밤 {xs[nearest]:.2f}배"), (color, f"주말 ÷ 평일 {ys[nearest]:.2f}배")]

    _interactive(canvas, "set_hover_lookup", [ax], lookup, [ring])
    _interactive(canvas, "set_navigation", [ax], y=True)
    canvas.figure.set_layout_engine("tight", pad=0.8)
    canvas.draw_idle()


def draw_result(canvas, result, *, show_heading: bool = True) -> None:
    """결과 종류에 맞는 그리기 함수를 고른다."""
    if isinstance(result, PairedAnalysis):
        draw_paired_analysis(canvas, result, show_caption=show_heading)
    elif isinstance(result, HourlyGap):
        draw_gap(canvas, result, show_heading=show_heading)
    elif isinstance(result, AgeShares):
        draw_age_shares(canvas, result, show_heading=show_heading)
    elif isinstance(result, CityScatter):
        draw_city_scatter(canvas, result, show_heading=show_heading)
    elif isinstance(result, AgePyramid):
        draw_age_pyramid(canvas, result)
    else:
        draw_line_series(canvas, result, show_heading=show_heading)
