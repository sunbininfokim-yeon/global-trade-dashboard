# 일일 여론조사 수집 복구 — 2026-10-15 갱신

사용자 요청: 자동수집을 지속하도록 보강하고 ME·최근 보류 발표를 검토한다. 10/15에는 제공한 취합 사이트로 수집 경로를 확대하며 베팅 지표는 이후로 미룬다. 병합·운영 workflow dispatch·배포는 사용자가 확정한다.

- checkout: `/Users/yeoninair/Documents/해운 데이터/us-poll-refresh-resilience-20261014`
- branch: `codex/poll-refresh-resilience-20261014`, PR #557. 주별 packet 없는 공용 기반이다.
- 이번 재검증 main: `57941ec0722940966abfe6c077d4c34db76efd7c`.
- workflow 예외는 `.github/workflows/us_election_polls_refresh.yml` 한 파일뿐이다. deploy.yml·Worker·UI·금융 workflow·주별 입력은 변경하지 않는다.

## 아직 운영 복구 완료가 아니다

10/15 확인한 일일 실행 [38656771365](https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/38656771365)는 `test_poll_nc_primary`의 `future state polling snapshot` 오류로 실패했고 refresh가 생략됐다. NC 자체의 새 state as_of보다 과거 national as_of를 테스트에 사용했다. 공용 public fixture 기준일이 전국 as_of뿐 아니라 각 주 as_of도 포함하도록 고친다. MN 입력 통합 검증에서 추가로 발견한 WA 테스트도 현행 명부 검증에는 공용 검토일, public join에는 공용 관측일을 사용한다. WA 과거 조사 시나리오의10/13은 보존한다. 데이터 수집일·원문 검토일·실제 미래 날짜 거부는 그대로다.

[배포 live](https://chokemonitor.com/public/data/usa_election_live_polls_v1.json)와 [health](https://chokemonitor.com/public/data/usa_election_live_polls_status_v1.json)를 실제 GET한 결과 as_of=10/11, fetched/checked=`2026-10-11T00:16:19.749666+00:00`이다. health의 옛 ok는 현재 수집 성공의 증거가 아니다. #557의 코드와 PR 검증만으로 운영 반영을 주장하지 않는다.

## 최종 동작

1. 별도 read-only capture job은 회귀 검사와 독립 실행한다. 실제 API 응답을 먼저 `.provider.json`에 기록하고, 보완 원문·명부 검토를 통과한 전체 재실행 체크포인트와 attempt 상태를 따로 기록한다. 뒤의 보완 출처 검토가 실패해도 이미 받은 API 감사 자료는 남는다. provider-only 감사 파일은 게시용 checkpoint로 재생할 수 없다.
2. 실제 270toWin 공개 목록 탐색을 별도 step으로 실행한다. primary capture 실패 때도 시도하며, 그 장애가 유효 VoteHub 게시를 막지 않는다. 탐색 JSON은 우세 집계 입력이 아니다. 자세한 검토는 `2026-10-15-codex-poll-source-expansion.md`.
3. 두 단계의 자료는 `us-polls-source-capture` artifact에 14일 보관한다. 게시에는 capture와 validate의 성공이 모두 필요하다. refresh는 보관된 체크포인트를 재검증하며 다시 API를 요청하거나 새 수집 시각을 만들지 않는다.
4. VoteHub 429·500·502·503·504와 일시 네트워크 오류는 총3회까지 재시도하고 숫자 Retry-After는30초로 제한한다. 403·잘못된 redirect·빈/변경 스키마는 성공으로 바꾸지 않는다.
5. 유효 여론조사와 의석 전망 실패를 구분한다. 의석 전망 의존 파일이 부족하면 forecast/health는 hold이지만 검증된 여론조사는 게시할 수 있다. API/검증 실패 시 게시를 보장하거나 검증을 우회하는 기능은 아니다.
6. 기존 일일06:10KST cron·workflow 이름·게시 충돌 시 최신 main 재생성/3회 재시도·배포 연결은 유지한다. 생성 JSON을 텍스트 병합하지 않는다.

## 실제 신규 수집과 로컬 재생

10/15 실제 capture: `2026-10-15T06:36:49.172887+00:00`, VoteHub1,484행·보완 포함1,509행. `/private/tmp/us-poll-expansion-20261015/us-polls-capture*.json`은 로컬 임시 검증 자료이며 GitHub artifact나 배포 데이터가 아니다. 원자료는 전날과 같은 행 수이며, 현재 API가 다른 모든 취합 사이트의 새 발표까지 포함한다는 뜻이 아니다.

최신 main의 검토 목록으로 이 실제 checkpoint를 `/private/tmp/us-poll-expansion-20261015/local-replay/`에서 재검증했다. 관측151개(집계 적격105·참고46), 보류752개이며 506개 선거의 관측 범위와 분리한다. 최근7일 우세 신호는 NC상원·TX상원의 단일 기관2곳이다. TX ReconMR의10/8 종료 조사는10/15 기준7일(10/9–15) 밖이지만14일에는 남는다. FL은 강제 양자 재질문·정파 의뢰 참고 전용이다. MN-01 신규 SurveyUSA 입력은 #564가 아직 미병합이라 이 main 재생에는 편입되지 않았다. 결측을 승패로 채우지 않는다.

## 최근 발표 및 운영 반영 순서

이미 main에 포함된 #524·#529·#540·#554·ME #541·WA #555·NC #562·TX #566·FL #568은 재병합하지 않는다. ME는 명부·원문 자료를 보강했어도 마지막 API 조사 종료일이10/5라 최신7일 자료가 없을 수 있다. 연방 IE 감사 부록과 전국 finance 게시 금액도 별도다.

TX Quantus의 초기 보류는 해소됐다. 연결된 실제 PDF와 대조해 전체854명과 Q1유효839명을 분리했고47.2/46.7/2.2를 검토했다(#566). 새 기관의 미래 발표가 모두 승인된 것은 아니다. AZ Equis는 API10월과 원문9월이 충돌해 최신 조사로 편입하지 않았다.

권장 남은 순서: **#557 공용 수집 복구 → MN #564 독립 입력**. 새 주별 PR은 최신 main 또는 명시한 packet-free 기반에서 분기한다. 사용자가 통합한 뒤 기존 일일 실행의 capture·validate·refresh·게시 commit·deploy run·배포 JSON의 실제 새 시각을 차례로 확인해야 복구 완료다. 운영 실행은 이 작업에서 하지 않았다.

## 검사

- native pending state 재생성 및 projection 성공. 원래 입력으로 재생성했으며 새 수집을 가장하지 않았다. 생성 결과는 커밋하지 않는다.
- polling500개, finance68개, 선거 JS74개, ops/소유권14개 통과. JS의 sparse checkout 제외 이스라엘 fixture는 HEAD에서 읽기 복원해 확인했다.
- 이후 provider 비교 파일 손상에도 보완 탐색이 보존되는 검사를 추가해 관련20개 재검사 통과.
- deploy-chain39개 연결 통과. deploy.yml diff 없음.
- 새 검사는 API 성공 뒤 후속 검토 실패 시 raw 보존·오용한 replay 거부·제한 retry·NC 날짜·출처 탐색의 후보 누락/광고/다중 문항/날짜·출처 장애를 검증한다.
- 로컬 검증과 GitHub PR 검사, 병합·배포는 각각 별도로 확인한다. API 키나 유료 권한이 새로 필요한 수집만 중단하고 요청하며, reset은 사용자만 클릭한다.
