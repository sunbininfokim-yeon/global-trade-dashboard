# Claude 인수인계: 미국 지도 선거자금 백엔드

사용자 요청: 정치 → 미국 → 선거 토글 → 미국 전체 지도 → 주별 지도에서 지역구별 후보·주지사 외부지출을 표시한다. Codex는 실제 자료와 반복 수집·조회 계약을 준비하고, Claude는 UI 설정과 배포를 맡는다.

## 현재 상태

- PR #260, `codex/us-superpac-pipeline`. UI·활성 `.github/workflows` 변경은 최종 diff에서 제외했다. 이전 패널 프로토타입을 배포하지 말고 아래 계약을 사용한다.
- 연방 2026 후보 등록 4,485명, 정기 독립지출 13,860건. 후보 ID 기준의 후보·지역구 레코드는 4,635개(등록 명부 밖 공시 후보, 복수 선거구 신고 포함)다. 전국 최종 후보 수라고 표시하지 않는다.
- 워싱턴 주지사 C6: 2024 사이클 29행 중 독립지출 배분 11행/후보 3명, 선거 관련 통신 18행 제외. 2026 사이클 조회는 해당 배분 행 없음. 다른 49개 주는 자동 미지원이다. 매사추세츠 공식 API는 실제 조회 HTTP 500으로 미연결.
- 연방 최신 포함 신고일 2026-08-20. 수집일이 신고 최신일을 대신하지 않는다. FEC_API_KEY는 GitHub Secret 등록 완료(사용자 확인), 로컬 값이나 브라우저 키가 필요하지 않다.
- **실제 운영 활성화/배포는 아직 하지 않았다.** 이 문서와 실행 템플릿까지가 인수 단계다.

## 브라우저가 읽을 경로

모든 경로의 기준은 `/public/data/`. 실제 파일명은 반드시 상위 JSON의 참조값으로 읽는다. 아래 경로만 고정이다.

1. `usa_election_finance_index_v1.json`: 사이클 목록, 출처별 마지막 성공 시각/신고일/품질, 금액 의미와 지도 join 계약. 약 5KB.
2. `index.cycles[cycle].national_file`: 선택 사이클 전국 자료. `states[stateId].data_file`, 주별 `totals_by_office`, 주지사 지원 상태. 약 128–137KB.
3. `national.states[stateId].data_file`: 해당 주의 `races`. 각 항목은 `race_id`, `office`, `district`, `totals_by_category`, `data_file`, `map_join`을 가진다.
4. `race.data_file`: 후보별 총액, `election_types[code].allocations`에 단체·금액·원문 링크·월별 내역. 최초 전체 다운로드 금지. 클릭한 주/선거 상세만 가져온다.

기존 국가/지도 코드의 진입점:

- `js/elections/country-explorer/index.js`: 미국 국가/주별 창
- `js/elections/country-explorer/usa-district-map.js`: GeoJsonLayer 클릭·hover 연결
- `js/elections/data/geo-service.js`: 주별 지도 로더

지도 join은 `feature.properties.state_id`와 `String(feature.properties.district).padStart(2,'0')`이다. 예: CA+01 → `USA:CA:house:01`. AK 전역 선거구는 00. 상원은 `USA:CA:senate`, 주지사는 `USA:CA:governor`, 대통령은 `USA:US:president`. 상원 seat class와 동시 선거 구분은 미지원이며 race_id는 지리/직위 그룹이지 확정 투표용지 선거 ID가 아니다.

현재 38개 신고/등록 선거구 코드가 기존 도형에 없어서 `national.unmatched_district_race_ids`로 제공된다. `map_join.existing_geometry_found=false`는 지도에 채색하지 말고 미연결 자료로 표시한다. 기존 도형은 119대 의회 기준이며 **2026 또는 향후 선거 경계와의 일치를 인증하지 않는다**. 새로운 구획으로 바뀌면 지도 소유자가 경계를 갱신해야 한다. 이름으로 후보를 현직 의원과 결합하지 않는다.

## 금액·필터 계약

- 금액은 USD 정수 센트. `support_cents` / `oppose_cents` 별도. 이는 **후보가 받은 후원금이 아니라 후보를 지지/반대하는 외부 독립지출**이다.
- 기본 슈퍼팩 필터는 `category=super_pac`(FEC O). 다른 PAC, 기타 단체, 워싱턴 `state_independent_spender_unclassified`를 합쳐 슈퍼팩이라 부르면 안 된다.
- `null`: 미확보 또는 해당 범주 관측 없음. 0으로 대체하거나 빈 지역을 지출 없는 지역으로 채색하지 않는다. 관측된 행에 지지/반대 중 한 방향만 없다면 그 방향은 0이다. 음수 정정 금액을 보존한다.
- 각 후보의 `election_types`는 `P2026`, `G2026`, `S2026`, `UNKNOWN` 등 원문 코드이다. 특정 경선을 선택하면 해당 코드의 allocations만 합산한다. 코드 앞 글자만 보고 연도를 섞지 않는다. 코드가 UNKNOWN인 주 공시를 날짜로 경선/본선 분류하지 않는다.
- `totals_by_reported_party`는 신고 정당 코드별 수치다. 후보의 신고 정당이 여러 개일 수 있으므로 필터는 allocations의 party에 적용한다. REP/GOP를 합치려면 표시 정책을 명시하고 원문 코드는 보존한다.
- 후보 명부에는 지출 없는 등록 후보도 포함하며 금액은 null이다. 등록 명부가 경선 참여·사퇴·최종 후보 여부를 확인한 것은 아니다. 워싱턴은 지출에서 식별한 후보만 있다.
- 주지사·상원은 주 전체 카드에 표시한다. 하원 각 지역구에 나눠 더하지 않는다. 대통령도 각 주로 분배하지 않는다.

`examples/superpac-map-client.mjs`는 DOM 없는 fetch/필터 예제다. 앱에서 사용할 모듈 위치로 Claude가 가져가면 된다.

```js
const api = createFinanceClient();
const { data: national, sourceStatus } = await api.getNational(2026);
const health = await api.getHealth(); // not_activated / success / failed
const state = await api.getState(2026, 'CA');
const district = await api.getRace(2026, 'CA', 'house', '01');
const rows = selectCandidateSpending(district, { phase: 'P2026', category: 'super_pac' });
const governor = await api.getRace(2024, 'WA', 'governor');
const stateRows = selectCandidateSpending(governor, { category: 'state_independent_spender_unclassified' });
```

검증된 실제 예: CA-01/P2026 슈퍼팩 지지 Mike McGuire $610,470.85, Audrey Denney 대상 반대 $126,791.45. 워싱턴 2024 C6 독립지출 지지 합계 $716,973.44, 반대 $78,833.85. **전체 선거자금이나 전국 슈퍼팩 총액이 아니다.**

## 매일/매주 실행과 미래 사이클

루트가 아니라 `New for anti/scripts/election_watch`에서:

```bash
python3 refresh_superpac.py --plan
python3 refresh_superpac.py --plan --date 2027-01-01
# 출력 cycles=[2028,2026]: 현재 사이클 자동 전환 + 직전 사이클 정정 재수집
python3 refresh_superpac.py --cadence daily
python3 refresh_superpac.py --cadence weekly
python3 refresh_superpac.py --force --cycle 2024
```

- 기본 매일 08:25 UTC(17:25 KST). `US_FINANCE_CADENCE=weekly` 저장소 변수를 설정하면 일요일만 실제 수집한다. 주간의 첫 일요일 또는 일간 매월 1일에 직전 사이클도 재수집한다. 2026 중간선거 이후에도 종료일 없이 동작하도록 작성했다.
- 자동 공시 사이클은 2027–2028→2028, 2029–2030→2030. 과거 자료는 계속 조회 가능하다. 그보다 오래된 정정 재수집은 명시적 `--cycle` 수동 실행이다.
- `ops/us_superpac_refresh.yml`는 **비활성 설치 템플릿**이다. Claude가 소유권 규칙에 맞게 `.github/workflows/us_superpac_refresh.yml`로 설치하고 main에 반영해야 한다. guard나 브랜치 소유자를 속이는 변경은 하지 않았다.
- 수집 성공 파일/상태를 GitHub에 저장한 뒤 기존 `deploy.yml`로 정적 asset 배포. 사용자 PC가 꺼져 있어도 GitHub runner에서 실행된다. main 보호 규칙에 따라 데이터 bot push 권한 또는 승인된 데이터 PR 방식이 필요하다. 새 개인 토큰을 요구하거나 자동 생성하지 않는다.
- 실패한 출처는 마지막 정상 파일을 보존하고 다른 출처는 갱신한다. 지도 금액/참조 검증 후에만 새 catalog를 원자 발행한다. 실패도 `usa_election_finance_refresh_status_v1.json`에 남기며 Actions는 실패 상태로 끝난다.
- UI는 catalog 재생성 시각보다 `source_status.*.last_success_at`과 `last_filing_date`를 사용한다. refresh_status의 failed + source 실패를 표시한다. 출처별 stale_after_hours를 사용한다(현재 사이클 일간 72h / 주간 240h, 직전 월간 사이클 1080h). 운영 미활성화 상태와 실패를 동일시하지 않는다.
- 데이터 해시 파일은 내용이 같으면 재사용. 이전 독자를 위해 자동 삭제하지 않는다. 장기 보존 정리는 현 catalog 참조·서비스 캐시 보존 기간을 고려해 별도 운영 작업으로 한다.
- API quota 및 원본 신고 주기로 지연될 수 있다. 매일 실행은 매일 새 신고가 존재한다는 보장이 아니다. 요청 예산 초과/타임아웃을 성공으로 위장하지 않는다.

## 주지사 확장

현재 자동 어댑터는 워싱턴 C6 하나다. 공식 `67cp-h962` 데이터에서 현재 정정본 C6.3의 `portion_of_amount`만 합산한다. 반복된 `total_cycle`, `total_this_report`, vendor 지출, funding source를 같이 합산하지 않는다. C4 등은 포함하지 않아 partial이다. 메타데이터 변경 또는 순회 중 revision 변경은 실패로 처리한다.

나머지 주의 자료는 공식 출처 검증 후 개별 어댑터가 필요하다. `config/usa_state_campaign_finance_sources_v1.json`에 8개 주 접근처와 구현 상태가 있다. 기존 수동 주지사 입력 계약도 유지하나 WA 자동 입력과 겹치면 중복을 피하기 위해 빌드가 실패한다.

워싱턴 데이터는 공식 배포 페이지에 개인 목록의 상업적 사용 제한 문구가 있다. 이 어댑터는 기부자 목록·주소·연락처를 수집/발행하지 않는다. Claude의 제품 배포 검토에 이 출처의 이용조건 링크를 함께 넘긴다: https://data.wa.gov/api/views/67cp-h962.json

## 배포 전 검증

```bash
python3 -m unittest discover -s tests -p 'test_superpac*.py' -v
python3 build_superpac_map.py
python3 validate_superpac_map.py
node examples/verify-superpac-client.mjs
```

첫 수동 Actions 실행 후 최신 커밋의 catalog, CA-01, WA-2024 주지사 파일이 운영 경로에서 HTTP 200인지 확인한다. 미래 경계 일치·최종 후보 확정·49개 주지사 자동 수집·긴급보고·모금/기부자 추적은 이 인수 작업으로 완료됐다고 표시하면 안 된다.
