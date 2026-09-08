"""서울 생활인구 CSV를 읽어 행정동별로 집계하는 모듈.

두 개의 입력 파일을 다룬다.

* ``LOCAL_PEOPLE_DONG_YYYYMM.csv`` - 행정동 · 날짜 · 시간대별 생활인구
* ``dong_code.csv``                - 행정동 코드표 (시도 / 시군구 / 행정동명)

인구 파일은 30만 행이 넘기 때문에 원본을 그대로 들고 있지 않고,
읽으면서 행정동별 24시간 누적치로 줄여 담는다. 한 번 집계한 결과는
``.cache`` 에 저장해 두었다가 다음 실행에서 그대로 재사용한다.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path

# ── 인구 파일의 열 위치 ────────────────────────────────────────────────
COL_DATE = 0        # 기준일ID   (YYYYMMDD)
COL_HOUR = 1        # 시간대구분 (00 ~ 23)
COL_CODE = 2        # 행정동코드 (행자부 8자리)
COL_TOTAL = 3       # 총생활인구수
COL_MALE = 4        # 남자 0~9세 부터 14개 연령대
COL_FEMALE = 18     # 여자 0~9세 부터 14개 연령대
COL_END = 32        # 여자 70세 이상 다음 열

AGE_BANDS = (
    "0-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
    "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70+",
)
N_BANDS = len(AGE_BANDS)        # 14
N_AGE_COLS = N_BANDS * 2        # 남 14 + 여 14 = 28
HOURS = 24

CACHE_VERSION = 3
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


class DataError(Exception):
    """입력 파일을 읽을 수 없을 때 발생."""


# ── 행정동 코드표 ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class Dong:
    """행정동 한 곳. ``code`` 가 인구 파일과 이어지는 열쇠다."""

    code: int
    sido: str
    sigungu: str
    name: str

    @property
    def label(self) -> str:
        """'강남구 역삼1동' 처럼 시군구를 붙여 동명 중복을 없앤 이름."""
        return f"{self.sigungu} {self.name}"


class CodeBook:
    """행정동 코드표. 이름·코드 양방향 조회를 담당한다."""

    def __init__(self, dongs: list[Dong]) -> None:
        self._dongs = dongs
        self._by_code = {d.code: d for d in dongs}

    @classmethod
    def from_csv(cls, path: str | os.PathLike) -> "CodeBook":
        dongs: list[Dong] = []
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                next(reader)      # 한글 헤더
                next(reader)      # 영문 헤더
                for row in reader:
                    if len(row) < 5 or not row[1].strip():
                        continue
                    dongs.append(
                        Dong(
                            code=int(row[1]),
                            sido=row[2].strip(),
                            sigungu=row[3].strip(),
                            name=row[4].strip(),
                        )
                    )
        except FileNotFoundError as exc:
            raise DataError(f"행정동 코드 파일을 찾을 수 없습니다: {path}") from exc
        except (ValueError, IndexError, StopIteration) as exc:
            raise DataError(f"행정동 코드 파일 형식이 올바르지 않습니다: {exc}") from exc

        if not dongs:
            raise DataError("행정동 코드 파일에서 읽어들인 행이 없습니다.")
        return cls(dongs)

    def __len__(self) -> int:
        return len(self._dongs)

    def by_code(self, code: int) -> Dong | None:
        return self._by_code.get(code)

    def search(self, name: str) -> list[Dong]:
        """행정동명으로 검색. '신사동'처럼 여러 구에 있는 이름은 모두 돌려준다."""
        key = name.strip()
        return [d for d in self._dongs if d.name == key]

    def sigungu_list(self) -> list[str]:
        return sorted({d.sigungu for d in self._dongs})

    def in_sigungu(self, sigungu: str) -> list[Dong]:
        return sorted(
            (d for d in self._dongs if d.sigungu == sigungu),
            key=lambda d: d.name,
        )


# ── 행정동별 집계 ─────────────────────────────────────────────────────
@dataclass
class DongAggregate:
    """행정동 한 곳의 24시간 누적 생활인구.

    모두 '한 달치 합계'라서, 나눌 일수는 :class:`Population` 이 들고 있다.
    """

    code: int
    total: list[float] = field(default_factory=lambda: [0.0] * HOURS)
    weekday: list[float] = field(default_factory=lambda: [0.0] * HOURS)
    weekend: list[float] = field(default_factory=lambda: [0.0] * HOURS)
    # age[시간대][0:14] = 남자 연령대, [14:28] = 여자 연령대
    age: list[list[float]] = field(
        default_factory=lambda: [[0.0] * N_AGE_COLS for _ in range(HOURS)]
    )


class Population:
    """집계가 끝난 생활인구 데이터셋."""

    def __init__(
        self,
        aggregates: dict[int, DongAggregate],
        dates: set[str],
        weekday_dates: set[str],
        source: str = "",
    ) -> None:
        self.aggregates = aggregates
        self.dates = dates
        self.n_days = len(dates)
        self.n_weekday = len(weekday_dates)
        self.n_weekend = self.n_days - self.n_weekday
        self.source = source

    @property
    def period(self) -> str:
        if not self.dates:
            return ""
        lo, hi = min(self.dates), max(self.dates)
        return f"{lo[:4]}-{lo[4:6]}-{lo[6:]} ~ {hi[:4]}-{hi[4:6]}-{hi[6:]}"

    def has(self, code: int) -> bool:
        return code in self.aggregates

    def get(self, code: int) -> DongAggregate:
        try:
            return self.aggregates[code]
        except KeyError:
            raise DataError(f"인구 데이터에 없는 행정동 코드입니다: {code}") from None


def _is_weekend(date_str: str) -> bool:
    year, month, day = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
    return datetime.date(year, month, day).weekday() >= 5


def _estimate_rows(path: Path) -> int:
    """진행률 표시용 행 수 추정. 행 길이가 고르므로 파일 크기로 나눠 잡는다."""
    size = path.stat().st_size
    sample_bytes, sample_lines = 0, 0
    with open(path, "rb") as f:
        f.readline()  # 헤더
        for line in f:
            sample_bytes += len(line)
            sample_lines += 1
            if sample_lines >= 500:
                break
    if not sample_lines:
        return 1
    return max(1, int(size / (sample_bytes / sample_lines)))


def _cache_path(population_csv: Path, code_csv: Path) -> Path:
    parts = []
    for p in (population_csv, code_csv):
        st = p.stat()
        parts.append(f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}")
    key = hashlib.sha1("||".join(parts).encode()).hexdigest()[:16]
    return CACHE_DIR / f"agg-v{CACHE_VERSION}-{key}.pickle"


def load_population(
    population_csv: str | os.PathLike,
    code_csv: str | os.PathLike,
    progress=None,
    use_cache: bool = True,
) -> tuple[Population, CodeBook]:
    """인구 파일과 코드 파일을 읽어 :class:`Population` 과 :class:`CodeBook` 을 만든다.

    Args:
        progress: ``fn(percent: int, message: str)`` 형태의 진행률 콜백.
        use_cache: True면 이전 집계 결과를 재사용한다.
    """
    pop_path, code_path = Path(population_csv), Path(code_csv)
    if not pop_path.exists():
        raise DataError(f"인구 데이터 파일을 찾을 수 없습니다: {pop_path}")
    if not code_path.exists():
        raise DataError(f"행정동 코드 파일을 찾을 수 없습니다: {code_path}")

    def report(pct: int, msg: str) -> None:
        if progress is not None:
            progress(pct, msg)

    report(0, "행정동 코드표를 읽는 중...")
    codebook = CodeBook.from_csv(code_path)

    cache_file = _cache_path(pop_path, code_path) if use_cache else None
    if cache_file is not None and cache_file.exists():
        report(50, "저장해 둔 집계 결과를 불러오는 중...")
        try:
            with open(cache_file, "rb") as f:
                population = pickle.load(f)
            report(100, f"캐시에서 불러옴 ({len(population.aggregates)}개 행정동)")
            return population, codebook
        except Exception:
            cache_file.unlink(missing_ok=True)   # 깨진 캐시는 버리고 다시 읽는다

    report(1, "인구 데이터를 읽는 중...")
    estimated = _estimate_rows(pop_path)
    aggregates: dict[int, DongAggregate] = {}
    dates: set[str] = set()
    weekday_dates: set[str] = set()
    weekend_flag: dict[str, bool] = {}

    try:
        with open(pop_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            if len(header) < COL_END:
                raise DataError(
                    f"인구 데이터의 열 개수가 부족합니다 (필요 {COL_END}, 실제 {len(header)})."
                )

            for line_no, row in enumerate(reader, start=2):
                if len(row) < COL_END:
                    continue                     # 파일 끝의 빈 줄 등
                date = row[COL_DATE]
                hour = int(row[COL_HOUR])
                code = int(row[COL_CODE])

                is_weekend = weekend_flag.get(date)
                if is_weekend is None:
                    is_weekend = weekend_flag[date] = _is_weekend(date)
                    dates.add(date)
                    if not is_weekend:
                        weekday_dates.add(date)

                rec = aggregates.get(code)
                if rec is None:
                    rec = aggregates[code] = DongAggregate(code=code)

                total = float(row[COL_TOTAL])
                rec.total[hour] += total
                if is_weekend:
                    rec.weekend[hour] += total
                else:
                    rec.weekday[hour] += total

                bucket = rec.age[hour]
                bucket[:] = [
                    a + v for a, v in zip(bucket, map(float, row[COL_MALE:COL_END]))
                ]

                if line_no % 20000 == 0:
                    pct = min(97, 1 + int(96 * line_no / estimated))
                    report(pct, f"인구 데이터 {line_no:,}행 처리 중...")
    except UnicodeDecodeError as exc:
        raise DataError(f"인구 데이터 인코딩을 읽을 수 없습니다(UTF-8 아님): {exc}") from exc
    except ValueError as exc:
        raise DataError(f"인구 데이터에 숫자로 바꿀 수 없는 값이 있습니다: {exc}") from exc

    if not aggregates:
        raise DataError("인구 데이터에서 읽어들인 행이 없습니다.")

    population = Population(
        aggregates=aggregates,
        dates=dates,
        weekday_dates=weekday_dates,
        source=str(pop_path),
    )

    if cache_file is not None:
        report(98, "집계 결과를 저장하는 중...")
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "wb") as f:
                pickle.dump(population, f, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError:
            pass                                  # 캐시 저장 실패는 치명적이지 않다

    report(100, f"{len(aggregates)}개 행정동 · {population.n_days}일치 집계 완료")
    return population, codebook


def default_data_dir() -> Path | None:
    """미리 채워 둘 기본 데이터 폴더를 찾는다.

    ``HOTPLACE_DATA_DIR`` 환경변수를 먼저 보고, 없으면 형제 저장소인
    Univ_Programming1 의 midterm 데이터 폴더를 찾아본다.
    """
    env = os.environ.get("HOTPLACE_DATA_DIR")
    if env and Path(env).is_dir():
        return Path(env)

    here = Path(__file__).resolve()
    repo_root = here.parents[3]                   # .../advanced-programming-2
    candidates = [
        repo_root / "data",
        repo_root.parent / "Univ_Programming1" / "Lectures" / "midterm" / "data",
    ]
    for c in candidates:
        if (c / "dong_code.csv").exists():
            return c
    return None


def find_population_csv(data_dir: Path) -> Path | None:
    """데이터 폴더에서 LOCAL_PEOPLE_DONG_*.csv 를 찾아준다."""
    matches = sorted(data_dir.glob("LOCAL_PEOPLE_DONG_*.csv"))
    return matches[-1] if matches else None
