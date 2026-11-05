# Market microstructure tables — 2026-11-04

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
| Conc_top2 (005930+000660) % | 48.9129 | KRX OpenAPI sto/stk_bydd_trd basDd=20261104 | observed |
| Conc_top5 % | 56.1542 | KRX OpenAPI sto/stk_bydd_trd basDd=20261104 | observed |
| Conc_top10 % | 62.8846 | KRX OpenAPI sto/stk_bydd_trd basDd=20261104 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 207940, 005380, 105560, 032830 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -842710854000 | covered_underlyings_spot | estimated |
| retail | 824615312000 | covered_underlyings_spot | estimated |
| institution | -303379790000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 19,193,787,369,650 | 13,709,848,121.18 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20261104 | observed |
| KR single-stock LETF AUM (listed) | 4,005,710,293,769 | 2,861,221,638.41 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 2,390,090,853,759 | 6,297,032,987,500 | 0.0955 | 0.651 | None |
| 005930 | 1,615,619,440,010 | 4,802,353,031,949 | 0.0408 | 0.3622 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.0014000000000000002 | mid | 96.5 | 3.5 | 34.5 | 543471176000 | -634797496000 | 0.1138 |
| 005930 | -0.0068000000000000005 | low | 98.8 | 1.2 | 3.4 | 281144136000 | -207913358000 | 0.4686 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 1,357,164,789,729 | 282,840,732,331 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 850,390,376,420 | 105,538,210,228 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 28,387,248,752 | 1,925,271,902 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 21,965,609,043 | 521,802,230 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 28,114,765,955 | 2,199,254,414 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 6,244,706,401 | 527,394,675 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 13,000,420,829 | 259,439,542 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 84,822,936,630 | 207,651,999,740 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 972,934,533,468 | 105,659,578,897 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 554,980,638,472 | 82,799,250,454 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 26,201,315,629 | 328,633,910 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 18,163,769,663 | 302,396,154 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 8,699,011,615 | 266,765,285 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 5,535,590,133 | 38,603,117 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 9,619,374,341 | 174,582,607 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 19,485,206,689 | 6,581,683,551 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 5722443276.81 |
| HK CSOP swap LETF | notional AUM×\|L\| | None |
| Crypto Binance perps | OI notional | None |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 196396791948.81 |

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
| 000660 | -0.05 | 255,973,672,702 | 4.065 | watch |
| 000660 | -0.1 | 511,947,345,404 | 8.13 | watch |
| 000660 | 0.05 | 255,973,672,702 | 4.065 | watch |
| 000660 | -0.0014000000000000002 | 7,167,262,836 | 0.1138 | low |
| 005930 | -0.05 | 165,458,985,339 | 3.4454 | watch |
| 005930 | -0.1 | 330,917,970,678 | 6.8907 | watch |
| 005930 | 0.05 | 165,458,985,339 | 3.4454 | watch |
| 005930 | -0.0068000000000000005 | 22,502,422,006 | 0.4686 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 13709848121.18 | -47.27 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5456 | -74.02 | estimated |
| leverage_exposure_pct_notional | None | 0.4926 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 882412.78 | 2026-11-03 | observed |
| 신용잔고 | 289501.85 | 2026-11-03 | observed |
| 신용/예탁금 % | 32.808 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -2452800000000.0 | 26.11.04 | observed |
| retail | 962900000000.0 | 26.11.04 | observed |
| institution | 1133400000000.0 | 26.11.04 | observed |

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
