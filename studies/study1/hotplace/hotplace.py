"""핫플레이스(행정동) 분석 클래스.

강의자료 Project 1 의 ``Hotplace`` 클래스를 그대로 따르되,
계산과 그리기를 분리했다. 각 ``analysisN()`` 은 그래프를 직접 띄우지 않고
:class:`LineSeries` / :class:`AgePyramid` 같은 '결과 값'을 돌려주고,
그리는 일은 :mod:`hotplace.plotting` 이 맡는다. 덕분에 UI 없이도
분석 결과를 그대로 검증하거나 CSV 로 내보낼 수 있다.

    analysis1  시간대별 평균 생활인구
    analysis2  주중 / 주말 시간대별 평균 생활인구
    analysis3  남 / 녀 시간대별 평균 생활인구
    analysis4  두 지역의 시간대별 평균 생활인구 비교
    analysis5  연령대별 인구 피라미드 (추가 분석)
    analysis6~8   일별 추이 · 요일×시간 · 규모를 맞춘 하루 흐름
    analysis9~14  시간대별 차이 · 요일별 · 여성 비율 · 연령 비중 · 연령×시간 · 서울 속 위치
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math

from .dataset import AGE_BANDS, HOURS, N_BANDS, Dong, Population

# 주간 / 야간 구간 정의 (요약 통계에서 사용)
DAY_HOURS = range(9, 19)     # 09시 ~ 18시
NIGHT_HOURS = range(0, 7)    # 00시 ~ 06시
WEEKDAYS = tuple("월화수목금토일")

# 상권 유형 구분 기준. 요약 통계와 '서울 속 위치' 차트가 함께 쓴다.
WEEKEND_BUSY = 1.03          # 주말 ÷ 평일이 이 값 이상이면 주말 상권 후보
WEEKDAY_BUSY = 0.93          # 주말 ÷ 평일이 이 값 이하이면 업무지구 후보
OFFICE_DAY_NIGHT = 1.3       # 낮 ÷ 밤이 이 값 이상이면 업무지구 후보
RESIDENTIAL_DAY_NIGHT = 1.05  # 낮 ÷ 밤이 이 값 이하이면 주거지


def finite_mean(values) -> float:
    available = [v for v in values if math.isfinite(v)]
    return sum(available) / len(available) if available else float("nan")


def csv_number(value: float) -> str:
    return f"{value:.1f}" if math.isfinite(value) else ""


@dataclass
class LineSeries:
    """시간대(0~23)를 x축으로 하는 꺾은선 그래프 한 장 분량의 결과."""

    title: str
    labels: list[str]
    values: list[list[float]]
    xlabel: str = "시간대"
    ylabel: str = "평균 생활인구(명)"
    note: str = ""
    xlabels: list[str] | None = None       # 날짜(YYYYMMDD) 축
    unit: str = "명"
    categories: list[str] | None = None    # 요일처럼 이름이 붙은 축
    reference: float | None = None         # 기준선 (예: 50%, 평균 = 100)

    @property
    def ticks(self) -> list[str]:
        if self.xlabels is not None:
            return self.xlabels
        if self.categories is not None:
            return self.categories
        return [str(hour) for hour in range(len(self.values[0]))]

    def csv_rows(self) -> list[list[str]]:
        rows = [[self.xlabel] + self.labels]
        for index, tick in enumerate(self.ticks):
            rows.append([tick] + [csv_number(v[index]) for v in self.values])
        return rows


@dataclass
class AgePyramid:
    """연령대별 남/녀 평균 생활인구."""

    title: str
    bands: list[str] = field(default_factory=lambda: list(AGE_BANDS))
    male: list[float] = field(default_factory=list)
    female: list[float] = field(default_factory=list)
    note: str = ""

    def csv_rows(self) -> list[list[str]]:
        rows = [["연령대", "남자", "여자"]]
        for band, m, f in zip(self.bands, self.male, self.female):
            rows.append([band, f"{m:.1f}", f"{f:.1f}"])
        return rows


@dataclass
class Heatmap:
    title: str
    values: list[list[float]]
    rows: list[str] = field(default_factory=lambda: list(WEEKDAYS))
    note: str = "요일·시간대별 평균 · 빈 칸은 관측이 없는 시간"
    row_label: str = "요일"
    value_label: str = "평균 생활인구(명)"
    percent: bool = False

    def csv_rows(self) -> list[list[str]]:
        return [[f"{self.row_label} / 시간", *map(str, range(HOURS))]] + [
            [row, *map(csv_number, values)] for row, values in zip(self.rows, self.values)]


@dataclass
class HourlyGap:
    """두 지역의 시간대별 평균 생활인구와 그 차이 (A − B)."""

    title: str
    regions: tuple[str, str]
    a: list[float]
    b: list[float]
    note: str = ""
    unit: str = "명"
    xlabels = None
    categories = None

    @property
    def gap(self) -> list[float]:
        return [x - y for x, y in zip(self.a, self.b)]

    # 마우스 판독이 LineSeries 와 같은 방식으로 값을 읽는다.
    @property
    def labels(self) -> list[str]:
        return ["A", "B", "차이"]

    @property
    def values(self) -> list[list[float]]:
        return [self.a, self.b, self.gap]

    def csv_rows(self) -> list[list[str]]:
        rows = [["시간대", f"A · {self.regions[0]}", f"B · {self.regions[1]}", "A − B"]]
        for hour, (x, y, d) in enumerate(zip(self.a, self.b, self.gap)):
            rows.append([str(hour), csv_number(x), csv_number(y), csv_number(d)])
        return rows


@dataclass
class AgeShares:
    """두 지역의 연령대별 인구 비중(%)."""

    title: str
    regions: tuple[str, str]
    shares: tuple[list[float], list[float]]
    bands: list[str] = field(default_factory=lambda: list(AGE_BANDS))
    note: str = ""

    def csv_rows(self) -> list[list[str]]:
        rows = [["연령대", f"A · {self.regions[0]} (%)", f"B · {self.regions[1]} (%)", "A − B (%p)"]]
        for band, x, y in zip(self.bands, *self.shares):
            rows.append([band, csv_number(x), csv_number(y), csv_number(x - y)])
        return rows


@dataclass
class CityScatter:
    """서울 행정동 전체의 낮 ÷ 밤, 주말 ÷ 평일 배율과 비교 중인 두 지역."""

    title: str
    regions: tuple[str, str]
    names: list[str]
    day_night: list[float]
    weekend: list[float]
    marks: list[str]          # "A", "B", "A·B" 또는 ""
    note: str = ""

    def csv_rows(self) -> list[list[str]]:
        rows = [["행정동", "낮 ÷ 밤 (배)", "주말 ÷ 평일 (배)", "비교 지역"]]
        for name, x, y, mark in zip(self.names, self.day_night, self.weekend, self.marks):
            rows.append([name, f"{x:.3f}", f"{y:.3f}", mark])
        return rows


@dataclass
class PairedAnalysis:
    """동일한 분석을 두 지역에 적용한 결과. 두 지역 모두 CSV에 포함한다."""

    title: str
    regions: tuple[str, str]
    analyses: tuple[LineSeries, LineSeries] | tuple[AgePyramid, AgePyramid] | tuple[Heatmap, Heatmap]
    note: str = ""

    def csv_rows(self) -> list[list[str]]:
        left, right = (analysis.csv_rows() for analysis in self.analyses)
        header = [left[0][0]]
        for side, region, rows in zip(("A", "B"), self.regions, (left, right)):
            header.extend(f"{side} · {region} · {column}" for column in rows[0][1:])
        return [header] + [a + b[1:] for a, b in zip(left[1:], right[1:])]


class Hotplace:
    """행정동 한 곳을 분석 대상으로 감싸는 클래스.

    Attributes:
        name: 행정동명 (예: '역삼1동')
        code: 행자부 행정동 코드 (예: 11680640)
    """

    def __init__(self, dong: Dong, population: Population) -> None:
        self.name = dong.name
        self.code = dong.code
        self.dong = dong
        self._pop = population
        self._agg = population.get(dong.code)

    def __repr__(self) -> str:
        return f"Hotplace({self.dong.label!r}, code={self.code})"

    @property
    def label(self) -> str:
        return self.dong.label

    # ── 기초 계산 ────────────────────────────────────────────────────
    def _mean(self, values, counts, fallback_days) -> list[float]:
        if self._agg.daily:
            return [v / n if n else float("nan") for v, n in zip(values, counts)]
        # Keep support for aggregate-only callers used by the original exercises.
        return [v / fallback_days if fallback_days else float("nan") for v in values]

    def mean_hourly(self) -> list[float]:
        """시간대별 평균 생활인구 (한 달 누적 ÷ 일수)."""
        return self._mean(self._agg.total, self._agg.counts, self._pop.n_days)

    def mean_weekday(self) -> list[float]:
        return self._mean(self._agg.weekday, self._agg.weekday_counts, self._pop.n_weekday)

    def mean_weekend(self) -> list[float]:
        return self._mean(self._agg.weekend, self._agg.weekend_counts, self._pop.n_weekend)

    def mean_by_gender(self) -> tuple[list[float], list[float]]:
        """(남자, 여자) 시간대별 평균 생활인구."""
        male, female = [], []
        for hour in range(HOURS):
            band = self._agg.age[hour]
            male.append(sum(band[:N_BANDS]))
            female.append(sum(band[N_BANDS:]))
        return (self._mean(male, self._agg.counts, self._pop.n_days),
                self._mean(female, self._agg.counts, self._pop.n_days))

    def mean_by_age(self) -> tuple[list[float], list[float]]:
        """(남자, 여자) 연령대별 평균 생활인구. 24시간을 평균한 값이다."""
        days = self._pop.n_days or 1
        divisor = sum(self._agg.counts) if self._agg.daily else days * HOURS
        male = [0.0] * N_BANDS
        female = [0.0] * N_BANDS
        for hour in range(HOURS):
            band = self._agg.age[hour]
            for i in range(N_BANDS):
                male[i] += band[i]
                female[i] += band[N_BANDS + i]
        return (
            [v / divisor for v in male],
            [v / divisor for v in female],
        )

    # ── 분석 1 ~ 5 ───────────────────────────────────────────────────
    def analysis1(self) -> LineSeries:
        """시간대별 평균 생활인구."""
        return LineSeries(
            title=f"{self.label} 시간대별 평균 생활인구",
            labels=["평균 생활인구"],
            values=[self.mean_hourly()],
            note=f"{self._pop.period} · {self._pop.n_days}일 평균",
        )

    def analysis2(self) -> LineSeries:
        """주중 / 주말 시간대별 평균 생활인구."""
        return LineSeries(
            title=f"{self.label} 주중·주말 시간대별 평균 생활인구",
            labels=["평일", "주말"],
            values=[self.mean_weekday(), self.mean_weekend()],
            note=f"평일 {self._pop.n_weekday}일 · 주말 {self._pop.n_weekend}일 평균",
        )

    def analysis3(self) -> LineSeries:
        """남 / 녀 시간대별 평균 생활인구."""
        male, female = self.mean_by_gender()
        return LineSeries(
            title=f"{self.label} 남녀 시간대별 평균 생활인구",
            labels=["남자", "여자"],
            values=[male, female],
            note=f"{self._pop.period} · {self._pop.n_days}일 평균",
        )

    def analysis4(self, other: "Hotplace") -> LineSeries:
        """다른 행정동과 시간대별 평균 생활인구를 비교."""
        return LineSeries(
            title=f"{self.label} vs {other.label} 시간대별 평균 생활인구",
            labels=[self.label, other.label],
            values=[self.mean_hourly(), other.mean_hourly()],
            note=f"{self._pop.period} · {self._pop.n_days}일 평균",
        )

    def analysis5(self) -> AgePyramid:
        """연령대별 남/녀 평균 생활인구 (인구 피라미드)."""
        male, female = self.mean_by_age()
        return AgePyramid(
            title=f"{self.label} 연령대별 평균 생활인구",
            male=male,
            female=female,
            note=f"{self._pop.period} · 24시간 평균",
        )

    def analysis6(self) -> LineSeries:
        """Daily means require all 24 hours. Rolling mean requires seven complete days."""
        dates = self._pop.calendar_dates
        values = [sum(self._agg.daily[d].values()) / HOURS
                  if len(self._agg.daily.get(d, {})) == HOURS else float("nan") for d in dates]
        rolling = [sum(values[i - 6:i + 1]) / 7
                   if i >= 6 and all(math.isfinite(v) for v in values[i - 6:i + 1])
                   else float("nan") for i in range(len(values))]
        return LineSeries(f"{self.label} 일별 추세", ["일평균", "7일 이동평균"], [values, rolling],
                          xlabel="날짜", xlabels=dates,
                          note="24시간이 모두 관측된 날만 표시 · 이동평균은 연속 7일 기준")

    def analysis7(self) -> Heatmap:
        buckets = [[[] for _ in range(HOURS)] for _ in range(7)]
        for date, observations in self._agg.daily.items():
            day = datetime.strptime(date, "%Y%m%d").weekday()
            for hour, value in observations.items():
                buckets[day][hour].append(value)
        return Heatmap(f"{self.label} 주간 리듬", [[finite_mean(cell) for cell in row] for row in buckets])

    def analysis8(self, other: "Hotplace") -> LineSeries:
        profiles = []
        for place in (self, other):
            hourly = place.mean_hourly()
            average = finite_mean(hourly)
            profiles.append([value / average * 100 if average > 0 else float("nan") for value in hourly])
        return LineSeries(f"{self.label} · {other.label} 패턴 비교", [self.label, other.label], profiles,
                          ylabel="지역 평균 = 100", unit="", reference=100,
                          note="지역마다 하루 평균을 100으로 맞춘 값 · 인구 규모와 상관없이 하루 흐름만 비교")

    def analysis9(self, other: "Hotplace") -> HourlyGap:
        """시간대별 평균 생활인구 차이 (이 지역 − 다른 지역)."""
        return HourlyGap(f"{self.label} − {other.label} 시간대별 차이", (self.label, other.label),
                         self.mean_hourly(), other.mean_hourly(),
                         note=f"{self._pop.period} · 막대가 위로 뻗으면 A, 아래로 뻗으면 B가 더 많음")

    def analysis10(self) -> LineSeries:
        """요일별 평균 생활인구. 요일·시간대 평균(analysis7)을 요일마다 다시 평균한다."""
        observed = [0] * 7
        for date in self._agg.daily:
            observed[datetime.strptime(date, "%Y%m%d").weekday()] += 1
        counts = "·".join(f"{day} {n}" for day, n in zip(WEEKDAYS, observed))
        return LineSeries(f"{self.label} 요일별 평균 생활인구", ["평균 생활인구"],
                          [[finite_mean(row) for row in self.analysis7().values]],
                          xlabel="요일", categories=list(WEEKDAYS),
                          note=f"요일마다 시간대별 평균의 평균 · 관측한 날 수 {counts}")

    def analysis11(self) -> LineSeries:
        """시간대별 여성 비율 (성별·연령 집계 기준)."""
        male, female = self.mean_by_gender()
        share = [f / (m + f) * 100 if math.isfinite(m + f) and m + f > 0 else float("nan")
                 for m, f in zip(male, female)]
        return LineSeries(f"{self.label} 시간대별 여성 비율", ["여성 비율"], [share],
                          ylabel="여성 비율(%)", unit="%", reference=50,
                          note="성별·연령 집계 중 여성의 비율 · 점선은 50%")

    def age_shares(self) -> list[float]:
        """연령대별 비중(%). 남녀를 합쳐 전체를 100으로 본다."""
        male, female = self.mean_by_age()
        bands = [m + f for m, f in zip(male, female)]
        total = sum(bands)
        return [band / total * 100 if total > 0 else float("nan") for band in bands]

    def analysis12(self, other: "Hotplace") -> AgeShares:
        """두 지역의 연령대별 비중 비교. 인구 규모와 상관없이 구성만 본다."""
        return AgeShares(f"{self.label} · {other.label} 연령대별 비중", (self.label, other.label),
                         (self.age_shares(), other.age_shares()),
                         note="지역마다 인구를 100%로 볼 때 연령대별 비중 · 24시간·전체 기간 평균")

    def analysis13(self) -> Heatmap:
        """시간대별 연령 구성. 시간마다 그 시간 인구를 100%로 본다."""
        values = []
        for band in range(N_BANDS):
            row = []
            for hour in range(HOURS):
                cells = self._agg.age[hour]
                total = sum(cells)
                missing = self._agg.daily and not self._agg.counts[hour]
                row.append(float("nan") if missing or total <= 0
                           else (cells[band] + cells[N_BANDS + band]) / total * 100)
            values.append(row)
        # 피라미드처럼 나이 많은 연령대를 위에 둔다.
        return Heatmap(f"{self.label} 시간대별 연령 구성", values[::-1], rows=list(AGE_BANDS)[::-1],
                       note="시간마다 인구를 100%로 볼 때 연령대별 비중 · 두 지역이 같은 색 범위를 씀",
                       row_label="연령대", value_label="그 시간 인구 중 비중(%)", percent=True)

    def analysis14(self, other: "Hotplace", codebook) -> CityScatter:
        """서울 행정동 전체 속에서 두 지역의 낮 ÷ 밤, 주말 ÷ 평일 배율 위치."""
        names, day_night, weekend, marks = [], [], [], []
        for dong, stats in character_points(self._pop, codebook):
            names.append(dong.label)
            day_night.append(stats["day_night_ratio"])
            weekend.append(stats["weekend_ratio"])
            marks.append("·".join(tag for tag, place in (("A", self), ("B", other)) if place.code == dong.code))
        return CityScatter(f"서울 행정동 속 {self.label} · {other.label}", (self.label, other.label),
                           names, day_night, weekend, marks,
                           note=f"회색 점은 서울 행정동 {len(names)}곳 · 점선은 상권 유형 구분 기준 "
                                "(가장 붐비는 시간 조건은 생략)")

    # ── 요약 통계 ────────────────────────────────────────────────────
    def summary(self) -> dict[str, object]:
        """그래프 아래에 함께 보여줄 요약 지표."""
        hourly = self.mean_hourly()
        hours = [h for h in range(HOURS) if math.isfinite(hourly[h])]
        peak_hour = max(hours, key=lambda h: hourly[h]) if hours else 0
        low_hour = min(hours, key=lambda h: hourly[h]) if hours else 0

        day_avg = finite_mean(hourly[h] for h in DAY_HOURS)
        night_avg = finite_mean(hourly[h] for h in NIGHT_HOURS)

        weekday = self.mean_weekday()
        weekend = self.mean_weekend()
        weekday_avg = finite_mean(weekday)
        weekend_avg = finite_mean(weekend)

        male, female = self.mean_by_gender()
        male_avg = finite_mean(male)
        female_avg = finite_mean(female)

        return {
            "daily_avg": finite_mean(hourly),
            "peak_hour": peak_hour,
            "peak_value": hourly[peak_hour],
            "low_hour": low_hour,
            "low_value": hourly[low_hour],
            "swing": hourly[peak_hour] - hourly[low_hour],
            "day_avg": day_avg,
            "night_avg": night_avg,
            "day_night_ratio": day_avg / night_avg if night_avg else float("nan"),
            "weekday_avg": weekday_avg,
            "weekend_avg": weekend_avg,
            "weekend_ratio": weekend_avg / weekday_avg if weekday_avg else float("nan"),
            "male_avg": male_avg,
            "female_avg": female_avg,
            "male_share": male_avg / (male_avg + female_avg) if (male_avg + female_avg) else float("nan"),
            "character": self._character(peak_hour, weekend_avg, weekday_avg, day_avg, night_avg),
        }

    @staticmethod
    def _character(peak_hour, weekend_avg, weekday_avg, day_avg, night_avg) -> str:
        """생활인구 패턴으로 상권 성격을 어림잡는다 (규칙 기반 참고값)."""
        if not all(math.isfinite(v) for v in (weekend_avg, weekday_avg, day_avg, night_avg)):
            return "판단 보류 (관측 부족)"
        if not weekday_avg or not night_avg:
            return "판단 보류 (기준 인구 부족)"
        weekend_ratio = weekend_avg / weekday_avg if weekday_avg else 1.0
        day_night = day_avg / night_avg if night_avg else 1.0

        if weekend_ratio >= WEEKEND_BUSY and 11 <= peak_hour <= 21:
            return "주말 상권형 (주말에 더 붐빔)"
        if weekend_ratio <= WEEKDAY_BUSY and 9 <= peak_hour <= 18 and day_night >= OFFICE_DAY_NIGHT:
            return "업무지구형 (평일 낮에 붐빔)"
        if peak_hour >= 20 or peak_hour <= 6 or day_night <= RESIDENTIAL_DAY_NIGHT:
            return "주거지형 (밤에도 인구 유지)"
        return "혼합형 (주거·업무 섞임)"


def summary_text(hotplace: Hotplace) -> str:
    """요약 통계를 사람이 읽을 문장으로 바꾼다."""
    s = hotplace.summary()

    def fmt(key, digits=0, scale=1):
        value = s[key] * scale
        return f"{value:,.{digits}f}" if math.isfinite(value) else "관측 부족"

    female = f"{(1 - s['male_share']) * 100:.1f}" if math.isfinite(s['male_share']) else "관측 부족"
    return (
        f"■ {hotplace.label} (코드 {hotplace.code})\n"
        f"  · 일평균 생활인구   {fmt('daily_avg')} 명\n"
        f"  · 가장 붐비는 시간  {s['peak_hour']:>2d}시  ({fmt('peak_value')} 명)\n"
        f"  · 가장 한산한 시간  {s['low_hour']:>2d}시  ({fmt('low_value')} 명)\n"
        f"  · 낮 / 밤          낮 {fmt('day_avg')} / 밤 {fmt('night_avg')}"
        f"  ({fmt('day_night_ratio', 2)}배)\n"
        f"  · 평일·주말         평일 {fmt('weekday_avg')} / 주말 {fmt('weekend_avg')}"
        f"  ({fmt('weekend_ratio', 2)}배)\n"
        f"  · 성비              남 {fmt('male_share', 1, 100)}% / 여 {female}%\n"
        f"  · 상권 유형(추정)   {s['character']}"
    )


def character_points(population: Population, codebook) -> list[tuple[Dong, dict[str, object]]]:
    """코드표와 매칭되고 두 배율이 모두 계산되는 행정동과 요약 통계."""
    points = []
    for code in population.aggregates:
        dong = codebook.by_code(code)
        if dong is None:
            continue
        stats = Hotplace(dong, population).summary()
        if math.isfinite(stats["day_night_ratio"]) and math.isfinite(stats["weekend_ratio"]):
            points.append((dong, stats))
    return points


def rank_by_daily_average(population: Population, codebook, top: int = 10) -> list[tuple[Dong, float]]:
    """일평균 생활인구 상위 행정동. 어느 동을 볼지 고를 때 참고용."""
    scored: list[tuple[Dong, float]] = []
    for code, agg in population.aggregates.items():
        dong = codebook.by_code(code)
        if dong is None:
            continue
        value = finite_mean(Hotplace(dong, population).mean_hourly())
        if math.isfinite(value):
            scored.append((dong, value))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top]
