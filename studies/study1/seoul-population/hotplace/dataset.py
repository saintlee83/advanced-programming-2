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
import math
import os
import pickle
import sys
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

CACHE_VERSION = 4
CACHE_DIR = (Path.home() / "Library" / "Caches" / "Hotplace"
             if getattr(sys, "frozen", False) and sys.platform == "darwin"
             else Path(__file__).resolve().parent.parent / ".cache")


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
        except (OSError, UnicodeError) as exc:
            raise DataError(f"행정동 코드 파일을 읽을 수 없습니다: {exc}") from exc
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
        key = name.strip().casefold()
        if not key:
            return []
        exact = [d for d in self._dongs if d.name.casefold() == key or str(d.code) == key]
        return exact or [d for d in self._dongs if key in d.label.casefold()]

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
    # Compact date/hour observations support trends and distinguish missing from zero.
    daily: dict[str, dict[int, float]] = field(default_factory=dict)
    counts: list[int] = field(default_factory=lambda: [0] * HOURS)
    weekday_counts: list[int] = field(default_factory=lambda: [0] * HOURS)
    weekend_counts: list[int] = field(default_factory=lambda: [0] * HOURS)


class Population:
    """집계가 끝난 생활인구 데이터셋."""

    def __init__(
        self,
        aggregates: dict[int, DongAggregate],
        dates: set[str],
        weekday_dates: set[str],
        source: str = "",
        duplicate_rows: int = 0,
    ) -> None:
        self.aggregates = aggregates
        self.dates = dates
        self.n_days = len(dates)
        self.n_weekday = len(weekday_dates)
        self.n_weekend = self.n_days - self.n_weekday
        self.source = source
        self.duplicate_rows = duplicate_rows

    @property
    def calendar_dates(self) -> list[str]:
        if not self.dates:
            return []
        start = datetime.datetime.strptime(min(self.dates), "%Y%m%d").date()
        end = datetime.datetime.strptime(max(self.dates), "%Y%m%d").date()
        return [(start + datetime.timedelta(days=i)).strftime("%Y%m%d")
                for i in range((end - start).days + 1)]

    def quality(self, codebook: CodeBook) -> dict[str, int | float]:
        observed = sum(sum(rec.counts) for rec in self.aggregates.values())
        expected = len(self.aggregates) * len(self.calendar_dates) * HOURS
        return {"observed": observed, "expected": expected,
                "coverage": observed / expected if expected else 0.0,
                "missing": max(0, expected - observed),
                "duplicates": self.duplicate_rows,
                "unmatched": sum(codebook.by_code(code) is None for code in self.aggregates)}

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
        parts.append(f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}")
    key = hashlib.sha1("||".join(parts).encode()).hexdigest()[:16]
    return CACHE_DIR / f"agg-v{CACHE_VERSION}-{key}.pickle"


def load_population(
    population_csv: str | os.PathLike,
    code_csv: str | os.PathLike,
    progress=None,
    use_cache: bool = True,
    cancelled=None,
) -> tuple[Population, CodeBook]:
    """인구 파일과 코드 파일을 읽어 :class:`Population` 과 :class:`CodeBook` 을 만든다.

    Args:
        progress: ``fn(percent: int, message: str)`` 형태의 진행률 콜백.
        use_cache: True면 이전 집계 결과를 재사용한다.
    """
    pop_path, code_path = Path(population_csv), Path(code_csv)
    if not pop_path.is_file():
        raise DataError(f"인구 데이터 파일을 찾을 수 없습니다: {pop_path}")
    if not code_path.is_file():
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
    duplicate_rows = 0
    line_no = 1

    try:
        with open(pop_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            if len(header) < COL_END:
                raise DataError(
                    f"인구 데이터의 열 개수가 부족합니다 (필요 {COL_END}, 실제 {len(header)})."
                )

            for line_no, row in enumerate(reader, start=2):
                if cancelled and cancelled():
                    raise DataError("데이터 불러오기를 취소했습니다.")
                if not row or not any(value.strip() for value in row):
                    continue
                if len(row) < COL_END:
                    raise DataError(f"{line_no}행: 인구 데이터의 열 개수가 부족합니다.")
                date = row[COL_DATE].strip()
                if len(date) != 8 or not date.isdigit():
                    raise DataError(f"{line_no}행: 날짜는 YYYYMMDD 형식이어야 합니다.")
                hour = int(row[COL_HOUR])
                code = int(row[COL_CODE])
                if not 0 <= hour < HOURS:
                    raise DataError(f"{line_no}행: 시간대는 0~23이어야 합니다.")
                total = float(row[COL_TOTAL])
                age_values = list(map(float, row[COL_MALE:COL_END]))
                if any(not math.isfinite(v) or v < 0 for v in [total, *age_values]):
                    raise DataError(f"{line_no}행: 인구는 유한한 0 이상의 숫자여야 합니다.")

                is_weekend = weekend_flag.get(date)
                if is_weekend is None:
                    is_weekend = weekend_flag[date] = _is_weekend(date)
                    dates.add(date)
                    if not is_weekend:
                        weekday_dates.add(date)

                rec = aggregates.get(code)
                if rec is None:
                    rec = aggregates[code] = DongAggregate(code=code)

                daily = rec.daily.setdefault(date, {})
                if hour in daily:
                    duplicate_rows += 1
                    continue  # One observation per date/hour/dong; retain the first.
                daily[hour] = total
                rec.counts[hour] += 1
                rec.total[hour] += total
                if is_weekend:
                    rec.weekend[hour] += total
                    rec.weekend_counts[hour] += 1
                else:
                    rec.weekday[hour] += total
                    rec.weekday_counts[hour] += 1

                bucket = rec.age[hour]
                bucket[:] = [
                    a + v for a, v in zip(bucket, age_values)
                ]

                if line_no % 20000 == 0:
                    pct = min(97, 1 + int(96 * line_no / estimated))
                    report(pct, f"인구 데이터 {line_no:,}행 처리 중...")
    except UnicodeDecodeError as exc:
        raise DataError(f"인구 데이터 인코딩을 읽을 수 없습니다(UTF-8 아님): {exc}") from exc
    except (ValueError, StopIteration) as exc:
        raise DataError(f"{line_no}행: 인구 데이터의 날짜 또는 숫자가 올바르지 않습니다: {exc}") from exc
    except OSError as exc:
        raise DataError(f"인구 데이터 파일을 읽을 수 없습니다: {exc}") from exc

    if not aggregates:
        raise DataError("인구 데이터에서 읽어들인 행이 없습니다.")
    if not any(codebook.by_code(code) for code in aggregates):
        raise DataError("인구 데이터와 코드표에 일치하는 행정동 코드가 없습니다.")

    population = Population(
        aggregates=aggregates,
        dates=dates,
        weekday_dates=weekday_dates,
        source=str(pop_path),
        duplicate_rows=duplicate_rows,
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

    ``HOTPLACE_DATA_DIR`` 환경변수를 먼저 보고, 없으면 저장소의 ``data/`` 와
    형제 저장소인 Univ_Programming1 의 midterm 데이터 폴더를 찾아본다.
    저장소 루트는 위로 올라가며 ``pyproject.toml`` 이 있는 폴더로 정하므로
    앱 폴더를 옮겨도 동작한다.
    """
    env = os.environ.get("HOTPLACE_DATA_DIR")
    if env and Path(env).is_dir():
        return Path(env)

    # 빌드한 앱은 실행 파일 위치에서, 소스 실행은 이 파일 위치에서 찾는다.
    start = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    repo_root = next((parent for parent in start.parents if (parent / "pyproject.toml").is_file()), None)
    if repo_root is None:
        return None
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
