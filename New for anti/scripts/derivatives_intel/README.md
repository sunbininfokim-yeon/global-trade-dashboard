# derivatives_intel — 옵션 포지셔닝 + 공매도 추적

미국 주식 특정 종목의 **옵션 이상 거래**와 **공매도 현황(Short Volume / Short
Interest)** 을 수집해 `public/data/derivatives_intel_v1.json` 으로 떨어뜨리는
파이프라인. 텔레그램·디스코드 다이제스트 발송 포함.

**전 소스 무료 · API 키 불필요 · 계정 불필요.** 실행 비용 $0.

구조는 `scripts/macro_intel/` 관행을 그대로 따른다 (`build_*.py` CLI + 패키지 +
`config/` + `schemas/` + `tests/`, `cache/` 는 gitignore).

---

## 1. 데이터 소스

| 소스 | 무엇 | 키 | 지연 |
|---|---|---|---|
| **CBOE delayed chain** | 전 종목 옵션 체인 — 볼륨·OI·호가·IV·**그릭스** | 불필요 | ~15분 |
| **FINRA 일별 공매도 거래량** | `CNMSshvol<YYYYMMDD>.txt` | 불필요 | 당일 저녁 |
| **FINRA 통합 공매도 잔고** | consolidatedShortInterest API | 불필요 | 약 3주 |

```
https://cdn.cboe.com/api/global/delayed_quotes/options/TSLA.json
https://cdn.finra.org/equity/regsho/daily/CNMSshvol20260806.txt
https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest
```

> 원 요청에 있던 ChartExchange 스크래핑은 넣지 않았다. 그 사이트 숫자가 결국 위
> FINRA 파일을 가공한 것이라, 원본을 직접 받는 쪽이 빠르고 안 깨지고 ToS 문제도
> 없다.

---

## 2. 이 도구가 할 수 없는 것 (먼저 읽을 것)

무료 소스만 쓰기로 했으므로 **아래 둘은 구조적으로 불가능하다.**

- **Sweep 탐지** — 한 매수자가 수백 ms 안에 여러 거래소 호가를 쓸어담는 패턴.
  체인 스냅샷에는 체결 시각이 없으므로 재구성 자체가 안 된다.
- **체결 방향(aggressor) 판정** — "산 콜"인지 "판 콜"인지. OPRA 체결 레코드에는
  방향 플래그가 없어서, 체결 시점 NBBO에 체결가를 대봐야만 알 수 있다.

둘 다 **OPRA 틱 데이터(유료, Databento 등)** 가 있어야 한다. 그래서 이 파이프라인은
**방향 라벨을 붙이지 않는다.** 없는 정보를 지어내는 게 이 도구가 할 수 있는 가장
해로운 일이라서다.

### 대신 무엇을 보는가 — volume / OI

무료 툴(Barchart 등)이 실제로 돌리는 신호이자, 방향 추측보다 훨씬 단단하다.

> **오늘 거래량이 장 시작 시점 미결제약정(OI)보다 많다** → 있던 물량이 도는 게
> 아니라 **오늘 새로 깔린 포지션**이다.

실제 탐지 예 (2026-08-06):

```
NVDA 08/07 217.5P | vol 130,818 / OI 6,188 (21.1x) | $16.35M | 0DTE
TSLA 08/07 317.5P | vol  73,805 / OI 1,316 (56.1x) | $14.61M | 0DTE
AMD  08/14 507.5C | vol   2,531 / OI    58 (43.6x) |  $3.19M | 7DTE
```

여기에 더해 그릭스가 딸려오므로 **GEX(딜러 감마 노출)**, net delta notional,
P/C 볼륨·프리미엄·OI 비율까지 계산한다. 유료 툴이 파는 지표 대부분이 여기서 나온다.

### 노이즈 제거

- `max_abs_delta: 0.95` — 딥 ITM은 행사·배정·박스스프레드라 방향성 베팅이 아닌데
  프리미엄만 커서 상위권을 다 잡아먹는다. 잘라낸다.
- `max_spread_pct: 0.6` — 호가가 벌어진 비유동 계약 제외.
- `min_volume` / `min_notional` — 잔챙이 제외.

---

## 3. 사용법

```bash
cd "New for anti/scripts/derivatives_intel"
pip install requests pytest
```

```bash
python build_derivatives.py                 # 전체 (약 12초)
python build_derivatives.py --no-chain      # 공매도만
python build_derivatives.py --no-fetch      # 캐시만, 네트워크 0
python build_derivatives.py --print-stats -v
```

### 장중 폴링 감시

```bash
python watch_chain.py --tickers TSLA NVDA --interval 300
```

체인이 15분 지연이라 5분보다 빨리 돌려도 새 정보가 없다 (60초 미만은 clamp).
새로 감지된 계약만 알림하므로 같은 종목이 오후 내내 떠도 한 번만 온다.

### 알림 발송

기본은 **드라이런(콘솔 출력)**. `--send` 를 붙이고 아래 환경변수가 있을 때만
실제로 나간다.

```bash
export TELEGRAM_BOT_TOKEN=...   # + TELEGRAM_CHAT_ID
export DISCORD_WEBHOOK_URL=...
python build_derivatives.py --send
```

### 워치리스트

`config/watchlist.json` 의 `tickers` 를 고치면 끝. 새 종목을 넣으면 다음 실행에
공매도 20일 baseline이 자동 백필된다 (커버리지가 가장 낮은 티커 기준으로 판단).

---

## 4. 출력 계약

`public/data/derivatives_intel_v1.json` · 스키마 `schemas/derivatives_intel_v1.schema.json`

UI가 반드시 지킬 것:

1. **`chain_available: false`** 면 옵션 패널을 **숨긴다.** 0을 렌더링하면
   "이상 거래가 없었다"로 오독된다 (실제로는 데이터를 못 받은 것).
2. **`short_ratio` 를 단독으로 띄우지 않는다.** 항상 `short_ratio_z` 와 같이.
3. **`model.limitations` 를 패널에 노출한다.** sweep·방향을 볼 수 있다고
   오해하게 두면 안 된다.

### short volume ≠ short interest

마켓메이커는 헤지하면서 상시 공매도로 체결을 찍는다. 유동성 좋은 종목의
**40~50% 공매도 비율은 정상 기저 상태**지 공매도 공격이 아니다. 실측:

| | 당일 short ratio | 20일 baseline | z |
|---|---|---|---|
| TSLA | 48.5% | 45.2% | +0.69 |
| AAPL | 50.9% | 49.2% | +0.38 |
| NVDA | 33.3% | 36.5% | −0.69 |

TSLA 48.5%는 절대값만 보면 무섭지만 자기 기저 대비 +0.69σ, 평범한 날이다.
**신호는 비율이 아니라 자기 baseline 대비 편차에 있다.**

`gamma_exposure` 도 마찬가지로 절대 레벨이 아니라 **부호 전환과 크기 변화**를 본다.
딜러가 콜 롱/풋 숏이라는 관행적 가정 위에 계산된 값이라 부호는 모델 가정이다.

---

## 5. 캐시

`cache/derivatives.sqlite` (gitignore).

- `short_volume` — z-score용 20일 baseline. 없는 날짜만 채우므로 첫 실행 ~20초,
  이후 증분 ~12초. 지워도 공개 파일에서 전부 복구된다.
- `unusual_activity` — 일자별 이상 계약. 며칠 연속 뜨는 행사가를
  `recurring_strikes` 로 뽑는다. 하루짜리 굉음과 **쌓이고 있는 포지션**은 다르다.

---

## 6. 테스트

```bash
python -m pytest tests/ -q      # 33 passed, 네트워크·키 불필요
```

픽스처(`tests/fixtures/`)는 실제 CBOE·FINRA 응답에서 잘라온 것이다.

---

## 7. 나중에 유료로 올린다면

틱 단위 sweep·방향 판정이 필요해지면 Databento OPRA(`OPRA.PILLAR`)를 붙이면 된다.
붙일 때 중요한 두 가지만 적어둔다.

- 스키마는 **`tbbo`** 를 쓸 것. `trades` 는 체결에 호가가 안 붙어 방향 판정이
  불가능해서 목적 자체가 무너진다.
- 심볼은 **parent 심볼로지**(`stype_in="parent"`, `TSLA.OPT`)로 구독할 것.
  OPRA 전체 피드는 하루 수 TB다.
- 과금 전 `metadata.get_cost()` 로 견적을 받고 상한을 걸 것.
