# Market microstructure tables — 2026-11-24

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
| Conc_top2 (005930+000660) % | 46.9145 | KRX OpenAPI sto/stk_bydd_trd basDd=20261124 | observed |
| Conc_top5 % | 53.9393 | KRX OpenAPI sto/stk_bydd_trd basDd=20261124 | observed |
| Conc_top10 % | 60.8301 | KRX OpenAPI sto/stk_bydd_trd basDd=20261124 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 373220 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 373220, 009150, 207940, 005380, 105560, 032830 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | 306934416800 | covered_underlyings_spot | estimated |
| retail | -914499524200 | covered_underlyings_spot | estimated |
| institution | 221850611600 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 16,603,202,117,651 | 11,859,430,084.04 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20261124 | observed |
| KR single-stock LETF AUM (listed) | 2,862,554,200,917 | 2,044,681,572.08 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 1,675,285,466,915 | 4,245,412,786,814 | 0.0827 | 0.5686 | None |
| 005930 | 1,187,268,734,002 | 3,257,170,019,300 | 0.0284 | 0.3064 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0673 | mid | 96.0 | 4.0 | 49.3 | -270419634000 | -137790420000 | 5.7382 |
| 005930 | 0.067 | low | 98.3 | 1.7 | 6.2 | -644079890200 | 444724836800 | 5.0512 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 961,509,715,717 | 132,928,083,388 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 578,963,531,479 | 41,989,506,778 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 19,580,541,770 | 486,535,065 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 15,061,687,831 | 388,627,930 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 19,614,745,420 | 1,467,966,185 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 4,556,181,281 | 50,486,070 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 8,695,957,303 | 519,371,746 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 67,303,106,114 | 173,059,562,130 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 705,673,192,300 | 61,721,240,591 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 410,093,135,219 | 23,834,369,974 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 20,101,915,439 | 508,797,240 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 13,422,970,137 | 177,857,360 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 6,667,941,497 | 142,749,400 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 4,033,844,658 | 419,779,625 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 7,002,337,184 | 55,963,625 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 20,273,397,568 | 5,736,435,325 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 4089363144.17 |
| HK CSOP swap LETF | notional AUM×\|L\| | None |
| Crypto Binance perps | OI notional | None |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 194763711816.17 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | None | 0.0 | None | 0.0 |
| 005930 | None | 0.0 | None | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | None | None | 306734834.7162417 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | None | None | 30687945.837737955 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | None | None | 4553889.619996785 | indirect_swap |

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
| 000660 | -0.05 | 180,989,167,914 | 4.2632 | watch |
| 000660 | -0.1 | 361,978,335,829 | 8.5263 | watch |
| 000660 | 0.05 | 180,989,167,914 | 4.2632 | watch |
| 000660 | 0.0673 | 243,611,420,013 | 5.7382 | watch |
| 005930 | -0.05 | 122,781,552,914 | 3.7696 | watch |
| 005930 | -0.1 | 245,563,105,828 | 7.5392 | watch |
| 005930 | 0.05 | 122,781,552,914 | 3.7696 | watch |
| 005930 | 0.067 | 164,527,280,904 | 5.0512 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 11859430084.04 | -54.39 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5393 | -74.32 | estimated |
| leverage_exposure_pct_notional | None | 0.4196 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 853361.63 | 2026-11-23 | observed |
| 신용잔고 | 259426.55 | 2026-11-23 | observed |
| 신용/예탁금 % | 30.401 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | 813000000000.0 | 26.11.24 | observed |
| retail | -2135000000000.0 | 26.11.24 | observed |
| institution | 873400000000.0 | 26.11.24 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 4.23 | 81.79 | 54.679 |
| overseas | 25 | 0.014 | 0.26 | 0.175 |
| sector | 8 | 0.543 | 10.49 | 7.012 |
| single_stock | 16 | 0.386 | 7.46 | 4.986 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
