# Claude UI handoff — US Macro Monitor (+ layout / news)

**Owner:** Claude Code (UI / deploy). **Cursor does not edit** `app.js`, `style.css`, `index.html`, `data.js`, `shipping.js`, `_worker.js`, workflows, ops.  
**Read this before deploy.** Data: `public/data/macro_monitor_v1.json` (`engine_version` ≥ `0.20.0`).  
Index: [`CLAUDE_UI_HANDOFF.md`](./CLAUDE_UI_HANDOFF.md).

Additive JSON fields — ignore unknown keys safely.

---

## A. Layout — country overlay too small (선빈)

국가 클릭 후 오버레이/스테이지가 **너무 작다**. 탭 + 칩 + 차트(+뉴스)가 들어갈 **면적을 크게** 잡을 것.

권장:
- Country stage/overlay: 뷰포트 대비 **높이 ≥ ~70–80%**, 너비 **≥ ~min(920px, 92vw)** (데스크톱)
- 탭 행 + 칩 그리드가 스크롤 없이 한 화면에 더 많이 보이게
- 차트 드로어는 오버레이 안에서 **좌:차트 / 우:뉴스** (아래 §B)
- 지도는 배경으로 유지하되, 오버레이가 콘텐츠를 가리지 않게 여유 마진
- 모바일: 오버레이 거의 full-bleed; 뉴스는 차트 **아래** 스택

---

## B. News beside indicator (API forthcoming)

지표 칩/차트 클릭 시 **차트 옆 사이드 패널**에 관련 최신 뉴스.

### Data contract (Cursor already stubs)
- Series/indicator optional: `news_query` (string), `news_tags` (string[])
- `news: null` in fixture — **절대 가짜 기사 배열을 fixture에 넣지 말 것**
- Worker later: `GET /api/macro-news?iso3=&series_id=` (또는 기존 프록시)  
  - 서버사이드 fetch + **KV/캐시** (쿼터·레이트리밋)
  - 검색 입력 = `news_query` / tags / country aliases
  - 응답 예: `{ items: [{ title, url, source, published_at, snippet? }], asof, disclaimer_ko }`

### UI
- Desktop: **chart column + news rail** (대략 62% / 38%)
- Empty state: “관련 뉴스 없음 / API 연결 대기” — 스피너만 돌리지 말 것
- 각 아이템: 제목 · **출처** · 시각 · 외부 링크
- Footer: “투자 권유 아님 · 뉴스 요약은 참고용”
- 로딩/에러 상태를 차트와 분리
- Mobile: news **below** chart

---

## C. Chart / chip behavior (existing US tuning)

### Line charts (default)
- Y numeric, X time; hover → **date + value** (+ crosshair 권장)
- `chart_type: "line"` when set

### Equity MA5
- Non-vol equities: overlay MA5 = **5-period on visible window**
- Use `history.*.ma5[]` if present; else compute client-side
- Skip VIX / fear gauges (`ma` absent or `higher_is: fear`)

### Inflation
- Line + when `components` present: BEA/BLS-style breakdown panel  
  `[{id,label_ko,contrib_pp,share}]`
- USA: CPI / Core CPI / Dallas trimmed mean + **one** BEI (`bei_10y`)
- Core PCE demoted (`ui.chip: false`); not headline

### GDP
- Composite `gdp`: chip **`display_chip`** = YoY left | QoQ right (**not SAAR**)
- Drawer top-right toggle **YoY | QoQ** via `modes` / `ui.dual`
- Hide `gdp_qoq_saar` on USA

### Fed UST (SOMA)
- One chip `fed_ust_holdings` — label shows SOMA / Fed B/S (not market yield)
- Chart `chart_type: "stack"`; buckets ≤1y / 1–5y / 5–10y / >10y; hover = bucket

### QRA
- `qra_issuance` — **클릭 기본 뷰 = `compare`** (전분 실적 · 직전 예측 · 당기 공시 그룹 바 + 표)
- 보조: `components` 만기별 바 (bills/coupons when present)
- 계약 상세: [`CLAUDE_UI_HANDOFF_FULL.md`](./CLAUDE_UI_HANDOFF_FULL.md) §1
- 데이터: `qra_engine_v1.json` + `--live` 오버레이

### FedWatch
- Label **`FedWatch`** (not cut-prob)
- Chip text = top outcome only e.g. `25bp 인상 57%`
- Bar over `outcomes[{label_ko,bp_change,prob}]`

### High Yield
- `hy_oas` label: **High Yield OAS**

### NFP
- Show `note_ko`: 신뢰도 낮음 / 개정 큼

### Meta badge
- Show `source` · `asof` · `refresh_tier` on chart header when present

### Limitations
- Render country `limitations` (already in pack)

### Hierarchy
- `benchmark` (USA) + `featured` kits: visual priority on map/list

---

## D. Cursor-recommended UI polish (for Claude)

1. **Larger country overlay** (§A) — highest priority UX  
2. **News side rail** (§B) — wire to Worker; empty until API live  
3. Hover **crosshair** + tooltip (date/value; stack = bucket)  
4. GDP **YoY|QoQ** toggle + dual chip  
5. Equity **MA5** overlay  
6. Stacked **Fed UST SOMA**; **QRA** / **FedWatch** bars  
7. Badge: source / asof / refresh_tier  
8. Limitations block accessible from country view  
9. Mobile: news below chart; overlay near full-screen  
10. Featured/benchmark hierarchy on map  
11. **No fake news** in static JSON  

---

## E. Smoke checklist
1. Country click → large overlay, tabs+chips usable  
2. USA SOMA one chip → stack hover buckets  
3. 3M/2Y/10Y lines; FedWatch bar+chip; High Yield label  
4. GDP dual chip + drawer toggle; NFP note  
5. CPI open → components; no bei_5y / no core_pce chip  
6. SPX + MA5  
7. QRA **compare** bar+table (prior actual / prior forecast / current); maturity components secondary  
8. News rail empty-state (no fabricated articles)  
9. Meta badge shows asof/source/tier when available  

## Out of scope for Cursor
Main dashboard UI/deploy. Refresh tiers: `REFRESH_TIERS.md`. News API implementation = Claude/Worker when keys ready.
