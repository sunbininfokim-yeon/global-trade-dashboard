# Claude 구현 초안 — 선거 지도 3단계

**목적:** 선거 UI를 단일 JS에 넣지 말고, 확보된 GeoJSON과 공개 보드 데이터를 연결한다. 작황 모니터의 구현 코드는 재사용하지 않는다. 화면 흐름만 참고해 선거용으로 새로 만든다.

## 1. 화면 전환은 두 기능으로만 분리

```
홈 선거
  세계 정치 지도 + 날짜순 세계 선거 일정
    └─ 국가 클릭
       국가 전체 지도 + 국가 대시보드
         └─ USA에서 주 클릭
            해당 주의 연방 하원 선거구 지도 + 주 상세 대시보드
```

- 홈에서는 `timeline/`만 보인다.
- 국가를 열면 전 세계 일정은 반드시 숨긴다.
- 국가 지도에서는 해당 국가의 전체 경계를 보여 준다. 지도 옆 행정부·의회·정당 탭은 국가 대시보드로 전환한다.
- USA만 주 클릭을 한 단계 더 허용한다. 주 화면에서 연방 하원 선거구 도형을 지도에 표시한다.
- 화면에 국가 등급·중요도·별점은 표시하지 않는다.

## 2. 데이터 자산과 로더 경계

| 종류 | 경로 | 책임 모듈 | 브라우저 역할 |
|---|---|---|---|
| 게이트·국가 보드·세계 일정 | `public/data/elections_*_v1.json` | `data/core-service.js` | manifest → board/calendar 순서로 1회 읽기 |
| 국가 광역 경계 | `public/data/admin1/{ISO3}.json` | `data/geo-service.js` | 국가 클릭 후 지연 로드 |
| 미국 하원 선거구 | `public/data/congressional_districts/USA/{STATE}.json` | `data/geo-service.js` | USA 주 클릭 후 해당 주만 지연 로드 |
| 읽기 전용 선택 | `data/selectors.js` | selector | 화면별 필요한 행만 반환 |

UI 컴포넌트는 직접 `fetch()`하지 않는다. `core-service`와 `geo-service`만 네트워크를 담당한다. 브라우저는 의원·계파·정당을 새로 계산하거나 두 데이터 파일을 조인하지 않는다.

## 3. GeoJSON 현황

| 대상 | 자산 | 상태 |
|---|---|---|
| USA | `admin1/USA.json` | 51개 주·DC 경계, 준비됨 |
| KOR | `admin1/KOR.json` | 17개 광역 경계, 준비됨 |
| JPN | `admin1/JPN.json` | 47개 도도부현 경계, 준비됨 |
| GBR | `admin1/GBR.json` | 232개 광역 경계, 준비됨 |
| USA House districts | `congressional_districts/USA/{STATE}.json` | Census 119대 의회 도형. `fetch_usa_congressional_districts.py --all`로 증분 생성 |

미국 선거구 생성기는 Census TIGERweb의 공식 2025-01-01 경계를 받고, `elections_board_v1.json`의 해당 주 하원의원·당적을 **빌드 시점**에 속성으로 넣는다. UI는 `feature.properties.member_name`, `party_abbr`, `district`만 쓴다.

## 4. USA 주 상세 우측 대시보드

주 클릭 후에는 다음 순서로 박스를 보여 준다.

1. **주 행정부:** 주지사·당적, 부지사, 법무장관, 주 단위 계파
2. **연방 의회:** 상원의원 2명, 하원의원(선거구 번호·이름·당적)
3. **주 의회:** 주 상원·하원 다수당과 의석 구성
4. **선거 과정:** 해당 주 `primary_2026`가 있을 때만 표시

값이 `불명`이거나 공개 정본이 없으면 그 사실을 그대로 쓴다. 부지사·법무장관·주 단위 계파를 추측해 채우지 않는다.

## 5. 권장 모듈 경로

```
js/elections/
├── index.js                         # 선거 모드 상태·전환만
├── state.js                         # world / country / usa-state 상태
├── data/
│   ├── core-service.js               # manifest, board, calendar
│   ├── geo-service.js                # admin1, USA district geojson
│   └── selectors.js                  # country/state/event 읽기
├── timeline/
│   ├── index.js                      # 날짜순 세로 일정
│   └── group-by-date.js
└── country-explorer/
    ├── world-map.js                  # 세계 지도
    ├── country-map.js                # 국가 전체 지도
    ├── country-shell.js              # 일반 국가 대시보드
    ├── usa-state-dashboard.js        # 우측 3단계 대시보드
    ├── usa-district-map.js           # 주별 선거구 GeoJSON
    └── special/{usa,china,iran}.js   # 국가별 탭 이름만
```

`app.js`에는 DeckGL·pane 연결 adapter만 둔다. 국가별 렌더링, JSON fetch, 정치색 판단을 넣지 않는다.

## 6. 완료 조건

- 선거 메뉴 → 실제 세계 지도 → 추적 국가 클릭이 작동한다.
- USA/KOR/JPN/GBR 클릭 시 실제 `admin1` 경계로 줌 전환한다.
- USA 주 클릭 시 해당 주의 선거구 GeoJSON이 있을 때 실제 구역을 표시한다. 없으면 주 경계와 `공식 선거구 도형 수집 대기`만 보이고 가상 구역은 그리지 않는다.
- USA 주 상세의 3개 대시보드가 board의 사전 결합 필드만 사용한다.
- 세계 일정은 국가 진입 동안 보이지 않는다.
