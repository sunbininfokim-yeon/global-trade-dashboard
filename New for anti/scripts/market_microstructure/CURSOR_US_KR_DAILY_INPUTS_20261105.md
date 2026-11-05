# Cursor 전달: 11/6부터 개장 전 방향 엔진 입력 갱신

소유: 데이터 수집/보관은 Cursor, 엔진은 Codex, `.github/workflows/**`·UI·배포는 Claude Code.
수집 데이터가 늘어나도 `us_kr_preopen_20261022_v1.json`의 계수나 사건 정의를 바꾸지 않는다.
추가된 비교 모델도 고정한다. 상세 실행/평가 계약: `US_KR_FORWARD_EVALUATION.md`.

## 매일 반드시 확보

### 1. KRX 15007 콜/풋

private `krx-month-paste`의 기존 경로:

```
data/raw/krx_15007/<KR-source-session>/options_call_buy.csv
data/raw/krx_15007/<KR-source-session>/options_call_sell.csv
data/raw/krx_15007/<KR-source-session>/options_put_buy.csv
data/raw/krx_15007/<KR-source-session>/options_put_sell.csv
```

- 내일 2026-11-06 예측은 한국 직전 거래일 2026-11-05 자료가 필요하다.
- 직전 **61개 KRX 거래일 전체**가 콜/풋 모두 유효해야 한다. 최신 하루만 있어서는 부족하다.
- 기존 `merge_date_folder` / `build_detailed_15007` 파서를 사용한다. 단위나 CSV 해석을 새로 만들지 않는다.
- 파싱된 각 날짜는 `quality=observed`, foreign buy/sell/net, market_total buy/sell 금액(KRW)을 보존한다.
  외국인 buy−sell=net, 시장 buy=sell, 음수·합계 초과·단위 혼동 검사를 통과해야 한다.
- futures 파일은 원래 계약대로 함께 보관하되 현재 고정 방향 모델의 필수 특징은 아니다.
- 누락일은 skip/missing으로 남긴다. 날짜 이동, 0 채움, 이전 관측치의 observed 재표시 금지.
- 원본은 private 저장소/Drive에 보관하고 수집 시각·KR 세션일·SHA256·업로드 commit을 manifest로 남긴다.
  대시보드 공개 저장소에는 private 원본 CSV를 복사하지 않는다.

### 2. 한국 가격 (추론과 사후 정답을 같은 기준으로)

- 대상: `005930`, `000660`, `KOSPI`.
- 추론: 직전 한국 거래일까지 정확한 21개 세션 OHLC. 기존 runner가 네이버 차트에서 수집한다.
- 사후 평가: 평가 시작일 직전 종가부터 각 대상일 시가·고가·저가·종가까지 누적 보관한다.
- CSV/JSON을 따로 공급하면 기존 `candidates[].ticker`, `rows[].date/open/high/low/close/quality` 계약을 지킨다.
- 최신 21일만 저장하고 옛 정답 가격을 지우지 않는다. 사후 평가 스크립트에도 직접 수집 모드가 있다.
- 제공처/가격 조정 방식/시장 범위/수집 시각을 명시한다. KRX 단독 가격과 네이버 가격은 섞지 않는다.
  가격 기준을 바꾸려면 별도 모델 검증이 필요하다.

### 3. 미국 마감 입력

- `QQQ`, `SPY`, `SMH`, `MU`, `NVDA`, `AMD`, `^VIX`의 직전 완료 미국 정규 세션과 그 직전 세션 종가.
- Yahoo `auto_adjust=True` 기준으로 runner가 받는다. 임의 환산/다른 제공처 혼합 금지.
- 미국 세션일·실제 거래소 마감 UTC·수집 시각·제공처/조정 여부·SHA256을 보존한다.
- 미국/한국 휴장일과 DST는 기존 거래소 달력으로 계산한다. 단순 전날 날짜를 쓰지 않는다.
- 미국 옵션 체인이나 호가 자료는 현재 고정 모델의 필수 입력이 아니다.

## 매일 확인할 완료 조건

1. private 원격 commit에서 해당 원본과 manifest를 다시 읽을 수 있는가. 로컬 파일 존재만으로 완료 처리하지 않는다.
2. 기존 runner가 실제 시각 기준 두 시장 마감 이후, 한국 08:30 이전에 실행됐는가.
3. `data/forecasts/us_kr_direction/<target>/<model-prefix>/first.json`이 새로 생겼는가.
4. `comparisons.status=research_preopen_forecast`이고 비교 모델 버전이 일치하는가.
5. 실패면 `attempts/*.json`에 이유가 있으며 어제 점수를 오늘 값으로 넘기지 않았는가.
6. 장 마감 후 평가 입력에 해당 날짜 시가·종가가 들어갔는가. 결측과 가격 수정은 원래 스냅샷을 남긴 채 보고한다.

보고 형식: target / KR source / US source / raw 원격 commit / 모델·비교 ID /
first·attempt 경로 / 생성 시각 / 실패 사유 / 결과 가격 마지막 날짜.

추가 연구용 KOSPI 주식 한정 12008 장기 수급·단위 검증, 삼성전자/하이닉스 개별 파생 일별 이력은
계속 확보할 가치가 있다. 다만 현재 모델이 사용한다고 보고하거나 일일 추론의 필수 조건에 새로 넣지는 않는다.

## 추가 연구 입력 요청 (기존 일일 모델의 필수 입력과 구분)

`OPTION_FLOW_RESEARCH_EXTENSION_20261105.md`에 문헌 근거와 정확한 분석 용도를 정리했다.

- 삼성전자/하이닉스 외국인 일별 순매수 **수량**의 장기 이력(2019년 이후 목표),
  가능하면 매수·매도 각각 수량/실제 거래대금, 주체 범위·기업행동 기준·원천/공개 시각.
  현재 공개 스냅샷 180일만으로 기존 모델과 같은 독립 학습/보정/평가 구간을 만들 수는 없다.
- QQQ 및 반도체 대상의 미국 옵션 원시 체인: 계약 ID, 만기, 행사가, 콜/풋, volume/OI,
  bid/ask/IV, 가능하면 delta/vega와 승수. 미국 세션·원천 timestamp/timezone·OI 기준일·수집일을 따로 보존.
- 현재 Cboe 집계의 거래량/OI는 전체 만기 합, Yahoo 대체는 최근 만기다. 두 범위를 섞지 않는다.
  ATM IV도 만기가 고정된 값이 아니므로 현재 집계의 일별 차분을 연구 패널로 바로 쓰지 않는다.
- 원시 volume/OI 누락과 실제 0을 구분하고 유효 계약 비중을 기록한다.
  buy/sell·open/close·딜러 포지션은 총거래량이나 OI로 만들어 채우지 않는다.

확보한 범위·결측·출처·원격 commit을 먼저 보고한다. 옵션 세부 거래의 새 계약/구매가
필요하면 접근 가능 범위와 조건부터 보고하고, 기존 승인 없는 데이터 구매는 진행하지 않는다.
