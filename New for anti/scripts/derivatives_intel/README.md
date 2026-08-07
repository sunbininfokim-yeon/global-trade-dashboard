# derivatives_intel — 옵션 플로우 + 공매도 추적

미국 주식 특정 종목의 **옵션 이상 거래(Options Flow)** 와 **공매도 현황(Short
Volume / Short Interest)** 을 수집해 `public/data/derivatives_intel_v1.json` 으로
떨어뜨리는 파이프라인. 디스코드·텔레그램 다이제스트 발송 포함.

구조는 `scripts/macro_intel/` 관행을 그대로 따른다 (`build_*.py` CLI +
패키지 + `config/` + `schemas/` + `tests/`, `cache/` 는 gitignore).

---

## 1. 무엇이 유료이고 무엇이 공짜인가

| 소스 | 무엇 | 비용 | 키 |
|---|---|---|---|
| **FINRA 일별 공매도 거래량** | `CNMSshvol<YYYYMMDD>.txt` (파이프 구분) | **무료** | 불필요 |
| **FINRA 통합 공매도 잔고** | `api.finra.org` consolidatedShortInterest | **무료** | **불필요** (익명 POST 허용) |
| **Databento OPRA** | 옵션 체결 + 체결 시점 NBBO | 종량제 | `DATABENTO_API_KEY` |

즉 **키 없이도 공매도 파트는 전부 돈다.** `--no-flow` 로 돌리면 비용 0.

> 참고: 원래 요청에 있던 ChartExchange 스크래핑은 넣지 않았다. 그 사이트가
> 보여주는 숫자가 결국 위 FINRA 파일을 가공한 것이라, 원본을 직접 받는 쪽이
> 더 빠르고 안 깨지고 ToS 문제도 없다.

### 옵션 데이터에서 진짜로 중요한 것

OPRA 체결 레코드에는 **매수/매도 방향 플래그가 없다.** 그래서 `trades` 스키마만
받으면 "산 콜"과 "판 콜"을 구분할 수 없고, 이는 옵션 플로우의 존재 이유 자체를
날려버린다. 이 파이프라인이 **`tbbo`** 스키마를 쓰는 이유 — 체결마다 그 순간의
NBBO가 같이 붙어 오므로 체결가를 호가에 대봐서 공격자(aggressor)를 판정할 수 있다.
스프레드 안쪽에 찍힌 체결은 추측하지 않고 `MID`(중립)로 남긴다.

---

## 2. 비용 통제

세 겹으로 막아뒀다.

1. **Parent 심볼로지** — `stype_in="parent"` + `TSLA.OPT` 로 구독하면 TSLA 옵션
   전 종목만 온다. OPRA 전체 피드는 하루 수 TB지만 워치리스트 몇 개는 그에 비하면
   반올림 오차.
2. **사전 견적 + 하드 스톱** — `EodFlowLoader` 는 과금되는 다운로드 **전에**
   `metadata.get_cost()` 로 견적을 받고, `max_cost_usd`(기본 $1.00)를 넘으면
   `CostLimitExceeded` 를 던지고 아무것도 받지 않는다.
3. **EOD 배치 우선** — 장중에 즉시 반응할 필요가 없다면 `build_derivatives.py`
   (장 마감 후 1세션 배치)가 `watch_flow.py`(상시 구독)보다 훨씬 싸다.

`stats.flow_cost_usd` 에 실제 견적이 기록되므로 크레딧 소진 속도를 추적할 수 있다.

---

## 3. 사용법

```bash
cd "New for anti/scripts/derivatives_intel"
pip install requests databento pytest        # databento는 flow 쓸 때만 필요
```

### 공짜로 공매도만 (키 불필요)

```bash
python build_derivatives.py --no-flow --tickers TSLA NVDA
```

### 옵션 플로우까지 (EOD 배치, 비용 상한 $0.50)

```bash
DATABENTO_API_KEY=db-... python build_derivatives.py --max-cost 0.50
```

### 실시간 감시 (장중, 과금 구간)

```bash
DATABENTO_API_KEY=db-... python watch_flow.py --tickers TSLA NVDA --min-notional 2000000
```

### 알림 실제 발송

기본값은 **드라이런(콘솔 출력)** 이다. 실제 발송은 `--send` 를 붙이고 아래 중
하나를 환경변수로 준 경우에만 일어난다.

```bash
export TELEGRAM_BOT_TOKEN=...   # + TELEGRAM_CHAT_ID
export DISCORD_WEBHOOK_URL=...
python build_derivatives.py --no-flow --send
```

주요 플래그: `--no-fetch`(캐시만, 네트워크 0) · `--session YYYY-MM-DD`(플로우
대상일) · `--print-stats` · `-v`.

---

## 4. 출력 계약

`public/data/derivatives_intel_v1.json`, 스키마는 `schemas/derivatives_intel_v1.schema.json`.

UI가 반드시 지켜야 할 두 가지:

- **`flow_available: false`** 이면 옵션 패널을 **숨긴다.** 0을 렌더링하면
  "이상 거래가 없었다"로 오독된다 (실제로는 데이터를 안 받은 것).
- **`short_ratio` 를 단독으로 띄우지 않는다.** 반드시 `short_ratio_z` 와 같이
  보여준다. 아래 이유.

### short volume ≠ short interest

마켓메이커는 헤지하면서 상시 공매도로 체결을 찍는다. 그래서 유동성 좋은 종목의
**40~50% 공매도 비율은 정상 기저 상태**지 공매도 공격이 아니다. 실측 예:

| | 당일 short ratio | 20일 baseline | z |
|---|---|---|---|
| TSLA | 48.5% | 45.2% | +0.69 |
| NVDA | 33.3% | 36.5% | −0.69 |

TSLA 48.5%는 절대값만 보면 무섭지만 자기 기저 대비 +0.69σ, 그냥 평범한 날이다.
**신호는 비율이 아니라 자기 baseline 대비 편차에 있다.**

`short_interest` 는 격주 정산치이고 FINRA가 **약 3주 지연** 발행한다. 최신값이
몇 주 전 날짜인 건 정상이다.

---

## 5. 캐시

`cache/derivatives.sqlite` (gitignore). z-score용 20일 baseline을 쌓아두는 용도라,
매번 FINRA 파일 20개를 다시 받지 않고 없는 날짜만 채운다. 지워도 공개 파일에서
전부 복구된다 — 첫 실행만 ~15초, 이후 증분 실행은 ~5초.

---

## 6. 테스트

```bash
python -m pytest tests/ -q      # 29 passed, 네트워크·키 불필요
```

픽스처는 실제 FINRA 응답에서 잘라온 것이다.
