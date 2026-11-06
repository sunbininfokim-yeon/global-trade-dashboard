# Market microstructure tables — 2026-11-05

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
| Conc_top2 (005930+000660) % | 47.3086 | KRX OpenAPI sto/stk_bydd_trd basDd=20261105 | observed |
| Conc_top5 % | 54.4315 | KRX OpenAPI sto/stk_bydd_trd basDd=20261105 | observed |
| Conc_top10 % | 61.3245 | KRX OpenAPI sto/stk_bydd_trd basDd=20261105 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 373220 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 373220, 009150, 207940, 005380, 105560, 068270 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -2654012239500 | covered_underlyings_spot | estimated |
| retail | 2087209417000 | covered_underlyings_spot | estimated |
| institution | 310606403000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 17,538,227,198,891 | 12,527,305,142.07 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20261105 | observed |
| KR single-stock LETF AUM (listed) | 3,356,333,167,527 | 2,397,380,833.95 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 1,973,660,397,421 | 5,478,348,796,620 | 0.0689 | 0.5938 | None |
| 005930 | 1,382,672,770,106 | 5,038,715,454,486 | 0.0302 | 0.3353 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.0946 | mid | 95.2 | 4.8 | 36.9 | 875790208000 | -1490914544000 | 7.4749 |
| 005930 | -0.0757 | low | 98.3 | 1.7 | 4.8 | 1211419209000 | -1163097695500 | 4.295 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 1,103,708,850,021 | 171,961,122,901 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 695,385,569,286 | 61,578,004,367 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 22,959,677,166 | 995,992,265 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 17,767,529,376 | 481,887,615 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 22,930,182,032 | 2,045,370,627 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 5,036,374,663 | 488,236,995 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 10,517,099,250 | 692,421,630 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 95,355,115,627 | 139,280,501,777 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 827,472,228,303 | 84,169,285,468 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 473,798,557,282 | 59,307,124,599 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 22,312,762,904 | 938,412,460 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 15,454,085,646 | 170,917,707 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 7,403,947,775 | 329,491,532 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 4,708,520,556 | 33,852,122 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 8,153,303,570 | 123,532,320 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 23,369,364,070 | 7,279,516,227 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 4794761667.9 |
| HK CSOP swap LETF | notional AUM×\|L\| | None |
| Crypto Binance perps | OI notional | None |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 195469110339.9 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | None | 0.0 | None | 0.0 |
| 005930 | None | 0.0 | None | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | None | None | 270370183.024959 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | None | None | 46870474.63478357 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | None | None | 2437117.7828095104 | indirect_swap |

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
| 000660 | -0.05 | 216,437,062,868 | 3.9508 | watch |
| 000660 | -0.1 | 432,874,125,735 | 7.9015 | watch |
| 000660 | 0.05 | 216,437,062,868 | 3.9508 | watch |
| 000660 | -0.0946 | 409,498,922,945 | 7.4749 | watch |
| 005930 | -0.05 | 142,941,149,825 | 2.8369 | low |
| 005930 | -0.1 | 285,882,299,649 | 5.6737 | watch |
| 005930 | 0.05 | 142,941,149,825 | 2.8369 | low |
| 005930 | -0.0757 | 216,412,900,834 | 4.295 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 12527305142.07 | -51.82 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5265 | -74.93 | estimated |
| leverage_exposure_pct_notional | None | 0.4507 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 892273.2 | 2026-11-04 | observed |
| 신용잔고 | 286446.21 | 2026-11-04 | observed |
| 신용/예탁금 % | 32.103 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -3373300000000.0 | 26.11.05 | observed |
| retail | 2208700000000.0 | 26.11.05 | observed |
| institution | 881900000000.0 | 26.11.05 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 6.571 | 77.2 | 27.435 |
| overseas | 25 | 0.028 | 0.32 | 0.115 |
| sector | 8 | 1.115 | 13.1 | 4.656 |
| single_stock | 16 | 0.798 | 9.37 | 3.33 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
