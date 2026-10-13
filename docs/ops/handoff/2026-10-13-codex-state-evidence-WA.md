# 워싱턴(WA) 주별 입력 — 2026-10-13

사용자 NH 다음 주 요청에 따라 C그룹 WA 한 주를 처리한다. 다른 원본 선거 세션은 ME 담당이며 NE 중지는 유지한다. 담당 채팅 `01a11ee3-df39-77d2-a1d0-5201c358636e`, checkout `/Users/yeoninair/Documents/해운 데이터/us-wa-evidence-input-20261013`, branch `codex/wa-evidence-input-20261013`.

최신 main `fbca2775b6417348acab9877370a8e2ecec6d3ea`와 열린 PR/다른 세션/수집 상태를 확인했다. 공용 fixture·수집 경로에 필요한 #524의 `32fa4760ded80b83ed93c80d8d627c3231a9e92d`에서 독립 분기했으며 다른 주 PR 위에 쌓지 않았다. #529의 강화된 검사·세션 시작 규칙도 적용한다. 이 작업에서 드러난 공용 날짜 검사는 담당 세션의 별도 clock 기반에서 보강 중이다. 최종 base SHA·PR 의존성·검증 결과는 게시 전 아래에 갱신한다.

## 공식 명부와 선거 범위

[VoteWA GENERAL 2026 주 전체 목록](https://voter.votewa.gov/CandidateList.aspx?c=99&e=899)을 실제 요청해 확인했다. 선택값899(11/3 본선)/99(주 전체), U.S. Representative/Regular/2/Active, 하원10구·후보20명·각구2명과 순서를 검증했다. 빈 county=0과 특정 county=04 목록을 주 전체 명부로 오인하지 않는다. [SOS 8/21 인증 안내](https://www.sos.wa.gov/about-office/news/2026/secretary-state-certifies-candidates-and-measures-november-general-election)와 대조했다. 현재 공식 Active 명부이며 향후 기명후보 등록·최종 선거결과 인증과 구분한다. 자동 무투표 당선/100% 득표/공식 승자를 생성하지 않는다.

|지역구|DEM|REP|
|---|---|---|
|01|Suzan DelBene|Mary Silva|
|02|Rick Larsen|Edwin H. Feller|
|03|Marie Gluesenkamp Perez|John Braun|
|04|John Duresky|Amanda McKinney|
|05|Carmela Conroy|Michael Baumgartner|
|06|Emily Randall|Teresa Fox|
|07|Pramila Jayapal|Nirav Sheth|
|08|Kim Schrier|Spencer Meline|
|09|Adam Smith|Doug Basler|
|10|Marilyn Strickland|Chris D. Chung|

올해 대상은 하원10곳이며 연방 상원·주지사는 비선거다. 상원2028/2030·주지사2028의 정기 선거를2026 본선으로 추가하지 않는다. 8/4 top-two 경선과8/5 이후 본선 비교를 분리한다. 해당 주 파서는 선거/주전체 선택·직위·10구/20명·상태가 달라지면 실패시켜 재검토를 요구하고 연락처를 결과에 남기지 않는다. 미래 같은 당 두 후보를 자동으로 다른 정당으로 바꾸지 않으며 새 정당/구조는 검토 전 보류한다.

## 여론조사

10/13 공개 API 실제 발견3건은 모두WA03이다. DHM/OPB9/17–27, LV543 조사1건을 원문14페이지의 방법·문항·표본·응답으로 재검토했다. [의뢰 매체 원문](https://www.opb.org/article/2026/10/01/gluesenkamp-perez-braun-southwest-washington-3rd-district/), [전체 PDF](https://www.opb.org/pdf/OPB%20Fall%202026%20Election%20Survey--Toplines%20(Washington%20Abridged)--September%202026_1790882419395.pdf).

- Q21 최초 투표의향: Perez44/Braun46/미정11, LV543.
- Q21–24 미정층 선호 배분 합산: Perez47/Braun48/미정5, LV543. **API47/48은 오기가 아니라 다른 문항 결과**다.
- RV600의 Q21은 Perez44/Braun43/미정13이며 LV와 섞지 않는다.

일반 우세 집계에는 검토한 Q21을 선택한다. 기존 정확한 API 스냅샷에만 기존 `provider_answer_correction` 경로를 사용하되, 근거에 오류 정정이 아닌 문항 선택 정규화임을 명시했다. 원래API47/48·선택44/46·전체 raw·문항별 값·문서 지문을 보존하며 동일 조사1건만 센다. 레코드/표본/의뢰자/날짜가 달라지면 기존 검토를 승계하지 않는다. 새로운 조사처럼 추가하거나 July 조사로 날짜를 바꾸지 않는다.

등록 유권자 명부에서 live 전화/문자 초대 웹으로 조사했다. 연령·성별·정당·지역·인종·소득·교육 quota, 투표 확실성 및 정당/연령/과거 투표 이력에 따른 LV 모델을 공개했다. 전체 가중 상세/응답률/정확도는 미확보이며 ±4.2pp/95%는 기관 보고값이다. 후보 호감도 문항이 Q21보다 앞서므로 완전 무자극 조사라고 주장하지 않는다. AAPOR/기관 수를 정확도 등급으로 바꾸지 않고 격차 유의성·당선확률을 생성하지 않는다.

9/27 종료이므로10/13 기준7일·14일 모두 기간 밖이다. 누적/과거 원문은 보존하되 최근 승패·지도 우세로 만들지 않는다. Emerson/NPI7/8–10은 정당 관련 의뢰·경선 전 가상 본선, Voter Sciences2025는 정파/표본 미확보로 보류했다. 나머지9구 API 기명조사 미확보는 실제 조사 전수 부재가 아니다. 전구의 공식 후보 이름/약칭과 발견 슬롯을 연결해 신규API조사가 출처·대진·기간·표본 검사를 통과하면 편입할 수 있다. 이 자동 편입은 원문 수치 재검토 완료·새 비API발표 자동 전수 발견과 다르다.

## 연방 독립지출

공식 이름과 [Green Papers의 동일 구·정당·정식 이름/명시 FEC ID](https://www.thegreenpapers.com/G26/WA), 기존 같은 레이스 공시 이름을20명 각각 대조했다. 별명/중간이름은7개 명시적 대응표로 검토했고 일반 퍼지 매칭은 추가하지 않았다. 후보 ID 출처를 공식 VoteWA가 제공했다고 표시하지 않는다.

WA09 Adam Smith / GP David Adam “Adam” Smith / 공시 SMITH, D. ADAM / H6WA09025의 연결을 보완해 현재 후보 ID19→20, 현재후보 O범주 관측 레이스9→10/10이다. 해당 기존 관측은 지지1,000센트이며 새로운 금액 수집/추정이 아니다.

연방 금융 마지막 성공10/9T15:43:33.129021Z·공시 기준일10/7을 유지했고 **FEC를 새로 수집하지 않았다.** 후보 캠프 수입과 후보 대상 독립지출, O/U/V/W, 경선/본선/미확인, 정정/중복은 원래 계약을 유지한다. 비선거인 주지사에2026 IE 레이스를 억지로 만들지 않으며, 기존WA C6 주별 지출을 연방 슈퍼팩으로 부르지 않는다. 새 키·유료 접근 권한 사용 없음.

## 입력·검증·인수

커밋 범위는 WA packet, WA 공식 목록 파서/테스트, WA 원문 감사, 이 인수 문서뿐이다. 공용 검토 목록에 임시 작성한 검토를32개 operation으로 동결했고 공용 목록4개를 원상복구했다. 전국JSON은 `/private/tmp/wa-state-evidence-20261013/preview/data`와 별도 validation 사본에서만 재생성했다. 원문 HTML/PDF·후보 연락처는 커밋하지 않았다.

```sh
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state WA --packet --as-of YYYY-MM-DD
python3 publish_state_packets.py --states WA --public /tmp/election-preview/data
python3 publish_packet_projections.py --public /tmp/election-preview/data
```

본 작업의 packet은 실제10/13 수집이다. 후속 재생성은 그 입력의 replay이며 새 수집 시각을 만들지 않는다. 재수집 때 현재 검토와 다른 후보/문항/원문은 자동 승인하지 않는다. 최종 공용 clock 기반 이전에는 전체 projection이 오래된 타주 검증일로 WA 새 검토일을 검사해 실패하므로 그 기반이 선행해야 한다. 날짜를 낮추거나 타주 원래 수집일을 높여 우회하지 않았다.

WA 회귀11개 통과: 공식 범위·경선/군부분집합 거절·주의회 제외·초기/배분/RV 분리·원래값 보존·기간 만료·변경 스냅샷 보류·미관측8구 신규 정상API 연결과 옛 후보 거절·비선거석·ID/금액/원래 금융일 보존. 선거JS51개·금융 지도 계약·deploy-chain39 연결 통과. 전체 및 GitHub 검증은 공용 clock 기반 반영 후 갱신한다.

보존 비교: 타주496poll레이스·65누적이력, 타주 영수증·전국 원래as_of/fetched_at·타주 지도/국가, 기존publicJSON5,208파일의 원본 byte 동일. `house_poll_focus`는 기존 규칙으로 재계산했으며 타주 항목은 그대로다. derived projection 검증일과 원래 수집일을 구분한다. main 병합·배포·production workflow dispatch·UI 변경 없음.

다음 현행 순서 OR→MT→IN→IL→KY. 이번 요청으로 다음 주를 자동 시작하지 않는다.
