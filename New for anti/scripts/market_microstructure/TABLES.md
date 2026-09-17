# Market microstructure tables — 2026-09-17

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
| Conc_top2 (005930+000660) % | 49.6592 | KRX OpenAPI sto/stk_bydd_trd basDd=20260917 | observed |
| Conc_top5 % | 56.6529 | KRX OpenAPI sto/stk_bydd_trd basDd=20260917 | observed |
| Conc_top10 % | 62.8911 | KRX OpenAPI sto/stk_bydd_trd basDd=20260917 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 005380, 207940, 105560, 028260 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | -1772732487500 | covered_underlyings_spot | estimated |
| retail | 151063722500 | covered_underlyings_spot | estimated |
| institution | -43823425000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 24,111,870,297,603 | 17,222,764,498.29 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260917 | observed |
| KR single-stock LETF AUM (listed) | 6,257,646,837,154 | 4,469,747,740.82 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 3,882,316,681,326 | 4,917,831,824,540 | 0.0659 | 0.846 | None |
| 005930 | 2,375,330,155,828 | 3,004,779,914,636 | 0.0368 | 0.4597 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | -0.008 | mid | 97.8 | 2.2 | 23.8 | 160986720000 | -1224634020000 | 1.3197 |
| 005930 | -0.0039000000000000003 | low | 99.5 | 0.5 | 2.7 | -9922997500 | -548098467500 | 0.6231 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,199,155,378,334 | 169,085,564,610 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,433,739,211,850 | 73,896,816,000 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 50,214,922,058 | 313,407,725 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 36,550,589,572 | 124,085,975 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 40,013,478,210 | 1,405,813,045 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 12,039,294,495 | 113,327,645 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 23,599,862,971 | 1,857,874,590 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 87,003,943,836 | 77,211,466,866 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,327,941,340,870 | 65,324,794,886 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 932,266,202,392 | 41,702,880,193 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 36,696,222,647 | 208,953,005 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 26,487,213,329 | 113,364,515 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 15,929,763,888 | 76,201,785 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 7,919,850,611 | 5,234,795 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 15,645,950,584 | 105,157,680 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 12,443,611,507 | 3,010,453,668 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 8939495481.65 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1402866100.51 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 209219006582.16 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1100228923.08 | 0.0 | 0.3132 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.141 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 550114461.5384616 | 301848913.69691163 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 20076246.771885797 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 984056.8694894513 | indirect_swap |

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
| 000660 | -0.05 | 405,632,456,900 | 8.2482 | watch |
| 000660 | -0.1 | 811,264,913,800 | 16.4964 | high |
| 000660 | 0.05 | 405,632,456,900 | 8.2482 | watch |
| 000660 | -0.008 | 64,901,193,104 | 1.3197 | low |
| 005930 | -0.05 | 240,021,737,884 | 7.988 | watch |
| 005930 | -0.1 | 480,043,475,768 | 15.976 | high |
| 005930 | 0.05 | 240,021,737,884 | 7.988 | watch |
| 005930 | -0.0039000000000000003 | 18,721,695,555 | 0.6231 | low |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 17222764498.29 | -33.76 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5804 | -72.36 | estimated |
| leverage_exposure_pct_notional | None | 0.6414 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 995748.64 | 2026-09-16 | observed |
| 신용잔고 | 330735.25 | 2026-09-16 | observed |
| 신용/예탁금 % | 33.215 |  |  |

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
| index | 53 | 3.558 | 75.78 | 18.085 |
| overseas | 26 | 0.016 | 0.34 | 0.081 |
| sector | 8 | 0.616 | 13.12 | 3.13 |
| single_stock | 16 | 0.505 | 10.76 | 2.568 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
