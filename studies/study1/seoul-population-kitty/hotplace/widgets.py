"""지표 비교표, 차트 선택기, 차트 한 장을 담는 화면 부품."""

from __future__ import annotations

import math

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QStackedWidget,
    QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from qfluentwidgets import ComboBox as FluentComboBox, MenuAnimationType
from qfluentwidgets.components.widgets.combo_box import ComboBoxMenu

from .hotplace import Hotplace, summary_text
from .plotting import HOVER_ENABLED, PlotCanvas
from .theme import make_icon


class _ComboMenu(ComboBoxMenu):
    """콤보 상자의 목록. 펼쳐지는 애니메이션을 건너뛰고 바로 제자리에 표시한다."""

    def exec(self, pos, ani=True, aniType=MenuAnimationType.DROP_DOWN):
        super().exec(pos, ani, aniType)
        animation = self.aniManager.ani
        animation.setCurrentTime(animation.duration())


class ComboBox(FluentComboBox):
    """Fluent 콤보 상자. 모양은 그대로 두고 목록의 펼침 애니메이션만 끈다."""

    def _createComboMenu(self):
        return _ComboMenu(self)


def label(text: str, role: str, wrap: bool = False) -> QLabel:
    result = QLabel(text)
    result.setProperty("role", role)
    result.setWordWrap(wrap)
    return result


def region_badge(region: str) -> QLabel:
    badge = label(region[-1], "regionBadgeB" if region.endswith("B") else "regionBadge")
    badge.setFixedSize(26, 26)
    badge.setAlignment(Qt.AlignCenter)
    badge.setAccessibleName(region)
    return badge


# (요약 통계의 키, 표에 보일 이름, 값 표기, 마우스를 올렸을 때의 설명)
METRICS = (
    ("daily_avg", "일평균 생활인구", "{:,.0f}명", "시간대별 평균 인구의 평균입니다. 하루 방문자 수가 아닙니다."),
    ("peak_hour", "가장 붐비는 시간", "{}시", "평균 인구가 가장 많은 시간대입니다."),
    ("day_night_ratio", "낮 ÷ 밤 인구", "{:.2f}배", "낮(09~18시) 평균 ÷ 밤(00~06시) 평균. 1보다 크면 낮에 사람이 더 많습니다."),
    ("weekend_ratio", "주말 ÷ 평일 인구", "{:.2f}배", "주말 평균 ÷ 평일 평균. 1보다 작으면 평일에 더 붐빕니다."),
)


class MetricLabels:
    """비교표에서 한 지역(한 칸)의 값들을 함께 갱신한다."""

    def __init__(self) -> None:
        self.values: dict[str, QLabel] = {}

    def update_place(self, place: Hotplace | None) -> None:
        stats = place.summary() if place else {}
        for key, _title, pattern, _help in METRICS:
            number = stats.get(key, math.nan)
            self.values[key].setText(pattern.format(number) if math.isfinite(number) else "—")
            self.values[key].setToolTip(summary_text(place) if place else "")


class ComparisonMetrics(QFrame):
    """지역 선택 아래에 놓는 비교표. 줄은 지표, 칸은 지역 A·B 다."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metricsTable")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.region_a = MetricLabels()
        self.region_b = MetricLabels()
        grid = QGridLayout(self)
        grid.setContentsMargins(14, 10, 14, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(0, 1)
        grid.setRowMinimumHeight(0, 36)
        for column, region in enumerate("AB", start=1):           # 머리 줄: 지역 선택과 같은 A·B 표시
            grid.addWidget(region_badge(region), 0, column, Qt.AlignRight | Qt.AlignVCenter)
            grid.setColumnMinimumWidth(column, 70)                # 값이 바뀌어도 두 칸의 너비가 같게 유지된다
        for index, (key, title, _pattern, help_text) in enumerate(METRICS):
            row = index * 2 + 1                                    # 구분선 한 줄 + 지표 한 줄
            line = QFrame()
            line.setProperty("role", "separator")
            line.setFixedHeight(1)
            grid.addWidget(line, row, 0, 1, 3)
            name = label(title, "muted")
            name.setToolTip(help_text)
            grid.addWidget(name, row + 1, 0)
            grid.setRowMinimumHeight(row + 1, 38)
            for column, (region, holder) in enumerate((("A", self.region_a), ("B", self.region_b)), start=1):
                value = label("—", "metricValue")
                value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)   # 숫자는 오른쪽 맞춤이라야 자릿수가 비교된다
                value.setAccessibleName(f"지역 {region} {title}")
                holder.values[key] = value
                grid.addWidget(value, row + 1, column)


class AnalysisToolbar(NavigationToolbar2QT):
    """분석에 필요한 탐색 도구만 표시한다. 저장은 화면의 내보내기 버튼에서 한다."""

    toolitems = (
        ("처음 범위", "처음 범위로 되돌리기", "home", "home"),
        ("뒤로", "이전 범위", "back", "back"),
        ("앞으로", "다음 범위", "forward", "forward"),
        ("이동", "드래그해서 두 차트를 함께 이동", "move", "pan"),
        ("확대", "영역을 드래그해서 두 차트를 함께 확대", "zoom_to_rect", "zoom"),
    )


READOUT_HINT = "차트 위에 마우스를 올리면 두 지역의 값이 여기에 표시됩니다." if HOVER_ENABLED else ""


class AnalysisTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setBackgroundRole(QPalette.Base)
        self.setAutoFillBackground(True)
        self.canvas = PlotCanvas(self)
        self.toolbar = AnalysisToolbar(self.canvas, self)
        self.toolbar.setIconSize(QSize(15, 15))
        self.toolbar.setMinimumHeight(32)
        self.toolbar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.toolbar.coordinates = False
        # 좌표 대신 생활인구 수치를 읽는 한국어 안내를 표시한다.
        if hasattr(self.toolbar, "locLabel"):
            self.toolbar.locLabel.hide()
        self.readout = label(READOUT_HINT, "caption")
        self.readout.setObjectName("chartReadout")
        self.readout.setWordWrap(True)
        self.readout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.readout.setFixedHeight(32)
        self.canvas.hovered.connect(self._show_readout)
        controls = QHBoxLayout()
        controls.setContentsMargins(6, 4, 6, 0)
        controls.addWidget(self.toolbar)
        controls.addWidget(self.readout, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(controls)
        self.toolbar.hide()
        self.hint = READOUT_HINT

    def _show_readout(self, text: str) -> None:
        self.readout.setText(text or self.hint)

    def refresh_icons(self) -> None:
        icons = {
            "home": "home", "back": "back", "forward": "arrow", "pan": "pan",
            "zoom": "zoom", "configure_subplots": "settings",
            "edit_parameters": "chart", "save_figure": "download",
        }
        for callback, icon in icons.items():
            if callback in self.toolbar._actions:
                self.toolbar._actions[callback].setIcon(make_icon(icon))


class AnalysisTabs(QWidget):
    """분석 분류와 차트 선택기를 갖춘 비교 패널."""

    currentChanged = pyqtSignal(int)

    def __init__(self, titles, groups, parent=None):
        super().__init__(parent)
        self._titles, self._groups = titles, groups
        self._last = [indices[0] for _name, indices in groups]
        self._group_of = {index: group for group, (_name, indices) in enumerate(groups) for index in indices}
        self.group_picker, self.chart_picker = ComboBox(), ComboBox()
        self.group_picker.setAccessibleName("분석 분류")
        self.chart_picker.setAccessibleName("차트")
        for group, (name, _indices) in enumerate(groups):
            self.group_picker.addItem(name, userData=group)
        for picker in (self.group_picker, self.chart_picker):
            picker.setFont(QApplication.font())
            picker.setMinimumHeight(38)
            picker.setMinimumWidth(146)
        self.group_picker.currentIndexChanged.connect(self._choose_group)
        self.chart_picker.currentIndexChanged.connect(self._choose_chart)
        self.stack = QStackedWidget(self)
        self.pages = [AnalysisTab(self) for _ in titles]
        for page in self.pages:
            self.stack.addWidget(page)
        self.stack.currentChanged.connect(self._changed)
        controls = QFrame()
        controls.setProperty("role", "chartControls")
        row = QHBoxLayout(controls)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        row.addWidget(label("분석 분류", "field"))
        row.addWidget(self.group_picker, 1)
        row.addWidget(label("차트", "field"))
        row.addWidget(self.chart_picker, 1)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(14)
        self._layout.addWidget(controls)
        self._layout.addWidget(self.stack, 1)
        self._select(0)

    def set_header(self, header):
        self._layout.insertLayout(0, header)

    def _choose_group(self, group):
        if group >= 0:
            self.setCurrentIndex(self._last[group])

    def _choose_chart(self, _row):
        index = self.chart_picker.currentData()
        if index is not None:
            self.setCurrentIndex(index)

    def _select(self, index):
        group = self._group_of[index]
        self._last[group] = index
        self.group_picker.blockSignals(True)
        self.chart_picker.blockSignals(True)
        self.group_picker.setCurrentIndex(group)
        self.chart_picker.clear()
        for chart in self._groups[group][1]:
            self.chart_picker.addItem(self._titles[chart], userData=chart)
        self.chart_picker.setCurrentIndex(self.chart_picker.findData(index))
        self.group_picker.blockSignals(False)
        self.chart_picker.blockSignals(False)

    def _changed(self, index):
        self._select(index)
        self.currentChanged.emit(index)

    def currentIndex(self):
        return self.stack.currentIndex()

    def setCurrentIndex(self, index):
        if index in self._group_of:                   # 선택 목록에 없는(비활성화한) 차트는 열지 않는다
            self.stack.setCurrentIndex(index)
