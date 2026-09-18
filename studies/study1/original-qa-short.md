# Original ver — "이건 어떻게 구현했나요?" 답변 (코드 기준)

경로 기준: `seoul-population/hotplace/`


## 분석 분류별 구현

모든 분석은 `hotplace.py › Hotplace.analysisN()`이 계산해서 결과 객체를 반환하고, `plotting.py › draw_result()`가 그 타입에 맞춰 그립니다. A·B를 따로 계산하는 분석은 `PairedAnalysis`로 묶어 좌우 두 차트(`subplots(1, 2, sharex, sharey)`)로 그립니다.

### 하루 흐름

**시간대 (analysis1)**
A. `mean_hourly()`로 `total[h] / counts[h]`를 24시간 모두 계산해 `LineSeries`로 반환하고, `draw_line_series()`가 꺾은선과 그 아래 영역으로 그립니다.

**평일·주말 (analysis2)**
A. 읽을 때 `_is_weekend()`로 나눠 누적한 `weekday[h]`, `weekend[h]`를 각각 `weekday_counts`, `weekend_counts`로 나눠 선 두 개로 그립니다.

**겹쳐 보기 (analysis4)**
A. `place_a.analysis4(place_b)`가 두 지역의 `mean_hourly()`를 한 `LineSeries`에 넣어서, 한 차트에 A·B 선 두 개를 겹쳐 그립니다.

**시간대별 차이 (analysis9)**
A. 두 지역의 `mean_hourly()`를 `HourlyGap`에 담고 `gap` 속성에서 시간대별 `A − B`를 구합니다. `draw_gap()`이 0 기준선 위는 A 색, 아래는 B 색 막대로 그립니다.

**흐름 비교 (analysis8)**
A. 지역마다 `시간대 값 / 하루 평균 × 100`으로 평균을 100에 맞춰, 인구 규모가 달라도 하루 흐름 모양만 비교합니다. `reference=100`으로 기준 점선을 그립니다.

### 요일·날짜

**요일별 (analysis10)**
A. `analysis7()`의 요일×시간 평균을 요일마다 다시 `finite_mean()`으로 평균 내서 월~일 7개 값으로 만들고, `categories=WEEKDAYS`로 요일 축 꺾은선을 그립니다.

**요일×시간 (analysis7)**
A. `daily[날짜][시간]` 값을 `datetime.strptime(...).weekday()`로 7×24 칸에 모아 칸마다 평균 낸 `Heatmap`을 반환하고, `draw_heatmaps()`가 `imshow()`로 A·B를 위아래에 같은 색 범위(`vmax`)로 그립니다.

**일별 추이 (analysis6)**
A. 날짜별로 24시간이 모두 있는 날만 일평균을 내고, 연속 7일이 모두 유효할 때만 7일 이동평균을 계산합니다. `xlabels=날짜`로 날짜 축 꺾은선 두 개를 그립니다.

### 성별·연령

**성별 (analysis3)**
A. `mean_by_gender()`가 `age[h]`의 앞 14칸(남자)과 뒤 14칸(여자)을 각각 합쳐 시간대 평균을 내고, 남녀 선 두 개로 그립니다.

**여성 비율 (analysis11)**
A. 같은 남녀 값으로 `여자 / (남자 + 여자) × 100`을 시간대마다 구하고, `reference=50`으로 50% 점선을 함께 그립니다.

**연령 (analysis5)**
A. `mean_by_age()`가 24시간 연령대 값을 모두 더해 관측 수로 나누고, `draw_age_pyramid()`가 `barh()`로 남자는 음수(왼쪽), 여자는 양수(오른쪽) 막대를 그려 피라미드를 만듭니다.

**연령 비중 (analysis12)**
A. `age_shares()`가 남녀를 합친 연령대별 값을 전체 합으로 나눠 %로 바꾸고, `draw_age_shares()`가 연령대마다 A·B 점을 찍고 두 점을 선으로 이어 차이를 보여 줍니다.

**연령×시간 (analysis13)**
A. 시간대마다 그 시간 인구를 100%로 보고 연령대 비중을 구한 14×24 `Heatmap`을 만들고, 나이 많은 연령대가 위로 오게 뒤집어서 `draw_heatmaps()`로 그립니다.

### 서울 전체

**서울 속 위치 (analysis14)**
A. `character_points()`가 서울 모든 행정동의 `summary()`에서 낮÷밤, 주말÷평일 배율을 구하고, `draw_city_scatter()`가 전체는 회색 점, A·B는 색 점으로 산점도를 그립니다. 상권 유형 기준 상수를 `axvline()`, `axhline()` 점선으로 표시합니다.

---

## 기능별 구현

**Q. CSV 불러오기는 어떻게 구현했나요?**
A. `dataset.py › load_population()`에서 `csv.reader`로 한 줄씩 읽고, 열 번호 상수(`COL_DATE=0, COL_HOUR=1, COL_CODE=2, COL_TOTAL=3, COL_MALE=4, COL_FEMALE=18`)로 값을 꺼냅니다. 그 값을 행정동 코드를 키로 하는 `dict[int, DongAggregate]`의 `total[24]`, `weekday/weekend[24]`, `age[24][28]`, `counts[24]`에 바로 누적해서, 원본 대신 집계본만 들고 있습니다.

**Q. 평균은 어떻게 계산했나요?**
A. `hotplace.py › Hotplace._mean()`이 누적합을 시간대별 실제 관측 수 `counts[h]`로 나눕니다. `n == 0`이면 `float("nan")`을 넣고, 이후 `finite_mean()`에서 NaN은 빼고 평균을 냅니다.

**Q. 중복 행·잘못된 값은요?**
A. `daily[date]`에 이미 같은 hour가 있으면 `duplicate_rows += 1` 후 `continue`로 건너뜁니다. 날짜 형식, 시간 범위(0~23), 음수·무한대는 검사해서 `DataError(f"{line_no}행: ...")`로 몇 번째 행인지 알려 줍니다.

**Q. 두 번째 실행이 빠른 건요?**
A. `_cache_path()`가 두 파일의 경로·크기·수정시각(`st_mtime_ns`)을 SHA-1로 해시해 캐시 파일 이름을 만들고, 집계 결과 `Population`을 `pickle.dump()`로 저장합니다. 다음 실행에서 같은 이름의 파일이 있으면 `pickle.load()`로 바로 불러옵니다.

**Q. 로딩 중에 화면이 안 멈추는 건요?**
A. `ui.py › start_load()`에서 `LoadWorker(QObject)`를 만들어 `moveToThread(QThread)`로 옮기고, `thread.started`에 `worker.run`을 연결합니다. 워커는 `load_population(progress=콜백)`의 진행률을 `progress = Signal(int, str)`로, 결과를 `loaded = Signal(object, object)`로 보내고, 메인 스레드의 `_on_progress()`, `_on_loaded()`가 받아서 화면을 갱신합니다.

**Q. 로딩 중에 창을 닫으면요?**
A. `closeEvent()`에서 `thread.requestInterruption()`을 호출하고 `event.ignore()`로 닫기를 한 번 보류합니다. 워커는 매 행 `isInterruptionRequested()`를 확인해 `DataError`로 빠져나오고, `_on_failed()`에서 `_closing` 플래그를 보고 창을 닫습니다.

**Q. 지역 드롭다운(자치구 → 행정동)은 어떻게 구현했나요?**
A. `RegionSelector.populate()`가 `codebook.sigungu_list()`로 코드표 CSV의 자치구 목록을 가져와 첫 번째 `ComboBox`에 `addItems()` 합니다. 자치구를 바꾸면 `currentIndexChanged` → `_on_sigungu_changed()`가 `codebook.in_sigungu()`로 그 구의 행정동을 가져오고, `population.has(dong.code)`로 인구 데이터에 있는 동만 `addItem(dong.name, userData=dong)`으로 넣습니다. 행정동을 고르면 `changed` 시그널 → `MainWindow._on_region_changed()` → `_render_current()`로 차트가 다시 그려집니다. 목록을 채우는 동안에는 `_loading` 플래그로 시그널을 막아 중간에 여러 번 다시 그리지 않게 했습니다.

**Q. 분석 탭 14개는 어떻게 분석 함수와 연결했나요?**
A. `tabs.currentChanged` → `_render_current()`에서 탭 번호 `index`를 받아 `getattr(place_a, f"analysis{index + 1}")`로 해당 분석을 부릅니다. 두 지역을 한 번에 계산하는 탭(`PAIR_TABS = {3, 7, 8, 11}`)은 `place_a.analysisN(place_b)`, 나머지는 A·B 각각 실행해서 `PairedAnalysis`로 묶습니다. 결과는 `self._results[index]`에 캐시하고 지역이 바뀌면 `clear()` 합니다.

**Q. 계산 결과를 그래프로 어떻게 그렸나요?**
A. `analysisN()`은 `LineSeries`, `AgePyramid`, `Heatmap` 같은 dataclass만 반환하고, `plotting.py › draw_result()`가 `isinstance`로 타입을 확인해 `draw_line_series`, `draw_age_pyramid`, `draw_heatmaps` 등을 부릅니다. 캔버스는 `FigureCanvasQTAgg`를 상속한 `PlotCanvas`입니다.

**Q. A·B 비교 차트는 어떻게 맞췄나요?**
A. `draw_paired_analysis()`에서 `figure.subplots(1, 2, sharex=True, sharey=True)`로 좌우 축을 공유하고, 히트맵은 `draw_heatmaps()`에서 두 지역 값 중 최댓값을 `vmax`로 같이 써서 색 범위를 맞췄습니다.

**Q. 마우스를 올리면 값이 나오는 건요?**
A. `PlotCanvas`에서 `mpl_connect("motion_notify_event", _on_motion)`으로 마우스 이벤트를 받아, `round(event.xdata)`로 시간대를 구합니다. `_series_readout()`이 그 시간의 A·B 값을 꺼내고, 커서 옆 `HoverCallout(QFrame)`에 표시합니다.

**Q. 확대·이동은요?**
A. `wheelEvent()`에서 Ctrl/⌘+휠, `event()`에서 트랙패드 핀치(`NativeGesture`)를 받아 `zoom()`으로 커서 위치 기준 `set_xlim()`을 바꿉니다. 드래그는 `button_press_event`/`motion_notify_event`로 `_pan()`, 더블클릭은 `reset_view()`입니다. 처음 범위를 `_home`에 저장해 두고 `_limit()`에서 그 밖으로 못 나가게 막았습니다.

**Q. 페이지 전환 애니메이션은요?**
A. `widgets.py › AnimatedStack.setCurrentIndex()`에서 바꾸기 전 화면을 `grab()`으로 캡처하고, 페이지는 즉시 바꾼 뒤 캡처한 그림을 `TransitionOverlay`에 올려 `QVariantAnimation`으로 흐려지며 옆으로 밀려나게 그립니다.

**Q. 다크 테마는요?**
A. `theme.py`에 색 묶음 `LIGHT`, `DARK`를 두고, `_toggle_theme()` → `apply_theme()`이 전역 테마를 바꾼 뒤 Qt 스타일시트·`QPalette`·matplotlib 색을 다시 적용하고 `_render_current()`로 차트를 다시 그립니다.

**Q. 상권 유형은 어떻게 판정했나요?**
A. `Hotplace.summary()`에서 주말÷평일, 낮(9~18시)÷밤(0~6시) 배율, 가장 붐비는 시간을 구하고, `_character()`가 상수 기준(`WEEKEND_BUSY=1.03`, `WEEKDAY_BUSY=0.93`, `OFFICE_DAY_NIGHT=1.3`, `RESIDENTIAL_DAY_NIGHT=1.05`)과 `if`문으로 비교해 주말 상권·업무지구·주거지·혼합형으로 나눕니다.

**Q. '평소와 다른 날'은요?**
A. `analytics.py › diagnostics()`에서 `analysis6()`의 일평균을 평일·주말로 나누고, 각 묶음의 중앙값과 MAD로 수정 z 점수 `0.6745 × (값 − 중앙값) / MAD`를 구해 3.5를 넘는 날을 골랐습니다.

**Q. 두 지역 유사도는요?**
A. `compare_places()`에서 두 지역 24시간 평균값으로 피어슨 상관계수를 직접 계산하고, `similarity_label()`이 0.9 / 0.7 / 0.4 기준으로 "매우 비슷함"~"다름"으로 바꿉니다.

**Q. PNG·CSV 저장은요?**
A. `_save_png()`는 `QFileDialog.getSaveFileName()`으로 경로를 받아 `canvas.figure.savefig(dpi=EXPORT_DPI)`로 저장합니다. `_export_csv()`는 결과 객체의 `csv_rows()`를 `csv.writer().writerows()`로 `utf-8-sig` 인코딩으로 씁니다.

**Q. 디자인은 어떻게 했나요?**
A. `theme.py`에 색 묶음을 `Theme` dataclass(`LIGHT`, `DARK`)로 한 곳에 정의하고, `apply_theme()`이 이 색으로 Qt 쪽(`QPalette`, `app.setStyleSheet()`, qfluentwidgets `setTheme()`/`setThemeColor()`)을 칠합니다. 차트 쪽은 그리는 함수들이 `theme()`에서 같은 색을 읽어 쓰고, `_style_axes()`에서 테두리(spine)를 아래쪽만 남기고 눈금선·글자색을 옅게 정리했습니다. 위젯마다 `setProperty("role", ...)`를 붙이고 스타일시트에서 `QLabel[role="heading"]`처럼 역할별로 글자 크기·색을 지정했고, 아이콘은 SVG 문자열을 `QSvgRenderer`로 그려(`make_icon()`) 테마 색을 그대로 입힙니다.
