# Market microstructure tables — 2026-08-07

공개 상품 AUM·거래대금 기반 추정. 증권사 고객 레버리지 공시가 아님. 투자 권유 아님.

## 0. 증권사 레버리지 공시?

| 항목 | 값 |
|------|-----|
| available | False |
| note | 증권사는 종목별 고객 레버리지 비율을 공시하지 않음. 대체: LETF AUM, FreeSIS 신용·미수 집계, KRX 투자자별 매매. |
| public_proxies | krx_letf_aum, krx_letf_turnover, kofia_freesis_margin, krx_investor_flows, krx_short_interest, yahoo_hk_letf, yahoo_us_levered_inverse, binance_stock_perps, us_options_regime |

## 1. Concentration (paper: concentration matters)

| metric | value | source | quality |
|--------|------:|--------|---------|
| Conc_top2 (005930+000660) % | 46.3033 | FinanceDataReader StockListing(KOSPI) | observed |
| Conc_top5 % | 53.1997 | FinanceDataReader StockListing(KOSPI) | observed |
| Conc_top10 % | 60.1022 | FinanceDataReader StockListing(KOSPI) | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 005380, 207940, 105560, 012450 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -481471431000 | covered_underlyings_spot | estimated |
| retail | 429260562000 | covered_underlyings_spot | estimated |
| institution | 55250700000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 22,900,400,000,000 | 16,357,428,571.43 | FinanceDataReader ETF/KR names matching 레버리지|인버스 | observed |
| KR single-stock LETF AUM (listed) | 5,817,400,000,000 | 4,155,285,714.29 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 3,435,100,000,000 | 7,254,601,948,500 | 0.0918 | 0.9186 | None |
| 005930 | 2,382,300,000,000 | 4,791,580,972,001 | 0.0365 | 0.504 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.048799999999999996 | low | 96.1 | 3.9 | 30.3 | 282867084000 | -80139654000 | 4.9809 |
| 005930 | 0.0022 | low | 98.9 | 1.1 | 7.3 | 146393478000 | -401331777000 | 0.2236 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,027,300,000,000 | 306,312,000,000 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,116,600,000,000 | 150,496,000,000 | cash |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 133,600,000,000 | 201,499,000,000 | futures |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 46,500,000,000 | 2,349,000,000 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 45,400,000,000 | 3,557,000,000 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 33,800,000,000 | 651,000,000 | cash |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 21,400,000,000 | 486,000,000 | futures |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 10,500,000,000 | 357,000,000 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,440,600,000,000 | 107,429,000,000 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 796,600,000,000 | 53,070,000,000 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 45,500,000,000 | 704,000,000 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 29,800,000,000 | 487,000,000 | cash |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 26,300,000,000 | 12,754,000,000 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 20,400,000,000 | 136,000,000 | futures |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 14,800,000,000 | 244,000,000 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 8,300,000,000 | 233,000,000 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 8310571428.57 |
| HK CSOP swap LETF | notional AUM×\|L\| | 4312317226.67 |
| Crypto Binance perps | OI notional | 537779897.58 |
| Crypto Binance perps | 24h quote volume | 312178082.35 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 199492168120.82 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 3351317267.69 | 374545898.85 | 0.6467 | 0.0723 |
| 005930 | 960999958.97 | 22064145.14 | 0.2808 | 0.0064 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 1675658633.846154 | 1283079737.7843857 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 479216082.05128205 | 139342661.76173675 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 3210239.7435897435 | indirect_swap |

| Crypto product | underlying | OI USD | 24h vol USD | funding | impact |
|---------------|------------|-------:|------------:|--------:|--------|
| SKHYNIXUSDT | 000660 | 374545898.8544 | 132861776.6924 | 0.0 | indirect_synthetic |
| SAMSUNGUSDT | 005930 | 22064145.1356 | 11485933.296 | 0.0 | indirect_synthetic |
| KORUUSDT | KORU | 46931594.37100001 | 39900009.9195 | -0.0003312 | indirect_synthetic |
| SOXLUSDT | SOXL | 86507171.7075 | 109008187.5135 | -9.68e-05 | indirect_synthetic |
| SOXSUSDT | SOXS | 7731087.51 | 18922174.9278 | 2.542e-05 | indirect_synthetic |

## 5. Rebalancing short-gamma scenarios (TR / IR)

| ticker | R | TR_abs | IR % | band |
|--------|--:|-------:|-----:|------|
| 000660 | -0.05 | 370,230,000,000 | 5.1034 | watch |
| 000660 | -0.1 | 740,460,000,000 | 10.2068 | high |
| 000660 | 0.05 | 370,230,000,000 | 5.1034 | watch |
| 000660 | -0.048799999999999996 | 361,344,480,000 | 4.9809 | watch |
| 005930 | -0.05 | 243,490,000,000 | 5.0816 | watch |
| 005930 | -0.1 | 486,980,000,000 | 10.1632 | high |
| 005930 | 0.05 | 243,490,000,000 | 5.0816 | watch |
| 005930 | 0.0022 | 10,713,560,000 | 0.2236 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 16357428571.43 | -37.09 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5917 | -71.82 | estimated |
| leverage_exposure_pct_notional | None | 0.6871 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

네이버 증시자금(금투협 FreeSIS 계열 공개 재배포). 종목별 고객 레버 아님. 미수·반대매매는 이 표에 없음.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1032125.0 | 2026-08-05 | observed |
| 신용잔고 | 280277.0 | 2026-08-05 | observed |
| 신용/예탁금 % | 27.155 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -865100000000.0 | 26.08.07 | observed |
| retail | 267500000000.0 | 26.08.07 | observed |
| institution | 585400000000.0 | 26.08.07 | observed |

## 9. Levered ETF TV by category

이름에 레버리지|인버스|곱버스 포함 ETF 전부. 곱버스=지수 인버스2X 계열. 지수/섹터 레버는 단일종목 wag-the-dog 분모와 다름. 카테고리·방향 비중은 거래대금 기준.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 4.946 | 78.28 | 19.998 |
| overseas | 26 | 0.016 | 0.25 | 0.064 |
| sector | 8 | 0.516 | 8.16 | 2.085 |
| single_stock | 16 | 0.841 | 13.31 | 3.4 |

## 10. Short interest

| quality | missing |
| source | None |
| note | data.krx 비회원 LOGOUT(2026-02~)으로 pykrx 공매도 다수 실패. KRX_API 공매도 엔드포인트 이용신청 또는 data.krx 로그인 필요. |
