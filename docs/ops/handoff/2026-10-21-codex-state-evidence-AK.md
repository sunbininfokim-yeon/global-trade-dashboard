# AK 최신 원문 조사 편입 — 2026-10-21 Codex

사용자 후속 보강 요청. 하원 경합 우선 발견 목록에서 API에 없는 실제 원문을 확인해 **알래스카 한 주**만 연결했다. 병합·배포 보류를 유지한다.

- checkout: `/Users/yeoninair/Documents/해운 데이터/us-ne-research-integration-20261020` (이전 #654를 모두 push한 뒤 순차 재사용; 타 세션 checkout 변경 없음)
- branch: `codex/ak-poll-evidence-20261021`
- packet 없는 공용 기반: #651 `codex/poll-capture-validation-recovery-20261020`; 시작 SHA `763ba363c06a22ec71b0ccb5d7f14c8ddbd4938f`
- 확인한 최신 main: `9bf900f67ae062c4ab03433db938ebb7291822d8`. 시작 main과 미국 election_watch/주별 규칙 파일 차이 없음. 미병합 다른 주 PR 위에 쌓지 않는다.
- #654는 발견·Cursor 대기열 공용 PR이며 이 주별 PR에 그 diff를 복사하지 않는다.
- 이 PR은 AK packet·AK 원문 검토 감사·AK 테스트·이 인수 문서만 수정한다. 전국 생성 JSON·공용 목록·수집 코드·TASKS·UI·workflow·LETF 수정 없음.

## 실제 신규 수집

2026-10-20 UTC(한국 10월 21일)에 공개 VoteHub API를 실제 조회했다. 전국 원자료 1,540행 중 AK 선거 대상은 39행이다. 이전 AK packet의 37행은 전부 존재하며 수치·날짜·메타데이터가 동일하다. 새 API 2행은 PPP 상원 `us-202pub53b72052`, ASR 주지사 `gov202ala7c90a5de`이며 개별 원문·문항 검토가 없어 계속 보류한다. 이를 승인하거나 0으로 대체하지 않았다.

- 원 API 수집 시각: `2026-10-20T23:05:13.375006+00:00`
- 원문 발표: <https://www.dataforprogress.org/blog/2026/10/20/every-statewide-race-in-alaska-is-close-as-7-in-10-voters-worry-about-affording-gas-and-food>
- 원문 표: <https://www.filesforprogress.org/datasets/2026/10/dfp_alaska_oct_2026.pdf>
- PDF SHA-256: `c7a753b09705ff2a44ae5c95b942a80b10a5a4e059cbe0b7f4fcc3a3c0c2d8b4`
- 발표문 `datePublished`: `2026-10-20T13:54:18-0400`; 발표문이 해당 PDF를 직접 링크함을 확인했다.
- 조사기간: 2026-10-08~16; Alaska LV 전체 694; SMS+웹 패널, 영어; 나이·성별·교육·인종·지역·과거 투표 가중.
- 한 파동을 `ak-dfp-20261008-20261016`로 식별한다. **새 조사 1파동 / 3개 선거 연결 / 9개 문항 관측**이다. 9개 독립 조사 또는 9개 기관으로 세지 않는다.

API·PDF·발표문은 실제로 새로 받았고, 기존 Quantus 파일을 포함한 AK 원문 보완 10개 항목의 문서 지문을 재확인했다. 아래 비게시 재생은 이 수집 입력을 다시 사용하는 오프라인 검증이며 또 다른 신규 수집이 아니다.

## 원문 표 확인

PDF 1쪽의 방법론과 11~14쪽 Topline 열을 직접 렌더링·대조했다. 후보 이름은 기존 공식 명부에 검토된 동일 신원으로 연결하고 원문 역순 성명·공동 티켓 표시는 출처에서 확인했다. 현직 Dan S. Sullivan과 Daniel J. Sullivan Jr.를 합치지 않는다. Bill Hill은 IND이다.

| 선거 | 첫 선호 | 게시된 2후보 모의 | 별도 소진표 재배분 가정 |
|---|---|---|---|
| 주지사 | Q10, N694: JKT46 / Wilson28 / Bronson12 / Taylor9, 미정5 | Q13, N629: JKT53 / Wilson47 | Q14, N660: 50 / 50 |
| 상원 | Q15, N694: Peltola47 / Dan Sullivan44 / Daniel Sullivan Jr.4 / Heikes1, 미정3 | Q18, N671: Peltola51 / Dan Sullivan49 | Q19, N675: 50 / 50 |
| 하원 전역구 | Q20, N694: Begich48 / Hill42 / Hafner5 / McDermott1, 미정4 | Q23, N659: Begich51 / Hill49 | Q24, N668: 50 / 50 |

Q13은 게시된 제거 경로이고 Q14가 명시적 소진표 재배분 가정이다. Q12 표에 50%가 보이지만 반올림된 수치이므로 정확한 과반 여부를 추정하지 않는다. Senate Q15는 미정까지 합해 반올림 합계99이며 100으로 재정규화하지 않는다. 중간 3/4후보 제거 단계 Q11·12·16·17·21·22를 독립 조사로 추가하지 않았다.

최종 모의·가정 N은 각 표의 Weighted N이며 전체 694로 바꾸지 않는다. 전체 조사 공표 오차 ±4를 최종 라운드 오차나 실제 예측 정확도로 적용하지 않는다. 외부 의뢰자·정확한 모집 프레임·신뢰수준·역사적 정확도는 미확인 상태다.

## 자동 경로와 관측 한계

AK packet은 기존 `primary_supplements_2026.json`·`quality_reviews_2026.json` overlay 경로로 로드된다. 원문 재확인 → `normalize` → 기존 observation/UI 계약을 그대로 사용한다. 기존 일일 Actions의 수집·게시 코드나 기관 전체 허용 도메인을 바꾸지 않는다.

동일 파동의 문항은 정확한 ID·문항별 값·표본 지문으로 분리한다. 뒤늦은 API의 동일 문항은 한 번만 유지하고 다른 라운드는 별도 문항으로 보존한다. 값·표본·의뢰자 충돌은 #651의 격리 경로에서 원자료를 영수증에 보관하고 참고 상태로 유지한다. 문서 변경/장애는 원래 수치·기간·검토일을 보존한 참고 상태다. 새 PDF나 새 파동까지 통째로 자동 승인하지 않는다.

**RCV 문항은 기존 계약대로 일반 7/14일 DEM/GOP 우세·확정 승자·지도색 집계에 포함하지 않는다.** 화면에서 볼 원문 수치는 연결되지만 보통 투표의 2후보 지지율로 바꾸지 않는다. 각 선거의 최근 참고 문항3개는 같은 기관·같은 파동의 문항3개이며 독립 조사3개가 아니다. `ballot_question.wave_id`와 원문 문항 번호를 후속 UI 그룹 표시에 사용할 수 있다. UI는 이번 PR 범위가 아니다.

공식 AK 투표용지 재접근은 `URLError`였다. 기존 2026-10-09 공식 명부 검토를 보존하며 오늘 명부를 재인증했다고 쓰지 않는다. 연방 FEC·주지사 주별 IE는 새로 수집하지 않았고 이전 자금·신원 자료를 보존했다. 추가 API 키는 사용하지 않았다.

## 보존·검증

- 기존 AK config operation19개는 값·순서까지 동일하다. 새로 승인한 개별 문항의 operation만 뒤에 추가했다.
- 기존 2026-10-09 수집 영수증은 `prior_capture_receipt`에 보존했다. 기존 Quantus의 `original_reviewed_on=2026-10-09`, 조사종료일2026-09-30을 유지한다.
- `/private/tmp/poll-ak-20261021/replay`에만 전국 live/history 사본을 재생성했다. 다른 503개 선거·다른 주 영수증·이력은 동일하고, 하원 우선104곳의 ID도 동일하다. AK 표시 관측은6→15(추가9문항)이며 일반 적격 집계는 늘리지 않는다.
- 재생성 재실행의 live/history 바이트 동일성 확인. 이 재생을 사이트 반영 또는 신규 수집으로 부르지 않는다.
- AK 관련25개, 자금77개, 선거 JS114개, 소유권14개, deploy-chain42 workflow 검사를 통과했다. 최신 최종 통합 결과는 아래에 덧붙인다.

전체 polling 검사에서 공용 `test_poll_state_inputs`가 packet의 실제 날짜 대신 10월11일을 ‘더 최신’이라고 가정하는 문제를 발견했다. 해당 수정은 이 주별 PR에 넣지 않고 #651 공용 기반에서 처리한다. 초기 AK 신규 테스트의 충돌 자료 위치 검증도 실제 계약인 `conflicting_provider_records` 영수증을 검사하도록 바로잡았다. 원자료 보존 검증을 없애지 않았다.

## 인수와 순서

#651 공용 검증 복구 후 이 AK 독립 PR을 검토한다. #654 발견/대기열과는 주별 파일 충돌이 없다. 병합·배포·운영 workflow dispatch는 실행하지 않는다. 다음 주 작업은 시작하지 않았다. TX-09 Hobby 공개 원문을 발견했으나 이번 PR에 타주 데이터를 넣지 않았다.
