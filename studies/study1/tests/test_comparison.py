"""두 지역을 바꿔도 계산·화면·내보내기가 대칭인지 검증한다."""

import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtWidgets import QApplication

from hotplace.dataset import CodeBook, Dong, DongAggregate, Population
from hotplace.hotplace import PairedAnalysis
from hotplace.ui import MainWindow, OVERLAY_TAB


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
        for target, selector in enumerate((self.window.region_a, self.window.region_b)):
            self.window.search_target.setCurrentIndex(target)
            self.window.search_edit.setText("다동")
            self.window.search_button.click()
            self.settle()
            self.assertEqual(selector.current(), self.dongs[2])
            self.assertEqual(self.window.tabs.currentIndex(), 2)
        paired = self.window._results[2]
        self.assertEqual(paired.analyses[0], paired.analyses[1])
        self.assertTrue(self.window.export_csv_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
