# CO 공식 후보·여론조사·주 공시 수집 인수 — 2026-10-09

사용자의 다음 주 요청으로 B그룹 콜로라도 한 주를 처리했다. 브랜치 `codex/co-state-evidence-20261009`, 기반은 미병합 Draft PR #504의 `9bed30f9a750867237943832cc411f5631c66933`이다. #492의 Claude 배포 준비와 기존 후속 PR을 보존하고 별도 Draft PR로 제출한다. 병합·배포·workflow 실행과 화면 코드는 변경하지 않았다. 다음 새 주는 **VA(버지니아)**이며 이번에 시작하지 않았다.

## 공식 본선 명부

[CO SOS 공식 명부](https://www.sos.state.co.us/pubs/elections/vote/generalCandidates.html)는 9월4일 카운티 인증, 2026년11월3일 본선 자료다. 실제 HTML SHA256은 `ae01d8cf38421975662c9b80728372784e3cff80b5e4e234cc1633a712436df9`이다. 고정 열·회기·인증 문구·하원8구 전체·정당·기명후보·철회 표시를 검사하는 재사용 파서를 추가했다. 부지사와 주의회 상원/하원은 연방/주지사 집계에서 제외한다.

- 하원 **8구·38명**: 공식 후보명과 기존 검토 FEC ID를 명시적 별칭+같은 주/직위/지역구/정당으로 연결했다. 법적 이름과 공개 별칭의 검토 근거를 남겼으며 등록 후보를 새 본선 후보로 승격하지 않았다. CO06 `Patty McMahon`과 이전 `Patty McMahan`은 추가 신원 검증 없이 같은 ID라고 주장하지 않는다.
- 연방상원 **1석·9명**: Mark Baisley(REP)·John Hickenlooper(DEM) 외 소수정당과 기명후보3명을 보존했다. 기명후보는 WRI와 신고 정당을 별도로 기록한다. Hickenlooper의 기존 출마 상태도 유지했다.
- 주지사 **7명**: Victor Marx(REP)·Phil Weiser(DEM), Stephen T. Hamilton(CST), Eric Mulder(LIB), Jeff Peckman(OTH/Unity), Erik Underwood(APV), Greg Lopez(IND). 주요2명의 기존 ID를 보존했다. 본선 명부7명과 여론조사 비교 대상2명은 별개이며, CO의 명시적 비교 계약으로만 양자 조사를 허용한다. Alaska 등 타주 복수 주요 후보·독립 후보 비교 조건을 축소하지 않는다.

검토한 10개 선거에 모두 복수 후보가 있어 공식 명부상 무경쟁으로 판정한 곳은 없다. 명부 인증은 당선 결과 인증이 아니다. 일반 본선 기간은 공식6월30일 경선 다음날7월1일부터이고, 원문 후보가 인증 후보와 일치해야 한다. 지도용 `elections_board_v1.json`에서는 CO의 연방 표시 명부만 갱신했다.

## 실제 여론조사

공개 VoteHub API의 CO 대상은 **1건**이다. CO03의1월 Hurd–Alex Kelloff 조사는 지금 DEM 본선 후보 Dwayne L. Romero와 달라 보류하고 값을 새 후보에게 넘기지 않았다. API 밖의 검토된 원문2개를 추가해 **CO 표시2건, 적격0·참고2**다. 기존 우선 대상 CO05/08을 먼저 검토했다.

| 대상·원문 | 검증된 실제 응답 | 처리 |
|---|---|---|
| [CO05 GSG 메모](https://newspack-coloradosun.s3.amazonaws.com/wp-content/uploads/2026/07/CO-05-Polling-Memo-F07.24.26.pdf) |7/16–21,450LV, Killin44·Crank45·미정11|Killin 캠프 내부 조사임을 실제 캠프의 원문 소개와 대조. 참고 전용. 초기 응답만 사용. 후보 소개 후47/44/미정9는 제외. 전체 문항·순서·모드·가중·질문표본은 미확보|
| [CO08 McLaughlin 문항표](https://cdn.prod.website-files.com/6943653ee8791a8a352e27f7/6aadecdc9101b1b52f7aeec1_CO-08%20Toplines%20(9%3A17).pdf) |9/16–17,400LV, Rutinel46.3·Evans48·미정5.7|Enhancing American Competitiveness 옹호 의뢰. 참고 전용. Q8은 일반 정당투표/Q4·후보 호감도/Q6–7 뒤, 정책 프레이밍/Q10 이전. 실제 leaner 포함 수치를 보존하고46으로 반올림하지 않음|

CO08은 유선2.8%·휴대전화63.6%·문자33.6%, 영어90.4%·스페인어9.6%, 투표 의향 definitely92.7/very likely4.7/somewhat2.6 등을 확인했다. 공개 지리 분포를 완전한 가중 설계라고 주장하지 않는다. 발표 오차4.6/4.9pp와 실제 신뢰수준·정확도 등급은 별개다. 확인되지 않은 표본틀·전체 가중·LV 모형을 명시했다. 기관 수나 AAPOR 참여로 정확도 등급을 만들지 않았다.

CO05 메모의 Weiser44·Marx42는 **CO05 응답자만** 대상이라 주 전체 주지사 조사에서 제외했다. CPI655RV의 정책/호감도 조사도 검증된 후보간 본선 투표 의향으로 바꾸지 않았다. 이번 검색에서 **주 전체 주지사·연방상원 본선 조사 원문을 확보하지 못했다.** 모든 CO 선거의7일·14일 적격 기관 수는0이며 우세색·승자·의석 전망을 새로 만들지 않는다. 존재하지 않는다고 전수 단정하지 않는다.

## 반복 수집 범위

`refresh_state_polls.py`와 전국 수집기는 공개 API의 새 기록을 기존 기관·원문·후보·기간 계약으로 검사한다. 추가한 CO PDF2개는 **특정 URL·레코드·SHA256**만 재확인하며 shared CDN 도메인 전체를 허용하지 않는다. 실제 재수집에서2개 PDF 모두 동일 지문을 확인했다. 변경/장애 시 원래 검토일·수치를 참고 전용으로 보존하고, 후발 API의 동일 파동은 수치·표본·의뢰자·당파/내부 여부가 일치할 때만 중복 제거한다. 충돌은 마지막 유효 출력 보존으로 처리한다.

내부 조사의 raw `internal:true`를 사실대로 유지하면서 **정확한 원문 검토 지문과 참고 전용 계약**이 있을 때만 표시하도록 보호 조건을 추가했다. 미래 기관 발표·미등록 새 기사 전체를 자동 탐색하거나 승인하는 기능은 아니다. 새 API 키·유료 권한은 필요하지 않았다.

## 주지사 공개 공시 — 수집 성공, 금액 정규화 보류

[공식 TRACER 다운로드](https://tracer.sos.colorado.gov/PublicSite/DataDownload.aspx)의 2026 일반 지출 ZIP을 실제 수집했다. 공시 페이지 기준은 **10/8/2026 2:00 AM**(원문 시간대 미표기), 실제 **84,102행**, Independent Expenditure Committee 유형 **2,277행**이다. CP1252·고정28열·ZIP 파일명/크기·신고연도/날짜·금액·정정 플래그를 검증한다. 이 수는 주지사 대상 독립지출 건수가 아니다.

[공식 필드 설명](https://tracer.sos.colorado.gov/PublicSite/Resources/DownloadDataFileKey.pdf)에 따라 CandidateName은 **신고 후보 캠프 소유자**이고 독립지출 수혜 후보가 아니다. 일반 ZIP에는 지지/반대 및 대상 후보 열이 없어 **주지사 후보7명의 지지·반대액과 대상 건수는 null**이다. 캠프 비용을 슈퍼팩 금액으로 바꾸거나 설명문 이름 검색으로 나누지 않는다. 정정/원본 계보도 미검증 상태로 진단 수만 기록하고 합산하지 않는다. 전체 파일 마지막 신고일10/7은 주지사 독립지출 마지막 신고일이 아니다. 2025년·전체 양식·전체 선거 단계 관측을 주장하지 않는다.

48 Hour IE 공개 검색과 FIGHTING FOR COLORADO의7개 신고(확인 범위의 마지막6/29)는 접근 가능했다. 특정 신고자 부분 발견이며 전체7개 거래 정규화를 뜻하지 않는다. ViewReport/SSRS의 거래·후보·S/O·정정 연결은 아직 미구현이고6월 신고를 날짜만으로 본선에 옮기지 않았다. 문제는 새 키가 아니라 **보조 양식의 실제 대상/방향/거래 매핑 확보**다. 공개 세션 토큰·ViewState·원본 CSV·주소는 저장소에 넣지 않았다.

새 `refresh_governor_finance_audit.py --state CO` 경로는 재실행할 수 있고 실제 실행도 성공했다. 현재 Actions에 이 명령을 추가한 것은 아니므로 별도 주 공시 정기 수집 설치는 Claude의 후속이다. 기존 금액 파일과 연방 공시는 이번에 새로 수집하지 않았다.

## 기존 연방 지출 연결

하원 현재 후보 **21/38명 ID연결**, O범주 누적 관측 **4/8구(CO01·03·05·08)**. 상원 현재 후보 **2/9명 ID연결**, Hickenlooper에 관측이 있다. 후보별 상세 공백은 감사 JSON의 `unlinked_current_finance_candidates`에 이름·정당·보고ID로 남겼다. U 단일후보 IE·V/W hybrid와 O를 합치지 않는다. 후보 연결은 모든 후보·모든 지출 확보를 뜻하지 않으며 경선·본선·UNKNOWN을 구분한다. FEC 마지막 성공일 `2026-10-08T08:23:14.889991+00:00`과 전역 금융 기준일을 유지했다.

## 검증과 재실행

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state CO --as-of YYYY-MM-DD
python3 refresh_governor_finance_audit.py --state CO
python3 refresh_state_evidence.py --state CO --as-of YYYY-MM-DD
```

후속 수집의 실제 영수증이 이번 고정 원문 심화 검토를 소급 새 검토일로 바꾸지는 않는다. `state_captures.CO`와 각 레이스의 `as_of/fetched_at`, 공시 감사의 `captured_at/source_as_of_text`를 확인한다. 전국poll 날짜는10/8을 보존했고 CO 개별poll 날짜만10/9다. 오래된 전체48주 실행 로그를 새 수집처럼 덮지 않았다.

로컬 polling306·finance68·federal6·JS51, **431개 검사 통과** 및 금융 원본/지도 합계 검증 통과. 내부 조사 미래 파동/의뢰자 변경·원문 지문 변경·중복/충돌·초기/정보제공·지역구/주 전체 범위·후보 철회/기명/명부 누락·공시 변경/실패 보존을 검증했다. 과거 조사 시나리오 시각은 고정하되 최신 명부 fixture 조립 시각을 분리했다. 화면 코드는 건드리지 않고 JS의 published windows 비교 검사만 실제 주별 캡처 날짜를 사용하도록 수정했다.

타주 **496poll레이스·51누적이력·49주index**, **기존 금융/감사4,641파일**, 타주/타국 지도와 전역 날짜·금융index의 보존을 실제 대조했다. 자동 일정 변경·수동workflow dispatch·병합·배포는 없다. PR 병합 및 실제 운영 자동화/배포 여부는 별도 확인해야 한다.
