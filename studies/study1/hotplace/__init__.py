"""서울 생활인구(LOCAL_PEOPLE_DONG) 분석 패키지.

레이어는 셋으로 나뉜다.

    dataset   CSV 읽기 · 행정동별 집계 · 캐시
    hotplace  Hotplace 클래스 (analysis1~5, 요약 통계)
    plotting  matplotlib 렌더링
    ui        PyQt5 화면
"""

from .dataset import (
    CodeBook, DataError, Dong, Population, default_data_dir,
    find_population_csv, load_population,
)
from .hotplace import AgePyramid, Hotplace, LineSeries, rank_by_daily_average, summary_text

__all__ = [
    "AgePyramid", "CodeBook", "DataError", "Dong", "Hotplace", "LineSeries",
    "Population", "default_data_dir", "find_population_csv", "load_population",
    "rank_by_daily_average", "summary_text",
]
