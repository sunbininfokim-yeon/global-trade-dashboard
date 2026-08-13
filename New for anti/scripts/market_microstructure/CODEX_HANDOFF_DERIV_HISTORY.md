# Codex 요청 — 파생 수급 시계열 히스토리 (2026-08-13)

현재 `derivatives_board_v1.json` / `market_microstructure_v1.json`은 **오늘값 단일 스냅샷**뿐이라
UI에서 시계열 차트를 못 그림. 아래 3개 히스토리 파일을 일별 append 방식으로 추가해줘.
필드명은 기존 스냅샷 파일에서 쓰던 것을 그대로 재사용 (신규 명명 금지 — UI 매핑 깨짐).

## 1. `derivatives_activity_history_v1.jsonl` — 시장 전체 거래활동

한 줄 = 하루. 기존 `derivatives_board_v1.json.kr` 필드 재사용.

```json
{"date": "2026-08-12", "as_of": "2026-08-12", "source": "KRX OpenAPI drv/fut_bydd_trd, opt_bydd_trd", "quality": "observed",
 "kospi200_futures": {"volume": 117061.0, "trading_value_krw": 28804638312500.0},
 "kospi200_options": {"call_volume": 244075.0, "put_volume": 164860.0,
   "call_trading_value_krw": 136370282500.0, "put_trading_value_krw": 152200352500.0,
   "put_call_volume": 0.6754, "put_call_trading_value": 1.1161}}
```

## 2. `leverage_direction_history_v1.jsonl` — 방향별 레버리지

`market_microstructure_v1.json.market_letf_derivatives_ratios.by_direction` 필드 재사용.
방향 키 4개 고정: `long` / `inverse` / `inverse_2x` / `gobus_inverse_2x`.

```json
{"date": "2026-08-12", "as_of": "2026-08-12", "source": "FinanceDataReader/KRX", "quality": "observed",
 "kospi_cash_tv_krw": 24730513259160.0,
 "levered_inverse_etf_tv_over_kospi_cash_tv_pct": 25.547,
 "by_direction": {
   "long":            {"trading_value_krw": 3547503000000.0, "share_of_lev_tv_pct": 56.15, "share_of_kospi_tv_pct": 14.34},
   "inverse":         {"trading_value_krw": 2770491000000.0, "share_of_lev_tv_pct": 25.74, "share_of_kospi_tv_pct": 6.57},
   "inverse_2x":      {"trading_value_krw": 214253000000.0,  "share_of_lev_tv_pct": 3.39,  "share_of_kospi_tv_pct": 0.87},
   "gobus_inverse_2x":{"trading_value_krw": 930059000000.0,  "share_of_lev_tv_pct": 14.72, "share_of_kospi_tv_pct": 3.76}
 }}
```

`share_of_kospi_tv_pct`(코스피 현물 거래대금 대비)와 `share_of_lev_tv_pct`(레버 풀 내부 비중)는
서로 다른 분모다. UI가 둘 다 별도 차트로 그리니 **둘 다** 저장해줘.

## 3. `stock_letf_history_v1.jsonl` — 단일종목 LETF 추이 (하닉 + 삼성전자)

`market_microstructure_v1.json.stocks[]`에 단일종목 LETF 필드가 있는 종목은 **하닉(000660)과
삼성전자(005930) 둘 다**다. 종목별 파일을 나누지 말고, 한 파일에 `ticker`로 구분해서 하루당
종목 수만큼 줄을 씀 (오늘 2종목 관측이면 하루에 2줄). 필드는 `letf_aum_sum_krw`,
`letf_trading_value_krw`, `letf_turnover_ratio`(=LETF거래대금/현물거래대금) 재사용.

```json
{"date": "2026-08-12", "as_of": "2026-08-12", "source": "FinanceDataReader/KRX", "quality": "observed",
 "ticker": "000660",
 "spot_trading_value_krw": 725000000000.0,
 "letf_trading_value_krw": 665707000000.0,
 "letf_turnover_ratio": 0.0918,
 "letf_aum_sum_krw": 3435100000000.0,
 "letf_aum_long_krw": 3301500000000.0,
 "letf_aum_inverse_krw": 133600000000.0,
 "products": [{"ticker": "252670", "name": "KODEX 200선물인버스2X", "aum_krw": null, "trading_value_krw": null}]
}
{"date": "2026-08-12", "as_of": "2026-08-12", "source": "FinanceDataReader/KRX", "quality": "observed",
 "ticker": "005930",
 "spot_trading_value_krw": 4791580972001.0,
 "letf_trading_value_krw": 175057000000.0,
 "letf_turnover_ratio": 0.0365,
 "letf_aum_sum_krw": 2382300000000.0,
 "letf_aum_long_krw": 2356000000000.0,
 "letf_aum_inverse_krw": 26300000000.0
}
```
`products[]` AUM·거래대금 개별 확보 안 되면 필드 자체를 비우지 말고 값만 `null` + 해당 관측치
`quality: "partial"`로 표시. 통짜로 스킵 금지 (UI가 "부분 관측"으로 구분 렌더링함).
새 단일종목 LETF 이름이 추가되면 이 파일에 `ticker`만 늘려서 append — 새 파일 만들 필요 없음.

## 공통 규칙

- **날짜 키는 KST 거래일 기준**, 휴장일은 아예 줄 자체를 넣지 않음 (UI가 임의 보간 안 함)
- 파일당 스키마 검증: 필수 키(`date`, `as_of`, `source`, `quality`) 없으면 append 실패시켜야 함
- 데모/추정값이 섞이면 `quality: "estimated"`로 명시 — UI가 실측과 다른 스타일로 렌더링
- append-only, 기존 줄 수정 금지 (날짜+ticker 중복 시 최신 관측치로 override는 허용)
- 초기 히스토리가 하루치뿐이면 그대로 1줄만 커밋 — UI 쪽에서 "히스토리 축적 중" 배지로 처리함

## UI 쪽(Claude) 진행 상황 — 완료

파일이 아직 없어도 UI는 안 깨짐 (404 → 빈 배열 → "히스토리 축적 중 · 관측 N일" 배지).
파일이 생기는 즉시 코드 수정 없이 아래가 살아남:
- B/C 섹션 카드 클릭 → 시계열 라인 차트 (기본 30거래일, 90일/전체 토글, 모달당 토글 1개)
- 수급 불균형 탭 D 섹션: LETF 비율이 있는 모든 종목 행에 "추이" 버튼 (하닉은 알림-레벨 버킷 모달,
  그 외 — 지금은 삼성전자 — 는 `stock_letf:<ticker>` 제네릭 추이 모달로 라우팅)
- 추정·부분 관측(quality ≠ observed)은 실측과 별도로 카운트해 각주에 표시
