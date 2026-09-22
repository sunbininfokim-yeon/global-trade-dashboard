# Market microstructure tables — 2026-09-21

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
| Conc_top2 (005930+000660) % | 51.2813 | KRX OpenAPI sto/stk_bydd_trd basDd=20260921 | observed |
| Conc_top5 % | 58.5818 | KRX OpenAPI sto/stk_bydd_trd basDd=20260921 | observed |
| Conc_top10 % | 64.5169 | KRX OpenAPI sto/stk_bydd_trd basDd=20260921 | observed |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 | | |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 005380, 207940, 105560, 028260 | | |

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

## 2. Foreign vs retail (paper: foreign vs retail)

| actor | net_krw | scope | quality |
|-------|--------:|-------|---------|
| foreign | 443710492000 | covered_underlyings_spot | estimated |
| retail | -3393171888000 | covered_underlyings_spot | estimated |
| institution | 1326633960000 | covered_underlyings_spot | estimated |

## 3. Leveraged ETF AUM (paper: leverage reset)

| metric | KRW | USD | source | quality |
|--------|----:|----:|--------|---------|
| total levered ETF AUM | 25,525,013,858,252 | 18,232,152,755.89 | KRX OpenAPI etp/etf_bydd_trd names 레버리지|인버스 basDd=20260921 | observed |
| KR single-stock LETF AUM (listed) | 7,072,396,689,951 | 5,051,711,921.39 | sum products | observed |

## 4. Stock LETF turnover & leverage exposure

| ticker | LETF AUM | ADV spot | LETF turnover / ADV | lev_exposure % free float | short_ratio % |
|--------|---------:|---------:|--------------------:|--------------------------:|--------------:|
| 000660 | 4,388,467,270,267 | 5,153,761,949,199 | 0.0731 | 0.8933 | None |
| 005930 | 2,683,929,419,684 | 6,053,449,470,058 | 0.034 | 0.4787 | None |

## 4b. Flow tangle (수급이 어떻게 꼬였는지)

| ticker | day_R | wag_the_dog | long_aum% | inv_aum% | inv_tv% | retail_net | foreign_net | realized IR% |
|--------|------:|:-----------:|----------:|---------:|--------:|-----------:|------------:|-------------:|
| 000660 | 0.0059 | mid | 98.0 | 2.0 | 18.0 | -611362776000 | -674321848000 | 1.045 |
| 005930 | 0.049800000000000004 | low | 99.6 | 0.4 | 5.2 | -2781809112000 | 1118032340000 | 4.4542 |

해석 힌트: `wag_the_dog=high`면 LETF 거래가 현물을 잠식. 인버스 거래비중(`inv_tv%`)이 AUM 비중보다 크면 하락일에 리밸런싱 압력이 비대칭.

## 4c. Product-level LETF (국내, 합산 금지: 홍콩 별도)

| underlying | product | L | AUM | trading_value | structure |
|------------|---------|--:|----:|--------------:|-----------|
| 000660 | 0193T0 KODEX SK하이닉스단일종목레버리지 | 2.0 | 2,491,729,130,016 | 203,776,852,243 | cash |
| 000660 | 0195S0 TIGER SK하이닉스단일종목레버리지 | 2.0 | 1,624,512,242,562 | 102,733,297,791 | cash |
| 000660 | 0194T0 ACE SK하이닉스단일종목레버리지 | 2.0 | 56,810,683,767 | 860,767,750 | cash |
| 000660 | 0192L0 RISE SK하이닉스단일종목레버리지 | 2.0 | 41,690,218,645 | 238,770,110 | cash |
| 000660 | 0197W0 SOL SK하이닉스단일종목레버리지 | 2.0 | 45,669,895,685 | 738,629,950 | cash |
| 000660 | 0194R0 KIWOOM SK하이닉스선물단일종목레버리지 | 2.0 | 13,475,969,088 | 297,093,675 | futures |
| 000660 | 0198D0 1Q SK하이닉스선물단일종목레버리지 | 2.0 | 26,819,213,943 | 281,733,665 | futures |
| 000660 | 0197X0 SOL SK하이닉스선물단일종목인버스2X | -2.0 | 87,759,916,561 | 67,974,044,560 | futures |
| 005930 | 0193W0 KODEX 삼성전자단일종목레버리지 | 2.0 | 1,545,616,086,705 | 112,350,059,049 | cash |
| 005930 | 0195R0 TIGER 삼성전자단일종목레버리지 | 2.0 | 1,011,140,846,216 | 81,236,825,400 | cash |
| 005930 | 0194M0 ACE 삼성전자단일종목레버리지 | 2.0 | 42,540,836,777 | 709,121,362 | cash |
| 005930 | 0192M0 RISE 삼성전자단일종목레버리지 | 2.0 | 30,814,115,788 | 322,280,440 | cash |
| 005930 | 0193K0 PLUS 삼성전자단일종목레버리지 | 2.0 | 14,944,107,932 | 189,557,505 | cash |
| 005930 | 0194N0 KIWOOM 삼성전자선물단일종목레버리지 | 2.0 | 9,188,878,942 | 241,949,580 | futures |
| 005930 | 0198B0 1Q 삼성전자선물단일종목레버리지 | 2.0 | 18,061,703,749 | 317,803,715 | futures |
| 005930 | 0193L0 PLUS 삼성전자선물단일종목인버스2X | -2.0 | 11,622,843,575 | 10,639,518,034 | futures |

## 4d. Global leverage stack (HK + crypto, venue-separated)

venue 분리: KR cash 회전율 식에 HK/US/crypto 합산 금지. 다만 Distortion·Spillover에서는 해외 롱/인버스 노셔널을 1급으로 표시 (스왑 상대 헷지 → 국내 압력).

| venue | metric | USD |
|-------|--------|----:|
| KR single-stock LETF | notional AUM×\|L\| | 10103423842.79 |
| HK CSOP swap LETF | notional AUM×\|L\| | 1402866100.51 |
| Crypto Binance perps | OI notional | 0.0 |
| Crypto Binance perps | 24h quote volume | 0.0 |
| Stack (KR+HK+crypto OI) | sum (reference only) | 210382934943.3 |

| underlying | HK notional USD | Crypto OI USD | HK/spot ADV | Crypto OI/spot ADV |
|------------|----------------:|--------------:|------------:|-------------------:|
| 000660 | 1100228923.08 | 0.0 | 0.2989 | 0.0 |
| 005930 | 302637177.44 | 0.0 | 0.07 | 0.0 |

| HK product | underlying | L | AUM USD | TV USD | impact |
|------------|------------|--:|--------:|-------:|--------|
| 7709.HK CSOP SK Hynix Daily Max (2x) | 000660 | 2.0 | 550114461.5384616 | 332502809.1798122 | indirect_swap |
| 7747.HK CSOP Samsung Electronics Daily Max (2x) | 005930 | 2.0 | 150034691.2820513 | 74010711.48256156 | indirect_swap |
| 7347.HK CSOP Samsung Electronics Daily Max (-2x) | 005930 | -2.0 | 1283897.435897436 | 5365663.359243671 | indirect_swap |

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
| 000660 | -0.05 | 456,398,710,339 | 8.8556 | watch |
| 000660 | -0.1 | 912,797,420,678 | 17.7113 | high |
| 000660 | 0.05 | 456,398,710,339 | 8.8556 | watch |
| 000660 | 0.0059 | 53,855,047,820 | 1.045 | low |
| 005930 | -0.05 | 270,717,510,683 | 4.4721 | watch |
| 005930 | -0.1 | 541,435,021,367 | 8.9442 | watch |
| 005930 | 0.05 | 270,717,510,683 | 4.4721 | watch |
| 005930 | 0.049800000000000004 | 269,634,640,641 | 4.4542 | watch |

## 6. Paper calibration

| field | paper_anchor | model_value | delta_pct | quality |
|-------|-------------:|------------:|----------:|---------|
| levered_etf_aum_usd | 26000000000.0 | 18232152755.89 | -29.88 | observed |
| leverage_exposure_pct_aum_over_ff | 2.1 | 0.5883 | -71.98 | estimated |
| leverage_exposure_pct_notional | None | 0.6723 |  | estimated |

## 7. Deposit & credit (Naver / FreeSIS-style)

금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. UI 기본은 예탁금·신용거래융자·미수·반대매매만 표시. 예탁증권담보융자·대주·광의신용공여(융자+담보)는 원본 필드만 유지·기본 표 제외 (코스피 가격대 수급 설명력 낮음). 반대매매는 시장 전체 미수 대비 금액·비중만 공개.

| metric | 억원 | as_of | quality |
|--------|-----:|-------|---------|
| 고객예탁금 | 983346.48 | 2026-09-18 | observed |
| 신용잔고 | 329146.24 | 2026-09-18 | observed |
| 신용/예탁금 % | 33.472 |  |  |

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
| index | 53 | 2.618 | 74.14 | 9.314 |
| overseas | 26 | 0.015 | 0.42 | 0.052 |
| sector | 8 | 0.387 | 10.97 | 1.379 |
| single_stock | 16 | 0.511 | 14.47 | 1.817 |

## 10. Short interest

| quality | missing |
| source | None |
| note | 공매도 잔고는 이 일일 공개 수집기에서 확인하지 못했다. 값을 추정하지 않는다. |
