# Market microstructure tables — 2026-09-15

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
| Conc_top2 (005930+000660) % | 49.1796 | KRX OpenAPI sto/stk_bydd_trd basDd=20260915 | observed |
| Conc_top5 % | 56.1415 | KRX OpenAPI sto/stk_bydd_trd basDd=20260915 | observed |
| Conc_top10 % | 62.4642 | KRX OpenAPI sto/stk_bydd_trd basDd=20260915 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 005380, 207940, 105560, 032830 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -1262130531500 | covered_underlyings_spot | estimated |
| retail | 397138941000 | covered_underlyings_spot | estimated |
| institution | -748734471500 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 22,939,581,109,952 | 16,385,415,078.54 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260915 | observed |
| KR single-stock LETF AUM (listed) | 5,880,752,222,900 | 4,200,537,302.07 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 3,612,080,502,990 | 4,647,356,240,500 | 0.0794 | 0.8127 | None |
| 005930 | 2,268,671,719,910 | 2,849,221,682,500 | 0.0489 | 0.4462 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.0040999999999999995 | mid | 96.1 | 3.9 | 24.2 | 54242240000 | -991752840000 | 0.687 |
| 005930 | -0.002 | low | 99.3 | 0.7 | 2.5 | 342896701000 | -270377691500 | 0.3227 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,017,669,766,675 | 195,003,455,685 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,301,181,264,899 | 82,916,439,206 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 46,965,293,931 | 382,741,005 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 34,173,721,886 | 150,648,425 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 37,378,424,678 | 915,123,595 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 12,008,764,127 | 87,459,425 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 21,966,212,390 | 311,863,550 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 140,737,054,404 | 89,180,500,022 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,280,929,128,172 | 76,519,863,907 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 873,956,724,094 | 58,724,325,219 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 35,344,363,329 | 244,321,585 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 25,470,447,823 | 101,733,985 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 15,337,774,557 | 67,978,500 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 7,594,387,641 | 72,904,545 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 15,020,708,572 | 146,908,225 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 15,018,185,722 | 3,518,040,357 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 8401074604.14 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1402866100.51 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 208680585704.66 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1100228923.08 | 0.0 | 0.3314 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.1487 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 550114461.5384616 | 379676379.5486612 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 41298179.70846127 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 2574704.0173636796 | indirect_swap |

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
| 000660 | -0.05 | 389,355,461,180 | 8.378 | watch |
| 000660 | -0.1 | 778,710,922,360 | 16.756 | high |
| 000660 | 0.05 | 389,355,461,180 | 8.378 | watch |
| 000660 | -0.0040999999999999995 | 31,927,147,817 | 0.687 | low |
| 005930 | -0.05 | 229,870,809,135 | 8.0678 | watch |
| 005930 | -0.1 | 459,741,618,271 | 16.1357 | high |
| 005930 | 0.05 | 229,870,809,135 | 8.0678 | watch |
| 005930 | -0.002 | 9,194,832,365 | 0.3227 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 16385415078.54 | -36.98 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5597 | -73.35 | estimated |
| leverage_exposure_pct_notional | None | 0.6171 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 1068179.08 | 2026-09-14 | observed |
| 신용잔고 | 326230.6 | 2026-09-14 | observed |
| 신용/예탁금 % | 30.541 |  |  |

## 8. KOSPI market investor flows

| actor | net_krw | date | quality |
|-------|--------:|------|---------|
| foreign | -1545800000000.0 | 26.09.15 | observed |
| retail | 859600000000.0 | 26.09.15 | observed |
| institution | -958500000000.0 | 26.09.15 | observed |

## 9. Levered ETF TV by category

이름에 레버리지·인버스·곱버스가 든 상장 ETF의 당일 거래대금이다. 방향은 상품명 분류이며 투자자의 실제 순포지션이 아니다.

| category | n | TV 조 | % of lev TV | % of KOSPI TV |
|----------|--:|------:|------------:|--------------:|
| index | 53 | 3.558 | 75.78 | 18.085 |
| overseas | 26 | 0.016 | 0.34 | 0.081 |
| sector | 8 | 0.616 | 13.12 | 3.13 |
| single_stock | 16 | 0.505 | 10.76 | 2.568 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
