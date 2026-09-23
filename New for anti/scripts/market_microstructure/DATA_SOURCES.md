# DATA_SOURCES — 공개 파이프라인 맵

증권사가 **고객 레버리지 비율(종목별)** 을 공시하지 않는다.  
페이퍼의 “레버리지”는 **상품 AUM·거래대금·리밸런싱**으로 역산한다.

## 페이퍼 지표 → 공개 소스

| 페이퍼 지표 (AI Casino 등) | 공개 정의 | 1차 소스 | 품질 |
|---------------------------|-----------|----------|------|
| Leveraged ETF AUM ($53bn→$26bn) | 국내 레버/인버스 ETF 순자산 합 | KRX ETP / pykrx ETF OHLCV·시가총액 / 코스콤 ETF CHECK(웹) | observed |
| Leverage / free float **2.1%** | `Σ(AUM×\|L\|×β) / free_float_mcap` | 위 AUM + KRX 유통시총 | estimated (공식 고정) |
| LETF turnover % of cash equity | `LETF_trading_value / Underlying_ADV` | KRX ETF 거래대금 / 현물 거래대금 | observed |
| Rebalancing = short-gamma | `TR = Σ AUM×(L²−L)×R` | AUM + L + 현물 수익률 | estimated |
| Concentration | Conc_top2/5/10 | KRX `get_market_cap` (pykrx) | observed |
| Foreign vs retail | 투자자별 순매수 (현물·ETF) | KRX 투자자별 매매 (pykrx) | observed |
| 가격대별 누가 샀나 | 일별 순매수 → 종가/고저 빈 귀속 | Naver `trend?pageSize=` + FDR OHLC | **estimated** (틱 단위 아님) |
| Shorts | 공매도 잔고·비중 | KRX OpenAPI 공매도 엔드포인트 / pykrx | **missing** (data.krx LOGOUT since 2026-02; needs `KRX_API` 이용신청 or login) |
| 미수·강제청산 (Paper C) | 신용융자·미수·반대매매 | 네이버 증시자금 **신용잔고·예탁금** (FreeSIS 재배포) | observed (미수·반대는 미포함) |
| 코스피 시장 수급 | 투자자별 순매수 | Naver `investorDealTrendDay` | observed |
| 레버 ETF 유형 분해 | 지수/섹터/해외/단일종목 TV | FDR ETF Name classify | observed |
| 홍콩 단일종목 레버 | HK LETF AUM·거래 | HKEX / 리서치 PDF | observed (국내와 **분리**) |
| US SOXL / KORU | 미국 레버 ETF | Yahoo 등 | observed |
| K200 선물·콜·풋 투자자별 수급 (2019~) | 외국인·기관·개인·기타법인 매수/매도/순매수 거래대금 | KRX 15007 정규화 이력 (`krx-month-paste` `data/normalized/krx_15007_k200_investor`) → `build_krx_deriv_flow.py` → `krx_deriv_flow_v1.json` | observed (OI 아님) |
| K200 선물 최근월물 종가·OI | 정규장 종가 · 시장 전체 미결제약정 | KRX 15003 (`kospi200_futures_oi`) → 같은 파일 `futures_front` | observed (외국인 OI 아님) |
| K200 옵션 최근월물 체인 OI·ATM IV | 콜/풋 OI 합계·최대 OI 행사가·P/C OI·ATM IV, 최신일 행사가별 OI | KRX 15018 (`kospi200_option_oi`) → 같은 파일 `option_oi` | observed (외국인 OI 아님, 만기일 OI 미공시) |
| 프로그램매매 (유가증권) | 차익·비차익·전체 순매수 | KRX 12012 (`kospi_program`) → 같은 파일 `program` (자체 날짜축) | observed (수집률 67%, 빈 기간 있음) |

## 쓰지 않는 것 / 없는 것

| 원하는 값 | 현실 |
|-----------|------|
| 증권사별 “하이닉스 고객 레버리지” | **비공시** |
| Dealer gamma 장부 | 비공개 → IR·OI로 proxy |
| LSEG/Bloomberg 차트 숫자 원천 | 유료 → `paper_anchor`로만 캘리브 |

## 파이프라인 우선순위

1. **KRX OpenAPI** — 시크릿 이름 **`KRX_API`** (Cloudflare `env.KRX_API`)  
   - `sto/stk_bydd_trd` 시총·거래대금  
   - `etp/etf_bydd_trd` ETF AUM·거래대금  
   - 로컬: `export KRX_API=...` 또는 `.dev.vars`  
   - **API마다 마이페이지 이용신청** 필요
2. **Naver mobile** — `dealTrendInfos` (외인/기관/개인)
3. **해외 LETF 보드** (`overseas_letf_board_v1.json`) — 홍콩 CSOP L&I
   (`7709.HK` 하닉, `7747.HK`/`7347.HK` 삼전). `fetch_external_venues.py`가
   직접 Yahoo를 치던 경로는 제거했다: 배율을 config의 2로 고정하고, HKD를
   상수 7.8로 환산하고, 기준일 없는 `totalAssets`를 관측치처럼 실었기 때문이다.
   운용사가 기준일과 함께 공개한 AUM·배율만 쓰므로 미공개 구간에는 노셔널이
   비고, 그 대신 가정이 필요 없는 `etf_to_kr_cash_tv_ratio`(홍콩 거래대금 ÷
   같은 날 한국 현물 거래대금)를 쓴다 — 국내 `letf_turnover_ratio`와 **분모의 정의가**
   같다. 다만 **같은 날은 아니다**: 해외 수집은 국내 배치보다 보통 한 거래일 앞선
   날짜까지만 확정되므로(예: 스냅샷 2026-09-10 ↔ 보드 2026-09-09), 두 비율은 서로
   다른 날의 거래대금으로 나눈 값이다. `hk_tv_as_of`를 반드시 함께 표시할 것.
4. **Binance USD-M** — `SKHYNIXUSDT` / `SAMSUNGUSDT` (+ `KORUUSDT`/`SOXLUSDT` 프록시)
5. **FinanceDataReader** — `KRX_API` 없을 때 KR fallback
6. **fixture / 수동 CSV** — unittest
7. **금투협 FreeSIS** — 신용·미수 집계

### Venue 합산 규칙
- **KR cash/futures LETF** → wag-the-dog / TR / IR (현물 ADV 대비)
- **HK swap LETF** → 글로벌 노출·규모 비교만 (`kr_spot_impact=indirect_swap`)
- **Crypto perps** → OI notional / 24h volume (`indirect_synthetic`)
- `global_stack_usd`는 참고 합산; **한 셀에 섞어 wag-the-dog로 쓰지 말 것**

## 합산 규칙

- 국내 LETF / 홍콩 LETF / ADR·선물 / ELW 는 **절대 한 셀에 섞지 않음**
- 롱 레버와 인버스는 TR을 **각각 계산 후 합산** (상쇄로 합치면 안 됨)
- 모든 필드: `source`, `as_of`, `quality: observed|estimated|demo|paper_anchor`
