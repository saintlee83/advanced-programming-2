"""상단 메뉴, 세로 지표, 차트 선택기, 항목별 비교 카드."""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QRectF, QSize, Qt, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout,
    QWidget, QStackedWidget,
)
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from qfluentwidgets import ComboBox, NavigationPushButton

from .hotplace import Hotplace, summary_text
from .plotting import PlotCanvas
from .theme import DARK, LIGHT, make_icon, theme


def motion_enabled() -> bool:
    app = QApplication.instance()
    return os.environ.get("HOTPLACE_REDUCED_MOTION") != "1" and not (app and app.property("reducedMotion"))


class TransitionOverlay(QWidget):
    """Fade and translate a snapshot, leaving the live destination fully interactive."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.pixmap = None
        self.progress = 0.0
        self.direction = 1
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self._step)
        self.animation.finished.connect(self.hide)
        self.hide()

    def _step(self, value):
        self.progress = value
        self.update()

    def paintEvent(self, event):
        if self.pixmap is None:
            return
        painter = QPainter(self)
        painter.setOpacity(1 - self.progress)
        painter.drawPixmap(int(-self.direction * 24 * self.progress), 0, self.pixmap)
        painter.end()


class AnimatedStack(QStackedWidget):
    """Interruptible page transitions. Selection state changes synchronously."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlay = TransitionOverlay(self)

    def addWidget(self, widget, **_kwargs):
        return super().addWidget(widget)

    def setCurrentIndex(self, index, duration=240):
        if index == self.currentIndex() or not 0 <= index < self.count():
            return
        self.overlay.animation.stop()
        self.overlay.hide()
        old = self.currentIndex()
        snapshot = self.grab() if self.isVisible() and motion_enabled() else None
        super().setCurrentIndex(index)
        if snapshot is not None:
            self.overlay.pixmap = snapshot
            self.overlay.direction = 1 if index > old else -1
            self.overlay.progress = 0
            self.overlay.setGeometry(self.rect())
            self.overlay.show()
            self.overlay.raise_()
            self.overlay.animation.setDuration(duration)
            self.overlay.animation.start()

    def stop_transition(self):
        self.overlay.animation.stop()
        self.overlay.hide()
        self.update()

    def resizeEvent(self, event):
        self.stop_transition()
        super().resizeEvent(event)


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
    badge.setFixedSize(26, 26)
    badge.setAlignment(Qt.AlignCenter)
    badge.setAccessibleName(region)
    return badge


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class NavigationItem(NavigationPushButton):
    """상단 내비게이션. 마우스와 키보드 활성화를 모두 지원한다."""

    def __init__(self, icon, text: str, parent=None, selectable: bool = True) -> None:
        super().__init__(icon, text, selectable, parent)
        self.setCompacted(False)
        self.setFixedSize(146, 38)
        self.setFont(QApplication.font())
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setTextColor(LIGHT.ink, DARK.ink)
        self.setIndicatorColor(LIGHT.accent, DARK.accent)
        self._keyboard_focus = False

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setAccessibleName(text)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.click()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        # 창이 열릴 때 생기는 포커스에는 테두리를 그리지 않는다. 키보드로 이동할 때만 표시한다.
        self._keyboard_focus = event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._keyboard_focus = False
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:
        t = theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        elif self.isPressed:
            painter.setOpacity(0.8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(t.accent_soft if self.isSelected else t.hover if self.isEnter else t.background))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)
        ink = t.ink
        icon = self.icon()
        icon.paint(painter, 14, 10, 18, 18, Qt.AlignCenter, QIcon.Normal)
        font = self.font()
        font.setBold(self.isSelected)
        painter.setFont(font)
        painter.setPen(QColor(ink))
        painter.drawText(QRectF(40, 0, self.width() - 48, self.height()), Qt.AlignVCenter, self.text())
        if self.hasFocus() and self._keyboard_focus:
            painter.setPen(QPen(QColor(t.ink), 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(3, 3, -3, -3), 4, 4)
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
        self.values["peak_hour"].setText(f"{stats['peak_hour']}")
        for key in ("day_night_ratio", "weekend_ratio"):
            value = stats[key]
            self.values[key].setText(f"{value:.2f}" if math.isfinite(value) else "—")
        for value in self.values.values():
            value.setToolTip(summary_text(place))


METRICS = (
    ("daily_avg", "일평균 생활인구", "명", "시간대별 평균 인구의 평균입니다. 하루 방문자 수가 아닙니다."),
    ("peak_hour", "가장 붐비는 시간", "시", "평균 인구가 가장 많은 시간대입니다."),
    ("day_night_ratio", "낮 ÷ 밤 인구", "배", "낮(09~18시) 평균 ÷ 밤(00~06시) 평균. 1보다 크면 낮에 사람이 더 많습니다."),
    ("weekend_ratio", "주말 ÷ 평일 인구", "배", "주말 평균 ÷ 평일 평균. 1보다 작으면 평일에 더 붐빕니다."),
)


class ComparisonMetrics(QFrame):
    """지역 선택 아래에 놓는 세로 지표 카드 네 장."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metricsStrip")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.region_a = MetricLabels()
        self.region_b = MetricLabels()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        for index, (key, title, unit, help_text) in enumerate(METRICS):
            card = QFrame()
            card.setProperty("role", "metricCard")
            cell = QVBoxLayout(card)
            cell.setContentsMargins(14, 10, 14, 10)
            cell.setSpacing(6)
            heading = label(title, "field")
            heading.setToolTip(help_text)
            cell.addWidget(heading)
            row = QHBoxLayout()
            row.setSpacing(8)
            for region, holder in (("A", self.region_a), ("B", self.region_b)):
                number_row = QHBoxLayout()
                number_row.setSpacing(4)
                number_row.addWidget(label(region, "regionTag" if region == "A" else "regionTagB"), 0, Qt.AlignBottom)
                value = label("—", "metricValue")
                value.setAccessibleName(f"지역 {region} {title}")
                holder.values[key] = value
                number_row.addWidget(value, 0, Qt.AlignBottom)
                number_row.addWidget(label(unit, "metricUnit"), 0, Qt.AlignBottom)
                number_row.addStretch()
                row.addLayout(number_row, 1)
            cell.addLayout(row)
            layout.addWidget(card)


class AnalysisToolbar(NavigationToolbar2QT):
    """분석에 필요한 탐색 도구만 표시한다. 저장은 화면의 내보내기 버튼에서 한다."""

    toolitems = (
        ("처음 범위", "처음 범위로 되돌리기", "home", "home"),
        ("뒤로", "이전 범위", "back", "back"),
        ("앞으로", "다음 범위", "forward", "forward"),
        ("이동", "드래그해서 두 차트를 함께 이동", "move", "pan"),
        ("확대", "영역을 드래그해서 두 차트를 함께 확대", "zoom_to_rect", "zoom"),
    )


READOUT_HINT = "차트 위에 마우스를 올리면 두 지역의 값이 여기에 표시됩니다."


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

    currentChanged = Signal(int)

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
        self.stack = AnimatedStack(self)
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
        if not motion_enabled():
            self.finish_motion()
        self.currentChanged.emit(index)

    def finish_motion(self):
        self.stack.stop_transition()

    def currentIndex(self):
        return self.stack.currentIndex()

    def setCurrentIndex(self, index):
        self.stack.setCurrentIndex(index, duration=220)


def stat_cell(caption: str) -> tuple[QVBoxLayout, QLabel, QLabel]:
    """작은 제목 · 큰 값 · 보조 설명 한 묶음."""
    cell = QVBoxLayout()
    cell.setSpacing(4)
    cell.addWidget(label(caption, "muted"))
    value = label("—", "statValue")
    note = label("", "caption", True)
    cell.addWidget(value)
    cell.addWidget(note)
    return cell, value, note


class ComparisonTable(QFrame):
    """항목별로 A/B 결과를 나란히 표시하는 비교 카드."""

    chartRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("observationNotes")
        self._regions = ("지역 A", "지역 B")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        self._body = QVBoxLayout()
        self._body.setSpacing(14)
        outer.addLayout(self._body)
        self.empty = label("데이터를 불러오고 두 지역을 선택하면 비교 결과가 표시됩니다.", "notice", True)
        outer.addWidget(self.empty)

    def set_regions(self, left, right):
        self._regions = (left, right)

    def set_rows(self, rows):
        clear_layout(self._body)
        self.empty.setVisible(not rows)
        for index, (name, definition, chart, *cells) in enumerate(rows):
            card = QFrame()
            card.setProperty("role", "noteCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(20, 18, 20, 18)
            layout.setSpacing(12)
            heading = QHBoxLayout()
            heading.addWidget(label(name, "section"), 1)
            if chart is not None:
                link = label(f'<a href="{chart}" style="color: {theme().ink};">차트 보기</a>', "caption")
                link.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
                link.linkActivated.connect(lambda href: self.chartRequested.emit(int(href)))
                heading.addWidget(link)
            layout.addLayout(heading)
            layout.addWidget(label(definition, "caption", True))
            values = QHBoxLayout()
            values.setSpacing(12)
            for column, (value, detail) in enumerate(cells):
                panel = QFrame()
                panel.setProperty("role", "noteA" if column == 0 else "noteB")
                cell = QVBoxLayout(panel)
                cell.setContentsMargins(14, 12, 14, 12)
                cell.setSpacing(6)
                cell.addWidget(label(f"{'AB'[column]} · {self._regions[column]}", "regionTag" if column == 0 else "regionTagB", True))
                cell.addWidget(label(value, "cellValue", True))
                if detail:
                    cell.addWidget(label(detail, "muted", True))
                cell.addStretch()
                values.addWidget(panel, 1)
            layout.addLayout(values)
            self._body.addWidget(card)
