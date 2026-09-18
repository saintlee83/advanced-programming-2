# 발표 Q&A 답변 스크립트 — 서울 생활인구 비교

대상: [seoul-population](seoul-population/) · 코드 해설 원문: [original-ver.md](original-ver.md)
기준: 2026-09-18 작업 트리. 같은 날 `unittest` 31개 통과 확인.

> 인용 블록(`>`)이 **그대로 말할 답변**이고, 그 아래 `근거`가 화면에 띄울 코드 위치다.
> 파일 경로는 모두 `seoul-population/hotplace/` 기준이다.

---

## 0. 어떤 질문이든 이 순서로 답한다

1. **한 문장 결론** — "그건 ○○ 클래스가 담당합니다."
2. **코드 위치** — 파일 → 클래스/함수 이름.
3. **데이터 흐름** — 무엇이 들어와서 무엇이 나가는지.
4. **왜 그렇게 했는지 / 한계** — 한 문장.

모든 기능은 결국 아래 한 줄로 환원된다. 막히면 이 줄로 돌아온다.

```text
사용자 입력(Qt 시그널)
  → MainWindow 슬롯 (ui.py)
  → Hotplace.analysisN() (hotplace.py)      ← 계산만, 화면 모름
  → 결과 데이터 클래스 (LineSeries / Heatmap / …)
  → draw_result() (plotting.py)             ← 그리기만, 계산 안 함
  → PlotCanvas (matplotlib Figure를 담은 Qt 위젯)
```

---

## 1. 오프닝 (30초)

> 서울시 생활인구 CSV를 행정동별로 집계해서, 두 행정동을 같은 기준·같은 축으로 비교하는 데스크톱 앱입니다.
> 구조는 세 층입니다. `dataset.py`가 CSV를 읽어 집계하고, `hotplace.py`가 그 집계에서 14개 분석 결과를 데이터 클래스로 만들고, `plotting.py`가 그 결과를 matplotlib으로 그립니다. `ui.py`는 PySide6로 네 개 페이지를 만들고 사용자의 선택을 이 세 층에 연결하는 역할만 합니다.
> 계산 계층에는 Qt 의존성이 없어서, 같은 분석을 GUI 없이 `--check` 명령으로도 돌리고 단위 테스트로 검증합니다.

| 파일 | 한 줄 책임 |
|---|---|
| [app.py](seoul-population/app.py) | GUI / `--check` CLI 분기 |
| [dataset.py](seoul-population/hotplace/dataset.py) | CSV 검증·집계·품질·디스크 캐시 |
| [hotplace.py](seoul-population/hotplace/hotplace.py) | `Hotplace` 클래스, 14개 분석, 결과 데이터 클래스 |
| [analytics.py](seoul-population/hotplace/analytics.py) | 진단 지표, 두 지역 비교, 리포트 텍스트 |
| [ui.py](seoul-population/hotplace/ui.py) | `MainWindow`, 4개 페이지, 로딩 스레드, 내보내기 |
| [widgets.py](seoul-population/hotplace/widgets.py) | 재사용 위젯 (탭, 지표 띠, 비교표, 전환 애니메이션) |
| [plotting.py](seoul-population/hotplace/plotting.py) | `PlotCanvas`, 차트 렌더러 7종, 마우스 판독, 확대·이동 |
| [theme.py](seoul-population/hotplace/theme.py) | Qt와 차트가 같이 쓰는 색·글꼴·SVG 아이콘 |

---

## 2. 전체 구조 질문

**Q. 왜 계산과 그리기를 나눴나요?**
> 원래 강의 예제의 `analysisN()`은 함수 안에서 바로 그래프를 띄웠습니다. 저는 `analysisN()`이 그림 대신 `LineSeries`, `Heatmap` 같은 결과 객체를 반환하도록 바꿨습니다. 그래서 같은 결과 객체 하나로 화면 차트, PNG 저장, CSV 내보내기, 단위 테스트를 모두 처리합니다. 각 결과 클래스가 `csv_rows()`를 갖고 있어서 화면 모양을 몰라도 CSV로 바꿀 수 있습니다.

근거: [hotplace.py:1-16](seoul-population/hotplace/hotplace.py#L1) 모듈 독스트링, [hotplace.py:47-192](seoul-population/hotplace/hotplace.py#L47) 결과 클래스들.

**Q. 결과 타입에 따라 어떻게 다른 차트를 그리나요?**
> `draw_result()`가 `isinstance`로 분기합니다. `PairedAnalysis`면 A/B 나란히, `HourlyGap`이면 차이 막대, `AgeShares`면 점 비교, `CityScatter`면 산점도, 나머지 `LineSeries`는 꺾은선입니다. 새 분석을 추가할 때 기존 결과 타입을 재사용하면 렌더러는 손대지 않아도 됩니다.

근거: [plotting.py:1093](seoul-population/hotplace/plotting.py#L1093).

**Q. 차트 탭 14개를 if문 14개로 연결했나요?**
> 아닙니다. 탭 인덱스 `i`가 `analysis{i+1}` 메서드에 대응하도록 맞추고 `getattr`로 호출합니다. 분기는 세 갈래뿐입니다. 메서드 자체가 두 지역을 받는 분석(`PAIR_TABS = {3, 7, 8, 11}`)은 `place_a.analysisN(place_b)`, 서울 전체 산점도(`CITY_TAB = 13`)는 코드표까지 넘기고, 나머지 단일 지역용 분석은 A와 B에 각각 호출해서 `PairedAnalysis`로 묶습니다.

근거: [ui.py:1020-1034](seoul-population/hotplace/ui.py#L1020), 상수는 [ui.py:41-55](seoul-population/hotplace/ui.py#L41).

**Q. 왜 pandas를 안 썼나요?**
> CSV를 `csv.reader`로 한 행씩 읽으면서 바로 행정동별 누적값으로 줄여 담습니다. 원본 30만여 행을 메모리에 들고 있을 필요가 없고, 행 단위로 검증 오류를 "몇 번째 행"까지 알려 줄 수 있습니다. 계산 계층은 표준 라이브러리만 쓰고, numpy는 `plotting.py`에서 히트맵·산점도 그릴 때만 씁니다.

근거: [dataset.py:8-10](seoul-population/hotplace/dataset.py#L8), [dataset.py:291-342](seoul-population/hotplace/dataset.py#L291).

**Q. 캐시가 있다던데, 뭘 캐시하나요?**
> 두 종류입니다. 하나는 디스크 캐시로, CSV 집계 결과 `Population` 객체를 pickle로 저장합니다. 키는 두 파일의 절대경로·크기·수정시각을 SHA-1 한 값이라 파일이 바뀌면 자동으로 무효화됩니다. 다른 하나는 메모리 캐시 `MainWindow._results`로, 현재 A/B 선택에서 이미 계산한 분석 결과를 탭 번호로 보관합니다. 지역을 바꾸면 비웁니다.

근거: [dataset.py:227](seoul-population/hotplace/dataset.py#L227) `_cache_path`, [ui.py:976](seoul-population/hotplace/ui.py#L976) `_on_region_changed`.

---

## 3. 데이터 계층 (`dataset.py`)

**Q. CSV를 어떤 자료구조로 바꾸나요?**
> 네 개입니다. `Dong`은 불변 데이터 클래스로 행정동 한 곳의 코드·구·동 이름, `CodeBook`은 그 목록과 코드→`Dong` 사전, `DongAggregate`는 행정동 한 곳의 집계, `Population`은 전체 집계와 날짜·품질 정보입니다. `DongAggregate`에는 시간대별 누적 `total[24]`, 평일/주말 누적, 시간×성별연령 `age[24][28]`, 그리고 날짜별 원값 `daily[날짜][시간]`이 들어 있습니다.

근거: [dataset.py:53-149](seoul-population/hotplace/dataset.py#L53).

**Q. 누적값 옆에 `counts`를 따로 두는 이유는요?**
> 누락을 0으로 오해하지 않기 위해서입니다. 평균을 낼 때 전체 일수가 아니라 그 시간대에 **실제로 관측된 횟수**로 나눕니다. 기간이 3일인데 09시 관측이 두 번뿐이면 `합 ÷ 2`입니다. 관측이 아예 없으면 0이 아니라 `NaN`을 돌려주고, 차트는 그 구간을 비워 둡니다.

근거: [hotplace.py:218](seoul-population/hotplace/hotplace.py#L218) `_mean`, [dataset.py:321-333](seoul-population/hotplace/dataset.py#L321).

**Q. 잘못된 데이터는 어떻게 처리하나요?**
> 읽는 도중 행 단위로 검증합니다. 열 개수 32개 미만, 날짜가 8자리 숫자가 아님, 시간이 0~23 밖, 인구가 음수·NaN·무한대면 `DataError`에 행 번호를 담아 던집니다. 같은 날짜·시간·행정동이 중복되면 첫 행만 쓰고 `duplicate_rows`를 올립니다. 이 숫자는 데이터 페이지의 '제외한 중복 행'에 표시됩니다.

근거: [dataset.py:294-324](seoul-population/hotplace/dataset.py#L294).

**Q. 관측 완전성은 어떻게 계산하나요?**
> `실제 관측 수 ÷ (파일에 있는 행정동 수 × 첫날~마지막 날 달력 일수 × 24)`입니다. 달력 일수는 파일에 빠진 날까지 포함합니다. 다만 파일에 한 번도 안 나온 행정동은 분모에 없어서 이 비율로는 드러나지 않습니다. 그래서 화면에도 그 한계를 문구로 적어 뒀습니다.

근거: [dataset.py:172-187](seoul-population/hotplace/dataset.py#L172), 안내 문구 [ui.py:666](seoul-population/hotplace/ui.py#L666).

**Q. 평일/주말은 어떻게 나누나요? 공휴일은요?**
> `date.weekday() >= 5`로만 나눕니다. 평일에 낀 공휴일은 주말로 재분류하지 않습니다. 비교 리포트의 '평소와 다른 날' 설명에도 "공휴일은 따로 보정하지 않습니다"라고 명시했습니다.

근거: [dataset.py:206](seoul-population/hotplace/dataset.py#L206), [analytics.py:96](seoul-population/hotplace/analytics.py#L96).

---

## 4. 페이지별 질문

### 4.0 공통 뼈대

**Q. 화면 전체는 어떻게 짜여 있나요?**
> `MainWindow`는 `QWidget` 하나이고, 가로 레이아웃으로 왼쪽 212px 내비게이션 레일과 오른쪽 작업 영역을 둡니다. 작업 영역은 위에서부터 상단 바, 페이지 스택, 상태 표시줄입니다. 페이지 스택은 `AnimatedStack`이고 인덱스는 0 지역 비교, 1 지역 찾기, 2 데이터, 3 비교 리포트입니다. 메뉴에 보이는 순서는 비교·리포트·찾기가 위, 한 번만 쓰는 데이터가 아래라서 내부 인덱스와 다릅니다.

근거: [ui.py:235-263](seoul-population/hotplace/ui.py#L235), 메뉴 배치 [ui.py:287-297](seoul-population/hotplace/ui.py#L287).

**Q. 페이지를 바꾸면 무슨 일이 일어나나요?**
> `_show_page(index)` 한 곳에서 처리합니다. 스택 인덱스를 바꾸고, 상단 바의 제목·설명을 `PAGE_TITLES`/`PAGE_NOTES`에서 갈아 끼우고, 내비게이션 항목의 선택 상태를 갱신합니다.

근거: [ui.py:338](seoul-population/hotplace/ui.py#L338).

### 4.1 데이터 페이지

**Q. 큰 CSV를 읽는 동안 화면이 안 멈추는 이유는요?**
> `LoadWorker`라는 `QObject`를 `QThread`로 `moveToThread` 해서 실행합니다. 워커는 위젯을 직접 건드리지 않고 `progress`, `loaded`, `failed` 세 시그널만 내보냅니다. 스레드가 다른 시그널은 Qt가 메인 스레드 이벤트 큐로 넘겨 주기 때문에, 슬롯인 `_on_progress`, `_on_loaded`, `_on_failed`는 메인 스레드에서 안전하게 위젯을 갱신합니다.

근거: [ui.py:86-112](seoul-population/hotplace/ui.py#L86) `LoadWorker`, [ui.py:854-862](seoul-population/hotplace/ui.py#L854) 스레드 연결.

**Q. `load_population`은 Qt를 모르는데 진행률은 어떻게 전달하나요?**
> 콜백 주입입니다. `load_population(progress=fn, cancelled=fn)` 형태로 일반 함수를 받습니다. 워커가 `progress`에는 시그널 emit 람다를, `cancelled`에는 `QThread.currentThread().isInterruptionRequested()`를 넣어 줍니다. 그래서 같은 로더를 CLI에서는 콜백 없이 그대로 씁니다. 진행률은 2만 행마다 보고하고, 전체 행 수는 앞 500행의 평균 길이로 파일 크기를 나눠 추정합니다.

근거: [ui.py:101-106](seoul-population/hotplace/ui.py#L101), [dataset.py:211](seoul-population/hotplace/dataset.py#L211), [dataset.py:340](seoul-population/hotplace/dataset.py#L340).

**Q. 로딩 중에 창을 닫으면요?**
> `closeEvent`에서 스레드가 돌고 있으면 `requestInterruption()`을 걸고 닫기 이벤트를 `ignore()`합니다. 로더의 행 반복문이 취소 콜백을 보고 `DataError`를 던지면 `_on_failed`가 호출되고, 거기서 `_closing` 플래그를 보고 스레드를 정리한 뒤 다시 `close()`합니다. 스레드가 살아 있는 채로 객체가 파괴되는 걸 막는 구조입니다.

근거: [ui.py:1126](seoul-population/hotplace/ui.py#L1126), [ui.py:884-892](seoul-population/hotplace/ui.py#L884).

**Q. 다시 불러오기가 실패하면 기존 데이터는요?**
> 유지됩니다. `self.population`은 `_on_loaded`에서만 교체하기 때문에, 실패 시에는 오류만 표시하고 배지도 기존 행정동 수로 되돌립니다. 테스트에도 이 경우가 들어 있습니다.

근거: [ui.py:886](seoul-population/hotplace/ui.py#L886), [ui.py:901](seoul-population/hotplace/ui.py#L901).

**Q. 데이터 페이지 아래 네 칸은 뭔가요?**
> 품질 패널입니다. `population.quality(codebook)` 결과로 행정동 수(코드표와 안 맞는 코드 수), 기간(평일·주말 일수), 관측 완전성, 제외한 중복 행을 채웁니다. 각 칸은 `stat_cell()` 헬퍼가 만드는 '작은 제목·큰 값·보조 설명' 묶음이고, 리포트 페이지 상단에서도 같은 헬퍼를 재사용합니다.

근거: [ui.py:926-938](seoul-population/hotplace/ui.py#L926), [widgets.py:368](seoul-population/hotplace/widgets.py#L368).

**Q. 파일 경로가 처음부터 채워져 있던데요?**
> `_prefill_paths()`가 `default_data_dir()`로 기본 폴더를 찾습니다. 순서는 `HOTPLACE_DATA_DIR` 환경변수, 저장소 루트의 `data/`, 형제 저장소의 midterm 데이터 폴더입니다. 저장소 루트는 위로 올라가며 `pyproject.toml`이 있는 폴더로 정해서, 앱 폴더를 옮겨도 동작합니다. 경로만 채우고 자동으로 로딩하지는 않습니다.

근거: [ui.py:810](seoul-population/hotplace/ui.py#L810), [dataset.py:376](seoul-population/hotplace/dataset.py#L376).

### 4.2 지역 비교 페이지 (메인)

**Q. 이 페이지 구성을 설명해 주세요.**
> 이 페이지 자체가 또 하나의 `AnimatedStack`입니다. 0번은 "먼저 데이터를 불러오세요" 환영 화면, 1번이 대시보드이고 `_on_loaded`에서 1번으로 넘깁니다. 대시보드는 위에서부터 지역 선택 줄(`RegionSelector` A · 바꾸기 버튼 · `RegionSelector` B · 찾기), 지표 띠 `ComparisonMetrics`, 차트 패널 `AnalysisTabs`, 상권 유형 띠 순서이고 전체를 `SmoothScrollArea`로 감쌌습니다.

근거: [ui.py:346-388](seoul-population/hotplace/ui.py#L346).

**Q. 지역을 바꾸면 어디까지 갱신되나요?**
> `RegionSelector.changed` 시그널이 `_on_region_changed`에 연결돼 있고, 거기서 네 가지를 합니다. 결과 캐시 비우기, 지표 띠와 상권 유형 갱신, 현재 차트 다시 그리기, 리포트 페이지 갱신입니다. 보고 있지 않은 13개 차트는 미리 계산하지 않고 탭을 눌렀을 때 계산합니다.

근거: [ui.py:976-980](seoul-population/hotplace/ui.py#L976).

**Q. A/B 바꾸기 버튼은 어떻게 구현했나요?**
> 두 선택기의 시그널을 `blockSignals(True)`로 막고 서로의 `Dong`을 `set_dong`으로 넣은 다음, `finally`에서 시그널을 풀고 `_on_region_changed`를 **한 번만** 호출합니다. 막지 않으면 콤보가 바뀔 때마다 중간 상태로 차트를 두세 번 다시 그립니다.

근거: [ui.py:982-994](seoul-population/hotplace/ui.py#L982).

**Q. 맨 아래 '상권 유형(추정)'은 머신러닝인가요?**
> 아닙니다. 규칙 기반입니다. `summary()`가 계산한 주말÷평일 배율, 낮÷밤 배율, 가장 붐비는 시간을 `_character()`가 위에서부터 순서대로 검사합니다. 주말÷평일 1.03 이상이고 정점이 11~21시면 주말 상권형, 0.93 이하·정점 9~18시·낮÷밤 1.3 이상이면 업무지구형, 정점이 밤이거나 낮÷밤 1.05 이하면 주거지형, 나머지는 혼합형입니다. 임계값은 모듈 상수로 빼서 '서울 속 위치' 차트의 기준선과 공유합니다. 화면에도 '추정'이라고 표기했습니다.

근거: [hotplace.py:32-35](seoul-population/hotplace/hotplace.py#L32), [hotplace.py:447-462](seoul-population/hotplace/hotplace.py#L447).

**Q. '상세 통계' 버튼은요?**
> `_show_summary()`가 `QDialog`를 즉석에서 만들어 A/B 두 칸에 `summary_text(place)`를 고정폭 글꼴 `QPlainTextEdit`로 보여 줍니다. 읽기 전용이지만 드래그 복사가 됩니다. 같은 `summary_text`가 지표 띠 숫자의 툴팁에도 쓰입니다.

근거: [ui.py:1052](seoul-population/hotplace/ui.py#L1052), [hotplace.py:465](seoul-population/hotplace/hotplace.py#L465).

### 4.3 지역 찾기 페이지

**Q. 검색은 어떻게 동작하나요?**
> `CodeBook.search()`가 두 단계로 찾습니다. 먼저 동 이름이나 코드가 **정확히 일치**하는 것을 찾고, 없으면 `구 + 동` 문자열에 **부분 일치**하는 것을 돌려줍니다. 그다음 인구 데이터에 실제로 있는 동만 남깁니다. 결과가 하나면 바로, '신사동'처럼 여러 구에 있으면 `DongPickDialog`를 띄워 고르게 합니다. 고른 동은 '넣을 자리' 콤보에 따라 A 또는 B 선택기에 `set_dong`으로 넣고 비교 페이지로 돌아갑니다.

근거: [dataset.py:111](seoul-population/hotplace/dataset.py#L111), [ui.py:948-971](seoul-population/hotplace/ui.py#L948).

**Q. 순위표는 어떻게 만드나요?**
> 기본은 `rank_by_daily_average()`로, 모든 행정동의 시간대 평균의 평균을 구해 정렬한 상위 20곳입니다. 정렬 기준을 최대 시간대 인구·주말÷평일·낮÷밤으로 바꾸면 전체 행정동에 `Hotplace.summary()`를 돌려 해당 키로 다시 정렬합니다. 이미 집계된 24개 값에서 계산하는 거라 CSV를 다시 읽지 않습니다.

근거: [ui.py:552-577](seoul-population/hotplace/ui.py#L552), [hotplace.py:501](seoul-population/hotplace/hotplace.py#L501).

**Q. 표에서 행을 고르면 어떤 동인지 어떻게 아나요?**
> 표시된 텍스트를 다시 파싱하지 않습니다. 셀을 만들 때 `item.setData(Qt.UserRole, dong)`으로 `Dong` 객체 자체를 넣어 두고, 선택 시 `item.data(Qt.UserRole)`로 꺼냅니다. `RegionSelector`의 콤보도 같은 방식으로 `userData`에 `Dong`을 넣습니다. 동명이 겹쳐도 안전합니다.

근거: [ui.py:569](seoul-population/hotplace/ui.py#L569), [ui.py:583](seoul-population/hotplace/ui.py#L583), [ui.py:198](seoul-population/hotplace/ui.py#L198).

### 4.4 비교 리포트 페이지

**Q. 상단 세 칸은 어떻게 계산하나요?**
> `compare_places(left, right)`입니다. 두 지역 모두 값이 있는 시간대만 `common`에 모으고, 거기서 Pearson 상관계수를 직접 계산합니다. 공통 시간이 3개 미만이거나 분산이 0이면 `NaN`입니다. '차이가 가장 큰 시간'은 절대 차이가 최대인 시간, 유사도 문구는 `similarity_label()`이 0.9/0.7/0.4 구간으로 나눕니다.

근거: [analytics.py:65-88](seoul-population/hotplace/analytics.py#L65), [ui.py:718-747](seoul-population/hotplace/ui.py#L718).

**Q. 아래 비교표 여섯 항목은요?**
> 항목 정의는 `analytics.ROWS` 튜플 하나에 키·제목·계산 기준으로 모아 뒀고, 화면의 표와 텍스트 리포트가 같이 씁니다. `diagnostics()`가 값을 계산하고 `insight_cards()`가 표시용 문자열로 바꿉니다.
> - 붐비는 3시간: 시작 시각 24개를 돌며 `(h+step) % 24`로 자정을 넘는 구간까지 3시간 평균의 최댓값.
> - 시간대별 변동: 모집단 표준편차 ÷ 평균 × 100, 즉 변동계수.
> - 20~39세 비중: 연령 배열 `[3:7]` 합 ÷ 전체. 보조로 65세 이상 `[12:]`.
> - 평소와 다른 날: 아래 질문 참고.
> - 서울 내 순위, 관측 완전성.

근거: [analytics.py:24-62](seoul-population/hotplace/analytics.py#L24), [analytics.py:92-99](seoul-population/hotplace/analytics.py#L92).

**Q. '평소와 다른 날'은 어떻게 찾나요? 왜 평균·표준편차가 아닌가요?**
> 24시간이 모두 관측된 날의 일평균을 평일·주말 그룹으로 나누고, 그룹별 중앙값과 MAD로 수정 z 점수 `0.6745 × (값 − 중앙값) ÷ MAD`를 구해 절댓값이 3.5를 넘으면 표시합니다. 평균과 표준편차는 이상값 자체에 끌려가기 때문에 이상값을 찾는 기준으로는 중앙값 기반이 더 견고합니다. 그룹에 완전한 날이 7일 미만이거나 MAD가 0이면 판단을 보류합니다.

근거: [analytics.py:42-52](seoul-population/hotplace/analytics.py#L42).

**Q. '차트에서 보기' 링크는 어떻게 다른 페이지의 탭을 여나요?**
> `ComparisonTable`은 `MainWindow`를 모릅니다. 링크는 `href`에 탭 번호를 넣은 `QLabel`이고, 클릭되면 `chartRequested(int)` 시그널만 냅니다. `MainWindow._open_analysis`가 그걸 받아 탭을 바꾸고, 0번 페이지로 가고, `ensureWidgetVisible`로 차트 패널까지 스크롤합니다. 어느 항목이 어느 탭인지는 `ROW_CHARTS` 사전에 있습니다.

근거: [widgets.py:430-435](seoul-population/hotplace/widgets.py#L430), [ui.py:713](seoul-population/hotplace/ui.py#L713), [ui.py:71](seoul-population/hotplace/ui.py#L71).

---

## 5. 컴포넌트별 질문

| 컴포넌트 | 위치 | 말할 핵심 |
|---|---|---|
| `RegionSelector` | [ui.py:149](seoul-population/hotplace/ui.py#L149) | 자치구·행정동 콤보 한 쌍. 자치구가 바뀌면 인구 데이터에 **있는 동만** 채움. `_loading` 플래그로 목록을 채우는 동안 `changed`가 새지 않게 막음. 밖으로는 `changed` 시그널과 `current()`, `set_dong()`만 노출. |
| `ComparisonMetrics` | [widgets.py:201](seoul-population/hotplace/widgets.py#L201) | 지역별 카드가 아니라 **지표 한 칸 안에 A·B를 나란히**. 지표 정의는 `METRICS` 튜플(키·제목·단위·툴팁)에서 루프로 생성. `MetricLabels.update_place()`가 `summary()` 결과를 채움. |
| `AnalysisTabs` | [widgets.py:285](seoul-population/hotplace/widgets.py#L285) | 2단 탭. 위 `SegmentedWidget`(4그룹), 아래 그룹별 `Pivot`. `_group_of`(차트→그룹)와 `_last`(그룹별 마지막 차트)로 그룹을 오가도 보던 차트로 복귀. 밖으로는 `currentChanged(int)` 하나. |
| `AnalysisTab` | [widgets.py:244](seoul-population/hotplace/widgets.py#L244) | 차트 한 장: `PlotCanvas` + 안내 문구 + '원래 크기' 버튼. 버튼은 `canvas.zoomChanged` 시그널에 `setVisible`을 직접 연결. |
| `AnimatedStack` | [widgets.py:57](seoul-population/hotplace/widgets.py#L57) | 아래 질문 참고. |
| `ComparisonTable` | [widgets.py:380](seoul-population/hotplace/widgets.py#L380) | `QGridLayout` 3열(항목·A·B). `set_rows()`가 `clear_layout()`으로 비우고 다시 채움. 헤더와 본문 그리드에 같은 `columnStretch(5,6,6)`를 줘서 열을 맞춤. |
| `NavigationItem` | [widgets.py:129](seoul-population/hotplace/widgets.py#L129) | Fluent `NavigationPushButton` 상속. Enter/Space 활성화, 접근성 이름, **키보드(Tab)로 들어온 포커스일 때만** 테두리를 직접 `paintEvent`로 그림. |
| `DongPickDialog` | [ui.py:116](seoul-population/hotplace/ui.py#L116) | 동명이 여러 곳일 때 고르는 `QDialog`. 더블클릭 = 확인. |
| `LoadWorker` | [ui.py:86](seoul-population/hotplace/ui.py#L86) | 4.1 참고. |
| `PlotCanvas` / `HoverCallout` | [plotting.py:233](seoul-population/hotplace/plotting.py#L233) | 7장 참고. |

**Q. 페이지 전환 애니메이션은 어떻게 만들었나요?**
> `AnimatedStack.setCurrentIndex()`가 먼저 `self.grab()`으로 **이전 화면을 픽스맵으로 캡처**하고, 실제 페이지는 즉시 바꿉니다. 그 위에 `TransitionOverlay`가 캡처본을 올려놓고 `QVariantAnimation`으로 0→1 진행하면서 `paintEvent`에서 투명도를 낮추고 24px 옆으로 밉니다. 오버레이는 `WA_TransparentForMouseEvents`라서 전환 중에도 새 페이지를 바로 조작할 수 있습니다. 상태는 동기적으로 바뀌고 애니메이션은 장식일 뿐이라, 연속 클릭이나 창 크기 변경 시에는 그냥 중단하면 됩니다. 페이지 240ms, 차트 탭 220ms, `OutCubic`입니다.

근거: [widgets.py:27-92](seoul-population/hotplace/widgets.py#L27).

**Q. 애니메이션 끄기는요?**
> `motion_enabled()`가 환경변수 `HOTPLACE_REDUCED_MOTION=1`과 앱 속성 `reducedMotion`을 봅니다. 꺼져 있으면 캡처를 아예 안 하니 오버레이도 안 뜹니다. 토글 시에는 진행 중인 전환을 멈추고 Fluent 탭의 슬라이드 인디케이터도 최종 위치로 바로 옮깁니다. 빠르게 연속으로 페이지를 바꾼 뒤 모션을 껐다 켜도 상태가 안정되는지는 `test_rapid_navigation_and_reduced_motion_settle` 테스트로 확인합니다.

근거: [widgets.py:22](seoul-population/hotplace/widgets.py#L22), [ui.py:772](seoul-population/hotplace/ui.py#L772), [widgets.py:353](seoul-population/hotplace/widgets.py#L353).

---

## 6. 그래프별 질문 (14개)

탭 구조: `TAB_GROUPS` — **하루 흐름**(시간대·평일주말·겹쳐 보기·시간대별 차이·흐름 비교) / **요일·날짜**(요일별·요일×시간·일별 추이) / **성별·연령**(성별·여성 비율·연령·연령 비중·연령×시간) / **서울 전체**(서울 속 위치).

공통으로 먼저 말할 것:

> 단일 지역용 분석은 A와 B에 각각 돌려 `PairedAnalysis`로 묶고, `draw_paired_analysis()`가 `subplots(1, 2, sharex=True, sharey=True)`로 **좌우에 같은 축**으로 그립니다. 세로축 범위는 두 지역 값을 합쳐서 한 번만 정합니다. 그래서 눈으로 본 높이 차이가 실제 인구 차이입니다. 한 지역 안의 선은 모두 그 지역 색(A 초록, B 보라)을 쓰고, 두 번째 계열은 점선과 옅은 톤으로 구분합니다.

근거: [plotting.py:812-848](seoul-population/hotplace/plotting.py#L812).

### ① 시간대 — `analysis1` → `LineSeries` (계열 1개)
- **계산**: `mean_hourly()` = 시간대별 `total[h] ÷ counts[h]`.
- **그리기**: `draw_line_series`. 계열이 하나고 기준선이 없으면 `_area()`로 선 아래를 위→아래 옅어지는 그라데이션으로 채움. 정점 한 곳만 점+라벨.
- **Q. 그라데이션은 어떻게?** → `fill_between`으로 외곽 경로만 얻고 지운 뒤, 알파가 0.2→0.02로 변하는 64단 이미지를 `imshow`로 깔고 그 경로를 `set_clip_path`로 씌웁니다. [plotting.py:635](seoul-population/hotplace/plotting.py#L635)

### ② 평일·주말 — `analysis2` → `LineSeries` (2계열)
- **계산**: `weekday[h] ÷ weekday_counts[h]`, `weekend[h] ÷ weekend_counts[h]`. 집계 단계에서 이미 평일/주말로 나눠 누적.
- **그리기**: 평일 실선, 주말 점선+`_tint(색, 0.3)`. 계열이 2개 이상일 때만 차트 아래 범례.
- **Q. 왜 색을 안 바꾸고 점선으로?** → 색은 지역(A/B)을 뜻하는 데만 씁니다. 같은 패널 안에서 색이 바뀌면 지역으로 오해합니다.

### ③ 성별 — `analysis3` → `LineSeries` (남·여)
- **계산**: `mean_by_gender()`. 시간마다 `age[h][:14]` 합이 남자, `age[h][14:]` 합이 여자. 같은 `counts`로 나눔.
- **Q. 총생활인구 열에서 안 구하나요?** → 성별은 28개 성별·연령 열에만 있습니다. 총인구 열과 28개 합이 같다고 가정하지 않고, 성별·연령 비율은 항상 성별·연령 집계를 분모로 씁니다.

### ④ 겹쳐 보기 — `analysis4(other)` → `LineSeries` (A·B 2계열, 한 축)
- **계산**: 두 지역의 `mean_hourly()`를 한 결과에 담음. `PAIR_TABS`라서 `PairedAnalysis`로 다시 묶지 않음.
- **그리기**: 같은 `draw_line_series`지만 `single_color`가 없어서 계열 0은 A색, 1은 B색. 축이 하나라 교차 지점이 바로 보임.
- **Q. ①과 뭐가 다른가요?** → ①은 나란히(모양 비교), ④는 겹쳐서(어느 시간에 역전되는지). 계산은 같고 결과 객체의 구성만 다릅니다.

### ⑤ 연령 — `analysis5` → `AgePyramid`
- **계산**: `mean_by_age()`. 24시간의 성별·연령 누적을 합쳐 **전체 실제 관측 수** `sum(counts)`로 나눔.
- **그리기**: `draw_age_pyramid`. 남자를 **그릴 때만** 음수 폭으로 눕혀 좌우 대칭. 원본 값과 CSV는 양수. 눈금 포매터가 `abs(v)`로 표시. 가운데 흰 2px 선으로 두 막대 분리. A/B 비교에선 두 지역 최댓값 기준으로 `xlim`을 ±대칭으로 통일.
- **Q. 막대 끝이 둥근데요?** → `RoundedBar`가 `Rectangle`을 상속해 `get_path()`를 재정의합니다. 데이터 좌표를 화면 픽셀로 변환한 뒤 값 쪽 두 모서리만 2차 베지어(`CURVE3`)로 그립니다. 반경이 픽셀 기준이라 확대해도 모양이 유지됩니다. [plotting.py:139-173](seoul-population/hotplace/plotting.py#L139)
- **Q. 이 차트는 마우스 판독이 없네요?** → 맞습니다. 피라미드는 hover·확대를 등록하지 않았고, 대신 안내 문구로 읽는 법을 알려 줍니다. `AnalysisTab.set_hint()`가 `canvas.navigable`을 보고 확대 안내를 붙일지 정합니다.

### ⑥ 일별 추이 — `analysis6` → `LineSeries` (일평균 + 7일 이동평균, 날짜 축)
- **계산**: `calendar_dates`(빠진 날 포함)를 돌며, 그 날 **24시간이 모두 있을 때만** `합 ÷ 24`, 아니면 `NaN`. 이동평균은 직전 7일이 **전부 유한할 때만** 계산.
- **그리기**: `xlabels`가 있으면 x축 이름을 `MM/DD`로. 눈금 간격 후보 `[1, 2, 7, 10]`이라 주 단위로 떨어짐.
- **Q. 빠진 시간이 있는 날을 왜 버리나요?** → 새벽만 빠진 날은 평균이 높게, 낮만 빠진 날은 낮게 나옵니다. 부분 평균을 섞으면 추세가 아니라 누락 패턴을 그리게 됩니다.

### ⑦ 요일×시간 — `analysis7` → `Heatmap` (7×24)
- **계산**: `daily`를 돌며 `buckets[요일][시간]`에 값을 모으고 칸마다 `finite_mean`.
- **그리기**: `draw_heatmaps`. 히트맵만 **위아래** `subplots(2, 1)` — 24칸이 가로로 길어서. 두 지역 전체의 최댓값을 `vmax`로 공유하고 컬러바도 하나. `np.ma.masked_invalid` + `cmap.with_extremes(bad=muted)`로 관측 없는 칸은 회색. 칸 사이 틈은 minor 눈금 위치에 배경색 2px 그리드를 그려서 만듦.
- **Q. 색 범위를 왜 공유하나요?** → 따로 정규화하면 두 지역 모두 "가장 진한 칸"이 생겨서 규모 차이가 사라집니다. 여기서는 같은 색 = 같은 인구입니다.
- **Q. hover는요?** → 전용 `lookup`을 등록합니다. `round(xdata), round(ydata)`로 칸을 찾고, **두 패널 모두** 같은 칸에 테두리를 옮겨 A·B 값을 함께 보여 줍니다. [plotting.py:892-905](seoul-population/hotplace/plotting.py#L892)

### ⑧ 흐름 비교 — `analysis8(other)` → `LineSeries` (기준선 100)
- **계산**: 지역마다 `시간대 평균 ÷ 그 지역 하루 평균 × 100`. `reference=100`, `unit=""`.
- **의미**: 인구 규모를 지우고 **하루 리듬의 모양**만 비교. 리포트의 상관계수와 짝.
- **그리기**: 한 축에 A·B 두 선 + 100 점선.

### ⑨ 시간대별 차이 — `analysis9(other)` → `HourlyGap`
- **계산**: `a`, `b`만 저장하고 `gap`은 `@property`로 `a − b`.
- **그리기**: `draw_gap`. 시간마다 `RoundedBar`, 양수면 A색·음수면 B색. 절대 차이가 가장 큰 시간에 "18시 A가 12,345명 더 많음" 라벨. 한쪽이 계속 많아도 반대편을 최대값의 30%만큼 남겨 0선이 보이게 함.
- **Q. 결과 타입이 다른데 hover 코드는 같이 쓰나요?** → 네. `HourlyGap`에 `labels`, `values`, `unit` 속성을 `LineSeries`와 같은 모양으로 열어 둬서(덕 타이핑) `_series_readout`이 그대로 읽습니다. 막대 차트라서 세로선 대신 `band=True`로 그 시간 칸 전체를 옅게 칠합니다. [hotplace.py:126-133](seoul-population/hotplace/hotplace.py#L126)

### ⑩ 요일별 — `analysis10` → `LineSeries` (요일 축)
- **계산**: `analysis7().values`의 각 요일 행을 `finite_mean`. 즉 요일×시간 평균을 다시 시간 방향으로 평균 → 시간대마다 같은 비중. 노트에 요일별 관측 일수를 표기.
- **그리기**: `categories`가 있으면 점 마커를 찍음(7개 이산 값이라).
- **Q. 원본 행을 요일별로 그냥 평균하면 안 되나요?** → 특정 시간대가 많이 빠진 요일이 있으면 그 요일 평균이 왜곡됩니다. ⑦을 재사용하면 두 차트의 숫자도 항상 일치합니다.

### ⑪ 여성 비율 — `analysis11` → `LineSeries` (기준선 50%)
- **계산**: `여 ÷ (남 + 여) × 100`, 시간대별.
- **그리기**: `_value_axis`가 `reference`가 있고 단위가 `%`면 **기준선을 가운데 두고** `max(5, 최대편차×1.4)`만큼만 위아래를 잡음. 0~100으로 그리면 48~53% 변화가 직선으로 보이기 때문. [plotting.py:618-632](seoul-population/hotplace/plotting.py#L618)

### ⑫ 연령 비중 — `analysis12(other)` → `AgeShares`
- **계산**: `age_shares()` = 남녀 합산 연령대 평균 ÷ 전체 합 × 100.
- **그리기**: `draw_age_shares`. 덤벨 차트 — 연령대 행마다 A점·B점과 그 사이 연결선. 차이가 가장 큰 연령대에 "A가 3.2%p 높음". hover는 행 단위 `lookup`, 차이를 `%p`로 표시.
- **Q. ⑤ 피라미드와 차이는?** → ⑤는 절대 인구(규모 포함), ⑫는 구성비(규모 제거). 인구가 10배 차이 나는 두 동도 구성은 비교할 수 있습니다.

### ⑬ 연령×시간 — `analysis13` → `Heatmap` (14×24, `percent=True`)
- **계산**: 시간 열마다 그 시간 전체를 100%로 보고 연령대 비중. 즉 **열 합이 100**. 나이 많은 구간이 위로 가게 `[::-1]`.
- **그리기**: ⑦과 같은 `draw_heatmaps`. `percent` 플래그로 컬러바·말풍선 단위만 `%`로 바뀜. 행이 14개라 패널 높이를 760으로(`CHART_HEIGHTS`).
- **Q. 렌더러를 새로 안 만들었네요?** → `Heatmap` 클래스에 `rows`, `row_label`, `value_label`, `percent` 필드를 둬서 ⑦과 ⑬이 같은 타입·같은 렌더러를 씁니다.

### ⑭ 서울 속 위치 — `analysis14(other, codebook)` → `CityScatter`
- **계산**: `character_points()`가 코드표와 매칭되는 **모든 행정동**의 `summary()`를 구해 낮÷밤, 주말÷평일 배율을 수집. 선택 지역은 `marks`에 `"A"`, `"B"`, 같은 곳이면 `"A·B"`.
- **그리기**: `draw_city_scatter`. 나머지 동은 회색 반투명 점, A/B는 큰 색 점 + 이름. x축(낮÷밤)은 오른쪽으로 길게 치우쳐서 **로그 눈금**. 점선은 상권 유형 임계값 상수(1.05, 1.3, 0.93, 1.03)를 그대로 import해서 그림.
- **Q. 점 hover는 어떻게 찾나요?** → 모든 점을 `ax.transData.transform`으로 **화면 픽셀 좌표**로 바꾸고 커서와의 거리 `np.hypot`이 가장 작은 점을 고릅니다. 12px 이내일 때만 인정. 로그 축이라 데이터 좌표로 거리를 재면 왜곡되기 때문에 픽셀에서 잽니다. [plotting.py:1074-1085](seoul-population/hotplace/plotting.py#L1074)
- **Q. 점선 영역이 상권 유형과 정확히 일치하나요?** → 아닙니다. 유형 판정에는 '가장 붐비는 시간' 조건도 있는데 2차원 평면에는 못 그립니다. 차트 노트에 "가장 붐비는 시간 조건은 생략"이라고 적어 뒀습니다.

---

## 7. 차트 공통 기능

**Q. matplotlib 차트가 어떻게 Qt 창 안에 들어가 있나요?**
> `PlotCanvas`가 `FigureCanvasQTAgg`를 상속합니다. 이 클래스 자체가 `QWidget`이라 레이아웃에 그냥 `addWidget` 합니다. 탭 14개마다 `PlotCanvas`가 하나씩 있고, 그릴 때는 `canvas.clear()` 후 `figure`에 축을 새로 만들고 `draw_idle()`을 부릅니다.

근거: [plotting.py:233-256](seoul-population/hotplace/plotting.py#L233).

**Q. 마우스를 올리면 뜨는 말풍선은 matplotlib인가요?**
> 아닙니다. `HoverCallout`이라는 **Qt 위젯**입니다. 캔버스의 자식 `QFrame`이고 안에 RichText `QLabel`이 있습니다. matplotlib `motion_notify_event`에서 값을 찾아 내용만 채우고 `move()`로 위치를 옮깁니다. matplotlib annotation으로 하면 마우스가 움직일 때마다 Figure 전체를 다시 그려야 하는데, Qt 위젯은 옮기기만 하면 됩니다. 그리고 `_hover_key`로 **같은 시간 칸 안에서는 다시 그리지 않습니다.**

근거: [plotting.py:177-216](seoul-population/hotplace/plotting.py#L177), [plotting.py:353-372](seoul-population/hotplace/plotting.py#L353).

**Q. 좌우 두 패널의 값이 동시에 나오던데요?**
> `set_hover_series()`에 `(축, 결과, 지역 이름, 색)` 목록을 등록해 둡니다. `_series_readout`이 `round(event.xdata)`로 시간 인덱스를 구한 뒤 **등록된 모든 패널**에서 그 시간 값을 읽고, 각 패널의 세로 가이드선과 점 마커를 같은 위치로 옮깁니다. 선 차트가 아닌 히트맵·덤벨·산점도는 `set_hover_lookup()`에 전용 함수를 넘깁니다. 두 방식 모두 결국 `(키, 제목, [(색, 문구)])`를 돌려주는 같은 인터페이스입니다.

근거: [plotting.py:289-351](seoul-population/hotplace/plotting.py#L289).

**Q. 말풍선 좌표 변환에서 주의한 점은요?**
> 두 가지입니다. matplotlib 이벤트 좌표는 **물리 픽셀·원점 좌하단**이고 Qt는 **논리 픽셀·원점 좌상단**입니다. 그래서 `device_pixel_ratio`로 나누고 y를 `높이 − y`로 뒤집습니다. 레티나에서 이걸 빼면 말풍선이 두 배 멀리 뜹니다. 그리고 `point_at()`이 오른쪽·위로 넘치면 반대편으로 뒤집습니다.

근거: [plotting.py:371-372](seoul-population/hotplace/plotting.py#L371), [plotting.py:206-216](seoul-population/hotplace/plotting.py#L206).

**Q. 확대·이동은 matplotlib 툴바를 쓴 건가요?**
> 직접 구현했습니다. `set_navigation()`이 그리기가 끝난 시점의 축 범위를 `_home`에 저장합니다. `zoom()`은 커서 위치를 앵커로 범위를 `factor`배로 줄이고, `_limit()`이 원래 범위 밖으로 못 나가게, 12배(`MAX_ZOOM`)보다 깊게 못 들어가게 막습니다. 입력은 세 가지입니다. `wheelEvent`에서 ⌘/Ctrl이 눌렸을 때만 확대하고 아니면 `event.ignore()`로 **페이지 스크롤에 양보**, `QEvent.NativeGesture`로 트랙패드 핀치, 드래그로 이동·더블클릭으로 초기화.

근거: [plotting.py:384-486](seoul-population/hotplace/plotting.py#L384).

**Q. 로그 축(산점도)에서도 확대가 되나요?**
> 네. 범위를 다룰 때 `_scaled_limits()`가 축의 transform으로 **눈금 공간(log10)** 으로 바꾼 뒤 계산하고, 적용할 때 역변환합니다. 그래서 선형 축과 같은 코드로 로그 축도 확대·이동합니다.

근거: [plotting.py:219-230](seoul-population/hotplace/plotting.py#L219).

**Q. 한쪽 패널을 확대하면 다른 쪽도 같이 움직이던데요?**
> 축을 `sharex=True, sharey=True`로 만들었기 때문에 matplotlib이 범위를 동기화합니다. 제가 따로 맞추는 코드는 없습니다. 비교가 목적이라 의도한 동작입니다.

**Q. '원래 크기' 버튼은 언제 보이나요?**
> `_navigated()`가 현재 범위와 `_home`을 `np.allclose`로 비교해 `zoomChanged(bool)` 시그널을 냅니다. `AnalysisTab`에서 그 시그널을 버튼의 `setVisible`에 바로 연결했습니다.

근거: [plotting.py:433-441](seoul-population/hotplace/plotting.py#L433), [widgets.py:262](seoul-population/hotplace/widgets.py#L262).

**Q. 차트 글자 크기가 앱 UI와 잘 맞던데요?**
> Figure를 `DPI = 72`로 만듭니다. 72dpi에서는 1pt가 1px이라, matplotlib 글자 크기 숫자를 Qt 스타일시트의 px 값과 같은 감각으로 씁니다. PNG 저장은 `EXPORT_DPI = 144`로 2배 해상도입니다. 한글은 `configure_matplotlib()`이 설치된 폰트 중 Apple SD Gothic Neo → Malgun Gothic → Nanum 순으로 고르고 `axes.unicode_minus=False`로 마이너스 깨짐을 막습니다.

근거: [plotting.py:40-43](seoul-population/hotplace/plotting.py#L40), [plotting.py:76-91](seoul-population/hotplace/plotting.py#L76).

**Q. 축 눈금이 '16만'처럼 나오는데요?**
> `_short()`가 1만 이상이면 만 단위로 줄입니다. 축은 대략적인 크기만, 정확한 값은 말풍선에서 읽는다는 역할 분담입니다. 값 축은 `_trailing_values()`로 오른쪽에 둡니다.

근거: [plotting.py:98](seoul-population/hotplace/plotting.py#L98).

---

## 8. 테마 · 내보내기

**Q. 다크 모드는 어떻게 차트까지 같이 바뀌나요?**
> `Theme`는 `frozen` 데이터 클래스이고 `LIGHT`, `DARK` 두 인스턴스가 있습니다. 모듈 전역 `_theme`을 `theme()`로 읽는데, Qt 스타일시트를 만드는 `apply_theme()`와 `plotting.py`의 모든 렌더러가 **같은 객체**를 읽습니다. 토글하면 Fluent 테마·`QPalette`·스타일시트를 다시 적용하고, 아이콘을 새 색으로 다시 만들고, 현재 차트를 다시 그립니다. 첫 실행 때는 시스템 창 배경의 밝기가 128 미만이면 다크로 시작합니다.

근거: [theme.py:12-64](seoul-population/hotplace/theme.py#L12), [theme.py:106](seoul-population/hotplace/theme.py#L106), [ui.py:801](seoul-population/hotplace/ui.py#L801), [ui.py:1142](seoul-population/hotplace/ui.py#L1142).

**Q. 색은 어떤 원칙으로 정했나요?**
> 화면 크롬은 무채색, 색은 **데이터에만** 씁니다. A는 초록, B는 보라로 고정이고 배지·표 머리글·차트 선이 모두 같은 색입니다. 배지 글자는 같은 색상의 진한 톤 `series_ink`를 따로 둬서 대비 4.5:1을 맞췄습니다. 히트맵은 A/B 색과 안 겹치게 호박색 단색 계열입니다.

근거: [theme.py:28-44](seoul-population/hotplace/theme.py#L28).

**Q. 스타일시트에서 위젯을 어떻게 구분하나요?**
> `label(text, role)` 헬퍼가 `setProperty("role", …)`을 걸고, 스타일시트는 `QLabel[role="caption"]` 같은 속성 선택자로 잡습니다. 위젯 서브클래스를 만들지 않고도 타이포그래피 단계를 나눌 수 있습니다.

근거: [widgets.py:95](seoul-population/hotplace/widgets.py#L95), [theme.py:150-168](seoul-population/hotplace/theme.py#L150).

**Q. 아이콘은 이미지 파일인가요?**
> 아닙니다. `_ICONS` 사전에 SVG path 문자열만 있고, `make_icon()`이 현재 테마 색을 `stroke`에 넣어 `QSvgRenderer`로 2배 크기 픽스맵에 그립니다. 외부 아이콘 패키지가 없고, 테마가 바뀌면 색만 바꿔 다시 만듭니다.

근거: [theme.py:90](seoul-population/hotplace/theme.py#L90).

**Q. PNG/CSV 저장은요?**
> PNG는 `canvas.clear_hover()`로 가이드선을 지운 뒤 화면의 Figure를 그대로 `savefig(dpi=144)`합니다. 그래서 확대한 상태면 확대된 범위로 저장됩니다. CSV는 현재 결과 객체의 `csv_rows()`를 `csv.writer`에 넘기고, 엑셀에서 한글이 안 깨지게 `utf-8-sig`로 씁니다. `PairedAnalysis.csv_rows()`는 A와 B의 표를 옆으로 이어 붙이고 헤더에 `A · 지역명 · 계열명`을 넣습니다. 계산 불가 값은 빈 칸입니다.

근거: [ui.py:1085-1120](seoul-population/hotplace/ui.py#L1085), [hotplace.py:187](seoul-population/hotplace/hotplace.py#L187).

---

## 9. 테스트 · 실행 · 패키징

**Q. 테스트는 어떻게 했나요?**
> `unittest` 31개입니다. `test_analytics.py`는 임시 CSV나 합성 집계를 만들어 평균, 중복 제외, 누락 처리, 이동평균, 비율, 이상 일자, 검증 오류, 취소를 확인합니다. `test_comparison.py`는 `QT_QPA_PLATFORM=offscreen`으로 실제 `MainWindow`를 띄워 A/B 내보내기, 공통 축, 선택 유지, 검색·순위, 마우스 판독, 확대 제한·초기화, 테마, 재로딩 실패, 로딩 중 종료를 확인합니다. 계산과 화면이 분리돼 있어서 가능한 구성입니다. 다만 합성 데이터 기준이라, 실제 서울 CSV 전체의 수치를 검증했다는 뜻은 아닙니다.

**Q. `--check`는 뭔가요?**
> GUI 없이 같은 로더와 같은 `Hotplace`로 14개 분석·품질·리포트를 출력하는 CLI 모드입니다. `--out 폴더`를 주면 분석별 PNG도 저장합니다. 이때 캔버스 자리에 hover·확대 메서드가 없는 Figure 껍데기를 넘기는데, 렌더러는 `_interactive()` 헬퍼가 `hasattr`로 확인하고 없으면 건너뜁니다. `--check`는 `nargs="?", const=""`라서 지역명 없이도 쓸 수 있고, 그래서 `is not None`으로 모드를 판단합니다.

근거: [app.py:135-141](seoul-population/app.py#L135), [plotting.py:132](seoul-population/hotplace/plotting.py#L132).

**Q. 배포는요?**
> PyInstaller `Hotplace.spec`으로 macOS arm64 `.app`을 만듭니다. CSV는 번들에 넣지 않습니다. 번들 실행(`sys.frozen`)일 때는 캐시 위치가 프로젝트 `.cache/`가 아니라 `~/Library/Caches/Hotplace/`로 바뀝니다.

근거: [dataset.py:43-45](seoul-population/hotplace/dataset.py#L43).

---

## 10. 까다로운 질문 — 한계를 먼저 인정하고 이유를 말한다

**Q. '일평균 생활인구'가 하루 방문자 수인가요?**
> 아닙니다. 생활인구는 특정 시각에 그 지역에 있던 인구의 추정치이고, 제 '일평균'은 **시간대별 평균의 평균**입니다. 같은 사람이 여러 시간대에 중복으로 잡히므로 방문자 수로 읽으면 안 됩니다. 지표 툴팁과 리포트 하단에 이 문장을 넣어 뒀습니다.

근거: [widgets.py:194](seoul-population/hotplace/widgets.py#L194), [analytics.py:168](seoul-population/hotplace/analytics.py#L168).

**Q. 열을 이름이 아니라 위치로 읽던데, 형식이 바뀌면요?**
> 맞습니다. 0번 날짜, 1번 시간, 2번 코드, 3번 총인구, 4~17 남자, 18~31 여자로 고정입니다. 최소 32열인지는 검사하지만 열 순서가 바뀌면 감지하지 못합니다. 서울 열린데이터광장의 고정 형식을 전제로 했고, 개선한다면 헤더 이름 매핑을 추가하겠습니다.

**Q. pickle 캐시는 보안상 괜찮나요?**
> pickle은 신뢰할 수 없는 파일을 읽으면 위험합니다. 여기서는 앱이 직접 만든 파일을 자기 캐시 폴더에서만 읽고, 읽다 실패하면 지우고 CSV를 다시 읽습니다. 외부에서 받은 캐시를 여는 기능은 없습니다. 더 엄격히 하려면 JSON이나 npz로 바꿀 수 있습니다.

**Q. 리포트 화면의 '일평균 차이'와 저장한 텍스트 리포트의 '평균 인구 차이'가 다를 수 있나요?**
> 네, 기준이 다릅니다. 화면 카드는 지역별 `summary()["daily_avg"]`의 차이이고, 텍스트는 `compare_places()`의 **공통 관측 시간대만**의 평균 차이입니다. 두 지역의 누락 시간이 같으면 일치하지만 다르면 어긋납니다. 하나로 통일하는 게 맞는 개선점입니다.

근거: [ui.py:740](seoul-population/hotplace/ui.py#L740) vs [analytics.py:155](seoul-population/hotplace/analytics.py#L155).

**Q. 구조상 아쉬운 점은요?**
> 세 가지입니다. 첫째, `MainWindow`가 네 페이지의 생성과 이벤트를 모두 들고 있어 1,100줄입니다. 페이지별 클래스로 나누는 게 다음 단계입니다. 둘째, `analytics.py`가 `place._pop`, `place._agg` 같은 비공개 속성에 접근합니다. `Hotplace`에 공개 메서드를 두는 게 낫습니다. 셋째, '서울 속 위치'는 전체 행정동 배율이 A/B와 무관한데도 지역을 바꿀 때마다 다시 계산합니다. 데이터 로딩 시 한 번만 계산해 두면 됩니다.

**Q. 상권 유형 임계값(1.03, 0.93, 1.3, 1.05)의 근거는요?**
> 통계적으로 추정하거나 학습한 값이 아니라 제가 정한 규칙 기반 기준입니다. *(← 값을 어떻게 골랐는지는 본인 경험대로 한 문장 보태기)* 그래서 화면에 '추정'이라고 쓰고, ⑭ 산점도에서 그 기준선을 서울 전체 분포 위에 그대로 보여 줘서 사용자가 기준의 위치를 직접 판단할 수 있게 했습니다.

---

## 11. 모르는 질문이 나왔을 때

> "정확한 구현은 코드를 확인하고 말씀드리겠습니다. 다만 구조상 그 기능은 ○○ 계층의 책임이라 `○○.py`에 있습니다."

어느 계층인지 찾는 기준:

| 질문에 나온 단어 | 열 파일 |
|---|---|
| CSV, 읽기, 누락, 중복, 캐시, 경로 | `dataset.py` |
| 평균, 비율, 분석 N번, 상권 유형, 순위 | `hotplace.py` |
| 상관계수, 변동성, 이상한 날, 리포트 문구 | `analytics.py` |
| 버튼, 페이지, 선택, 로딩, 저장, 스레드 | `ui.py` |
| 탭, 지표 띠, 비교표, 애니메이션 | `widgets.py` |
| 선·막대·히트맵 모양, 말풍선, 확대 | `plotting.py` |
| 색, 글꼴, 다크 모드, 아이콘 | `theme.py` |

## 12. 시연하면서 짚을 코드 5곳

1. [hotplace.py:218](seoul-population/hotplace/hotplace.py#L218) `_mean` — 관측 횟수로 나누고 없으면 NaN.
2. [ui.py:1020](seoul-population/hotplace/ui.py#L1020) `_render_current` — `getattr` + 세 갈래 분기 + 결과 캐시.
3. [plotting.py:1093](seoul-population/hotplace/plotting.py#L1093) `draw_result` — 타입으로 렌더러 선택.
4. [ui.py:854](seoul-population/hotplace/ui.py#L854) `start_load` — 워커·스레드·시그널 연결.
5. [plotting.py:353](seoul-population/hotplace/plotting.py#L353) `_on_motion` — hover 키 비교와 좌표 변환.
