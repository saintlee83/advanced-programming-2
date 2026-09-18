"""서울 생활인구 비교 화면: 데이터 불러오기 → 차트 보기.
CSV 로딩과 계산·내보내기는 기존 Python 모델을 사용한다.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PyQt5.QtCore import (
    QLibraryInfo, QObject, QSize, QStandardPaths, Qt, QThread, QTimer, QTranslator, QUrl,
    pyqtSignal, pyqtSlot,
)
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractButton, QApplication, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLayout, QMessageBox, QPlainTextEdit, QSizePolicy,
    QSplitter, QStackedWidget, QTreeView, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    InfoBar, InfoBarPosition, PrimaryPushButton, ProgressBar, PushButton,
    ScrollArea, SmoothMode, TransparentPushButton,
)

from .dataset import (
    CodeBook, DataError, Dong, Population, default_data_dir, identify_csv, load_population,
)
from .hotplace import Hotplace, PairedAnalysis, rank_by_daily_average, summary_text
from .plotting import draw_result, theme
from .theme import apply_theme, kitty_pixmap, make_icon
from .widgets import (
    READOUT_HINT, AnalysisTabs, ComboBox, ComparisonMetrics, label as _label, region_badge,
)

# 차트 번호 i 는 Hotplace.analysis(i + 1) 에 대응한다.
TAB_TITLES = ("시간대", "평일·주말", "성별", "겹쳐 보기", "연령", "일별 추이", "요일×시간", "흐름 비교",
              "시간대별 차이", "요일별", "남녀 비율", "연령 비중", "연령×시간")
CHART_TITLES = ("시간대별 평균 인구", "평일과 주말의 시간대별 인구", "남녀 시간대별 인구", "두 지역을 한 차트에",
                "연령대별 인구 구성", "일별 평균과 7일 이동평균", "요일·시간대별 평균 인구", "하루 흐름 비교 (지역 평균 = 100)",
                "시간대별 인구 차이 (A − B)", "요일별 평균 인구", "시간대별 남녀 비율", "연령대별 비중 비교",
                "시간대별 연령 구성")
ALL_GROUPS = (
    ("하루 흐름", (0, 1, 3, 8, 7)),
    ("요일·날짜", (9, 6, 5)),
    ("성별·연령", (2, 10, 4, 11, 12)),
)
# 히트맵(요일×시간, 연령×시간)은 선택 목록에서 뺀다. 계산·그리기 코드는 남아 있어
# 이 집합에서 번호를 지우면 다시 나타난다.
DISABLED_CHARTS = frozenset({6, 12})
TAB_GROUPS = tuple(
    (name, tuple(chart for chart in charts if chart not in DISABLED_CHARTS))
    for name, charts in ALL_GROUPS
)
PAIR_TABS = {3, 7, 8, 11}      # 두 지역을 한 결과로 계산하는 분석
CHART_HEIGHTS = {4: 760, 6: 680, 11: 620, 12: 880}
# 차트 아래에 보여 줄 읽는 법. 없는 차트는 READOUT_HINT(마우스 판독 안내, 꺼져 있으면 빈칸)를 쓴다.
CHART_HINTS = {
    4: "왼쪽은 남자, 오른쪽은 여자 · 두 지역이 같은 축을 씁니다",
    6: "두 지역이 같은 색 범위를 씁니다",
    10: "실선은 여성, 점선은 남성 · 50% 선보다 위에 있는 쪽이 더 많습니다",
    12: "두 지역이 같은 색 범위를 씁니다",
}
PAGE_TITLE = "지역 비교"
PAGE_NOTE = "두 행정동의 생활인구를 같은 기준, 같은 축으로 비교합니다."
OVERLAY_TAB = 3
APP_NAME = "서울 생활인구 비교"
CSV_FILTER = "CSV 파일 (*.csv);;모든 파일 (*)"
# identify_csv() 가 돌려주는 파일 종류와 화면에 보여 줄 이름.
FILE_KINDS = {
    "population": "생활인구 CSV (LOCAL_PEOPLE_DONG_*.csv)",
    "codes": "행정동 코드표 (dong_code.csv)",
}


def _mono_font(point_size: int = 11) -> QFont:
    font = QFont("Menlo", point_size)
    font.setStyleHint(QFont.Monospace)
    return font


def _period(population: Population) -> str:
    return population.period.replace("-", ".").replace(" ~ ", " – ")


class LoadWorker(QObject):
    """CSV 읽기를 담당하는 워커. QThread 로 옮겨서 실행한다."""

    progress = pyqtSignal(int, str)
    loaded = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(self, population_csv: str, code_csv: str) -> None:
        super().__init__()
        self._population_csv = population_csv
        self._code_csv = code_csv

    @pyqtSlot()
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


class RegionSelector(QFrame):
    """자치구 + 행정동 콤보 한 쌍."""

    changed = pyqtSignal()

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
        # 파일 선택 창을 처음 열 폴더. 기본 데이터 폴더를 찾으면 거기서 시작한다.
        self._last_dir = str(default_data_dir() or "")
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("mainWindow")
        self.setWindowTitle(APP_NAME)
        self.resize(1480, 980)
        self.setMinimumSize(1080, 740)
        self._icon_buttons = []
        apply_theme(QApplication.instance(), False)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_topbar())
        self.pages = QStackedWidget()                  # 0: 데이터 불러오기, 1: 차트 보기
        self.pages.addWidget(self._build_welcome())
        self.pages.addWidget(self._build_dashboard())
        root.addWidget(self.pages, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(28, 10, 28, 12)
        self.status = _label("데이터를 불러오면 비교를 시작할 수 있습니다.", "caption", True)
        footer.addWidget(self.status, 1)
        root.addLayout(footer)
        self._refresh_theme_controls()

    def _button(self, text: str, icon: str, role: str = "") -> QAbstractButton:
        cls = PrimaryPushButton if role == "primary" else TransparentPushButton if role == "quiet" else PushButton
        button = cls(text)
        button.setFont(QApplication.font())
        button.setIconSize(QSize(16, 16))
        button.setMinimumHeight(34)
        button.setCursor(Qt.PointingHandCursor)
        self._icon_buttons.append((button, icon, role == "primary"))
        return button

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("appHeader")
        masthead = QHBoxLayout(header)
        masthead.setContentsMargins(28, 14, 28, 12)
        masthead.setSpacing(14)
        self.brand_icon = QLabel()
        self.brand_icon.setFixedSize(32, 28)
        self.brand_icon.setAlignment(Qt.AlignCenter)
        self.brand_icon.setAccessibleName("헬로키티")
        masthead.addWidget(self.brand_icon)
        masthead.addWidget(_label(APP_NAME, "brand"))
        masthead.addStretch()
        return header

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("pageHeader")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(28, 18, 28, 14)
        layout.setSpacing(16)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(_label(PAGE_TITLE, "pageTitle"))
        titles.addWidget(_label(PAGE_NOTE, "caption", True))
        layout.addLayout(titles, 1)
        self.period_label = _label("", "muted")
        layout.addWidget(self.period_label)
        self.data_badge = _label("데이터 없음", "badge")
        layout.addWidget(self.data_badge, 0, Qt.AlignVCenter)
        # 차트를 보는 중에 다른 달의 파일로 바꿀 때 쓴다. 첫 화면의 버튼과 같은 동작이다.
        self.reload_button = self._button("다른 데이터 불러오기", "folder", "quiet")
        self.reload_button.clicked.connect(self.load_data)
        self.reload_button.hide()
        layout.addWidget(self.reload_button, 0, Qt.AlignVCenter)
        return bar

    def _scroll_page(self, contents: QWidget) -> ScrollArea:
        contents.setObjectName("pageContents")
        scroll = ScrollArea()
        scroll.setSmoothMode(SmoothMode.NO_SMOOTH, Qt.Vertical)    # 휠 스크롤 애니메이션 없이 바로 이동
        scroll.setObjectName("workspacePage")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(contents)
        return scroll

    # ── 데이터 불러오기 ──────────────────────────────────────────────
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
        words.addWidget(_label("버튼을 누르면 파일 선택 창이 열립니다. 생활인구 CSV와 행정동 코드표, 두 파일을 함께 선택하세요.\n불러온 뒤 두 행정동을 골라 시간대·요일·연령별로 비교할 수 있습니다.", "welcomeCopy", True))
        self.connect_button = self._button("데이터 불러오기", "arrow", "primary")
        self.connect_button.setMinimumHeight(40)
        self.connect_button.clicked.connect(self.load_data)
        words.addWidget(self.connect_button, 0, Qt.AlignLeft)
        self.progress = ProgressBar(useAni=False)
        self.progress.setTextVisible(False)
        self.progress.hide()
        words.addWidget(self.progress)
        words.addWidget(_label("두 파일을 한 번에 고르려면 ⌘(Windows는 Ctrl) 키를 누른 채 클릭하세요. "
                               "하나만 고르면 나머지 파일을 이어서 묻습니다.", "caption", True))
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
        for number, title, note in (("01", "파일 선택", "생활인구 CSV + 행정동 코드표"),
                                    ("02", "지역 선택", "비교할 행정동 A·B 지정"),
                                    ("03", "분석", "생활인구 비교 차트 확인")):
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

    def load_data(self) -> None:
        """‘데이터 불러오기’ 버튼. 파일 두 개를 고르면 바로 불러오기를 시작한다."""
        files = self._pick_files()
        if files:
            self.start_load(files["population"], files["codes"])

    def _pick_files(self) -> dict[str, str] | None:
        """파일 선택 창에서 고른 CSV 를 {"population": 경로, "codes": 경로} 로 돌려준다.

        어느 쪽이 생활인구 파일인지는 identify_csv() 가 첫 줄의 열 개수로 가린다.
        그래서 고르는 순서나 파일 이름은 상관없다.
        """
        paths = self._ask_files("생활인구 CSV와 행정동 코드표를 함께 선택하세요", many=True)
        if not paths:
            return None
        self._last_dir = str(Path(paths[0]).parent)
        if len(paths) > 2:
            QMessageBox.warning(self, "파일은 두 개만", "생활인구 CSV와 행정동 코드표, 두 파일만 선택하세요.")
            return None
        try:
            files: dict[str, str] = {}
            for path in paths:
                kind = identify_csv(path)
                if kind in files:
                    QMessageBox.warning(self, "파일 종류 확인",
                                        f"두 파일이 모두 {FILE_KINDS[kind]} 형식입니다. 서로 다른 두 파일을 선택하세요.")
                    return None
                files[kind] = path
            for kind, caption in FILE_KINDS.items():      # 하나만 골랐으면 나머지를 이어서 묻는다
                if kind in files:
                    continue
                path = next(iter(self._ask_files(f"{caption}도 선택하세요")), "")
                if not path:
                    return None
                if identify_csv(path) != kind:
                    QMessageBox.warning(self, "파일 종류 확인", f"선택한 파일은 {caption} 형식이 아닙니다.")
                    return None
                files[kind] = path
        except DataError as exc:
            QMessageBox.critical(self, "파일을 읽을 수 없습니다", str(exc))
            return None
        return files

    def _file_dialog(self, caption: str, many: bool = False) -> QFileDialog:
        """항상 맨 앞에 뜨는 파일 선택 창을 만든다.

        운영체제의 기본 파일 창에는 ‘항상 위’ 옵션을 줄 수 없다. 그래서 Qt 가 직접 그리는
        파일 창을 쓰고 WindowStaysOnTopHint 를 켠다.
        """
        dialog = QFileDialog(self, caption, self._last_dir, CSV_FILTER)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dialog.setFileMode(QFileDialog.ExistingFiles if many else QFileDialog.ExistingFile)
        dialog.resize(900, 600)
        # 왼쪽에 자주 쓰는 폴더(컴퓨터·홈·바탕화면·문서·다운로드) 바로가기를 둔다.
        places = (QStandardPaths.HomeLocation, QStandardPaths.DesktopLocation,
                  QStandardPaths.DocumentsLocation, QStandardPaths.DownloadLocation)
        dialog.setSidebarUrls([QUrl("file:")] + [QUrl.fromLocalFile(QStandardPaths.writableLocation(place))
                                                 for place in places])
        # 바로가기 이름과 파일 목록의 이름·크기 칸이 잘리지 않도록 넓힌다.
        dialog.findChild(QSplitter).setSizes([170, 730])
        dialog.findChild(QTreeView).header().setSectionResizeMode(QHeaderView.ResizeToContents)
        return dialog

    def _ask_files(self, caption: str, many: bool = False) -> list[str]:
        """파일 선택 창을 띄우고 고른 경로들을 돌려준다. 취소하면 빈 목록."""
        dialog = self._file_dialog(caption, many)
        paths = dialog.selectedFiles() if dialog.exec() == QDialog.Accepted else []
        dialog.deleteLater()                              # 부를 때마다 새로 만드므로 쓰고 나면 지운다
        return paths

    def start_load(self, population_csv: str, code_csv: str) -> None:
        if self._thread is not None:
            return
        self.pages.setCurrentIndex(0)                     # 진행 상황은 첫 화면에서 보여 준다
        for button in (self.connect_button, self.reload_button):
            button.setEnabled(False)
        self.connect_button.setText("불러오는 중…")
        self.data_badge.setText("불러오는 중")
        self.status.setText("CSV 파일을 확인하고 있습니다…")
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
        for button in (self.connect_button, self.reload_button):
            button.setEnabled(True)
        self.connect_button.setText("데이터 불러오기")
        self.progress.hide()

    @pyqtSlot(int, str)
    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status.setText(message)

    @pyqtSlot(str)
    def _on_failed(self, message: str) -> None:
        self._finish_thread()
        self.data_badge.setText(f"{len(self.population.aggregates):,}개 행정동" if self.population else "불러오기 실패")
        self.status.setText(f"오류: {message}")
        if self._closing:
            self.close()
            return
        if self.population is not None:                   # 이전에 불러온 데이터가 있으면 그 차트로 돌아간다
            self.pages.setCurrentIndex(1)
        QMessageBox.critical(self, "데이터를 불러오지 못했습니다", message)

    @pyqtSlot(object, object)
    def _on_loaded(self, population: Population, codebook: CodeBook) -> None:
        was_loading = self._thread is not None
        self._finish_thread()
        if self._closing:
            self.close()
            return
        self.population = population
        self.codebook = codebook
        count = len(population.aggregates)
        self.data_badge.setText(f"{count:,}개 행정동")
        self.period_label.setText(_period(population))
        self.reload_button.show()

        self.region_a.blockSignals(True)
        self.region_b.blockSignals(True)
        self.region_a.populate(codebook, population)
        self.region_b.populate(codebook, population)
        # 지역 A/B 가 같은 곳이면 비교 그래프가 의미 없으니 B는 다른 동으로 옮겨 둔다.
        ranking = rank_by_daily_average(population, codebook, top=2)
        if ranking:
            self.region_a.set_dong(ranking[0][0])
            self.region_b.set_dong(ranking[-1][0])
        self.region_a.blockSignals(False)
        self.region_b.blockSignals(False)

        self.status.setText(f"{count:,}개 행정동 · {_period(population)} 데이터를 불러왔습니다.")
        self._on_region_changed()
        self.pages.setCurrentIndex(1)                     # 차트 보기로 넘어간다
        if was_loading:
            self._notify("불러오기 완료", f"{count:,}개 행정동 · 비교할 두 지역을 고르세요.")

    def _notify(self, title: str, content: str, duration: int = 2500) -> None:
        """오른쪽 위에 완료 알림을 띄운다. 미끄러짐·페이드 없이 바로 나타났다가 닫힌다."""
        bar = InfoBar.success(title, content, duration=-1, position=InfoBarPosition.NONE, parent=self)
        bar.move(self.width() - bar.width() - 24, 24)
        timer = QTimer(bar)
        timer.setSingleShot(True)
        timer.timeout.connect(bar.close)
        timer.start(duration)

    # ── 차트 보기 ────────────────────────────────────────────────────
    def _build_dashboard(self) -> ScrollArea:
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
        return self.dashboard_scroll

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

    def _refresh_theme_controls(self) -> None:
        for button, icon, primary in self._icon_buttons:
            button.setIcon(make_icon(icon, theme().on_accent if primary else theme().ink_soft))
        kitty = make_icon("kitty", size=128)
        self.setWindowIcon(kitty)
        QApplication.instance().setWindowIcon(kitty)
        self.brand_icon.setPixmap(kitty_pixmap(32, 28))
        self.welcome_icon.setPixmap(kitty_pixmap(132, 100))
        for page in self.tab_pages:
            page.refresh_icons()

    # ── 지역 선택 ────────────────────────────────────────────────────
    def _on_region_changed(self) -> None:
        self._results.clear()
        self._update_summary()
        self._render_current()

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
    import traceback

    # PyQt5 는 버튼 처리 중 잡히지 않은 오류가 나면 앱을 강제 종료한다.
    # 오류 내용만 출력하고 창은 계속 쓸 수 있게 한다.
    sys.excepthook = lambda *error: traceback.print_exception(*error)

    # Qt 5 는 고해상도(레티나) 화면 배율을 직접 켜야 글자와 아이콘이 선명하다.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # Qt 가 그리는 파일 선택 창의 글자(열기·취소·이름·크기 등)를 한국어로 표시한다.
    translator = QTranslator(app)
    if translator.load("qtbase_ko", QLibraryInfo.location(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
    window = MainWindow()
    window.show()
    if population_csv and code_csv:                       # 명령줄로 두 경로를 주면 바로 불러온다
        window.start_load(population_csv, code_csv)
    return app.exec()
