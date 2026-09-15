"""matplotlib 렌더링 - 한글 폰트 설정, Qt 캔버스, 그래프 그리기.

분석 결과(:mod:`hotplace.hotplace` 의 LineSeries / AgePyramid 등)를 받아
그림으로만 옮긴다. 계산은 하지 않는다.
"""

from __future__ import annotations

import matplotlib
import math

import matplotlib.patheffects as path_effects
from PySide6.QtCore import QSize, Signal
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch, Patch
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, MultipleLocator, NullLocator

from .hotplace import (
    OFFICE_DAY_NIGHT, RESIDENTIAL_DAY_NIGHT, WEEKDAY_BUSY, WEEKEND_BUSY,
    AgePyramid, AgeShares, CityScatter, Heatmap, HourlyGap, LineSeries, PairedAnalysis,
)

from .theme import DARK, LIGHT, Theme, set_theme, theme


def _halo():
    """직접 라벨이 선·막대 위에 겹쳐도 읽히도록 배경색 테두리를 두른다."""
    return [path_effects.withStroke(linewidth=3.2, foreground=theme().surface)]


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


def _hover(canvas, method: str, *args) -> None:
    # --check 에서 쓰는 Figure 껍데기에는 마우스 판독이 없다.
    if hasattr(canvas, method):
        getattr(canvas, method)(*args)


class PlotCanvas(FigureCanvasQTAgg):
    """Qt 위젯으로 쓰는 matplotlib 캔버스."""

    hovered = Signal(str)

    def __init__(self, parent=None, width=7.4, height=4.4, dpi=110) -> None:
        configure_matplotlib()
        self.figure = Figure(figsize=(width, height), dpi=dpi, facecolor=theme().surface)
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(250)
        self._reset_hover()
        self.mpl_connect("motion_notify_event", self._on_hover)
        self.mpl_connect("figure_leave_event", lambda _event: self.clear_hover())

    def sizeHint(self) -> QSize:
        # FigureCanvas의 기본 힌트는 현재 크기를 반환한다. 스크롤 영역에서는
        # 창을 줄여도 예전 높이를 요구하므로 안정된 선호 크기를 제공한다.
        return QSize(800, 320)

    def _reset_hover(self) -> None:
        self._hover_data = []
        self._hover_lines = []
        self._hover_axes = []
        self._hover_lookup = None
        self._hover_hour = None

    def clear(self) -> None:
        self._reset_hover()
        self.hovered.emit("")
        self.figure.clear()
        self.figure.set_facecolor(theme().surface)   # 테마가 바뀌었을 수 있다

    def set_hover_series(self, entries) -> None:
        """양쪽 그래프에서 같은 시간의 실제 값을 함께 읽는다."""
        self._hover_data = entries
        self._hover_lines = [
            ax.axvline(0, color=theme().ink_soft, linewidth=0.8,
                       linestyle=(0, (3, 4)), visible=False, zorder=8)
            for ax, _series, _name in entries
        ]
        self._hover_axes = [ax for ax, _series, _name in entries]
        self._hover_lookup = self._series_readout

    def set_hover_lookup(self, axes, lookup) -> None:
        """lookup(event) 가 (구분 키, 판독 문구) 또는 None 을 돌려준다."""
        self._hover_axes = list(axes)
        self._hover_lookup = lookup

    def _series_readout(self, event):
        first = self._hover_data[0][1]
        count = len(first.values[0])
        if not count:
            return None
        hour = max(0, min(count - 1, round(event.xdata)))
        values = [_tick(first, hour)]
        for (_ax, series, name), line in zip(self._hover_data, self._hover_lines):
            line.set_xdata([hour, hour])
            line.set_visible(True)
            for caption, numbers in zip(series.labels, series.values):
                parts = [name] if name else []
                if len(series.values) > 1 or not name:
                    parts.append(caption)
                values.append(f"{' '.join(parts)} {_number(numbers[hour], series.unit, caption == '차이')}")
        return hour, "  ·  ".join(values)

    def _on_hover(self, event) -> None:
        if self._hover_lookup is None or event.inaxes not in self._hover_axes or self.widgetlock.locked():
            self.clear_hover()
            return
        if event.xdata is None or event.ydata is None:
            return
        found = self._hover_lookup(event)
        if found is None:
            self.clear_hover()
            return
        key, text = found
        if key == self._hover_hour:
            return
        self._hover_hour = key
        self.hovered.emit(text)
        self.draw_idle()

    def clear_hover(self) -> None:
        if self._hover_hour is None:
            return
        self._hover_hour = None
        for line in self._hover_lines:
            line.set_visible(False)
        self.hovered.emit("")
        self.draw_idle()

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
                color=theme().ink, fontsize=13, fontweight="bold", wrap=True)
        if detail:
            ax.text(0.5, 0.32, detail, ha="center", va="center",
                    color=theme().ink_soft, fontsize=9, wrap=True)
        self.draw_idle()


def _style_axes(ax, grid_axis: str = "y") -> None:
    ax.set_facecolor(theme().surface)
    ax.grid(True, axis=grid_axis, color=theme().grid, linewidth=0.7, linestyle=(0, (3, 4)))
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(theme().axis)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=theme().ink_soft, labelsize=8.5, length=0, pad=9)


def _heading(ax, title: str, note: str = "") -> None:
    ax.set_title(title, fontsize=12, fontweight="bold", color=theme().ink, pad=30, loc="left")
    if note:
        ax.text(0, 1.045, note, transform=ax.transAxes, fontsize=8.5, color=theme().ink_soft, va="bottom")


def _legend(ax, **kwargs) -> None:
    legend = ax.legend(**{"frameon": False, "fontsize": 9, "handlelength": 1.4, "borderpad": 0.2, **kwargs})
    for text in legend.get_texts():
        text.set_color(theme().ink_soft)


def _legend_place(show_heading: bool) -> dict:
    """제목·설명이 차트 위에 있으면 범례를 안쪽에, 없으면 차트 위 오른쪽에 둔다."""
    if show_heading:
        return {"loc": "best"}
    return {"loc": "lower right", "bbox_to_anchor": (1, 1.0), "ncol": 2}


def _value_limits(series_list) -> tuple[float, float]:
    """세로축 범위. 비율(%)은 기준선을 가운데에 두고, 나머지는 0부터 시작한다."""
    finite = [v for series in series_list for values in series.values for v in values if math.isfinite(v)]
    first = series_list[0]
    if first.reference is not None and first.unit == "%":
        spread = max(5.0, max((abs(v - first.reference) for v in finite), default=0) * 1.4)
        return max(0.0, first.reference - spread), min(100.0, first.reference + spread)
    return 0.0, max(1.0, max(finite, default=1.0) * 1.2)


def draw_line_series(canvas: PlotCanvas, series: LineSeries, *, ax=None,
                     title: str | None = None, compact: bool = False,
                     single_color: str | None = None, show_heading: bool = True) -> None:
    """시간대·날짜·요일을 x축으로 하는 꺾은선 그래프. 계열은 최대 2개를 전제로 한다."""
    standalone = ax is None
    if standalone:
        canvas.clear()
        ax = canvas.figure.add_subplot(111)
    _style_axes(ax)

    positions = list(range(len(series.values[0])))
    for i, (label, values) in enumerate(zip(series.labels, series.values)):
        # 지역 A/B 비교에서는 한 차트 안의 모든 선이 그 지역 색을 쓰고, 선 모양으로 구분한다.
        color = single_color or theme().series[i % len(theme().series)]
        ax.plot(positions, values, label=label, color=color, linewidth=2.2,
                linestyle="-" if i == 0 else (0, (4, 2.5)),
                alpha=1.0 if i == 0 or not single_color else 0.7,
                marker="o" if series.categories is not None else None, markersize=4.5,
                solid_capstyle="round", zorder=3 + i)

        # 계열마다 정점 한 곳만 직접 라벨링한다 (모든 점에 값을 붙이지 않는다).
        available = [p for p in positions if math.isfinite(values[p])]
        if not available:
            continue
        peak = max(available, key=lambda p: values[p])
        ax.plot([peak], [values[peak]], marker="o", markersize=6.5, color=color,
                markeredgecolor=theme().surface, markeredgewidth=1.6, zorder=6)
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
            xytext=(0, 11 if i == 0 else -19),
            textcoords="offset points",
            ha="left" if peak < edge else "right" if peak >= len(positions) - edge else "center",
            fontsize=7.5 if compact else 8.5, color=theme().ink_soft, zorder=7,
            path_effects=_halo(),
        )

    if show_heading:
        if compact:
            ax.set_title(title or series.title, fontsize=10.5, fontweight="bold",
                         color=theme().ink, pad=18, loc="left")
        else:
            _heading(ax, title or series.title, series.note)

    if not compact:
        ax.set_xlabel(series.xlabel, fontsize=9, color=theme().ink_soft, labelpad=6)
    ax.set_ylabel(series.ylabel, fontsize=9, color=theme().ink_soft, labelpad=6)
    ax.set_xlim(-0.6, max(0.6, len(positions) - 0.4))

    if not any(math.isfinite(v) for values in series.values for v in values):
        ax.text(0.5, 0.5, "이 분석에 필요한 관측이 없습니다", transform=ax.transAxes,
                ha="center", color=theme().ink_soft)
    ax.set_ylim(*_value_limits([series]))
    if len(series.values) == 1 and series.reference is None:
        ax.fill_between(positions, series.values[0], 0,
                        color=single_color or theme().series[0], alpha=0.07, zorder=2)
    ax.xaxis.set_major_locator(MultipleLocator(1))
    if series.xlabels is not None:
        ticks = positions[::max(1, math.ceil(len(positions) / 6))]
        ax.set_xticks(ticks, [_tick(series, p) for p in ticks])
    elif series.categories is not None:
        ax.set_xticks(positions, series.categories)
    else:
        ticks = [0, 4, 8, 12, 16, 20, 23] if compact else positions
        ax.set_xticks(ticks, [f"{h}시" for h in ticks] if compact else None)
    if series.reference is not None:
        ax.axhline(series.reference, color=theme().ink_soft, linewidth=1, linestyle=":", zorder=2)
    ax.yaxis.set_major_formatter(FuncFormatter(
        (lambda v, _p: f"{v:.0f}%") if series.unit == "%" else _thousands))
    if compact:
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.tick_params(labelsize=8)

    # 계열이 2개 이상일 때만 범례를 둔다. 1개면 제목이 이미 이름을 말해 준다.
    if len(series.labels) > 1:
        _legend(ax, loc="upper left", handlelength=1.6)

    if standalone:
        _hover(canvas, "set_hover_series", [(ax, series, "")])
        canvas.figure.set_layout_engine("tight", pad=1.8)
        canvas.draw_idle()


def draw_age_pyramid(canvas: PlotCanvas, pyramid: AgePyramid, *, ax=None,
                     title: str | None = None, compact: bool = False,
                     color: str | None = None) -> None:
    """연령대별 남/녀 인구 피라미드 (남자는 왼쪽으로 눕힌 가로 막대).

    ``color`` 를 주면 지역 색 하나로 그리고, 여자 막대는 옅게 칠한다.
    """
    male_color, female_color = (color, color) if color else theme().series
    standalone = ax is None
    if standalone:
        canvas.clear()
        ax = canvas.figure.add_subplot(111)
    _style_axes(ax, "x")
    ax.tick_params(pad=4)

    positions = list(range(len(pyramid.bands)))
    ax.barh(positions, [-m for m in pyramid.male], height=0.62,
            color=male_color, label="남자", zorder=3)
    ax.barh(positions, pyramid.female, height=0.62,
            color=female_color, alpha=0.5 if color else 1.0, label="여자", zorder=3)

    ax.axvline(0, color=theme().surface, linewidth=2, zorder=4)   # 두 막대 사이 2px 여백
    ax.set_yticks(positions)
    ax.set_yticklabels(pyramid.bands)
    ax.set_xlabel("평균 생활인구(명)", fontsize=9, color=theme().ink_soft, labelpad=6)
    ax.set_ylabel("연령대(세)", fontsize=9, color=theme().ink_soft, labelpad=6)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{abs(v):,.0f}"))

    if compact:
        ax.set_title(title or pyramid.title, fontsize=10.5, fontweight="bold",
                     color=theme().ink, pad=18, loc="left")
    else:
        _heading(ax, title or pyramid.title, pyramid.note)

    # 가장 인구가 많은 연령대만 직접 라벨링한다.
    for values, sign, name in ((pyramid.male, -1, "남자"), (pyramid.female, 1, "여자")):
        if compact or not values or max(values) <= 0:
            continue
        top = max(positions, key=lambda i: values[i])
        ax.annotate(
            f"{name} 최다\n{pyramid.bands[top]}세 · {values[top]:,.0f}명",
            xy=(sign * values[top], top),
            xytext=(sign * 8, 0), textcoords="offset points",
            ha="left" if sign > 0 else "right", va="center",
            fontsize=8.5, color=theme().ink_soft, linespacing=1.35, zorder=6,
            path_effects=_halo(),
        )

    _legend(ax, loc="lower right", handlelength=1.2)

    # 인구 피라미드는 좌우 대칭 축이 기본. 여유폭은 직접 라벨이 들어갈 자리다.
    limit = max(max(pyramid.male, default=0), max(pyramid.female, default=0)) or 1.0
    ax.set_xlim(-limit * 1.5, limit * 1.5)

    if standalone:
        canvas.figure.set_layout_engine("tight", pad=1.8)
        canvas.draw_idle()


def draw_paired_analysis(canvas: PlotCanvas, comparison: PairedAnalysis, *, show_caption: bool = True) -> None:
    """동일한 크기와 공통 축으로 두 지역을 비교한다."""
    canvas.clear()
    if isinstance(comparison.analyses[0], Heatmap):
        draw_heatmaps(canvas, comparison)
        return
    axes = canvas.figure.subplots(2, 1, sharex=True, sharey=True)
    caption = comparison.analyses[0].title.removeprefix(comparison.regions[0]).strip()
    if show_caption:
        canvas.figure.suptitle(f"{caption} · {comparison.note}", fontsize=9, color=theme().ink_soft)
    is_age = isinstance(comparison.analyses[0], AgePyramid)
    for index, (ax, region, result) in enumerate(zip(axes, comparison.regions, comparison.analyses)):
        caption = f"{'AB'[index]} · {region}"
        if is_age:
            draw_age_pyramid(canvas, result, ax=ax, title=caption, compact=True,
                             color=theme().series[index])
        else:
            draw_line_series(canvas, result, ax=ax, title=caption, compact=True,
                             single_color=theme().series[index])
        ax.set_title(caption, loc="left", color=theme().ink, fontsize=10.5,
                     fontweight="bold", pad=16)
        # 위아래 차트 모두 같은 눈금과 단위를 표시한다.
        ax.tick_params(labelleft=True, labelbottom=True)

    if is_age:
        limit = max(max(result.male + result.female, default=0)
                    for result in comparison.analyses) or 1.0
        axes[0].set_xlim(-limit * 1.2, limit * 1.2)
        axes[0].xaxis.set_major_locator(MaxNLocator(nbins=4, symmetric=True))
    else:
        axes[0].set_ylim(*_value_limits(comparison.analyses))
        _hover(canvas, "set_hover_series", [(ax, result, "AB"[index])
                                            for index, (ax, result) in enumerate(zip(axes, comparison.analyses))])

    canvas.figure.set_layout_engine("tight", pad=1.6, h_pad=2.4)
    canvas.draw_idle()


def draw_heatmaps(canvas, comparison: PairedAnalysis) -> None:
    """두 지역의 히트맵을 위아래로, 같은 색 범위로 그린다."""
    from matplotlib.colors import LinearSegmentedColormap
    import numpy as np
    canvas.clear()
    canvas.figure.set_layout_engine("constrained")
    axes = canvas.figure.subplots(2, 1, sharex=True, sharey=True)
    first = comparison.analyses[0]
    peak = max((v for result in comparison.analyses for row in result.values for v in row
                if math.isfinite(v)), default=1) or 1
    cmap = LinearSegmentedColormap.from_list("hotplace", list(theme().heat)).with_extremes(bad=theme().surface)
    fmt = (lambda v, _p=None: f"{v:.0f}%") if first.percent else _thousands
    for i, (ax, region, result) in enumerate(zip(axes, comparison.regions, comparison.analyses)):
        _style_axes(ax)
        ax.grid(False)
        im = ax.imshow(np.ma.masked_invalid(result.values), aspect="auto", cmap=cmap, vmin=0, vmax=peak)
        ax.set_title(f"{'AB'[i]} · {region}", loc="left", color=theme().ink, fontsize=10.5,
                     fontweight="bold", pad=10)
        ax.set_yticks(range(len(result.rows)), result.rows)
        ticks = [0, 4, 8, 12, 16, 20, 23]
        ax.set_xticks(ticks, [f"{h}시" for h in ticks])
        ax.tick_params(labelbottom=True, pad=4, labelsize=7.5 if len(result.rows) > 7 else 8.5)
    bar = canvas.figure.colorbar(im, ax=list(axes), shrink=0.82, pad=0.03, format=FuncFormatter(fmt))
    bar.set_label(first.value_label, color=theme().ink_soft, fontsize=9)
    bar.ax.tick_params(colors=theme().ink_soft, labelsize=8)
    bar.outline.set_visible(False)

    suffix = "세" if first.row_label == "연령대" else "요일"

    def lookup(event):
        row, hour = round(event.ydata), round(event.xdata)
        if not (0 <= row < len(first.rows) and 0 <= hour < len(first.values[0])):
            return None
        unit = "%" if first.percent else "명"
        cells = [f"{'AB'[i]} {_number(result.values[row][hour], unit)}"
                 for i, result in enumerate(comparison.analyses)]
        return (row, hour), "  ·  ".join([f"{first.rows[row]}{suffix} {hour}시", *cells])

    _hover(canvas, "set_hover_lookup", axes, lookup)
    canvas.draw_idle()


def draw_gap(canvas, gap: HourlyGap, *, show_heading: bool = True) -> None:
    """시간대별 A − B. 0선 위는 A, 아래는 B가 더 많은 시간이다."""
    t = theme()
    canvas.clear()
    ax = canvas.figure.add_subplot(111)
    _style_axes(ax)
    diffs = gap.gap
    hours = list(range(len(diffs)))
    finite = [d for d in diffs if math.isfinite(d)]
    ax.bar(hours, [d if math.isfinite(d) else 0 for d in diffs], width=0.8,
           color=[t.series[0] if d >= 0 else t.series[1] for d in diffs], zorder=3)
    ax.axhline(0, color=t.axis, linewidth=1, zorder=4)
    # 한쪽이 계속 많아도 반대편을 조금 남겨 두어 0선의 의미가 보이게 한다.
    limit = max((abs(d) for d in finite), default=1) or 1
    ax.set_ylim(min(min(finite, default=0), -0.3 * limit) * 1.3, max(max(finite, default=0), 0.3 * limit) * 1.3)
    ax.set_xlim(-0.6, len(hours) - 0.4)
    ticks = [0, 4, 8, 12, 16, 20, 23]
    ax.set_xticks(ticks, [f"{h}시" for h in ticks])
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:+,.0f}" if round(v) else "0"))
    ax.set_ylabel("A − B (명)", fontsize=9, color=t.ink_soft, labelpad=6)

    if finite:
        hour = max((h for h in hours if math.isfinite(diffs[h])), key=lambda h: abs(diffs[h]))
        value = diffs[hour]
        ax.annotate(f"{hour}시 {'A' if value > 0 else 'B'}가 {abs(value):,.0f}명 더 많음",
                    xy=(hour, value), xytext=(0, 7 if value > 0 else -9), textcoords="offset points",
                    ha="left" if hour < 6 else "right" if hour > 17 else "center",
                    va="bottom" if value > 0 else "top",
                    fontsize=8.5, color=t.ink_soft, zorder=6, path_effects=_halo())
    else:
        ax.text(0.5, 0.5, "두 지역에 함께 관측된 시간이 없습니다", transform=ax.transAxes,
                ha="center", color=t.ink_soft)

    handles = [Patch(color=t.series[0], label=f"A가 더 많음 · {gap.regions[0]}"),
               Patch(color=t.series[1], label=f"B가 더 많음 · {gap.regions[1]}")]
    if show_heading:
        _heading(ax, gap.title, gap.note)
    _legend(ax, handles=handles, **_legend_place(show_heading))
    _hover(canvas, "set_hover_series", [(ax, gap, "")])
    canvas.figure.set_layout_engine("tight", pad=1.8)
    canvas.draw_idle()


def draw_age_shares(canvas, shares: AgeShares, *, show_heading: bool = True) -> None:
    """연령대마다 A와 B의 비중을 두 점과 연결선으로 비교한다."""
    t = theme()
    canvas.clear()
    ax = canvas.figure.add_subplot(111)
    _style_axes(ax, "x")
    ax.tick_params(pad=4)
    positions = list(range(len(shares.bands)))
    a, b = shares.shares
    for y, x1, x2 in zip(positions, a, b):
        if math.isfinite(x1) and math.isfinite(x2):
            ax.plot([x1, x2], [y, y], color=t.axis, linewidth=2, solid_capstyle="round", zorder=2)
    for index, values in enumerate((a, b)):
        ax.scatter(values, positions, s=60, color=t.series[index], edgecolors=t.surface, linewidths=1.6,
                   zorder=4 + index, label=f"{'AB'[index]} · {shares.regions[index]}")
    ax.set_yticks(positions, shares.bands)
    ax.set_ylim(-0.7, len(positions) - 0.3)
    finite = [v for v in (*a, *b) if math.isfinite(v)]
    ax.set_xlim(0, max(1.0, max(finite, default=1.0) * 1.2))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=8, steps=[1, 2, 5, 10]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}%"))
    ax.set_xlabel("지역 인구 중 비중(%)", fontsize=9, color=t.ink_soft, labelpad=6)
    ax.set_ylabel("연령대(세)", fontsize=9, color=t.ink_soft, labelpad=6)

    gaps = [(y, x1 - x2) for y, x1, x2 in zip(positions, a, b) if math.isfinite(x1 - x2)]
    if gaps:
        y, diff = max(gaps, key=lambda item: abs(item[1]))
        if abs(diff) >= 0.05:
            ax.annotate(f"{'A' if diff > 0 else 'B'}가 {abs(diff):.1f}%p 높음",
                        xy=(max(a[y], b[y]), y), xytext=(10, 0), textcoords="offset points",
                        va="center", fontsize=8.5, color=t.ink_soft, zorder=6, path_effects=_halo())
    else:
        ax.text(0.5, 0.5, "이 분석에 필요한 관측이 없습니다", transform=ax.transAxes,
                ha="center", color=t.ink_soft)

    if show_heading:
        _heading(ax, shares.title, shares.note)
    _legend(ax, handletextpad=0.3, **_legend_place(show_heading))

    def lookup(event):
        row = round(event.ydata)
        if not 0 <= row < len(positions):
            return None
        diff = a[row] - b[row]
        text = (f"{shares.bands[row]}세  ·  A {_number(a[row], '%')}  ·  B {_number(b[row], '%')}"
                + (f"  ·  차이 {diff:+.1f}%p" if math.isfinite(diff) else ""))
        return row, text

    _hover(canvas, "set_hover_lookup", [ax], lookup)
    canvas.figure.set_layout_engine("tight", pad=1.8)
    canvas.draw_idle()


def draw_city_scatter(canvas, scatter: CityScatter, *, show_heading: bool = True) -> None:
    """서울 행정동 전체를 회색 점으로, 비교 중인 두 지역을 색 점으로 그린다."""
    import numpy as np
    t = theme()
    canvas.clear()
    ax = canvas.figure.add_subplot(111)
    _style_axes(ax)
    ax.grid(True, axis="x", color=t.grid, linewidth=0.7, linestyle=(0, (3, 4)))
    ax.tick_params(pad=5)
    xs, ys = np.array(scatter.day_night, dtype=float), np.array(scatter.weekend, dtype=float)
    if not len(xs):
        ax.text(0.5, 0.5, "배율을 계산할 수 있는 행정동이 없습니다", transform=ax.transAxes,
                ha="center", color=t.ink_soft)
        canvas.draw_idle()
        return

    others = [i for i, mark in enumerate(scatter.marks) if not mark]
    ax.scatter(xs[others], ys[others], s=16, color=t.ink_soft, alpha=0.35, linewidths=0, zorder=2)

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
    ax.set_xlabel("낮 ÷ 밤 인구 (로그 눈금)", fontsize=9, color=t.ink_soft, labelpad=6)
    ax.set_ylabel("주말 ÷ 평일 인구", fontsize=9, color=t.ink_soft, labelpad=6)

    guide = dict(color=t.axis, linewidth=1, linestyle=(0, (3, 3)), zorder=1)
    for x in (RESIDENTIAL_DAY_NIGHT, OFFICE_DAY_NIGHT):
        ax.axvline(x, **guide)
    for y in (WEEKDAY_BUSY, WEEKEND_BUSY):
        ax.axhline(y, **guide)
    zone = dict(fontsize=8, color=t.ink_soft, zorder=3, path_effects=_halo())
    ax.text(x_lo * 1.06, WEEKEND_BUSY + 0.012, "주말 상권형 ↑", ha="left", va="bottom", **zone)
    ax.text(x_hi / 1.06, WEEKDAY_BUSY - 0.012, "업무지구형 ↘", ha="right", va="top", **zone)
    ax.text(RESIDENTIAL_DAY_NIGHT / 1.04, y_lo + 0.012, "← 주거지형", ha="right", va="bottom", **zone)

    for i, mark in enumerate(scatter.marks):
        if not mark:
            continue
        index = 0 if mark.startswith("A") else 1
        ax.scatter([xs[i]], [ys[i]], s=90, color=t.series[index], edgecolors=t.surface,
                   linewidths=1.8, zorder=5)
        ax.annotate(f"{mark} · {scatter.names[i]}", xy=(xs[i], ys[i]),
                    xytext=(9, 7 if index == 0 else -9), textcoords="offset points",
                    va="bottom" if index == 0 else "top", fontsize=9, fontweight="bold",
                    color=t.ink, zorder=6, path_effects=_halo())

    if show_heading:
        _heading(ax, scatter.title, scatter.note)

    def lookup(event):
        points = ax.transData.transform(np.column_stack([xs, ys]))
        distance = np.hypot(points[:, 0] - event.x, points[:, 1] - event.y)
        nearest = int(distance.argmin())
        if distance[nearest] > 12:
            return None
        mark = f"{scatter.marks[nearest]} · " if scatter.marks[nearest] else ""
        return nearest, (f"{mark}{scatter.names[nearest]}  ·  낮 ÷ 밤 {xs[nearest]:.2f}배"
                         f"  ·  주말 ÷ 평일 {ys[nearest]:.2f}배")

    _hover(canvas, "set_hover_lookup", [ax], lookup)
    canvas.figure.set_layout_engine("tight", pad=1.8)
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
