# Market microstructure

코스피 쏠림 · 레버리지 ETF 거래비중 · 리밸런싱(IR) · 외인 vs 개인 — **공개 데이터 역산**.

증권사 고객 레버리지 비율 공시 ≠ 없음. 대체 지표만 사용. 투자 권유 아님.

## 문서

- [`DATA_SOURCES.md`](./DATA_SOURCES.md) — 페이퍼 지표 ↔ 공개 파이프라인
- [`TABLES.md`](./TABLES.md) — 최신 표 (빌드 산출)
- [`AI_CASINO_BRIEF.md`](./AI_CASINO_BRIEF.md) — Market Ear 스타일 헤드라인 + ETF 순위
- [`config/paper_anchors.json`](./config/paper_anchors.json) — Market Ear 앵커
- [`config/letf_universe.json`](./config/letf_universe.json) — 국내 단일종목 레버 유니버스

## 실행

```bash
cd "New for anti/scripts/market_microstructure"
# 의존성
../../.venv/bin/python -m pip install finance-datareader requests pandas

# fixture
../../.venv/bin/python -m unittest discover -s tests -v
../../.venv/bin/python build_market_microstructure.py --print-stats

# 한국 라이브 — Cloudflare secret 이름: KRX_API (+ HK/crypto 자동)
export KRX_API='…'   # optional
../../.venv/bin/python build_market_microstructure.py --live --source auto --print-stats
# → KR + Yahoo(7709/7747/7347) + Binance(SKHYNIXUSDT/SAMSUNGUSDT/…)
# → public/data/market_microstructure_v1.json
# → public/data/ai_casino_brief_v1.json  (유동시총 대비 레버 % + ETF 순위)
# → AI_CASINO_BRIEF.md / TABLES.md
# 공개 추가분: 예탁금·신용잔고, 코스피 수급, 레버 카테고리 분해, 공매도(가능 시)
# venue 분리 표: TABLES.md §4d Global leverage stack

# Conc 시계열 (Top2/5/10)
../../.venv/bin/python build_conc_history.py --live --months 6 --print-stats
# → public/data/kospi_concentration_history_v1.json
# 이후 매일: --append-only

# 스케줄러 (UI 제외)
./run_daily.sh    # conc + D&S + FreeSIS credit + L3 + derivatives + investor×price

# LETF 거래대금 비중 과거 백필 (KRX_API 필요, 장 마감 일별)
./.venv/bin/python build_letf_share_history.py --live --months 6 --print-stats
# KOSPI 현물 투자자별 순매수: 일별 아카이브 / 최초 60거래일 백필
./.venv/bin/python build_investor_flow_history.py --append-only
./.venv/bin/python build_investor_flow_history.py --live --lookback-days 60
./run_weekly.sh   # conc backfill + discovery + hitrate + regime-proxy

# 페이퍼 대비 검증 + (가격경로) 이벤트 스터디
../../.venv/bin/python build_validation_backtest.py --live --print-stats

# 실측 전용 3단계 임계값 (풋 OI 히스토리 없음 → VIX/KR LETF만)
../../.venv/bin/python build_alert_levels.py --live --print-stats
# → public/data/alert_levels_v1.json · ALERT_LEVELS.md
# 주의: SOXL 수익률로 옵션 스트레스를 대체한 백테스트는 사용하지 말 것
```

공개 extras (`fetch_kr_public_extras.py`): 증권사 고객 레버(비공시) 제외.

- **KRX_API** → `sto/stk_bydd_trd` + `etp/etf_bydd_trd` (마이페이지에서 API별 이용신청 필요)
- Naver → 외인/기관/개인 순매수
- 키는 코드·깃에 넣지 말 것 (채팅에도 재부착 금지)

### KOSPI200 외국인 선물·콜·풋 수급

OI(전체 미결제약정)는 KRX 파생 일별 API로, 외국인 **당일 거래수급**은
투자자별 거래실적 CSV로 별도 받는다. `--csv-fut`, `--csv-opt-call`,
`--csv-opt-put`에 각각 전달한다. CSV는 `일자`와 외국인 `매수`·`매도`
또는 `합계(순매수)` 열을 가진다. 산출 JSON은 매수·매도·순매수를
백만원 단위로 보존하고 `kr_foreign_derivatives_history_v1.json`에 실측만
일별 적재한다. 외국인 보유 OI/포지션으로 해석하지 않는다.

## AI Casino brief

페이퍼 섹션 미러: concentration · leverage reset · **AUM/유동시총** · foreign vs retail · largest ETF drill-down.

- 정의1 (paper 2.1%): `KR 레버·인버스 ETF AUM / KOSPI 유동시총`
- 정의2: `Σ AUM×|L| / 커버 종목 유동시총`
- HK·crypto는 KR 유동시총 분모에 **합산하지 않음**
- AUM 1위는 보통 **7709.HK** (7708 아님)

## Paper-derived observed charts

- **Leverage reset**: 국내 레버·인버스 ETF AUM(관측)과 `AUM / KOSPI 유동시총 프록시`(추정)를 분리해 장마감 시계열로 보관한다. AUM 하락만으로 환매/자금유출을 주장하지 않는다.
- **Foreign vs retail**: KOSPI 현물의 외국인·개인·기관 **순매수**를 일별/보관시작일 대비 누적으로 표시한다. GS Gross/Net 국가배분·투자자 보유비중이 아니다.
- **Retail leverage stress**: 예탁금·신용융자·미수·반대매매는 FreeSIS 공표 시점의 시장전체 보조지표로 표시하며, 가격대별 수급이나 특정 투자자 포지션으로 귀속하지 않는다.
- **Leveraged pain / Korea leading**: `SOXL vs SMH`, `KORU vs EWY`는 Yahoo 조정종가를 100으로 재기준화한 외부 레짐 비교다. 원 도표의 SOX·GS 배분 데이터를 복제한 것이 아니며 한국 현물 리밸런싱 공식에 넣지 않는다.

## US → KR cross-market

```bash
../../.venv/bin/python build_us_kr_cross_market.py --live --print-stats
# → public/data/us_microstructure_v1.json
# → public/data/us_regime_v1.json
# → public/data/us_kr_transmission_v1.json
# → US_KR_TABLES.md

../../.venv/bin/python build_us_kr_l3.py --live --print-stats
# full L3: watchlist fetch + Tier A/B tx + discovery + open30m + hitrate
# → public/data/us_kr_hitrate_v1.json + US_KR_L3.md
```

- 공매: **FINRA** official API
- 옵션: **Cboe delayed CDN** 우선, Yahoo 폴백; 현물 프리마켓은 Yahoo
- VIX/VVIX/SKEW: Cboe 일별 CSV
- 링크 Tier A: `config/us_kr_link_graph.json` · Tier B: discovered edges (경보에 하향 가중 합류)
- hit-rate: `us_kr_hitrate_v1.json` (주간 재캘리브용)
- 설계: [`US_CROSS_MARKET.md`](./US_CROSS_MARKET.md)
- 채널: downside / upside / vol_up / vol_down (하방 강조)

## 핵심 공식

```
TR = Σ AUM × (L² − L) × R
IR(%) = |TR| / ADV_spot × 100
LETF_turnover_ratio = LETF_trading_value / Underlying_ADV
leverage_exposure_pct = Σ(AUM × |L| × β) / free_float_mcap × 100
```
