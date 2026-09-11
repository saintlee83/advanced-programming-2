"""Fluent 위젯으로 구성한 서울 생활인구 분석 작업 공간.

데이터 연결, 지역 탐색, 비교 분석을 서로 독립된 페이지로 제공한다.
CSV 로딩과 계산·내보내기는 기존 Python 모델을 사용한다.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PyQt5.QtCore import QObject, QSize, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPalette
from PyQt5.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QSizePolicy,
    QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    ComboBox, InfoBar, InfoBarPosition, LineEdit, PopUpAniStackedWidget,
    PrimaryPushButton, ProgressBar, PushButton, SearchLineEdit, SmoothScrollArea,
    TableWidget, TransparentPushButton, TransparentToolButton,
)

from .dataset import (
    CodeBook, DataError, Dong, Population, default_data_dir,
    find_population_csv, load_population,
)
from .hotplace import Hotplace, LineSeries, PairedAnalysis, rank_by_daily_average, summary_text
from .plotting import draw_line_series, draw_paired_analysis, set_theme, theme
from .theme import DARK, apply_theme, make_icon
from .widgets import (
    AnalysisTab, AnalysisTabs, CityIllustration, ComparisonMetrics, NavigationItem,
    label as _label, region_badge, separator as _separator,
)

TAB_TITLES = ("시간대별 추이", "평일 · 주말", "성별 분포", "추이 겹쳐보기", "연령별 분포")
OVERLAY_TAB = 3


def _mono_font(point_size: int = 11) -> QFont:
    font = QFont("Menlo", point_size)
    font.setStyleHint(QFont.Monospace)
    return font


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


class RegionSelector(QFrame):
    """자치구 + 행정동 콤보 한 쌍."""

    changed = pyqtSignal()

    def __init__(self, caption: str, parent=None) -> None:
        super().__init__(parent)
        self._codebook: CodeBook | None = None
        self._population: Population | None = None
        self._loading = False

        self.setProperty("role", "regionSelector")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(region_badge(caption))
        self.sigungu, self.dong = ComboBox(), ComboBox()
        for widget, text in ((self.sigungu, "자치구"), (self.dong, "행정동")):
            widget.setFont(QApplication.font())
            widget.setAccessibleName(f"{caption} {text}")
            widget.setPlaceholderText(f"{text} 선택")
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumWidth(88)
            layout.addWidget(widget, 1)

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
        self._results: dict[int, LineSeries | PairedAnalysis] = {}
        self._build_ui()
        self._prefill_paths()

    def _build_ui(self) -> None:
        self.setObjectName("mainWindow")
        self.setWindowTitle("Hotplace — 서울 생활인구 분석")
        self.resize(1480, 960)
        self.setMinimumSize(1080, 740)
        self._icon_buttons = []
        apply_theme(QApplication.instance(), theme() is DARK)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_navigation())
        workspace = QVBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(0)
        workspace.addWidget(self._build_topbar())
        self.workspace_stack = PopUpAniStackedWidget()
        self.workspace_stack.addWidget(self._build_analysis_page(), deltaY=16)
        self.workspace_stack.addWidget(self._build_explore_page(), deltaY=16)
        self.workspace_stack.addWidget(self._build_data_page(), deltaY=16)
        workspace.addWidget(self.workspace_stack, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(32, 8, 32, 12)
        self.status = _label("CSV 파일을 연결하면 분석을 시작할 수 있습니다.", "caption", True)
        footer.addWidget(self.status, 1)
        footer.addWidget(_label("SEOUL LIVING POPULATION", "eyebrow"))
        workspace.addLayout(footer)
        root.addLayout(workspace, 1)
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
        rail = QFrame()
        rail.setObjectName("navigationRail")
        rail.setFixedWidth(204)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(16, 28, 16, 22)
        layout.setSpacing(8)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 0)
        brand.setSpacing(9)
        mark = QLabel()
        mark.setObjectName("brandMark")
        mark.setFixedSize(31, 31)
        mark.setAlignment(Qt.AlignCenter)
        mark.setPixmap(make_icon("pulse", "#ffffff", 19).pixmap(QSize(19, 19)))
        brand.addWidget(mark)
        brand.addWidget(_label("hotplace", "brand"))
        brand.addStretch()
        layout.addLayout(brand)
        subtitle = _label("서울 생활인구 데이터 스튜디오", "caption")
        subtitle.setContentsMargins(8, 4, 0, 0)
        layout.addWidget(subtitle)
        layout.addSpacing(34)
        eyebrow = _label("WORKSPACE", "eyebrow")
        eyebrow.setContentsMargins(12, 0, 0, 8)
        layout.addWidget(eyebrow)
        self.nav_items = []
        for index, (title, icon) in enumerate((("비교 분석", "chart"), ("지역 탐색", "search"), ("데이터 연결", "folder"))):
            button = NavigationItem(make_icon(icon), title)
            button.clicked.connect(lambda _checked=False, i=index: self._show_page(i))
            layout.addWidget(button)
            self.nav_items.append((button, icon))
        layout.addStretch()
        layout.addWidget(_separator())
        layout.addSpacing(10)
        self.theme_button = self._button("어두운 테마", "moon", "quiet")
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button)
        caption = _label("시간과 지역으로 읽는\n도시의 새로운 표정", "caption", True)
        caption.setContentsMargins(12, 12, 0, 0)
        layout.addWidget(caption)
        return rail

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(32, 16, 32, 16)
        layout.setSpacing(12)
        layout.addWidget(_label("워크스페이스", "muted"))
        layout.addWidget(_label("/", "caption"))
        self.breadcrumb = _label("비교 분석", "field")
        layout.addWidget(self.breadcrumb)
        layout.addStretch()
        self.data_badge = _label("○  데이터 연결 전", "badge")
        layout.addWidget(self.data_badge)
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
        self.workspace_stack.setCurrentIndex(index, duration=200)
        self.breadcrumb.setText(("비교 분석", "지역 탐색", "데이터 연결")[index])
        for i, (item, _icon) in enumerate(self.nav_items):
            item.setSelected(i == index)

    def _build_analysis_page(self) -> QStackedWidget:
        self.analysis_state = QStackedWidget()
        self.analysis_state.addWidget(self._build_welcome())
        dashboard = QWidget()
        main = QVBoxLayout(dashboard)
        main.setContentsMargins(32, 26, 32, 12)
        main.setSpacing(18)
        main.setSizeConstraint(QLayout.SetMinimumSize)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        self.overview_title = _label("지역 비교", "title")
        self.overview_note = _label("서로 다른 두 지역의 하루를 같은 기준으로 살펴보세요.", "muted")
        titles.addWidget(self.overview_title)
        titles.addWidget(self.overview_note)
        heading.addLayout(titles)
        heading.addStretch()
        self.period_label = _label("분석 기간 —", "muted")
        heading.addWidget(self.period_label, 0, Qt.AlignVCenter)
        main.addLayout(heading)

        selectors = QHBoxLayout()
        selectors.setSpacing(12)
        self.region_a = RegionSelector("지역 A")
        self.region_b = RegionSelector("지역 B")
        self.region_a.changed.connect(self._on_region_changed)
        self.region_b.changed.connect(self._on_region_changed)
        selectors.addWidget(self.region_a, 1)
        self.swap_button = self._button("", "compare", "quiet")
        self.swap_button.setFixedSize(36, 36)
        self.swap_button.setToolTip("지역 A와 B 바꾸기")
        self.swap_button.setAccessibleName("지역 A와 B 바꾸기")
        self.swap_button.setEnabled(False)
        self.swap_button.clicked.connect(self._swap_regions)
        selectors.addWidget(self.swap_button)
        selectors.addWidget(self.region_b, 1)
        self.top_button = self._button("지역 찾기", "search")
        self.top_button.setEnabled(False)
        self.top_button.clicked.connect(lambda: self._show_page(1))
        selectors.addWidget(self.top_button)
        main.addLayout(selectors)

        metrics = ComparisonMetrics()
        self.metrics_a, self.metrics_b = metrics.region_a, metrics.region_b
        main.addWidget(metrics)
        main.addWidget(self._build_chart_panel(), 1)
        main.addWidget(self._build_insights())
        self.dashboard_scroll = self._scroll_page(dashboard)
        self.analysis_state.addWidget(self.dashboard_scroll)
        return self.analysis_state

    def _build_welcome(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 32, 48, 32)
        layout.setSpacing(16)
        layout.addStretch()
        self.city_art = CityIllustration()
        layout.addWidget(self.city_art, 0, Qt.AlignHCenter)
        eyebrow = _label("DISCOVER THE RHYTHM OF SEOUL", "eyebrow")
        layout.addWidget(eyebrow, 0, Qt.AlignHCenter)
        layout.addWidget(_label("서울의 하루, 지역의 차이", "welcomeTitle"), 0, Qt.AlignHCenter)
        note = _label("두 지역의 생활인구를 나란히 비교하고,\n시간·요일·성별·연령에 담긴 패턴을 발견하세요.", "muted", True)
        note.setAlignment(Qt.AlignCenter)
        layout.addWidget(note)
        layout.addSpacing(10)
        self.connect_button = self._button("데이터 연결하고 시작하기", "arrow", "primary")
        self.connect_button.setMinimumHeight(42)
        self.connect_button.clicked.connect(lambda: self._show_page(2))
        layout.addWidget(self.connect_button, 0, Qt.AlignHCenter)
        layout.addWidget(_label("생활인구 CSV + 행정동 코드표로 시작합니다.", "caption"), 0, Qt.AlignHCenter)
        layout.addStretch()
        layout.addStretch()
        return page

    def _build_chart_panel(self) -> QFrame:
        self.chart_panel = QFrame()
        self.chart_panel.setObjectName("chartPanel")
        layout = QVBoxLayout(self.chart_panel)
        layout.setContentsMargins(22, 18, 22, 14)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        self.chart_title = _label("시간대별 생활인구", "section")
        heading.addWidget(self.chart_title)
        heading.addStretch()
        self.save_png_button = self._button("이미지 저장", "download", "quiet")
        self.save_png_button.clicked.connect(self._save_png)
        self.export_csv_button = self._button("CSV 내보내기", "export")
        self.export_csv_button.clicked.connect(self._export_csv)
        for button in (self.save_png_button, self.export_csv_button):
            button.setEnabled(False)
            heading.addWidget(button)
        layout.addLayout(heading)
        self.tabs = AnalysisTabs(TAB_TITLES)
        self.tab_pages = self.tabs.pages
        self.tabs.currentChanged.connect(self._render_current)
        layout.addWidget(self.tabs, 1)
        return self.chart_panel

    def _build_insights(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("insightStrip")
        row = QHBoxLayout(panel)
        row.setContentsMargins(16, 10, 12, 10)
        row.setSpacing(14)
        self.insight_icon = QLabel()
        self.insight_icon.setFixedSize(18, 18)
        row.addWidget(self.insight_icon)
        row.addWidget(_label("지역 인사이트", "field"))
        self.insight_a = _label("—", "muted", True)
        self.insight_b = _label("—", "muted", True)
        row.addWidget(self.insight_a, 1)
        row.addWidget(self.insight_b, 1)
        self.summary_button = self._button("상세 통계", "info", "quiet")
        self.summary_button.setEnabled(False)
        self.summary_button.clicked.connect(self._show_summary)
        row.addWidget(self.summary_button)
        return panel

    def _build_explore_page(self) -> SmoothScrollArea:
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(20)
        layout.addWidget(_label("지역 탐색", "title"))
        layout.addWidget(_label("궁금한 행정동을 검색하거나, 생활인구가 많은 지역부터 살펴보세요.", "muted", True))
        search = QHBoxLayout()
        search.setSpacing(12)
        self.search_edit = SearchLineEdit()
        self.search_edit.setFont(QApplication.font())
        self.search_edit.setPlaceholderText("행정동 검색 · 예: 역삼1동, 서교동")
        self.search_edit.setAccessibleName("행정동명 검색")
        self.search_edit.setMinimumHeight(40)
        self.search_edit.searchSignal.connect(lambda _text: self._search_dong())
        self.search_button = self.search_edit.searchButton
        self.search_button.setAccessibleName("행정동 검색")
        search.addWidget(self.search_edit, 1)
        search.addWidget(_label("선택할 지역", "muted"))
        self.search_target = ComboBox()
        self.search_target.setFont(QApplication.font())
        self.search_target.addItems(["지역 A", "지역 B"])
        self.search_target.setAccessibleName("검색 및 순위로 선택할 지역")
        self.search_target.setFixedWidth(120)
        search.addWidget(self.search_target)
        layout.addLayout(search)
        panel = QFrame()
        panel.setObjectName("rankingPanel")
        ranking = QVBoxLayout(panel)
        ranking.setContentsMargins(22, 20, 22, 16)
        ranking.setSpacing(14)
        heading = QHBoxLayout()
        heading.addWidget(_label("생활인구 TOP 20", "section"))
        heading.addStretch()
        self.ranking_caption = _label("데이터 연결 후 순위가 표시됩니다.", "caption")
        heading.addWidget(self.ranking_caption)
        ranking.addLayout(heading)
        self.rank_table = TableWidget()
        self.rank_table.setColumnCount(4)
        self.rank_table.setHorizontalHeaderLabels(["순위", "자치구", "행정동", "일평균 생활인구"])
        self.rank_table.verticalHeader().hide()
        self.rank_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rank_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rank_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.rank_table.setColumnWidth(0, 70)
        self.rank_table.setColumnWidth(1, 160)
        self.rank_table.setColumnWidth(3, 190)
        self.rank_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.rank_table.setMinimumHeight(340)
        self.rank_table.cellDoubleClicked.connect(lambda row, _column: self._choose_rank(row))
        ranking.addWidget(self.rank_table, 1)
        actions = QHBoxLayout()
        actions.addWidget(_label("행을 두 번 클릭하거나 선택 후 버튼을 눌러 비교에 추가하세요.", "caption", True), 1)
        self.rank_select_button = self._button("선택한 지역 비교하기", "arrow", "primary")
        self.rank_select_button.setEnabled(False)
        self.rank_select_button.clicked.connect(lambda: self._choose_rank(self.rank_table.currentRow()))
        actions.addWidget(self.rank_select_button)
        ranking.addLayout(actions)
        layout.addWidget(panel, 1)
        for widget in (self.search_edit, self.search_target):
            widget.setEnabled(False)
        return self._scroll_page(contents)

    def _refresh_ranking(self) -> None:
        ranking = rank_by_daily_average(self.population, self.codebook, top=20)
        self.rank_table.setRowCount(len(ranking))
        for row, (dong, value) in enumerate(ranking):
            for column, text in enumerate((f"{row + 1:02d}", dong.sigungu, dong.name, f"{value:,.0f} 명")):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, dong)
                if column == 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.rank_table.setItem(row, column, item)
            self.rank_table.setRowHeight(row, 48)
        self.ranking_caption.setText(f"{len(self.population.aggregates):,}개 행정동 중 일평균 인구 기준")
        self.rank_select_button.setEnabled(bool(ranking))
        if ranking:
            self.rank_table.selectRow(0)

    def _choose_rank(self, row: int) -> None:
        item = self.rank_table.item(row, 0)
        if item is None:
            return
        dong = item.data(Qt.UserRole)
        self._search_selector().set_dong(dong)
        self.status.setText(f"{self.search_target.currentText()}: {dong.label}을 선택했습니다.")
        self._show_page(0)

    def _build_data_page(self) -> SmoothScrollArea:
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.setContentsMargins(40, 34, 40, 32)
        layout.setSpacing(18)
        layout.addWidget(_label("데이터 연결", "title"))
        layout.addWidget(_label("서울 생활인구 데이터와 행정동 코드표를 연결하세요.", "muted", True))
        layout.addSpacing(10)
        self.population_edit, self.code_edit = LineEdit(), LineEdit()
        self.file_buttons = []
        for number, title, note, edit in (
            ("01", "생활인구 데이터", "날짜·시간·행정동별 인구가 담긴 LOCAL_PEOPLE_DONG CSV", self.population_edit),
            ("02", "행정동 코드표", "행정동 코드와 지역명을 연결하는 dong_code CSV", self.code_edit),
        ):
            card = QFrame()
            card.setProperty("role", "fileCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(24, 22, 24, 22)
            card_layout.setSpacing(12)
            heading = QHBoxLayout()
            heading.addWidget(_label(number, "badge"))
            heading.addWidget(_label(title, "section"))
            heading.addStretch()
            card_layout.addLayout(heading)
            card_layout.addWidget(_label(note, "muted", True))
            row = QHBoxLayout()
            edit.setFont(QApplication.font())
            edit.setMinimumHeight(38)
            edit.setPlaceholderText("CSV 파일을 선택하거나 경로를 입력하세요.")
            edit.setAccessibleName(title + " 파일 경로")
            edit.textChanged.connect(lambda text, field=edit: self._update_path_hint(field, text))
            row.addWidget(edit, 1)
            button = self._button("파일 선택", "folder")
            button.setAccessibleName(title + " 찾아보기")
            button.clicked.connect(lambda _checked=False, field=edit, name=title: self._pick_file(field, name + " 파일 선택"))
            self.file_buttons.append(button)
            row.addWidget(button)
            card_layout.addLayout(row)
            layout.addWidget(card)
        self.progress = ProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.data_summary = _label("두 파일을 불러오면 지역 선택과 5가지 비교 분석을 사용할 수 있습니다.", "muted", True)
        layout.addWidget(self.data_summary)
        actions = QHBoxLayout()
        self.load_button = self._button("데이터 불러오기", "arrow", "primary")
        self.load_button.setMinimumHeight(42)
        self.load_button.clicked.connect(self.start_load)
        actions.addWidget(self.load_button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()
        return self._scroll_page(contents)

    @staticmethod
    def _update_path_hint(field: QLineEdit, value: str) -> None:
        field.setToolTip(value)
        if not field.hasFocus():
            field.setCursorPosition(len(value))
            field.deselect()

    def _refresh_theme_controls(self) -> None:
        for button, icon, primary in self._icon_buttons:
            button.setIcon(make_icon(icon, theme().on_accent if primary else theme().ink_soft))
        dark = theme() is DARK
        self.theme_button.setText("밝은 테마" if dark else "어두운 테마")
        self.theme_button.setIcon(make_icon("sun" if dark else "moon"))
        self.theme_button.setAccessibleName(self.theme_button.text())
        self.insight_icon.setPixmap(make_icon("spark", theme().accent, 18).pixmap(QSize(18, 18)))
        for item, icon in self.nav_items:
            item.setIcon(make_icon(icon))
        for page in self.tab_pages:
            page.refresh_icons()
        self.city_art.update()

    def _toggle_theme(self) -> None:
        apply_theme(QApplication.instance(), theme() is not DARK)
        self._refresh_theme_controls()
        for index, page in enumerate(self.tab_pages):
            result = self._results.get(index)
            if result is not None:
                self._draw_result(page, result)
        if self.population:
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
        self.data_badge.setText("◌  데이터 연결 중")
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
        self.data_badge.setText("!  연결 실패 · 다시 시도")
        self.status.setText(f"오류: {message}")
        self._finish_thread()
        QMessageBox.critical(self, "데이터 오류", message)

    def _on_loaded(self, population: Population, codebook: CodeBook) -> None:
        was_loading = self._thread is not None
        self.progress.hide()
        self._finish_thread()
        self.population = population
        self.codebook = codebook
        self.data_badge.setText(f"●  {len(population.aggregates):,}개 행정동 연결됨")
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
        self.data_summary.setText(
            f"{len(population.aggregates):,}개 행정동 · {population.period} · "
            f"평일 {population.n_weekday}일 / 주말 {population.n_weekend}일 연결 완료"
        )
        self._refresh_ranking()
        self.analysis_state.setCurrentIndex(1)
        self._on_region_changed()
        self._show_page(0)
        if was_loading:
            InfoBar.success("데이터 연결 완료", "비교할 두 지역을 선택하세요.",
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
        self._show_page(0)

    def _search_selector(self) -> RegionSelector:
        return self.region_a if self.search_target.currentIndex() == 0 else self.region_b

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
            draw_paired_analysis(page.canvas, result, show_caption=False)
        else:
            draw_line_series(page.canvas, result, show_heading=False)

    def _render_current(self, *_args) -> None:
        index = self.tabs.currentIndex()
        page = self.tab_pages[index]
        place_a, place_b = self._hotplaces()
        self.chart_panel.setMinimumHeight(520 if index == 4 else 420)
        self.chart_title.setText(("시간대별 생활인구", "평일과 주말의 차이", "성별 생활인구", "두 지역의 하루", "연령별 인구 구조")[index])
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
        if index == 4:
            page.readout.setText("남자 인구는 왼쪽, 여자 인구는 오른쪽 · 두 지역에 같은 축 적용")
        page.toolbar.setVisible(True)
        page.toolbar.update()
        self.save_png_button.setEnabled(True)
        self.export_csv_button.setEnabled(True)

    def _update_summary(self) -> None:
        place_a, place_b = self._hotplaces()
        self.metrics_a.update_place(place_a)
        self.metrics_b.update_place(place_b)
        for index, (place, field) in enumerate(((place_a, self.insight_a), (place_b, self.insight_b))):
            field.setText(f"{'AB'[index]} · {place.name}  {place.summary()['character']}" if place else "—")
        self.summary_button.setEnabled(place_a is not None or place_b is not None)
        self.swap_button.setEnabled(place_a is not None and place_b is not None)
        same = place_a and place_b and place_a.code == place_b.code
        self.overview_note.setText("같은 지역을 선택했습니다. 두 결과가 동일합니다." if same
                                   else "서로 다른 두 지역의 하루를 같은 기준으로 살펴보세요.")

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
        canvas = self.tab_pages[index].canvas
        canvas.clear_hover()
        canvas.figure.savefig(path, dpi=200, facecolor=theme().surface)
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
