# Market microstructure tables — 2026-09-10

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
| Conc_top2 (005930+000660) % | 50.427 | KRX OpenAPI sto/stk_bydd_trd basDd=20260910 | observed |
| Conc_top5 % | 57.6162 | KRX OpenAPI sto/stk_bydd_trd basDd=20260910 | observed |
| Conc_top10 % | 63.723 | KRX OpenAPI sto/stk_bydd_trd basDd=20260910 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 005380, 207940, 032830, 028260 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -3324792429000 | covered_underlyings_spot | estimated |
| retail | 10808750000 | covered_underlyings_spot | estimated |
| institution | 1680052449000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 25,276,972,862,585 | 18,054,980,616.13 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260910 | observed |
| KR single-stock LETF AUM (listed) | 7,253,087,605,231 | 5,180,776,860.88 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 4,554,844,714,322 | 8,279,969,782,300 | 0.077 | 0.9347 | None |
| 005930 | 2,698,242,890,909 | 6,028,310,398,811 | 0.0286 | 0.4902 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.0016 | mid | 97.8 | 2.2 | 19.8 | 127584609000 | -1772809572000 | 0.1838 |
| 005930 | -0.0019 | low | 99.5 | 0.5 | 2.7 | -116775859000 | -1551982857000 | 0.1717 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,639,698,595,818 | 414,398,320,469 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,611,588,487,432 | 93,052,124,504 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 60,102,493,007 | 926,170,595 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 46,153,457,896 | 493,206,195 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 55,116,446,273 | 2,023,525,055 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 14,634,842,509 | 212,739,405 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 27,284,967,485 | 349,276,875 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 100,265,423,902 | 126,298,005,092 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,528,273,814,668 | 107,279,438,212 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 1,039,174,415,540 | 58,788,679,336 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 42,176,703,664 | 834,394,670 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 31,019,002,908 | 345,331,455 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 17,968,048,820 | 126,384,435 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 8,908,750,657 | 138,777,875 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 18,252,323,486 | 128,169,500 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 12,469,831,166 | 4,663,553,405 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 10361553721.76 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1402866100.51 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 210641064822.27 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1100228923.08 | 0.0 | 0.186 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.0703 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 550114461.5384616 | 568344462.2234535 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 57400010.298209555 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 3607176.222860813 | indirect_swap |

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
| 000660 | -0.05 | 475,537,556,213 | 5.7432 | watch |
| 000660 | -0.1 | 951,075,112,425 | 11.4865 | high |
| 000660 | 0.05 | 475,537,556,213 | 5.7432 | watch |
| 000660 | -0.0016 | 15,217,201,799 | 0.1838 | low |
| 005930 | -0.05 | 272,318,255,324 | 4.5173 | watch |
| 005930 | -0.1 | 544,636,510,648 | 9.0346 | watch |
| 005930 | 0.05 | 272,318,255,324 | 4.5173 | watch |
| 005930 | -0.0019 | 10,348,093,702 | 0.1717 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 18054980616.13 | -30.56 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5808 | -72.34 | estimated |
| leverage_exposure_pct_notional | None | 0.6989 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1028461.7 | 2026-09-09 | observed |
| 신용잔고 | 324092.22 | 2026-09-09 | observed |
| 신용/예탁금 % | 31.512 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -2621700000000.0 | 26.09.10 | observed |
| retail | 380200000000.0 | 26.09.10 | observed |
| institution | 574400000000.0 | 26.09.10 | observed |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
