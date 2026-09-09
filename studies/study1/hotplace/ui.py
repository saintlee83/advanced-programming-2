"""PyQt5 화면 구성.

두 개의 CSV 파일을 입력받아 → 행정동을 고르고 → 분석 1~5를 탭으로 보여준다.
무거운 CSV 읽기는 별도 스레드에서 돌려 화면이 멈추지 않게 했다.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

from PyQt5.QtCore import QObject, QSize, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPalette
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from .dataset import (
    CodeBook, DataError, Dong, Population, default_data_dir,
    find_population_csv, load_population,
)
from .hotplace import Hotplace, LineSeries, PairedAnalysis, rank_by_daily_average, summary_text
from .plotting import PlotCanvas, draw_line_series, draw_paired_analysis, set_theme, theme
from .theme import DARK, apply_theme, make_icon

TAB_TITLES = (
    "시간대별 추이",
    "평일 · 주말",
    "성별 분포",
    "추이 겹쳐보기",
    "연령별 분포",
)
OVERLAY_TAB = 3


def _label(text: str, role: str, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", role)
    label.setWordWrap(wrap)
    return label


def _separator() -> QFrame:
    line = QFrame()
    line.setProperty("role", "separator")
    line.setFixedHeight(1)
    return line


def _mono_font(point_size: int = 11) -> QFont:
    """숫자를 세로로 맞춰 읽기 위한 고정폭 폰트."""
    font = QFont()
    font.setStyleHint(QFont.Monospace)
    font.setFamily("Menlo")
    font.setPointSize(point_size)
    return font


# ── 백그라운드 로딩 ───────────────────────────────────────────────────
class LoadWorker(QObject):
    """CSV 읽기를 담당하는 워커. QThread 로 옮겨서 실행한다."""

    progress = pyqtSignal(int, str)
    loaded = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(self, population_csv: str, code_csv: str) -> None:
        super().__init__()
        self._population_csv = population_csv
        self._code_csv = code_csv

    def run(self) -> None:
        try:
            population, codebook = load_population(
                self._population_csv,
                self._code_csv,
                progress=lambda pct, msg: self.progress.emit(pct, msg),
            )
        except DataError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:                      # 예상 못 한 오류도 화면으로
            self.failed.emit(f"데이터를 읽는 중 오류가 발생했습니다: {exc}")
        else:
            self.loaded.emit(population, codebook)


# ── 보조 대화상자 ─────────────────────────────────────────────────────
class DongPickDialog(QDialog):
    """같은 이름의 행정동이 여러 곳일 때 하나를 고르게 한다."""

    def __init__(self, dongs: list[Dong], parent=None, title="행정동 선택") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(440, 340)
        self._dongs = dongs

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(QLabel("같은 이름의 행정동이 여러 곳입니다. 하나를 고르세요."))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        for dong in dongs:
            self.list.addItem(QListWidgetItem(f"{dong.sigungu}  {dong.name}  ({dong.code})"))
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("선택")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self) -> Dong | None:
        row = self.list.currentRow()
        return self._dongs[row] if 0 <= row < len(self._dongs) else None


class TopDongDialog(QDialog):
    """일평균 생활인구가 많은 행정동 목록. 핫플레이스 후보를 훑어볼 때 쓴다."""

    def __init__(self, ranking: list[tuple[Dong, float]], parent=None, target="지역 A") -> None:
        super().__init__(parent)
        self.setWindowTitle("생활인구 상위 행정동")
        self.resize(520, 580)
        self._ranking = ranking

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(_label("생활인구 TOP 20", "heading"))
        layout.addWidget(_label(f"일평균 생활인구 기준 · 더블클릭하면 {target}로 선택됩니다.", "muted"))
        self.list = QListWidget()
        for rank, (dong, value) in enumerate(ranking, start=1):
            self.list.addItem(f"{rank:02d}    {dong.label}     {value:,.0f} 명")
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(f"{target}로 선택")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self) -> Dong | None:
        row = self.list.currentRow()
        return self._ranking[row][0] if 0 <= row < len(self._ranking) else None


class RegionSelector(QWidget):
    """자치구 + 행정동 콤보 한 쌍."""

    changed = pyqtSignal()

    def __init__(self, caption: str, parent=None) -> None:
        super().__init__(parent)
        self._codebook: CodeBook | None = None
        self._population: Population | None = None
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label = _label(caption, "regionTagB" if "B" in caption else "regionTag")
        self.sigungu = QComboBox()
        self.sigungu.setAccessibleName(f"{caption} 자치구")
        self.dong = QComboBox()
        self.dong.setAccessibleName(f"{caption} 행정동")
        self.sigungu.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.dong.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.sigungu, 1)
        row.addWidget(self.dong, 1)
        layout.addWidget(label)
        layout.addLayout(row)

        self.sigungu.currentIndexChanged.connect(self._on_sigungu_changed)
        self.dong.currentIndexChanged.connect(self._on_dong_changed)
        self.setEnabled(False)

    def populate(self, codebook: CodeBook, population: Population) -> None:
        self._codebook = codebook
        self._population = population
        self._loading = True
        self.sigungu.clear()
        self.sigungu.addItems(codebook.sigungu_list())
        self._loading = False
        self.setEnabled(True)
        self._on_sigungu_changed()

    def _on_sigungu_changed(self, *_args) -> None:
        if self._loading or self._codebook is None or self._population is None:
            return
        sigungu = self.sigungu.currentText()
        if not sigungu:
            return
        self._loading = True
        self.dong.clear()
        for dong in self._codebook.in_sigungu(sigungu):
            if self._population.has(dong.code):       # 인구 데이터에 있는 동만
                self.dong.addItem(dong.name, dong)
        self._loading = False
        self._on_dong_changed()

    def _on_dong_changed(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()

    def current(self) -> Dong | None:
        return self.dong.currentData()

    def set_dong(self, dong: Dong) -> None:
        """코드로 지정한 행정동에 콤보를 맞춘다."""
        index = self.sigungu.findText(dong.sigungu)
        if index < 0:
            return
        if index != self.sigungu.currentIndex():
            self.sigungu.setCurrentIndex(index)       # _on_sigungu_changed 가 목록을 새로 채운다
        target = self.dong.findData(dong)
        if target < 0:
            target = self.dong.findText(dong.name)
        if target >= 0:
            self.dong.setCurrentIndex(target)


class AnalysisTab(QWidget):
    """그래프 하나를 담는 탭 (캔버스 + 확대/저장 도구모음)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.canvas = PlotCanvas(self)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setMinimumHeight(32)
        self.toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toolbar.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.toolbar)

    def refresh_icons(self) -> None:
        # matplotlib 도구모음 아이콘도 현재 팔레트에 맞춰 다시 생성한다.
        for _text, _tooltip, image, callback in self.toolbar.toolitems:
            if image and callback in self.toolbar._actions:
                self.toolbar._actions[callback].setIcon(self.toolbar._icon(f"{image}.png"))


class RegionMetricsCard(QFrame):
    """A와 B에 동일한 크기, 지표, 글자 크기를 적용하는 요약 카드."""

    def __init__(self, region: str) -> None:
        super().__init__()
        self.setProperty("role", "metric")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        row = QHBoxLayout()
        row.addWidget(_label(region, "regionTagB" if region == "지역 B" else "regionTag"))
        self.name = _label("행정동 선택 전", "section")
        row.addWidget(self.name)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(_separator())
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        self.values: dict[str, QLabel] = {}
        for index, (key, title, unit) in enumerate((
            ("daily_avg", "일평균 생활인구", "명"),
            ("peak_hour", "가장 붐비는 시간", "시"),
            ("day_night_ratio", "주간 / 야간 인구", "배"),
            ("weekend_ratio", "주말 / 평일 인구", "배"),
        )):
            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.addWidget(_label(title, "muted"))
            numbers = QHBoxLayout()
            numbers.setSpacing(5)
            value = _label("—", "comparisonValue")
            self.values[key] = value
            numbers.addWidget(value)
            numbers.addWidget(_label(unit, "metricUnit"), 0, Qt.AlignBottom)
            numbers.addStretch()
            cell.addLayout(numbers)
            grid.addLayout(cell, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

    def update_place(self, place: Hotplace | None) -> None:
        self.name.setText(place.label if place else "행정동 선택 전")
        if place is None:
            for value in self.values.values():
                value.setText("—")
            self.setToolTip("")
            return
        summary = place.summary()
        self.values["daily_avg"].setText(f"{summary['daily_avg']:,.0f}")
        self.values["peak_hour"].setText(f"{summary['peak_hour']:02d}")
        for key in ("day_night_ratio", "weekend_ratio"):
            number = summary[key]
            self.values[key].setText(f"{number:.2f}" if math.isfinite(number) else "—")
        self.setToolTip(summary_text(place))


class InsightCard(QFrame):
    def __init__(self, region: str) -> None:
        super().__init__()
        self.setProperty("role", "insight")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(5)
        row = QHBoxLayout()
        row.addWidget(_label(region, "regionTagB" if "B" in region else "regionTag"))
        self.name = _label("행정동 선택 전", "field")
        row.addWidget(self.name)
        row.addStretch()
        layout.addLayout(row)
        self.character = _label("지역을 선택하면 생활인구 패턴을 요약합니다.", "muted", True)
        layout.addWidget(self.character)

    def update_place(self, place: Hotplace | None) -> None:
        if place is None:
            self.name.setText("행정동 선택 전")
            self.character.setText("지역을 선택하면 생활인구 패턴을 요약합니다.")
            return
        summary = place.summary()
        self.name.setText(place.label)
        self.character.setText(str(summary["character"]))
        self.setToolTip(summary_text(place))


# ── 메인 윈도우 ───────────────────────────────────────────────────────
class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.population: Population | None = None
        self.codebook: CodeBook | None = None
        self._thread: QThread | None = None
        self._worker: LoadWorker | None = None
        self._results: dict[int, LineSeries | PairedAnalysis] = {}

        self._build_ui()
        self._prefill_paths()

    # ── 화면 구성 ────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.setObjectName("mainWindow")
        self.setWindowTitle("서울 생활인구 분석기 — Hotplace Analyzer")
        self.resize(1440, 960)
        self.setMinimumSize(1080, 740)
        self._icon_buttons: list[tuple[QPushButton, str, bool]] = []
        apply_theme(QApplication.instance(), theme() is DARK)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 14)
        root.setSpacing(20)
        root.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(22)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        contents = QWidget()
        contents.setObjectName("scrollContents")
        controls = QVBoxLayout(contents)
        controls.setContentsMargins(20, 22, 20, 20)
        controls.setSpacing(23)
        controls.addWidget(self._build_file_group())
        controls.addWidget(_separator())
        controls.addWidget(self._build_region_group())
        controls.addStretch()
        scroll.setWidget(contents)
        sidebar_layout.addWidget(scroll)
        body.addWidget(sidebar)

        dashboard = QWidget()
        dashboard.setObjectName("scrollContents")
        main = QVBoxLayout(dashboard)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSizeConstraint(QLayout.SetMinimumSize)
        main.setSpacing(16)
        main.addLayout(self._build_overview())
        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.metrics_a = RegionMetricsCard("지역 A")
        self.metrics_b = RegionMetricsCard("지역 B")
        metrics.addWidget(self.metrics_a, 1)
        metrics.addWidget(self.metrics_b, 1)
        main.addLayout(metrics)
        main.addWidget(self._build_chart_panel(), 1)
        main.addWidget(self._build_summary_group())
        dashboard_scroll = QScrollArea()
        self.dashboard_scroll = dashboard_scroll
        dashboard_scroll.setWidgetResizable(True)
        dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        dashboard_scroll.setWidget(dashboard)
        body.addWidget(dashboard_scroll, 1)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.status_dot = _label("●", "regionTag")
        footer.addWidget(self.status_dot)
        self.status = _label("데이터 파일을 확인한 뒤 ‘데이터 불러오기’를 눌러 시작하세요.", "muted")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        footer.addWidget(_label("HOTPLACE ANALYZER", "muted"))
        root.addLayout(footer)
        self._refresh_theme_controls()
        self.load_button.setFocus()

    def _button(self, text: str, icon: str, role: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setIconSize(QSize(16, 16))
        if role:
            button.setProperty("role", role)
        self._icon_buttons.append((button, icon, role == "primary"))
        return button

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)
        mark = QLabel()
        mark.setObjectName("brandMark")
        mark.setFixedSize(48, 48)
        mark.setAlignment(Qt.AlignCenter)
        mark.setPixmap(make_icon("pulse", "#ffffff", 28).pixmap(QSize(28, 28)))
        row.addWidget(mark)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(_label("서울 생활인구 분석", "title"))
        titles.addWidget(_label("시간과 지역으로 살펴보는 도시의 흐름", "muted"))
        row.addLayout(titles)
        row.addStretch()
        self.data_badge = _label("데이터 연결 대기", "badge")
        row.addWidget(self.data_badge, 0, Qt.AlignVCenter)
        self.theme_button = self._button("", "moon", "quiet")
        self.theme_button.clicked.connect(self._toggle_theme)
        row.addWidget(self.theme_button)
        return row

    def _build_overview(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(5)
        row = QHBoxLayout()
        row.addWidget(_label("REGION COMPARISON", "eyebrow"))
        row.addStretch()
        self.period_label = _label("분석 기간 —", "muted")
        row.addWidget(self.period_label)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.overview_title = _label("두 지역을 나란히 비교하세요", "heading")
        row.addWidget(self.overview_title)
        row.addStretch()
        self.overview_note = _label("동일 기간 · 공통 축 · 같은 지표", "muted")
        row.addWidget(self.overview_note)
        layout.addLayout(row)
        return layout

    def _build_file_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(_label("01", "badge"))
        heading.addWidget(_label("데이터 연결", "section"))
        heading.addStretch()
        layout.addLayout(heading)
        layout.addWidget(_label("분석할 CSV 파일 2개를 선택하세요.", "muted"))
        self.population_edit = QLineEdit()
        self.population_edit.setPlaceholderText("생활인구 CSV 파일")
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("행정동 코드 CSV 파일")
        self.file_buttons = []
        for caption, edit in (("생활인구 데이터", self.population_edit), ("행정동 코드표", self.code_edit)):
            label = _label(caption, "field")
            label.setBuddy(edit)
            edit.setAccessibleName(caption + " 파일 경로")
            edit.textChanged.connect(lambda value, field=edit: self._update_path_hint(field, value))
            layout.addWidget(label)
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(edit, 1)
            button = self._button("", "folder")
            button.setFixedSize(36, 36)
            button.setToolTip(caption + " 찾아보기")
            button.setAccessibleName(caption + " 찾아보기")
            button.clicked.connect(lambda _checked=False, field=edit, name=caption: self._pick_file(field, name + " 파일 선택"))
            self.file_buttons.append(button)
            row.addWidget(button)
            layout.addLayout(row)
        self.load_button = self._button("데이터 불러오기", "arrow", "primary")
        self.load_button.setDefault(True)
        self.load_button.clicked.connect(self.start_load)
        layout.addWidget(self.load_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        return group

    @staticmethod
    def _update_path_hint(field: QLineEdit, value: str) -> None:
        field.setToolTip(value)
        # 좁은 패널에서는 경로의 마지막에 있는 파일 이름을 우선 보여준다.
        if not field.hasFocus():
            field.setCursorPosition(len(value))
            field.deselect()

    def _build_region_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        heading = QHBoxLayout()
        heading.addWidget(_label("02", "badge"))
        heading.addWidget(_label("지역 탐색", "section"))
        heading.addStretch()
        layout.addLayout(heading)
        self.region_a = RegionSelector("지역 A")
        self.region_b = RegionSelector("지역 B")
        self.region_a.changed.connect(self._on_region_changed)
        self.region_b.changed.connect(self._on_region_changed)
        layout.addWidget(self.region_a)
        layout.addWidget(self.region_b)
        self.swap_button = self._button("지역 A ↔ B 서로 바꾸기", "compare")
        self.swap_button.setEnabled(False)
        self.swap_button.clicked.connect(self._swap_regions)
        layout.addWidget(self.swap_button)
        layout.addWidget(_label("모든 탭에서 두 지역을 같은 기준으로 분석합니다.", "muted", True))
        target_row = QHBoxLayout()
        target_row.addWidget(_label("검색 · 순위 선택 대상", "field"))
        self.search_target = QComboBox()
        self.search_target.addItems(["지역 A", "지역 B"])
        self.search_target.setAccessibleName("검색 및 순위로 선택할 지역")
        target_row.addWidget(self.search_target, 1)
        layout.addLayout(target_row)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("행정동 검색 · 예: 역삼1동")
        self.search_edit.setAccessibleName("행정동명 검색")
        self.search_edit.returnPressed.connect(self._search_dong)
        self.search_button = self._button("", "search")
        self.search_button.setFixedSize(36, 36)
        self.search_button.setToolTip("행정동 검색")
        self.search_button.setAccessibleName("행정동 검색")
        self.search_button.clicked.connect(self._search_dong)
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)
        self.top_button = self._button("생활인구 TOP 20", "rank")
        self.top_button.clicked.connect(self._show_top_dongs)
        layout.addWidget(self.top_button)
        layout.addWidget(_label("지역을 바꾸면 분석이 바로 업데이트됩니다.", "muted", True))
        for widget in (self.search_edit, self.search_button, self.top_button, self.search_target):
            widget.setEnabled(False)
        return group

    def _build_chart_panel(self) -> QFrame:
        panel = QFrame()
        self.chart_panel = panel
        panel.setObjectName("chartPanel")
        panel.setMinimumHeight(430)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 8, 18, 12)
        layout.setSpacing(0)
        layout.addWidget(self._build_tabs(), 1)
        layout.addWidget(_separator())
        layout.addLayout(self._build_action_row())
        return panel

    def _build_tabs(self) -> QTabWidget:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.tab_pages = []
        for title in TAB_TITLES:
            page = AnalysisTab()
            page.canvas.message("비교할 두 지역을 선택하세요", "CSV 파일을 연결하고 지역 A와 B를 고르면 같은 기준으로 분석합니다.")
            self.tabs.addTab(page, title)
            self.tab_pages.append(page)
        for index in range(len(TAB_TITLES)):
            self.tabs.setTabToolTip(index, "지역 A와 B를 같은 축 범위로 비교합니다.")
        self.tabs.setTabToolTip(OVERLAY_TAB, "두 지역의 시간대별 생활인구를 하나의 그래프에 겹쳐 봅니다.")
        self.tabs.currentChanged.connect(self._render_current)
        return self.tabs

    def _build_summary_group(self) -> QWidget:
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        row = QHBoxLayout()
        row.addWidget(_label("지역 인사이트", "section"))
        row.addWidget(_label("생활인구 패턴에 따른 참고 지표", "muted"))
        row.addStretch()
        self.summary_button = self._button("상세 통계", "info", "quiet")
        self.summary_button.setEnabled(False)
        self.summary_button.clicked.connect(self._show_summary)
        row.addWidget(self.summary_button)
        layout.addLayout(row)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.insight_a = InsightCard("지역 A")
        self.insight_b = InsightCard("지역 B")
        cards.addWidget(self.insight_a, 1)
        cards.addWidget(self.insight_b, 1)
        layout.addLayout(cards)
        return group

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 9, 0, 0)
        row.addWidget(_label("양쪽 축을 함께 확대 · 이동", "muted"))
        row.addStretch()
        self.save_png_button = self._button("이미지 저장", "download", "quiet")
        self.save_png_button.clicked.connect(self._save_png)
        self.export_csv_button = self._button("CSV 내보내기", "export", "quiet")
        self.export_csv_button.clicked.connect(self._export_csv)
        for button in (self.save_png_button, self.export_csv_button):
            button.setEnabled(False)
            row.addWidget(button)
        return row

    def _refresh_theme_controls(self) -> None:
        for button, icon, primary in self._icon_buttons:
            button.setIcon(make_icon(icon, "#ffffff" if primary else theme().ink_soft))
        dark = theme() is DARK
        self.theme_button.setText("밝은 모드" if dark else "어두운 모드")
        self.theme_button.setIcon(make_icon("sun" if dark else "moon"))
        self.theme_button.setToolTip("밝은 화면으로 전환" if dark else "어두운 화면으로 전환")
        for page in self.tab_pages:
            page.refresh_icons()

    def _toggle_theme(self) -> None:
        apply_theme(QApplication.instance(), theme() is not DARK)
        self._refresh_theme_controls()
        for index, page in enumerate(self.tab_pages):
            result = self._results.get(index)
            if result is not None:
                self._draw_result(page, result)
            else:
                page.canvas.message("비교할 두 지역을 선택하세요", "CSV 파일을 연결하고 지역 A와 B를 고르면 같은 기준으로 분석합니다.")
        self._render_current()

    def _prefill_paths(self) -> None:
        """기본 데이터 폴더를 찾아 경로 칸을 미리 채운다."""
        data_dir = default_data_dir()
        if data_dir is None:
            return
        population_csv = find_population_csv(data_dir)
        if population_csv:
            self.population_edit.setText(str(population_csv))
        code_csv = data_dir / "dong_code.csv"
        if code_csv.exists():
            self.code_edit.setText(str(code_csv))
        if population_csv and code_csv.exists():
            self.status.setText("기본 데이터 파일을 찾았습니다. ‘데이터 불러오기’를 눌러 분석을 시작하세요.")
            self.status.setToolTip(str(data_dir))

    # ── 파일 선택 · 로딩 ─────────────────────────────────────────────
    def _pick_file(self, target: QLineEdit, caption: str) -> None:
        start_dir = str(Path(target.text()).parent) if target.text() else ""
        path, _ = QFileDialog.getOpenFileName(
            self, caption, start_dir, "CSV 파일 (*.csv);;모든 파일 (*)"
        )
        if path:
            target.setText(path)

    def start_load(self) -> None:
        if self._thread is not None:
            return
        population_csv = self.population_edit.text().strip()
        code_csv = self.code_edit.text().strip()
        if not population_csv or not code_csv:
            QMessageBox.warning(self, "입력 확인", "두 개의 CSV 파일 경로를 모두 지정해 주세요.")
            return

        self.load_button.setEnabled(False)
        self.load_button.setText("데이터 불러오는 중…")
        self.data_badge.setText("데이터 연결 중")
        self.status.setText("CSV 파일을 확인하고 있습니다…")
        for widget in (self.population_edit, self.code_edit, *self.file_buttons):
            widget.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()

        self._thread = QThread(self)
        self._worker = LoadWorker(population_csv, code_csv)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _finish_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None
        self.load_button.setEnabled(True)
        self.load_button.setText("데이터 다시 불러오기" if self.population else "데이터 불러오기")
        for widget in (self.population_edit, self.code_edit, *self.file_buttons):
            widget.setEnabled(True)

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status.setText(message)

    def _on_failed(self, message: str) -> None:
        self.progress.hide()
        self.data_badge.setText("연결 실패 · 다시 시도")
        self.status.setText(f"오류: {message}")
        self._finish_thread()
        QMessageBox.critical(self, "데이터 오류", message)

    def _on_loaded(self, population: Population, codebook: CodeBook) -> None:
        self.progress.hide()
        self._finish_thread()
        self.population = population
        self.codebook = codebook
        self.data_badge.setText(f"{len(population.aggregates):,}개 행정동 연결됨")
        self.period_label.setText(population.period.replace("-", ".").replace(" ~ ", " — "))
        self.load_button.setText("데이터 다시 불러오기")

        self.region_a.blockSignals(True)
        self.region_b.blockSignals(True)
        self.region_a.populate(codebook, population)
        self.region_b.populate(codebook, population)
        for widget in (self.search_edit, self.search_button, self.top_button,
                       self.summary_button, self.swap_button, self.search_target):
            widget.setEnabled(True)

        # 지역 A/B 가 같은 곳이면 비교 그래프가 의미 없으니 B는 다른 동으로 옮겨 둔다.
        ranking = rank_by_daily_average(population, codebook, top=2)
        if len(ranking) == 2:
            self.region_a.set_dong(ranking[0][0])
            self.region_b.set_dong(ranking[1][0])
        self.region_a.blockSignals(False)
        self.region_b.blockSignals(False)

        self.status.setText(
            f"{len(population.aggregates)}개 행정동 · {population.period} "
            f"(평일 {population.n_weekday}일 / 주말 {population.n_weekend}일) 준비 완료"
        )
        self._on_region_changed()

    # ── 행정동 선택 ──────────────────────────────────────────────────
    def _search_dong(self) -> None:
        if self.codebook is None:
            return
        name = self.search_edit.text().strip()
        if not name:
            return
        matches = [d for d in self.codebook.search(name) if self.population.has(d.code)]
        if not matches:
            self.status.setText(f"'{name}' 행정동을 찾을 수 없습니다.")
            QMessageBox.information(self, "검색 결과", f"'{name}' 행정동을 찾을 수 없습니다.")
            return
        if len(matches) == 1:
            chosen = matches[0]
        else:
            dialog = DongPickDialog(matches, self)
            if dialog.exec_() != QDialog.Accepted:
                return
            chosen = dialog.selected()
            if chosen is None:
                return
        target = self._search_selector()
        target.set_dong(chosen)
        self.status.setText(f"{self.search_target.currentText()}: {chosen.label}을 선택했습니다.")

    def _search_selector(self) -> RegionSelector:
        return self.region_a if self.search_target.currentIndex() == 0 else self.region_b

    def _show_top_dongs(self) -> None:
        if self.population is None or self.codebook is None:
            return
        ranking = rank_by_daily_average(self.population, self.codebook, top=20)
        dialog = TopDongDialog(ranking, self, target=self.search_target.currentText())
        if dialog.exec_() == QDialog.Accepted:
            chosen = dialog.selected()
            if chosen is not None:
                self._search_selector().set_dong(chosen)

    def _on_region_changed(self) -> None:
        self._results.clear()
        self._update_summary()
        self._render_current()

    def _swap_regions(self) -> None:
        dong_a, dong_b = self.region_a.current(), self.region_b.current()
        if dong_a is None or dong_b is None:
            return
        self.region_a.blockSignals(True)
        self.region_b.blockSignals(True)
        try:
            self.region_a.set_dong(dong_b)
            self.region_b.set_dong(dong_a)
        finally:
            self.region_a.blockSignals(False)
            self.region_b.blockSignals(False)
        self._on_region_changed()

    def _hotplaces(self) -> tuple[Hotplace | None, Hotplace | None]:
        if self.population is None:
            return None, None
        dong_a, dong_b = self.region_a.current(), self.region_b.current()
        place_a = Hotplace(dong_a, self.population) if dong_a else None
        place_b = Hotplace(dong_b, self.population) if dong_b else None
        return place_a, place_b

    # ── 그리기 ───────────────────────────────────────────────────────
    @staticmethod
    def _draw_result(page: AnalysisTab, result: LineSeries | PairedAnalysis) -> None:
        if isinstance(result, PairedAnalysis):
            draw_paired_analysis(page.canvas, result)
        else:
            draw_line_series(page.canvas, result)

    def _render_current(self, *_args) -> None:
        index = self.tabs.currentIndex()
        page = self.tab_pages[index]
        place_a, place_b = self._hotplaces()
        self.chart_panel.setMinimumHeight(560 if index == 4 else 430)
        self.save_png_button.setEnabled(False)
        self.export_csv_button.setEnabled(False)
        page.toolbar.setVisible(False)

        if place_a is None or place_b is None:
            page.canvas.message("비교할 두 지역을 선택하세요", "CSV 파일을 연결하고 지역 A와 B를 고르면 같은 기준으로 분석합니다.")
            return

        result = self._results.get(index)
        if result is None:
            if index == OVERLAY_TAB:
                result = place_a.analysis4(place_b)
            else:
                method = ("analysis1", "analysis2", "analysis3", "analysis4", "analysis5")[index]
                result = PairedAnalysis(
                    title=f"{place_a.label} · {place_b.label} {TAB_TITLES[index]} 비교",
                    regions=(place_a.label, place_b.label),
                    analyses=(getattr(place_a, method)(), getattr(place_b, method)()),
                    note=self.population.period,
                )
            self._results[index] = result

        self._draw_result(page, result)
        page.toolbar.setVisible(True)
        page.toolbar.update()
        self.save_png_button.setEnabled(True)
        self.export_csv_button.setEnabled(True)

    def _update_summary(self) -> None:
        place_a, place_b = self._hotplaces()
        self.metrics_a.update_place(place_a)
        self.metrics_b.update_place(place_b)
        self.insight_a.update_place(place_a)
        self.insight_b.update_place(place_b)
        self.summary_button.setEnabled(place_a is not None or place_b is not None)
        self.swap_button.setEnabled(place_a is not None and place_b is not None)
        self.overview_title.setText("두 지역을 나란히 비교하세요")
        same = place_a and place_b and place_a.code == place_b.code
        self.overview_note.setText("같은 지역 선택됨 · 동일한 결과" if same else "동일 기간 · 공통 축 · 같은 지표")

    def _show_summary(self) -> None:
        places = self._hotplaces()
        if not any(places):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("두 지역 상세 통계")
        dialog.resize(1080, 580)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(_label("두 지역 상세 통계", "heading"))
        layout.addWidget(_label("동일한 항목을 나란히 비교하세요. 텍스트를 선택해 복사할 수 있습니다.", "muted"))
        columns = QHBoxLayout()
        columns.setSpacing(16)
        for index, place in enumerate(places):
            column = QVBoxLayout()
            column.addWidget(_label(f"지역 {'AB'[index]}", "regionTag" if index == 0 else "regionTagB"))
            summary_view = QPlainTextEdit()
            summary_view.setReadOnly(True)
            summary_view.setLineWrapMode(QPlainTextEdit.NoWrap)
            summary_view.setFont(_mono_font())
            summary_view.setPlainText(summary_text(place) if place else "행정동을 선택해 주세요.")
            column.addWidget(summary_view, 1)
            columns.addLayout(column, 1)
        layout.addLayout(columns, 1)
        layout.addWidget(_label("추정 상권 성격은 생활인구 패턴에 따른 규칙 기반 참고값입니다.", "muted"))
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("닫기")
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec_()

    # ── 내보내기 ─────────────────────────────────────────────────────
    def _save_png(self) -> None:
        index = self.tabs.currentIndex()
        result = self._results.get(index)
        if result is None:
            QMessageBox.information(self, "저장", "먼저 그래프를 표시해 주세요.")
            return
        default = f"{self._slug(result.title)}.png"
        path, _ = QFileDialog.getSaveFileName(self, "그래프 저장", default, "PNG 이미지 (*.png)")
        if not path:
            return
        self.tab_pages[index].canvas.figure.savefig(path, dpi=200, facecolor=theme().surface)
        self.status.setText(f"그래프를 저장했습니다: {path}")

    def _export_csv(self) -> None:
        index = self.tabs.currentIndex()
        result = self._results.get(index)
        if result is None:
            QMessageBox.information(self, "내보내기", "먼저 그래프를 표시해 주세요.")
            return
        default = f"{self._slug(result.title)}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "CSV 내보내기", default, "CSV 파일 (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(result.csv_rows())
        except OSError as exc:
            QMessageBox.critical(self, "내보내기 실패", str(exc))
            return
        self.status.setText(f"CSV로 내보냈습니다: {path}")

    @staticmethod
    def _slug(title: str) -> str:
        return "".join(c if c.isalnum() or c in "가-힣" or ord(c) > 127 else "_" for c in title).strip("_")

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)


def run() -> int:
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName("Hotplace Analyzer")
    # 시스템이 다크 모드면 그래프도 어두운 테마로 (창 배경 밝기로 판단).
    set_theme(app.palette().color(QPalette.Window).lightness() < 128)
    window = MainWindow()
    window.show()
    return app.exec_()
