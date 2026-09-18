"""서울 생활인구(LOCAL_PEOPLE_DONG) 분석 패키지.

계산과 화면을 분리한다.

    dataset   CSV 읽기 · 행정동별 집계 · 캐시
    hotplace  Hotplace 클래스 (analysis1~8, 요약 통계)
    analytics 확장 진단 · 리포트
    plotting  matplotlib 렌더링
    ui        PyQt5 화면
"""

from .dataset import (
    CodeBook, DataError, Dong, Population, default_data_dir,
    find_population_csv, load_population,
)
from .hotplace import AgePyramid, Heatmap, Hotplace, LineSeries, PairedAnalysis, rank_by_daily_average, summary_text

__all__ = [
    "AgePyramid", "Heatmap", "PairedAnalysis", "CodeBook", "DataError", "Dong", "Hotplace", "LineSeries",
    "Population", "default_data_dir", "find_population_csv", "load_population",
    "rank_by_daily_average", "summary_text",
]
