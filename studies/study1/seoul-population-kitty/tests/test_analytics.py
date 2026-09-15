"""Numerical and ingestion regressions, independent of Qt and real Seoul data."""

import csv
from datetime import date, timedelta
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hotplace.analytics import compare_places, diagnostics
from hotplace.dataset import CodeBook, DataError, Dong, DongAggregate, Population, load_population
from hotplace.hotplace import Hotplace, PairedAnalysis


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.pop_path = Path(self.directory.name) / "people.csv"
        self.code_path = Path(self.directory.name) / "codes.csv"
        with self.code_path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows([["header"], ["english"], ["", 1, "서울", "강남구", "가동"],
                                          ["", 2, "서울", "마포구", "나동"]])
        self.rows = []
        for day in range(9):
            stamp = (date(2026, 1, 1) + timedelta(days=day)).strftime("%Y%m%d")
            for code in (1, 2):
                for hour in range(24):
                    total = (100 + day * 10 + hour) * code
                    self.rows.append([stamp, hour, code, total, *([total / 28] * 28)])

    def load(self, rows=None):
        with self.pop_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow([f"column{i}" for i in range(32)])
            writer.writerows(self.rows if rows is None else rows)
        return load_population(self.pop_path, self.code_path, use_cache=False)

    def test_complete_data_preserves_baseline_and_adds_trends(self):
        population, codes = self.load()
        place = Hotplace(codes.by_code(1), population)
        self.assertEqual(place.mean_hourly(), [140 + h for h in range(24)])
        self.assertAlmostEqual(place.summary()["daily_avg"], 151.5)
        self.assertEqual(place.analysis6().values[0], [111.5 + d * 10 for d in range(9)])
        rolling = place.analysis6().values[1]
        self.assertTrue(all(math.isnan(v) for v in rolling[:6]))
        self.assertEqual(rolling[6:], [141.5, 151.5, 161.5])
        self.assertEqual(population.quality(codes)["coverage"], 1)
        self.assertAlmostEqual(sum(sum(values) for values in place.mean_by_age()), 151.5)

    def test_duplicates_do_not_inflate_population(self):
        population, codes = self.load(self.rows + [self.rows[0], self.rows[-1]])
        self.assertEqual(population.duplicate_rows, 2)
        self.assertEqual(population.quality(codes)["observed"], 9 * 24 * 2)
        self.assertEqual(Hotplace(codes.by_code(1), population).mean_hourly()[0], 140)

    def test_missing_hours_are_excluded_and_partial_days_are_gaps(self):
        rows = [row for row in self.rows if not (row[2] == 1 and row[1] == 0)]
        population, codes = self.load(rows)
        place = Hotplace(codes.by_code(1), population)
        self.assertTrue(math.isnan(place.mean_hourly()[0]))
        self.assertEqual(place.mean_hourly()[1], 141)
        self.assertTrue(all(math.isnan(v) for v in place.analysis6().values[0]))
        self.assertEqual(place.analysis1().csv_rows()[1][1], "")
        self.assertEqual(population.quality(codes)["missing"], 9)
        self.assertAlmostEqual(diagnostics(place)["coverage"], 23 / 24 * 100)

    def test_missing_calendar_day_breaks_rolling_window(self):
        population, codes = self.load([row for row in self.rows if row[0] != "20260104"])
        trend = Hotplace(codes.by_code(1), population).analysis6()
        self.assertEqual(len(trend.xlabels), 9)
        self.assertTrue(math.isnan(trend.values[0][3]))
        self.assertTrue(all(math.isnan(v) for v in trend.values[1]))
        self.assertEqual(population.quality(codes)["missing"], 48)

    def test_heatmap_uses_observed_weekday_counts(self):
        population, codes = self.load()
        result = Hotplace(codes.by_code(1), population).analysis7()
        self.assertEqual(result.values[3][0], (100 + 170) / 2)  # two Thursdays
        self.assertEqual(result.values[0][12], 152)  # one Monday
        pair = PairedAnalysis("heat", ("A", "B"), (result, result))
        self.assertEqual(len(pair.csv_rows()), 8)
        self.assertTrue(all(len(row) == 49 for row in pair.csv_rows()))

    def test_missing_weekend_is_not_zero(self):
        population, codes = self.load([row for row in self.rows if row[0] == "20260101"])
        place = Hotplace(codes.by_code(1), population)
        self.assertTrue(all(math.isnan(v) for v in place.mean_weekend()))
        self.assertTrue(math.isnan(place.summary()["weekend_ratio"]))
        self.assertIn("보류", place.summary()["character"])

    def test_normalization_removes_scale_and_comparison_is_symmetric(self):
        population, codes = self.load()
        a, b = (Hotplace(codes.by_code(i), population) for i in (1, 2))
        result = a.analysis8(b)
        self.assertEqual(result.values[0], result.values[1])
        self.assertAlmostEqual(sum(result.values[0]) / 24, 100)
        ab, ba = compare_places(a, b), compare_places(b, a)
        self.assertAlmostEqual(ab["correlation"], 1)
        self.assertEqual(ab["correlation"], ba["correlation"])
        self.assertEqual(ab["difference"], -ba["difference"])
        self.assertEqual(ab["largest_gap"][1], -ba["largest_gap"][1])

    def test_constant_and_zero_profiles_have_no_correlation(self):
        for constant in (0, 100):
            aggregate = DongAggregate(1, total=[constant] * 24)
            pop = Population({1: aggregate}, {"20260101"}, {"20260101"})
            place = Hotplace(Dong(1, "서울", "구", "동"), pop)
            self.assertTrue(math.isnan(compare_places(place, place)["correlation"]))
            if constant == 0:
                self.assertTrue(all(math.isnan(v) for v in place.analysis8(place).values[0]))

    def test_busiest_window_wraps_midnight(self):
        values = [1.0] * 24
        for hour in (23, 0, 1):
            values[hour] = 100
        pop = Population({1: DongAggregate(1, total=values)}, {"20260101"}, {"20260101"})
        place = Hotplace(Dong(1, "서울", "구", "동"), pop)
        self.assertEqual(diagnostics(place)["busy"], (23, 100))

    def test_robust_anomaly_flags_large_complete_day(self):
        rows = [list(row) for row in self.rows]
        for row in rows:
            if row[0] == "20260109":
                row[3] *= 100
        population, codes = self.load(rows)
        anomalies = diagnostics(Hotplace(codes.by_code(1), population))["anomalies"]
        self.assertEqual([day for day, _, _ in anomalies], ["20260109"])

    def test_hourly_gap_and_weekday_means(self):
        population, codes = self.load()
        a, b = (Hotplace(codes.by_code(i), population) for i in (1, 2))
        gap = a.analysis9(b)
        self.assertEqual(gap.gap, [x - y for x, y in zip(a.mean_hourly(), b.mean_hourly())])
        self.assertEqual(gap.gap, [-d for d in b.analysis9(a).gap])
        self.assertEqual(len(gap.csv_rows()), 25)
        self.assertTrue(all(len(row) == 4 for row in gap.csv_rows()))
        weekdays = a.analysis10()
        self.assertEqual(weekdays.categories, list("월화수목금토일"))
        self.assertEqual(weekdays.values[0][3], (111.5 + 181.5) / 2)  # two Thursdays
        self.assertEqual(weekdays.values[0][0], 151.5)  # one Monday
        self.assertEqual(weekdays.csv_rows()[1][0], "월")

    def test_female_share_and_age_composition(self):
        rows = [row for row in self.rows if not (row[2] == 1 and row[1] == 0)]
        population, codes = self.load(rows)
        a, b = (Hotplace(codes.by_code(i), population) for i in (1, 2))
        share = a.analysis11().values[0]
        self.assertTrue(math.isnan(share[0]))
        self.assertTrue(all(abs(v - 50) < 1e-9 for v in share[1:]))
        shares = a.analysis12(b)
        for values in shares.shares:
            self.assertAlmostEqual(sum(values), 100)
        self.assertEqual(len(shares.csv_rows()), 15)
        composition = a.analysis13()
        self.assertEqual(composition.rows[0], "70+")
        self.assertTrue(all(math.isnan(row[0]) for row in composition.values))
        for hour in range(1, 24):
            self.assertAlmostEqual(sum(row[hour] for row in composition.values), 100)

    def test_city_positions_mark_both_regions(self):
        population, codes = self.load()
        a, b = (Hotplace(codes.by_code(i), population) for i in (1, 2))
        scatter = a.analysis14(b, codes)
        self.assertEqual(dict(zip(scatter.names, scatter.marks)), {a.label: "A", b.label: "B"})
        self.assertEqual(scatter.day_night[0], a.summary()["day_night_ratio"])
        same = a.analysis14(a, codes)
        self.assertIn("A·B", same.marks)
        self.assertEqual(len(scatter.csv_rows()), 3)

    def test_invalid_observations_raise_actionable_errors(self):
        for column, value in ((1, -1), (1, 24), (3, "nan"), (3, "inf"), (4, -1),
                              (0, "20260230"), (0, "2026011"), (3, "*")):
            with self.subTest(column=column, value=value):
                row = list(self.rows[0])
                row[column] = value
                with self.assertRaises(DataError):
                    self.load([row])
        with self.assertRaises(DataError):
            self.load([["20260101", 0]])
        with self.assertRaises(DataError):
            self.load([])

    def test_unmatched_codes_and_cancellation(self):
        row = list(self.rows[0])
        row[2] = 999
        with self.assertRaisesRegex(DataError, "일치"):
            self.load([row])
        self.load()
        with self.assertRaisesRegex(DataError, "취소"):
            load_population(self.pop_path, self.code_path, use_cache=False, cancelled=lambda: True)


if __name__ == "__main__":
    unittest.main()
