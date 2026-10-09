# AK 공식 명부·순위선택 조사·기존 독립지출 인수 — 2026-10-09

사용자의 알래스카 재개 요청으로 **AK 한 주**를 검토했다. 브랜치 `codex/ak-state-evidence-20261009`, 시작 기반은 Draft PR #506의 `a3a8e14ab4c8208951696d7a0c93660827c494ab`다. 작업 중 다른 세션에서 #506 스택이10/9 04:50UTC main에 병합된 것을 원격으로 확인해, 선거 코드·데이터가 같은 최신main `3b2e2a0d3970d64c2598d59f4bab5b09cb2cb9a8` 위로 AK만 정렬하고 main 대상 별도 Draft PR을 준비했다. 기존 후보명부 작업 폴더는 CT 브랜치의 미커밋 작업을 포함하므로 그대로 보존하고, AK 변경만 별도 worktree로 복원했다. 이번 세션에서 UI 제품 코드·workflow·LETF 변경, main 병합·배포·수동 Actions 실행은 없다. JS 변경은 최신 명부 검토일을 반영하는 회귀검사의 시계뿐이다.

## 공식 선거와 후보

[Alaska Division of Elections 본선 견본 투표용지](https://www.elections.alaska.gov/election/2026/General/SampleBallots/HD1-JD1.pdf)의 인쇄 후보를 대조했다. **상원1석·연방 하원 전역구1석·주지사1석, 각각4명**이다. 문서명 HD1은 주의회 구역이며 연방 하원은 `USA:AK:house:00`으로 유지한다. API의 전역구 운송 번호01을 주의회1구와 혼동하지 않는다.

| 선거 | 인쇄 후보와 정당 |
|---|---|
| 상원 | Gerald L. Heikes REP · Mary Peltola DEM · Daniel J. Sullivan Jr. OTH · Dan S. Sullivan REP |
| 하원 전역구 | Nick Begich REP · Eric Hafner DEM · Bill Hill IND · James C. “Jim” McDermott LIB |
| 주지사 | Dave Bronson REP · Jonathan S. “JKT” Kreiss-Tomkins DEM · Treg Taylor REP · Bernadette M. Wilson REP |

공식 등록 정당을 지지·추천 정당과 바꾸지 않았다. Hill의 Nonpartisan은 IND, 정당 표기가 없는 Daniel J. Sullivan Jr.는 OTH다. 현직 Dan S. Sullivan과 별도 후보 Daniel J. Sullivan Jr.는 동일인이 아니다. 주지사 러닝메이트4명은 각 티켓에 보존하며 주지사 후보를8명으로 세지 않는다. 모든 선거에 복수 후보가 있어 **명부상 무경쟁/무투표 당선으로 판정한 선거는 없다.** 기명후보 전수 확인이나 당선 인증을 주장하지 않는다.

공식 PDF는 웹 도구의 추출 텍스트로 후보·직위를 확인했다. 직접 바이너리 요청은405여서 **공식 투표용지 SHA256 및 이미지 대조는 미확보**다. 표본 문서가 전국/모든 투표용지 인증을 대체하지 않는다. [공식 선거제도 안내](https://www.elections.alaska.gov/election-information/)와 대조해 세 선거를 순위선택투표(RCV)로 표시했다.

## 실제 수집 결과: API37레코드 중5개와 원문 보완1개

실제 공개 VoteHub API를 AK 범위에 재실행했다. 마지막 성공 조회 `2026-10-09T04:59:12.473203+00:00`, AK37레코드 중5개를 검토 편입하고 Quantus 첫 선택 원문1개를 보완했다. **6개는 조사 문항 관측 수이며 독립 조사6회가 아니다.** Quantus·Cygnal·AARP 공동조사라는3개 기관 그룹/파동이다. AARP는 같은 파동의 세 선거 문항이다.

| 선거·기관 | 기간·문항 | 관측 | 처리 |
|---|---|---|---|
| 상원 Quantus | 9/28–30, Q1 첫 선택 | Dan46.1 · Mary45.5 · Daniel J.1.6 · Heikes1.3 | PDF 보완1건 · 참고 |
| 상원 Quantus | 같은 파동, Q3+Q4 강제 양자 및 leaner | Mary47.2 · Dan47.8 | API1건 · 참고, 최종 RCV와 다름 |
| 상원 AARP | 9/8–11, 최종 라운드 모의 결과 | Mary53 · Dan47 | API1건 · 참고 |
| 하원 AARP | 같은 파동, 최종 라운드 모의 결과 | Nick57 · Bill43 | API1건 · 참고 |
| 주지사 AARP | 같은 파동, 최종 라운드 모의 결과 | JKT55 · Wilson45 | API1건 · 참고 |
| 주지사 Cygnal | 9/24–27, 첫 선택 | JKT44 · Wilson24 · Bronson8 · Taylor9 · 미정15 | API1건 · 참고 |

Quantus 연구 전체 표본은758, 투표 의향 문항 표본은737, 후속 leaner 조건부 표본은35다. 전체 표본758을 최종 유효표/조건부 문항 표본으로 복사하지 않는다. [Quantus 원문 PDF](https://drive.usercontent.google.com/download?id=1nCtCrSwufcL_hlLEVQiN-xsM4f_6c-6C&export=download)의 방법론과 Q1을 이미지로 대조했다. 문서 SHA256 `7c8c88cf83234fad2acd5fd19d3647e8048c1ce541fefd12eeeb8b1ab375422f`는 실제 재조회에서도 동일하다.

[Cygnal 메모](https://www.cygn.al/wp-content/uploads/2026/10/AK_GOV_Memo.pdf)는502LV, live phone/SMS, 보고 오차4.37pp를 확인했다. 의뢰자·전체 문항 미공개와 당파성 표시를 보존하며 정확도 등급으로 바꾸지 않는다. 메모 페이지는 실제 이미지로 대조했다.

[AARP 원문](https://www.aarp.org/pri/topics/voter-research/politics/2026-midterm-election-poll-alaska/)과 발행기관 검색 텍스트/발표문을 대조했다. 전체800LV 연구라는 사실은 최종 라운드의 유효 응답자 수를 뜻하지 않으며 그 분모는null이다. API의 Fabrizio, Lee 표기와 발행기관의 Fabrizio Ward/Impact 표기를 함께 보존했다. 직접 HTML/PDF403 및 전체 질문지 미확보를 숨기지 않았다.

세 문항 형식을 `first_preference`, `forced_two_candidate`, `simulated_final_round`로 나눴다. **6개 모두 참고 전용이며 일반 우세·색상·의석 전망에는0개 편입**이다. 정확도 등급은null이다. RCV 문항을 통상 양자 선거의 승패 투표로 합산하지 않는다. 10/9 기준 기본7일에는 참고도0개, 14일에는 상원 Quantus2문항/주지사 Cygnal1문항만 기간 안에 있다. 하원 AARP는14일 밖으로 누적 이력에 보존한다.

나머지 API32개는 경선 전·과거 대진·문항 단계/원문 미검증 등 구체 사유로 보류했다. Siena 최신 주지사·상원 발표는 원문 일부를 찾았지만 전체 문항·RCV 단계/분모 접근을 마치지 못해 편입하지 않았다. 최신 Alaska Survey Research는2차 보도를 발견했으나 검증할 원문·방법론과 해당 API 레코드가 없어 감사 파일의 `discovered_not_ingested`에만 남겼다. Reddit/뉴스 헤드라인을 직접 조사 관측으로 만들지 않는다. 과거 ASR 페이지를10월 발표의 증거로 사용하지 않는다. 보류는 조사기관이 가짜라는 판정이나 해당 지역에 조사가 없다는 단정이 아니다.

## 후보별 독립지출: 기존 관측 연결, 새 FEC 수집 아님

하원2/4명, 상원3/4명의 검토된 FEC ID를 공식 후보에 연결했다. Mary `S6AK00276`, 현직 Dan `S4AK00214`, Heikes `S8AK00140`; 다른 Daniel J.에게 현직 ID를 복사하지 않았다. Nick `H2AK01083`, Bill `H6AK01092`를 유지한다. 이름 별칭에도 같은 검증 ID가 전달되도록 수정했다. Hafner·McDermott·Daniel J.의 새 FEC 신원 확인은 미완료이며 알려진 2차 출처 reported ID와 검증된 candidate ID를 구분한다.

아래는 **기존10/8 FEC O범주 Super PAC, 신고 선거유형P2026 관측**이다. 후보 캠프 수입이 아니며 이번 본선 지출로 바꾸지 않는다. 금액 단위는USD다.

| 후보 | 지지 독립지출 | 반대 독립지출 |
|---|---:|---:|
| Nick Begich | 518,945.87 | 125,000.00 |
| Bill Hill | 12.50 | 0.00(관측된 행 범위) |
| Gerald L. Heikes | 828,895.12 | 0.00(관측된 행 범위) |
| Mary Peltola | 72,743.99 | 2,860,561.18 |
| Dan S. Sullivan | 327,969.22 | 1,149,171.53 |

현재 후보의 G2026 본선 O범주 관측은 미확보/null이다. 위 금액·원래 P/G/UNKNOWN·정정/중복 처리와 원본 날짜를 그대로 보존했다. U단일후보 IE·V/W hybrid를 O범주에 합치지 않으며 반대액을 상대 후보 지지액으로 옮기지 않는다.

FEC 마지막 성공 `2026-10-08T08:23:14.889991+00:00`, 금융index 생성 `2026-10-08T10:27:35.080057+00:00`다. **이번에 FEC 신규 금액을 재수집하지 않았다.** 원래 전역 여론조사 기준일10/8·조회일을 유지하고 AK 개별 race와 capture만 실제10/9로 갱신했다.

## 주지사 공시: 공식 공개 경로 발견, 접속 장애

[APOC Independent Expenditures Form15-6 검색](https://aws.state.ak.us/ApocReports/IndependentExpenditures/IEForms.aspx)과 [공식 안내](https://apoc.doa.alaska.gov/media/kdsh41zz/cdt-2024-ie-group-training-booklet.pdf)를 확인했다. 검색 폼이 열린 것과 거래 데이터 수집 성공을 구분한다. 대소문자가 맞는 현재 Home/IEForms 경로로 수집기를 실제 재시도했으나 두 경로 모두 timeout이었다. 마지막 probe `2026-10-09T04:53:55.597272+00:00`, 상태 `source_unavailable`, `candidate_amounts_available:false`다.

따라서 주지사4후보의 대상/S-O/신고·정정 관계를 검증한 금액은 아직null이다. 공개 검색에서 후보와 주민투표가 함께 나올 수 있으므로 주민투표 지출·일반 캠프 비용을 후보 IE로 만들지 않는다. 접속 복구 후 어댑터·후보 식별·거래/정정 전수 검증이 남았다. **새 API 키가 필요하다는 증거는 없으며 키를 요청하지 않았다.** 유료/인증 경로가 새로 필요해지면 그 수집만 멈추고 사용자에게 요청한다.

## 자동 수집과 재실행

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state AK --as-of YYYY-MM-DD
python3 publish_federal_matchups.py --state AK --as-of YYYY-MM-DD
python3 refresh_governor_source_access.py --state AK --cycle 2026
python3 refresh_state_evidence.py --state AK --as-of YYYY-MM-DD
```

후보 게시기에 `--state`를 추가해 AK만 게시할 때 과거 타주 검토자료를 재적용하지 않도록 했다. 전국 게시의 기존 동작은 유지하고 없는 주를 요청하면 기존 파일을 보존하며 실패한다. 이번 표시 board는 #506 원본을 입력으로 AK만 생성하여 타주49개를 그대로 보존했다. 생성 수치 파일을 충돌 구간별로 손병합하지 않았다.

주별/전국 수집기는 미래 API 레코드를 발견한다. 다만 **AK의 새 RCV 문항은 원문·단계 검토 전 자동 우세 판정하지 않는다.** 이번6개는 레코드 지문에 고정한 특정 발표 검토다. 미래 발표·기관 전체를 자동 승인한 것이 아니다. Quantus 보완 문서는 재조회 지문이 같을 때만 현 관측으로 재검증하며, 변경/실패 시 원래 관측일과 참고 상태를 보존한다. 같은 파동의 Q1/Q3+Q4를 문항별로 분리하고 후발 API 동일 문항은 중복 제거, 값 충돌은 보류한다. `.pdf`로 끝나지 않는 허용 PDF 다운로드 경로의 실제 `%PDF-` 시그니처 검사도 수정했다.

이 스택 브랜치의 정기 polling workflow는 매주 월요일06:10KST다. 사용자가 요청한 일일 변경은 별도 #489 통합 대상이며 이번 PR에 workflow 변경을 섞지 않았다. 원문 수기 검토 영수증은 감사 JSON에 보존하며 수집기가 미래 수기 검토까지 수행한다고 주장하지 않는다. 배포는 사용자 확정 순서를 기다린다.

## 검증·보존·다음 작업

로컬 **polling326 + finance68 + federal7 + JS51 = 452개 통과**. RCV 형식 혼합·문항 표본/분모·정확도 오판·후발 API 중복/충돌·문서 변경·두 Sullivan 신원·주 한정 게시/실패 보존·원래7/14일 계약을 검사했다. 금융 지도 검증(2026:576race·4,842candidate-race·16,265source행), `check_deploy_chain.py`(39workflow) 및 diff 공백 검사도 통과했다. 원문 접근 실패를 일부러 넣는 테스트의 실패 메시지는 기대한 예외 경로이며 검사 실패가 아니다.

SHA/구조 비교로 **타주503live race·55누적 이력·49state index·49표시 state, 기존 금융/주공시/감사/접근4,649파일, 과거 immutable state evidence116파일, 금융index 및 전역 날짜**가 보존됨을 확인했다. 임시 재생성한 AK evidence 중 최종 index가 참조하는 파일만 커밋한다. AK 상태는 `live_poll_sources_reviewed_finance_blocked`/`partial_observed`이며 완결로 표시하지 않는다.

수동 신규주 순서의 다음은 **B/KS(캔자스)**이며 시작하지 않았다. 자동 index의 `next_state_to_review:IA`는 선행 미완료 심화 검토를 가리키며 수동 순서를 대신하지 않는다. 기존 CT 폴더·다른 세션·#489 통합 대기는 보존한다. 병합/배포는 하지 않았다.
