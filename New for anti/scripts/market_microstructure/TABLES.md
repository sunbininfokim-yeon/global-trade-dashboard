# Market microstructure tables — 2026-10-26

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
| Conc_top2 (005930+000660) % | 48.2173 | KRX OpenAPI sto/stk_bydd_trd basDd=20261026 | observed |
| Conc_top5 % | 55.3271 | KRX OpenAPI sto/stk_bydd_trd basDd=20261026 | observed |
| Conc_top10 % | 62.2127 | KRX OpenAPI sto/stk_bydd_trd basDd=20261026 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 373220 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 373220, 009150, 207940, 005380, 105560, 032830 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -605360487000 | covered_underlyings_spot | estimated |
| retail | 148921182000 | covered_underlyings_spot | estimated |
| institution | 435037974000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 18,284,504,595,578 | 13,060,360,425.41 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20261026 | observed |
| KR single-stock LETF AUM (listed) | 3,722,004,535,778 | 2,658,574,668.41 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 2,145,775,786,575 | 3,447,834,901,245 | 0.0734 | 0.64 | None |
| 005930 | 1,576,228,749,203 | 2,430,729,239,364 | 0.0365 | 0.3617 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.0016 | mid | 94.5 | 5.5 | 36.7 | 79709175000 | -395683500000 | 0.2212 |
| 005930 | -0.0116 | low | 98.8 | 1.2 | 5.1 | 69212007000 | -209676987000 | 1.5419 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 1,191,485,646,745 | 121,356,544,496 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 750,031,582,364 | 36,800,371,103 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 24,364,628,377 | 175,090,382 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 18,889,095,068 | 318,971,546 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 25,403,576,697 | 1,379,921,797 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 5,725,346,979 | 36,268,635 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 11,254,947,726 | 317,821,916 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 118,620,962,619 | 92,837,286,397 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 949,710,189,589 | 52,996,349,050 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 540,436,128,230 | 30,499,762,026 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 25,095,483,678 | 196,607,040 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 17,802,853,636 | 285,977,815 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 8,638,469,172 | 87,793,510 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 5,352,900,366 | 41,472,990 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 9,585,578,842 | 72,413,880 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 19,607,145,690 | 4,520,194,642 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 5317149336.83 |
| HK CSOP swap LETF | notional AUM×\|L\| | None |
| Crypto Binance perps | OI notional | None |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 226719018408.83 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | None | 0.0 | None | 0.0 |
| 005930 | None | 0.0 | None | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | None | None | 329587722.1043267 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | None | None | 93467765.16293816 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | None | None | 3895753.0869576475 | indirect_swap |

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
| 000660 | -0.05 | 238,301,771,181 | 6.9116 | watch |
| 000660 | -0.1 | 476,603,542,363 | 13.8233 | high |
| 000660 | 0.05 | 238,301,771,181 | 6.9116 | watch |
| 000660 | -0.0016 | 7,625,656,678 | 0.2212 | low |
| 005930 | -0.05 | 161,544,304,058 | 6.6459 | watch |
| 005930 | -0.1 | 323,088,608,117 | 13.2918 | high |
| 005930 | 0.05 | 161,544,304,058 | 6.6459 | watch |
| 005930 | -0.0116 | 37,478,278,542 | 1.5419 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 13060360425.41 | -49.77 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5401 | -74.28 | estimated |
| leverage_exposure_pct_notional | None | 0.4827 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 898626.21 | 2026-10-23 | observed |
| 신용잔고 | 301521.59 | 2026-10-23 | observed |
| 신용/예탁금 % | 33.554 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -1672600000000.0 | 26.09.16 | carried_forward |
| retail | -1206100000000.0 | 26.09.16 | carried_forward |
| institution | 1225100000000.0 | 26.09.16 | carried_forward |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 5.553 | 81.83 | 31.96 |
| overseas | 26 | 0.025 | 0.37 | 0.144 |
| sector | 8 | 0.644 | 9.49 | 3.705 |
| single_stock | 16 | 0.565 | 8.32 | 3.249 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
