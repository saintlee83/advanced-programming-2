"""데이터 불러오기 → 차트 보기 흐름과, 두 지역을 바꿔도 계산·화면·내보내기가 대칭인지 검증한다."""

import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_API", "pyqt5")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import QAbstractAnimation
from PyQt5.QtWidgets import QApplication, QStackedWidget
from PyQt5.QtTest import QTest
from matplotlib.backend_bases import MouseEvent

from hotplace.dataset import COL_END, CodeBook, DataError, Dong, DongAggregate, Population, identify_csv
from hotplace.hotplace import Hotplace, PairedAnalysis
from hotplace.plotting import draw_result
from hotplace.theme import LIGHT, theme
from hotplace.ui import CITY_TAB, DISABLED_CHARTS, MainWindow, OVERLAY_TAB, TAB_GROUPS


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dongs = [
            Dong(1, "서울", "강남구", "가동"),
            Dong(2, "서울", "마포구", "나동"),
            Dong(3, "서울", "종로구", "다동"),
        ]
        aggregates = {}
        for index, dong in enumerate(self.dongs):
            aggregate = DongAggregate(dong.code)
            for hour in range(24):
                total = (index + 1) * 1000 + hour * 20
                aggregate.total[hour] = total
                aggregate.weekday[hour] = total * 0.6
                aggregate.weekend[hour] = total * 0.4
                aggregate.age[hour] = [total / 28] * 28
            aggregates[dong.code] = aggregate
        population = Population(aggregates, {"20260102", "20260103"}, {"20260102"})
        self.window = MainWindow()
        self.window.show()
        self.window._on_loaded(population, CodeBook(self.dongs))
        self.window.region_a.set_dong(self.dongs[0])
        self.window.region_b.set_dong(self.dongs[1])
        self.settle()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.settle()

    def settle(self):
        for _ in range(4):
            self.app.processEvents()

    def test_every_analysis_exports_both_regions(self):
        for index, columns in enumerate((3, 5, 5, 3, 5)):
            with self.subTest(tab=index):
                self.window.tabs.setCurrentIndex(index)
                self.settle()
                result = self.window._results[index]
                rows = result.csv_rows()
                self.assertEqual(len(rows), 15 if index == 4 else 25)
                self.assertTrue(all(len(row) == columns for row in rows))
                self.assertIn(self.dongs[0].label, " ".join(rows[0]))
                self.assertIn(self.dongs[1].label, " ".join(rows[0]))
                self.assertNotEqual(rows[1][1], rows[1][(columns + 1) // 2])

    def test_swapping_only_reverses_regions(self):
        for index in range(5):
            with self.subTest(tab=index):
                self.window.tabs.setCurrentIndex(index)
                self.settle()
                before = self.window._results[index]
                metrics_a = [value.text() for value in self.window.metrics_a.values.values()]
                metrics_b = [value.text() for value in self.window.metrics_b.values.values()]
                self.window.swap_button.click()
                self.settle()
                after = self.window._results[index]
                self.assertEqual(self.window.tabs.currentIndex(), index)
                self.assertEqual([value.text() for value in self.window.metrics_a.values.values()], metrics_b)
                self.assertEqual([value.text() for value in self.window.metrics_b.values.values()], metrics_a)
                if index == OVERLAY_TAB:
                    self.assertEqual(after.values, before.values[::-1])
                else:
                    self.assertIsInstance(after, PairedAnalysis)
                    self.assertEqual(after.regions, before.regions[::-1])
                    self.assertEqual(after.analyses, before.analyses[::-1])

    def test_paired_plots_use_equal_size_and_shared_axes(self):
        self.window.resize(1080, 740)
        for index in (0, 1, 2, 4):
            with self.subTest(tab=index):
                self.window.tabs.setCurrentIndex(index)
                self.settle()
                left, right = self.window.tab_pages[index].canvas.figure.axes
                self.assertAlmostEqual(left.bbox.width, right.bbox.width)
                self.assertAlmostEqual(left.bbox.height, right.bbox.height)
                self.assertEqual(left.get_xlim(), right.get_xlim())
                self.assertEqual(left.get_ylim(), right.get_ylim())
                if index != 4:
                    self.assertEqual(left.get_ylim()[0], 0)
                left.set_xlim(1, 10)
                self.assertEqual(left.get_xlim(), right.get_xlim())

    def test_either_region_keeps_the_selected_analysis(self):
        self.window.tabs.setCurrentIndex(2)
        for selector in (self.window.region_a, self.window.region_b):
            selector.set_dong(self.dongs[2])
            self.settle()
            self.assertEqual(selector.current(), self.dongs[2])
            self.assertEqual(self.window.tabs.currentIndex(), 2)
        paired = self.window._results[2]
        self.assertEqual(paired.analyses[0], paired.analyses[1])
        self.assertTrue(self.window.export_csv_button.isEnabled())

    def test_window_moves_from_loading_to_charts(self):
        fresh = MainWindow()
        try:
            self.assertEqual(fresh.pages.count(), 2)
            self.assertEqual(fresh.pages.currentIndex(), 0)
            self.assertTrue(fresh.reload_button.isHidden())
            self.assertTrue(fresh.progress.isHidden())
        finally:
            fresh.deleteLater()
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertFalse(self.window.reload_button.isHidden())
        self.assertIn("3개 행정동", self.window.data_badge.text())

    def write_csvs(self, directory):
        population = Path(directory) / "people.csv"
        population.write_text(",".join(f"c{i}" for i in range(COL_END)) + "\n", encoding="utf-8")
        codes = Path(directory) / "codes.csv"
        codes.write_text("통계청행정동코드,행자부행정동코드,시도명,시군구명,행정동명\n", encoding="utf-8-sig")
        return str(population), str(codes)

    def test_load_button_picks_two_files_in_any_order(self):
        with tempfile.TemporaryDirectory() as directory:
            population, codes = self.write_csvs(directory)
            self.assertEqual(identify_csv(population), "population")
            self.assertEqual(identify_csv(codes), "codes")
            for picked in ([population, codes], [codes, population]):
                with patch("hotplace.ui.QFileDialog.getOpenFileNames", return_value=(picked, "")), \
                     patch.object(self.window, "start_load") as start:
                    self.window.load_data()
                start.assert_called_once_with(population, codes)
            # 하나만 고르면 나머지 파일을 이어서 묻는다.
            with patch("hotplace.ui.QFileDialog.getOpenFileNames", return_value=([codes], "")), \
                 patch("hotplace.ui.QFileDialog.getOpenFileName", return_value=(population, "")) as second, \
                 patch.object(self.window, "start_load") as start:
                self.window.load_data()
            self.assertIn("생활인구", second.call_args.args[1])
            start.assert_called_once_with(population, codes)

    def test_load_button_rejects_wrong_selections(self):
        with tempfile.TemporaryDirectory() as directory:
            population, codes = self.write_csvs(directory)
            cases = ([], [codes, codes], [population, codes, codes])
            for picked in cases:
                with self.subTest(picked=len(picked)), \
                     patch("hotplace.ui.QFileDialog.getOpenFileNames", return_value=(picked, "")), \
                     patch("hotplace.ui.QMessageBox.warning") as warning, \
                     patch.object(self.window, "start_load") as start:
                    self.window.load_data()
                    start.assert_not_called()
                    self.assertEqual(warning.called, bool(picked))
            with patch("hotplace.ui.QFileDialog.getOpenFileNames", return_value=([codes], "")), \
                 patch("hotplace.ui.QFileDialog.getOpenFileName", return_value=("", "")), \
                 patch.object(self.window, "start_load") as start:
                self.window.load_data()                       # 두 번째 창에서 취소
            start.assert_not_called()

    def test_heatmaps_are_disabled_but_still_drawable(self):
        self.assertEqual(DISABLED_CHARTS, {6, 12})
        offered = {chart for _name, charts in TAB_GROUPS for chart in charts}
        self.assertEqual(offered, set(range(14)) - DISABLED_CHARTS)
        tabs = self.window.tabs
        tabs.setCurrentIndex(5)
        for index in DISABLED_CHARTS:
            tabs.setCurrentIndex(index)
            self.assertEqual(tabs.currentIndex(), 5)
        for group in range(tabs.group_picker.count()):
            tabs.group_picker.setCurrentIndex(group)
            titles = [tabs.chart_picker.itemText(row) for row in range(tabs.chart_picker.count())]
            self.assertNotIn("요일×시간", titles)
            self.assertNotIn("연령×시간", titles)
        # 계산과 그리기 코드는 남아 있다(--check --out 에서 쓴다): 두 히트맵은 같은 색 범위를 쓴다.
        places = [Hotplace(dong, self.window.population) for dong in self.dongs[:2]]
        result = PairedAnalysis("요일 × 시간대 비교", tuple(place.label for place in places),
                                tuple(place.analysis7() for place in places))
        canvas = self.window.tab_pages[6].canvas
        draw_result(canvas, result, show_heading=False)
        canvas.draw()
        top, bottom = canvas.figure.axes[:2]
        self.assertEqual(top.images[0].get_clim(), bottom.images[0].get_clim())

    def test_hover_reads_both_regions_and_stays_out_of_export(self):
        page = self.window.tab_pages[0]
        canvas = page.canvas
        canvas.draw()
        left = canvas.figure.axes[0]
        x, y = left.transData.transform((12, left.get_ylim()[1] / 2))
        canvas.callbacks.process("motion_notify_event", MouseEvent("motion_notify_event", canvas, x, y))
        result = self.window._results[0]
        for region, series in zip("AB", result.analyses):
            self.assertIn(f"{region} {series.values[0][12]:,.0f}명", page.readout.text())
        self.assertEqual(len(canvas._hover_lines), 2)
        self.assertTrue(all(line.get_visible() and list(line.get_xdata()) == [12, 12]
                            for line in canvas._hover_lines))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "comparison.png"
            with patch("hotplace.ui.QFileDialog.getSaveFileName", return_value=(str(output), "PNG")):
                self.window._save_png()
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1000)
        self.assertFalse(any(line.get_visible() for line in canvas._hover_lines))

    def test_small_workspace_pages_have_no_horizontal_overflow(self):
        self.window.resize(1080, 740)
        for index in (1, 0):
            self.window.pages.setCurrentIndex(index)
            self.settle()
            scroll = self.window.pages.widget(index)
            self.assertLessEqual(scroll.widget().width(), scroll.viewport().width())

    def test_new_analyses_export_and_render_missing_observations(self):
        for index, rows, columns in ((5, 3, 5), (7, 25, 3)):
            with self.subTest(tab=index):
                self.window.tabs.setCurrentIndex(index)
                self.settle()
                result = self.window._results[index]
                exported = result.csv_rows()
                self.assertEqual(len(exported), rows)
                self.assertTrue(all(len(row) == columns for row in exported))
                self.assertIn(self.dongs[0].label, " ".join(exported[0]))
                self.assertIn(self.dongs[1].label, " ".join(exported[0]))
                self.window.tab_pages[index].canvas.draw()

    def test_added_comparisons_export_and_render(self):
        for index, rows, columns in ((8, 25, 4), (9, 8, 3), (10, 25, 3), (11, 15, 4), (13, 4, 4)):
            with self.subTest(tab=index):
                self.window.tabs.setCurrentIndex(index)
                self.settle()
                exported = self.window._results[index].csv_rows()
                self.assertEqual(len(exported), rows)
                self.assertTrue(all(len(row) == columns for row in exported))
                text = " ".join(" ".join(row) for row in exported[:4] if index == CITY_TAB) or " ".join(exported[0])
                for dong in self.dongs[:2]:
                    self.assertIn(dong.label, text)
                self.window.tab_pages[index].canvas.draw()
                self.assertTrue(self.window.export_csv_button.isEnabled())

    def test_chart_pickers_remember_the_chart_in_each_group(self):
        tabs = self.window.tabs
        tabs.setCurrentIndex(8)
        tabs.setCurrentIndex(11)
        self.settle()
        self.assertEqual(tabs.group_picker.currentData(), 2)
        self.assertEqual(tabs.chart_picker.currentData(), 11)
        tabs.group_picker.setCurrentIndex(0)
        self.settle()
        self.assertEqual(tabs.currentIndex(), 8)
        self.assertEqual(tabs.chart_picker.currentData(), 8)
        self.assertEqual(self.window.chart_title.text(), "시간대별 인구 차이 (A − B)")

    def test_gap_and_city_hover_readouts(self):
        self.window.tabs.setCurrentIndex(8)
        self.settle()
        page = self.window.tab_pages[8]
        page.canvas.draw()
        ax = page.canvas.figure.axes[0]
        x, y = ax.transData.transform((12, 0))
        page.canvas.callbacks.process("motion_notify_event", MouseEvent("motion_notify_event", page.canvas, x, y))
        gap = self.window._results[8]
        self.assertIn(f"차이 {gap.gap[12]:+,.0f}명", page.readout.text())

        self.window.tabs.setCurrentIndex(CITY_TAB)
        self.settle()
        page = self.window.tab_pages[CITY_TAB]
        page.canvas.draw()
        scatter = self.window._results[CITY_TAB]
        ax = page.canvas.figure.axes[0]
        point = scatter.marks.index("B")
        x, y = ax.transData.transform((scatter.day_night[point], scatter.weekend[point]))
        page.canvas.callbacks.process("motion_notify_event", MouseEvent("motion_notify_event", page.canvas, x, y))
        self.assertIn(f"B · {self.dongs[1].label}", page.readout.text())

    def test_screens_switch_immediately_without_animation(self):
        for index in (7, 1, 5, 0):
            self.window.tabs.setCurrentIndex(index)
        self.assertEqual(self.window.tabs.currentIndex(), 0)
        for index in (0, 1, 0, 1):
            self.window.pages.setCurrentIndex(index)
        self.assertEqual(self.window.pages.currentIndex(), 1)
        # 화면 전환은 기본 QStackedWidget 이 맡고, 앱이 만든 애니메이션 객체는 없다.
        for stack in (self.window.pages, self.window.tabs.stack):
            self.assertIs(type(stack), QStackedWidget)
        self.assertFalse(self.window.progress.isUseAni())
        running = [ani for ani in self.window.findChildren(QAbstractAnimation)
                   if ani.state() == QAbstractAnimation.Running]
        self.assertEqual(running, [])

    def test_light_theme_is_fixed(self):
        self.window.tabs.setCurrentIndex(5)
        self.settle()
        self.assertIs(theme(), LIGHT)
        self.assertEqual(self.window.tabs.currentIndex(), 5)

    def test_failed_background_reload_preserves_analysis(self):
        previous = self.window.population
        with patch("hotplace.ui.load_population", side_effect=DataError("bad data")), \
             patch("hotplace.ui.QMessageBox.critical") as error:
            self.window.start_load("population.csv", "codes.csv")
            self.assertEqual(self.window.pages.currentIndex(), 0)     # 진행 상황은 첫 화면에서 보여 준다
            self.assertFalse(self.window.connect_button.isEnabled())
            for _ in range(100):
                QTest.qWait(10)
                if self.window._thread is None:
                    break
            self.assertIsNone(self.window._thread)
            error.assert_called_once()
        self.assertIs(self.window.population, previous)
        self.assertEqual(self.window.pages.currentIndex(), 1)         # 이전 데이터의 차트로 돌아온다
        self.assertTrue(self.window.connect_button.isEnabled())
        self.assertTrue(self.window.reload_button.isEnabled())

    def test_close_cancels_worker_before_destroying_thread(self):
        entered = threading.Event()

        def loading(*_args, cancelled, **_kwargs):
            entered.set()
            while not cancelled():
                time.sleep(0.005)
            raise DataError("cancelled")

        with patch("hotplace.ui.load_population", side_effect=loading):
            self.window.start_load("population.csv", "codes.csv")
            self.assertTrue(entered.wait(2))
            self.window.close()
            for _ in range(100):
                QTest.qWait(10)
                if self.window._thread is None:
                    break
            self.assertIsNone(self.window._thread)
            self.assertFalse(self.window.isVisible())


if __name__ == "__main__":
    unittest.main()
