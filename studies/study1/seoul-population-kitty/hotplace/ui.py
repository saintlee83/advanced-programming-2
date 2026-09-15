"""상단 메뉴와 좌우 패널로 구성한 서울 생활인구 비교 화면.
CSV 로딩과 계산·내보내기는 기존 Python 모델을 사용한다.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QSizePolicy,
    QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    ComboBox, InfoBar, InfoBarPosition, LineEdit,
    PrimaryPushButton, ProgressBar, PushButton, SearchLineEdit, SmoothScrollArea,
    TableWidget, TransparentPushButton, TransparentToolButton,
)

from .dataset import (
    CodeBook, DataError, Dong, Population, default_data_dir,
    find_population_csv, load_population,
)
from .hotplace import Hotplace, PairedAnalysis, rank_by_daily_average, summary_text
from .plotting import draw_result, set_theme, theme
from .theme import DARK, apply_theme, make_icon
from .analytics import ROWS, compare_places, display, insight_cards, report_text, similarity_label
from .widgets import (
    READOUT_HINT, AnalysisTabs, ComparisonMetrics, ComparisonTable, NavigationItem,
    AnimatedStack, label as _label, motion_enabled, region_badge, separator as _separator, stat_cell,
)

# 차트 번호 i 는 Hotplace.analysis(i + 1) 에 대응한다.
TAB_TITLES = ("시간대", "평일·주말", "성별", "겹쳐 보기", "연령", "일별 추이", "요일×시간", "흐름 비교",
              "시간대별 차이", "요일별", "여성 비율", "연령 비중", "연령×시간", "서울 속 위치")
CHART_TITLES = ("시간대별 평균 인구", "평일과 주말의 시간대별 인구", "남녀 시간대별 인구", "두 지역을 한 차트에",
                "연령대별 인구 구성", "일별 평균과 7일 이동평균", "요일·시간대별 평균 인구", "하루 흐름 비교 (지역 평균 = 100)",
                "시간대별 인구 차이 (A − B)", "요일별 평균 인구", "시간대별 여성 비율", "연령대별 비중 비교",
                "시간대별 연령 구성", "서울 행정동 속 두 지역의 위치")
TAB_GROUPS = (
    ("하루 흐름", (0, 1, 3, 8, 7)),
    ("요일·날짜", (9, 6, 5)),
    ("성별·연령", (2, 10, 4, 11, 12)),
    ("서울 전체", (13,)),
)
PAIR_TABS = {3, 7, 8, 11}      # 두 지역을 한 결과로 계산하는 분석
CITY_TAB = 13
CHART_HEIGHTS = {4: 760, 6: 680, 11: 620, 12: 880, 13: 680}
CHART_HINTS = {
    4: "왼쪽은 남자, 오른쪽은 여자 · 두 지역이 같은 축을 씁니다",
    6: "두 지역이 같은 색 범위를 씁니다 · 칸에 마우스를 올리면 값이 표시됩니다",
    11: "연령대 줄에 마우스를 올리면 두 지역의 비중이 표시됩니다",
    12: "두 지역이 같은 색 범위를 씁니다 · 칸에 마우스를 올리면 값이 표시됩니다",
    13: "점에 마우스를 올리면 행정동 이름과 배율이 표시됩니다",
}
PAGE_TITLES = ("지역 비교", "지역 찾기", "데이터", "비교 리포트")
PAGE_NOTES = (
    "두 행정동의 생활인구를 같은 기준, 같은 축으로 비교합니다.",
    "이름으로 검색하거나 순위표에서 골라 지역 A 또는 B에 넣습니다.",
    "생활인구 CSV와 행정동 코드표를 불러옵니다.",
    "두 지역의 특징을 항목별 수치로 나란히 정리합니다.",
)
# 비교 리포트의 각 항목을 자세히 볼 수 있는 차트.
ROW_CHARTS = {"busy": 0, "volatility": 7, "ages": 11, "unusual": 5}
OVERLAY_TAB = 3
APP_NAME = "서울 생활인구 비교"


def _mono_font(point_size: int = 11) -> QFont:
    font = QFont("Menlo", point_size)
    font.setStyleHint(QFont.Monospace)
    return font


def _period(population: Population) -> str:
    return population.period.replace("-", ".").replace(" ~ ", " – ")


class LoadWorker(QObject):
    """CSV 읽기를 담당하는 워커. QThread 로 옮겨서 실행한다."""

    progress = Signal(int, str)
    loaded = Signal(object, object)
    failed = Signal(str)

    def __init__(self, population_csv: str, code_csv: str) -> None:
        super().__init__()
        self._population_csv = population_csv
        self._code_csv = code_csv

    @Slot()
    def run(self) -> None:
        try:
            population, codebook = load_population(
                self._population_csv,
                self._code_csv,
                progress=lambda pct, msg: self.progress.emit(pct, msg),
                cancelled=lambda: QThread.currentThread().isInterruptionRequested(),
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

    def __init__(self, dongs: list[Dong], parent=None, title="행정동 고르기") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(440, 340)
        self._dongs = dongs

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(QLabel("같은 이름의 행정동이 여러 곳 있습니다. 비교할 곳을 고르세요."))
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


class RegionSelector(QFrame):
    """자치구 + 행정동 콤보 한 쌍."""

    changed = Signal()

    def __init__(self, caption: str, parent=None) -> None:
        super().__init__(parent)
        self._codebook: CodeBook | None = None
        self._population: Population | None = None
        self._loading = False

        self.setProperty("role", "regionSelector")
        self.setProperty("region", "B" if caption.endswith("B") else "A")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(region_badge(caption))
        heading.addWidget(_label(caption, "field"), 1)
        layout.addLayout(heading)
        choices = QHBoxLayout()
        choices.setSpacing(8)
        self.sigungu, self.dong = ComboBox(), ComboBox()
        for widget, text in ((self.sigungu, "자치구"), (self.dong, "행정동")):
            widget.setFont(QApplication.font())
            widget.setAccessibleName(f"{caption} {text}")
            widget.setPlaceholderText(text)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumWidth(88)
            choices.addWidget(widget, 1)

        layout.addLayout(choices)

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
                self.dong.addItem(dong.name, userData=dong)
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


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.population: Population | None = None
        self.codebook: CodeBook | None = None
        self._thread: QThread | None = None
        self._worker: LoadWorker | None = None
        self._results: dict[int, object] = {}
        self._closing = False
        self._build_ui()
        self._prefill_paths()

    def _build_ui(self) -> None:
        self.setObjectName("mainWindow")
        self.setWindowTitle(APP_NAME)
        self.resize(1480, 980)
        self.setMinimumSize(1080, 740)
        self._icon_buttons = []
        apply_theme(QApplication.instance(), theme() is DARK)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_navigation())
        root.addWidget(self._build_topbar())
        self.workspace_stack = AnimatedStack()
        self.workspace_stack.addWidget(self._build_analysis_page())
        self.workspace_stack.addWidget(self._build_explore_page())
        self.workspace_stack.addWidget(self._build_data_page())
        self.workspace_stack.addWidget(self._build_report_page())
        root.addWidget(self.workspace_stack, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(28, 10, 28, 12)
        self.status = _label("데이터를 불러오면 비교를 시작할 수 있습니다.", "caption", True)
        footer.addWidget(self.status, 1)
        root.addLayout(footer)
        self._refresh_theme_controls()
        self._show_page(0)

    def _button(self, text: str, icon: str, role: str = "") -> QAbstractButton:
        cls = PrimaryPushButton if role == "primary" else TransparentPushButton if role == "quiet" else PushButton
        button = cls(text) if text else TransparentToolButton()
        button.setFont(QApplication.font())
        button.setIconSize(QSize(16, 16))
        button.setMinimumHeight(34)
        button.setCursor(Qt.PointingHandCursor)
        self._icon_buttons.append((button, icon, role == "primary"))
        return button

    def _build_navigation(self) -> QFrame:
        header = QFrame()
        header.setObjectName("appHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(28, 14, 28, 12)
        layout.setSpacing(12)
        masthead = QHBoxLayout()
        masthead.setSpacing(14)
        self.brand_icon = QLabel()
        self.brand_icon.setFixedSize(32, 28)
        self.brand_icon.setAlignment(Qt.AlignCenter)
        self.brand_icon.setAccessibleName("헬로키티")
        masthead.addWidget(self.brand_icon)
        masthead.addWidget(_label(APP_NAME, "brand"))
        masthead.addStretch()
        layout.addLayout(masthead)
        navigation = QHBoxLayout()
        navigation.setSpacing(8)
        pages = (("지역 비교", "chart"), ("지역 찾기", "search"), ("데이터", "folder"), ("비교 리포트", "export"))
        self.nav_items = []
        for index, (title, icon) in enumerate(pages):
            button = NavigationItem(make_icon(icon), title)
            button.clicked.connect(lambda _checked=False, i=index: self._show_page(i))
            self.nav_items.append((button, icon))
        for index in (0, 3, 1, 2):
            navigation.addWidget(self.nav_items[index][0])
        navigation.addStretch()
        self.theme_button = NavigationItem(make_icon("moon"), "어두운 테마", selectable=False)
        self.theme_button.clicked.connect(lambda _checked=False: self._toggle_theme())
        navigation.addWidget(self.theme_button)
        self.motion_button = NavigationItem(make_icon("pulse"), "", selectable=False)
        self.motion_button.clicked.connect(lambda _checked=False: self._toggle_motion(motion_enabled()))
        self._set_motion_text()
        navigation.addWidget(self.motion_button)
        layout.addLayout(navigation)
        return header

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("pageHeader")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(28, 18, 28, 14)
        layout.setSpacing(16)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.page_title = _label(PAGE_TITLES[0], "pageTitle")
        self.page_note = _label(PAGE_NOTES[0], "caption", True)
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_note)
        layout.addLayout(titles, 1)
        self.period_label = _label("", "muted")
        layout.addWidget(self.period_label)
        self.data_badge = _label("데이터 없음", "badge")
        layout.addWidget(self.data_badge, 0, Qt.AlignVCenter)
        return bar

    def _scroll_page(self, contents: QWidget) -> SmoothScrollArea:
        contents.setObjectName("pageContents")
        scroll = SmoothScrollArea()
        scroll.setObjectName("workspacePage")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(contents)
        return scroll

    def _show_page(self, index: int) -> None:
        self.workspace_stack.setCurrentIndex(index, duration=240)
        self.page_title.setText(PAGE_TITLES[index])
        self.page_note.setText(PAGE_NOTES[index])
        for i, (item, _icon) in enumerate(self.nav_items):
            item.setSelected(i == index)

    # ── 지역 비교 ────────────────────────────────────────────────────
    def _build_analysis_page(self) -> QStackedWidget:
        self.analysis_state = AnimatedStack()
        self.analysis_state.addWidget(self._build_welcome())
        dashboard = QWidget()
        main = QHBoxLayout(dashboard)
        main.setContentsMargins(28, 12, 28, 24)
        main.setSpacing(20)
        main.setSizeConstraint(QLayout.SetMinimumSize)
        sidebar = QWidget()
        sidebar.setFixedWidth(292)
        selectors = QVBoxLayout(sidebar)
        selectors.setContentsMargins(0, 0, 0, 0)
        selectors.setSpacing(10)
        selectors.addWidget(_label("비교 지역", "section"))
        self.region_a = RegionSelector("지역 A")
        self.region_b = RegionSelector("지역 B")
        self.region_a.changed.connect(self._on_region_changed)
        self.region_b.changed.connect(self._on_region_changed)
        selectors.addWidget(self.region_a)
        selectors.addWidget(self.region_b)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.swap_button = self._button("지역 교환", "compare")
        self.swap_button.setToolTip("지역 A와 B 바꾸기")
        self.swap_button.setAccessibleName("지역 A와 B 바꾸기")
        self.swap_button.setEnabled(False)
        self.swap_button.clicked.connect(self._swap_regions)
        actions.addWidget(self.swap_button, 1)
        self.top_button = self._button("찾기", "search")
        self.top_button.setEnabled(False)
        self.top_button.clicked.connect(lambda: self._show_page(1))
        actions.addWidget(self.top_button)
        selectors.addLayout(actions)
        selectors.addSpacing(10)
        selectors.addWidget(_label("주요 지표", "section"))
        metrics = ComparisonMetrics()
        self.metrics_a, self.metrics_b = metrics.region_a, metrics.region_b
        selectors.addWidget(metrics)
        selectors.addStretch()
        main.addWidget(sidebar, 0, Qt.AlignTop)
        notebook = QVBoxLayout()
        notebook.setSpacing(14)
        self.overview_note = _label("지역 A와 B가 같습니다. 다른 지역을 고르면 차이를 비교할 수 있습니다.", "notice", True)
        self.overview_note.hide()
        notebook.addWidget(self.overview_note)
        notebook.addWidget(self._build_chart_panel(), 1)
        notebook.addWidget(self._build_type_strip())
        main.addLayout(notebook, 1)
        self.dashboard_scroll = self._scroll_page(dashboard)
        self.analysis_state.addWidget(self.dashboard_scroll)
        return self.analysis_state

    def _build_welcome(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 28, 48, 32)
        layout.setSpacing(20)
        layout.addStretch()
        invitation = QFrame()
        invitation.setObjectName("invitation")
        card = QHBoxLayout(invitation)
        card.setContentsMargins(40, 34, 40, 34)
        card.setSpacing(30)
        words = QVBoxLayout()
        words.setSpacing(16)
        words.addWidget(_label("먼저 데이터를 불러오세요", "emptyTitle"))
        words.addWidget(_label("생활인구 CSV와 행정동 코드표가 필요합니다.\n불러온 뒤 두 행정동을 선택해 시간대·요일·연령별로 비교할 수 있습니다.", "welcomeCopy", True))
        self.connect_button = self._button("데이터 불러오기", "arrow", "primary")
        self.connect_button.setMinimumHeight(40)
        self.connect_button.clicked.connect(self._start_from_welcome)
        words.addWidget(self.connect_button, 0, Qt.AlignLeft)
        self.welcome_hint = _label("", "caption", True)
        words.addWidget(self.welcome_hint)
        card.addLayout(words, 3)
        stamp = QFrame()
        stamp.setObjectName("kittyStamp")
        stamp.setFixedWidth(200)
        picture = QVBoxLayout(stamp)
        picture.setContentsMargins(24, 30, 24, 24)
        picture.setSpacing(18)
        self.welcome_icon = QLabel()
        self.welcome_icon.setFixedSize(132, 100)
        self.welcome_icon.setAlignment(Qt.AlignCenter)
        self.welcome_icon.setAccessibleName("빨간 리본을 단 헬로키티")
        picture.addWidget(self.welcome_icon, 0, Qt.AlignCenter)
        card.addWidget(stamp)
        layout.addWidget(invitation)
        steps = QHBoxLayout()
        steps.setSpacing(16)
        for number, title, note in (("01", "파일 연결", "생활인구 CSV + 행정동 코드표"),
                                    ("02", "지역 선택", "비교할 행정동 A·B 지정"),
                                    ("03", "분석", "차트와 비교 리포트 확인")):
            tile = QFrame()
            tile.setProperty("role", "stepCard")
            row = QHBoxLayout(tile)
            row.setContentsMargins(18, 16, 18, 16)
            row.addWidget(_label(number, "noteNumber"))
            text = QVBoxLayout()
            text.addWidget(_label(title, "section"))
            text.addWidget(_label(note, "caption", True))
            row.addLayout(text, 1)
            steps.addWidget(tile, 1)
        layout.addLayout(steps)
        layout.addStretch()
        return self._scroll_page(page)

    def _start_from_welcome(self) -> None:
        self._show_page(2)
        if self.population_edit.text().strip() and self.code_edit.text().strip():
            self.start_load()

    def _refresh_welcome_hint(self) -> None:
        ready = bool(self.population_edit.text().strip() and self.code_edit.text().strip())
        self.welcome_hint.setText("파일 경로가 채워져 있어 바로 불러옵니다." if ready
                                  else "‘데이터’ 화면에서 두 파일을 지정합니다.")

    def _build_chart_panel(self) -> QFrame:
        self.chart_panel = QFrame()
        self.chart_panel.setObjectName("chartPanel")
        layout = QVBoxLayout(self.chart_panel)
        layout.setContentsMargins(22, 16, 22, 12)
        layout.setSpacing(0)
        self.tabs = AnalysisTabs(TAB_TITLES, TAB_GROUPS)
        self.tab_pages = self.tabs.pages
        self.tabs.currentChanged.connect(self._render_current)
        heading = QHBoxLayout()
        heading.setContentsMargins(0, 4, 0, 0)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.chart_title = _label(CHART_TITLES[0], "chartTitle", True)
        self.chart_note = _label("", "caption", True)
        titles.addWidget(self.chart_title)
        titles.addWidget(self.chart_note)
        heading.addLayout(titles, 1)
        self.save_png_button = self._button("PNG 저장", "download", "quiet")
        self.save_png_button.clicked.connect(self._save_png)
        self.export_csv_button = self._button("CSV 저장", "export", "quiet")
        self.export_csv_button.clicked.connect(self._export_csv)
        for button in (self.save_png_button, self.export_csv_button):
            button.setEnabled(False)
            heading.addWidget(button, 0, Qt.AlignTop)
        self.tabs.set_header(heading)
        layout.addWidget(self.tabs, 1)
        return self.chart_panel

    def _build_type_strip(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("insightStrip")
        row = QHBoxLayout(panel)
        row.setContentsMargins(18, 10, 12, 10)
        row.setSpacing(10)
        title = _label("상권 유형 (추정)", "field")
        title.setToolTip("낮/밤 배율, 주말/평일 배율, 가장 붐비는 시간으로 나눈 규칙 기반 참고값입니다.")
        row.addWidget(title)
        row.addSpacing(8)
        self.insight_a = _label("—", "muted", True)
        self.insight_b = _label("—", "muted", True)
        for region, field in (("A", self.insight_a), ("B", self.insight_b)):
            row.addWidget(region_badge(region))
            row.addWidget(field, 1)
        self.summary_button = self._button("상세 통계", "info", "quiet")
        self.summary_button.setEnabled(False)
        self.summary_button.clicked.connect(self._show_summary)
        row.addWidget(self.summary_button)
        return panel

    # ── 지역 찾기 ────────────────────────────────────────────────────
    def _build_explore_page(self) -> SmoothScrollArea:
        contents = QWidget()
        layout = QHBoxLayout(contents)
        layout.setContentsMargins(28, 12, 28, 24)
        layout.setSpacing(20)
        station = QFrame()
        station.setObjectName("searchStation")
        station.setFixedWidth(292)
        search = QVBoxLayout(station)
        search.setContentsMargins(20, 24, 20, 24)
        search.setSpacing(14)
        search.addWidget(_label("행정동 검색", "section"))
        self.search_edit = SearchLineEdit()
        self.search_edit.setFont(QApplication.font())
        self.search_edit.setPlaceholderText("행정동·자치구·코드 검색")
        self.search_edit.setAccessibleName("행정동 검색")
        self.search_edit.setMinimumHeight(40)
        self.search_edit.searchSignal.connect(lambda _text: self._search_dong())
        self.search_button = self.search_edit.searchButton
        self.search_button.setAccessibleName("검색")
        search.addWidget(self.search_edit)
        search.addWidget(_label("선택한 지역 넣기", "field"))
        self.search_target = ComboBox()
        self.search_target.setFont(QApplication.font())
        self.search_target.addItems(["지역 A", "지역 B"])
        self.search_target.setAccessibleName("검색하거나 고른 지역을 넣을 자리")
        self.search_target.currentIndexChanged.connect(self._update_target_labels)
        search.addWidget(self.search_target)
        search.addSpacing(12)
        search.addWidget(_separator())
        self.ranking_caption = _label("순위 정렬 기준", "section")
        search.addWidget(self.ranking_caption)
        self.rank_metric = ComboBox()
        self.rank_metric.setFont(QApplication.font())
        self.rank_metric.addItems(["일평균 생활인구", "가장 붐비는 시간의 인구", "주말 ÷ 평일 배율", "낮 ÷ 밤 배율"])
        self.rank_metric.setAccessibleName("순위 정렬 기준")
        self.rank_metric.currentIndexChanged.connect(self._refresh_ranking)
        search.addWidget(self.rank_metric)
        search.addWidget(_label("선택한 기준으로 상위 20개 행정동을 표시합니다.", "muted", True))
        search.addStretch()
        layout.addWidget(station, 0, Qt.AlignTop)
        panel = QFrame()
        panel.setObjectName("rankingPanel")
        ranking = QVBoxLayout(panel)
        ranking.setContentsMargins(22, 22, 22, 18)
        ranking.setSpacing(16)
        heading = QHBoxLayout()
        heading.addWidget(_label("생활인구 상위 20곳", "chartTitle"))
        heading.addStretch()
        ranking.addLayout(heading)
        self.rank_table = TableWidget()
        self.rank_table.setColumnCount(4)
        self.rank_table.setHorizontalHeaderLabels(["순위", "자치구", "행정동", "일평균 생활인구"])
        self.rank_table.verticalHeader().hide()
        self.rank_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rank_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rank_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.rank_table.setColumnWidth(0, 56)
        self.rank_table.setColumnWidth(1, 100)
        self.rank_table.setColumnWidth(3, 180)
        self.rank_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.rank_table.setMinimumHeight(440)
        self.rank_table.cellDoubleClicked.connect(lambda row, _column: self._choose_rank(row))
        ranking.addWidget(self.rank_table, 1)
        actions = QHBoxLayout()
        self.rank_hint = _label("데이터를 불러오면 순위가 표시됩니다.", "caption", True)
        actions.addWidget(self.rank_hint, 1)
        self.rank_select_button = self._button("지역 A에 넣기", "arrow", "primary")
        self.rank_select_button.setEnabled(False)
        self.rank_select_button.clicked.connect(lambda: self._choose_rank(self.rank_table.currentRow()))
        actions.addWidget(self.rank_select_button)
        ranking.addLayout(actions)
        layout.addWidget(panel, 1)
        for widget in (self.search_edit, self.search_target):
            widget.setEnabled(False)
        return self._scroll_page(contents)

    def _update_target_labels(self, *_args) -> None:
        self.rank_select_button.setText(f"{self.search_target.currentText()}에 넣기")

    def _refresh_ranking(self) -> None:
        if self.population is None:
            return
        ranking = rank_by_daily_average(self.population, self.codebook, top=20)
        index = self.rank_metric.currentIndex()
        if index:
            key = ("daily_avg", "peak_value", "weekend_ratio", "day_night_ratio")[index]
            ranking = [(dong, Hotplace(dong, self.population).summary()[key])
                       for dong, _ in rank_by_daily_average(self.population, self.codebook, top=len(self.population.aggregates))]
            ranking = sorted(((dong, value) for dong, value in ranking if math.isfinite(value)),
                             key=lambda item: item[1], reverse=True)[:20]
        self.rank_table.setHorizontalHeaderLabels(["순위", "자치구", "행정동", self.rank_metric.currentText()])
        self.rank_table.setRowCount(len(ranking))
        for row, (dong, value) in enumerate(ranking):
            formatted = f"{value:.2f}배" if index >= 2 else f"{value:,.0f}명"
            for column, text in enumerate((f"{row + 1}", dong.sigungu, dong.name, formatted)):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, dong)
                if column == 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.rank_table.setItem(row, column, item)
            self.rank_table.setRowHeight(row, 54)
        self.rank_hint.setText("행을 더블클릭하면 바로 넣습니다.")
        self.rank_select_button.setEnabled(bool(ranking))
        if ranking:
            self.rank_table.selectRow(0)

    def _choose_rank(self, row: int) -> None:
        item = self.rank_table.item(row, 0)
        if item is None:
            return
        dong = item.data(Qt.UserRole)
        self._search_selector().set_dong(dong)
        self.status.setText(f"{self.search_target.currentText()}에 {dong.label}을 넣었습니다.")
        self._show_page(0)

    # ── 데이터 ───────────────────────────────────────────────────────
    def _build_data_page(self) -> SmoothScrollArea:
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.setContentsMargins(28, 12, 28, 24)
        layout.setSpacing(14)
        board = QFrame()
        board.setObjectName("fileBoard")
        tickets = QVBoxLayout(board)
        tickets.setContentsMargins(24, 24, 24, 24)
        tickets.setSpacing(20)
        tickets.addWidget(_label("데이터 파일", "section"))
        tickets.addWidget(_label("생활인구 CSV와 해당 행정동 코드표를 지정하세요.", "muted"))
        files = QHBoxLayout()
        files.setSpacing(18)
        self.population_edit, self.code_edit = LineEdit(), LineEdit()
        self.file_buttons = []
        for number, title, note, edit in (
            ("1", "생활인구", "LOCAL_PEOPLE_DONG_YYYYMM.csv · 날짜·시간대·행정동별 생활인구", self.population_edit),
            ("2", "행정동 코드표", "dong_code.csv · 행정동 코드와 자치구·동 이름", self.code_edit),
        ):
            card = QFrame()
            card.setProperty("role", "fileCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(22, 18, 22, 18)
            card_layout.setSpacing(10)
            heading = QHBoxLayout()
            heading.setSpacing(10)
            step = _label("0" + number, "noteNumber")
            step.setFixedSize(36, 36)
            step.setAlignment(Qt.AlignCenter)
            step.setStyleSheet("padding: 0;")
            heading.addWidget(step)
            heading.addWidget(_label(title, "chartTitle"), 1)
            heading.addSpacing(6)
            card_layout.addLayout(heading)
            card_layout.addWidget(_label(note, "caption", True))
            row = QHBoxLayout()
            edit.setFont(QApplication.font())
            edit.setMinimumHeight(36)
            edit.setPlaceholderText("파일을 고르거나 경로를 붙여넣으세요")
            edit.setAccessibleName(title + " 파일 경로")
            edit.textChanged.connect(lambda text, field=edit: self._update_path_hint(field, text))
            edit.textChanged.connect(lambda _text: self._refresh_welcome_hint())
            row.addWidget(edit, 1)
            button = self._button("찾아보기", "folder")
            button.setAccessibleName(title + " 파일 찾아보기")
            button.clicked.connect(lambda _checked=False, field=edit, name=title: self._pick_file(field, name + " 파일 고르기"))
            self.file_buttons.append(button)
            row.addWidget(button)
            card_layout.addLayout(row)
            files.addWidget(card, 1)
        tickets.addLayout(files)
        layout.addWidget(board)

        actions = QHBoxLayout()
        actions.setSpacing(16)
        self.load_button = self._button("불러오기", "arrow", "primary")
        self.load_button.setMinimumHeight(38)
        self.load_button.setMinimumWidth(128)
        self.load_button.clicked.connect(self.start_load)
        actions.addWidget(self.load_button)
        self.progress = ProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        actions.addWidget(self.progress, 1)
        self.data_summary = _label("불러오면 파일 상태가 아래에 표시됩니다.", "muted", True)
        actions.addWidget(self.data_summary, 1)
        layout.addLayout(actions)

        self.quality_panel = QFrame()
        self.quality_panel.setProperty("role", "panel")
        self.quality_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        quality = QVBoxLayout(self.quality_panel)
        quality.setContentsMargins(22, 18, 22, 16)
        quality.setSpacing(14)
        cells = QHBoxLayout()
        cells.setSpacing(0)
        self.quality_values = {}
        for index, (key, caption) in enumerate((("dongs", "행정동"), ("days", "기간"),
                                                ("coverage", "관측 완전성"), ("duplicates", "제외한 중복 행"))):
            if index:
                cells.addSpacing(20)
                cells.addWidget(_separator(True))
                cells.addSpacing(20)
            cell, value, note = stat_cell(caption)
            self.quality_values[key] = (value, note)
            cells.addLayout(cell, 1)
        quality.addLayout(cells)
        quality.addWidget(_label("완전성은 파일에 있는 행정동과 첫날~마지막 날을 기준으로 셉니다. "
                                 "파일에 아예 없는 행정동은 이 비율에 드러나지 않습니다.", "caption", True))
        self.quality_panel.hide()
        layout.addWidget(self.quality_panel)
        layout.addStretch()
        return self._scroll_page(contents)

    # ── 비교 리포트 ──────────────────────────────────────────────────
    def _build_report_page(self) -> SmoothScrollArea:
        contents = QWidget()
        layout = QHBoxLayout(contents)
        layout.setContentsMargins(28, 12, 28, 24)
        layout.setSpacing(20)
        summary = QFrame()
        summary.setObjectName("reportSummary")
        summary.setFixedWidth(292)
        row = QVBoxLayout(summary)
        row.setContentsMargins(22, 24, 22, 24)
        row.setSpacing(18)
        row.addWidget(_label("비교 요약", "section"))
        self.comparison_values = {}
        for key, caption in (("similarity", "하루 흐름 유사도"), ("gap", "차이가 가장 큰 시간"), ("difference", "일평균 인구 차이")):
            row.addWidget(_separator())
            cell, value, note = stat_cell(caption)
            self.comparison_values[key] = (value, note)
            row.addLayout(cell)
        self.report_button = self._button("리포트 저장", "download", "primary")
        self.report_button.setEnabled(False)
        self.report_button.clicked.connect(self._export_report)
        row.addWidget(self.report_button)
        row.addWidget(_label("생활인구는 특정 시간에 해당 지역에 존재하는 인구 추정치입니다. 방문자 수나 실제 이동량이 아닙니다.", "caption", True))
        row.addStretch()
        layout.addWidget(summary, 0, Qt.AlignTop)
        self.comparison_note = self.comparison_values["similarity"][1]
        self.comparison_note.setText("데이터를 불러오면 표시됩니다.")
        notes = QVBoxLayout()
        self.report_table = ComparisonTable()
        self.report_table.chartRequested.connect(self._open_analysis)
        notes.addWidget(self.report_table)
        notes.addStretch()
        layout.addLayout(notes, 1)
        return self._scroll_page(contents)

    def _open_analysis(self, index):
        self.tabs.setCurrentIndex(index)
        self._show_page(0)
        self.dashboard_scroll.ensureWidgetVisible(self.chart_panel)

    def _update_intelligence(self):
        left, right = self._hotplaces()
        self.report_button.setEnabled(bool(left and right))
        if left is None or right is None:
            return
        comparison = compare_places(left, right)
        correlation = comparison["correlation"]
        value, note = self.comparison_values["similarity"]
        value.setText(display(correlation, digits=2))
        note.setText(f"{similarity_label(correlation)} · 시간대별 평균의 상관계수 "
                     f"(공통 {comparison['common_hours']}시간)")

        value, note = self.comparison_values["gap"]
        gap = comparison["largest_gap"]
        if gap and gap[1]:
            value.setText(f"{gap[0]}시")
            note.setText(f"{'A' if gap[1] > 0 else 'B'}가 {abs(gap[1]):,.0f}명 더 많음")
        else:
            value.setText("—")
            note.setText("시간대별 차이가 없습니다")

        value, note = self.comparison_values["difference"]
        a, b = left.summary()["daily_avg"], right.summary()["daily_avg"]
        if math.isfinite(a) and math.isfinite(b) and a != b:
            larger, big, small = ("A", a, b) if a > b else ("B", b, a)
            value.setText(f"{big - small:,.0f}명")
            note.setText(f"{larger}가 {(big / small - 1) * 100:.1f}% 더 많음" if small > 0 else f"{larger}가 더 많음")
        else:
            value.setText("—" if not (math.isfinite(a) and math.isfinite(b)) else "0명")
            note.setText("비교할 수 없습니다" if value.text() == "—" else "차이가 없습니다")

        self.report_table.set_regions(left.label, right.label)
        columns = [insight_cards(place, self.codebook) for place in (left, right)]
        self.report_table.set_rows([
            (title, definition, ROW_CHARTS.get(key), (a.title, a.detail), (b.title, b.detail))
            for (key, title, definition), a, b in zip(ROWS, *columns)
        ])

    def _export_report(self):
        left, right = self._hotplaces()
        if left is None or right is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "리포트 저장", "생활인구_비교_리포트.txt", "텍스트 (*.txt)")
        if path:
            try:
                Path(path).write_text(report_text(left, right, self.codebook), encoding="utf-8")
            except OSError as exc:
                QMessageBox.critical(self, "저장하지 못했습니다", str(exc))
                return
            self.status.setText(f"리포트를 저장했습니다: {path}")

    def _set_motion_text(self) -> None:
        self.motion_button.setText("애니메이션 끄기" if motion_enabled() else "애니메이션 켜기")

    def _toggle_motion(self, checked):
        QApplication.instance().setProperty("reducedMotion", checked)
        self._set_motion_text()
        if checked:
            for stack in self.findChildren(AnimatedStack):
                stack.stop_transition()
            self.tabs.finish_motion()

    @staticmethod
    def _update_path_hint(field: QLineEdit, value: str) -> None:
        field.setToolTip(value)
        if not field.hasFocus():
            field.setCursorPosition(len(value))
            field.deselect()

    def _refresh_theme_controls(self) -> None:
        for button, icon, primary in self._icon_buttons:
            button.setIcon(make_icon(icon, theme().on_accent if primary else theme().ink_soft))
        kitty = make_icon("kitty", size=128)
        self.setWindowIcon(kitty)
        QApplication.instance().setWindowIcon(kitty)
        self.brand_icon.setPixmap(make_icon("kitty", size=32).pixmap(QSize(32, 28)))
        dark = theme() is DARK
        self.theme_button.setText("밝은 테마" if dark else "어두운 테마")
        self.theme_button.setIcon(make_icon("sun" if dark else "moon"))
        self.motion_button.setIcon(make_icon("pulse"))
        self.welcome_icon.setPixmap(make_icon("kitty", size=132).pixmap(QSize(132, 100)))
        for item, icon in self.nav_items:
            item.setIcon(make_icon(icon))
        for page in self.tab_pages:
            page.refresh_icons()
        self.tabs.finish_motion()

    def _toggle_theme(self) -> None:
        for stack in self.findChildren(AnimatedStack):
            stack.stop_transition()
        apply_theme(QApplication.instance(), theme() is not DARK)
        self._refresh_theme_controls()
        if self.population:
            self._render_current()
            self._update_intelligence()

    def _prefill_paths(self) -> None:
        """기본 데이터 폴더를 찾아 경로 칸을 미리 채운다."""
        self._refresh_welcome_hint()
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
            self.status.setText("기본 데이터 폴더에서 두 파일을 찾았습니다.")
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
            QMessageBox.warning(self, "파일 경로 필요", "생활인구 CSV와 행정동 코드표 경로를 모두 입력하세요.")
            return

        self.load_button.setEnabled(False)
        self.load_button.setText("불러오는 중…")
        self.data_badge.setText("불러오는 중")
        self.status.setText("CSV 파일을 확인하고 있습니다…")
        for widget in (self.population_edit, self.code_edit, *self.file_buttons):
            widget.setEnabled(False)
        self.data_summary.hide()
        self.progress.setValue(0)
        self.progress.show()

        self._thread = QThread(self)
        self._worker = LoadWorker(population_csv, code_csv)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.failed.connect(self._on_failed)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _finish_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self.load_button.setEnabled(True)
        self.load_button.setText("다시 불러오기" if self.population else "불러오기")
        self.progress.hide()
        self.data_summary.show()
        for widget in (self.population_edit, self.code_edit, *self.file_buttons):
            widget.setEnabled(True)

    @Slot(int, str)
    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status.setText(message)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._finish_thread()
        self.data_badge.setText(f"{len(self.population.aggregates):,}개 행정동" if self.population else "불러오기 실패")
        self.data_summary.setText(f"불러오지 못했습니다. {message}")
        self.status.setText(f"오류: {message}")
        if self._closing:
            self.close()
            return
        QMessageBox.critical(self, "데이터를 불러오지 못했습니다", message)

    @Slot(object, object)
    def _on_loaded(self, population: Population, codebook: CodeBook) -> None:
        was_loading = self._thread is not None
        self._finish_thread()
        if self._closing:
            self.close()
            return
        self.population = population
        self.codebook = codebook
        self.data_badge.setText(f"{len(population.aggregates):,}개 행정동")
        self.period_label.setText(_period(population))
        self.load_button.setText("다시 불러오기")

        self.region_a.blockSignals(True)
        self.region_b.blockSignals(True)
        self.region_a.populate(codebook, population)
        self.region_b.populate(codebook, population)
        for widget in (self.search_edit, self.search_button, self.top_button,
                       self.summary_button, self.swap_button, self.search_target):
            widget.setEnabled(True)

        # 지역 A/B 가 같은 곳이면 비교 그래프가 의미 없으니 B는 다른 동으로 옮겨 둔다.
        ranking = rank_by_daily_average(population, codebook, top=2)
        if ranking:
            self.region_a.set_dong(ranking[0][0])
            self.region_b.set_dong(ranking[-1][0])
        self.region_a.blockSignals(False)
        self.region_b.blockSignals(False)

        count = len(population.aggregates)
        self.status.setText(f"{count:,}개 행정동 · {_period(population)} 데이터를 불러왔습니다.")
        self.data_summary.setText(f"{Path(population.source).name if population.source else '생활인구'}를 불러왔습니다.")
        quality = population.quality(codebook)
        cells = {
            "dongs": (f"{count:,}곳", f"코드표와 맞지 않는 코드 {quality['unmatched']:,}개"),
            "days": (f"{population.n_days}일",
                     f"{_period(population)} · 평일 {population.n_weekday}일, 주말 {population.n_weekend}일"),
            "coverage": (f"{quality['coverage']:.1%}",
                         f"{quality['observed']:,} / {quality['expected']:,}시간 관측 · 빠진 시간 {quality['missing']:,}"),
            "duplicates": (f"{quality['duplicates']:,}행", "같은 날짜·시간·행정동이 반복된 행은 첫 행만 씁니다"),
        }
        for key, (value, note) in cells.items():
            self.quality_values[key][0].setText(value)
            self.quality_values[key][1].setText(note)
        self.quality_panel.show()
        self._refresh_ranking()
        self.analysis_state.setCurrentIndex(1)
        self._on_region_changed()
        self._show_page(0)
        if was_loading:
            InfoBar.success("불러오기 완료", f"{count:,}개 행정동 · 비교할 두 지역을 고르세요.",
                            duration=2500, position=InfoBarPosition.TOP_RIGHT, parent=self)

    # ── 행정동 선택 ──────────────────────────────────────────────────
    def _search_dong(self) -> None:
        if self.codebook is None:
            return
        name = self.search_edit.text().strip()
        if not name:
            return
        matches = [d for d in self.codebook.search(name) if self.population.has(d.code)]
        if not matches:
            self.status.setText(f"‘{name}’에 해당하는 행정동이 없습니다.")
            QMessageBox.information(self, "검색 결과 없음", f"‘{name}’에 해당하는 행정동이 없습니다.")
            return
        if len(matches) == 1:
            chosen = matches[0]
        else:
            dialog = DongPickDialog(matches, self)
            if dialog.exec() != QDialog.Accepted:
                return
            chosen = dialog.selected()
            if chosen is None:
                return
        target = self._search_selector()
        target.set_dong(chosen)
        self.status.setText(f"{self.search_target.currentText()}에 {chosen.label}을 넣었습니다.")
        self._show_page(0)

    def _search_selector(self) -> RegionSelector:
        return self.region_a if self.search_target.currentIndex() == 0 else self.region_b

    def _on_region_changed(self) -> None:
        self._results.clear()
        self._update_summary()
        self._render_current()
        self._update_intelligence()

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
    def _render_current(self, *_args) -> None:
        index = self.tabs.currentIndex()
        page = self.tab_pages[index]
        place_a, place_b = self._hotplaces()
        self.chart_panel.setMinimumHeight(CHART_HEIGHTS.get(index, 650))
        self.chart_title.setText(CHART_TITLES[index])
        self.save_png_button.setEnabled(False)
        self.export_csv_button.setEnabled(False)
        page.toolbar.setVisible(False)

        if place_a is None or place_b is None:
            self.chart_note.setText("")
            page.canvas.message("비교할 두 지역을 고르세요", "데이터를 불러오면 지역 A와 B를 같은 기준으로 비교합니다.")
            return

        result = self._results.get(index)
        if result is None:
            method = f"analysis{index + 1}"
            if index in PAIR_TABS:
                result = getattr(place_a, method)(place_b)
            elif index == CITY_TAB:
                result = place_a.analysis14(place_b, self.codebook)
            else:
                result = PairedAnalysis(
                    title=f"{place_a.label} · {place_b.label} {TAB_TITLES[index]} 비교",
                    regions=(place_a.label, place_b.label),
                    analyses=(getattr(place_a, method)(), getattr(place_b, method)()),
                    note=self.population.period,
                )
            self._results[index] = result

        page.hint = CHART_HINTS.get(index, READOUT_HINT)
        draw_result(page.canvas, result, show_heading=False)
        page.readout.setText(page.hint)
        self.chart_note.setText(result.analyses[0].note if isinstance(result, PairedAnalysis) else result.note)
        page.toolbar.setVisible(True)
        page.toolbar.update()
        self.save_png_button.setEnabled(True)
        self.export_csv_button.setEnabled(True)

    def _update_summary(self) -> None:
        place_a, place_b = self._hotplaces()
        self.metrics_a.update_place(place_a)
        self.metrics_b.update_place(place_b)
        for place, field in ((place_a, self.insight_a), (place_b, self.insight_b)):
            field.setText(f"{place.name} · {place.summary()['character']}" if place else "—")
        self.summary_button.setEnabled(place_a is not None or place_b is not None)
        self.swap_button.setEnabled(place_a is not None and place_b is not None)
        self.overview_note.setVisible(bool(place_a and place_b and place_a.code == place_b.code))

    def _show_summary(self) -> None:
        places = self._hotplaces()
        if not any(places):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("상세 통계")
        dialog.resize(1080, 580)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(_label("상세 통계", "heading"))
        layout.addWidget(_label("텍스트를 드래그해서 복사할 수 있습니다.", "muted"))
        columns = QHBoxLayout()
        columns.setSpacing(16)
        for index, place in enumerate(places):
            column = QVBoxLayout()
            column.addWidget(_label(f"지역 {'AB'[index]}", "regionTag" if index == 0 else "regionTagB"))
            summary_view = QPlainTextEdit()
            summary_view.setReadOnly(True)
            summary_view.setLineWrapMode(QPlainTextEdit.NoWrap)
            summary_view.setFont(_mono_font())
            summary_view.setPlainText(summary_text(place) if place else "행정동을 고르세요.")
            column.addWidget(summary_view, 1)
            columns.addLayout(column, 1)
        layout.addLayout(columns, 1)
        layout.addWidget(_label("상권 유형은 낮/밤·주말/평일 배율과 가장 붐비는 시간으로 나눈 참고값입니다.", "caption"))
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("닫기")
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # ── 내보내기 ─────────────────────────────────────────────────────
    def _save_png(self) -> None:
        index = self.tabs.currentIndex()
        result = self._results.get(index)
        if result is None:
            QMessageBox.information(self, "PNG 저장", "저장할 차트가 아직 없습니다.")
            return
        default = f"{self._slug(result.title)}.png"
        path, _ = QFileDialog.getSaveFileName(self, "PNG 저장", default, "PNG 이미지 (*.png)")
        if not path:
            return
        canvas = self.tab_pages[index].canvas
        canvas.clear_hover()
        try:
            canvas.figure.savefig(path, dpi=200, facecolor=theme().surface)
        except OSError as exc:
            QMessageBox.critical(self, "저장하지 못했습니다", str(exc))
            return
        self.status.setText(f"차트를 저장했습니다: {path}")

    def _export_csv(self) -> None:
        index = self.tabs.currentIndex()
        result = self._results.get(index)
        if result is None:
            QMessageBox.information(self, "CSV 저장", "저장할 차트가 아직 없습니다.")
            return
        default = f"{self._slug(result.title)}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "CSV 저장", default, "CSV 파일 (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(result.csv_rows())
        except OSError as exc:
            QMessageBox.critical(self, "저장하지 못했습니다", str(exc))
            return
        self.status.setText(f"CSV를 저장했습니다: {path}")

    @staticmethod
    def _slug(title: str) -> str:
        return "".join(c if c.isalnum() or c in "가-힣" or ord(c) > 127 else "_" for c in title).strip("_")

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._closing = True
            self._thread.requestInterruption()
            self.status.setText("불러오기를 멈추고 종료합니다…")
            event.ignore()
            return
        super().closeEvent(event)


def run(population_csv=None, code_csv=None) -> int:
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # 시스템이 다크 모드면 그래프도 어두운 테마로 (창 배경 밝기로 판단).
    set_theme(app.palette().color(QPalette.Window).lightness() < 128)
    window = MainWindow()
    if population_csv:
        window.population_edit.setText(population_csv)
    if code_csv:
        window.code_edit.setText(code_csv)
    window.show()
    return app.exec()
