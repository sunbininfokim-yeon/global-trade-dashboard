# Market microstructure tables — 2026-11-17

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
| Conc_top2 (005930+000660) % | 46.3254 | KRX OpenAPI sto/stk_bydd_trd basDd=20261117 | observed |
| Conc_top5 % | 53.2676 | KRX OpenAPI sto/stk_bydd_trd basDd=20261117 | observed |
| Conc_top10 % | 60.1242 | KRX OpenAPI sto/stk_bydd_trd basDd=20261117 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 373220 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 373220, 207940, 009150, 105560, 005380, 068270 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -911234738900 | covered_underlyings_spot | estimated |
| retail | 214928849000 | covered_underlyings_spot | estimated |
| institution | 309385601200 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 15,782,285,511,420 | 11,273,061,079.59 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20261117 | observed |
| KR single-stock LETF AUM (listed) | 2,675,414,105,105 | 1,911,010,075.08 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 1,481,195,300,067 | 4,159,524,356,892 | 0.0968 | 0.5302 | None |
| 005930 | 1,194,218,805,038 | 3,219,293,139,094 | 0.0232 | 0.3067 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.0196 | mid | 93.3 | 6.7 | 55.4 | -82850688000 | -438456654000 | 1.5836 |
| 005930 | -0.033 | low | 98.2 | 1.8 | 7.9 | 297779537000 | -472778084900 | 2.5352 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 814,708,272,254 | 133,447,876,945 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 506,443,169,090 | 44,286,700,506 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 17,737,610,587 | 738,460,520 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 13,654,704,375 | 124,574,215 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 17,289,848,508 | 489,103,801 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 3,953,927,284 | 149,792,677 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 7,833,013,046 | 151,197,175 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 99,574,754,923 | 223,050,680,428 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 712,881,008,378 | 41,657,375,585 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 408,199,943,158 | 26,465,403,352 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 20,362,554,279 | 299,467,345 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 13,563,055,469 | 100,539,334 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 6,794,693,781 | 17,127,775 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 4,101,375,125 | 29,649,605 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 7,114,370,794 | 85,678,915 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 21,201,804,054 | 5,875,637,150 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 3822020150.15 |
| HK CSOP swap LETF | notional AUM×\|L\| | None |
| Crypto Binance perps | OI notional | None |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 194496368822.15 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | None | 0.0 | None | 0.0 |
| 005930 | None | 0.0 | None | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | None | None | 263486938.00292706 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | None | None | 47513343.665023215 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | None | None | 3896959.7242741757 | indirect_swap |

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
| 000660 | -0.05 | 168,034,480,991 | 4.0398 | watch |
| 000660 | -0.1 | 336,068,961,983 | 8.0795 | watch |
| 000660 | 0.05 | 168,034,480,991 | 4.0398 | watch |
| 000660 | -0.0196 | 65,869,516,549 | 1.5836 | low |
| 005930 | -0.05 | 123,662,241,315 | 3.8413 | watch |
| 005930 | -0.1 | 247,324,482,629 | 7.6826 | watch |
| 005930 | 0.05 | 123,662,241,315 | 3.8413 | watch |
| 005930 | -0.033 | 81,617,079,268 | 2.5352 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 11273061079.59 | -56.64 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5162 | -75.42 | estimated |
| leverage_exposure_pct_notional | None | 0.4 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 869247.33 | 2026-11-16 | observed |
| 신용잔고 | 262588.41 | 2026-11-16 | observed |
| 신용/예탁금 % | 30.209 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -1419000000000.0 | 26.11.17 | observed |
| retail | 431000000000.0 | 26.11.17 | observed |
| institution | 513400000000.0 | 26.11.17 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 4.606 | 79.82 | 27.553 |
| overseas | 25 | 0.015 | 0.26 | 0.089 |
| sector | 8 | 0.655 | 11.34 | 3.916 |
| single_stock | 16 | 0.495 | 8.58 | 2.96 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
