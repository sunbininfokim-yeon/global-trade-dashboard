# 인수인계 2026-10-07 — claude (수출통제는 모니터에서만)

사용자 지시: "수출통제 모니터에서만 수출 통제 보여줄 생각이야. 그 외에서 수출통제가 보이지 않았으면 해."

## 바꾼 것

- **trade.js**
  - 무역 지도의 통제 색칠 레이어(`trade-export-controls`)와 범례(`renderTradeLegend`) 호출을 제거했다.
  - 국가 화면의 통제 카드(`ctl-card`)를 제거했다.
  - 중국 화면의 "중국 수출통제 공고 (원문)" 박스를 없앴다. `REPORT_BOARDS_BY_COUNTRY = {}`이고, 박스 코드는 남겨 두었으며 비어 있으면 아무것도 그리지 않는다.
- **app.js:** 품목 화면에서 통제 카탈로그 로드 후 지도를 다시 그리던 훅을 제거했다.
- **commodity_reports `sources.json`:** `cn_mofcom_aqygzj`를 `board_only`로 바꿨다. OFAC·BIS와 같이 수출통제 보드에만 들어가고, 품목 보고서 창(예: 희토류·중국)에는 안 뜬다.
- **CLAUDE.md:** 위 원칙을 명시했다.

## 그대로인 것

- `export-controls.js`의 `controlsFor` / `renderTradeLegend` / `FILL` / `LINE`: 모듈 API는 남겨 두었다. 지금은 모니터 밖에서 호출하는 곳이 없다.
- 수출통제 모니터 자체(현행 조치, 최근 공고): 변경 없다. 브라우저에서 정상 동작을 확인했다.
