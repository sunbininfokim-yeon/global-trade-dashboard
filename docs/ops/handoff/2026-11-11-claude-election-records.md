# 2026-11-11 Claude → 선거 UI: 국가별 선거 기록 52개국 통합 반영

## 한 일
Cursor가 나라별로 올린 `cursor/*-election-records-2026-11` PR 52개(#927~#996 등)를 한 번에 반영했다.
개별 PR은 모두 공용 생성물 `public/data/election_records/index.json`을 같이 고쳐서, 하나를 병합하면 나머지가 충돌한다.
그래서 입력 `config/election_records/<iso3>.json` 52개를 각 PR 브랜치에서 그대로 가져오고, 빌더(`build_election_records.py`)를 **한 번만** 돌렸다.

- 입력은 Cursor가 쓴 그대로다. 숫자·날짜·출처는 고치지 않았다.
- 빌더 검증(형식·날짜·출처·투표율 범위·의석 합계)을 52개 모두 통과했고, `--check`도 통과한다.
- 독일은 연방하원 기록이 생겨서 `election-records.test.mjs`의 "연방하원 비어 있음" 단언을 고쳤다.
- 개별 Cursor PR은 이 통합 PR에 포함돼 중복이므로 닫는다.

## 선거 UI가 볼 만한 공백 (데이터로 직접 센 값)
54개국 중 입력이 없는 나라: **GBR, FRA** (쟁점 대상 10개국에도 들어 있다).

| 공백 | 나라 |
|---|---|
| 직위별 `coverage` 미기재 (요청서 2-3절 이전 제출분, 24개국) | ARG AUS BRA CAN CHL CHN COL DEU IDN IND IRN ISR ITA JPN KOR MEX MYS NGA PHL POL RUS SAU THA USA |
| 후보 한글명(`name_ko`) 없음 (사람 수) | KWT 50 · NGA 18 · POL 15 · COL 15 · CHL 12 · PHL 10 · BRA 9 · IRN 6 · KOR 5 · MEX 5 · IDN 3 · USA 2 |
| 의회 직위 자체가 없음 | IRN MEX PHL |
| 지방선거 직위가 없음 | 52개국 중 30개국 (예: ARE ARG ARM CHE CHL CHN COL DEU IDN IND …) |
| 기록이 하나도 없음 | ARE ARG CHN GEO HTI LBN PSE QAT SAU |
| 쟁점(`issues`)이 없는 쟁점 대상국 | BRA DEU ESP IND JPN KOR TWN USA (GBR·FRA는 입력 자체가 없음) |

직위 단위 `coverage`는 전체 135개 직위 중 `complete` 3 · `partial` 51 · `not_collected` 22이고, 나머지 59개는 미기재다.

## 해석 주의
- 기록이 없는 9개국은 이유가 서로 다르다. 입력의 `note_ko`·`coverage_note_ko`에 적힌 그대로다.
  - ARE·QAT·CHN·SAU: 국민이 직접 뽑는 전국 선거의 결과표가 없는 유형이다(ARE는 대통령을 연방최고회의가 뽑고, QAT 국왕은 선출 직책이 아니며, CHN·SAU는 유권자 투표 표가 없다).
  - ARG·GEO·HTI·LBN·PSE: 출처 파일을 이번에 열지 못했거나 열지 않아 비워 뒀다. 선거가 없다는 뜻이 아니다. 이 5개국은 후속 수집 대상이다.
- `coverage` 미기재 직위를 "수집 안 됨"으로 표시하지 않는다. 시도하지 않은 칸과 막힌 칸을 구분하는 것이 요청서 10번 규칙이다.
- 리비아(LBY) 입력은 2014년 대표원 선거와 2021년 12월 연기 발표만 담는다. 제안일(2022-01-24)을 다음 선거일로 넣지 않았다.
  같은 날 반영한 리비아 보드(UNSMIL S/2026/661)와 이름 표기가 서로 다르지 않은지 화면에서 확인해 달라.

## 화면에서 확인해 달라
이 세션은 지도·로그인 라이브러리를 막은 로컬 환경이라 국가 화면의 '선거' 블록을 실제 화면으로 하나하나 보지 못했다. JS 테스트(`js/elections/tests`)와 빌더 검증만 통과를 확인했다.
- 직위 `coverage`가 `not_collected`/`partial`일 때 안내 문구가 맞게 나오는지
- 기록이 하나도 없는 9개국에서 빈 카드가 어색하지 않은지
- `name_ko`가 없는 후보가 원문 표기만으로 나올 때 레이아웃이 깨지지 않는지(KWT 50명)
- 리비아 카드: 2014-06-25, 선거인 1,509,317, 투표율 빈칸, 다음 선거 빈칸

## 알려진 CI 상태
`US election polls`의 `validate`가 미시간(`refresh_state_evidence.py --state MI`)의 `ValueError`로 실패한다. 이 PR과 무관하며, 수정하지 않은 main에서도 같은 명령이 똑같이 실패한다. `election_watch/**`나 `js/elections/**`를 건드리는 PR이 전부 영향을 받는다. 선거 자료 담당이 별도로 확인해야 한다.
