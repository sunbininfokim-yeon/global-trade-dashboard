# Claude handoff — derivatives P0 deployment wiring

## What Codex changed in the data-engine scope

- `market_microstructure/engine.py` now emits the additive canonical
  `distortion_squeeze` block inside `market_microstructure_v1.json`.
- `market_microstructure/us_scenarios.py` now emits
  `global_spillover` and `why_short_ko` in `us_kr_transmission_v1.json`.
- `build_deposit_credit.py` builds the separate market-wide
  `public/data/deposit_credit_v1.json` from FreeSIS, with Naver only as an
  explicitly labelled fallback.
- `fetch_kr_public_extras.py` now supplies FreeSIS deposit/credit,
  KOSPI investor net flow, LETF category/direction turnover and best-effort
  public short balance.  None of these fields imply customer positions.

## Claude-owned changes required for deployment

### 1. `.github/workflows/market_microstructure_daily.yml`

Before `US→KR L3`, add a **D&S + FreeSIS** step:

```yaml
- name: D&S + FreeSIS credit/deposit
  run: |
    python build_market_microstructure.py --live --source auto --print-stats
    python build_deposit_credit.py --print-stats
```

In `Commit snapshots`, add these exact output paths:

```text
New for anti/public/data/market_microstructure_v1.json
New for anti/public/data/deposit_credit_v1.json
New for anti/scripts/market_microstructure/MARKET_MICROSTRUCTURE.md
```

Keep `KRX_API: ${{ secrets.KRX_API }}` only on the derivatives-board step.
Set that GitHub Actions secret to a newly issued key; do not commit it or put
it in Cloudflare settings.  The previously pasted key must be revoked.

### 2. `app.js` volume-panel contract

Fetch `deposit_credit_v1.json` as a separate market-wide overlay.  Render
`deposit_credit.components` according to `deposit_credit.ui_display.groups`:

- cash/leverage values: 조원; stress values: 억원 and a separate small strip;
- right axis default: `credit_over_deposit_pct`;
- always show the scope badge: `시장 전체 · 종목별/주체별 포지션 아님`;
- never merge the overlay into a ticker's price-bin / investor volume data.

For Global Spillover, read `t.global_spillover` (not raw `t.channels` and
`t.evidence_us`) for the headline, channels, top edges and evidence cards.

## Acceptance checks

1. Manually dispatch the workflow with a fresh `KRX_API` GitHub Secret.
2. Confirm both new JSON files have `quality=observed` where the public source
   responded; `missing` must remain visible rather than be converted to zero.
3. Confirm D&S still renders during a refresh: old top-level fields and the
   new `distortion_squeeze` block coexist by design.
4. Confirm the volume overlay has no ticker/investor-position wording.
5. Confirm the spillover panel renders `global_spillover.evidence_us_top` and
   labels open30m as a return-bucket proxy, not option-OI validation.
