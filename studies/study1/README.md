# Study 1 — 두 프로젝트 코드 해설

서울 생활인구 CSV를 분석하는 두 데스크톱 앱을 **실제 코드의 자료구조, 함수 호출, 화면 이벤트 흐름**으로 설명한다. 설명 기준은 2026-09-16 작업 트리다.

## 문서

1. [Original ver 코드 해설](original-ver.md): `seoul-population`의 데이터 집계, 14개 분석, 리포트, GUI, 차트 구현.
2. [Kitty ver 코드 해설](kitty-ver.md): `seoul-population-kitty`의 공통 분석 구조와 화면·차트·테마 변경 구현.
3. [Kitty ver 발표 스크립트](kitty-presentation-script.md): 개발을 모르는 발표자를 위한 시연 대본과 “이 기능은 어떻게 구현했어요?” 질문별 답변.

여기서 **Original**은 현재 저장소의 `seoul-population`을 뜻한다. 강의 최초 예제만을 가리키는 이름이 아니다. 현재 두 버전 모두 `analysis1`부터 `analysis14`까지 구현한다.

## 두 버전의 관계

두 폴더는 각각 자신의 `app.py`와 `hotplace` 패키지를 가진다. Kitty가 Original을 런타임에 가져오거나 상속하는 구조는 아니다. 다음 파일은 현재 내용이 동일한 복사본이다.

- `hotplace/hotplace.py`
- `hotplace/analytics.py`
- `tests/test_analytics.py`

`hotplace/dataset.py`는 기본 데이터 폴더를 찾는 `default_data_dir()`이 다르고 Kitty 쪽에 파일 종류 판별 `identify_csv()`가 추가되어 있다. `hotplace/__init__.py`는 설명 문구만 다르다. 집계와 검증 코드는 같다.

따라서 같은 CSV와 같은 행정동을 사용하면 분석 수치는 같고, 결과를 보여주는 방식이 달라진다. 한쪽 분석 파일을 수정해도 다른 폴더에 자동 반영되지는 않는다.

| 구분 | Original ver | Kitty ver |
|---|---|---|
| 프로젝트 | [seoul-population](seoul-population/) | [seoul-population-kitty](seoul-population-kitty/) |
| GUI 라이브러리 | PySide6 (Qt 6) | PyQt5 (Qt 5.15) |
| 화면 전환 | 페이드·슬라이드 애니메이션 | 애니메이션 없이 즉시 전환 |
| 화면 흐름 | 왼쪽 세로 메뉴, 4개 화면 | 메뉴 없음. 데이터 불러오기 → 차트 보기 두 단계 |
| 파일 지정 | ‘데이터’ 화면에서 경로 입력·찾아보기 | 버튼을 누르면 파일 선택 창에서 두 CSV를 함께 선택 |
| 지역 선택·지표 | 위쪽 가로 배치 | 왼쪽 292px 패널에 세로 배치 |
| 분석 선택 | `SegmentedWidget` + `Pivot`, 14개 차트 | `ComboBox` 두 개, 12개 차트(히트맵 2개 비활성화) |
| 일반 A/B 차트·피라미드 | 좌우 `subplots(1, 2)` | 위아래 `subplots(2, 1)` |
| A/B 히트맵 | 위아래, 공통 색 범위 | GUI에서 비활성화(`--check --out`에서만 그림) |
| 값 판독 | 커서 옆 `HoverCallout` | 차트 하단 `QLabel` |
| 확대·이동 | `PlotCanvas`의 직접 구현 | `NavigationToolbar2QT` 기반 도구 모음 |
| 테마 | 밝음·어두움 전환, A 초록/B 보라 | GUI는 밝음 고정, A 빨강/B 파랑 |
| 검색·리포트 | GUI에서 사용 가능 | 삭제(텍스트 리포트는 `--check`로 출력) |
| 빌드 결과 | `Hotplace.app` | `HotplaceKitty.app` + Kitty SVG |

겹쳐 보기·흐름 비교·시간대별 차이·연령 비중·서울 속 위치는 두 지역을 한 결과로 표현하므로 위 표의 일반 A/B 차트 배치와 구분해서 읽는다.

## 코드 읽기 순서

```text
app.py
  → dataset.py       CSV를 어떤 구조로 바꾸는가?
  → hotplace.py      집계에서 어떤 분석 결과를 만드는가?
  → analytics.py     비교 지표와 리포트는 어떻게 계산하는가?
  → ui.py            사용자의 선택이 어떤 함수를 호출하는가?
  → widgets.py       화면 상태와 재사용 위젯은 어떻게 구성하는가?
  → plotting.py      같은 결과를 어떤 그림과 조작 방식으로 보여주는가?
  → theme.py         색·글꼴·아이콘을 어떻게 적용하는가?
```

Original의 실행 의존성은 저장소 루트의 [pyproject.toml](../../pyproject.toml)에, Kitty(PyQt5)의 의존성은 [Kitty 폴더의 pyproject.toml](seoul-population-kitty/pyproject.toml)에 있다. 각 프로젝트의 기존 README는 실행·사용 안내이고, 이 폴더의 두 문서는 코드 설명용이다.

## 문서 작성 시 검증

2026-09-18, Kitty를 PyQt5로 옮기고 애니메이션을 제거한 뒤, 화면을 ‘데이터 불러오기 → 차트 보기’로 줄이고 히트맵을 비활성화했다. Kitty 폴더의 환경에서 테스트 33개가 통과했다. 옮기기 전후의 화면을 같은 크기로 캡처해 비교했을 때 달라진 픽셀은 화면당 0.4% 미만(글자 가장자리)이었다. 아래 표는 옮기기 전의 기록이다.

2026-09-16, 저장소의 `.venv/bin/python`으로 각 프로젝트의 기존 `unittest` 테스트를 별도 프로세스에서 실행했다.

| 대상 | 결과 |
|---|---|
| Original | 31개 통과 |
| Kitty | 30개 통과 |

합성 데이터 분석과 offscreen 화면 테스트 결과다. 실제 서울 CSV 실행과 macOS 번들 빌드는 이번 문서 작성 검증에 포함하지 않았다. 문서의 로컬 링크와 Python 코드 발췌의 문법도 확인했다.
