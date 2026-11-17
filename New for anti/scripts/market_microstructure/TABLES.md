# Market microstructure tables — 2026-11-16

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
| Conc_top2 (005930+000660) % | 46.6968 | KRX OpenAPI sto/stk_bydd_trd basDd=20261116 | observed |
| Conc_top5 % | 53.6874 | KRX OpenAPI sto/stk_bydd_trd basDd=20261116 | observed |
| Conc_top10 % | 60.4841 | KRX OpenAPI sto/stk_bydd_trd basDd=20261116 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 373220 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 373220, 207940, 009150, 105560, 005380, 032830 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -790046609600 | covered_underlyings_spot | estimated |
| retail | 996548678400 | covered_underlyings_spot | estimated |
| institution | -609636432000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 16,623,901,735,116 | 11,874,215,525.08 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20261116 | observed |
| KR single-stock LETF AUM (listed) | 2,851,422,658,269 | 2,036,730,470.19 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 1,565,384,162,263 | 4,807,316,656,176 | 0.0806 | 0.5315 | None |
| 005930 | 1,286,038,496,006 | 3,225,951,145,096 | 0.0302 | 0.3194 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.0789 | mid | 93.2 | 6.8 | 44.6 | 564063360000 | -178865120000 | 5.8327 |
| 005930 | -0.0447 | low | 98.5 | 1.6 | 5.5 | 432485318400 | -611181489600 | 3.6744 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 852,639,984,870 | 173,755,657,183 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 542,678,020,901 | 38,450,332,425 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 19,222,830,307 | 653,978,505 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 14,248,802,176 | 256,969,619 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 18,516,790,702 | 767,589,217 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 4,130,604,126 | 438,644,345 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 8,177,344,217 | 260,209,157 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 105,769,784,964 | 172,767,516,615 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 763,378,005,903 | 57,470,104,337 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 446,871,882,234 | 33,033,293,775 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 22,189,084,484 | 758,558,581 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 14,441,710,567 | 508,225,155 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 7,251,871,676 | 46,713,225 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 4,377,550,986 | 122,427,877 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 7,603,867,174 | 108,697,435 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 19,924,522,982 | 5,395,519,724 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 4073460940.38 |
| HK CSOP swap LETF | notional AUM×\|L\| | None |
| Crypto Binance perps | OI notional | None |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 194747809612.38 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | None | 0.0 | None | 0.0 |
| 005930 | None | 0.0 | None | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | None | None | 412693228.7061574 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | None | None | 59820686.972878456 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | None | None | 5395518.721681257 | indirect_swap |

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
| 000660 | -0.05 | 177,692,373,219 | 3.6963 | watch |
| 000660 | -0.1 | 355,384,746,438 | 7.3926 | watch |
| 000660 | 0.05 | 177,692,373,219 | 3.6963 | watch |
| 000660 | -0.0789 | 280,398,564,940 | 5.8327 | watch |
| 005930 | -0.05 | 132,588,754,197 | 4.1101 | watch |
| 005930 | -0.1 | 265,177,508,394 | 8.2201 | watch |
| 005930 | 0.05 | 132,588,754,197 | 4.1101 | watch |
| 005930 | -0.0447 | 118,534,346,252 | 3.6744 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 11874215525.08 | -54.33 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5258 | -74.96 | estimated |
| leverage_exposure_pct_notional | None | 0.409 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 874443.79 | 2026-11-13 | observed |
| 신용잔고 | 260005.28 | 2026-11-13 | observed |
| 신용/예탁금 % | 29.734 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -1328700000000.0 | 26.11.16 | observed |
| retail | 1290400000000.0 | 26.11.16 | observed |
| institution | -456200000000.0 | 26.11.16 | observed |

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
