# Market microstructure tables — 2026-11-09

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
| Conc_top2 (005930+000660) % | 46.8367 | KRX OpenAPI sto/stk_bydd_trd basDd=20261109 | observed |
| Conc_top5 % | 53.8557 | KRX OpenAPI sto/stk_bydd_trd basDd=20261109 | observed |
| Conc_top10 % | 60.8657 | KRX OpenAPI sto/stk_bydd_trd basDd=20261109 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 373220 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 373220, 207940, 009150, 005380, 105560, 068270 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -85981740600 | covered_underlyings_spot | estimated |
| retail | -532273271100 | covered_underlyings_spot | estimated |
| institution | 263016179500 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 15,881,221,260,454 | 11,343,729,471.75 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20261109 | observed |
| KR single-stock LETF AUM (listed) | 2,834,704,521,452 | 2,024,788,943.89 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 1,623,335,127,224 | 5,058,042,680,498 | 0.0661 | 0.5434 | None |
| 005930 | 1,211,369,394,228 | 3,790,579,717,830 | 0.0249 | 0.3117 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0034999999999999996 | mid | 93.4 | 6.6 | 41.0 | -376982736000 | 1128048000 | 0.2544 |
| 005930 | 0.0064 | low | 98.0 | 2.1 | 6.9 | -155290535100 | -87109788600 | 0.4258 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 883,582,921,180 | 131,870,082,343 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 569,118,056,168 | 62,703,201,942 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 17,874,462,799 | 580,005,382 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 14,238,337,344 | 337,201,477 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 18,383,479,466 | 1,215,158,352 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 4,134,092,044 | 258,884,125 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 8,446,395,492 | 177,424,542 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 107,557,382,731 | 137,235,488,260 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 722,450,779,901 | 48,551,093,856 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 413,146,631,467 | 38,516,214,392 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 20,013,990,916 | 381,650,075 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 13,439,101,268 | 199,887,975 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 6,451,563,698 | 9,552,812 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 4,052,239,440 | 159,399,280 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 7,041,012,045 | 111,885,799 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 24,774,075,493 | 6,462,814,450 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 4049577887.79 |
| HK CSOP swap LETF | notional AUM×\|L\| | None |
| Crypto Binance perps | OI notional | None |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 194723926559.79 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | None | 0.0 | None | 0.0 |
| 005930 | None | 0.0 | None | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | None | None | 783291314.2618301 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | None | None | 72806855.42347191 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | None | None | 5152285.637672258 | indirect_swap |

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
| 000660 | -0.05 | 183,844,989,269 | 3.6347 | watch |
| 000660 | -0.1 | 367,689,978,537 | 7.2694 | watch |
| 000660 | 0.05 | 183,844,989,269 | 3.6347 | watch |
| 000660 | 0.0034999999999999996 | 12,869,149,249 | 0.2544 | low |
| 005930 | -0.05 | 126,091,754,521 | 3.3265 | watch |
| 005930 | -0.1 | 252,183,509,043 | 6.6529 | watch |
| 005930 | 0.05 | 126,091,754,521 | 3.3265 | watch |
| 005930 | 0.0064 | 16,139,744,579 | 0.4258 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 11343729471.75 | -56.37 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5112 | -75.66 | estimated |
| leverage_exposure_pct_notional | None | 0.4124 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 903342.44 | 2026-11-06 | observed |
| 신용잔고 | 283856.43 | 2026-11-06 | observed |
| 신용/예탁금 % | 31.423 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -525600000000.0 | 26.11.09 | observed |
| retail | -688600000000.0 | 26.11.09 | observed |
| institution | 753500000000.0 | 26.11.09 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 7.758 | 81.08 | 26.766 |
| overseas | 25 | 0.05 | 0.52 | 0.173 |
| sector | 8 | 0.905 | 9.45 | 3.121 |
| single_stock | 16 | 0.856 | 8.94 | 2.952 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
