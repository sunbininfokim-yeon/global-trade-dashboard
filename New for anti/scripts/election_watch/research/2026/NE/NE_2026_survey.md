# 네브래스카 2026 — 한 주 조사

확인일: 2026-10-20. 비교 기준은 로컬 작업 트리가 아니라 `origin/main` `4b3655d3`이다. 로컬 `main`은 그 커밋보다 뒤처져 있고, 이 조사는 브랜치를 바꾸지 않았다. 열린 PR 중 선거 조사를 맡은 것은 없었다. 그룹 순서에서 패킷이 없고 이미 병합된 조사 커밋도 없는 다음 주가 네브래스카였다.

UI, 공용 수집기, workflow, 전국 생성 JSON은 수정하지 않았다. 병합과 배포도 하지 않았다.

Cook 현재 등급에는 Toss-Up도 Lean도 없다. 우선순위 2의 현재 등급 조사는 비어 있고, 아래 여론조사는 우선순위 3으로 원문을 확인한 것이다. NE-02는 2026-10-09 레이스 페이지에서 Lean D에서 Likely D로 옮겨진 이력이 있다.

## 선거

| 직위 | 지역 | 구분 | 선거일 |
|---|---|---|---|
| 주지사·부지사 동반 출마 | 주 전체 | 본선 인증 명부 | 2026-11-03 |
| 연방 상원 | 주 전체, 임기 6년 | 본선 인증 명부 | 2026-11-03 |
| 연방 하원 | 1·2·3구, 임기 2년 | 본선 인증 명부 | 2026-11-03 |

경선일은 기존 카탈로그와 Cook 레이스 페이지가 2026-05-12로 적고 있다. 이번 인증 PDF는 본선 명부이며 경선 명부가 아니다.

공식 명부: [Final Statewide General Candidate List](https://sos.nebraska.gov/sites/default/files/doc/elections/2026/Final_Statewide_General_Candidate_Filing_List_9.11.26.pdf). 표지 날짜 9/11/2026, 1쪽. 인증 보도자료는 같은 날 Bob Evnen 명의 1쪽이다. 거리 주소와 전화는 원문 PDF에만 두고 여기에는 적지 않는다.

### 본선 명부 (PDF 1쪽)

상원: Pete Ricketts (Republican, 현직), Mike Marvin (Legal Marijuana NOW), Robin Richards (Nebraska Working People), Chuck Conboy (America First), Dan Osborn (By Petition).

하원 1구: Mike Flood (Republican, 현직), Chris Backemeyer (Democratic), Nik Sandman (Libertarian), Dan Hartong (America First).

하원 2구: Brinker Harding (Republican), Denise Powell (Democratic), Eric Michael Foreman (Libertarian).

하원 3구: Adrian Smith (Republican, 현직), Becky Kelly Stille (Democratic), David J. Else (Legal Marijuana NOW), Macey Budke (Nebraska Working People), Mark Cohen (By Petition).

주지사·부지사: Jim Pillen and Joe Kelly (Republican, 현직), Lynne Walz and Ben Steffen (Democratic), Rick Beard and Keenya Barnes (Legal Marijuana NOW), Brett Lindstrom and Michael Picard (America First).

## 1. 캠프 모금

주 공시 창구는 Nebraska Accountability and Disclosure Commission의 FirstTuesday다. 안내 페이지는 [NADC 공시 안내](https://nadc.nebraska.gov/view-campaign-filings-personal-financial-disclosures-potential-conflicts-lobbying-reports-and-more)이고, 위원회 조회는 `nadc-e.nebraska.gov`다.

2026-10-20에 그 호스트(`164.119.176.37`)로 직접 연결하면 25초 안에 타임아웃이 났다. Form B-1 PDF를 받지 못했다. 금액, 보고 기간, 신고일, 정정 여부, 개인 기부, 본인 출연, 대출, 이체는 비워 둔다. 0달러로 두지 않았다.

검색 엔진이 공식 위원회 페이지를 렌더한 결과에는 Pillen 위원회(조직 7688)와 Walz 위원회(조직 7640)가 보였다. 이 기계에서 그 HTML을 받지 못했으므로 위원회 ID는 미확인이다. 경선 기간 수입이 본선 후보 누적에 들어 있는지도 보고서 원문이 없어 미확인이다.

연방 후보 위원회 수입은 OpenFEC가 API 키를 요구한다. 환경에 `FEC_API_KEY`가 없어 그 경로는 멈췄다.

## 2. 여론조사

취합 사이트의 숫자는 넣지 않았다. 내려받은 원문만 적는다.

Cook를 2026-10-20에 브라우저로 확인했다. curl은 Cloudflare 확인 페이지에서 멈췄다.

| 선거 | 현재 등급 | 화면의 왼쪽 → 오른쪽 | 등급 시각 | 출처 |
|---|---|---|---|---|
| 상원 | Likely R | Solid R → Likely R | 2026-04-13 | [상원 레이스](https://www.cookpolitical.com/senate/race/488631) |
| 주지사 | Likely R | Solid R → Likely R | 2026-10-13 | [주지사 레이스](https://www.cookpolitical.com/governor/race/479541) |
| 하원 2구 | Likely D | Lean D → Likely D | 2026-10-09 | [NE-02 레이스](https://www.cookpolitical.com/house/race/483461) |
| 하원 1구 | Likely Republican | 차트 열 | 차트 날짜 2026-10-16 | [하원 등급표](https://www.cookpolitical.com/ratings/house-race-ratings) |
| 하원 3구 | Solid Republican | 차트 열 | 차트 날짜 2026-10-16 | 같은 등급표 |
| 하원 2구 재확인 | Likely Democrat (17) | 차트 열 | 2026-10-16 | 같은 등급표 |

후보 명단, 내러티브, 과거 득표 상세는 로그인 뒤다. 등급 위젯과 공개 등급표만 확인했다. 이 등급은 여론조사 행이 아니다.

### YouGov, 2026-09-24–10-03

원문 PDF 12쪽. 발표일은 PDF에 없다. 의뢰자 이름도 없다. 파일명 날짜 `20260921`은 조사 시작일 9월 24일과 다르므로 현장 기간으로 쓰지 않았다.

- 모집단: Nebraska likely voters 1,809. 유권자 명부에서 층화 무작위 추출, 문자 접촉 후 YouGov 웹 조사.
- 가중: 성별, 연령, 주 내 지역, 정당 등록, 추정 교육, 2024 대선 투표, 과거 상원 투표. raking. 예상 투표자 가중치 범위는 0.1 미만에서 9.5, 변동계수 1.0.
- 오차범위: ±3.3%포인트. 적용 대상은 1,809명. 신뢰수준은 적혀 있지 않다.
- 상원 문항은 요약 2쪽 6번, 교차표 8쪽 5번. 확정 투표자에게는 will, 그 밖에는 would. 미정에게 선호를 물어 배분했다고 적혀 있다. 배분 뒤에도 미정 3%가 남는다. Pete Ricketts (Republican) 47, Dan Osborn (Independent) 48, Someone else 0, Undecided 3, 이 선거에 투표하지 않음 1. 교차표 비가중 N은 1,808이다. 인증 명부의 5인 문항이 아니다.
- 주지사 문항은 요약 2쪽 9번, 교차표 11쪽 8번. 미정 배분 문장은 없다. Lynne Walz (Democrat) 43, Jim Pillen (Republican) 44, Someone else 2, Undecided 10, 투표하지 않음 1. 비가중 N 1,808. Beard·Lindstrom 이름이 없다.
- 하원 문항은 없다.
- 방법 12쪽은 보고하지 않은 문항이 다섯 개라고만 하고, 그 문항 원문은 추출되지 않았다.
- 상원 다음 7·8번은 이미 후보를 고른 사람에게 마음을 바꿀 수 있는지를 묻는 후속 문항이다. 초기 지지율과 섞지 않았다.

### co/efficient, 2026-09-28–30

기관 페이지 HTML. 별도의 발표일은 없다. 페이지는 후보 위원회, 정당 위원회, 독립지출의 의뢰가 아니라고 적는다.

- 1,113 likely general election voters. 휴대전화 문자와 유선전화.
- 가중: 연령, 성별, 인종, 교육, 하원 선거구, 지역 유형.
- 오차범위 ±2.92%포인트. 신뢰수준과 적용이 전체 표본인지 문항 응답인지 적혀 있지 않다.
- Q1은 트럼프 직무. Q2 주지사가 상원 후보 문항보다 앞이다.
- Q2 원문: “If the November 3rd general election for Governor of Nebraska were held today, who would you vote for?” Jim Pillen, Republican 43. Lynne Walz, Democrat 38. Brett Lidstorm, America First Party Nebraska 5. Rick Beard, Legal Marijuana Now Party 3. Undecided 10. 합계 99이고 맞추지 않았다.
- 인쇄된 `Brett Lidstorm`은 인증 명부의 Brett Lindstrom과 철자가 다르다. 같은 사람이라고 자동 연결하지 않는다.
- Q6은 5인 상원 초기 문항이다. Ricketts 45, Osborn 40, Marvin 2, Richards 1, Conboy 1, Undecided 11. Osborn 표기는 Nonpartisan이고 명부의 By Petition과 다르다.
- Q7은 그 뒤의 양자 문항이다. Ricketts 48, Osborn 43, Undecided 8. Q4–Q6 이후이므로 초기 문항이 아니다.
- 하원 문항은 없다.

### NPA Polling, 현장 2026-10-02–05, 메모 날짜 2026-10-12

3쪽 메모. 수신자는 Interested Parties이고 의뢰 기관은 없다. 문항 원문, 미정·기타의 명시, 가중 변수 목록, 설문지 순서가 없다. 편입 가능한 수치가 아니라 추가 검토다.

메모가 적은 범위는 다음과 같다.  Statewide likely voters. 기울어진 응답을 포함한다고 한다. 800명(전역 600과 NE-02 초과표본 200). 전역 결과는 800명을 가중하고 초과표본은 주 전체 비중으로 낮춘다. NE-02는 따로 가중하며 n=377. 오차범위는 95%에서 전역 ±4.0%포인트(600명 기준), NE-02 ±5.0%포인트(377명). 전역 오차범위를 800명에 적용하지 않는다.

- 상원 5인 문항으로 읽히는 문장: Ricketts 46, Osborn 43. 나머지 세 후보와 미정은 숫자가 없다. 46과 43의 나머지를 미정으로 채우지 않았다.
- 상원 양자: Ricketts 49, Osborn 46. 같은 이유로 나머지를 채우지 않았다.
- 주지사 4인: Pillen 44, Walz 40, Lindstrom 7, Beard 5.
- NE-02 3인: Powell 50, Harding 38, Foreman 6. 표본은 그 구 likely voters n=377.
- 같은 메모의 호감도, 일반 투표, 동기 문항은 초기 지지율이 아니다.

하원 1구·3구의 원문 조사는 이번 검색에서 확인하지 못했다. 조사가 없다는 뜻이 아니다. DDHQ에 올라온 Wedgewood 9월 중순 조사는 발견만 했고 원문을 받지 않아 숫자를 옮기지 않았다.

## 3. 독립지출

연방 Schedule E는 API 키가 없어 조회하지 않았다. 주 독립지출도 NADC에 연결되지 않아 지지·반대 금액이 없다. 없는 금액을 0으로 두지 않았다. 캠프 모금과 독립지출을 합치지 않았다.

## 기존 데이터와 다른 점

`origin/main`에는 `state_evidence/2026/NE.json`이 없다. 주 공시 출처 목록에도 NE가 없다. `usa_polls` 설정에서 `2026 Nebraska` 또는 `2026 NE-` 조사 원문은 찾지 못했다.

| 기존 기록 | 이번 원문 | 처리 |
|---|---|---|
| 주지사 Pillen·Walz만, NGA, 주 인증 아님 | 인증 명부에 티켓 4개와 부지사 이름 | 명부 정정은 편입 가능. 금액은 보류 |
| 상원 Ricketts(REP), Osborn(IND), 민주당 없음 | 민주당 후보 없음은 맞다. Osborn은 By Petition. Marvin, Richards, Conboy가 있다 | 편입 가능. IND를 명부 정당으로 단정하지 않음 |
| 하원 1·2구 Green Papers 명단은 인증 명부와 같은 사람 | Backemeyer의 기존 긴 이름, Sandman의 FEC ID 공백 | 이름 별칭은 추가 검토 |
| 하원 3구 Stille, Smith, Else | 인증 명부에 Budke, Cohen이 더 있다. Stille의 기존 중간 이름 Lynn은 PDF 1쪽에 없다 | 추가 인원은 편입 가능. 중간 이름은 별칭 검토 |
| 여론조사 없음 | YouGov, co/efficient, NPA 메모 | YouGov와 co/efficient는 결측을 명시한 채 검토 가능. NPA는 문항 원문이 없어 보류 |
| 모금·독립지출 없음 | 원문 미도달 | 변경 없음. 0 입력 금지 |

## 재수집 경로

| 자료 | 형식 | 접근 | 파싱 위치 | 자동화 |
|---|---|---|---|---|
| 본선 인증 명부 | PDF | 공개 URL. 이 네트워크는 DNS를 8.8.8.8으로 지정해야 했다 | 1쪽 표 | 가능. 표 추출 후 사람 확인 |
| 인증 보도자료 | PDF | 같은 사이트 | 1쪽 본문 | 날짜·인증 사실만 |
| NADC B-1 | HTML 뒤 PDF | 2026-10-20 연결 타임아웃 | 미확인 | 지금은 불가 |
| YouGov 교차표 | PDF | CloudFront 공개 파일 | 2쪽, 8쪽, 11쪽, 12쪽 | 이 파일만. 다음 발표 자동 승인 아님 |
| co/efficient | HTML | 기관 페이지 | Q2, Q6, Q7, Methodology | 이 페이지 구조가 유지될 때만 |
| NPA 메모 | PDF | 기관 미디어 경로 | 1–3쪽 | 메모는 문항 표가 아님 |
| Cook 등급 | HTML | 브라우저. curl은 확인 페이지 | 레이스 등급 위젯, 하원 등급표 열 | 등급만. 유료 본문 제외 |
| OpenFEC | API | 키 없음 | 멈춤 | 키 없이 진행하지 않음 |

## 편입과 보류

편입 가능한 것: 인증 PDF 1쪽의 본선 후보 이름·정당·현직 여부, Cook 등급 위젯과 2026-10-16 하원 등급표, YouGov와 co/efficient의 문항·표본·기간. 주 패킷으로 넣기 전에 기존 카탈로그의 `before_sha256`을 다시 계산해야 한다. 이번 파일은 그 패킷이 아니다.

추가 검토: NPA 메모, `Lidstorm` 표기, Osborn의 By Petition과 Independent/Nonpartisan 표기, 기존 FEC ID와 긴 이름, NADC 금액, 연방 독립지출.

결측은 미발견, 원문 접근 장애, 방법론 부족, 신원 불일치를 구분해 두었다. 승패나 0으로 채우지 않았다.

## Codex 편입 보완 (2026-10-20)

NPA 10/12는 메모 작성일이고 공개일은 미확인이다. 전체 인터뷰800·NE-02 인터뷰377로 필드명을 수정했다. API는10/13 레코드 날짜를 별도로 보존한다. 9/30·10/3·10/5 종료 조사는10/20 현재7일·14일 밖이며 누적 참고 자료로만 연결한다. 새 발표 전체를 자동 승인하지 않는다.
