# 오하이오 OH 후속 — 2026-10-08

사용자 즉시 요청으로 B그룹 OH를 검토했다. TX는 10/9 03:40 한국시간 별도 예약, WI04:20/AZ05:00/NV06:00 예약을 그대로 유지한다. 기존 순서 index는 미검토 WI를 다음으로 유지하며 OH를 즉시 처리했다고 A그룹/50주 완료로 표시하지 않는다. B그룹 다음 수동 대상은 IA이다. 후보 PR #490 기반 Draft [PR #492](https://github.com/sunbininfokim-yeon/global-trade-dashboard/pull/492), 브랜치 codex/us-state-evidence-20261008. UI·workflow·LETF·병합·배포 변경 없음.

## 실제 연결

하원15곳·상원 보궐1석·주지사1곳을 점검했다. API 대상48건을 `2026-10-08T14:49:17.021601+00:00`에 수집했고 표시8관측(상원3·주지사4·하원09 참고1), 새 원문재검토7관측이다. 같은조사의상원/주지사결과를 독립기관2개로 세지 않는다. 기존Siena주지사1건은10/5요약수치검토/상세방법미확인을보존한다. 전국506슬롯/91관측(적격72·참고19), 전국전수원문확보를뜻하지않는다.

| 선거 | 현재 여론조사 연결 | 7일 기본 | 14일 선택 |
|---|---|---|---|
| 상원 보궐 | CNN/SSRS·Marist·Suffolk 3관측 | CNN/SSRS LV1기관, Brown49/Husted43 | LV2기관(CNN/Suffolk); MaristRV는LV와합산하지 않음 |
| 주지사 | CNN/SSRS·Marist·Suffolk·기존Siena 4관측 | CNN/SSRS LV1기관, Acton50/Ramaswamy42 | LV3기관(CNN/Suffolk/Siena); MaristRV별도보존 |
| 하원09 | DCCC 9/22–23, 481LV Kaptur48/Merrin48 | 최근적격없음 | 최근적격없음·내부조사참고전용 |
| 다른하원14곳 | API감시·후보명부연결은 유지, 통과관측없음 | 우세/0%/승자생성안함 | 동일 |

CNN [의뢰기사](https://www.cnn.com/2026/10/08/politics/cnn-polls-ohio-iowa-senate-governor-midterms)·[SSRS공식발표](https://ssrs.com/news/an-ohio-edge-and-iowa-tossup-heading-into-the-2026-election/)에서 직접연결한 [전체조사표](https://www.documentcloud.org/documents/28729016-cnn-ohio-poll-conducted-by-ssrs/)를확인했다. 9/29–10/5 등록유권자760명(RBS524/확률패널236)을모두유지해투표가능성으로가중한LV결과이다. 760명LV선별하위집단으로 설명하지 않는다. 문항은 초기선택과leaner합산이며 미정·기타응답을보존한다. 발표오차±4.5pp/95%/설계효과포함은원문기재값이고 후보차이유의성·당선확률은계산하지 않는다.

Marist [원문방법/전체표](https://maristpoll.marist.edu/wp-content/uploads/2026/09/Marist-Poll_OH-NOS-and-Tables_202609281347aC909p6465.pdf)는9/24–27 RV1298명, 전화213/문자858/온라인227, L2/Cint매칭·가중·설계효과1.93을대조했다. 상원51/43, 주지사50/44이다. 예상승자질문(상원50/47·주지사43/53)을투표의향으로쓰지 않는다. 주지사기타3/미정3/무응답<1도전체표에남긴다.

Suffolk [공식목록](https://www.suffolk.edu/academics/research-at-suffolk/political-research-center/polls/other-states)·[전체표](https://www.suffolk.edu/-/media/suffolk/documents/academics/research-at-suffolk/suprc/polls/other-states/2026/10_2_2026_ohio_statewide_complete_marginals.pdf?hash=F70867C91DB279D508E706D79D98CCAA446A720D&la=en)는9/23–27 LV500명, livephone/군별PPS·할당설계를확인했다. 주지사50.4/41.4/Kissick2.8, 상원Brown46.6/Husted44/Levy1/Redpath2이며 미정·거절·기입을분리했다. 상원은API48건에없어유한PDF보완목록에추가했다. 정확URL/원문SHA·PDF형식/3MB·메타데이터검사, 원문장애/변경시원래날짜참고이월, API후발동일파동의중복/충돌검사를유지한다. 새PDF전수발견기가아니다.

DCCC [원문](https://dccc.org/dccc-polling-memo-oh-09-is-a-dead-heat/)은정당내부조사·전화/text-to-web·±4.5pp/95%를명시한다. API internal=false와원문internal이라는불일치를원값과함께보존하고표시 internal=true로명시한다. 이정정은검토된동일레코드의참고전용승인에묶인다. 정당내부조사를최신우세집계에편입하거나일반신규내부조사를자동승인하지 않는다. 모집틀/가중/전체문항/LV선별미공개는quality에기재한다.

## 보류한 조사와 실제 장애

검토감사11레코드에발견·원값·보류이유를남긴다. OH01 Quantus기관페이지는응답200이지만실제질문/방법본문미확보, OH07 Tavern원문총635/API560의문항표본불일치 및 책임기관·의뢰자미확인, Bedrock/NOTUS재인용은원문방법미확보이다. OH15 HMP6월원문은초기40/45/Barrington3을기재하지만API표본550/방법없음;9월자료는X링크만확보했다. OH상원Quantus동적원문·Insider접근장애와 BigData Ohio기사방법본문Texas기재/주지사원표누락을보류한다. 방법확인실패를조사없음이나패배로바꾸지 않는다. 오래된/경선기간원자료는기존단계검사로제외하며일괄9/1하한을전체주에확대정정하지 않았다.

등록된 CNN/SSRS새API발표는기관·원문호스트·현재대진·의뢰자·날짜·표본검사를통과하면자동수집될수있다. 새원문재검토가없는새레코드의등급은부분검증이다. 새기관·공유호스트·API밖발표는자동검토완료를보장하지 않는다.

## 후보·외부지출

Ohio SOS [Directive2026-45](https://www.ohiosos.gov/assets/dir2026-45-form-of-the-official-ballot-for-the-november%203-general-election.pdf)에서상원본선4명과기입3명, 주지사표기3명(Acton/DEM·Ramaswamy/REP·DonKissick/LIB)과기입4팀을확인했다. 상원은1/3/2029종료임기보궐이라는기존contest_id를유지한다. 기입후보는정당이아닌WRI로분리하고단독·무투표승자로판정하지 않는다. 1·8구는 [Hamilton9/8인증명부](https://votehamiltoncountyohio.gov/wp-content/uploads/2026/09/November-2026-Certified-Candidate-Profile-and-Data.pdf)로보강;13구는현재공식사이트가연결한 [Summit9/1명부](https://www.boe.ohio.gov/summit/c/upload/Election_CandidateList.pdf)의SandeepDixit/Nonparty를기존검토대기에서연결했다. SUBJECTTO WITHDRAWAL과원래명부일을보존한다. 후속철회는별도검증이다. 의원/후보주소·연락처는공개JSON으로복사하지 않는다.

Vanessa Enoch의공식이름·secondary에기재된H8OH08097·같은8구/DEM의FEC ENOCH,VANESSAL.DR.를대조해금융신원1명추가(하원31→32연결)했다. 기존위원회가O범주관측없으므로SuperPAC지지/반대는null이며 신원을연결했다고새지출이생기지 않는다. 기존O누적관측은하원8/15·상원1/1, 주지사0/1이다. 경선/본선/미확인·O/U/V/W범주와후보캠프후원금을분리한다. 기존FEC15,955건·수집10/8·마지막포함신고10/6 및 원래finance기준일을그대로유지했다. 새FEC금액재수집없음.

주지사공식 [발견페이지](https://www.ohiosos.gov/elections/campaign-finance)는Simple/Advanced/FileTransfer를 [현재공시DataPortal](https://data.ohiosos.gov/portal/campaign-finance)에연결한다. 직접요청은403으로실패했다. 공개검색화면존재·후보일반지출은후보대상독립지출확보가아니다. 현재source_access_blocked와금액null을별도공개하고지출유형·후보타깃·지지/반대·정정·선거단계원자료없이는금액을만들지 않는다. 새API키/유료권한필요근거는확보하지 못했다.

## 검증·인수

- 최신 OH파일 `usa_election_state_evidence/2026/OH-be13dac18146728a.json` (약252KB), 감사 `usa_election_poll_release_reviews/2026/OH-primary-20261008.json`, 접근건강 `usa_governor_source_access/2026/OH.json`.
- polling238·금융58·연방명부6·JS51=353검사통과. 새11검사는실제선거유형/보궐·LV/RV분리·minor/미정·내부참고와원값·자동수집부분검증/의뢰자검사·PDF장애/변경/후발중복충돌·후보명부/기입·금융신원/금액null을검증한다.
- 타주489poll레이스·누적이력41레이스·49주index·기존금융/감사/접근/SuperPAC4,639파일·금융index·전역원래날짜·타주명부/신원목록을비교해보존했다. 미참조이번실행OH중간파일만제거하고이전커밋자료는보존한다.
- Draft #492에후속추가. 일일Actions PR #489는별도. workflow dispatch/병합/배포없음.

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state OH --as-of 2026-10-08
python3 refresh_governor_source_access.py --state OH
python3 refresh_state_evidence.py --state OH --as-of 2026-10-08
```

자동transport수집시각은수기원문검토시각을갱신하지않는다. 실제재검토7ID와감사경로를receipt에연결했다. 다음상태연결점검은WI/기존장애재시도GA→MI→OH이며OH공시403을완료로표시하지 않는다.
