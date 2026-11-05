# 2026-11-05 — Codex: 공식 개표 수집 기반 보강

## 범위·현재 상태

- 요청: 미국 선거 결과 반영을 시작한다.
- 시작 main: `7e67d8b026dbd1514d49778b341903491a546525`.
- worktree: `/Users/yeoninair/Documents/해운 데이터/us-official-results-20261105`
- branch: `codex/us-official-results-20261105`
- 이 PR은 **packet 없는 공용 기반**이다. 주별 운영 입력은 다음 독립 PR에서 등록한다. UI·workflow·전국 생성 JSON·당선 선언·공식 인증 파일을 수정하지 않는다.
- Claude의 #867·#869는 병합돼 있다. 기존 GA·CO·IA 수집 경로와 UI를 재사용한다.
- 기존 공식 개표 workflow의 최근 조회 결과: scheduled run `41995449536`, 2026-11-05 08:33:56 UTC 시작, success. 그다음 이전 실행은 01:35:38 UTC다. cron 설정은 20분이지만 실제 실행 간격을 보장한다고 보고하지 않는다.
- 이번 세션에서 main 병합·배포·workflow dispatch·reset 클릭은 하지 않았다.

## 실제 신규 확보 자료

애리조나 당국이 안내한 공개 JSON을 **한 번** 요청해 받았다. API 키가 필요하지 않았다.

- 안내: <https://azsos.gov/press> (11/04 공개 JSON·자동 수집 간격 안내 확인; 11/05 웹 읽기 도구에서는 403).
- 원자료: <https://app.enhancedvoting.com/cdn/results/Arizona/export-110326GeneralElection.json>
- 원문 electionDate: `2026-11-03`, results.name: `Arizona`.
- 원문 published_at: `2026-11-05T03:50:47.2427526Z`.
- 실제 다운로드 완료 시각: `2026-11-05T12:15:54.070421+00:00` (로컬 파일 mtime).
- 72,592,544 bytes; SHA-256 `28830cab092badf79d30a0d3297ff36b0baa1a4c6e51c224f112790744c60de3`.
- raw는 `/tmp/az-official-20261105.json`에만 있다. 대용량 원자료를 커밋하지 않는다.
- 회귀 fixture는 하원 9곳·주지사 1곳의 statewide 후보별 관측과 15개 카운티의 해당 선거 보고 수만 남겼다. 후보 수치·이름·ID를 바꾸지 않았고 precinct/group 세부 데이터만 제외했다. 축약 방식·원문 해시·원래 수집 시각은 fixture 안에 있다.

fixture는 공용 파서 회귀 검사용이다. 운영 주별 등록이나 전국 게시 완료를 뜻하지 않는다.

## 고친 부분

1. Enhanced Voting의 `U.S. Representative in Congress - District No. n` 명칭을 기존 하원 race ID로 정규화한다. 애리조나에 2026 상원 선거를 만들지 않는다.
2. 카운티 자료가 root `localResults` 또는 `results.localResults`에 있을 수 있다. 하나만 선택하며, 두 값이 다르면 보류한다. 중복 카운티·선거·후보도 오류로 처리한다.
3. 주지사/부지사 티켓을 먼저 분리한 뒤 정당 접미사를 제거한다. 공급원 후보 ID는 `source_candidate_id`로 보존하며 FEC ID라고 가정하지 않는다.
4. 보고 누락과 후보 득표 누락을 0으로 만들지 않는다. 실제 0표와 유효한 하향 정정은 허용한다.
5. 기타·기명투표 합계도 득표율 분모에 남긴다. 집계용 기명투표 행은 특정 후보의 선두 판정 대상으로 쓰지 않는다. 명시된 후보 이름은 유지한다. Clarity의 기존 write-in 처리 범위는 이번에 바꾸지 않았다.
6. 수집 시각과 원문 발행 시각을 분리하고 문서 SHA-256을 남긴다. 잘못된 선거일·다른 주·빈 결과·기존 선거 소실·더 오래된 발행 시각은 마지막 유효 자료를 `stale`로 보존한다. 실패 시 이전 영수증의 발행/수집 시각도 보존하고 `attempted_at`만 새로 기록한다.
7. 주별 출처는 `config/official_results_sources/2026/<STATE>.json`에서 독립 등록할 수 있다. 기존 공용 `official_results_2026.json`의 GA·CO·IA는 변경하지 않는다. 중복 주, 파일명/주 불일치, 연도·선거일 불일치는 거부한다. 기존 workflow가 같은 CLI를 실행하므로 workflow 변경 없이 로딩된다.
8. `render_fallback: false`인 JSON 출처는 HTTP 실패 후 브라우저로 즉시 재요청하지 않는다. AZ 등록에서 이를 사용해 안내된 요청 간격을 지킨다. 기존 GA/CO/IA 기본 경로는 유지한다.

## 검토 시 주의

- `unofficial_count`는 당국이 공개한 **인증 전 개표**다. `leader`는 현재 개표 선두일 뿐이다. 언론 선언·인증 결과·의석수·지도 승자색으로 승격하지 않았다.
- 보고된 투표구 수/전체 투표구 수는 예상 총투표 중 개표 비율이 아니다. 카운티 보고 수와도 다르다.
- 기존 UI는 `precincts_total`만 있고 `precincts_reporting`이 null이면 0으로 표시하는 한계가 있다. 이번 AZ 원자료의 10곳은 둘 다 관측돼 이 경우에 해당하지 않는다. 후속 UI 담당은 null을 0으로 바꾸는 표시를 고쳐야 한다. 원자료 누락을 임의 값으로 채우지 않는다.
- source feed는 약 73 MB다. 모든 상세 투표구 원자료를 public JSON에 싣지 않는다. AZ 공식 안내의 최소 요청 간격 2분을 준수하며 기존 20분 cron은 이보다 느리다. 이번에는 원문 한 번만 신규 요청했다.
- 주정부 인증 전 수치는 수정될 수 있다. 과거 수치의 하향 정정을 투표 삭제나 부정의 증거로 해석하지 않는다.
- API 키/계약이 없는 AP 자료를 가져오거나 AP 선언을 생성하지 않았다.

## 게시 순서

1. 이 공용 기반 PR을 검토한다.
2. 이 기반에 의존하는 **AZ 출처 등록 PR**을 별도로 검토한다. 입력은 AZ 파일 하나와 AZ 전용 검사·인수 문서뿐이다.
3. 두 변경이 main에 반영된 뒤 기존 공식 개표 정기 수집이 원자료를 다시 받아 전국 결과 JSON을 생성한다. 운영 dispatch와 병합·배포는 사용자가 정한다.
4. 공개 파일에 AZ 10 race, 발행 시각, `sources.status=ok`가 있고 UI에서 인증 전 개표로 보이는지 확인한다. 로컬 fixture/replay를 새 운영 수집으로 보고하지 않는다.

## 검증 기록

- 공식 개표 전용 검사 16개 통과: 실제 축약 원문 10선거 매핑, 양쪽 카운티 위치, 누락/중복/기명투표, 실패·발행일 후퇴·미래 시각·정정·선거 혼입 보존, 독립 출처 로딩, JSON 실패 시 재요청 차단.
- 기존 GA·CO·IA fixture 검사는 그대로 통과.
- 소유권 규칙 검사 15개 통과.
- 추가 언론 선언 검사는 처음 sparse checkout에서 ratings JSON이 없어 실행되지 않았다. 해당 main 파일을 읽기 전용으로 checkout한 뒤 2개 모두 통과했다. 제품 회귀가 아니다.
- deploy-chain 검사 통과: main에 쓰는 57개 workflow가 연결돼 있다. workflow 파일 변경 없음.
- 운영 수집·배포 결과는 아직 아니다. 전체 polling·finance·JS는 수정 범위 밖이라 재실행하지 않았다. 이 PR은 공식 개표 수집기와 직접 연관된 검사만 실행했다.
