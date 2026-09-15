"""분석 작업 공간의 공통 위젯. Fluent 내비게이션·전환을 Qt 화면에 통합한다."""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QRectF, QSize, Qt, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout,
    QWidget, QStackedWidget,
)
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from qfluentwidgets import NavigationPushButton, Pivot, SegmentedWidget

from .hotplace import Hotplace, summary_text
from .plotting import PlotCanvas
from .theme import make_icon, theme


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
            item.widget().deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class NavigationItem(NavigationPushButton):
    """Fluent 내비게이션에 키보드 활성화와 한국어 접근성 이름을 더한다."""

    def __init__(self, icon, text: str, parent=None, selectable: bool = True) -> None:
        super().__init__(icon, text, selectable, parent)
        self.setCompacted(False)
        self.setFixedSize(180, 38)
        self.setFont(QApplication.font())
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(text)
        self.setCursor(Qt.PointingHandCursor)
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
        super().paintEvent(event)
        if self.hasFocus() and self._keyboard_focus:
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
    """지역별 카드 대신 동일 지표 안에서 A와 B를 바로 대조한다."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metricsStrip")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.region_a = MetricLabels()
        self.region_b = MetricLabels()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(0)
        for index, (key, title, unit, help_text) in enumerate(METRICS):
            if index:
                layout.addWidget(separator(True))
            cell = QVBoxLayout()
            cell.setContentsMargins(20, 0, 20, 0)
            cell.setSpacing(8)
            heading = label(title, "muted")
            heading.setToolTip(help_text)
            cell.addWidget(heading)
            row = QHBoxLayout()
            row.setSpacing(12)
            for region, holder in (("A", self.region_a), ("B", self.region_b)):
                number_row = QHBoxLayout()
                number_row.setSpacing(6)
                number_row.addWidget(label(region, "regionTag" if region == "A" else "regionTagB"), 0, Qt.AlignBottom)
                value = label("—", "metricValue")
                value.setAccessibleName(f"지역 {region} {title}")
                holder.values[key] = value
                number_row.addWidget(value, 0, Qt.AlignBottom)
                number_row.addWidget(label(unit, "metricUnit"), 0, Qt.AlignBottom)
                number_row.addStretch()
                row.addLayout(number_row, 1)
            cell.addLayout(row)
            layout.addLayout(cell, 1)


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
    """그룹(위 줄)과 그 안의 차트(아래 줄)로 나눈 두 단계 분석 내비게이션.

    차트 번호는 그룹과 상관없이 ``titles`` 순서를 따른다.
    """

    currentChanged = Signal(int)

    def __init__(self, titles: tuple[str, ...], groups: tuple[tuple[str, tuple[int, ...]], ...],
                 parent=None) -> None:
        super().__init__(parent)
        self.segmented = SegmentedWidget(self)
        self.subtabs = QStackedWidget(self)
        self.pivots: list[Pivot] = []
        self.stack = AnimatedStack(self)
        self.pages = [AnalysisTab(self) for _ in titles]
        for page in self.pages:
            self.stack.addWidget(page)
        self._group_of: dict[int, int] = {}
        self._last = [indices[0] for _name, indices in groups]
        for group, (name, indices) in enumerate(groups):
            item = self.segmented.addItem(f"group-{group}", name,
                                          onClick=lambda _checked=False, g=group: self.setCurrentIndex(self._last[g]))
            item.setFont(QApplication.font())
            item.setAccessibleName(f"{name} 차트 묶음")
            pivot = Pivot(self)
            for index in indices:
                tab = pivot.addItem(f"tab-{index}", titles[index],
                                    onClick=lambda _checked=False, i=index: self.setCurrentIndex(i))
                tab.setFont(QApplication.font())
                tab.setAccessibleName(titles[index])
                self._group_of[index] = group
            self.pivots.append(pivot)
            # Pivot 을 그대로 쌓으면 항목이 가로로 퍼지므로 왼쪽에 모아 둔다.
            pivot.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            holder = QWidget(self)
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(pivot)
            row.addStretch()
            self.subtabs.addWidget(holder)
        self.subtabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._select(0)
        self.stack.currentChanged.connect(self._changed)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._layout.addWidget(self.segmented, 0, Qt.AlignLeft)
        self._layout.addWidget(self.subtabs)
        self._layout.addWidget(self.stack, 1)

    def set_header(self, header: QLayout) -> None:
        """탭과 차트 사이에 현재 차트의 제목 줄을 둔다."""
        self._layout.insertLayout(2, header)

    def _select(self, index: int) -> None:
        group = self._group_of[index]
        self._last[group] = index
        self.segmented.setCurrentItem(f"group-{group}")
        self.subtabs.setCurrentIndex(group)
        self.pivots[group].setCurrentItem(f"tab-{index}")

    def _changed(self, index: int) -> None:
        self._select(index)
        if not motion_enabled():
            self.finish_motion()
        self.currentChanged.emit(index)

    def finish_motion(self):
        for bar in (self.segmented, *self.pivots):
            if bar.currentItem() is None:
                continue
            bar.slideAni.stop()
            bar.slideAni.setValue(bar.currentIndicatorGeometry())
            bar.update()

    def currentIndex(self) -> int:
        return self.stack.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
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
    """항목을 행으로, 지역 A·B를 열로 두는 비교표."""

    chartRequested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 8)
        outer.setSpacing(0)
        head = QFrame()
        head.setProperty("role", "tableHead")
        self._head = QGridLayout(head)
        self._head.setContentsMargins(20, 10, 20, 10)
        self.head_labels = [label("항목", "columnHead"), label("지역 A", "regionTag", True), label("지역 B", "regionTagB", True)]
        for column, widget in enumerate(self.head_labels):
            self._head.addWidget(widget, 0, column)
        outer.addWidget(head)
        self._body = QGridLayout()
        self._body.setContentsMargins(20, 0, 20, 0)
        self._body.setHorizontalSpacing(24)
        self._body.setVerticalSpacing(0)
        for grid in (self._head, self._body):
            grid.setHorizontalSpacing(24)
            grid.setColumnStretch(0, 5)
            grid.setColumnStretch(1, 6)
            grid.setColumnStretch(2, 6)
        outer.addLayout(self._body)
        self.empty = label("데이터를 불러오고 지역 비교 화면에서 두 지역을 고르면 표가 채워집니다.", "muted", True)
        self.empty.setContentsMargins(20, 18, 20, 12)
        outer.addWidget(self.empty)

    def set_regions(self, left: str, right: str) -> None:
        self.head_labels[1].setText(f"A · {left}")
        self.head_labels[2].setText(f"B · {right}")

    def set_rows(self, rows) -> None:
        """rows: (항목, 설명, 차트 탭 번호 또는 None, (A 값, A 보충), (B 값, B 보충))."""
        clear_layout(self._body)
        self.empty.setVisible(not rows)
        for index, (name, definition, chart, *cells) in enumerate(rows):
            line = index * 2
            if index:
                self._body.addWidget(separator(), line - 1, 0, 1, 3)
            heading = QVBoxLayout()
            heading.setContentsMargins(0, 14, 0, 14)
            heading.setSpacing(3)
            heading.addWidget(label(name, "field"))
            heading.addWidget(label(definition, "caption", True))
            if chart is not None:
                link = label(f'<a href="{chart}" style="color: {theme().ink}; text-decoration: none;">'
                             "차트에서 보기 ›</a>", "caption")
                link.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
                link.setCursor(Qt.PointingHandCursor)
                link.linkActivated.connect(lambda href: self.chartRequested.emit(int(href)))
                heading.addSpacing(4)
                heading.addWidget(link, 0, Qt.AlignLeft)
            heading.addStretch()
            self._body.addLayout(heading, line, 0)
            for column, (value, detail) in enumerate(cells, start=1):
                cell = QVBoxLayout()
                cell.setContentsMargins(0, 14, 0, 14)
                cell.setSpacing(3)
                cell.addWidget(label(value, "cellValue", True))
                if detail:
                    cell.addWidget(label(detail, "muted", True))
                cell.addStretch()
                self._body.addLayout(cell, line, column)
