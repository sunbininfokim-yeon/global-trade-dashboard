# 2026-11-25 Claude → Cursor: Yahoo 장중 분·시간봉 백필 + 매일 적립

## 한 줄

KOSPI·삼성전자·SK하이닉스(+미국 비교 지표)의 장중 봉을 Yahoo에서 받아 레포에 쌓는다.

- **지금 한 번 백필:** 60분 봉 약 3년, 15분 봉 60거래일, 1분 봉 약 30일
- **이후 매일:** 장 마감 후 그날 봉을 덧붙인다. Yahoo는 과거 분봉을 계속 지우므로, 쌓지 않으면 표본이 늘지 않는다.

용도: 장 전 방향 신호의 "파워"(움직임 크기)와 장중 반전 검증. 자세한 내용은 `docs/ops/handoff/2026-11-25-claude-to-codex-move-power.md`(브랜치 `claude/handoff-move-power`)를 본다.

## 1. 엔드포인트 (키 없음, 2026-11-25 Claude가 직접 확인)

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range={RANGE}&interval={INTERVAL}&includePrePost=false
Header: User-Agent: Mozilla/5.0      ← 없으면 429/403이 잦다
```

- `SYMBOL`은 URL 인코딩한다(`^KS11` → `%5EKS11`).
- 응답 형식: `chart.result[0]` 안에 `timestamp[]`(UTC epoch 초), `indicators.quote[0].{open,high,low,close,volume}[]`, `meta.exchangeTimezoneName`(`Asia/Seoul`), `meta.gmtoffset`가 있다.
- 오류: `chart.error.description` (예: "1h data not available for startTime=... The requested range ...")

### 간격별 한계 (실측)

| interval | 요청 방법 | 받을 수 있는 범위 | 실측 |
|---|---|---|---|
| `60m` | **`range=730d`만 쓴다** | 약 730거래일 (≈3년) | KOSPI·005930·000660 모두 2023-11-23~2026-11-24, 4,381봉, 하루 6봉 |
| `15m` | `range=60d` | 60거래일 | 2026-08-27~11-24, 1,441봉 |
| `5m`, `30m` | `range=60d` | 60거래일 | `period1/2`로 59일을 요청하면 40일만 나온다 → `range` 사용 |
| `1m` | `period1`/`period2`로 **7일 이하 창**을 여러 번 | 최근 약 30일 | 29~22일 전은 성공, 40~33일 전은 오류 |
| `1d` | `range=max` | 수십 년 | 일봉은 이미 있으니 이번 범위가 아님 |

**주의 — `60m`은 `period1/period2`로 요청하지 말 것.** 700~900일 전 구간을 그렇게 요청하면 "not available" 오류가 난다. `range=730d` 한 번에 받는다.

## 2. 대상 심볼

| 키 | Yahoo | 비고 |
|---|---|---|
| kospi | `^KS11` | 지수 (거래량 0일 수 있음) |
| samsung | `005930.KS` | |
| hynix | `000660.KS` | |
| kospi200 | `^KS200` | 존재 확인됨 |
| ewy | `EWY` | 미국장 — `includePrePost=false`, 시간대 America/New_York |
| spy / qqq / smh | `SPY` `QQQ` `SMH` | 미국장 비교용(선택) |

한국 정규장은 09:00~15:30 KST다. 실측한 Yahoo 봉 구성은 다음과 같다.
- 60분 봉: 09:00·10:00·…·14:00 여섯 개가 기본이다.
- 15분 봉: **09:00~14:45, 하루 24봉**이고, 15:00 봉은 날에 따라 있거나 없다.
- 15:20~15:30 종가 동시호가는 별도 봉이 없다. 그래서 **마지막 봉의 close는 공식 종가가 아니다.** 종가는 네이버 일봉을 쓴다.
- `^KS200`은 존재한다(15분 봉 확인).

## 3. 저장 위치·형식

- **위치:** `data/intraday/yahoo/{interval}/{key}/{YYYY-MM}.jsonl`
  - 레포 루트의 `data/`라서 사이트에 배포되지 않는다. Cloudflare 정적 파일 20,000개 한도와 무관하다.
  - **`New for anti/public/` 아래에 두지 말 것.**
- **한 줄 = 한 봉:**
  ```json
  {"ts_utc":"2026-11-24T00:00:00Z","ts_local":"2026-11-24T09:00:00+09:00","session_date":"2026-11-24","interval":"15m","symbol":"^KS11","open":..,"high":..,"low":..,"close":..,"volume":..,"source":"yahoo_chart_v8","collected_at":"2026-11-25T07:40:12Z"}
  ```
- **중복 제거:** 키는 `(symbol, interval, ts_utc)`다. 같은 봉이 다시 오면 **나중 값으로 덮지 말고 기존 값을 유지**한다. 값이 달라졌다면 `revisions` 로그(`data/intraday/yahoo/revisions.jsonl`)에 따로 남긴다. 진행 중인 봉이 확정 봉을 덮는 일을 막기 위해서다.
- **진행 중인 봉 제외:** `ts_local`이 수집 시각 기준으로 아직 끝나지 않은 봉은 버린다. 한국 장중에 실행하면 15:00 봉이 미완성이다.
- **결측 처리:** `open/high/low/close` 중 하나라도 `null`이거나 0 이하이면 그 봉은 저장하지 않는다. 대신 `data/intraday/yahoo/gaps.jsonl`에 날짜와 봉을 기록한다. 0으로 채우지 말 것.
  - 2026-11-23 KOSPI 일봉에서 Yahoo 시가가 0으로 온 사례가 있다.
- **매니페스트:** `data/intraday/yahoo/manifest.json`에 심볼·간격별로 첫 봉, 마지막 봉, 봉 수, 마지막 수집 시각을 둔다.

## 4. 스크립트

`New for anti/scripts/market_microstructure/collect_yahoo_intraday.py`를 만든다(새 파일).

```
python collect_yahoo_intraday.py backfill --intervals 60m,15m,5m,1m --symbols kospi,samsung,hynix,ewy,spy,qqq,smh
python collect_yahoo_intraday.py daily    --intervals 15m,5m,60m,1m  --symbols ...   # 최근분만 덧붙임
```

- **backfill**
  - `60m`: `range=730d`
  - `5m/15m/30m`: `range=60d`
  - `1m`: 오늘부터 7일 창으로 거슬러 올라가며 오류가 날 때까지 받는다(약 4~5번).
- **daily:** `15m/5m/60m`은 `range=5d`, `1m`은 `range=5d` 1회. 중복 제거 규칙대로 합친다.
- **네트워크 실패:** 심볼별로 3회 재시도한다(지수 백오프 2·4·8초). 그래도 실패하면 그 심볼만 건너뛰고 종료 코드 0으로 끝낸다. 실패 사실은 매니페스트의 `last_error`에 남긴다.
- **요청 간격:** 요청 사이에 0.5~1초 쉰다. 동시 요청은 하지 않는다.
- **의존성:** `requests`만 쓴다. `yfinance`는 쓰지 않는다. 응답 형식을 직접 다뤄야 검증이 쉽다.
- **테스트:** `tests/test_collect_yahoo_intraday.py`
  - 시간대 변환: UTC 00:00 → KST 09:00, session_date
  - 중복 시 기존 값 유지 + revisions 기록
  - null·0 봉 제외 + gaps 기록
  - 진행 중인 봉 제외
  - 1m 창 분할(7일 이하)
  - 실제 네트워크 대신 고정 응답(fixture)을 쓴다.

## 5. 워크플로 (Claude 소유 — PR로 올리면 Claude가 리뷰)

`.github/workflows/yahoo_intraday_collect.yml`

- **일정:** `cron: '40 7 * * 1-5'` (16:40 KST, 한국 장 마감 후). 미국 심볼은 다음 날 한국 아침 실행분에 들어오니, 같은 job이 둘 다 처리해도 된다.
- `workflow_dispatch` 입력 `mode: backfill|daily`
- `concurrency: yahoo-intraday`
- **커밋:** `git add data/intraday/yahoo` → 변경이 있으면 커밋 → `bash tools/ops/git_push_retry.sh`
- `timeout-minutes: 15`
- 비밀값은 필요 없다.

## 6. 검증 (PR 본문에 결과 표로)

1. 백필 뒤 심볼·간격별 첫 봉, 마지막 봉, 봉 수를 확인한다. 기대값: 60m 2023-11~ 하루 6봉, 15m 60거래일 하루 24봉(가끔 25).
2. **일봉 대조:** 2026-10-23~11-24 각 날짜에 대해 15분 봉 첫 open을 네이버 일봉 시가와, 마지막 확정 봉 close와 네이버 종가의 차이를 분포로 보고한다. 종가 동시호가 때문에 차이가 나는 게 정상이다. 이 차이로 '장 막판 동시호가 변동'을 따로 볼 수 있다.
   - 네이버 일봉은 v1 엔진이 쓰는 원천이다: `build_kospi200_price_panel.fetch_naver_chart`.
   - 차이가 0.5%를 넘는 날은 목록으로 보고한다. 시가 동시호가 처리 차이일 수 있다.
3. **기존 첫 15분 자료 대조:** `krx-month-paste`의 `data/normalized/regular_first15m_close_*.json`(네이버 분봉, 11/10~11/13 등)과 같은 날 첫 15분 봉 close를 비교한다.
4. 휴장일(KRX 캘린더, `exchange_calendars` XKRX)에 봉이 있으면 경고한다.

## 7. 하지 말 것

- `New for anti/public/` 아래 저장 (배포 파일 수 한도)
- Investing.com 등의 스크래핑 (약관상 자동 수집 금지), 유료 API
- 기존 v1·v2 엔진, 모델 파일, 예측 기록(first/attempt), 공개 카드 수정
- `main` 직접 push, force-push. 병합과 배포는 사용자가 확정한다.

## 8. 다음 단계 (참고)

데이터가 쌓이면 Codex가 "움직임 파워" 분석에 쓴다. 대상은 개장 후 1시간 변동, 시가→종가 반전, 신호 강도별 크기다.
결과는 `docs/ops/handoff/<날짜>-cursor-to-claude-yahoo-intraday.md`로 넘긴다. 내용은 수집 범위, 대조 결과, 남은 문제다.
