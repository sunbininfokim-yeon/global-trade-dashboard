# Market microstructure tables — 2026-11-13

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
| Conc_top2 (005930+000660) % | 47.8286 | KRX OpenAPI sto/stk_bydd_trd basDd=20261113 | observed |
| Conc_top5 % | 54.9885 | KRX OpenAPI sto/stk_bydd_trd basDd=20261113 | observed |
| Conc_top10 % | 61.6352 | KRX OpenAPI sto/stk_bydd_trd basDd=20261113 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 373220 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 373220, 207940, 009150, 105560, 005380, 032830 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -448642160000 | covered_underlyings_spot | estimated |
| retail | 67199860000 | covered_underlyings_spot | estimated |
| institution | -38256712000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 0 | 0.00 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20261113 | partial |
| KR single-stock LETF AUM (listed) | 0 | 0.00 | sum products | partial |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | — | 4,013,966,109,000 | 0.0994 | None | None |
| 005930 | — | 2,688,420,817,000 | 0.0356 | None | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.030299999999999997 | mid | None | None | 39.7 | 8355136000 | -450334656000 | None |
| 005930 | -0.0096 | low | None | None | 4.7 | 58844724000 | 1692496000 | None |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | — | 194,117,189,762 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | — | 44,323,439,776 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | — | 389,606,790 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | — | 687,596,174 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | — | 1,042,498,770 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | — | 186,974,110 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | — | 87,182,705 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | — | 158,294,721,295 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | — | 58,397,033,371 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | — | 32,440,199,895 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | — | 87,658,050 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | — | 63,736,965 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | — | 181,726,900 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | — | 56,051,319 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | — | 46,234,880 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | — | 4,505,130,815 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 0 |
| HK CSOP swap LETF | notional AUM×\|L\| | None |
| Crypto Binance perps | OI notional | None |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 190674348672.0 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | None | 0.0 | None | 0.0 |
| 005930 | None | 0.0 | None | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | None | None | 463243833.0678586 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | None | None | 49097425.3504122 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | None | None | 3807941.6943095266 | indirect_swap |

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

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 0.0 | -100.00 | partial |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.0 | -100.00 | estimated |
| leverage_exposure_pct_notional | None | None |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 922347.21 | 2026-11-12 | observed |
| 신용잔고 | 257728.69 | 2026-11-12 | observed |
| 신용/예탁금 % | 27.943 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -541900000000.0 | 26.11.13 | observed |
| retail | 14500000000.0 | 26.11.13 | observed |
| institution | -5900000000.0 | 26.11.13 | observed |

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
