# 네바다 NV — 2026-10-09 06:00 예약 작업

WI efbbcdfb/Draft#500과 AZ5232e411/Draft#501의 완료·선거검증SUCCESS/refreshSKIPPED 및 깨끗한 checkout을 확인한 뒤 별도 `codex/nv-state-evidence-20261009`에서 NV한주만 처리했다. 사용자 최신 “이후 별도PR” 지시를 따르며 기존 #492에 추가하지 않는다. 의존 #501→#500→#499→#498→#492. UI/workflow/LETF편집·병합·배포·workflow dispatch없음. 선거수집PID/Actions확인 후 중복수집없이진행했다. 타주원문·부분보강·출처장애와원래날짜보존. 실제UTC2026-10-08/KST10-09파일명을구분한다.

## 대상·명부

NV하원4선거·주지사1선거·연방상원2026비선거. 상원출마등록자·현직상원지지도질문을 이번상원선거/전망으로 만들지 않았다. 기존 공식/검토본선후보·별명·minor/당코드/명부날짜를유지한다.

공식2026선거페이지 https://www.nvsos.gov/sos/elections/election-information/2026-election-information 는HTTP200이지만1043byte Incapsula Request unsuccessful 보안차단본문이었다. 인증명부다운로드성공/전수재검증완료가아니다. The Green Papers 현페이지는보조확인만했다. NV03 Lee/O'Donnell 및NV04 Horsford/Whipple 감시를유지하되 명부에한명만있다는이유로 무투표당선/승자를생성하지않는다. 기존명부에소수후보가있고주지사조사에는Danielle Ford(NPP)가있으므로양당강제결과와다후보문항을구분한다.

## 실제여론조사

공개VoteHub API6주지사레코드를 실제확인했고 현재표시3건/원문검토3건을 연결했다. 하원API레코드0이며경합NV03/04를현재후보로검색했지만편입가능원문을확보하지못했다. 발견범위상미확보이며모든조사가존재하지않는다는판정이아니다. 오래된Lee/Horsford구도·확률모형·예측시장·후원금은2026투표의향으로수입하지않았다.

### Noble Predictive Insights9/22–26

기관발표10/6과직접링크한공개엑셀을다운로드해RV·LV·SampleSummary를대조했다. XLSX SHA c519dce9d26f6ee95ff8d91c02b1470c229690f990130ae983601814e1bf46fb. 원문모집단은온라인opt-in등록유권자800과선별된LV708이며,성별/지역/연령/정당/인종/교육/2024회상투표를voterfile·NevadaSOS·Census로가중했다.

- API RV800은Joe Lombardo38/Aaron Ford37/Danielle Ford7. RV원문과일치해수치그대로보존한다. 미정13/다른후보1/이중없음5를방법검토에보존한다.
- API에없는LV708은42/40/7,미정9/다른후보1/이중없음2. `primary-noble-nv-governor-lv-20261006` 특정원문보완으로연결했다. RV를LV로덮어쓰거나800을708문항N으로치환하지않는다.
- 보고오차RV3.46pp/LV3.68pp,모형상세·신뢰수준미공개는명시한다. 가중표의WeightedN합을문항별실제응답수로추정하지않는다. 초기투표의향과후보신뢰/직무평가/정책문항을구분한다.
- 같은파동RV/LV관측2개는기관하나이며선택기간집계는LV우선,두기관/두독립조사로세지않는다. 정치기관수·AAPOR참여를정확도등급으로만들지않는다.

### Emerson/KLAS9/5–8

공개발표와연결GoogleSheets의엑셀export를다운로드하여Topline Results의초기주지사문항을확인했다. LV680,전체초기Aaron44.157→API44.2/Joe42.046→42.0/Danielle2.438→2.4/미정11.358→11.4. 직무지지도·기사정수44/42와구분했다. ConsensusStrategies probability-voter-panel의MMStext-to-web와PureSpectrum패널,Aristotle full-name/ZIP매칭,인구/유권자파일가중,보고credibility interval3.7pp/95%를기록한다. 가중Frequency합을실제문항표본수로역산하지않았다.9/8조사는최근14일밖누적참고이다.

7일기본10/2–8에는부족,14일9/25–10/8에는Noble LV1기관 `single_poll_lead REP`이다. 한기관수치상우세이며 당선예측/확정의석/통계적유의성판정아니다. Emerson옛조사를현재기관수에포함하지않는다.

## 자동연결계약

기존주별API수집은유지한다. API누락LV엑셀은finite-reviewed-release와exactrecord/document SHA로만보완하고미래Noble발표를전체자동승인하지않는다. 추가엑셀허용호스트는기관보고서의단일HubSpot도메인이며HTTPS/인증정보없음/.xlsx/3MB이하/형식헤더/exactSHA/리다이렉트거부를검사한다. 임의엑셀/공유문서호스트자동허용아님. 실행시엑셀셀을추정전사하는스크레이퍼를설치한것이아니다.

후속API에같은LV파동이들어오면표본/수치/의뢰자일치때하나만남고충돌시실패하여마지막유효자료보존. 원문파일변경/접근실패때원래9/26날짜의참고전용으로이월한다. RV와LV의파동키는구분한다. 반복원문검사는정기수집기에서연결되지만새발표발견·검토전부를보장하지않는다.

## 슈퍼팩과주공시

기존FEC O 현재후보지출관측하원3/4·후보ID9개를보존했고새FEC금액재수집은하지않았다. 하원02미관측은0달러가아니다. O/U/V/W구분과후보별지지/반대·경선/본선·공시정정/중복·원래신고일을유지한다. 후보캠프수입을외부지출로바꾸지않는다.

기존NevadaSOS/AURORA공시검색경로 https://www.nvsos.gov/SOSCandidateServices/AnonymousAccess/CEFDSearchUU/Search.aspx 를실제재시도했다. HTTP200/1037byte본문은Request unsuccessful Incapsula보안차단이다. 단순200이면public_endpoint_reachable로보던접근검사를고쳐정확한차단표지를인식하고 `source_access_blocked`로기록했다. 재설정/보안우회없음. 현재거래조회·신고정정·후보대상지지/반대매핑을끝낸것이아니며주지사금액null이다. 공개사양과실제사용가능성은별도이며현재새API키가필요하다는근거없음.

## 산출·검증·후속

- `usa_election_state_evidence/2026/NV-971abb2e98395276.json`, work_status `live_poll_sources_reviewed_finance_blocked`.
- `usa_election_poll_release_reviews/2026/NV-primary-20261009.json`, `usa_governor_source_access/2026/NV.json`.
- polling275·금융63·연방명부6·JS51=395검사. 신규8검사는RV/LV수치/표본,기관파동중복,7/14일유의성미평가,Emerson소수점초기문항,엑셀허용범위/후발API중복·충돌,변경원문날짜보존,HTTP200차단≠금액성공,상원비선거·하원결측을검증한다.
- 타주501poll레이스·48누적이력·49주index·기존금융/감사4644파일과타주명부/원래날짜보존검사통과.

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state NV --as-of 2026-10-08
python3 refresh_governor_source_access.py --state NV
python3 refresh_state_evidence.py --state NV --as-of 2026-10-08
```

NV예약은한번처리후종료한다. 다음A순서는NC지만기존NC원문작업은c6472d1d및인수문서가있으므로후속때현재완료/변경상태먼저확인해야한다. 이번예약에서NC를재실행하지않았다. 남은것은하원실제조사원문확보,공식명부접근,주지사공시차단복구와거래매핑이다.
