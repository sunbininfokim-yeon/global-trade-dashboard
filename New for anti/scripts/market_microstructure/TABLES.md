# Market microstructure tables — 2026-08-21

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
| Conc_top2 (005930+000660) % | 50.9275 | KRX OpenAPI sto/stk_bydd_trd basDd=20260821 | observed |
| Conc_top5 % | 58.1486 | KRX OpenAPI sto/stk_bydd_trd basDd=20260821 | observed |
| Conc_top10 % | 64.5724 | KRX OpenAPI sto/stk_bydd_trd basDd=20260821 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 005380, 373220, 207940, 032830, 028260 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -3517338138500 | covered_underlyings_spot | estimated |
| retail | 3893664567500 | covered_underlyings_spot | estimated |
| institution | -2064648500000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 25,584,828,074,897 | 18,274,877,196.35 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260821 | observed |
| KR single-stock LETF AUM (listed) | 7,427,533,927,273 | 5,305,381,376.62 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 4,329,860,010,253 | 7,430,733,958,500 | 0.0884 | 0.9517 | None |
| 005930 | 3,097,673,917,020 | 7,703,213,942,500 | 0.0416 | 0.5378 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0231 | mid | 98.3 | 1.7 | 21.5 | 761834910000 | -1579948450000 | 2.7831 |
| 005930 | 0.0387 | low | 99.6 | 0.4 | 3.4 | 3131829657500 | -1937389688500 | 3.14 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,514,925,767,774 | 352,873,437,424 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,539,509,722,104 | 155,876,797,695 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 59,296,370,814 | 2,228,210,231 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 42,591,139,202 | 936,192,625 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 57,520,914,465 | 2,933,177,572 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 14,122,342,043 | 313,095,121 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 28,716,139,653 | 461,043,144 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 73,177,614,198 | 141,410,405,982 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,831,741,929,103 | 185,639,903,611 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 1,099,892,859,181 | 119,336,915,504 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 55,343,223,349 | 1,919,296,772 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 36,385,107,122 | 1,409,388,827 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 20,237,927,787 | 286,033,210 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 10,848,000,752 | 156,129,630 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 29,539,965,094 | 539,013,030 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 13,684,904,632 | 10,858,028,331 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 10610762753.25 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1712280303.59 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 198654542624.84 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1409643126.15 | 0.0 | 0.2656 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.055 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 704821563.0769231 | 755513527.4752544 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 171122471.10432553 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 10902828.236858204 | indirect_swap |

| Crypto product | underlying | OI USD | 24h vol USD | funding | impact |
|---------------|------------|-------:|------------:|--------:|--------|
| SKHYNIXUSDT | 000660 |  |  |  | ERROR |
| SAMSUNGUSDT | 005930 |  |  |  | ERROR |
| KORUUSDT | KORU |  |  |  | ERROR |
| SOXLUSDT | SOXL |  |  |  | ERROR |
| SOXSUSDT | SOXS |  |  |  | ERROR |

## 5. Rebalancing short-gamma scenarios (TR / IR)

| ticker | R | TR_abs | IR % | band |
|--------|--:|-------:|-----:|------|
| 000660 | -0.05 | 447,621,523,865 | 6.0239 | watch |
| 000660 | -0.1 | 895,243,047,730 | 12.0478 | high |
| 000660 | 0.05 | 447,621,523,865 | 6.0239 | watch |
| 000660 | 0.0231 | 206,801,144,026 | 2.7831 | low |
| 005930 | -0.05 | 312,504,372,628 | 4.0568 | watch |
| 005930 | -0.1 | 625,008,745,257 | 8.1136 | watch |
| 005930 | 0.05 | 312,504,372,628 | 4.0568 | watch |
| 005930 | 0.0387 | 241,878,384,414 | 3.14 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 18274877196.35 | -29.71 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5971 | -71.57 | estimated |
| leverage_exposure_pct_notional | None | 0.7205 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1007456.46 | 2026-08-21 | observed |
| 신용잔고 | 324162.88 | 2026-08-21 | observed |
| 신용/예탁금 % | 32.176 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -3669100000000.0 | 26.08.24 | observed |
| retail | 3321700000000.0 | 26.08.24 | observed |
| institution | -1290100000000.0 | 26.08.24 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 3.897 | 74.96 | 14.893 |
| overseas | 26 | 0.012 | 0.24 | 0.047 |
| sector | 8 | 0.495 | 9.51 | 1.89 |
| single_stock | 16 | 0.795 | 15.29 | 3.039 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
