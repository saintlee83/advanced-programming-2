#!/usr/bin/env python3
"""서울 생활인구 분석기 실행 파일.

    uv run app.py                  # GUI 실행 (이 폴더에서)
    uv run app.py --check 역삼1동   # GUI 없이 분석 결과만 확인
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# matplotlib 이 Qt 바인딩을 고를 때 PyQt5 를 쓰도록 못 박는다.
os.environ.setdefault("QT_API", "pyqt5")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hotplace.dataset import (                                     # noqa: E402
    DataError, default_data_dir, find_population_csv, load_population,
)


def resolve_paths(args) -> tuple[str, str]:
    """명령줄 인자 → 기본 데이터 폴더 순으로 파일 경로를 정한다."""
    population_csv, code_csv = args.population, args.codes
    if population_csv and code_csv:
        return population_csv, code_csv

    data_dir = default_data_dir()
    if data_dir is None:
        raise SystemExit(
            "데이터 폴더를 찾지 못했습니다. --population / --codes 로 경로를 지정하거나\n"
            "HOTPLACE_DATA_DIR 환경변수를 설정해 주세요."
        )
    found = find_population_csv(data_dir)
    if found is None:
        raise SystemExit(f"{data_dir} 에서 LOCAL_PEOPLE_DONG_*.csv 를 찾지 못했습니다.")
    return population_csv or str(found), code_csv or str(data_dir / "dong_code.csv")


def run_check(args) -> int:
    """GUI 없이 데이터 로딩과 분석 1~13을 한 번씩 실행해 본다."""
    from hotplace.hotplace import Hotplace, PairedAnalysis, rank_by_daily_average, summary_text
    from hotplace.analytics import report_text
    from hotplace.plotting import configure_matplotlib, theme

    population_csv, code_csv = resolve_paths(args)
    print(f"인구 데이터 : {population_csv}")
    print(f"행정동 코드 : {code_csv}\n")

    try:
        population, codebook = load_population(
            population_csv, code_csv,
            progress=lambda pct, msg: print(f"  [{pct:3d}%] {msg}", end="\r"),
        )
    except DataError as exc:
        print(f"\n오류: {exc}")
        return 1
    print()

    print(f"기간 {population.period} · 행정동 {len(population.aggregates)}개 "
          f"· 평일 {population.n_weekday}일 / 주말 {population.n_weekend}일")
    print(f"한글 폰트: {configure_matplotlib()}\n")

    ranking = rank_by_daily_average(population, codebook, top=5)
    print("일평균 생활인구 상위 5곳")
    for rank, (dong, value) in enumerate(ranking, start=1):
        print(f"  {rank}. {dong.label:<14s} {value:>12,.0f} 명")
    print()

    matches = [dong for dong in codebook.search(args.check) if population.has(dong.code)] if args.check else []
    if args.check and not matches:
        print(f"분석할 지역을 찾을 수 없습니다: {args.check}")
        return 1
    dong_a = matches[0] if matches else ranking[0][0]
    dong_b = next((d for d, _ in ranking if d.code != dong_a.code), dong_a)
    place_a, place_b = Hotplace(dong_a, population), Hotplace(dong_b, population)

    print(summary_text(place_a))
    print()

    regions = (place_a.label, place_b.label)
    results = {
        "analysis1": place_a.analysis1(),
        "analysis2": place_a.analysis2(),
        "analysis3": place_a.analysis3(),
        "analysis4": place_a.analysis4(place_b),
        "analysis5": place_a.analysis5(),
        "analysis6": place_a.analysis6(),
        "analysis7": PairedAnalysis("요일 × 시간대 비교", regions, (place_a.analysis7(), place_b.analysis7())),
        "analysis8": place_a.analysis8(place_b),
        "analysis9": place_a.analysis9(place_b),
        "analysis10": PairedAnalysis("요일별 평균 비교", regions, (place_a.analysis10(), place_b.analysis10())),
        "analysis11": PairedAnalysis("시간대별 남녀 비율 비교", regions, (place_a.analysis11(), place_b.analysis11())),
        "analysis12": place_a.analysis12(place_b),
        "analysis13": PairedAnalysis("시간대별 연령 구성 비교", regions, (place_a.analysis13(), place_b.analysis13())),
    }
    for name, result in results.items():
        print(f"  {name}: {result.title}")

    quality = population.quality(codebook)
    print(f"\n관측 완전성 {quality['coverage']:.1%} · 누락 {quality['missing']:,}개 · 중복 제외 {quality['duplicates']:,}행")
    print("\n" + report_text(place_a, place_b, codebook))

    if args.out:
        from matplotlib.figure import Figure
        from hotplace.plotting import draw_result

        class _Fig:                       # 캔버스 없이 Figure 만 쓰는 얇은 껍데기
            def __init__(self):
                self.figure = Figure(figsize=(7.4, 7.2), dpi=110, facecolor=theme().surface)
            def clear(self): self.figure.clear()
            def draw_idle(self): pass

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, result in results.items():
            holder = _Fig()
            draw_result(holder, result)
            path = out_dir / f"{name}.png"
            holder.figure.savefig(path, dpi=160, facecolor=theme().surface)
            print(f"  저장: {path}")

    print("\n분석 1~13 정상 동작 확인.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="서울 생활인구 분석기")
    parser.add_argument("--population", help="LOCAL_PEOPLE_DONG_*.csv 경로")
    parser.add_argument("--codes", help="dong_code.csv 경로")
    parser.add_argument("--check", nargs="?", const="", metavar="행정동명",
                        help="GUI 없이 분석 결과만 출력")
    parser.add_argument("--out", metavar="폴더", help="--check 와 함께 쓰면 그래프를 PNG로 저장")
    args = parser.parse_args()

    if args.check is not None:
        return run_check(args)

    from hotplace.ui import run
    return run(args.population, args.codes)


if __name__ == "__main__":
    raise SystemExit(main())
