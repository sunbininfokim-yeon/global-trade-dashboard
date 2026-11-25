# Cursor 요청 — 코스피200 위클리·차근월 옵션 체인 + ETF 순자산 복구 (2026-11-25)

## 왜

시장 미시구조 › 파생 수급 탭에 「코스피200 커버드콜 공급」이 생겼다(`covered_call_supply_v1.json`).
국내 K200 커버드콜 ETF는 2026-09-07 시가총액 8.67조다. 가장 큰 KODEX 200타겟위클리커버드콜(5.96조)을 포함해
대부분 **위클리** 콜을 판다. 그런데 krx-month-paste의 `kospi200_option_oi`(15018)는 **월물 최근월물만** 담고 있다.
그래서 이 매도가 어느 행사가에 쌓이고 IV·스큐를 어떻게 누르는지 볼 수 없다.
3537.HK(CSOP KOSPI 200 커버드콜, 2026-07-31 상장)도 KRX 옵션을 쓴다면 같은 체인에 흔적이 남는다.

## 요청

1. **위클리 옵션 체인**
   - 코스피200 위클리 옵션(목요일·월요일 만기 각각)의 행사가별 시세·미결제약정·IV를 일별로 받는다.
   - 경로: `data/normalized/kospi200_weekly_option_oi/year=YYYY/month=MM/part.jsonl.gz`
   - 행 스키마는 `kospi200_option_oi`와 같게 하고 두 필드를 추가한다: `expiry_date`(YYYY-MM-DD), `series`("weekly_thu" | "weekly_mon").
2. **월물 차근월**: `kospi200_option_oi`에 두 번째 월물도 함께 넣는다. 스키마는 같고 `expiry_or_contract_month`로 구분한다.
3. **ETF 순자산**
   - `etf_eod`(13101)의 `aum_krw`가 2026-09부터 전부 비어 있다(`aum_unavailable=true`).
   - 순자산총액 열이 export에서 빠졌는지 확인하고, 가능하면 복구한다.
   - 지금은 시가총액으로 대신 쓴다.
4. **etf_eod 일별 수집**: 현재 2023년과 2026-07~09 중 72거래일만 있다. 커버드콜 시계열이 이어지도록 일별로 받는다.

규칙은 기존 radar와 같다.
- KRW로 저장하고 0으로 채우지 않는다.
- 휴장일은 행을 넣지 않는다.
- 재수집하면 `collected_at`이 최신인 행을 쓴다.

## 대시보드 쪽 (Claude)

- `build_covered_call_supply.py`가 `etf_eod`로 과거를 채우고 FDR ETF/KR로 매일 이어 붙인다.
- 위 1·2가 들어오면 같은 탭에 두 가지를 추가한다: 행사가별 커버드콜 매도 위치, 위클리 만기 전후 IV 변화.
