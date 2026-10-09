# 텍사스 TX — 2026-10-09 예약 작업

사용자가 지정한 TX 한 주만 처리했다. 기준99add883, `codex/tx-state-evidence-20261009`의 별도 PR이며 #498 → #492에 의존한다. #492 추가 변경·UI·workflow·LETF·병합·배포 없음. 실제 UTC10/8 기준으로 TX만 갱신하고 타주/전국 원래 날짜를 보존했다. WI04:20/AZ05:00/NV06:00 예약을 변경하거나 대신 수행하지 않았다.

## 실제 여론조사와 원문 계약

TX API91레코드를 점검했다. 표시 관측은 하원3구 각1건, 상원6건, 주지사6건=15건. 이번 원문 재검토9건(신규 TSU하원3, TSU주전체2, UMassLowell/YouGov2, 기존Fox2). 기존 다른 조사의 검토일은 보존하며 새 원문 재검토를 주장하지 않는다. 상원·주지사 각1선거와 하원38슬롯의 감시를 유지한다.

- 하원15/28/34 TSU API에는7/27–30으로 잘못 전달됐으나 원문은8/18–22. 원래3레코드는 `primary_provider_field_dates_conflict`로 보류하고 검토된 특정 PDF/SHA와 올바른 날짜의 원문 보완3건을 연결했다. 표본15/34각700LV,28구600LV, 영어/스페인어 SMS→온라인, 투표가능성·과거참여 선별. 원문4페이지는2025 재획정 후2026지역구 경계를 명시한다. 후보 초기투표의향은15구Pulido50/DeLaCruz45,28구Cuellar45/Tijerina34/Durán6,34구Gonzalez45/Flores42/Espinoza3/Royal2, 미정각5/15/8. 이3지역구의 상원·주지사 응답은 주 전체 표본이 아니므로 수입하지 않는다.
- 하원3구는 모두8월 누적참고이며 최근7/14일 우세/의석 전망에 넣지 않는다. 정당 수나 기관수에 기반한 품질 등급을 만들지 않는다.
- TSU 주전체9/15–19,1800LV/보고오차2.31pp, 등록유권자 무작위SMS·온라인·2단계LV선별. 상원Talarico47/Paxton46/Brown3,주지사Abbott49/Hinojosa45/Dixon2,미정4. 현재14일 밖 자료는참고.
- UMassLowell/YouGov9/18–28,850LV(910조사 후850매칭), 비확률온라인패널/매칭·CPS2024/APVoteCast/반복비례가중, 보고오차4.5pp. 공식방법론 발표일10/8과 URL날짜10/9를 분리했다. Q1 상원Talarico45/Paxton45/Brown2, Q4주지사Abbott48/Hinojosa44/Dixon1. 원문미정/기타/비투표 응답은방법 검토에 보존했다. AAPOR투명성참여는 정확도나표본추출확률 인증이 아니다.
- Fox LV881, Q3상원51/49와Q12주지사47/52, leaner포함·RV열과분리해 원문PDF 지문을 재검증했다.
- 최신TX15 Normington9/24–28(54/41)와TX35내부발표는 방법론 원문 미확보로 `commissioner_primary_methodology_not_obtained`. 조사 발견과미발견을 구분하며 미확보를0%/승패로채우지 않는다.

최근7일은 TX38하원·상원·주지사 모두유효 최신조사없음. 최근14일 상원 tie,주지사 poll_lead REP이며7일기본/14일선택은그대로이다. 8월하원3조사의우세를현재우세로사용하지 않는다.

원문보완은유한한특정발표 목록이며 새PDF발표를무조건승인하지않는다. 같은파동이후API에들어오면표본·수치·의뢰자등일치때중복제외,불일치시실패보존. 원문지문변경/장애는원래날짜참고전용이월. 공유PDF호스트전체조사 자동승인아님.

## 후보와 공식 공시

Texas SOS8/28최종본선인증PDF를1396페이지 다운로드·SHA검증했다. 이번 직접후보대조는하원15/28/34·상원·주지사5선거이며, 정당·소수후보·수기별명(예 VicenteGonzalez→VicenteGonzález, ChrisRoyal→ChrisB.Royal)을 연결했다. TedBrown LIB/PatDixon LIB도추가했다. 공식이름및현재명부와FEC등록을구분한다. 이5선거는복수정당경쟁이며확정승자/무투표당선아님. 남은33하원은기존검토명부를유지하며이번에직접공식전체명부검증을완료했다고주장하지않는다. 반복군별PDF 자동파서는34하원구만추출하므로전수명부완료로쓰지않는다. 연락처·주소는공개산출에복사하지않았다.

기존FEC O누적현재후보금액은하원30/38·상원1/1 연결. 새FEC금액재수집은하지않았고 원래공시·정정/중복/O·U·V·W분리를보존했다. 미관측하원07/16/20/25/28/31/33/36은지출0이아님.

Texas TEC 공식ZIP은실제접근·범위다운로드·CAND수집에성공했고253873행중2025–26주지사후보수혜단일거래1행을감사에보존했다. report101068243/expenditure106389233, 신고10/5·지출9/9, AmericaPAC, 신고이름 `Greg Abbot`, 총27024705센트. 이름이공식 `Greg Abbott`와다르므로미확인·정당UNKNOWN이며 후보에게귀속하지않았다. CAND에는지지/반대필드가없어단일수혜행도지원액으로바꾸지않는다. 일반비용·후보캠프수입·연방SuperPAC O로변환하지않는다. 다중대상/중복/정정취소/타사이클행을제외한표는전체주지사외부지출총액이아니다. 지지/반대후보금액은null,상태 `collected_normalization_held`.

`refresh_governor_tx_audit.py`는공식공시감사를반복수집하며오류시마지막유효파일/원래시점보존·별도건강상태를기록한다. UI나정기Actions설치는이번에추가하지않았다. 필요한장애는키가아니라거래별방향과공식신원정정근거이다.

## 산출·검증

- 주별파일 `usa_election_state_evidence/2026/TX-0c054fa1b525f040.json`. work_status `live_sources_reviewed_partial`는일부원문/공시검토이고전수최신금액완료가아니다.
- 원문감사 `usa_election_poll_release_reviews/2026/TX-primary-20261009.json`.
- 공시감사 `usa_governor_finance_audits/2026/TX.json`, 건강상태 `usa_governor_finance_audit_status/2026/TX.json`.
- polling252·금융63·연방6·JS51=372검사통과. 새7검사는원문/API 날짜충돌,LV표본,주전체/지역구구분,별명교차오연결,소수후보,미확인IE방향/이름,후속레코드변경을검사한다.
- 타주466poll레이스·42누적이력·49주index·기존금융/감사파일4641개및타주후보명부/날짜보존을검증했다.

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state TX --as-of 2026-10-08
python3 refresh_governor_tx_audit.py
python3 refresh_state_evidence.py --state TX --as-of 2026-10-08
```

텍사스예약한번처리후종료한다. 다른주순차작업은이번예약에서시작하지않는다. 03:55로재실행시간을옮기려던변경은자동승인심사가예약유지지시를이유로거절했고기존시간변경은발생하지않았다.
