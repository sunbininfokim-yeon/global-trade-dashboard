# 인수인계 2026-11-12 — claude → codex: PE/CR 엔진에 들어간 변경

사용자 지시("카드 중 없는 엔진은 너가 만들어")로 `New for anti/scripts/dart/` 를 직접 고쳤다.
11-11 인수인계(`2026-11-11-claude-to-codex-pecr-live.md`)의 문제 1~5에 대한 처리 내역이다.
기존 엄격(strict) 카드의 정의·키·테스트는 바꾸지 않았다. 253 테스트 통과(신규 18).

## 바뀐 것

| 파일 | 내용 |
|---|---|
| `dart_kfa/xbrl_notes.py` (신규) | OpenDART 원본 XBRL(`fnlttXbrl.xml`)에서 회사가 태그한 주석값 → `kfa-pe-cr-reviewed/1` 행. 키: `PPE_DEPRECIATION`, `INTANGIBLE_AMORTIZATION`, `interest`, `interest_income`. 규칙: FY 기간 정확 일치, 연결/별도 멤버, 그 외 차원은 합계 멤버 화이트리스트만, 같은 개념의 모든 컨텍스트 값이 같을 때만. 삼성전자 FY2025 수기 검토 묶음 3행을 정확히 재현(테스트). `evidence.document` 에 "자동 추출" 표기 — 수기 검토행과 구분된다. 수기 묶음이 있으면 수기가 우선(`merge_packs`). |
| `dart_kfa/pe_cr.py` | 공시계정 기준 카드를 **별도 키**로 추가: `ebitda_cf`, `ebitda_cf_margin`, `gross_debt_reported`, `net_debt_reported`, `net_debt_reported_to_ebitda`(strict EBITDA 우선), `interest_coverage_cash`, `ev_reported`, `ev_reported_to_ebitda`, `ev_reported_to_sales`, `per_basic`, `pbr_basic`. strict 카드에 값을 쓰지 않는다. |
| `dart_kfa/pe_cr_screen.py` | 연간 이력에 `interest_coverage_cash`, 신호 `interest_coverage_cash_under_1_3y`. SECTIONS 에 위 카드 키 추가(렌더러가 strict 가 비었을 때만 대체 표시). |
| `dart_kfa/entity_policy.py`, `pe_cr_industry.py` | KSIC 64992(지주회사)는 이름에 금융 업권 단어가 있을 때만 금융. HD한국조선해양 → `general` 키트. |
| `dart_kfa/pe_cr_dart_schedules.py` | `미상환잔액`/`미상환 잔액` 공백 무시 비교. |
| `config/pe_cr_inputs.json` | `payables` 에 `ifrs-full_TradeAndOtherCurrentPayablesToTradeSuppliers`; 공시계정 기준 카드용 입력 11개(`cf_*`, `borrowings_*`, `bonds_*`, `lease_*`). |

## 결과 (FY2025, 비금융 12개사)

strict 이자보상배율 1→11, strict EBITDA 1→11, EBIT 0→9, FCF/EBITDA 1→11, 순차입금(공시계정) 0→10,
EV 0→8. 삼성전자 EBITDA 90.53조 / ICR 72.0x (PE_CR_ENGINE.md 대조값과 일치).

## 남은 것 / 검토 부탁

- `ebitda_cf` 는 대기업에서 거의 안 나온다(단일재무제표 API 의 CF 에 상각 행이 없음). XBRL strict 가 대신 채운다.
- 매출채권 기초잔액 결측으로 CCC 5/12 — 회사별 태그 차이(`missing:opening_receivables`).
- 시장 입력: 주식수와 종가를 같은 보고서 기준일(현재 2026-06-30)로 맞춰 120일·기업행동 규칙을
  만족시켰다. 시세가 최대 한 분기 늦다. 더 최신 시세를 쓰려면 기업행동 확인 절차가 필요.
- `xbrl_notes` 의 화이트리스트(`TOTAL_MEMBERS`)와 개념 우선순위를 다른 업종(건설·조선 등) 원본으로 더 대조해 주면 좋다.
