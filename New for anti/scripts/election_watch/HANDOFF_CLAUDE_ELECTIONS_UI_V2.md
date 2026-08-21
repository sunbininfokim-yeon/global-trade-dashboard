# HANDOFF → Claude — 선거 UI 데이터 계약 v2

**contract_updated:** 2026-08-20 (국가별 데이터 기준일은 각 JSON의 `as_of`/`source_as_of`를 따른다)
**소유권:** 데이터·파이프라인 = election_watch / UI = Claude
**정본:** `MIGRATION_HANDOFF_2026-08-13.md`
**이 문서의 목적:** UI가 어떤 화면에서 어떤 공개 JSON 필드를 쓰는지 고정한다. 없는 데이터는 추측하거나 더미로 채우지 않는다.

## 0. UI 모듈 경계 (2026-08-20)

선거는 한 개의 거대 JS가 아니라 아래 두 기능으로 분리한다. 화면에 국가 등급·중요도는 표시하지 않는다.

```
js/elections/
├── index.js                         # 앱 시작·전역 상태 조정만
├── data/core-service.js             # manifest → board/calendar fetch
├── data/geo-service.js              # admin1·미국 선거구 GeoJSON fetch
├── data/selectors.js                # JSON 읽기 전용 selector
├── timeline/                        # 기능 1: 홈의 날짜순 세계 선거 일정
└── country-explorer/                # 기능 2: 세계지도 → 국가 상세
    ├── world-map.js
    ├── country-shell.js
    └── special/{usa,china,iran}.js
```

- **홈:** 세계 지도와 `timeline/`의 월별 세로 일정만 함께 보인다. 달력 격자가 아니라 날짜별 카드가 위에서 아래로 나열된다.
- **국가 진입:** `country-explorer/`만 보이고 전 세계 일정은 반드시 숨긴다.
- **국가 지도:** 선택한 국가의 `/public/data/admin1/{ISO3}.json`을 지연 로드해 국가 전체 경계를 표시한다. USA는 주지사 당적으로 주를 색칠하며, 주 클릭은 우측의 주 행정부 → 연방의회 → 주의회 순서 대시보드로 연결한다.
- **연방 하원 선거구:** `fetch_usa_congressional_districts.py --all`은 U.S. Census Bureau 2025 TIGERweb 119th Congressional Districts를 내려받아 board의 의원·당적과 사전 결합한 `/public/data/congressional_districts/USA/{STATE}.json`을 만든다. 자산이 없으면 UI는 가상 구역을 그리지 않고 주 경계 지도와 대기 문구만 표시한다.
- `app.js`는 DeckGL·기존 pane을 넘기는 adapter만 가진다. 국가별 UI·데이터 fetch·정치 판정은 넣지 않는다.
- JSON을 직접 fetch하는 모듈은 `data/core-service.js`와 `data/geo-service.js`뿐이다. 화면 모듈은 이 두 service와 selector를 통해서만 읽는다.
- USA·CHN·IRN만 `special/`에 국가별 탭 이름을 둔다. 나머지는 공통 shell을 사용한다.

## 1. 브라우저가 읽을 파일

클라이언트는 아래 공개 파일만 fetch한다. `scripts/election_watch/config/**`는 브라우저에서 읽지 않는다.

| 용도 | URL | 핵심 필드 |
|---|---|---|
| UI 준비도·라우팅 게이트 | `/public/data/elections_ui_manifest_v1.json` | `claude_handoff_gate`, `global_screens`, `countries[ISO3].screens` |
| 국가·권력·의회 보드 | `/public/data/elections_board_v1.json` | `countries[]` |
| 홈 우측 전 세계 일정 | `/public/data/elections_calendar_master_v1.json` | `world_by_month`, `world_national_highlights` |
| 국가/주 지도 도형 | `/public/data/admin1/{ISO3}.json` | 지리 도형만. 정치 정보 없음 |

초기 로드는 **manifest → board + calendar → 필요한 admin1** 순서다. `manifest.claude_handoff_gate.can_start_ui !== true`면 선거 UI를 열지 않는다. 이후 `const byIso3 = new Map(board.countries.map(c => [c.iso3, c]))`로 보관한다. 각 화면은 manifest의 `ready / partial / disabled`를 그대로 따른다.

클라이언트는 인원 합산, 파일 간 인물 조인, 계파 중복 제거, 없는 사실의 추정·보강을 하지 않는다. 필요한 결합은 빌더가 공개 JSON에 미리 넣는다.

## 2. 화면별 매핑

| UI 화면 | 바로 표시할 데이터 | 상태 |
|---|---|---|
| 홈 세계 지도 | `country.map_spectrum`, `country.head`, `country.name_ko` | 19개국 수장 보유. 색상은 수장 소속 스펙트럼이며 선거 예측이 아님 |
| 홈 우측 일정 | `calendar.world_by_month[YYYY-MM][]` | 108개 보드 일정 행 + 전 세계 주요 국가 일정. 보드에 없는 국가 클릭은 일정만 표시 |
| 국가 진입 셸 | `head`, `ruling_party`, `parties_tracked`, `events`, `governance_polls`, `legislature`, `legislature_live` | 공통 카드 가능 |
| 국가 지도 | `/admin1/{ISO3}.json` + 국가별 `subnational_live` | 정치 속성이 있는 국가만 색칠. 다른 국가는 중립 지도 |
| 정당/계파 탭 | `country.factions` | USA·JPN만 현재 표시. 계파는 출처·신뢰도도 함께 표기 |
| 진행 중 선거 | `country.race_progress` | USA·KOR만. `aggregation.interim_display.user_caution_ko`를 반드시 표시 |

국가 화면이 열린 뒤에는 전 세계 일정 패널을 닫는다. 상단에는 `지도 / 행정부·정부 / 의회 / 정당` 탭만 남긴다. 중국은 `공산당 / 국무원 / 군`으로 바꾼다.

## 3. 미국 — 지금 구현 가능한 범위

`const usa = byIso3.get('USA')`

| 화면 | 필드 경로 | 구현 가능 | 주의 |
|---|---|---|---|
| 국가 헤더 | `usa.head`, `usa.executive_live.core` | 대통령·부통령·백악관/부통령실·NSC 핵심 | NSC 법정 의장은 대통령, 국가안보보좌관은 실무 책임으로 별도 표기 |
| 연방 행정부 | `usa.executive_live` | `core` 5인 + `cabinet` 21개 공개 직위 | `cabinet[].status="acting"`은 직무대행을 그대로 표시 |
| 미국 지도 | `usa.subnational_live.governors[]` | 50주 주지사 정당 색 | 주지사만 색칠 |
| 주 상세 | `usa.ui_ready.state_drilldown.states[]` | 지도 조인키, 주지사·부지사·법무장관, 주 상·하원 의석·의장·제2당 원내지도부, 연방 대표, 해당 주 경선까지 사전 결합 | 일반 주의원 개인 명단은 없음 |
| 주의 연방 대표 | `usa.ui_ready.state_drilldown.states[].federal_delegation` | 주별 House 의원·정당·지역구 및 상원의원 이름 | 상원의원 임기 종료일은 없음 |
| 연방 의회 | `usa.ui_ready.congress` | 상·하원 명단 사전 분리, 정당 의석, 의장·원내지도부 | 하원 반원은 `summary.house_by_party`(표결권 현원) + `house_vacancies`만 사용. 437명 roster에는 6명 대표단이 포함 |
| 하원 계파 | `usa.factions.parties` | 민주·공화 하원 계파 카드와 `display_count` | 공개 명단이 없는 계파는 `불명`. 중복 허용이므로 계파 수를 합산하지 않음 |
| 2026 경선 | `usa.race_progress` | 주별 공천 진척 및 승자 | 전국 득표·선거인단처럼 표현 금지 |

**미국 UI 금지:** 상원 임기·상임위·일반 주의원 개인 명단을 UI에서 추정해 만들지 않는다. 해당 영역은 `데이터 수집 예정` 카드로만 둔다. 연방 행정부는 `config/extracted/tier12_executives.json#countries.USA`의 White House 공개 명부 기반 값만 사용한다. 부지사·법무장관·주 의회 지도부는 `config/extracted/usa_state_officials.json`의 공개 명부 기반 값만 사용한다. 부지사 직위가 없는 AZ/ME/NH/OR/WY는 후계 서열자를 대입하지 않고 `해당 직위 없음`으로 표시한다.

**미국 주 상세 표시 규칙:**

- 주 행정부는 `governor`, `lieutenant_governor`, `attorney_general` 3장으로 제한한다.
- 연방 상원의원은 2인 실명·당적을 바로 보이고, 하원의원은 `federal_delegation.house_members`를 **선거구 순 접기/펴기** 목록으로 보인다.
- `state_legislature.state_senate/state_house`는 정당별 다수·상대 의석과 `leadership.presiding_officer`, `leadership.second_party_floor_leader`만 보인다. 주 상·하원의 일반 의원 이름은 표시하지 않는다.
- Nebraska는 단원제이므로 주 상원은 `해당 없음`으로, 단원제 의회는 주 하원 카드의 공개 지도부로 표현한다.

**미국 하원 집계 규칙:** `house_voting_seats=435`, `house_voting_members=431`, `house_by_party={GOP:218, DEM:212, IND:1}`, `house_vacancies=4`가 반원·정당 의석 표기 정본이다. `house_roster_rows_including_delegates=437`은 의원 검색·주/준주 드릴다운용이며 DC·5개 준주 대표단 6명을 포함한다.

## 4. 일본·한국 — 지금 구현 가능한 범위

| 국가 | 표시 가능 | 아직 없음 |
|---|---|---|
| JPN | 내각총리대신·관방장관, 17개 각료의 직책·정당, 중·참의원 정당별 의석·의장단, 47도도부현 지사, LDP 계파 | 도도부현 의회 상세 |
| KOR | 대통령·국무총리·대통령실장·국가안보실장·정책실장, 공개 명부가 합치하는 17개 국무위원, 국회 정당별 의석·원내지도부, 광역단체장 정당 요약, 전당대회 진행 | 광역단체별 개별 수장/지방의회, 정당 계파 정본 |

JPN은 `jpn.executive_live`, `jpn.legislature_live.chamber_leadership`, `jpn.subnational_live`, `jpn.factions`를 사용한다. 각료의 `party_abbr`는 반드시 표시하므로 향후 연립·타당 출신 각료도 별도 조건문 없이 표현된다. KOR는 `kor.executive_live`, `kor.legislature_live`, `kor.subnational_live`, `kor.party_leadership_live`, `kor.race_progress`를 사용한다. KOR의 `executive_live.source_conflicts_excluded`가 있으면 그 직책을 억지로 채우지 말고 보류 사유를 각주로 표시한다.

### 4-1. 1·2급 행정부 공통 계약

`countries[ISO3].executive_live`는 1·2급 전체에 존재한다. UI는 `core`를 바로 표시하고, `cabinet`이 있는 국가만 접기 목록을 추가한다.

- USA: `full_cabinet_plus_eop_core` — 백악관·부통령실·NSC 핵심 5인과 21개 장관/각료급 직위.
- JPN/KOR: 국가별 정본의 전체 공개 각료 명단.
- GBR/ISR/DEU/FRA/BRA/TUR/IND/TWN/IDN/ZAF/NGA/RUS: `executive_core` — 수반·정부수반/부수반과 외교·재무·국방·내무 등 권력축. 일반 장관 전수 명단을 UI가 추정해 보충하면 안 된다.
- CHN/IRN/SAU: `party_state_executive_core` / `dual_power_executive_core` / `royal_executive_core`. 이들은 `leadership`·`power_structure` 탭과 함께 읽고, 서구식 내각 서열로 바꾸지 않는다.

각 국가의 `sources` 및 `coverage`를 UI의 출처/신선도 각주로 노출할 수 있다. `source_conflicts_excluded`가 있으면 해당 직책은 보류로 표시한다.

## 5. 중국 — 별도 권력 구조

`const chn = byIso3.get('CHN')`

| 탭 | 필드 경로 | 구현 가능 |
|---|---|---|
| 공산당 | `chn.leadership.party_state.general_secretary`, `.politburo_standing_committee`, `.politburo`, `.central_departments` | 총서기, 정치국 상무위·정치국, 조직·선전·정법·통전 등 핵심 부서 |
| 국무원 | `chn.leadership.party_state.state_council` | 총리·부총리 |
| 군 | `chn.leadership.cmc`, `.service_branches`, `.theater_commands`, `chn.leadership.security_organs` | 중앙군사위, 군종, 5대 전구, 공안·국가안전 축 |
| 지도 | `/public/data/admin1/CHN.json` | 도형만. 성별 행정수장 정치 데이터는 아직 없음 |

전인대 탭은 만들지 않는다. `display_rules`와 인물별 `confidence`, `status`를 그대로 사용하고, 숙청·조사·계파 관련 문구는 원문 상태표시를 바꾸거나 단정적으로 재서술하지 않는다.

## 6. 공통 렌더링 규칙

- `null`, `없음`, `불명`은 빈 칸이 아니라 그대로 표시한다.
- `sources`, `confidence`, `as_of`가 있는 카드에는 정보 버튼 또는 각주를 둔다.
- `map_spectrum`은 `conservative=red`, `nationalist_conservative=red/amber`, `progressive=blue`, `centrist=purple/gray`, `catch_all_governing_party=neutral gold/gray`로 처리한다. `authoritarian_*`·`theocratic_authoritarian`은 별도 체제 색 또는 hatch로 처리하며, 중국·러시아·이란에 서구 좌우 색을 강제하지 않는다.
- `calendar`와 `race_progress`는 날짜·진척 정보다. 확률·예측·LLM 생성 후보 명단으로 확장하지 않는다.
- `admin1` JSON은 기후/지리용 경계선일 수 있으므로, 정치 필드가 존재할 때만 정치 색을 덮는다.

### 국가 등급별 최대 깊이

| 등급 | UI 최대 깊이 |
|---|---|
| USA deep | 연방 행정부·상하원·계파 + 50주 주지사·주의회 정당 의석·연방 대표·경선 |
| 1급 JPN/CHN/RUS | 국가별 특수 권력구조 중심. 필요한 광역 수장 요약까지만 선택 |
| 2급 | 국가수반·국가 의회 정당 구성/여야 비율·핵심 일정이 기본. 광역 요약은 선택. 이란·사우디는 권력기관·안보·에너지 축을 추가 |
| 3급 | 국가수반·집권축·핵심 일정. UAE처럼 국가 권력 브리프 중심 |

전 세계 지방의원 명단을 동일 깊이로 만들지 않는다. 특히 한국은 광역단체 정당 요약까지만 기본 범위이며, 광역의원·기초단체장·기초의원 개별 명단은 수집·UI 범위 밖이다. 국가별 실제 허용 깊이는 manifest의 `countries[ISO3].detail_profile`을 따른다.

## 7. 데이터 파이프라인과 변경 경계

```
공개 출처 → raw 캐시/수동 검토 → profiles·extracted 정본
         → build_factions → build_board.py → elections_board_v1.json
캘린더 정본 → build_calendar_master.py → elections_calendar_master_v1.json
보드+캘린더+지도 자산 → build_ui_manifest.py → elections_ui_manifest_v1.json → UI 게이트
```

`capture_sources.py`와 `run_refresh_cycle.py`는 원문과 검토 보고서까지만 만든다. 인명·의석·날짜를 자동으로 정본에 승격하지 않는다. 현재 자동 수집 대상은 IDN/ZAF/NGA/IRN이고, USA/JPN/CHN 월간 수집은 별도 파이프라인 작업이다.

## 8. Claude 작업 범위

1. 위 공개 JSON만 fetch하여 홈 → 국가 → 탭 구조를 만든다. manifest를 항상 먼저 읽는다.
2. 첫 구현은 세계 지도·일정, USA 지도/의회/주 상세, JPN 계파, CHN 3탭으로 제한한다.
3. 이 문서의 `아직 없음` 영역은 빈 데이터가 아니라 비활성 카드로 표시한다.
4. 수정 허용: `app.js`, `style.css`, `index.html` 및 UI 보조 JS. 수정 금지: `scripts/election_watch/**`, `public/data/*.json`.
5. UI PR은 반드시 이 데이터 커밋 이후 별도 브랜치에서 시작한다. 기존 `app.js`를 건드리는 매크로·글로브 PR과 한 PR로 섞지 않는다.

## 9. 데이터 담당 빌드·인수 검증

```bash
cd "New for anti/scripts/election_watch"
python3 run_refresh_cycle.py --build-derived
```

이 명령은 계파 → 보드 → 캘린더 → UI 매니페스트를 순서대로 다시 만든다. 마지막 출력에서 `claude_handoff_gate.can_start_ui=true`와 `errors=[]`여야 인수 가능하다. `partial`은 오류가 아니라 확보된 카드만 표시하라는 계약이며, `disabled` 화면을 클로드가 별도 모델링이나 새 데이터 파일로 채우면 안 된다.
