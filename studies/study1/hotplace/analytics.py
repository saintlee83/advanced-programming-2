"""Explainable diagnostics built on the five baseline analyses; no predictive claims."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from statistics import median, pstdev

from .hotplace import Hotplace, finite_mean, rank_by_daily_average


@dataclass(frozen=True)
class Insight:
    category: str
    title: str
    detail: str


def display(value: float, suffix: str = "", digits: int = 1) -> str:
    return f"{value:,.{digits}f}{suffix}" if math.isfinite(value) else "관측 부족"


def diagnostics(place: Hotplace, codebook=None) -> dict:
    hourly = place.mean_hourly()
    average = finite_mean(hourly)
    available = [v for v in hourly if math.isfinite(v)]
    volatility = pstdev(available) / average * 100 if len(available) >= 2 and average > 0 else math.nan
    windows = [(h, sum(hourly[(h + step) % 24] for step in range(3)) / 3)
               for h in range(24) if all(math.isfinite(hourly[(h + step) % 24]) for step in range(3))]
    busy = max(windows, key=lambda item: item[1]) if windows else None
    quiet = min(windows, key=lambda item: item[1]) if windows else None
    male, female = place.mean_by_age()
    ages = [a + b for a, b in zip(male, female)]
    age_total = sum(ages)
    young_share = sum(ages[3:7]) / age_total * 100 if age_total else math.nan
    senior_share = sum(ages[12:]) / age_total * 100 if age_total else math.nan
    series = place.analysis6()
    complete = [(day, value) for day, value in zip(series.xlabels, series.values[0]) if math.isfinite(value)]
    anomalies = []
    calibrated_groups = 0
    for weekend in (False, True):
        group = [(day, value) for day, value in complete
                 if (datetime.strptime(day, "%Y%m%d").weekday() >= 5) == weekend]
        if len(group) < 7:
            continue
        center = median(value for _, value in group)
        mad = median(abs(value - center) for _, value in group)
        if mad > 0:
            calibrated_groups += 1
            anomalies.extend((day, value, 0.67448975 * (value - center) / mad) for day, value in group
                             if abs(0.67448975 * (value - center) / mad) > 3.5)
    anomalies.sort()
    expected = len(place._pop.calendar_dates) * 24
    coverage = sum(place._agg.counts) / expected * 100 if expected and place._agg.daily else math.nan
    ranking = rank_by_daily_average(place._pop, codebook, top=len(place._pop.aggregates)) if codebook else []
    rank = next((i for i, (dong, _) in enumerate(ranking, 1) if dong.code == place.code), None)
    return {"average": average, "volatility": volatility, "busy": busy, "quiet": quiet,
            "young_share": young_share, "senior_share": senior_share,
            "coverage": coverage, "complete_days": len(complete), "anomalies": anomalies,
            "calibrated_groups": calibrated_groups,
            "rank": rank, "rank_total": len(ranking)}


def compare_places(left: Hotplace, right: Hotplace) -> dict:
    a, b = left.mean_hourly(), right.mean_hourly()
    common = [(h, x, y) for h, (x, y) in enumerate(zip(a, b)) if math.isfinite(x) and math.isfinite(y)]
    ma, mb = finite_mean(x for _, x, _ in common), finite_mean(y for _, _, y in common)
    numerator = sum((x - ma) * (y - mb) for _, x, y in common)
    denominator = math.sqrt(sum((x - ma) ** 2 for _, x, _ in common) * sum((y - mb) ** 2 for _, _, y in common))
    correlation = max(-1.0, min(1.0, numerator / denominator)) if denominator and len(common) >= 3 else math.nan
    gap = max(common, key=lambda item: abs(item[1] - item[2])) if common else None
    return {"correlation": correlation, "common_hours": len(common),
            "difference": ma - mb, "relative_difference": (ma / mb - 1) * 100 if mb > 0 else math.nan,
            "largest_gap": (gap[0], gap[1] - gap[2]) if gap else None}


def similarity_label(correlation: float) -> str:
    """상관계수를 읽기 쉬운 말로 옮긴다. 숫자와 함께 보여 준다."""
    if not math.isfinite(correlation):
        return "산출할 수 없음"
    if correlation >= 0.9:
        return "매우 비슷함"
    if correlation >= 0.7:
        return "비슷함"
    if correlation >= 0.4:
        return "조금 비슷함"
    return "다름"


# 비교표의 행 순서와 각 항목의 계산 기준. 화면과 리포트가 함께 쓴다.
ROWS = (
    ("busy", "붐비는 3시간", "연속한 3시간의 평균 인구가 가장 높은 구간"),
    ("volatility", "시간대별 변동", "시간대별 평균의 표준편차 ÷ 평균. 클수록 시간에 따라 인구 차이가 큽니다"),
    ("ages", "20~39세 비중", "성별·연령 집계 합계 기준이라 총생활인구와 조금 다를 수 있습니다"),
    ("unusual", "평소와 다른 날", "평일·주말을 나눠 중앙값에서 크게 벗어난 날(수정 z 점수 3.5 초과). 공휴일은 따로 보정하지 않습니다"),
    ("rank", "서울 내 순위", "코드표와 매칭된 행정동 중 일평균 생활인구 순위"),
    ("coverage", "관측 완전성", "기간 내 날짜 × 24시간 중 실제 관측이 있는 비율. 빠진 시간은 0으로 채우지 않습니다"),
)
ROW_TITLES = {key: title for key, title, _ in ROWS}


def _day(stamp: str) -> str:
    return f"{stamp[4:6]}/{stamp[6:]}({'월화수목금토일'[datetime.strptime(stamp, '%Y%m%d').weekday()]})"


def insight_cards(place: Hotplace, codebook=None) -> list[Insight]:
    """ROWS 순서대로 지역 하나의 값(title)과 보충 설명(detail)을 만든다."""
    stats = diagnostics(place, codebook)
    summary = place.summary()
    values: dict[str, tuple[str, str]] = {}

    if stats["busy"]:
        hour, value = stats["busy"]
        ratio = f" · 하루 평균의 {value / stats['average']:.2f}배" if stats["average"] else ""
        values["busy"] = (f"{hour}~{(hour + 3) % 24}시", f"3시간 평균 {value:,.0f}명{ratio}")
    else:
        values["busy"] = ("관측 부족", "")

    extremes = ""
    if math.isfinite(summary["peak_value"]) and math.isfinite(summary["low_value"]):
        extremes = (f"가장 적은 {summary['low_hour']}시 {summary['low_value']:,.0f}명 · "
                    f"가장 많은 {summary['peak_hour']}시 {summary['peak_value']:,.0f}명")
    values["volatility"] = (display(stats["volatility"], "%"), extremes)
    values["ages"] = (display(stats["young_share"], "%"), f"65세 이상 {display(stats['senior_share'], '%')}")

    anomalies = stats["anomalies"]
    if stats["calibrated_groups"]:
        days = ", ".join(f"{_day(day)} {value:,.0f}명" for day, value, _ in anomalies[:4])
        if len(anomalies) > 4:
            days += f" 외 {len(anomalies) - 4}일"
        if stats["calibrated_groups"] < 2:
            days = (days + " · " if days else "") + "평일·주말 중 한쪽만 판단했습니다"
        values["unusual"] = (f"{len(anomalies)}일" if anomalies else "없음", days)
    else:
        values["unusual"] = ("판단 보류", "완전한 날이 7일 미만이거나 날마다 값이 같습니다")

    values["rank"] = ((f"{stats['rank']}위", f"전체 {stats['rank_total']}곳 기준") if stats["rank"]
                      else ("—", "코드표에 없는 지역입니다"))
    values["coverage"] = (display(stats["coverage"], "%"), f"24시간이 모두 관측된 날 {stats['complete_days']}일")
    return [Insight(ROW_TITLES[key], *values[key]) for key, _, _ in ROWS]


def report_text(left: Hotplace, right: Hotplace, codebook) -> str:
    comparison = compare_places(left, right)
    gap = comparison["largest_gap"]
    correlation = comparison["correlation"]
    lines = ["서울 생활인구 비교 리포트", "",
             f"기간  {left._pop.period}",
             f"A     {left.label}",
             f"B     {right.label}", "",
             "[두 지역 비교]",
             f"하루 흐름 상관계수   {display(correlation, digits=3)} ({similarity_label(correlation)})",
             f"공통 관측 시간대     {comparison['common_hours']} / 24",
             f"평균 인구 차이       A − B {display(comparison['difference'], '명', 0)}"]
    if gap:
        lines.append(f"차이가 가장 큰 시간  {gap[0]}시 (A − B {gap[1]:+,.0f}명)")
    lines.append("")
    lines.append("[항목별 비교]")
    columns = [insight_cards(place, codebook) for place in (left, right)]
    for a, b in zip(*columns):
        lines.append(a.category)
        for name, card in zip("AB", (a, b)):
            lines.append(f"  {name}  {card.title}" + (f" — {card.detail}" if card.detail else ""))
    lines.append("")
    lines.append("[계산 기준]")
    lines.extend(f"- {title}: {note}" for _, title, note in ROWS)
    lines.append("- 생활인구는 특정 시간에 그 지역에 있던 인구의 추정치입니다. "
                 "일평균은 시간대 평균이며 하루 방문자 수가 아닙니다.")
    return "\n".join(lines)
