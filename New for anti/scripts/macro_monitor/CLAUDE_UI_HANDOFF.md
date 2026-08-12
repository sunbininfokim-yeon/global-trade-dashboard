# Claude UI handoff — Macro Monitor (index)

**Cursor** = 엔진·데이터 (`scripts/macro_monitor/**`, `public/data/macro_monitor_v1.json`, `qra_engine_v1.json`)  
**Claude** = UI/배포 (`app.js`, `style.css`, `index.html`, Worker…) — **UI만. 엔진 재구현 금지.**

정본: **[`CLAUDE_UI_HANDOFF_FULL.md`](./CLAUDE_UI_HANDOFF_FULL.md)**

스냅샷: `engine_version` **≥ 0.34.0** · `ui.claude_handoff` → 위 FULL 문서.

```bash
cd "New for anti/scripts/macro_monitor"
python3 build_macro_monitor.py --live   # 필요 시 QRA 오버레이
```

---

## 이번 머지 — Claude UI 할 일 (우선순)

| 우선 | 무엇 | JSON 계약 | UI |
|------|------|-----------|-----|
| **P0** | QRA 레이어 스택 | `qra_issuance.issuance_layers` | A 정태→B 통시→C 좌표. 기본 A1. [`ISSUANCE_LAYERS.md`](./ISSUANCE_LAYERS.md) |
| **P0** | 관료 헤더 | `countries[].officials` (19국) | 중앙은행 + 재정. `appointed` 표시. **중국만** `set[]`(당서기+장관/행장) |
| **P0** | 발전량·믹스 | growth `electricity_generation` · `ui.click_view=energy_mix` | 칩=TWh 라인 → 클릭 시 연료 비중 바 |
| **P0** | 미리보기 헤드라인 | `headlines[].role` 6슬롯 | 성장·기준금리·물가·S&P등급·환율·핵심 |
| **P0** | TGA | line + `maturity_*` secondary | 잔고 선 → 토글 시 QRA 만기 바/표 |
| **P1** | Fiscal Data 미국 | `dts_marketable_net` · `public_debt_outstanding` · `mts_*` | 바/선 + 표 |
| **P0** | 전 국가 지표 설명 | `limitations.kind=explainers` | 한계 문구 대신 설명 패널 (19국) |

한국 재정 = **재정경제부 구윤철** (금융위·기획예산처 아님).  
EMU 전력 = Ember **EU** 프록시.

---

## 기존 요청 (엔진 반영됨 → UI 연결만)

상세: FULL §2 · [`CLAUDE_UI_HANDOFF_US_TUNING.md`](./CLAUDE_UI_HANDOFF_US_TUNING.md)

- 국가 오버레이 확대 · 뉴스 레일(`news_query`, 가짜 기사 금지)
- 차트: 라인+크로스헤어, MA5, SOMA stack, FedWatch bar, limitations
- 원자재→growth · 노동 `reference` · 인도/금리 칩 순서 · CN B주 제외 · ISR만(이란 없음)
- CME FedWatch **스크래프 금지** · IndexErgo **복제 금지**

---

## Smoke

1. USA → liquidity → QRA → 비교 바/표 → 만기 토글  
2. 임의 국가 헤더 → 관료 2명(+임명일); 중국은 세트  
3. growth → 발전량 칩 → 클릭 믹스 바  
4. FedWatch 스크래프 경로 없음  

---

## Out of scope (Claude)

- `scripts/macro_monitor` 엔진·공식 파서 재작성  
- 이코노미21/네이버 문장 복제 · CME 스크래프  
- `climate_registry` / yield `app.js` 국가 하드코딩 (별 파이프라인)
