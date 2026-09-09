# Scenario backtest engine — T25b / Claude 연결 계약

2026-09-07. `scenario.mjs`는 **임의 종목·관찰 변수·기간·조건**을 받는 순수 ESM이다.
천연가스·한전·미쓰이를 하드코딩하지 않는다. 증권사 비공개 시스템을 복제한 것이
아니며, 아래 공개 방법론을 참고한 **비용 차감 전 역사적 전략 연구 도구**다.
기존 포트폴리오 엔진 `index.mjs` 및 Python 계산식을 변경하지 않았다.

## 사용자 흐름과 책임 경계

```text
Claude: 종목 식별 + 기간/조건 입력 + 공개 가격·역사적 FX 조회
  → 브라우저 내 공통 날짜 정렬 / 품질 확인 / 기준통화 환산
Codex: runScenario(input)
  ├─ 자산·요인 관계: 상관, 베타, 방향 가설, 개별 수익률
  └─ 비중이 있으면: 현금/롱숏 원장 → 성과·VaR·낙폭 → 비교/후반 검증
Claude: 같은 결과 객체를 Basic | Expert로 설명
```

| 입력 수준 | 계산 결과 |
|---|---|
| 종목/관찰 변수 + 기간, `strategy` 없음 | 관계·개별 시계열 통계. 전략 성과는 없음 |
| 위 입력 + 롱/숏 비중 | 초기 NAV 100으로 정규화한 전략 수익률·변동성·VaR |
| 위 입력 + `strategy.initialCapital` | 동일한 수익률에 기준통화 금액 손익 추가 |

수익률을 계산하는 데 투자금 자체는 필요 없다. **비중**이 있어야 전략 수익률이
정해진다. 관찰 변수는 매매 포지션이 아니다. 같은 상품을 관찰·매매 모두에 쓰면
서로 다른 ID로 등록한다. 투자금 미입력 시 금액 키는 `null`, 0원이 아니다.

현재 보유계좌 분석(T25), 평균매입가 기반 개인 손익, 가상 전략 백테스트(T25b)는
별개다. 실제 계좌의 신용 원장을 이 가상 초기자본 원장으로 대체하지 않는다.

## API / 실행 가능한 합성 예시

```js
import {runScenario, compareScenarioVariants} from '/portfolio-engine/scenario.mjs';
const input = {
  dates: ['2024-01-08', '2024-01-09', '2024-01-10'],
  baseCurrency: 'KRW',
  assets: [
    {id: 'EXAMPLE_A', prices: [100, 110, 121], baseCurrency: 'KRW',
      priceBasis: 'adjusted_total_return', source: 'SYNTHETIC_TEST_ONLY'},
    {id: 'EXAMPLE_B', prices: [100, 90, 81], baseCurrency: 'KRW',
      priceBasis: 'adjusted_total_return', source: 'SYNTHETIC_TEST_ONLY'},
  ],
  strategy: {weights: [0.5, -0.5], rebalance: 'buy_and_hold'},
};
const result = runScenario(input); // total_return ≈ 0.20, monetary_results=null
const moneyResult = runScenario({...input,
  strategy: {...input.strategy, initialCapital: 10_000_000}}); // P&L ≈ 2m KRW
const relationOnly = runScenario({...input, strategy: null});
```

이 3개 가격은 수학 검사용이다. 실제시장 근거나 충분한 위험 표본이 아니다.
합성 데이터는 사용자 기본 보유목록/성과로 넣지 않는다.

### 입력 계약

- `dates`: 중복 없는 오름차순 ISO 날짜. 공통 평일 종가 관측 3개 이상.
  주말, 비유한값, 결측, 불일치 길이는 오류. 엔진이 자동 전일값 채움/종목 제거를
  하지 않는다. 최소 2개 수익률은 계산 가능성 기준일 뿐, 통계 신뢰성 기준이 아니다.
- `assets`: 고유 `id`, 양수 `prices`, `baseCurrency` 필수.
  가격은 **선택 기준통화로 이미 환산한 배당·분할 반영 총수익 시계열**이어야 한다.
  `source`, `datasetVersion`, `priceBasis`를 기록한다. `priceBasis` 미확인은 경고다.
- `baseCurrency`: 기본 KRW, USD 지원. 자산·비교지수의 baseCurrency 불일치는 오류.
  현지가격 × 해당 날짜의 ‘현지통화 1단위당 기준통화’로 변환한다.
  오늘 환율로 과거 전체를 환산하지 않는다. 관찰 요인은 별도 고유 단위를 유지한다.
- `factors` 선택: `{id, values, change, unit, source, datasetVersion, availability}`.
  `change: 'relative'` 기본: 양수 수준의 변화율. `'difference'`: 절대 변화량,
  음수·0 수준 허용(예: 금리). 금리를 %p로 줄지 소수로 줄지 `unit`에 명시한다.
  `availability: 'known_by_common_close'`는 당시 이용 가능성을 **호출자가 확인했다는
  선언**이지 엔진 인증이 아니다. 없으면 공표시각·수정 이력 미확인 경고.
- `startDate`, `endDate`: 제공 데이터 범위 안. 실제 시작은 요청일 이상 첫 공통일,
  실제 끝은 요청일 이하 마지막 공통일. 최소 2개 수익률 필요. 결과에 요청/실제
  날짜를 모두 반환한다. 조건용 워밍업 이력은 선택 시작일 이전에 제공할 수 있다.
- `strategy.weights`: assets 순서의 NAV 비중, 소수. `0.5`=50% 롱, `-0.5`=50% 숏.
  합계 100% 강제나 절댓값 합 재정규화 없음. 위 예시는 순노출 0%, 총노출 100%다.
  레버리지 상한을 임의로 넣지 않으며 높은 노출은 UI에서 보여 준다.
- `strategy.rebalance`: `buy_and_hold` 기본 / `daily` / `monthly`.
  monthly는 새 달의 **첫 공통 관측 종가**, daily는 매 공통 종가. 비용 없는 가정.
- `strategy.initialCapital`: 생략/null 또는 양수. 기준통화 단위.
- `assets[].shortable`: false인 자산 숏은 오류, 미확인은 경고. true도 대차료·리콜·
  역사적 수량/재고 검증을 의미하지 않는다. 실제 숏 주문을 생성하지 않는다.
- `benchmark` 선택: 자산과 같은 가격 계약, 별도 고유 id. 선택 전략의 실제 계산
  종료일(파산 시 조기 종료)까지 동일한 구간으로 비교한다.
- `hypotheses` 선택: `[{assetId, factorId, expectedSign: -1 | 1}]`.
  동기간 단변량 회귀 부호 일치 여부만 검사. 유의성/인과관계 검정이 아니다.
- `holdoutStart` 선택: 선택 구간 내부 날짜. 이 날짜부터 후반 수익률로 나눈다.
  분할 경계 종가 직전부터 당일 종가 수익도 후반에 들어간다. 전략은 경계에서
  재시작/재최적화하지 않는다. 파산이 분할일보다 앞서면 split은 null이다.
- `risk`: `{confidence:.95, window:60, rfAnn:0, periods:252}` 기본.
  confidence는 (0,1), window는 정수≥2, rfAnn>−1, periods>0.
- `bootstrap`: `{blockLength:5, replications:500, seed:1729}` 기본.
  replications 100..5000. 동일 입력/seed는 동일 결과.

### 조건: 날짜 선택 또는 여러 관찰 변수의 AND / OR

조건 없이 기간만 정하면 시작 종가 진입, 종료 종가 청산이다. 사건 설명문을
입력했다고 자동으로 기업 이익/가격 효과를 추정하지 않는다.

```js
// 실제 이력과 함께 전달할 일반적인 규칙 형태. 특정 종목 추천 아님.
const condition = {
  all: [
    {factorId: 'FX_CHANGE_FACTOR', lookbackBars: 5, threshold: 0.03, operator: 'gte'},
    {factorId: 'RATE_LEVEL_FACTOR', lookbackBars: 5, threshold: -0.25, operator: 'lte'},
  ],
  holdingBars: 10,
};
```

FX 요인은 relative, 금리 요인은 difference/%p로 공급했다는 예시다.
단일 조건 `{factorId, lookbackBars, threshold, operator, holdingBars}`도 된다.
all/any 중첩 깊이 최대 8, 한 그룹 최대 20개. 평가 가능한 과거 길이가 있어야 하며,
**전체 조건이 false→true가 된 종가 다음 공통 종가**에 진입한다.
매수한 다음 관측부터 손익이 발생한다. holdingBars만큼 보유, 동시 겹침/청산 당일
재진입 없음. 보유 중 발생한 신호는 예약하지 않는다. 시작부터 이미 true이면
새 crossing까지 진입하지 않는다. 기간 끝의 미완 보유는 censored로 표시한다.
관계 분석 자체는 선택 기간 전체이며, 조건 일치일만의 상관을 반환하지 않는다.

### 회계·성과·위험의 정확한 의미

| 결과 경로 | 기준 / 주의점 |
|---|---|
| `relationship.correlation` | 자산 단순 수익률 vs 요인 변화량. 가격 수준 상관이 아님; 평탄/표본 부족은 null |
| `relationship.factor_exposures` | 동시점 + 요인 1관측 선행 단변량 OLS. 베타 단위는 입력 요인 단위에 의존 |
| `strategy.curve` | cash + signed units × price = NAV. gross/net 노출은 NAV 대비; 파산 시 null |
| `strategy.metrics.total_return` | 선택 구간 전체 누적 NAV 수익률. 파산이면 중단일까지, 100% 초과 손실 가능 |
| `daily_volatility`, `annualized_volatility` | 단순 수익률 표본표준편차(ddof=1), ×√periods. daily는 공통 관측 bar 의미 |
| `cagr` | n≥periods 및 최종 NAV>0일 때만 복리 연환산, 그 외 null. 미래 예측 아님 |
| `sharpe_arithmetic` | (평균 단순 수익률 − 일환산 무위험수익률) / 표준편차 ×√periods |
| `var_1bar`, `cvar_1bar` | 전체 선택 기간의 역사적 선형 분위수 손실 및 해당 꼬리 평균, 최소 0으로 표시 |
| `max_drawdown`, `recovery_bars` | 초기 NAV도 고점 후보. 최대낙폭 고점→회복 관측수; 미회복은 null |
| `pnl_attribution` | 각 롱/숏 가상 수량의 가격변화 손익 합. 잔여 오차는 attribution_residual |
| `rolling_var` | 현재 관측 제외, 직전 window개 **실현 전략 수익률**로 추정한 VaR와 초과 횟수 |
| `monetary_results.*_amount_on_initial_nav` | 기간의 수익률 위험 통계 × **초기** 투자금. 현재계좌 위험금액 아님 |

`sharpe_arithmetic`은 기존 T25의 CAGR 기반 `sharpe_short`와 **정의가 다르다**.
같은 이름으로 덮어쓰거나 수치를 강제로 맞추지 않는다. 누적 수익은 복리지만
산술 Sharpe를 쓰는 것은 의도한 별도 지표다. 연환산은 관측 주기를 환산하는 표기일
뿐, 변동 국면이 내년에도 계속될 것이라는 예측이 아니다. Basic은 기간 수익·낙폭을
우선 표시하고 연환산 가정을 함께 설명한다. 불규칙 공통일이면 252 가정도 불안정하다.

VaR는 보장된 최대 손실이 아니며 95% 성공 확률도 아니다. 꼬리 표본 수를 표시한다.
여러 달력일 간격의 공통 관측 bar를 무조건 ‘1일 VaR’라 부르지 않는다.
rolling_var는 현재 보유비중 재평가 방식의 규제용 VaR 백테스트가 아니다.
조건 미발생 기간은 이자 0 현금 수익 0으로 성과/위험/승률에 포함된다.

가상 수량은 **총수익 조정지수의 소수 단위**이지 실제 체결 주수/호가가 아니다.
숏은 총수익 시계열의 반대 손익(배당 부담 포함)을 취하는 연구 근사다.
실제 분할/배당 지급일 원장, 거래 최소단위, 선물 승수·만기·롤·증거금,
옵션 가치평가/그릭스, 채권 경과이자·쿠폰 현금흐름은 이 엔진에 없다.
실제 레버리지 ETF는 그 상품 가격을 그대로 넣으며 다시 배수를 곱하지 않는다.
원자재 요인의 상대가격 변화율은 선물의 투자수익률로 간주하지 않는다.

### ‘투자 가치’ 대신 역사적 근거를 분리해 반환

`strategy.assessment`는 공개된 연구용 휴리스틱이다. 투자 등급/추천/유의성 검정이
아니다. 40/60개 관측, 10개 완료 거래라는 기준도 기관 표준이나 수학 정리가 아니다.

- 파산 또는 40개 이상 관측에서 누적 수익≤0: `not_supported_in_period`.
- 후반 관측≥60, 조건 전략은 전체 완료 거래≥10일 때: 기간 수익>0,
  비교지수 초과수익>0, 후반 평균 block-bootstrap 95% 구간 하한>0,
  입력한 방향 가설이 모두 일치해야 `historical_support_only`; 아니면 `mixed_evidence`.
- 나머지는 `insufficient_evidence`.

이는 ‘당시 가격에서 규칙을 적용한 결과’의 요약이다. 완료 거래 10개도 독립 표본은
아니다. `episode_independence_verified=false`, `execution_validated=false`,
`investment_decision=null`, `multiple_testing_adjusted=false`를 유지한다.
공표시각/데이터 품질 경고는 status와 독립이며 긍정 status가 경고를 상쇄하지 않는다.

Bootstrap은 circular moving-block 평균 수익률 구간이며 n<max(40,4×blockLength)이면
미산출. 블록 내부 의존성만 일부 유지한다. 구조 변화·극단 꼬리·여러 번의 전략 탐색을
해결하지 않는다. 후반을 본 뒤 다시 조정했다면 진정한 out-of-sample이 아니다.
지금의 split은 고정 규칙의 전후 비교이지 반복 재학습 walk-forward 최적화가 아니다.

`compareScenarioVariants(base, [{id, overrides}, ...])`는 최대 30개 명시적 변형을
모두 반환한다. overrides는 최상위 전체 필드 교체(중첩 merge 아님). 자동 우승자
선정/최적화 없음. 다른 기간을 비교하면 구간 차이와 모든 결과를 함께 보여 준다.

## Claude가 구현할 화면 및 데이터 연결 / 완료 기준

사용자 최신 요구로 기존 `진단 리포트` 탭을 **시나리오 백테스팅**으로 교체하고,
포트폴리오 직접 입력은 유지한다. 이전 UI_HANDOFF의 ‘진단 리포트 없음’ 원칙은
지키되, 새로운 전략 연구 기능은 이 문서를 따른다. 기존 JSON 리포트를 이름만
바꾸지 않는다. 이번 커밋은 화면을 변경하거나 배포하지 않는다.

- [ ] 빈 종목 목록으로 시작. 예시를 고르면 합성/예시임을 표시. 자동 계산/조회 없음.
- [ ] 자산(롱/숏/비중)과 관찰 변수(거래 아님) 영역 분리. 금액은 선택.
- [ ] 기간 모드 / 조건 모드, AND/OR·lookback·holding·재조정 주기 제공.
- [ ] 과거 가격과 날짜별 환율 공급. `/api/quote`, `/api/futures` 기존 공개 프록시의
  **실제 역사 데이터 지원을 먼저 확인**. 현재가만 있으면 계산 불가 안내.
- [ ] 거래소/티커/상품 유형/통화 확인. 이름이 비슷한 다른 상장상품이나 가스 벤치마크를
  자동 대체하지 않음. ADR·ETF·실물 기초자산을 동일 상품으로 취급하지 않음.
- [ ] 거래소별 휴일·시간대·마감시각·수정주가·FX 공통 정렬 과정과 제거 행 수 노출.
  한 시장 종가가 다른 시장보다 늦으면 같은 날짜만으로 동시 관측이라 가정하지 않음.
- [ ] 공통일 교집합 때문에 상장폐지/신규 상장/정지 이력이 사라질 때 경고하고 확인.
  엔진은 당시 전체 상장 universe를 복원하지 않음(생존편향 미해결).
- [ ] 옵션 동시만기 등 사건은 검증된 거래소별 날짜가 있을 때 사용자 기간/이벤트
  레이블로 표시. 자동 만기 캘린더 수집이나 옵션 손익 엔진은 이번 범위에 없음.
- [ ] Basic | Expert는 **동일 runScenario 결과**만 표시. 토글 시 재계산 금지.
  Basic: 당시 성과, 흔들림, 가장 큰 하락, 함께 움직임, 검증 한계.
  Expert: 단순수익률/NAV/관측수/신뢰수준/추정 창/연환산/거래원장까지 표시.
- [ ] VaR: ‘선택 과거 구간에서 추정한 손실 기준. 더 큰 손실도 가능’이라고 설명.
  데이터 미확인/짧은 표본 경고와 비용 제외 표시는 Basic에서도 숨기지 않음.
- [ ] 오류 시 이전 결과를 지우고 실패 원인 표시. null은 ‘산출 불가’이지 0이 아님.
- [ ] 금액 미입력/입력 간 모든 비율 동일, 금액만 비례하는 UI 테스트.
- [ ] 테스트의 20% buy-and-hold, 21% daily 값을 UI에도 동일하게 표시하는 연결 테스트.
- [ ] 브라우저 모듈 Web Worker에서 계산 가능(대량 bootstrap의 화면 멈춤 방지).
  서버/Cloudflare Worker와 다른 개념이며 사용자 기기에서 실행한다.
- [ ] 보유내역·금액·비중·조건·결과·업로드 파일을 Supabase/API/분석로그/오류추적에
  전송하지 않는다. 순수 엔진에는 fetch/storage/telemetry가 없다.
  공개 가격 조회에는 공개 티커/기간만 전달. 티커 요청 자체는 프록시 운영자가
  볼 수 있으므로 ‘조회 종목까지 완전 익명’이라고 약속하지 않는다.
- [ ] source_manifest + run_config는 로컬 재현용. 자동 업로드하지 않음.

## 검증과 남은 범위

2026-09-07: Node **43/43 통과**, skip 0(기존 T25 21 + T25b 22).
Python oracle 및 기존 1,291개 관측 캐시 대조도 재실행. 새 가격 수집 없음.
기존 Python golden은 **T25 계산** 검증이며 새로운 조건/원장 엔진의 정답지가 아니다.
T25b는 손계산 가능한 합성 기대값으로 누적 P&L·리밸런싱·VaR·낙폭·조건 지연을 검증한다.
실제 기관 백테스터와의 독립 대조 및 실제 다국가 전략 데이터 검증은 아직 없다.

```bash
# 리포지토리 루트. 기본 실행은 Python/cache opt-in 2개가 명시적으로 skip됨.
node --test tests/portfolio-engine/engine.test.mjs tests/portfolio-engine/scenario.test.mjs
# 기존 Python 및 캐시가 있으면 두 검증도 포함:
PORTFOLIO_PYTHON=/absolute/path/to/python-with-numpy-pandas \
PORTFOLIO_CACHE=/absolute/path/to/existing/cache/prices \
node --test tests/portfolio-engine/engine.test.mjs tests/portfolio-engine/scenario.test.mjs
# 실제 브라우저 ESM 검증: 아래 로컬 URL을 브라우저에서 열어 PASS 확인
node tests/portfolio-engine/scenario-serve.mjs
# http://127.0.0.1:8769/tests/portfolio-engine/scenario-browser.html
```

실제 Chromium에서도 PASS 확인: 모듈 import 이후 network/storage API를 막고
20%/21%·선택 금액·관계 모드·입력 불변 검증. 테스트 HTML은 제품 화면이 아니다.
이 검증은 **모듈의 동작**이지 아직 연결되지 않은 전체 사이트의 개인정보 감사가 아니다.

향후 별도 작업: 독립 시장 데이터 fixture, 기관 엔진과 대조, point-in-time 데이터,
체결/대차/유동성/증거금, 거래비용(사용자 요청에 따라 지금 제외), 세금(마지막 단계),
학습-검증 분리한 재최적화 walk-forward, 다중검정 보정, 선물·옵션 전용 원장.

## 참고한 공개 방법론 (2026-09-07 확인)

- 가설/규칙 정의, 기간 성과·위험, 역사적 시나리오, 민감도 및 look-ahead/생존편향
  구분에 참고: [CFA Institute — Backtesting & Simulation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation).
  문헌의 전체 walk-forward 체계를 구현했다는 의미는 아니다.
- 실제 체결·슬리피지·수수료·대차·매수여력·결제·마진콜 같은 실행 모델이 필요함을
  확인: [QuantConnect/LEAN — Reality Modeling](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts).
  현재 엔진은 이 실행 모델을 제공하지 않으므로 실거래 가능성 검증이라고 부르지 않는다.
- 여러 전략을 탐색한 뒤 좋은 결과만 채택하는 문제 참고:
  [CFA Institute — Backtesting digest](https://rpc.cfainstitute.org/research/cfa-digest/2016/03/backtesting-digest-summary).
  현재는 전체 비교 결과 보존/경고까지이며 통계 보정은 미구현이다.
