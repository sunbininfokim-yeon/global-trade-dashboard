# Codex review — FreeSIS 신용·예탁·미수 (최종)

**Branch:** `cursor/macro-monitor-fix`  
**PR:** https://github.com/sunbininfokim-yeon/global-trade-dashboard/pull/36  
**HEAD tip after this pack:** see latest commit on branch  
**Scope:** market microstructure · Volume Profile / D&S credit overlay only  
**Not in scope:** UI (`app.js` = Claude-owned), KFA, shipping, elections

---

## Start here (read in order)

1. **This file** — checklist
2. `scripts/market_microstructure/CLAUDE_CREDIT_TABLE.md` — table + scale for UI
3. `scripts/market_microstructure/CREDIT_OVERLAY_UI.md` — dual-Y + field list
4. `scripts/market_microstructure/fetch_freesis_credit.py` — engine contract (`components`, `ui_display`)
5. `public/data/deposit_credit_v1.json` — sample (as_of 2026-08-06)

Supporting:

- `scripts/market_microstructure/TABLES.md` §7 (credit numbers)
- `scripts/market_microstructure/UI_DS_AND_VOLUME.md` (broader D&S/Volume; credit section may lag — prefer CREDIT_OVERLAY_UI.md)

---

## Product intent

Price-bin × who bought/sold + how much retail leverage.

| Keep in default UI | Exclude from default UI |
|--------------------|-------------------------|
| 투자자예탁금 | 예탁증권담보융자 |
| 신용거래융자 (+유가/코스닥) | 신용거래대주 |
| 위탁매매미수금 | 광의 신용공여(융자+담보) |
| 반대매매 · 미수대비% | |

Raw excluded keys may remain on JSON; hide via `ui_display.exclude_keys`.

---

## Scale

| Series | ~size | Display |
|--------|------:|---------|
| 예탁 | 104조 | 조원 |
| 신용 | 29조 | 조원 |
| 미수 | 1조 | 억원 |
| 반대매매 | 100억 | 억원 |

- No single Y-axis absolute for 예탁+미수.
- Table: absolute + ratios.
- Volume Y-right default: `credit_over_deposit_pct`.
- Stress: separate strip.

---

## Data rules

- FreeSIS public only (no API key): STATSCU0100000060 / 0070
- Market-wide only — not ticker / broker / account
- No invented numbers; quality=missing on fail
- 반대매매 = FreeSIS market vs 미수 (not internal blotter)

---

## Checklist

- [ ] `components[]` has no collateral_loan / short_loan / credit_funds
- [ ] `ui_display.exclude_keys` lists those three
- [ ] value_jo on 예탁·신용; stress prefers 억원
- [ ] chart_y_right_default == credit_over_deposit_pct
- [ ] note_ko: 담보 제외 + 시장 전체
- [ ] CLAUDE_CREDIT_TABLE numbers match deposit_credit_v1.json
- [ ] No price target / buy-sell opinion fields

---

## Gaps

- `investor_price_levels_v1.json` full file may not be on remote (size); credit contract is deposit_credit_v1 + fetch_freesis_credit.
- Live FreeSIS rebuild needs network; sample frozen 2026-08-06.
