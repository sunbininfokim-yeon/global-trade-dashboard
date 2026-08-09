# Paste to Claude Code

Read and follow:

`New for anti/scripts/market_microstructure/CLAUDE_UI_HANDOFF.md` and `CLAUDE_UI_HANDOFF_DERIV_3PANEL.md`

## Goal
Wire market-microstructure + US→KR + derivatives + **investor×price levels** into the dashboard.
Engine/JSON on PR branch (real data only). Merge to `main` for daily cron.

## You own
- `New for anti/{app.js,style.css,index.html,data.js}` (and related UI)
- Merge path to `main` so `.github/workflows/market_microstructure_daily.yml` schedule runs
- Optional repo secret `KRX_API`
- `docs/ops/DATA_CADENCE.md` one-line for the new cron

## Do not
- Invent numbers when `quality=demo` / null / missing
- Label VIX alerts as put-OI
- Brand alerts “Leopold”
- Treat SOXL returns as options positioning
- Edit `scripts/market_microstructure/**` unless schema bug (hand back to Cursor)

## First UI surfaces
1. `us_kr_transmission_v1.json` → headline + downside heat + KR chips (000660 first)
2. `alert_levels_v1.json` → 관찰/주의/경계
3. `kospi_concentration_history_v1.json` → Conc lines
4. `derivatives_board_v1.json` → foreign boxes (empty OK) + US OI rule level
5. `ai_casino_brief_v1.json` / `market_microstructure_v1.json` → brief cards
6. `investor_price_levels_v1.json` → **실측만** · 시총상위 + 시총100위 내 고변동 · index levels + close_day tables + bins (`observed|missing`)

Always show `disclaimer_ko`. Not investment advice. Never invent numbers.
