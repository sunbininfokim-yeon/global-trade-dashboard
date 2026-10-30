# 애리조나 AZ — 2026-10-09 05:00 예약 작업

WI 최종efbbcdfb/Draft #500/선거 GitHub validate SUCCESS·refresh SKIPPED와 깨끗한 checkout을 확인한 후 `codex/az-state-evidence-20261009` 별도 브랜치에서 AZ 한 주만 처리했다. 사용자의 최신 “이후 별도PR” 지시를 따라 #492에 추가하지 않는다. 의존 #500 → #499 → #498 → #492. 병합·배포·workflow dispatch·UI·LETF 편집 없음. NV06:00 예약을 유지하고 NV 작업은 시작하지 않았다.

실제 기준일은 UTC2026-10-08이며 KST2026-10-09 파일명과 구분한다. 수집PID/Actions를 확인했고 동시 선거 수집은 없었다. WI 부분 보강·원문·공시 장애를 보존했다.

## 후보와 선거 범위

하원9선거·주지사1선거이며 연방상원은2026 비선거이다. 현 공식 선거 페이지 https://azsos.gov/elections/election-information/2026-election-info 와 후보 포털 https://apps.arizona.vote/electioninfo/ 에 실제 접근해 모두HTTP403을 기록했다. 다른 잘못된/옛URL 접근실패와 별도이다. 접근 가능한 The Green Papers는 현재 명부를 확인한 보조 출처이며 공식 최종 인증을 대신하지 않는다. 기존 후보별 ID·별명·minor·write-in·명부 날짜/품질을 보존했고 이번 공식 전수 재검증 완료를 주장하지 않는다.

현재 하원1/6구는 양당 외 소수정당·write-in 후보도 주별 명부에 있다. 조사 양당 문항을 전체 후보가 없는 선거 또는 무투표 당선으로 바꾸지 않는다. 주지사 기존NGA 주요2명 대진은 모든소수/기입후보 완전명부가 아니다. TGP에는 Risa Lombardo(Green),Teri Ann Hourihan(No Labels) 및write-in이 추가로 발견되며 공식 인증과 당코드·신원 검토가 남아 이번에 자동 후보로 승격하지 않았다. TGP는7/21경선 일정 변경도 기록하지만 기존NGA8/4메타데이터는 공식 근거 검증 전 보존했다. 현재 본선후보확정과 원래명부의 일정오류 여부는 별도이다.

## 원문 조사 편입·보류

공개 VoteHub API24레코드를 실제 확인했다. 관측3건=기존주지사8월2건 원문재확인 + 새하원1구1건 원문보완이다. 후보가정·과거·당파·정보제공후·일반정당문항을 본선초기 후보대결로 바꾸지 않는다.

### FirstStrategic 하원1구

공개 원문 https://s3.documentcloud.org/documents/28722214/shahfeeley-poll-release.pdf 실제200/570218bytes/SHA4216fd9e9c49eaeedf211e9faface9f3ca7db0f418f8ce30a9d6cfaab6785318. 발행10/5, 조사10/1, Q1초기 Amish Shah44.4/Jay Feely41.6/미정14.0. 원문7쪽은 **등록유권자400 RV**, 유권자파일→text-to-web, 정당/연령/성별 투표율모형 가중, Q1응답무작위 순서를 명시한다. API는LV이므로원본 `us-202firaf458383`을 `primary_provider_population_conflict`로보류하고 특정원문RV보완 `primary-firststrategic-az-house01-rv-20261005`을연결했다. 모형가중이 LV선별검증은아니다.

발표오차5.4pp/95%,설계효과1.24/가중전4.9pp를 기록했다. 발표자의 승패차 오차·“statisticaltie”설명을 원문 주장으로 보존하지만 자체 유의성/당선확률을 계산하지 않는다. 유료의뢰자/응답률/모집확률 상세는미공개,기관정확도등급미평가. 특정발표 검토이며기관의 미래발표전체승인아님.

최근7일(10/2–8)은부족,14일(9/25–10/8)은RV 단일기관 참고 `single_poll_lead DEM`이다. 한조사수치상우세이며 승자/확정의석/통계적유의한우세아니다. LV와RV를 합치지않는다. 후발API에 같은RV파동이 들어오면표본·수치·의뢰자일치때한번만남기고 충돌때실패보존. PDF변경/장애는 원래10/1날짜를보존한참고이월. DocumentCloud도메인 전체 신규조사 자동승인아님.

### 주지사 기존8월2건

HighGround8/15–18 LV400,초기49.5/34.3와API반올림50/34,유권자파일·전화·연령/정당/성별/지역가중·GOP+8가정·발표오차4.9pp/95%설계효과미포함을 재확인했다. Noble8/10–13은 전체1040RV와923LV를구분,48/35, opt-in패널·선별·등록유권자및LV별가중·발표오차3.23pp를 재확인했다. 누적참고이며7/14현재우세에넣지않는다. 과거검토를현재자동정확도등급으로바꾸지않는다.

### 실제발견 보류·미확보

- ASU/BSP8/18–9/4 API LV/sample null. 기관Linktree가링크한공개Dropbox25쪽원문을실제다운로드했고 N1300/Latino700, Q8[Q1≠won'tvote]초기47/34/2/1/미정16 확인. 전체1300을조건부Q8문항N/LV N으로강제채우지않는다. 모집단·LV정의·문항별N·가중검증 부족을 `primary_population_sample_mapping_required`로보류한다. 숫자가없다/가짜라고판정하지않는다.
- HMP/Normington6/8–11 WI가아닌AZ06공식의뢰자페이지에서초기47/45와정보제공후52/44를구분했다. API500LV는해당공개원문에서검증못해 `primary_methodology_sample_not_obtained` 보류. 52/44를초기조사로수입하지않는다.
- AZ06 Ragnar3월자료는유료언론발견·의뢰자원문방법미확보,PPP2025자료는경선전과거보류. 일반DEM/REP문항을현재후보숫자로치환하지않는다. 유료경로를우회하거나구입하지않았다.
- Equis9/1–9 기관공개PDF발견:전체1214RV/Latino400RV/50%전화50%문자웹/보고오차3.2와4.9.49/43은LV결과지만LV문항N미공개이고설명+7과반올림수치차6을구분해야한다. 53%two-way는미정층비례배분값이다. 조건미확인이라discovery_only,현재관측으로입력하지않았다. 광고비추정도후보별공식독립지출로변환하지않는다.

## 독립지출·공시 장애

현재후보 O SuperPAC 지출관측 하원7/9·후보ID20 연결은기존공시 재사용이다. 새FEC금액재수집없음,기존공시일/정정/중복/O·U·V·W/경선·본선분리보존. 미관측08/09는0달러아니다. 상원비선거에슬롯을만들지않는다.

Arizona SOS Spotlight 공식공개API경로 https://spotlightv2.arizona.vote/Reporting/Api 를실제재시도했고HTTP403이다. 주별접근CLI에AZ를추가해재시도영수증 `source_access_blocked`, `financial_data_collected:false`, `candidate_amounts_available:false`를남겼다. 공개사양상키불필요와실제접근성공은다르다. 새API키로해결된다고추정하지않는다. 후보별지지/반대·거래정정매핑 미구현이며 주지사 금액null/원래유효자료보존. 후보캠프수입/일반비용/광고추정치를 주별IE로 바꾸지않는다.

## 산출·검증·후속

- `usa_election_state_evidence/2026/AZ-ca03a67cdc336e4e.json` / work_status `live_poll_sources_reviewed_finance_blocked`.
- `usa_election_poll_release_reviews/2026/AZ-primary-20261009.json`, `usa_governor_source_access/2026/AZ.json`.
- polling267·금융63·연방명부6·JS51=387 로컬검사. 신규7검사는API LV와원문 RV 분리,중복방지,7/14일단일기관/유의성미평가,과거주지사제외,ASU조건부표본/HMP정보제공후보류,원문변경·후발API충돌/중복,403≠0/상원비선거를검증한다.
- 타주496poll레이스·47누적이력·49주index·기존금융/감사4643파일및타주후보명부/날짜보존검사통과.

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state AZ --as-of 2026-10-08
python3 refresh_governor_source_access.py --state AZ
python3 refresh_state_evidence.py --state AZ --as-of 2026-10-08
```

남은것:공식본선명부접근/소수후보·일정검증,주지사거래API접근및정규화,AZ06조사방법·ASU문항표본/모집단검증. 이번예약은AZ한번처리후종료하고 다음NV는별도06:00예약에서진행한다.
