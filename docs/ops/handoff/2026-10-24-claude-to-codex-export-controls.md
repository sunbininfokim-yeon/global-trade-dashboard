# 2026-10-24 Claude → Codex: 수출통제 모니터·미국 통상 자료 인수인계

수출통제 모니터(원자재 › 모니터링 › 수출통제 모니터, `/export_controls`)와 그 옆 미국
관세·제재 자료를 Codex 가 이어서 만질 때 알아야 할 것.

## 1. 화면 구조

- 코드: `New for anti/export-controls.js` + `export-controls.css` (`window.ExportControls`).
  app.js 와는 `exportControlsHost()` 어댑터로만 연결. 수출통제는 이 모니터에서만 보인다
  (무역 지도·국가 카드에 다시 붙이지 말 것 — CLAUDE.md).
- 탭: 「현행 조치」(수기 카탈로그, 국가별·품목별) / 「최근 공고」(규제기관 공고 자동 수집).
- 미국만 예외: 미국 클릭 시 「관세 정책 | 제재 | 일반 수출통제」 토글. 관세 정책은
  `us_tariffs_v1.json`, 제재는 `us_sanctions_v1.json`.
- 「시행 중」 아래 「제재 한시 허용 (OFAC 일반 면허)」 블록은 `us_sanctions_v1.json` 의
  `status: "time_limited_authorization"` 항목을 그대로 읽는다(현재 GL 135 러시아 경유,
  2027-04-07 만료). **관세 파일에 복제하지 말 것** — 한 기록을 두 화면이 읽는 구조.
- 지도 색: 금지 빨강 · 제한 주황 · 검토 노랑 · 기한 경과 회색 점선 · 미국 청록.

## 2. 데이터와 소유

| 파일 | 내용 | 고치는 쪽 |
|---|---|---|
| `public/data/export_controls/{manifest,agri,energy,minerals}.json` | 현행 조치 카탈로그 24행. 한 파일로 합치지 말 것 | Claude (Cursor 주간 확인 → Claude 반영) |
| `public/data/trade_policy/us_tariffs_v1.json` | 미국 관세 조치·국가별 세율·법적 수단 (시뮬레이터와 공유는 아직 안 됨 — 6절) | Codex |
| `public/data/trade_policy/us_sanctions_v1.json` | 4개국 제재·한시 허용·기업 대조 | Codex |
| `public/data/trade_policy/country_announcements_v1.json` | 국가별 통상 발표 | Codex |
| `public/data/commodity_reports_v1.json` 의 `boards.export_controls` | 「최근 공고」 (4시간 주기 수집) | 파이프라인 `scripts/commodity_reports` |

검증: `cd "New for anti/scripts" && python3 -m export_controls.validate` (카탈로그),
`python3 -m unittest discover -s export_controls/tests -t .`.

## 3. 「최근 공고」 수집원 (7개국)

미국 OFAC·BIS, 중국 상무부 수출통제국, 러시아 정부 결정문(`вывоз|экспорт`만), 인도 DGFT
고시 표(`html_table`), 인도네시아 무역부(`board_title_re` 로 수출금지·쿼터·수출세·DMO만),
아르헨티나 관보(수출세·수출금지·DJVE만). 모두 `board_only` 또는 제목 필터.

- 2026-10-20 수정: 이월 항목이 `board_title_re` 를 건너뛰던 버그(#640). 이월 경로도
  `_board_for()` 를 쓴다. 새 소스를 붙일 때 같은 경로를 탄다.
- 기술 통제(반도체·드론·쉴드기 등)는 공고 탭에만 남고 카탈로그 후보에서 빠진다.

## 4. 주간 순환

- 월 11:00 KST GitHub Actions → 결과표 PR `cursor/export-controls-weekly-survey`
  (기한·링크·공고 후보). 카탈로그는 자동 수정 안 함.
- 월 12:00 KST Cursor 원문 확인 → `surveys/review/<주>.md` PR.
- Claude 가 팩트체크 후 카탈로그 반영·배포. 규칙: `docs/ops/handoff/2026-10-04-claude-export-controls-research-for-cursor.md`
  (법적 근거 official / 사실상 조치 reported 두 층, 원문 없으면 high 금지).

## 5. 다가오는 기한 (Codex 자료와 겹침)

| 날짜 | 내용 | 영향 |
|---|---|---|
| 2026-10-31 | 러시아 생산자 경유 수출금지 연장 만료 (10-10 일부 해제 50만 t) | `rus-fuel-products` 재검토 |
| 2026-11-10 | 중국 희토류 확대 6건 유예 종료(공고 70/2025). 2027-01-10 연장은 상무부 해설뿐 | 연장 공고 없으면 단계 변경 검토. 미·중 휴전과 같은 날짜라 **us_tariffs 의 중국 휴전 항목도 같이 확인** |
| 2026-11-27 | 중국 갈륨·게르마늄·안티모니 대미 불허 유예 종료(공고 72/2025) | `chn-gallium` |
| 2027-01-10 | 미·중 휴전 연장 발표일(베선트 2026-09-24, 공식 문서 확인 필요) | us_tariffs 의 `sec301-china` |
| 2027-04-07 | OFAC GL 135 만료 | us_sanctions |

## 6. Codex 에게 부탁

1. **(미완료, 2026-10-24 Codex 확인으로 정정)** 시뮬레이터는 아직 `us_tariffs_v1.json` 을
   쓰지 않는다. `policy-simulator/policy-catalog.mjs` 에 별도 세율·계산 규칙이 있다.
   목표: 공용 자료에 HTS·원산지·발효일·중첩(stacking) 조건을 구조화해 넣고, 모니터와
   시뮬레이터가 그 하나를 함께 읽게 한다. 설명문(`rate_ko` 등)에서 숫자를 뽑아 계산하지
   말 것 — 계산은 구조화 필드로만.
2. 미국 조치를 바꾸면 `as_of` 와 해당 항목 `verification`·`verified_at` 을 같이 갱신.
   2차 자료만 있는 항목은 `primary_text_checked` 로 올리지 않는다.
3. 11-10 전후 미·중 휴전·희토류 유예가 바뀌면 Claude 에게 알려 줄 것 — 카탈로그
   `chn-rare-earths` 와 같은 날 맞춰야 한다.
4. 알려진 테스트 결함: `commodity_reports` 의 FederalRegister 날짜 테스트가 한국 시간에서
   하루 어긋남(UTC 에서는 통과). #484 계열 코드, 이번 작업과 무관.

## 7. 남은 일 (Claude 쪽)

- 언론 출처 행 7건을 정부 원문으로 교체(블룸버그·렉솔로지 등, 결과표 「자동 확인 불가」).
- 미확인 감시 쌍 265개 — Cursor 주 3쌍 점검.
