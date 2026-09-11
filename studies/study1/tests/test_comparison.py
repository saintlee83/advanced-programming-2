"""두 지역을 바꿔도 계산·화면·내보내기가 대칭인지 검증한다."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from matplotlib.backend_bases import MouseEvent

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

    def test_workspace_navigation_and_ranking_preserve_comparison(self):
        self.window.tabs.setCurrentIndex(2)
        before_a = self.window.region_a.current()
        self.window.nav_items[1][0].click()
        self.settle()
        self.assertEqual(self.window.workspace_stack.currentIndex(), 1)
        self.assertEqual(self.window.tabs.currentIndex(), 2)
        self.window.search_target.setCurrentIndex(1)
        selected = self.window.rank_table.item(0, 0).data(Qt.UserRole)
        self.window.rank_select_button.click()
        self.settle()
        self.assertEqual(self.window.region_a.current(), before_a)
        self.assertEqual(self.window.region_b.current(), selected)
        self.assertEqual(self.window.workspace_stack.currentIndex(), 0)
        self.assertEqual(self.window.tabs.currentIndex(), 2)
        self.window.nav_items[2][0].click()
        self.settle()
        self.assertEqual(self.window.workspace_stack.currentIndex(), 2)
        self.assertTrue(self.window.load_button.isEnabled())

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
        for index in range(3):
            self.window._show_page(index)
            self.settle()
            scroll = self.window.dashboard_scroll if index == 0 else self.window.workspace_stack.widget(index)
            self.assertLessEqual(scroll.widget().width(), scroll.viewport().width())


if __name__ == "__main__":
    unittest.main()
