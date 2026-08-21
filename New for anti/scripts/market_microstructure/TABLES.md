# Market microstructure tables — 2026-08-19

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
| Conc_top2 (005930+000660) % | 47.6699 | KRX OpenAPI sto/stk_bydd_trd basDd=20260819 | observed |
| Conc_top5 % | 54.7083 | KRX OpenAPI sto/stk_bydd_trd basDd=20260819 | observed |
| Conc_top10 % | 61.4501 | KRX OpenAPI sto/stk_bydd_trd basDd=20260819 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 005380, 373220, 207940, 012450, 105560 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | 1514306985000 | covered_underlyings_spot | estimated |
| retail | -2556972547500 | covered_underlyings_spot | estimated |
| institution | 128650785000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 23,136,613,094,866 | 16,526,152,210.62 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260819 | observed |
| KR single-stock LETF AUM (listed) | 5,825,593,760,580 | 4,161,138,400.41 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 3,397,769,365,318 | 6,408,342,771,947 | 0.0979 | 0.8614 | None |
| 005930 | 2,427,824,395,262 | 5,682,871,706,750 | 0.0272 | 0.4794 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.0975 | mid | 97.6 | 2.4 | 27.4 | -1383258000000 | 469459500000 | 10.8342 |
| 005930 | -0.0782 | low | 99.2 | 0.8 | 8.4 | -1173714547500 | 1044847485000 | 6.7825 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 1,973,153,734,593 | 318,838,607,783 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,182,418,527,656 | 129,781,608,716 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 46,836,105,413 | 1,795,410,590 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 33,547,718,008 | 645,133,997 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 46,629,609,588 | 3,141,029,882 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 11,047,962,550 | 229,256,585 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 22,775,968,088 | 1,029,342,327 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 81,359,739,422 | 171,798,995,796 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,434,981,859,195 | 94,610,207,658 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 853,486,131,632 | 44,240,354,730 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 45,482,377,949 | 1,278,546,007 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 28,379,623,313 | 264,224,035 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 15,819,142,996 | 510,222,817 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 8,431,159,398 | 199,620,525 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 22,932,625,456 | 415,695,337 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 18,311,475,323 | 12,912,938,057 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 8322276800.83 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1712280303.59 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 196366056672.42 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1409643126.15 | 0.0 | 0.308 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.0746 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 704821563.0769231 | 1083798160.8154101 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 141253164.8939749 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 8968654.31375068 | indirect_swap |

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
| 000660 | -0.05 | 356,048,884,416 | 5.556 | watch |
| 000660 | -0.1 | 712,097,768,832 | 11.112 | high |
| 000660 | 0.05 | 356,048,884,416 | 5.556 | watch |
| 000660 | -0.0975 | 694,295,324,612 | 10.8342 | high |
| 005930 | -0.05 | 246,444,734,591 | 4.3366 | watch |
| 005930 | -0.1 | 492,889,469,182 | 8.6732 | watch |
| 005930 | 0.05 | 246,444,734,591 | 4.3366 | watch |
| 005930 | -0.0782 | 385,439,564,900 | 6.7825 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 16526152210.62 | -36.44 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5783 | -72.46 | estimated |
| leverage_exposure_pct_notional | None | 0.6466 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1065750.16 | 2026-08-19 | observed |
| 신용잔고 | 313120.08 | 2026-08-19 | observed |
| 신용/예탁금 % | 29.38 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | 1706800000000.0 | 26.08.20 | observed |
| retail | -2271200000000.0 | 26.08.20 | observed |
| institution | -489500000000.0 | 26.08.20 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 5.483 | 74.92 | 19.435 |
| overseas | 26 | 0.017 | 0.24 | 0.062 |
| sector | 8 | 0.76 | 10.38 | 2.693 |
| single_stock | 16 | 1.058 | 14.46 | 3.752 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
