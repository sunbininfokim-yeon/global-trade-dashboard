# UI 스펙 — D&S + Volume Profile

Claude UI 전용. 엔진 JSON만 fetch. **가짜 숫자 금지.**

---

## 0. “라이브 재빌드”가 뭐냐

로컬/서버에서 아래를 실행하는 것:

```bash
cd New for anti/scripts/market_microstructure
python build_market_microstructure.py --live --source auto --fx 1400
```

하는 일:
1. KRX API(있으면) 또는 FinanceDataReader로 **당일** 시총·ETF AUM·거래대금·수급 수집
2. Yahoo(HK 7709 등) + Binance(perp) 외부 베뉴 수집
3. `engine.build_snapshot` → `public/data/market_microstructure_v1.json` 덮어쓰기
4. `ai_casino_brief_v1.json`, `TABLES.md` 갱신

**안 하는 일:** UI 코드 수정, 옵션 장부 생성, 공매 가짜 채우기.

fixture만 쓰면 옛 날짜(데모)가 나옴. 라이브를 돌려야 `by_direction`·최신 turnover가 JSON에 반영됨.  
이 환경에 `KRX_API` / 네트워크 의존성이 있으면 Grok 샌드박스에서 실패할 수 있음 → 그때는 로컬/CI에서 돌리면 됨.

---

## 1. Distortion & Squeeze 화면 스펙

**JSON:** `market_microstructure_v1.json` → `distortion_squeeze`  
(없으면 fallback: `concentration` + `stocks` + `letf_category_share`)

### 레이아웃 (위에서 아래)

```
┌─────────────────────────────────────────────────────────┐
│ A. 헤더                                                  │
│  수급 불균형 모니터링 · as_of · disclaimer 한 줄          │
│  [데이터 한계 배지] short=missing · options=limited …   │
└─────────────────────────────────────────────────────────┘
┌──────────────┬──────────────┬──────────────┐
│ B1 Conc_top2 │ B2 Top5      │ B3 Top10     │  ← concentration
│  46.3%       │  53.2%       │  60.1%       │
│  삼전+하닉   │  tickers 칩  │  tickers 칩  │
└──────────────┴──────────────┴──────────────┘
┌──────────────┬──────────────┬──────────────┐
│ C1 레버 AUM  │ C2 외인 vs   │ C3 예탁/신용 │
│  $XXbn       │  개인 순매수 │  신용/예탁%  │
└──────────────┴──────────────┴──────────────┘
┌─ D. by_direction (곱버스) ─────────────────────────────┐
│  long | inverse | gobus_inverse_2x   TV·비중 막대       │
│  없으면 “라이브 후 표시” / quality 배지                  │
└─────────────────────────────────────────────────────────┘
┌─ E. 종목 스트레스 표 (stocks[]) ───────────────────────┐
│ ticker | turnover | wag | inv_tv% | IR-5% | IR-10% | band│
│ 000660 | 0.09     | low | 0.30    | 5.1   | 10.2   | high│
│ 행 클릭 → 상품별 AUM/TV 드릴다운 (products[])            │
└─────────────────────────────────────────────────────────┘
┌─ F. 해석 힌트 (read_ko[]) ─────────────────────────────┐
│  · wag=high → …                                         │
│  · IR-10%≥10 → …                                        │
└─────────────────────────────────────────────────────────┘
```

### 카드 필드 매핑

| 블록 | 경로 |
|------|------|
| Conc | `distortion_squeeze.concentration.*` |
| 레버 AUM | `distortion_squeeze.market.levered_etf_aum_usd` |
| 외인/개인 | `distortion_squeeze.market.foreign_vs_retail` |
| 예탁/신용 | `distortion_squeeze.market.deposit_credit` |
| 곱버스 | `distortion_squeeze.market.by_direction` |
| 종목표 | `distortion_squeeze.stocks[]` |
| 한계 배지 | `distortion_squeeze.data_limits` |
| 힌트 | `distortion_squeeze.read_ko` |

### 색 / 밴드

- `wag_the_dog_band`: low=회색, mid=노랑, high=빨강
- `realized_band` / `band_if_minus_10pct`: low / watch / high (IR bands 3·10)
- `quality=missing` → 숫자 대신 **「데이터 없음」** 배지 (0 금지)

### 클릭

- Conc 카드 → Top5/Top10 티커 리스트
- 종목 행 → `products[]` 표 (ticker, L, aum, trading_value, direction)
- data_limits 배지 → note_ko 툴팁

---

## 2. Volume Profile 화면 스펙

**JSON:** `investor_price_levels_v1.json`  
탭2. 가격대별 체결 분포 (인포맥스형)

### 이미 있는 것 (양호)

- `as_of: 2026-08-08`, quality observed
- 코스피 지수 `bins_by_close` 15개 구간 (개인/외인/기관 순매수 억)
- 종목 17개: 시총 상위 + 시총100 내 고변동 (하닉·삼전·삼성전기·한미반도체 등)
- 종목별 `bins_by_close` + `bins_by_range`
- `close_day_table_marcap` / `high_vol`
- `cannot_do_ko` / `data_policy_ko`: **틱 매집 아님**, 일별 수급→종가 빈 귀속

### 레이아웃

```
┌─ 헤더: 가격대별 수급 · as_of · “틱 단위 아님” 배지 ─────┐
├─ 토글: [코스피 지수] [시총상위] [고변동] ───────────────┤
├─ 종목 셀렉터 (tickers 키) ─────────────────────────────┤
├─ 인포맥스형 가로 막대 ─────────────────────────────────┤
│  가격 bin (lo–hi)                                       │
│  ████████ +개인   ░░░░ -외인   ▓▓▓ +기관                │
│  (retail_net_krw / foreign_net_krw / institution_net_krw)│
├─ 당일 종가 표 (close_day_table_*) ─────────────────────┤
│  종목 | 종가 | 개인 | 외인 | 기관                        │
└─ highlights / headline_ko (코스피 상단 요약) ───────────┘
```

### 매핑

| UI | JSON |
|----|------|
| 코스피 막대 | `kospi_index_levels.bins_by_close[]` |
| 종목 막대 | `tickers[code].bins_by_close[]` |
| 시총 표 | `close_day_table_marcap` |
| 고변동 표 | `close_day_table_high_vol` |
| 정책 배지 | `data_policy_ko`, `cannot_do_ko` |
| 헤드라인 | `kospi_index_levels.headline_ko` |

### Volume 쪽에서 잘된 점

- 하닉만이 아님: 고변동 유니버스에 삼성전기·한미반도체·SK스퀘어 등
- 실측 only, demo 금지 정책이 문서·JSON에 박혀 있음
- 단위(억/주) 명시

### Volume에서 보완하면 좋은 점

1. **D&S와 연동 클릭** — D&S 종목 행 클릭 시 Volume 탭으로 같은 ticker 점프
2. **bin 부호 색** — 순매수 녹 / 순매도 적 (이미 데이터에 +/- 있음)
3. **n_days 작은 bin** — n_days≤2면 “표본 적음” 툴팁 (`n_days` 필드 있음)
4. 재빌드 주기: D&S와 별도 (`build_investor_price_levels.py`) — as_of가 하루 어긋날 수 있음 → UI에 as_of 각각 표시

---

## 3. 엔진 vs UI 책임

| | Cursor/Grok (엔진) | Claude (UI) |
|--|-------------------|-------------|
| distortion_squeeze 블록 | ✅ 추가됨 | 카드/표 렌더 |
| by_direction | 코드 추가, **라이브 후** JSON 반영 | 막대 |
| investor_price_levels | ✅ 존재 | 인포맥스 막대 |
| 옵션/공매 숫자 | missing 유지 | 배지만 |
| 클릭 모달 | ❌ | ✅ |

---

## 4. 한 줄 요약

- **라이브** = 당일 공개 시세를 다시 받아 JSON을 덮어쓰는 빌드 명령.
- **D&S** = `distortion_squeeze` 카드 5단(Conc → 시장 → 곱버스 → 종목표 → 힌트).
- **Volume** = 데이터는 이미 쓸 만함. 막대 + 시총/고변동 표 + “틱 아님” 배지 + D&S 종목 연동.
