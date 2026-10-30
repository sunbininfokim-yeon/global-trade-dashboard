# NH 후보·여론조사·공시 연결 검토 — 2026-10-09

사용자 지정 AL→NJ→NM→**NH** 순서의 마지막 주. NM #513 / 1e5721db에서 `codex/nh-evidence-20261009`와 `us-nh-state-evidence-20261009`로 분리했다. 이 문서는 수집·검토 결과이며 전국 완결이나 배포 완료를 뜻하지 않는다. UI/workflow/LETF/병합/배포/배포 dispatch는 변경·실행하지 않았다.

## 후보·선거 범위

하원2·상원1·주지사1의4선거, 보조 명부11명(하원5·상원3·주지사3)을 대조했다. [공식 선거 페이지](https://www.sos.nh.gov/2026-election-details)는403. 따라서 [Green Papers NH](https://www.thegreenpapers.com/G26/NH)와 기존 NGA 주요 후보 명부의 검토이며 공식 인증·전체 기명후보 완결·무투표 당선 확인으로 승격하지 않았다. 경선9/8 다음9/9부터 본선 비교. Class2 상원1석만 대상이며 Class3 Maggie Hassan의2028선거를 추가하지 않았다.

- NH01: DEM Stefany Amber Shaheen / REP Anthony DiLorenzo.
- NH02: DEM Maggie Goodlander / REP Lily Tang Williams / IND Robbie S. Mahrou.
- 상원: DEM Chris Pappas / REP John E. Sununu / CST Edmond J. “Ed” Laplante, Jr.
- 주지사: REP Kelly Ayotte / DEM Cinde Warmington / LIB Stephen Villee.

하원5명·상원3명 FEC ID 연결. Laplante의 공시 정당코드 RNC와 명부의 Constitution/CST를 각각 보존하며 REP로 바꾸지 않았다. Stephen Villee는 보조 명부의 지역 후보 ID이며 공시 거래 ID가 아니다. 주요 정당 후보만 조사에 제시됐더라도 제3당 지지율을0으로 채우지 않는다.

## 실제 조사와 판정

[YouGov의10/7발표](https://yougov.com/en-us/articles/55703-new-polls-in-seven-states-show-tight-races-for-senate-and-governor-in-each-including-leads-for-talarico-brown-and-acton)에서 연결된 [NH 전체 PDF](https://d3nkl3psvxxpe9.cloudfront.net/documents/ttw_nh_20260921_lv.pdf)12페이지의 수치·문항별 표본·방법을 확인했다. 파일명9/21을 조사일로 쓰지 않았다. 실제 조사9/28–10/5, 총1,520LV.

|선거|발표 수치|문항 표본|처리|
|---|---|---:|---|
|상원|Pappas51 / Sununu43 / 기타1 / 미정4 / 투표 안 함0|1,519|미정층 선호 재질문 배분값. 원문 관측을 보존하되 일반 우세 집계와 분리하는 참고 전용|
|주지사|Warmington40 / Ayotte49 / 기타0 / 미정11 / 투표 안 함1|1,520|배분 여부 원문 명시 없음. 7/14일 각1기관, REP 수치상 우세·단일 기관 참고|

등록 유권자 명부의 층화 추출→문자 초대→온라인 조사, 성별·연령·주내 지역·정당 등록·추정 교육·2024대선/과거상원 투표로 raking 가중. LV 모형은 과거 투표·인구특성·자기보고 투표 가능성을 사용. 가중치 범위<0.1~9.9/CV1.2. 보고±3.9pp는 전체1,520LV에 대한 기관 수치이며 검증된 정확도·유의성·상원1,519명 문항별 정밀도가 아니다. 미공개5문항이 있어 전체 문항 순서·후보 정보 노출 전 최초 문항이라고 단정하지 않았다.

API 미편입2관측을 정확한 PDF URL/지문에 한정해 추가했다. 새로운 YouGov 발표 전체·공유 CDN 호스트 전체를 승인하지 않는다. 같은 파동 API 후발 편입 때 표본·수치·의뢰자 일치만1건으로 병합, 충돌은 실패시켜 마지막 유효 자료 보존. 문서 변경/접근 실패 때 원래 날짜의 참고 자료로 이월한다. 전체 API39발견 레코드와 검토 근거는 `usa_election_poll_release_reviews/2026/NH-primary-20261009.json`에 있다.

NH01 UNH API의 `Stephany Shaheen`은 원문 초록의 `Stefany Shaheen`과 불일치한다. [UNH 발표 페이지](https://scholars.unh.edu/survey_center_polls/1005/)는 접근 가능하나 [전체 PDF](https://scholars.unh.edu/cgi/viewcontent.cgi?article=2004&context=survey_center_polls)는403으로 방법·수치 재검토를 못했다. 정확한 오류 레코드를 보류하고 원자료·이유를 감사 파일에 보존했다. 올바른 새 레코드는 검토 대진/등록 출처/날짜·표본 등 일반 검사를 통과하면 자동 편입될 수 있다. 기존 오류 ID의 수정은 재검토가 필요하다. NH02의9/17–21 UNH702LV Goodlander56/Williams35/Mahrou3은 부분 검증 누적 관측으로 보존하며 최근7/14일로 갱신하지 않았다.

상원4·주지사3·하원2구1, 총8관측을 보존했다. 원문 재검토 완료는 신규YouGov2개이고 나머지 기존6개는 API 부분 검증 수준이다. 적격7개 중 최근7/14일 관측은 주지사YouGov1개뿐이다. 상원 최신YouGov는 참고1개. [AARP/Saint Anselm 발표](https://www.aarp.org/pri/topics/voter-research/politics/2026-midterm-election-poll-new-hampshire/)는 발견했지만 원문403/상세방법 미확보로 편입하지 않았다. 주전체·50세 이상 부분표본을 혼합하지 않았다. 조사 미편입·기관 미등록·원문 장애·현재 기간 조사 없음은 별도로 남겼다.

## 독립지출·자동화 한계

하원2/2·상원1/1에서 현재 후보의 기존 연방 O범주 지지/반대 관측 연결을 확인했다. **FEC 금액을 새로 수집하지 않았다.** 기존10/8 원래 공시/수집 날짜·O/U/V/W·경선/본선/기타·정정/중복 계약 보존.

[NH 공식 CFS 공개 사이트](https://cfs.sos.nh.gov/)와 [공개 보고서 검색](https://cfs.sos.nh.gov/Public/ViewFiledReports)은403. 재실행 가능한 공개 사이트 접근 검사를 추가했으며 후보별 주지사 IE 수집기는 미완료다. 금액은null, 작업 상태는 `live_poll_sources_reviewed_finance_blocked`. 사이트 접근 검사를 공시 수집 성공으로 보고하지 않았다. 캠프 수입·일반 비용·직접 기부를 후보 대상 지지/반대 IE로 바꾸지 않는다. 새 API키/유료권한을 요구하는 출처는 발견하지 않았다.403을 키 부족으로 판단하지 않으며 로그인/신고/재설정은 사용하지 않았다.

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state NH --as-of YYYY-MM-DD
python3 refresh_governor_source_access.py --state NH
python3 refresh_state_evidence.py --state NH --as-of YYYY-MM-DD
```

두 번째 명령은 접근 장애를 기록하고 종료코드1을 반환한다. 마지막 명령은 공시 금액이 비어 있어도 부분 관측과 접근 장애를 함께 조인한다. 기존 API 경로는 다음 정상 조사를 반복 검사하고, 원문 보완은 검토한 동일 문서만 재확인한다. 새로운 비API발표 전수 발견·Actions 설치/일일 실행·화면 배포를 이번 PR에서 완료했다고 주장하지 않는다.

## 검증·인수

NH 회귀12개: 문항 표본·미정층 배분 참고 분리·제3당/미응답 보존·변경 레코드 보류·잘못된 이름 보류/다음 정상API 연결·보조 명부 출처/비선거석·CST/RNC·공유CDN 유한 승인·문서 변경 이월·후발 중복/충돌·공시null·동일 주 접근 기록을 검사한다. election_watch 전체477검사 통과. 금융 지도 계약·diff 검사·타주 보존 비교 통과. GitHub 검증은 PR 게시 후 별도 확인한다.

보존 비교: 타주502poll레이스·57누적이력·49주index·기존금융/공시/접근4,304파일(금융4,290·주지사금융5·접근9), 글로벌 여론조사 기준일·금융index·타주지도/국가·타주 수집/접근 기록 동일. 금융 지도 계약 검사 통과. 수정한 NH01 기존 오류 관측은 숨기기만 하는 대신 발견 원자료와 보류 근거를 별도 감사 파일에 보존했다.

사용자 지정 AL→NJ→NM→NH 검토 순서를 마쳤다. 공식 NH 명부 접근, NH01 전체 원문 검토, AARP 상세방법 확보, 주지사 IE 공시 매핑은 미완료로 인수한다. 다음 주를 임의로 시작하지 않는다. 병합·배포 보류 유지.
