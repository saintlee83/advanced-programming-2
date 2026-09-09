"""matplotlib 렌더링 - 한글 폰트 설정, Qt 캔버스, 그래프 그리기.

분석 결과(:mod:`hotplace.hotplace` 의 LineSeries / AgePyramid)를 받아
그림으로만 옮긴다. 계산은 하지 않는다.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("QtAgg")

import matplotlib.patheffects as path_effects
from PyQt5.QtCore import QSize
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter, MaxNLocator, MultipleLocator

from .hotplace import AgePyramid, LineSeries, PairedAnalysis

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


class PlotCanvas(FigureCanvasQTAgg):
    """Qt 위젯으로 쓰는 matplotlib 캔버스."""

    def __init__(self, parent=None, width=7.4, height=4.4, dpi=110) -> None:
        configure_matplotlib()
        self.figure = Figure(figsize=(width, height), dpi=dpi, facecolor=theme().surface)
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(250)

    def sizeHint(self) -> QSize:
        # FigureCanvas의 기본 힌트는 현재 크기를 반환한다. 스크롤 영역에서는
        # 창을 줄여도 예전 높이를 요구하므로 안정된 선호 크기를 제공한다.
        return QSize(640, 280)

    def clear(self) -> None:
        self.figure.clear()
        self.figure.set_facecolor(theme().surface)   # 테마가 바뀌었을 수 있다

    def message(self, text: str, detail: str = "") -> None:
        """그래프 대신 안내 문구만 보여준다."""
        self.clear()
        self.figure.set_layout_engine(None)
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(theme().surface)
        ax.axis("off")
        # 빈 화면도 분석 화면과 같은 시각 언어를 사용한다. 실제 데이터와
        # 혼동할 수 있는 샘플 그래프 대신 작은 추상 막대 아이콘을 그린다.
        for x, height in ((0.452, 0.07), (0.484, 0.13), (0.516, 0.10), (0.548, 0.17)):
            ax.add_patch(FancyBboxPatch(
                (x - 0.01, 0.62), 0.018, height,
                boxstyle="round,pad=0.001,rounding_size=0.008",
                transform=ax.transAxes, facecolor=theme().accent, alpha=0.65,
                edgecolor="none",
            ))
        ax.text(0.5, 0.45, text, ha="center", va="center",
                color=theme().ink, fontsize=14, fontweight="bold", wrap=True)
        if detail:
            ax.text(0.5, 0.32, detail, ha="center", va="center",
                    color=theme().ink_soft, fontsize=9, wrap=True)
        self.draw_idle()


def _style_axes(ax) -> None:
    ax.set_facecolor(theme().surface)
    ax.grid(True, axis="y", color=theme().grid, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    for side in ("bottom",):
        ax.spines[side].set_color(theme().axis)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=theme().ink_soft, labelsize=8.5, length=0, pad=9)


def draw_line_series(canvas: PlotCanvas, series: LineSeries, *, ax=None,
                     title: str | None = None, compact: bool = False,
                     single_color: str | None = None) -> None:
    """시간대별 꺾은선 그래프. 계열은 최대 2개를 전제로 한다."""
    standalone = ax is None
    if standalone:
        canvas.clear()
        ax = canvas.figure.add_subplot(111)
    _style_axes(ax)

    hours = list(range(24))
    for i, (label, values) in enumerate(zip(series.labels, series.values)):
        color = theme().series[i % len(theme().series)]
        if len(series.values) == 1 and single_color:
            color = single_color
        ax.plot(hours, values, label=label, color=color, linewidth=2.3,
                linestyle="-" if i == 0 else (0, (5, 3)),
                solid_capstyle="round", zorder=3 + i)

        # 계열마다 정점 한 곳만 직접 라벨링한다 (모든 점에 값을 붙이지 않는다).
        peak = max(hours, key=lambda h: values[h])
        ax.plot([peak], [values[peak]], marker="o", markersize=6, color=color,
                markeredgecolor=theme().surface, markeredgewidth=1.6, zorder=6)
        peak_text = f"{label} 최대 {peak}시 · {values[peak]:,.0f}명"
        if compact:
            peak_text = f"{peak}시 · {values[peak]:,.0f}명"
        ax.annotate(
            peak_text,
            xy=(peak, values[peak]),
            xytext=(0, 11 if i == 0 else -19),
            textcoords="offset points",
            ha="left" if peak <= 5 else "right" if peak >= 18 else "center",
            fontsize=7.5 if compact else 8.5, color=theme().ink_soft, zorder=7,
            path_effects=_halo(),
        )

    ax.set_title(title or series.title, fontsize=10.5 if compact else 12,
                 fontweight="bold", color=theme().ink, pad=18 if compact else 30, loc="left")
    if series.note and not compact:
        ax.text(0, 1.045, series.note, transform=ax.transAxes,
                fontsize=8.5, color=theme().ink_soft, va="bottom")

    ax.set_xlabel(series.xlabel, fontsize=9, color=theme().ink_soft, labelpad=6)
    ax.set_ylabel(series.ylabel, fontsize=9, color=theme().ink_soft, labelpad=6)
    ax.set_xlim(-0.6, 23.6)

    # 정점 위·아래에 붙는 라벨이 들어갈 자리를 세로로 확보한다.
    lo = min(min(v) for v in series.values)
    hi = max(max(v) for v in series.values)
    span = (hi - lo) or (hi or 1.0)
    ax.set_ylim(lo - span * 0.14, hi + span * 0.16)
    if len(series.values) == 1:
        ax.fill_between(hours, series.values[0], 0 if compact else lo - span * 0.14,
                        color=single_color or theme().series[0], alpha=0.065, zorder=2)
    ax.xaxis.set_major_locator(MultipleLocator(1))
    ax.set_xticks([0, 4, 8, 12, 16, 20, 23] if compact else hours)
    ax.yaxis.set_major_formatter(FuncFormatter(_thousands))
    if compact:
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.tick_params(labelsize=8)

    # 계열이 2개 이상일 때만 범례를 둔다. 1개면 제목이 이미 이름을 말해 준다.
    if len(series.labels) > 1:
        legend = ax.legend(loc="upper left", frameon=False, fontsize=9,
                           handlelength=1.6, borderpad=0.2)
        for text in legend.get_texts():
            text.set_color(theme().ink_soft)

    if standalone:
        canvas.figure.set_layout_engine("tight", pad=1.8)
        canvas.draw_idle()


def draw_age_pyramid(canvas: PlotCanvas, pyramid: AgePyramid, *, ax=None,
                     title: str | None = None, compact: bool = False) -> None:
    """연령대별 남/녀 인구 피라미드 (남자는 왼쪽으로 눕힌 가로 막대)."""
    standalone = ax is None
    if standalone:
        canvas.clear()
        ax = canvas.figure.add_subplot(111)
    ax.set_facecolor(theme().surface)
    ax.grid(True, axis="x", color=theme().grid, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(theme().axis)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=theme().ink_soft, labelsize=8.5, length=0)

    positions = list(range(len(pyramid.bands)))
    ax.barh(positions, [-m for m in pyramid.male], height=0.72,
            color=theme().series[0], label="남자", zorder=3)
    ax.barh(positions, pyramid.female, height=0.72,
            color=theme().series[1], label="여자", zorder=3)

    ax.axvline(0, color=theme().surface, linewidth=2, zorder=4)   # 두 막대 사이 2px 여백
    ax.set_yticks(positions)
    ax.set_yticklabels(pyramid.bands)
    ax.set_xlabel("평균 생활인구(명)", fontsize=9, color=theme().ink_soft, labelpad=6)
    ax.set_ylabel("연령대", fontsize=9, color=theme().ink_soft, labelpad=6)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{abs(v):,.0f}"))

    ax.set_title(title or pyramid.title, fontsize=10.5 if compact else 12,
                 fontweight="bold", color=theme().ink, pad=18 if compact else 30, loc="left")
    if pyramid.note and not compact:
        ax.text(0, 1.045, pyramid.note, transform=ax.transAxes,
                fontsize=8.5, color=theme().ink_soft, va="bottom")

    # 가장 인구가 많은 연령대만 직접 라벨링한다.
    for values, sign, color, name in (
        (pyramid.male, -1, theme().series[0], "남자"),
        (pyramid.female, 1, theme().series[1], "여자"),
    ):
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

    legend = ax.legend(loc="lower right", frameon=False, fontsize=9,
                       handlelength=1.2, borderpad=0.2)
    for text in legend.get_texts():
        text.set_color(theme().ink_soft)

    # 인구 피라미드는 좌우 대칭 축이 기본. 여유폭은 직접 라벨이 들어갈 자리다.
    limit = max(max(pyramid.male, default=0), max(pyramid.female, default=0)) or 1.0
    ax.set_xlim(-limit * 1.5, limit * 1.5)

    if standalone:
        canvas.figure.set_layout_engine("tight", pad=1.8)
        canvas.draw_idle()


def draw_paired_analysis(canvas: PlotCanvas, comparison: PairedAnalysis) -> None:
    """동일한 크기와 공통 축으로 두 지역을 비교한다."""
    canvas.clear()
    axes = canvas.figure.subplots(1, 2, sharex=True, sharey=True)
    caption = comparison.analyses[0].title.removeprefix(comparison.regions[0]).strip()
    canvas.figure.suptitle(f"{caption} · {comparison.note}", fontsize=9, color=theme().ink_soft)
    is_age = isinstance(comparison.analyses[0], AgePyramid)
    for index, (ax, region, result) in enumerate(zip(axes, comparison.regions, comparison.analyses)):
        caption = f"{'AB'[index]} · {region}"
        if is_age:
            draw_age_pyramid(canvas, result, ax=ax, title=caption, compact=True)
        else:
            draw_line_series(canvas, result, ax=ax, title=caption, compact=True,
                             single_color=theme().series[index])
        # 공유 축이어도 양쪽에 같은 눈금과 단위를 표시한다.
        ax.tick_params(labelleft=True)

    if is_age:
        limit = max(max(result.male + result.female, default=0)
                    for result in comparison.analyses) or 1.0
        axes[0].set_xlim(-limit * 1.2, limit * 1.2)
        axes[0].xaxis.set_major_locator(MaxNLocator(nbins=4, symmetric=True))
    else:
        peak = max(max(values) for result in comparison.analyses for values in result.values)
        axes[0].set_ylim(0, (peak or 1.0) * 1.2)

    canvas.figure.set_layout_engine("tight", pad=1.4, w_pad=2.4)
    canvas.draw_idle()
