# Claude UI handoff — Market Microstructure / US→KR

Cursor owns engine + `public/data/*` snapshots below.  
**Claude owns** dashboard UI / Worker / Actions ownership for merge to `main`.

**Branch:** `cursor/macro-monitor-fix`  
**Engine commit (cron + scripts):** `8d668ac`  
**Do not brand alerts “Leopold”** — scenario/channel names only.  
**Investment advice 아님** — 모든 패널에 `disclaimer_ko` 노출.

---

## 선빈 → Claude 요청 (UI만)

1. **미시구조 / AI Casino 브리프** 패널 — 집중도·레버 ETF·예탁/신용·수급
2. **US→KR early warning** — `headline` + 채널 heat + KR 타깃(하닉 우선)
3. **파생 보드** — 오늘 코스피200 외인 선물/콜/풋 박스 + US OI 룰 헤드라인
4. **Alert 레벨** — KR 하닉 LETF 비율 · US VIX→KR (풋 OI 히스토리 아님)
5. **Conc 시계열** — Conc_top2/5/10 라인

엔진·JSON은 Cursor가 유지. UI는 fetch만.

---

## Ops Claude must do (Cursor 금지 경로)

| 할 일 | 왜 |
|------|-----|
| 이 브랜치(또는 스냅샷)를 **`main`에 머지** | Actions **schedule는 default branch에서만** 돈다 |
| repo secret **`KRX_API`** (선택) | KR OI / 외인 파생 자동. 없으면 US·Conc만 갱신 |
| `docs/ops/DATA_CADENCE.md`에 cron 한 줄 추가 | `market_microstructure_daily.yml` · `30 7 * * 1-5` UTC (= 16:30 KST) |
| UI에서 `public/data/*.json` fetch | Worker 정적 assets = `New for anti` |

워크플로: `.github/workflows/market_microstructure_daily.yml`  
로컬 동일: `New for anti/scripts/market_microstructure/run_daily.sh`

---

## JSON 계약 (fetch 경로)

베이스: `./public/data/` 또는 배포 루트 `/public/data/` (기존 대시보드 패턴 따를 것).

| 파일 | 용도 | UI 핵심 필드 |
|------|------|-------------|
| `market_microstructure_v1.json` | KR 미시구조 당일 | `concentration`, `market_levered_etf`, `stocks`, `flows_kospi_market`, `deposit_credit`, `letf_category_share`, `short_interest_meta` |
| `ai_casino_brief_v1.json` | 브리프/헤드라인 카드 | `headlines`, `concentration`, `leverage_notional`, `disclaimer_ko` |
| `kospi_concentration_history_v1.json` | Conc 차트 | `points[]` · `latest.conc_top2_samsung_hynix_pct` · `stats` |
| `us_kr_transmission_v1.json` | US→KR 경보 | `headline` (예: `high:downside`) · `channels.{downside,upside,vol_up,vol_down}` · `drivers[]` · `kr_tickers` |
| `us_regime_v1.json` | US 레짐 상세 | 심볼별 regime |
| `us_microstructure_v1.json` | US 스냅 (옵션/숏) | watchlist 스냅 |
| `derivatives_board_v1.json` | 파생 보드 | `kr.investor_nets` · `kr.kospi200_options` · `us_kr_rules.headline_level` |
| `us_oi_daily_archive.jsonl` | US OI 히스토리(줄단위) | 차트 백엔드용; UI는 보드 JSON 우선 |
| `alert_levels_v1.json` | 관찰/주의/경계 | `kr_hynix_letf.today_level` · `today_ratio` · `us_vix_to_kr` |
| `validation_backtest_v1.json` | 내부 검증(선택 UI) | paper vs engine |
| `investor_price_levels_v1.json` | 코스피 시총상위 가격대×수급 | `market=KOSPI` · `tickers.*` · `bins_by_close` · `highlights` |
| `us_kr_hitrate_v1.json` 등 | L3 부속 | 고급/접기 패널 |

스키마 문서:
- `scripts/market_microstructure/README.md`
- `US_CROSS_MARKET.md`
- `DATA_SOURCES.md`
- `DERIVATIVES_BOARD.md` / `ALERT_LEVELS.md` / `US_KR_L3.md` (생성 메모)

---

## quality / missing 규칙 (반드시 지킬 것)

- `quality: demo` · `null` · `errors[]` → **가짜 숫자로 채우지 말 것.** “데이터 없음 / KRX 키 필요” 배지.
- **외인 콜/풋/선물 분리** (`investor_nets.futures|options_call|options_put`)는 현재 대부분 `null`.  
  UI 시드만 있는 것은 `options_total_seed_from_ui` (옵션 **전체**, quality=`demo`).
- **숏 잔고** `short_interest` 자주 `missing` (data.krx LOGOUT).
- **SOXL 수익률을 옵션 포지션으로 포장 금지** (엔진도 금지).
- Alert US 쪽은 **Cboe VIX 일변화**이지 풋 OI가 아님 → 라벨에 “풋 OI” 쓰지 말 것.
- 풋 매도 ≠ 하방. 하방 채널은 풋 매수 / P/C↑ / downside heat.

---

## 추천 UI 와이어 (최소)

```
[헤드라인] us_kr_transmission_v1.headline + channels.downside.heat
         → KR 타깃 chips: 000660 먼저, 그다음 005930

[Alert]   alert_levels_v1.kr_hynix_letf.today_level + today_ratio
         alert_levels_v1.us_vix_to_kr (레벨·VIX)

[Conc]    kospi_concentration_history_v1.points → line
         latest top2/5/10

[파생]    derivatives_board_v1
         - 외인 옵션 전체 시드 스파크 (demo 배지)
         - us_kr_rules.headline_level
         - call/put/fut 박스는 null이면 빈 슬롯 + “KRX_API/CSV”

[브리프]  ai_casino_brief_v1.headlines + concentration

[가격×수급] investor_price_levels_v1 (**KOSPI** 시총 상위 보통주)
         - tickers.{code}.highlights.close_bin.{retail,foreign,institution}.buy
         - bins_by_close 막대 · quality=estimated
```

Cursor 쪽 참고 캔버스(IDE only, 배포 아님):  
`~/.cursor/projects/.../canvases/derivatives-board.canvas.tsx`

---

## E2E 스냅샷 상태 (2026-08-08 로컬 최종런)

| 항목 | 값 |
|------|-----|
| Conc_top2 | ~46.3% (observed) |
| US→KR headline | `high:downside` |
| KR LETF alert | 관찰 (ratio ~0.09) |
| VIX alert | 관찰 |
| 파생 외인 콜/풋/선물 | missing / demo seed only |
| KR OI | missing (`KRX_API` unset in that run) |

공개 JSON은 이 핸드오프와 같이 브랜치에 커밋할 것(아래). cron 머지 후 Actions가 덮어씀.

---

## Cursor / Claude 경계

| Cursor | Claude |
|--------|--------|
| `scripts/market_microstructure/**` | `app.js` `style.css` `index.html` … |
| `public/data/*_v1.json` (위 목록) | `_worker.js` `wrangler.jsonc` |
| 모델 로직·품질 플래그 | `.github/workflows/**` 머지·시크릿·cadence 문서 |

질문·스키마 변경은 Cursor. 화면·배포는 Claude.
