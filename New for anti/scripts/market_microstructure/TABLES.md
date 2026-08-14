# Market microstructure tables — 2026-08-13

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
| Conc_top2 (005930+000660) % | 48.5932 | KRX OpenAPI sto/stk_bydd_trd basDd=20260813 | observed |
| Conc_top5 % | 55.896 | KRX OpenAPI sto/stk_bydd_trd basDd=20260813 | observed |
| Conc_top10 % | 62.38 | KRX OpenAPI sto/stk_bydd_trd basDd=20260813 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 005380, 373220, 207940, 012450, 105560 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | 927628734000 | covered_underlyings_spot | estimated |
| retail | -2620231137000 | covered_underlyings_spot | estimated |
| institution | 1739460873000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 25,982,402,020,993 | 18,558,858,586.42 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260813 | observed |
| KR single-stock LETF AUM (listed) | 6,942,189,535,300 | 4,958,706,810.93 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 3,960,904,412,918 | 7,514,884,503,000 | 0.0826 | 0.9455 | None |
| 005930 | 2,981,285,122,382 | 9,517,753,428,321 | 0.0284 | 0.5437 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0592 | low | 98.2 | 1.8 | 25.3 | -1254221469000 | 1035198306000 | 6.4661 |
| 005930 | 0.0489 | low | 99.5 | 0.5 | 3.0 | -1366009668000 | -107569572000 | 3.0932 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,338,730,580,702 | 268,491,997,220 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,364,887,749,243 | 188,489,599,129 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 55,181,107,146 | 1,330,688,475 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 38,353,071,377 | 551,507,710 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 53,776,989,473 | 4,008,593,905 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 12,592,860,958 | 256,302,155 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 25,822,578,141 | 428,844,431 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 71,559,475,878 | 157,185,517,968 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,787,572,335,341 | 176,604,306,027 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 1,029,413,715,810 | 82,771,436,097 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 57,733,147,238 | 1,111,863,744 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 35,435,889,629 | 882,950,820 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 19,448,785,461 | 572,231,261 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 10,421,830,322 | 186,640,608 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 26,779,415,077 | 418,437,678 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 14,480,003,504 | 8,212,423,766 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 9917413621.86 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1712280303.59 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 197961193493.45 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1409643126.15 | 0.0 | 0.2626 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.0445 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 704821563.0769231 | 744161927.5452365 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 98740085.34408276 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 4399797.444649079 | indirect_swap |

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
| 000660 | -0.05 | 410,402,336,467 | 5.4612 | watch |
| 000660 | -0.1 | 820,804,672,935 | 10.9224 | high |
| 000660 | 0.05 | 410,402,336,467 | 5.4612 | watch |
| 000660 | 0.0592 | 485,916,366,377 | 6.4661 | watch |
| 005930 | -0.05 | 301,024,512,939 | 3.1628 | watch |
| 005930 | -0.1 | 602,049,025,878 | 6.3255 | watch |
| 005930 | 0.05 | 301,024,512,939 | 3.1628 | watch |
| 005930 | 0.0489 | 294,401,973,654 | 3.0932 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 18558858586.42 | -28.62 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.6165 | -70.64 | estimated |
| leverage_exposure_pct_notional | None | 0.7177 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1000683.83 | 2026-08-13 | observed |
| 신용잔고 | 309262.66 | 2026-08-13 | observed |
| 신용/예탁금 % | 30.905 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | 3054900000000.0 | 26.08.14 | observed |
| retail | -1887800000000.0 | 26.08.14 | observed |
| institution | -1141300000000.0 | 26.08.14 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 4.485 | 74.5 | 22.275 |
| overseas | 26 | 0.018 | 0.3 | 0.089 |
| sector | 8 | 0.682 | 11.33 | 3.389 |
| single_stock | 16 | 0.834 | 13.86 | 4.144 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
