# KS 후보·여론조사·독립지출 인수 — 2026-10-09

사용자 캔자스 진행 요청으로 **KS 한 주**를 보강했다. 기반은 미병합 Draft #508의 `6072b2e061df434751b049d06547732f7c96989f`, 브랜치는 `codex/ks-state-evidence-20261009`다. 새 전체 worktree 생성이 디스크 부족으로 실패해 Git이 제거한 부분 checkout의 부재를 확인했고, 커밋·업로드 완료된 AK checkout에서 새 KS 브랜치로 전환했다. 경로는 `us-ak-state-evidence-20261009`지만 현재 브랜치는 KS다. 기존 후보명부/CT/AL 작업공간은 수정하지 않았다. UI 제품 코드·workflow·LETF 변경, main 병합·배포·수동 Actions 실행은 없다.

## 후보: 하원4곳·선거 상원1석·주지사1석

[KS 선관위 공식8/4 경선 결과 PDF](https://www.sos.ks.gov/elections/26elec/2026-Primary-Election-Official-Vote-Totals.pdf)의1–2페이지를 실제 다운로드·텍스트·이미지로 대조했다. SHA256 `4198e9acc9ce41aecb08a7e34e03c5aad4df2044315fae396c75be109d92c768`. 아래 민주·공화12명은 해당 당 공식 최다득표 후보와 일치한다. 경선 단독 후보의100%는 본선 무경쟁/무투표 당선이 아니다.

| 선거 | DEM | REP | 소수정당 검토 명부 |
|---|---|---|---|
| 하원01 | Lauren Reinhold | Tracey Robert Mann (공식 경선명 Tracey Mann) | Steven Robert Jacob LIB |
| 하원02 | Don Coover | Derek Schmidt | John Hauer LIB |
| 하원03 | Sharice L. Davids | Eric Jenkins | Steven Adam “Steve” Hohe LIB |
| 하원04 | Katy Tyndell | Ron Estes | Andrew Ira “Drew” Cranmer LIB |
| 상원 | Adam Hamilton | Roger Marshall | David C. Graham LIB |
| 주지사 | Cindy Holscher | Ty Masterson | 본선 전체 공식 확인 미완료 |

연방15명·주지사2명의 검토 명부를 게시했다. 주지사 러닝메이트 KC Ohaebosim·Jeffrey Klemp는 티켓에 별도로 보존하며 주지사 후보 수에 중복하지 않는다. Jerry Moran의 비선거 의석에 새 선거/조사를 만들지 않았다. 세 선거 종류 모두 민주·공화 상대가 있어 현재 명부로 무투표 당선이라고 표시한 곳은 없다.

[최신 공식 후보 명부](https://www.sos.ks.gov/elections/elections_upcoming_candidate.aspx)는 www 유무 모두403이다. 따라서 **공식 경선 당선자 검증과 전체 본선 투표용지 인증을 구분**했다. 소수정당은 [Green Papers KS 명부](https://www.thegreenpapers.com/G26/KS)의 특정 조회 지문 `5f91937e708511d64e6eae33f7268bd53f000d155199ae99ab442bec0965a9a1`에 근거한 검토된2차 명부이며 공식 재인증을 주장하지 않는다. Sharilyn Ray의 독립 기명후보 표시는 별도 참고이며 검증된 인쇄 주지사 후보로 추가하지 않았다. `coverage:reported_active_candidate_listing`을 유지하고 `complete_ballot`로 승격하지 않았다.

## 여론조사: API6건 중3문항, 최근 우세 판정 없음

공개 VoteHub API를 실제 재조회했다. KS 조회 `2026-10-09T10:02:32.320809+00:00`, 대상6레코드·편입3문항·보류3레코드다. 전국 누적127관측(적격92·참고35)이며 이번에 다른 주를 수집한 것은 아니다.

| 선거/기관 | 조사 기간·표본 | 보존한 수치 | 처리 |
|---|---|---|---|
| 상원 Emerson/Nexstar | 9/15–16 ·750LV | Adam45 · Roger43 · David4 | 원문/방법 대조 적격, 현재14일 밖 |
| 주지사 Emerson/Nexstar | 같은750LV 파동 | Ty51 · Cindy44 | 원문/방법 대조 적격, 현재14일 밖 |
| 주지사 NYT/Siena | API보고9/22–30 ·605LV | Ty49 · Cindy44 | 발행기관 수치 대조·방법/표본 원문 접근403, 참고 전용 |

Emerson2문항은 독립 조사2회가 아니라 **한 파동의 상원·주지사 문항**이다. [Emerson 발표](https://emersoncollegepolling.com/kansas-2026/)의 Aristotle voter file/PureSpectrum, text-to-web/panel, 가중·750LV·기간·Nexstar 의뢰 및 보고 credibility interval3.6pp를 확인했다. [기관이 연결한 전체 결과표](https://docs.google.com/spreadsheets/d/1tg-s80eUIL2lkRdrNEk3RCMsyEGaKXSg/edit?ouid=107857247170786005927&rtpof=true&sd=true&usp=sharing)는 웹 원문 표의63–76행을 대조했다. 직접 htmlview는 JS 껍데기여서 그 HTML SHA를 결과표 수치 검증으로 주장하지 않는다. 상원44.8/43.3/3.7·미정8.2, 주지사43.5/50.8·미정5.7을 별도 원문 필드에 보존하고, 본문/API 반올림값을 임의 재배분하지 않는다. 후보 호감도 뒤의 초기 투표 문항이며 정보제공 후/미정층 재질문으로 바꾸지 않았다.

[Siena 주지사 발표](https://sri.siena.edu/2026/10/04/nytimes-siena-poll-of-likely-voters-gubernatorial-races-2/)에서49/44만 직접 확인했다. NYT 현 조사 전체 질문·방법 원문은403이어서605LV/기간은 **API 보고값**이다. `question_sample_n:null`, `primary_metadata_checked:false`, `signal_eligible:false`로 표시한다. 최신이라는 이유로 미검증 방법을 채워 넣지 않았다. 기존 자동 부분 검증 편입을 명시적인 참고로 보강해 기본7일/선택14일 모두 우세 후보는null이다.

Wedgewood2개는 폴더 링크만 연결되어 특정 발표 원문·책임 연구자·방법/의뢰자 검증 미완료로 보류한다. 가짜 조사 판정이나 Google Drive 전체 차단이 아니다. Tavern1개는 경선 전 과거 양자 대진이며 강제 선택/방법 원문을 검증하지 못해 현재 본선으로 편입하지 않았다. [Siena 상원 발표](https://sri.siena.edu/2026/10/03/nytimes-siena-poll-of-likely-voters-senate-races/)45/45/3은 발견했지만 API 레코드 및 원문 표본·기간/문항 확인을 마치지 못해 `discovered_not_ingested`에만 보존한다. 기관 수나 AAPOR 참여를 정확도 등급으로 바꾸지 않는다.

KS 하원01–04는 API0개이고 후보 대진을 사용한 제한된 기관/지역 발표 탐색에서도 검증 가능한 현재 원문을 확보하지 못했다. **현재 수집 범위에서 미확보**이며 전국 어디에도 조사가 없다는 뜻이 아니다. 예측모델·시장확률·일반 정당 지지율을 하원 여론조사로 만들지 않는다. 조사 대상과 후보명부 연결은4구 모두 유지되어 새 API 발표를 발견할 수 있다.

## 연방 독립지출:10/8 기존 관측, 새 수집 아님

하원12명·상원 Adam/Roger2명의 검토된 FEC ID를 유지/명부에 연결했다. David C. Graham의2차 reported ID `S2KS00154`는 검증된 `candidate_id`와 구분해null로 남겼다. 새로운 FEC 신원/금액 수집은 수행하지 않았다. 기존 마지막 성공 `2026-10-08T08:23:14.889991+00:00`와 금융index 생성 `2026-10-08T10:27:35.080057+00:00`를 보존한다.

Roger Marshall의 기존 O범주 Super PAC 지지는 **G2026 본선11,218.22USD(4행)**, P2026 경선34,679.27USD(4행)다. 관측 행의 반대0과 미관측 후보의null을 구분한다. Adam 및 하원12명은 현 O범주 관측 미확보이며0달러로 만들지 않았다. U단일후보 IE/V·W hybrid·후보 캠프 수입을 O범주에 합치지 않는다. 원본 금융 JSON/정정·중복 처리/원래 선거단계와 날짜는 변경하지 않았다.

## KS 주지사 공시: 목록 어댑터와 경선 참고2개, 본선 합계 미완료

[Kansas Public Disclosure Commission 공식 공시 안내](https://kpdc.kansas.gov/campaign-finance/view-submitted-forms-and-reports/)에서 SOS 공개 저장소의 [독립지출 보고서 목록](https://www.kansas.gov/ethics/CFAScanned/Others/2026ElecCycle/IndependentExpendLink.htm)과 [PAC 목록](https://www.kansas.gov/ethics/CFAScanned/PACs/2026ElecCycle/PAC%20Links2026EC.htm)을 연결했다. 실제 수집기로 두 목록을 재조회하여 **13단체·27개 IE PDF 링크**를 수집했다. IE 목록 원래 Last Updated8/21, PAC 목록10/7을 그대로 보존한다. 수집일10/9를 최신 거래 공시일로 바꾸지 않는다. PAC의 S/O는 Statement of Organization이며 지지/반대가 아니다.

`governor_ks.py`는 목록 제목·주기·열·URL·빈/잘린 표·중복을 검사하고 신규 보고서 링크를 다시 발견한다. 현 공식 ACF행의 생략된 `</td>`를 HTML 규칙대로 처리한다. 제목/스키마/접근 실패 시 CLI는 마지막 유효 감사 JSON을 보존한다. 새 API 키가 필요한 증거는 없으며 공개 접근에 성공했다.

다음 두 특정 PDF는 이미지로 행·수치·수신 도장·체크박스를 대조하고 재수집기에서 실제 SHA 동일성을 재확인했다. 문서가 변경/실패/목록에서 사라지면 원래 검토일과 참고값을 보존하며 fresh 금액으로 바꾸지 않는다.

| 공식 문서 | 실제 행 | 구분/제한 |
|---|---|---|
| [Kansas Comeback KC1](https://www.kansas.gov/ethics/CFAScanned/Others/2026ElecCycle/202607/IE_KC1_2607.pdf) | 7/2 Ty Masterson 주지사 반대8,500USD | 문서 Total this Period378,943.63은 해당 행/후보 금액이 아님 |
| [Kansas Comeback KC4](https://www.kansas.gov/ethics/CFAScanned/Others/2026ElecCycle/202607/IE_KC4_2607.pdf) | 7/28 Ty Masterson 주지사 반대138,270USD | 목록202607과 PDF 체크202610 불일치; 거래는8/4 경선 전 |

위 두 행은 **경선 전 참고이며 합계/본선 후보 금액에0개 편입**이다. 정정·취소·다른 보고서와의 중복 계보/전체 보고 전수 검증이 끝나지 않았다. ACF10월 보고서의 HD02/72/75는 KS 주의회이며 연방 하원/주지사에 붙이지 않았다. 일반 캠프 비용이나 보고서 전체합계를 후보 IE로 만들지 않는다.

공개 출력 `usa_governor_finance_audits/2026/KS.json`은 `collection_scope:public_report_indices_only`, `input_record_unit:report_link_not_transaction`, 후보별 support/oppose는null이다. `reviewed_PDF_references`에 별도 참고 두 행을 보존하며 새 PDF 자동 OCR·거래/정정 매핑은 미구현이다. 주별 evidence에는 이 감사와 접근 상태가 연결되어 `partial_observed/live_sources_reviewed_partial`로 표시되며 공시 완결을 주장하지 않는다.

## 재실행·자동화·검증

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state KS --as-of YYYY-MM-DD
python3 publish_federal_matchups.py --state KS --as-of YYYY-MM-DD
python3 refresh_governor_source_access.py --state KS --cycle 2026
python3 refresh_governor_finance_audit.py --state KS --cycle 2026
python3 refresh_state_evidence.py --state KS --as-of YYYY-MM-DD
```

기존 polling workflow가 새 API 발표를 발견하고 해당 출처/대진/기간 계약을 적용한다. 이번 검토는 특정 레코드 지문에 고정되어 현재 레코드의 표본·수치·의뢰자 등이 바뀌면 재검토한다. **새 KS 공시 목록 어댑터는 재실행 가능한 CLI이며 이번에 Actions 일정에 추가하지 않았다.** 이 브랜치 기존 polling은 월요일06:10KST 주간, 사용자 요청 일일 변경/하원104석은 별도 #489 통합 대기다. workflow/deploy 변경 없음 조건을 유지한다. 후보 최종명부 자동 인증·새 여론조사 원문 수기 심사까지 자동화했다고 주장하지 않는다.

로컬 polling342(신규 KS16 포함) + finance68 + federal7 + JS51 = **468개 통과**. 보고서 합계와 행 금액, 잘린/빈 표·외부 URL·중복·생략된 td, 과거 경선/본선, 특정PDF 변경/실패·원래날짜 보존, 임명/비선거 상원 혼입, 최신 참고 조사의 일반 우세 제외와7/14일 계약을 확인했다. 금융 지도 검증(2026:576race·4,842candidate-race·16,265source행) 및 `check_deploy_chain.py`(39workflow), diff 공백 검사를 통과했다. 기대한 오류 경로를 출력하는 테스트 메시지는 실패가 아니다.

SHA/구조 대조로 타주500live race·56누적 이력·49state index·49표시 state·기존 금융/공시/감사/접근4,650파일·과거 immutable evidence117파일과 전역 원래 날짜를 보존했다. 생성 JSON은 수집기/게시기로 다시 만들었고 다른 주 데이터나 원래 수집일을 손으로 합치지 않았다.

남은 작업은 KS 공식 본선 전체 명부 접근 복구, 하원 실제 조사/누락 Siena 상원 원문 확보, David FEC 신원 검증, 새 연방 금액 재수집, KS PDF 거래·선거단계·정정 계보/합계 어댑터다. 새 유료/인증 접근이 필요해지면 해당 수집만 멈추고 사용자에게 요청한다. 다음 수동 신규주는 **B/NE(네브래스카)**이며 시작하지 않는다. 자동 index의 선행 미완료 IA 심화 순서는 별도로 유지한다. #489 통합과 main 병합·배포는 사용자 확정 순서를 기다린다.
