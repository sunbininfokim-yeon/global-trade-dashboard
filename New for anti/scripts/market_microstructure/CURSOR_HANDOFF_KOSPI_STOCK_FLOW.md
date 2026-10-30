# Cursor 요청 — KRX 12008 코스피 **주식** 투자자별 거래실적 (2026-09-24)

## 왜

`investor_price_levels_v1.json` › `kospi_index_levels`(시장 미시구조 › 가격대별 체결 › 코스피 지수)는
**유가증권시장 주식** 투자자별 순매수(억원)를 코스피 종가 레벨에 쌓는다. 원래 소스인 네이버
`finance.naver.com/sise/investorDealTrendDay.naver`가 **2026-09-17부터 빈 표**를 돌려줘서
9/16 이후 날짜가 들어오지 않는다. 지금은 9/16까지 발행된 날짜를 그대로 유지하고 "수집 멈춤" 배지를 띄운다.

krx-month-paste의 기존 `krx_12008_kospi_investor`는 **ETF·ETN 포함 유가증권 전체**라 쓸 수 없다.
9/16까지 157일을 대조한 결과 외국인은 거의 같지만 개인·기관이 그날 ETF 거래만큼 서로 반대로 벌어진다
(예: 2026-02-05 개인 네이버 +67,791억 vs 12008 +81,548억). 12008 거래대금 합계가 코스피 주식 거래대금보다
하루 5~17조 크다. 즉 다른 지표다.

## 요청

KRX 12008 「투자자별 거래실적」(MDC0201020301)을 **시장 = 유가증권, 증권구분 = 주식만**(ETF·ETN·ELW 제외),
일별추이, 거래대금으로 받아 krx-month-paste에 새 데이터셋으로 넣어 달라. `KRX_API` 또는 인증 export 어느 쪽이든 좋다.

- 경로: `data/normalized/krx_12008_kospi_stock_investor/year=YYYY/month=MM/part.jsonl.gz`
- manifest: `data/manifests/krx_12008_kospi_stock_investor.json` (기존 radar manifest 형식)
- 행 스키마: 기존 `krx_12008_kospi_investor` 행과 같고, **아래 한 필드를 반드시 추가**:

```json
{"date": "2026-09-17", "dataset": "krx_12008_kospi_stock_investor",
 "security_scope": "stock",
 "query_params": {"market": "KOSPI", "securities": "주식", "metric": "trading_value", "query_type": "일별추이"},
 "retail_buy_krw": ..., "retail_sell_krw": ..., "retail_net_krw": ...,
 "foreign_buy_krw": ..., "foreign_sell_krw": ..., "foreign_net_krw": ...,
 "institution_buy_krw": ..., "institution_sell_krw": ..., "institution_net_krw": ...,
 "collected_at": "…Z", "source_unit": "million_krw", "quality": "observed"}
```

- 빌더는 `security_scope == "stock"`인 행만 읽는다. 없는 행·다른 값은 무시한다.
- 금액 단위 KRW(백만원 ×1e6), 0으로 채우지 않기, 휴장일은 행 없음 — 기존 radar 규칙 그대로.
- `foreign_net_krw`는 네이버 "외국인"과 같은 정의(기타외국인 제외)로. 기타외국인은 `other_foreign_*`에 따로.
- 범위: 최소 2026-01-01 ~ 최신. 가능하면 2019-01-02부터.

## 검증 기준 (넣은 뒤 확인)

9/16 이전 날짜에서 네이버 값과 개인·외국인·기관이 **±수억원 안**에서 맞아야 한다. 대조용 네이버 값은
`investor_price_levels_v1.json` git 이력(커밋 `5fb287a1`, `kospi_index_levels.days`)에 157일치가 있다.

## 대시보드 쪽 (이미 끝남 — Claude)

- `build_investor_price_levels.py`는 `$KRX_MONTH_PASTE_DIR`의 위 데이터셋이 있으면 그것을, 없으면 네이버를,
  둘 다 비면 **이미 발행된 주식 기준 날짜를 유지**한다. 소스는 한 빌드 안에서 섞지 않고, 다른 범위의 과거 블록은 이어받지 않는다.
- 워크플로 `market_microstructure_daily.yml`가 이 경로를 sparse checkout한다. 데이터가 들어오는 다음 평일 배치(06:13 KST)부터 자동 반영.
- `public_extras.kospi_investor_flows`도 같은 데이터셋을 예비 소스로 쓴다.
