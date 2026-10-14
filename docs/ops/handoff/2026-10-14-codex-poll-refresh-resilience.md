# 일일 여론조사 수집 안정성과 ME 재진행 인수

사용자 2026-10-14 요청: 정기 수집 문제를 먼저 고치고 최근 보류 발표를 원문 검토한 뒤 ME를 진행한다. 자동수집이 중단되지 않도록 코드를 보강하고 운영 반영은 Claude가 검토할 수 있게 준비한다. 기존 병합·배포 보류는 유지한다.

- checkout: `/Users/yeoninair/Documents/해운 데이터/us-poll-refresh-resilience-20261014`
- branch: `codex/poll-refresh-resilience-20261014`
- 시작 main: `80497277`; 주별 packet 없는 공용 기반 PR이다.
- 소유권 예외는 이 정확한 브랜치의 `.github/workflows/us_election_polls_refresh.yml` 한 파일만이다. `deploy.yml`, Worker, UI 및 금융 workflow는 변경하지 않는다.

## 확인된 운영 장애와 변경

10/12–14 일일 polling 실행은 `validate`의 날짜/fixture 오류로 실패했고 `refresh`가 생략됐다. 10/14 실패 run은 `38489117223`이다. 공개 live/health JSON의 마지막 실제 수집은 `2026-10-11T00:16:19.749666+00:00`, as_of는 10/11이다. old health의 ok만으로 현재 수집 성공이라 판정하지 않는다.

기존 검증을 우회하지 않고 별도 read-only `capture` job을 먼저 실행한다. 회귀 검사가 실패해도 실제 API·검토 원문 입력은 `us-polls-source-capture` artifact에 14일 보관된다. `refresh`는 **capture와 validate 모두 성공한 경우만** 실행하고 이 체크포인트를 재검증한다. 두 번째 API 요청이나 새 수집일을 만들지 않는다. 일일 06:10 KST cron, workflow 이름, 기존 게시 충돌 재생성/3회 재시도, 배포 연결은 유지한다.

API의 429·500·502·503·504 및 일시 네트워크 오류는 총 3회로 제한해 재시도한다. Retry-After의 수치 지연은 최대 30초다. 403·다른 도메인 redirect·빈 응답·스키마 오류는 성공으로 바꾸지 않는다. 수집 전용 실패는 attempt 파일만 쓰며 공개 health/마지막 정상 JSON은 건드리지 않는다.

의석 전망의 의존 파일 부족은 forecast/health의 명시적 held 상태로 남긴다. 유효 여론조사 생성까지 실패 exit로 바꾸지 않으므로 검증된 여론조사는 계속 게시할 수 있다. 원자료 캡처 성공을 검증·게시·배포 성공과 혼동하지 않는다. 실제 API 장애나 검증 실패 때 게시를 보장하는 기능은 아니다.

## 실제 수집 검증

`--capture-only --capture-output /private/tmp/poll-evidence-20261014/full-run-capture.json`을 한 번 실제 실행했다. API 1,484행과 보완 포함 1,509행을 `2026-10-14T05:14:02.840821+00:00`에 캡처했다. 공개 데이터 diff는 없다. 모든 raw 행이 본선 집계 적격이라는 뜻은 아니다. 로컬 경로는 임시 검증 자료이며 GitHub에서 수집됐거나 배포된 artifact가 아니다.

## 최근 7건 원문 검토

정확한 발표·API 지문을 묶는 주별 검토 입력으로 편입해야 하며 기관의 모든 후속 발표를 자동 승인하지 않는다. 기관 수·AAPOR 참여에 정확도 등급을 붙이지 않는다. 아래 검토는 10/14 기준이다.

| 주/직위 | API ID | 원문 대조 | 처리 근거 |
|---|---|---|---|
| TX 상원 | us-202recc152b3f7 | ReconMR 10/5–8 LV617, Talarico48 / Paxton44 | 일반 named-ballot. 원문에는 ReconMR만 확인되므로 API의 Siena 공동표기는 미확인으로 별도 기록하고 기관 그룹은 reconmr로 분리 |
| TX 주지사 | gov202rec101a5410 | 같은 파동, Abbott48 / Hinojosa47 | 상원 문항과 별도 직위. 4.4pp 발표 sampling error·confidence level 미공개. 격차를 확정 승리로 바꾸지 않음 |
| NC 상원 | us-202surbcf9e1be | SurveyUSA 10/7–11 LV643, Cooper54 / Whatley40 | WRAL-TV·WSOC-TV 의뢰. Q3 일반 ballot, 발표 credibility interval5pp를 일반 sampling MOE로 바꾸지 않음 |
| MN 하원01 | us-202sur83d49b6b | SurveyUSA 10/4–9 LV565, Jake Johnson46 / Finstad44 | KAAL-TV 의뢰. Q7 일반 ballot, credibility interval4.6pp. 명부 Jacob "Jake" Johnson과의 정확한 별칭 검토 필요 |
| FL 주지사 | gov202chaea67d341 | Change Research 10/8–10 LV920, Jolly47 / Donalds47 | RV1106과 LV920 구분. 미정 후 양자 재질문·API partisan flag는 참고 전용. 전체 조사 modeled error3.1pp를 LV sampling MOE로 쓰지 않음 |
| AZ 주지사 | gov202equ8231431c | Equis 원문은 9/1–9, RV1214 | API 10/1–9와 불일치. 원문 LV 문항의 정확한 표본도 미확인. 최근7일 조사로 편입하지 않음 |
| TX 상원 | us-202quaee83ce98 | Quantus 원문 URL 접근은 되나 본문/방법 표가 나타나지 않음 | API 수치만으로 원문 검토 완료라 할 수 없어 보류 |

원문: [ReconMR 발표](https://reconmr.com/wp-content/uploads/2026/10/TXP004-October-Press-Release.pdf), [NC SurveyUSA 결과](https://results.surveyusa.com/client/PollReport.aspx?g=0a876c84-9a95-4995-9218-82b1015f5d77), [MN SurveyUSA 결과](https://results.surveyusa.com/client/PollReport.aspx?g=3605b38b-d541-4db4-9d70-f6d4875faeb8), [FL 방법론·결과](https://changeresearch.com/research/2026/2026-10-12-florida-aapor-methodology-statement), [AZ Equis 원문](https://www.weareequis.us/research/memo-arizona-voter-research---sept-2026), [TX Quantus 원문](https://quantusinsights.org/polling/f/texas-senate-paxton-and-talarico-in-a-near-tie).

ReconMR PDF SHA256 `7ba2aafe683effd2082c32abce5009f8e6895c97e7fe6000a0d828b01f0e2d7f`. SurveyUSA 최초 URL은 630바이트 frameset이므로 이것만 hash/검토하지 않고 실제 main/left/methodology 문서를 대조했다. 지문 영수증은 `/private/tmp/poll-evidence-20261014/surveyusa-documents.json`이다. FL 직접 HTTP 수집은 403이며 브라우저/웹 원문 검토와 자동 원문 다운로드 가능 여부를 구분한다. 공개 polling API는 새 키 없이 조회된다.

## 검사

- polling 전체 458개, finance 68개, 선거 JS63개, 소유권/ops14개 통과.
- `check_deploy_chain.py`: main 게시 workflow39개 모두 연결. deploy.yml diff 없음.
- 새 검사에는 수집 성공/실패 때 공개 데이터 보존, replay 오용 금지, source denial/schema fail-closed, 제한 retry, 의석 전망 실패와 여론조사 게시 분리가 있다.
- production workflow dispatch·main 병합·배포 없음. 실제 GitHub PR 검사 상태는 PR에 별도 기록한다.

## 운영 담당 반영 순서

#524 → #529 → #540은 10/14 main에 이미 병합됐다. 재병합하지 않는다. #554는 하위 state CLI의 catalog validation clock을 고치는 별도 공용 PR이며 ME/WA 입력 활성화 전에 필요하다. 이 수집 안정성 PR과 #554는 같은 파일을 수정하지 않아 독립 검토할 수 있다. 그 뒤 ME #541, WA #555와 새 발표 주별 입력을 각각 최신 main 기준으로 검증한다. 주별 PR끼리 다시 stack하지 않는다.

사용자가 운영 반영을 확정하면 공용 기반을 먼저 반영하고 기존 polling workflow의 실제 실행을 확인한다. capture·validate·refresh·게시 main commit·deploy run·배포 live/health JSON의 새 시각을 각각 확인한다. 검사가 실패하면 보관된 source artifact를 현재 코드·검토 목록으로 재검증하고 게시하며 생성 JSON을 손으로 합치지 않는다. API 키·유료 접근이 새로 필요한 경로만 멈추고 사용자에게 요청한다. 재설정은 사용자가 직접 클릭한다.
