# 미국50주 순차 여론조사·독립지출 연결 — 2026-10-08

사용자 지시: 50개 주를 A–E로 나누고 한 주씩 여론조사와 슈퍼팩을 연결. 후보 PR #490 기반의 별도 브랜치 `codex/us-state-evidence-20261008`에서 수행한다. UI·workflow·병합·배포는 이번 작업 범위 밖이며 배포 보류를 유지한다.

## 실행 순서

| 그룹 | 기준 | 주별 순서 |
|---|---|---|
| A | 요청 주·핵심 스윙스테이트 | NY → TN → GA → FL → PA → MI → WI → AZ → NV → NC |
| B | Cook 경합이 많은 나머지 주 | TX → OH → IA → CA → CO → VA → AK → KS → NE → ME |
| C | 남은 Cook 경합·한국기업 및 산업 관심 | AL → NJ → NM → NH → WA → OR → MT → IN → IL → KY |
| D | 나머지 주 1차 | CT → MD → MA → MN → MO → UT → HI → RI → ID → SD |
| E | 나머지 주 2차·루이지애나 별도 단계 | AR → DE → LA → MS → ND → OK → SC → VT → WV → WY |

그룹은 우선 작업 순서이며 선거 전망·품질 등급이 아니다. A는 NY/TN/GA/FL 및 기존 스윙 감시 주, 추가 요청 TX는 B 첫 순서다. B의 Cook 경합 수는 검토본 원래 날짜(하원9/25·상원10/6·주지사10/1)를 유지한다. 10/8 Cook 직접 접근은403이므로 최신 등급으로 갱신했다는 주장을 하지 않는다. 검토된 기업 시설 주는 AL/GA/MI/TN/TX이며 C 모든 주의 기업 주소 연결이 확인된 것은 아니다.

## 실제 완료와 남은 범위

- A→E 순서로50주 연결 점검을 실행했다. 하원435·선거 상원35·선거 주지사36의 후보/조사/공시를 주별 JSON에 연결한다. 비선거 상원·주지사를 공백으로 세지 않는다.
- GA→WY의 나머지48주도 계획 순서로 실제 여론조사 API 수집을 완료했다. NY의 나머지21개 하원 명부를 조사 대상에 추가 연결하고 NY→GA→FL을 후속 재수집했다. 하원435/435구가 검토 명부 기반 조사 대상에 연결된다. **수집 경로 점검은 전국 공시 완결·모든 원문 전수 검토와 다르다.** NY·TN의 부분 소스 검토와 나머지48주의 원문/공시 심화 검토를 구분한다. GA는 조사 원문6건을 보강했으나 최신 주 공시 접근 차단으로 미완료이고, FL 후속 원문9건·ECO172행 감사까지 부분 검토했고, PA 후속4건·공식ZIP 일반비용72,084행을 감사했고 다음 심화 검토는 **WI**, 재시도는 **GA→MI**이다. [GA 인수](2026-10-08-codex-state-evidence-GA.md).
- 주지사 후보별 금액은 CA·NY의2주만 구현된 부분 수집이다. TN은 공식 CSV 수집을 구현했으나 정정·거래 식별 검증 전 금액은 보류한다. FL은 공개ECO172행 일반지출 감사만 연결하고 후보별 금액은 보류한다. 금액 미확보34주는 TN·FL 감사2주, GA 접근 차단1주, 나머지31주 어댑터/출처 검토 필요로 구분하고, 비선거14주는 별도다. 미확보를0달러나 관측 없음 확정으로 처리하지 않는다.
- 하원917개 후보 ID가 같은 지역구 공시 카드와 연결된다. 상원은 현재 후보·공개 명부의 인용ID·동일 주/직위 FEC 이름/정당으로68개 후보의 ID를 추가 대조해34개 레이스에 현재 후보의 금액이 연결된다.9명의 이름/정당/ID는 여전히 미확인으로 남긴다. FEC 등록 자체로 본선 후보를 생성하지 않는다.

| 직위 | 선거 대상 | 현재 후보 대상 지출 관측 | 누적 조사 표시 가능 | 최근7일 | 최근14일 |
|---|---:|---:|---:|---:|---:|
| 하원 | 435 | 280 | 12 | 0 | 2 |
| 상원 | 35 | 34 | 12 | 1 | 5 |
| 주지사 | 36 | 2 | 18 | 1 | 7 |

위 숫자는 현재 후보 ID에 연결된 부분 관측/적격 조사이며 승패나 전체 지원금 총액이 아니다. 회기 전체 지출과 본선·경선·미확인 코드를 분리한다. NH01의 API `Stephany Shaheen`과 명부 `Stefany Amber Shaheen`은 이름 철자가 달라 신규 통합 계약에서는 원문/동일인 검토 전 보류한다. 다른 원래 조사 자료를 삭제하거나 숫자를 변경하지 않았다.

누적 표시79건(우세 집계 적격62·참고 전용17)이다. FL 원문9건 중3건을 참고 목록에 추가했다. [FL 검토·공시 한계·재실행](2026-10-08-codex-state-evidence-FL.md). GA 상원/주지사 각3건을 원문 대조했고6건 모두14일 창 밖이다. 새 FL16 PPP는 원문 대조된 참고 전용1건이며 우세색·7/14일 승패 집계에서 제외한다. GA Wedgewood2건은 원문의 책임 주체·연락처·기관 사이트가 확인되지 않아 `publisher_identity_unverified`로 보류한다. 기관 수와 출처 확인 수준을 기관 정확도 등급으로 바꾸지 않는다. 순차 실행 기록·보류 이유·재개 명령은 [후속 인수](2026-10-08-codex-state-sequence.md)에 있다.

## 뉴욕 실제 보강

- 실제 VoteHub API를 한 번 수집해 전체1426건 중 NY 관련30건을 발견했다. 기존 편입 기준을 유지해 NY17 하원·NY 주지사의2개 관측만 표시한다. 경선·미등록/원문 미확인 자료는 편입하지 않는다.
- [Emerson NY17](https://emersoncollegepolling.com/ny-17-2026-poll/):9/27–29 LV400명, PIX11 의뢰, 조사기관 원문·방법론 재확인.7일 창에는 없고14일 창에서 단일 기관 참고다.
- [Quinnipiac NY 주지사](https://poll.qu.edu/poll-release?releaseid=3967):9/17–20 LV1026명·58/39 원문Q1/방법·발표 오차범위4.1pp를 대조해 `source_quality`를 원문 수치 대조 완료로 보강했다. 정확도 등급/격차 유의성은 평가하지 않는다.7/14일 창 밖 누적 자료다.
- NY 공식 Schedule R/F를 다시 수집: 입력103건·검증76건(이전101/75). 미검토 IE지출자14건, 모호한 정정/복수 대상12건, 이름/방향 미해결1건은 제외한다. 검토된 지출자·동일 금액 단일 지급/단일 대상 연결만 집계한다.
- 주지사 집계는 연방 Super PAC이 아니라 주 미분류 독립지출이다. 신고 단계가 미확보이므로 본선 금액으로 추정하지 않는다.
- NY 단일 주 보강 당시 기존 지도 금융 index→새 NY 주/레이스 파일로 연결했다. 원래 전역 수집 날짜는 유지하며 실제 주별 수집 시점/응답SHA를 별도로 기록한다. 당시 연방 공시는10/5 수집·10/2 공시를 보존했다. 사용자 키 제공 후 전국 연방 재수집은 정상 완료(10/8 수집·10/6 포함 신고·15,955건)했고 기존 후보ID에 A→E 순서로 다시 연결했다. 주 공시 날짜·조사 관측 날짜는 유지했다. 상세는 후속 인수 문서에 있다.

## 재실행·인수 계약

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_evidence.py --state TN --as-of 2026-10-08
python3 refresh_state_evidence.py --group A --as-of 2026-10-08
python3 refresh_state_evidence.py --all --as-of 2026-10-08
python3 refresh_state_sequence.py --from-state GA --through-state WY --as-of 2026-10-08 --run-id 20261008-ga-wy --resume
```

개별 주의 새 API 관측을 수집하려면 `python3 refresh_state_polls.py --state TN --as-of 2026-10-08`을 먼저 실행한다. 이 실행기는 그 주의 전체 선거 슬롯만 갱신하며 다른 주의 관측·전역 기준일을 유지한다. 기존 기관·후보·기간 검사를 통과한 새 조사는 자동 편입되고 미등록 기관/변경 대진/원문과 다른 기존 레코드는 검토 대기다. API 밖의 모든 조사 발견을 보장하지 않는다. 참고 전용·당파성 조사는 우세 집계에서 제외한다.

테네시 공식 CSV 수집 감사는 `python3 refresh_governor_finance_audit.py --state TN --cycle 2026`으로 재실행한다. 주별 금액 정상화 수집기와 별도 경로이며 이 명령만으로 후보별 독립지출 금액이 공개되지 않는다.

- `refresh_state_evidence.py`는 검토 입력을 연결한다. `refresh_state_sequence.py`는 주마다 명부 연결→실제 공개 API 수집→주별 evidence 연결을 순차 수행하고 실행 기록을 저장한다. 새로운 지역지 조사·새 주별 공시 어댑터·GitHub 일정 설치는 별도다. 일일 여론조사 수집/본선 명부 편입 보강은 별도 PR #489이며 이 PR은 workflow를 편집하지 않았다.
- public index: `usa_election_state_evidence_index_v1.json`, 주별 파일: `usa_election_state_evidence/2026/{STATE}-{hash}.json`. index는 `baseline_join_checked`·`live_sources_reviewed_partial`·`live_poll_sources_reviewed_finance_blocked`, `next_state_to_review`·`next_state_to_retry`, 실패/이월 및 원래 자료 날짜를 구분한다. **새 주별 계약은 UI에 설치하지 않았다.** 기존 공시/여론조사 계약 변경은 기존 UI가 읽을 수 있다.
- evidence 연결기는 실패한 주의 마지막 정상 파일/기준일을 보존하고 다음 주를 점검한다. 실제 수집 순차 실행기는 실패한 주에서 멈춰 `blocked_state`를 저장하며 `--resume`은 성공한 주를 다시 수집하지 않는다. 동일 실행ID·기간·범위만 재개 가능하며 동시에 같은 공개 데이터 경로를 처리하는 순차 실행은 잠금으로 차단한다.
- 7/14일 창은 실행 기준일로 다시 계산하지만 자료 수집일을 바꾸지 않는다. 선거가 끝나거나 소스가 실패/오래되면 우세색을 보류한다. 선거 후 화면용 관측은 비우며 upstream 역사 자료는 보존하고, 인증 결과가 들어오면 별도 result로 남긴다.
- 새 API 키/유료권한이 필요한 경로는 수집을 멈추고 사용자에게 요청한다. 이번 NY 수집은 공개 무키 API이며 새로운 키를 요청하지 않았다. 재설정은 사용자가 직접 클릭한다.

## 검증 상태

- 최신 PA 후속: 원문4건(새 주지사1), 전국77건(적격60·참고17), 최근PA 주지사7/14일 단일기관 DEM 수치상앞섬. 신규 보완 원문은두PDF를 반복확인하며API동일파동중복/충돌을검사한다. PA08정당의뢰 원문은방법미확보보류. PA일반비용ZIP을IE금액으로변환하지않는다.325검사·타주488레이스/기존금융4637파일보존. 다음MI·장애재시도GA. [PA 인수](2026-10-08-codex-state-evidence-PA.md).

- 새 명부 연결6개·순차 실행3개·출처 보류1개 검사를 추가해 기존 검증과 GA13개 회귀 검증을 합쳐 Python polling185개, 연방 명부6개, 금융58개 및 JS51개 범위가 통과했다(합계300개). 실제50주·506레이스 조인과 TN 원본 관측/기준일 보존을 확인했다.
- API 장애/오래된 데이터의 색 보류, 선거 후 관측 비움, 이름 변경 보류, minor/Other 응답 보존, 지지/반대·경선/본선 분리, 동일 파일 재사용, 실패 파일/기준일 보존 검사가 통과했다.
- 병합·배포하지 않았다. 후보 PR #490 기반의 별도 검토 PR로 인수한다. ID 미확인/출처 장애/신규 공시 어댑터를 다음 주별 작업에서 계속 보강해야 한다.

## 50주 점검표

`지출`은 현재 후보의 지지/반대 관측이 연결된 레이스 수이며 전체 회기 레이스 합계와 다르다. 아래 표는 원래 입력의 수집 기준일과 신규 처리 날짜를 구분하는 JSON에서 생성한다.

| Order | Group / State | House spending / races | House polls | Senate spending / races | Senate polls | Governor polls | Governor disclosure route |
|---:|---|---:|---:|---|---:|---:|---|
| 1 | A / NY | 20/26 | 1 | non_election | 0 | 1 | implemented_partial |
| 2 | A / TN | 4/9 | 1 | 1/1 | 1 | 1 | collected_normalization_held |
| 3 | A / GA | 6/14 | 0 | 1/1 | 1 | 1 | source_access_blocked |
| 4 | A / FL | 16/28 | 3 | 1/1 | 1 | 1 | collected_normalization_held (ECO172, 후보금액null) |
| 5 | A / PA | 13/17 | 2 | non_election | 0 | 1 | collected_normalization_held (일반비용72084, 후보금액null) |
| 6 | A / MI | 13/13 | 0 | 1/1 | 1 | 1 | source_unavailable |
| 7 | A / WI | 5/8 | 0 | non_election | 0 | 1 | adapter_or_source_review_required |
| 8 | A / AZ | 7/9 | 0 | non_election | 0 | 1 | adapter_or_source_review_required |
| 9 | A / NV | 3/4 | 0 | non_election | 0 | 1 | adapter_or_source_review_required |
| 10 | A / NC | 7/14 | 1 (참고) | 1/1 | 1 | 0 | non_election |
| 11 | B / TX | 30/38 | 0 | 1/1 | 1 | 1 | adapter_or_source_review_required |
| 12 | B / OH | 8/15 | 1 (참고) | 1/1 | 1 | 1 | source_access_blocked |
| 13 | B / IA | 4/4 | 0 | 1/1 | 1 | 1 | adapter_or_source_review_required |
| 14 | B / CA | 49/52 | 1 | non_election | 0 | 1 | implemented_partial |
| 15 | B / CO | 4/8 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 16 | B / VA | 6/11 | 0 | 1/1 | 0 | 0 | non_election |
| 17 | B / AK | 1/1 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 18 | B / KS | 0/4 | 0 | 1/1 | 1 | 1 | adapter_or_source_review_required |
| 19 | B / NE | 3/3 | 1 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 20 | B / ME | 2/2 | 0 | 1/1 | 1 | 1 | adapter_or_source_review_required |
| 21 | C / AL | 2/7 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 22 | C / NJ | 7/12 | 0 | 1/1 | 0 | 0 | non_election |
| 23 | C / NM | 3/3 | 1 | 1/1 | 1 | 0 | adapter_or_source_review_required |
| 24 | C / NH | 2/2 | 1 | 1/1 | 1 | 1 | adapter_or_source_review_required |
| 25 | C / WA | 9/10 | 1 | non_election | 0 | 0 | non_election |
| 26 | C / OR | 3/6 | 0 | 1/1 | 0 | 1 | adapter_or_source_review_required |
| 27 | C / MT | 1/2 | 0 | 1/1 | 0 | 0 | non_election |
| 28 | C / IN | 2/9 | 0 | non_election | 0 | 0 | non_election |
| 29 | C / IL | 12/17 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 30 | C / KY | 3/6 | 0 | 1/1 | 0 | 0 | non_election |
| 31 | D / CT | 5/5 | 0 | non_election | 0 | 0 | adapter_or_source_review_required |
| 32 | D / MD | 6/8 | 0 | non_election | 0 | 0 | adapter_or_source_review_required |
| 33 | D / MA | 5/9 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 34 | D / MN | 2/8 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 35 | D / MO | 4/8 | 0 | non_election | 0 | 0 | non_election |
| 36 | D / UT | 3/4 | 0 | non_election | 0 | 0 | non_election |
| 37 | D / HI | 1/2 | 0 | non_election | 0 | 0 | adapter_or_source_review_required |
| 38 | D / RI | 0/2 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 39 | D / ID | 0/2 | 0 | 0/1 | 0 | 0 | adapter_or_source_review_required |
| 40 | D / SD | 1/1 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 41 | E / AR | 1/4 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 42 | E / DE | 0/1 | 0 | 1/1 | 0 | 0 | non_election |
| 43 | E / LA | 1/6 | 0 | 1/1 | 0 | 0 | non_election |
| 44 | E / MS | 1/4 | 0 | 1/1 | 0 | 0 | non_election |
| 45 | E / ND | 0/1 | 0 | non_election | 0 | 0 | non_election |
| 46 | E / OK | 2/5 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 47 | E / SC | 2/7 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |
| 48 | E / VT | 1/1 | 0 | non_election | 0 | 1 | adapter_or_source_review_required |
| 49 | E / WV | 1/2 | 0 | 1/1 | 0 | 0 | non_election |
| 50 | E / WY | 1/1 | 0 | 1/1 | 0 | 0 | adapter_or_source_review_required |

- 최신 MI 후속: 실제API91건·표시10건/원문9건·co/efficient2건신규편입, 전국79건(적격62·참고17). Fox미시간방법교체·Emerson소수점정정. 신원9명보강으로하원누적13/13, 본선4구. 주지사MiTN시간초과로미완료. 다음WI·재시도GA→MI.333검사·타주491레이스/기존금융4638파일보존. [MI 인수](2026-10-08-codex-state-evidence-MI.md).

- 최신 NC후속(사용자즉시요청): 공식상원4명/하원14대진보강, API38대상·표시9관측(상원8/하원1구참고1)·원문8대조. CommonCause/NRCC2원문누락보완, 최근7/14일적격0. 후보신원5명추가32→37연결, O누적하원7/14·상원1/1, 주지사비선거. 전국87관측(적격69/참고18). 최신NC01/BigData등방법·수치충돌보류.342검사·타주491레이스/기존금융4639파일보존. WI→AZ→NV예약유지·다음심화검토WI. [NC 인수](2026-10-08-codex-state-evidence-NC.md).

- OH 사용자즉시후속: API48대상·표시8(상원3/주지사4/하원09내부참고1), 원문재검토7. 7일상원/주지사CNN1기관씩;14일상원LV2/주지사LV3, RV별도. 공식후보주지사·보궐상원/하원01·08·13과기입/minor보강,13구Dixit추가·8구Enoch공시신원1추가. O누적하원8/15·상원1/1,주지사현재포털403.353검사·타주489레이스/기존금융4639파일보존. TX10/9 03:40·WI04:20/AZ05:00/NV06:00예약유지, B다음수동IA. [OH 인수](2026-10-08-codex-state-evidence-OH.md).
