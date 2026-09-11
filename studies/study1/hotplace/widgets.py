"""분석 작업 공간의 공통 위젯. Fluent 내비게이션·전환을 Qt 화면에 통합한다."""

from __future__ import annotations

import math

from PyQt5.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PyQt5.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from qfluentwidgets import NavigationPushButton, PopUpAniStackedWidget, SegmentedWidget

from .hotplace import Hotplace, summary_text
from .plotting import PlotCanvas
from .theme import make_icon, theme


def label(text: str, role: str, wrap: bool = False) -> QLabel:
    result = QLabel(text)
    result.setProperty("role", role)
    result.setWordWrap(wrap)
    return result


def separator(vertical: bool = False) -> QFrame:
    line = QFrame()
    line.setProperty("role", "separator")
    if vertical:
        line.setFixedWidth(1)
    else:
        line.setFixedHeight(1)
    return line


def region_badge(region: str) -> QLabel:
    badge = label(region[-1], "regionBadgeB" if region.endswith("B") else "regionBadge")
    badge.setFixedSize(28, 28)
    badge.setAlignment(Qt.AlignCenter)
    badge.setAccessibleName(region)
    return badge


class NavigationItem(NavigationPushButton):
    """Fluent 내비게이션에 키보드 활성화와 한국어 접근성 이름을 더한다."""

    def __init__(self, icon, text: str, parent=None) -> None:
        super().__init__(icon, text, True, parent)
        self.setCompacted(False)
        self.setFixedSize(172, 42)
        self.setFont(QApplication.font())
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(text)
        self.setCursor(Qt.PointingHandCursor)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.click()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.hasFocus():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor(theme().accent), 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)
            painter.end()


class MetricLabels:
    """각 지표 안에 배치된 한 지역의 값을 함께 갱신한다."""

    def __init__(self) -> None:
        self.values: dict[str, QLabel] = {}

    def update_place(self, place: Hotplace | None) -> None:
        if place is None:
            for value in self.values.values():
                value.setText("—")
            return
        stats = place.summary()
        self.values["daily_avg"].setText(f"{stats['daily_avg']:,.0f}")
        self.values["peak_hour"].setText(f"{stats['peak_hour']:02d}")
        for key in ("day_night_ratio", "weekend_ratio"):
            value = stats[key]
            self.values[key].setText(f"{value:.2f}" if math.isfinite(value) else "—")
        for value in self.values.values():
            value.setToolTip(summary_text(place))


class ComparisonMetrics(QFrame):
    """지역별 카드 대신 동일 지표 안에서 A와 B를 바로 대조한다."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metricsStrip")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.region_a = MetricLabels()
        self.region_b = MetricLabels()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 18, 0, 18)
        layout.setSpacing(0)
        for index, (key, title, unit) in enumerate((
            ("daily_avg", "일평균 생활인구", "명"),
            ("peak_hour", "가장 붐비는 시간", "시"),
            ("day_night_ratio", "주간 / 야간 인구", "배"),
            ("weekend_ratio", "주말 / 평일 인구", "배"),
        )):
            if index:
                layout.addWidget(separator(True))
            cell = QVBoxLayout()
            cell.setContentsMargins(20, 0, 20, 0)
            cell.setSpacing(10)
            cell.addWidget(label(title, "muted"))
            row = QHBoxLayout()
            row.setSpacing(16)
            for region, holder in (("A", self.region_a), ("B", self.region_b)):
                column = QVBoxLayout()
                column.setSpacing(3)
                column.addWidget(label(region, "regionTag" if region == "A" else "regionTagB"))
                number_row = QHBoxLayout()
                number_row.setSpacing(4)
                value = label("—", "metricValue")
                holder.values[key] = value
                number_row.addWidget(value)
                number_row.addWidget(label(unit, "metricUnit"), 0, Qt.AlignBottom)
                number_row.addStretch()
                column.addLayout(number_row)
                row.addLayout(column, 1)
            cell.addLayout(row)
            layout.addLayout(cell, 1)


class AnalysisToolbar(NavigationToolbar2QT):
    """분석에 필요한 탐색 도구만 표시한다. 저장은 화면의 내보내기 버튼에서 한다."""

    toolitems = (
        ("초기화", "차트의 원래 범위로 돌아가기", "home", "home"),
        ("이전", "이전 차트 범위", "back", "back"),
        ("다음", "다음 차트 범위", "forward", "forward"),
        ("이동", "드래그하여 두 차트를 함께 이동", "move", "pan"),
        ("확대", "영역을 선택하여 두 차트를 함께 확대", "zoom_to_rect", "zoom"),
    )


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
        self.readout = label("차트에 마우스를 올려 시간대별 수치를 확인하세요.", "caption")
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

    def _show_readout(self, text: str) -> None:
        self.readout.setText(text or "차트에 마우스를 올려 시간대별 수치를 확인하세요.")

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
    """이동하는 선택 표시와 짧은 페이지 전환을 갖는 분석 내비게이션."""

    currentChanged = pyqtSignal(int)

    def __init__(self, titles: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self.segmented = SegmentedWidget(self)
        self.stack = PopUpAniStackedWidget(self)
        self.pages = []
        for index, title in enumerate(titles):
            item = self.segmented.addItem(str(index), title, onClick=lambda _checked=False, i=index: self.setCurrentIndex(i))
            item.setFont(QApplication.font())
            item.setAccessibleName(title)
            page = AnalysisTab(self)
            self.pages.append(page)
            self.stack.addWidget(page, deltaY=14)
        self.segmented.setCurrentItem("0")
        self.stack.currentChanged.connect(self._changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self.segmented, 0, Qt.AlignLeft)
        layout.addWidget(self.stack, 1)

    def _changed(self, index: int) -> None:
        self.segmented.setCurrentItem(str(index))
        self.currentChanged.emit(index)

    def currentIndex(self) -> int:
        return self.stack.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        self.stack.setCurrentIndex(index, duration=180)


class CityIllustration(QWidget):
    """첫 실행 안내용 벡터 일러스트. 분석 결과를 흉내내지 않는다."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(420, 200)

    def paintEvent(self, event) -> None:
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.accent_soft))
        p.drawEllipse(QRectF(105, 7, 210, 175))
        # 두 지역을 연결하는 점선 경로와 건물 실루엣.
        p.setPen(QPen(QColor(t.accent), 1.5, Qt.DashLine))
        path = QPainterPath()
        path.moveTo(80, 148)
        path.cubicTo(130, 50, 290, 210, 345, 65)
        p.drawPath(path)
        for x, y, width, height, color in (
            (103, 89, 48, 81, t.series[0]), (156, 48, 59, 122, t.series[0]),
            (249, 103, 42, 67, t.series[1]), (296, 75, 40, 95, t.series[1]),
        ):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, y, width, height), 5, 5)
            p.setBrush(QColor(t.surface))
            for dx in range(10, width - 6, 15):
                for dy in range(12, height - 8, 18):
                    p.drawRoundedRect(QRectF(x + dx, y + dy, 5, 7), 1, 1)
        p.setPen(QPen(QColor(t.border), 1))
        p.drawLine(65, 171, 357, 171)
        p.end()
