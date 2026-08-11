# Codex review — FreeSIS 신용·예탁·미수 (최종)

**Branch:** `cursor/macro-monitor-fix`  
**PR:** https://github.com/sunbininfokim-yeon/global-trade-dashboard/pull/36  
**Scope:** market microstructure · Volume Profile / D&S credit overlay only  
**Not in scope:** UI (`app.js` etc. = Claude-owned), KFA, shipping, elections

---

## 1. Read these files (in order)

| # | Path | Why |
|---|------|-----|
| 1 | `scripts/market_microstructure/CODEX_REVIEW_CREDIT.md` | this checklist |
| 2 | `scripts/market_microstructure/CLAUDE_CREDIT_TABLE.md` | UI table + scale rules |
| 3 | `scripts/market_microstructure/fetch_freesis_credit.py` | fetch + `components` / `ui_display` contract |
| 4 | `public/data/deposit_credit_v1.json` | sample snapshot (as_of 2026-08-06) |
| 5 | `scripts/market_microstructure/UI_DS_AND_VOLUME.md` §신용공여 오버레이 | Volume dual-Y + table fields |
| 6 | `scripts/market_microstructure/TABLES.md` §7 | numbers table |

Optional context (broader MM, not required for credit review):

- `scripts/market_microstructure/DISTORTION_SQUEEZE.md`
- `scripts/market_microstructure/GLOBAL_SPILLOVER.md`

---

## 2. Product intent (must hold)

Show **at which KOSPI price levels who bought/sold**, and **how much leverage retail used**.

| Keep in UI | Drop from default UI |
|------------|----------------------|
| 투자자예탁금 | 예탁증권담보융자 |
| 신용거래융자 (+ 유가/코스닥) | 신용거래대주 |
| 위탁매매미수금 | 광의 신용공여(융자+담보) |
| 반대매매금액 · 미수대비% | |

Reason: collateral loan is securities-backed cash withdrawal — weak link to KOSPI price-bin supply/demand. Raw fields may remain in JSON; `ui_display.exclude_keys` hides them.

---

## 3. Scale contract (must hold)

| Series | Magnitude | Display unit |
|--------|-----------|--------------|
| 예탁 | ~104조 | **조원** (`value_jo`) |
| 신용융자 | ~29조 | **조원** |
| 미수 | ~1조 | **억원** |
| 반대매매 | ~100억 | **억원** |

- Do **not** put 예탁+미수 absolute on one Y-axis (미수 disappears).
- Table: absolute + ratio columns (`credit_over_deposit_pct`, `uncollected_over_deposit_pct`, `forced_sale_pct`).
- Volume Profile **Y-right default:** `credit_over_deposit_pct`.
- Alt: `credit_loan_jo`.
- 미수·반대매매: separate small strip / card.

JSON guide: `deposit_credit.ui_display.scale_note_ko`.

---

## 4. Data rules

- Source: FreeSIS public only (no API key)
  - 증시자금추이 `STATSCU0100000060`
  - 신용공여 잔고 추이 `STATSCU0100000070`
- Market-wide aggregate only — **not** per-ticker / per-broker / per-account.
- No invented numbers; `quality=missing` when fetch fails.
- 반대매매 = market total vs 미수 (FreeSIS), not broker internal forced-liquidation blotter.

---

## 5. Review checklist

- [ ] `components[]` has no `collateral_loan` / `short_loan` / `credit_funds`
- [ ] `ui_display.exclude_keys` lists those three
- [ ] `value_jo` present on 예탁·신용 rows; stress rows prefer 억원
- [ ] `chart_y_right_default == credit_over_deposit_pct`
- [ ] `note_ko` states 담보 제외 + 시장 전체 only
- [ ] CLAUDE_CREDIT_TABLE matches `deposit_credit_v1.json` numbers
- [ ] UI_DS_AND_VOLUME §신용공여 matches contract (no 담보 in table)
- [ ] No target price / buy-sell opinion fields

---

## 6. Out of scope / known gaps

- Full `investor_price_levels_v1.json` may lag remote (large file); credit contract is owned by `deposit_credit_v1.json` + `fetch_freesis_credit.py`.
- `TABLES.md` other sections are broader MM snapshot, not credit-specific.
- Live FreeSIS rebuild needs network; sample JSON is frozen as_of 2026-08-06.
