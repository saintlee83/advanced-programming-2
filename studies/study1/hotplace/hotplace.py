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
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dataset import AGE_BANDS, HOURS, N_BANDS, Dong, Population

# 주간 / 야간 구간 정의 (요약 통계에서 사용)
DAY_HOURS = range(9, 19)     # 09시 ~ 18시
NIGHT_HOURS = range(0, 7)    # 00시 ~ 06시


@dataclass
class LineSeries:
    """시간대(0~23)를 x축으로 하는 꺾은선 그래프 한 장 분량의 결과."""

    title: str
    labels: list[str]
    values: list[list[float]]
    xlabel: str = "시간대"
    ylabel: str = "평균 생활인구(명)"
    note: str = ""

    def csv_rows(self) -> list[list[str]]:
        header = ["시간대"] + self.labels
        rows = [header]
        for hour in range(HOURS):
            rows.append([str(hour)] + [f"{v[hour]:.1f}" for v in self.values])
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
class PairedAnalysis:
    """동일한 분석을 두 지역에 적용한 결과. 두 지역 모두 CSV에 포함한다."""

    title: str
    regions: tuple[str, str]
    analyses: tuple[LineSeries, LineSeries] | tuple[AgePyramid, AgePyramid]
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
    def mean_hourly(self) -> list[float]:
        """시간대별 평균 생활인구 (한 달 누적 ÷ 일수)."""
        days = self._pop.n_days or 1
        return [v / days for v in self._agg.total]

    def mean_weekday(self) -> list[float]:
        days = self._pop.n_weekday or 1
        return [v / days for v in self._agg.weekday]

    def mean_weekend(self) -> list[float]:
        days = self._pop.n_weekend or 1
        return [v / days for v in self._agg.weekend]

    def mean_by_gender(self) -> tuple[list[float], list[float]]:
        """(남자, 여자) 시간대별 평균 생활인구."""
        days = self._pop.n_days or 1
        male, female = [], []
        for hour in range(HOURS):
            band = self._agg.age[hour]
            male.append(sum(band[:N_BANDS]) / days)
            female.append(sum(band[N_BANDS:]) / days)
        return male, female

    def mean_by_age(self) -> tuple[list[float], list[float]]:
        """(남자, 여자) 연령대별 평균 생활인구. 24시간을 평균한 값이다."""
        days = self._pop.n_days or 1
        divisor = days * HOURS
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
            note=f"평일 {self._pop.n_weekday}일 · 주말 {self._pop.n_weekend}일 기준",
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
            note="24시간 · 전체 일자 평균",
        )

    # ── 요약 통계 ────────────────────────────────────────────────────
    def summary(self) -> dict[str, object]:
        """그래프 아래에 함께 보여줄 요약 지표."""
        hourly = self.mean_hourly()
        peak_hour = max(range(HOURS), key=lambda h: hourly[h])
        low_hour = min(range(HOURS), key=lambda h: hourly[h])

        day_avg = sum(hourly[h] for h in DAY_HOURS) / len(DAY_HOURS)
        night_avg = sum(hourly[h] for h in NIGHT_HOURS) / len(NIGHT_HOURS)

        weekday = self.mean_weekday()
        weekend = self.mean_weekend()
        weekday_avg = sum(weekday) / HOURS
        weekend_avg = sum(weekend) / HOURS

        male, female = self.mean_by_gender()
        male_avg = sum(male) / HOURS
        female_avg = sum(female) / HOURS

        return {
            "daily_avg": sum(hourly) / HOURS,
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
        weekend_ratio = weekend_avg / weekday_avg if weekday_avg else 1.0
        day_night = day_avg / night_avg if night_avg else 1.0

        if weekend_ratio >= 1.03 and 11 <= peak_hour <= 21:
            return "주말 집객형 (상업·나들이 상권)"
        if weekend_ratio <= 0.93 and 9 <= peak_hour <= 18 and day_night >= 1.3:
            return "평일 오피스형 (업무 밀집)"
        if peak_hour >= 20 or peak_hour <= 6 or day_night <= 1.05:
            return "주거 중심형 (야간 인구 우세)"
        return "혼합형 (주거·업무 혼재)"


def summary_text(hotplace: Hotplace) -> str:
    """요약 통계를 사람이 읽을 문장으로 바꾼다."""
    s = hotplace.summary()
    return (
        f"■ {hotplace.label} (코드 {hotplace.code})\n"
        f"  · 일평균 생활인구   {s['daily_avg']:>12,.0f} 명\n"
        f"  · 최대 혼잡 시간대  {s['peak_hour']:>2d}시  ({s['peak_value']:,.0f} 명)\n"
        f"  · 최소 시간대       {s['low_hour']:>2d}시  ({s['low_value']:,.0f} 명)\n"
        f"  · 주야 격차         주간 {s['day_avg']:,.0f} / 야간 {s['night_avg']:,.0f}"
        f"  (배율 {s['day_night_ratio']:.2f})\n"
        f"  · 평일·주말         평일 {s['weekday_avg']:,.0f} / 주말 {s['weekend_avg']:,.0f}"
        f"  (주말비 {s['weekend_ratio']:.2f})\n"
        f"  · 성비              남 {s['male_share'] * 100:.1f}% / 여 {(1 - s['male_share']) * 100:.1f}%\n"
        f"  · 추정 상권 성격    {s['character']}"
    )


def rank_by_daily_average(population: Population, codebook, top: int = 10) -> list[tuple[Dong, float]]:
    """일평균 생활인구 상위 행정동. 어느 동을 볼지 고를 때 참고용."""
    days = population.n_days or 1
    scored: list[tuple[Dong, float]] = []
    for code, agg in population.aggregates.items():
        dong = codebook.by_code(code)
        if dong is None:
            continue
        scored.append((dong, sum(agg.total) / (days * HOURS)))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top]
