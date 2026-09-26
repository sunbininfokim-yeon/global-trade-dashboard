# AI Casino brief — 2026-09-23

_Market Ear / Soc Gen AI Casino closing — quantitative mirror, not advice_

공개 상품 AUM·거래대금 기반 추정. 증권사 고객 레버리지 공시가 아님. 투자 권유 아님.

## 초심자 — 직관 비율

비유: 주차장(코스피 거래)에 차 100대가 들어오면, 그 중 약 25대가 ‘가속 페달 달린 특수차(레버·인버스 ETF)’입니다. 특수차 1대는 일반차 2대 분량의 힘을 씁니다(2배 레버).

- 오늘 코스피 현금 거래 중, 레버·인버스 ETF 거래는 대략 16.6% 수준
- ETF 시장 안에서는 레버·인버스가 약 24.1%
- ‘한 종목’ 레버(삼전·하닉)만 보면 코스피 거래의 약 2.41% — 나머지는 지수/섹터 레버
- 하닉: 현물 거래 100원이면 레버 ETF가 약 9원 같이 움직임(당일 기준)
- 삼전: 현물 100원 대비 레버 ETF 약 4원
- 레버리지 2배 ETF를 100만 원어치 사면, 하이닉스가 1% 움직일 때 그 상품은 대략 2%를 목표로 합니다. 그래서 ‘지갑의 100만 원’이 시장에서는 ‘약 200만 원짜리 베팅’처럼 움직입니다. 우리가 쓰는 노셔널(AUM×2)이 그 의미입니다.
- 시총 쏠림: 삼성+하닉만 코스피의 약 51.7618%

## 전문가 — 상세

- `LETF_turnover = Σ LETF TV / underlying ADV`
- `notional = Σ AUM×|L|×β`
- `TR = Σ AUM×(L²−L)×R ; IR = |TR|/ADV×100`
- `Conc_topN = Σ Marcap TopN / KOSPI total`
- `venue: KR cash wag ≠ HK swap ≠ crypto OI`

## Leverage = notional (1주 ≈ |L|주)

2배 레버 ETF 1좌의 경제적 노출 ≈ 기초자산 2좌. 모델은 AUM이 아니라 AUM×|L|로 센다.

- beginner: 레버리지 2배 ETF를 100만 원어치 사면, 하이닉스가 1% 움직일 때 그 상품은 대략 2%를 목표로 합니다. 그래서 ‘지갑의 100만 원’이 시장에서는 ‘약 200만 원짜리 베팅’처럼 움직입니다. 우리가 쓰는 노셔널(AUM×2)이 그 의미입니다.
- expert: Price target ≈ L×R (daily reset). Exposure stock = AUM×|L|. End-of-day hedge/rebalance notional TR = AUM×(L²−L)×R; IR = |TR|/ADV_spot. Long and inverse TR computed separately then summed.
- formulas: {'notional_exposure': 'Σ AUM × |L| × β', 'daily_rebalance_TR': 'Σ AUM × (L² − L) × R', 'L2_example': 'L=+2 → (L²−L)=2; L=-2 → (L²−L)=6 (인버스가 AUM 대비 리밸런싱 더 큼)'}

## Trading share (당일 거래대금)

| metric | value |
|--------|------:|
| 레버+인버스 / 전체 ETF % | 24.1 |
| 레버+인버스 / KOSPI % | 16.6 |
| 단일종목 LETF / KOSPI % | 2.41 |
| 레버 TV 조 | 3.76 |
| KOSPI TV 조 | 22.62 |

## Product UX (목록 vs 검색)

국내 단일종목 레버/인버스는 소수(삼전·하닉만)라 옆 후보 목록이 맞음. ELW·옵션·개별선물까지 보면 종목이 폭증하므로 그때는 검색/필터. 하이브리드: LETF는 카탈로그, 기타 파생은 검색.

- 지수 레버: KODEX 레버리지 / 인버스 / 200선물인버스2X
- 섹터 레버: 반도체레버리지, 2차전지레버리지 (바스켓 — 개별주 wag와 분모 다름)
- HK: 7709/7747/7347 (swap, KR 합산 금지)
- 기타 파생(검색): ELW, 주식선물, 옵션 OI

## Headlines

### Concentration matters / 집중도

**Conc_top2 51.8%**

삼성+하닉 51.8% · Top5 59.4% · Top10 65.2% · tickers Top5=['005930', '000660', '005935', '402340', '009150'] (분모=KOSPI 전체시총)

> paper: elevated concentration amplifies idiosyncratic + leverage feedback

### Leverage reset / 레버리지 AUM

**$0.0bn KR levered ETF**

KR 레버/인버스 ETF AUM $0.0bn (paper anchor $26.0bn). 단일종목 LETF $0.0bn.

> paper: paper peak ~$53bn → recent ~$26bn; model is live KR listing sum

### Leverage vs free float / 유동시총 대비 레버 비중

**0.0% of KOSPI free float (AUM)**

paper-style AUM/FF = 0.0% (paper 2.1%). 단일종목 LETF AUM/KOSPI FF = 0.0%. 노셔널 ΣAUM×|L|/커버종목 FF = 0.0%. HK·crypto는 분모에 넣지 않음.

> paper: Soc Gen chart ≈ levered ETF AUM / free float (not always ×|L|)

### Foreign vs retail / 외인 vs 개인

**foreign 0.1조 · retail -2.37조**

scope=covered_underlyings_spot · quality=estimated

> paper: who absorbs the other side of leverage flows

### Largest leverage product / 최대 레버 상품

**0193T0 · $0.0bn AUM**

KR KODEX SK하이닉스단일종목레버리지 · underlying 000660 · L=2.0 · notional $0.0bn · KRX LETF — TR/IR · wag-the-dog 대상. (참고: 하이닉스 HK 메인은 7709.HK. 7708은 현재 유니버스/Yahoo에 없음.)

> paper: drill-down: ranked product table

### Hynix wag-the-dog / 하이닉스 ETF 영향도

**LETF/ADV 6.89% · IR 0.0%**

현물 ADV 5.48조 · LETF TV 0.377조 · AUM 0.0조

> paper: YouTube reverse: turnover ratio + short-gamma IR

## Free float — how much is leverage ETF?

유동시총 대비 레버 = (정의1) KR 레버ETF AUM / KOSPI 유동시총 — paper 2.1% 대응. (정의2) Σ AUM×|L|×β / 커버 종목 유동시총. HK·crypto는 KR 유동시총 분모에 합산하지 않음.

| metric | value |
|--------|------:|
| KOSPI free float (USD bn, approx) | 3135.19 |
| KR all levered ETF AUM / KOSPI FF % | 0.0 |
| KR single-stock LETF AUM / KOSPI FF % | 0.0 |
| KR single-stock notional / covered FF % | 0.0 |
| paper anchor % | 2.1 |

## Concentration (시총 TopN → Conc)

Conc_topN = Σ(시총 TopN) / KOSPI 전체시총 ×100. constituent 표는 Top30 보관이어도 분모는 전종목 합; Top10은 시총 정렬로 확정.

| metric | value |
|--------|------:|
| Conc_top2 삼성+하닉 % | 51.7618 |
| Conc_top5 % | 59.384 |
| Conc_top10 % | 65.1655 |
| Top5 tickers | 005930, 000660, 005935, 402340, 009150 |
| Top10 tickers | 005930, 000660, 005935, 402340, 009150, 373220, 005380, 207940, 105560, 028260 |

## Top 3 ETF by AUM/NAV

| # | venue | ticker | name | AUM $bn | notional $bn |
|--:|-------|--------|------|--------:|-------------:|
| 1 | KR | 0193T0 | KODEX SK하이닉스단일종목레버리지 | 0.0 | 0.0 |
| 2 | KR | 0195S0 | TIGER SK하이닉스단일종목레버리지 | 0.0 | 0.0 |
| 3 | KR | 0194T0 | ACE SK하이닉스단일종목레버리지 | 0.0 | 0.0 |

AUM≈NAV×발행좌수 프록시 (KR MarCap / HK Yahoo marketCap)

## Hynix — YouTube wag-the-dog reverse

현물 ADV **5.48조** ($3.91bn) · 시총 $971.55bn · day R 0.012

KR LETF AUM **0.0조** ($0.0bn) · 일거래 **0.377조** · 노셔널 $0.0bn

| YouTube metric | value |
|---------------|------:|
| LETF 일거래대금 / 현물 당일 거래대금 % | 6.89 (mid) |
| LETF AUM / 하이닉스 시총 % | 0.0 |
| LETF AUM×|L| / 유동시총 % | 0.0 |
| 실현 IR (순합 리밸런싱 추정) % | 0.0 |
| 인버스 ETF 거래대금 비중 % | 18.25 |

### Hynix KR LETF Top3 AUM

| ticker | name | L | AUM 조 | day TV 조 |
|--------|------|--:|------:|----------:|
| 0193T0 | KODEX SK하이닉스단일종목레버리지 | 2.0 | 0.000 | 0.196 |
| 0195S0 | TIGER SK하이닉스단일종목레버리지 | 2.0 | 0.000 | 0.110 |
| 0194T0 | ACE SK하이닉스단일종목레버리지 | 2.0 | 0.000 | 0.000 |

HK notional unobserved (운용사 기준일 AUM 또는 당일 목표 배율 미공개 (가변 배율 구간)) · HK turnover 8.52% of KR cash turnover (observed) · crypto OI $0.0bn — 규모 비교용. 스왑→한국 기관 헷지 경로 가능 (YouTube wag reverse / 유튜브 하닉 레버 역산 계열).

## Ranked leverage ETFs (click / open detail)

하이닉스 HK 2x 메인은 CSOP 7709.HK. 7708.HK는 현재 파이프라인/Yahoo 유니버스에 없고, AUM 1위도 7709.

| # | venue | ticker | name | und | L | AUM $bn | notional $bn | impact |
|--:|-------|--------|------|-----|--:|--------:|-------------:|--------|
| 1 | KR | 0193T0 | KODEX SK하이닉스단일종목레버리지 | 000660 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 2 | KR | 0195S0 | TIGER SK하이닉스단일종목레버리지 | 000660 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 3 | KR | 0194T0 | ACE SK하이닉스단일종목레버리지 | 000660 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 4 | KR | 0192L0 | RISE SK하이닉스단일종목레버리지 | 000660 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 5 | KR | 0197W0 | SOL SK하이닉스단일종목레버리지 | 000660 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 6 | KR | 0194R0 | KIWOOM SK하이닉스선물단일종목레버리지 | 000660 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 7 | KR | 0198D0 | 1Q SK하이닉스선물단일종목레버리지 | 000660 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 8 | KR | 0197X0 | SOL SK하이닉스선물단일종목인버스2X | 000660 | -2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 9 | KR | 0193W0 | KODEX 삼성전자단일종목레버리지 | 005930 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 10 | KR | 0195R0 | TIGER 삼성전자단일종목레버리지 | 005930 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 11 | KR | 0194M0 | ACE 삼성전자단일종목레버리지 | 005930 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 12 | KR | 0192M0 | RISE 삼성전자단일종목레버리지 | 005930 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 13 | KR | 0193K0 | PLUS 삼성전자단일종목레버리지 | 005930 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 14 | KR | 0194N0 | KIWOOM 삼성전자선물단일종목레버리지 | 005930 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 15 | KR | 0198B0 | 1Q 삼성전자선물단일종목레버리지 | 005930 | 2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| 16 | KR | 0193L0 | PLUS 삼성전자선물단일종목인버스2X | 005930 | -2.0 | 0.0 | 0.0 | direct_cash_or_futures |
| — | HK | 7709.HK | CSOP SK Hynix Daily Max (2x) | 000660 | — | — | — | indirect_swap |
| — | HK | 7747.HK | CSOP Samsung Electronics Daily Max (2x) | 005930 | — | — | — | indirect_swap |
| — | HK | 7347.HK | CSOP Samsung Electronics Daily Max (-2x) | 005930 | — | — | — | indirect_swap |

## Stock microstructure cards

| ticker | day_R | LETF/ADV | lev% FF | wag | realized IR% |
|--------|------:|---------:|--------:|-----|-------------:|
| 000660 | 0.012 | 0.0689 | 0.0 | mid | 0.0 |
| 005930 | 0.0325 | 0.0282 | 0.0 | low | 0.0 |
