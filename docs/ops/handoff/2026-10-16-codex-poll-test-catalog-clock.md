# 일일 여론조사 게시 복구와 검토·수집 기준일 분리

Codex. 사용자 “하원 최근14일2개” 점검·진행 지시. Worktree `/Users/yeoninair/Documents/해운 데이터/us-poll-test-catalog-clock-20261016`, branch `codex/poll-test-catalog-clock-20261016`, base main `77f52560`. packet 없는 공용 기반. MT #591 등 주별 PR은 별도다.

## 실제 장애

main 일일 run https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/38824886906 에서 capture·validate 성공, refresh/publish 실패. OR의10/14 finance identity review를 기존 전국 poll as_of10/11과 비교해 `future finance identity review`가 발생했다. publish_packet_projections가 새 체크포인트 재생 이전에 실행되므로 이후 실행도 같은 오래된 자료에서 막힌다. 실패한 검사를 무시하거나 source_status를 새로 바꾸면 안 된다.

build_state에서 후보·identity·공시 접근/감사 검토는 validation_day의 실제 오늘 상한을 적용한 review_checked_as_of로 검증한다. 여론조사의 as_of/fetched_at·7/14일 계산·선거 종료·stale 기준은 기존 as_of를 유지한다. 계획 검토일도 원래 조사일과 별도로 검사한다. 미래 검토일·잘못된 주·후보 신원/원문 불일치 거절은 유지한다.

## 하원2곳의 의미와 남은 누락

2026-10-16 실제 공개 API1499행 중 하원132행. 조사 종료일10/3~10/16 원자료8행/6지역구이며 이는 중복 파동·양자/다후보 문항·정파 의뢰가 섞인 레코드 수다. 현재 정책으로 API-only offline replay 결과 집계 적격은 CA48·MN01의2행/2지역구다. 미국 전체 실제 조사 수가2라는 뜻이 아니다.

| 지역구 | 최근 API행 | 현재 상태 | 필요한 작업 |
|---|---:|---|---|
| CA48 | 1 | 원문 검토 적격 | #589 이후 정상 게시 필요 |
| MN01 | 1 | 원문 검토 적격 | 정상 게시 필요 |
| NY21 | 1 | unregistered_primary_host | Siena 원문 존재. API가 WPTZ 기사 URL을 줘 개별 발표 원문 검토 연결 필요 |
| NC01 | 1 | primary_methodology_not_obtained | 조사 원문·방법론 확보 필요 |
| NE02 | 1 | pollster_not_selected | NPA 원문은 발견. 의뢰자·초기/leaner 문항 검토 전 승패 신호 금지 |
| KY06 | 3 | pollster_not_selected | 정파 의뢰·동일 파동 양자/다후보 구분, 원문 검토 후 참고 경로 검토 |

서비스 `/public/data/usa_election_live_polls_v1.json` 및 health는 실제 조회 시10/11이었다. 사용자의 localhost8766은 점검 당시 connection refused라 그 화면2곳의 실제 파일은 재확인하지 못했다. API-only replay로2곳을 재현했으나 동일 화면 파일이라고 단정하지 않는다. UI summary.recent는 조사 건수가 아닌 지역구 수다. source discovery는10/15 119항목/68레이스를 찾았지만 실제 관측으로 자동 승인하지 않는다. NY21 primary 링크가 discovery에 이미 있으므로 해당 원문 연결 누락은 별도 주별 PR로 보강해야 한다.

## 테스트의 별도 날짜 오류

FL/ME/MN/NC/TX 최근 원문 테스트가 모든 주 명부를 읽으면서 정책 날짜10/14를 고정했다. MT10/16 명부 추가 시 ballot review date/source 실패. 기존 tests.poll_config_fixture.SNAPSHOT_DAY를 정책 생성에만 사용하고 실제 normalize/summarize10/14·수집 영수증은 유지한다. 새 회귀는 다른 주 MT10/16 명부 로딩과 미래 primary review 거절을 검증한다.

## 범위와 검증

주별 packet·감사자료·전국 생성 JSON·운영 workflow·UI·deploy.yml 변경 없음. 생성물은 임시 검증 사본에서만 재생성한다. 오늘 main Actions의 원래 체크포인트(as_of10/15, captured_at2026-10-15T23:39:53.130052+00:00)를 다운로드해 projection → retry-capture → projection을 로컬에서 검증한다. 이는 신규 source 수집이나 게시가 아니며 영수증 날짜를 새로 만들지 않는다.

병합·배포·운영 workflow 직접 실행 없음. PR 준비와 운영 정상화는 구분한다. 기반 병합 후 실제 예약 실행의 성공과 서비스 기준일 갱신을 다시 확인해야 한다.

로컬 검사: polling525, finance68, 선거 JS90, ops/소유권16 통과, deploy-chain40 workflow 통과. 원래 실제 체크포인트의 projection→retry-capture→projection 정상, 상태50개 원래 영수증 및104석 focus 유지, projection errors={}. CI와 동일한 --pending 재생성+projection 후 polling도 별도로 재검증 중이다. 새 API-key 필요 없음.
