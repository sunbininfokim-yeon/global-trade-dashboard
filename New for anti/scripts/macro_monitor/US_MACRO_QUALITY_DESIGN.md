# US Macro Quality Layer — Design v1

## Sol implementation checkpoint — 2026-08-12

The decision layer is now executable.  It lives in `macro_monitor/us_quality/`
and deliberately stops before repetitive official-series mapping.

- `contracts.py`: release vintage, publication time and point-in-time leakage gate
- `employment.py`: BLS composition labels; ADP kept separate
- `gdp.py`: BEA contribution groups and private-demand composition label
- `fomc.py`: public dissent/roster/vote transition comparison only
- `cpi.py`: relationship-type and current-relevance gate
- `backtest.py`: preregistered lag-evidence status; no lag search or causal claim
- `documents.py`: official evidence and derived summaries stored separately
- `config/us_macro_quality.spec.json`: thresholds fixed before results
- `build_us_macro_quality.py`: builds the separate quality snapshot

The following remain Terra implementation work: BLS/BEA series IDs, historical
release caches, monthly table-row mapping, FOMC/Beige Book document collectors,
and repeated fixture creation.  A CPI hypothesis cannot move beyond
`hypothesis` until those point-in-time histories produce an out-of-sample result.

미국 매크로 모니터에 정책위원회·고용·물가·GDP의 **구성(quality)** 을 추가한다.
목적은 숫자 하나로 경기·물가·정책을 단정하지 않고, 공식 발표 당시 이용 가능한 세부 구성과 근거를 보존하는 것이다.

## 1. 범위와 원칙

### 포함

1. FOMC 회의별 표결·공개 소수의견·투표권 구성 변화
2. ADP와 BLS CES 고용의 산업별 구성
3. CPI 세부항목의 구성·시차 가설·백테스트 결과
4. GDP 지출측 기여도와 민간 내수 중심 성장 여부
5. Fed의 Beige Book, SEP, Monetary Policy Report 원문과 이전 회차 대비 변화

### 제외 (v1)

- 정책금리·주가·CPI의 단일 숫자 예측 또는 투자 신호
- 공개되지 않은 FOMC 참가자의 개인 선호 추정
- ADP와 BLS 수치를 같은 모집단으로 간주하는 단순 합산
- 일본·유럽·영국 데이터 수집

### 필수 원칙

- 모든 관측값은 `published_at`, `reference_period`, `vintage`를 가진다.
- 원문 수치와 모델 해석은 별도 필드로 저장한다.
- `as_of` 이후에 공개·개정된 정보는 해당 시점 백테스트의 입력으로 사용할 수 없다.
- 원문 URL, 문서 제목, 페이지/표 위치, 추출 품질을 남긴다.
- "강한 고용", "끈질긴 물가" 같은 문구는 근거 데이터가 있을 때만 생성한다.

## 2. 산출물과 디렉터리

새 빌더는 기존 `build_macro_monitor.py`와 분리한다. 원문 수집 실패가 기존 매크로 스냅샷 생성을 막지 않도록 한다.

```
scripts/macro_monitor/
  build_us_macro_quality.py
  macro_monitor/us_quality/
    releases.py          # point-in-time release envelope
    fomc_votes.py        # 회의·표결·투표권 roster
    employment.py        # ADP/BLS CES 산업 분해
    inflation.py         # CPI 구성·시차 가설 입력
    gdp.py               # BEA 기여도
    fed_documents.py     # Beige Book / SEP / MPR 원문 목록·추출
    backtest.py          # walk-forward lag validation only
  tests/test_us_macro_quality.py
  tests/fixtures/us_macro_quality/

public/data/us_macro_quality_v1.json
public/data/us_macro_quality_backtest_v1.json
```

원문 PDF/HTML은 `cache/us_macro_quality/`에 저장하고 Git에는 올리지 않는다. 공개 JSON에는 URL·해시·필요한 추출값만 저장한다.

## 3. 공통 point-in-time 계약

모든 관측값과 문서는 아래 envelope를 따른다.

```json
{
  "source_id": "bls_ces|bls_cpi|adp_ner|bea_gdp|fomc|fed_beige_book|fed_sep|fed_mpr",
  "release_id": "고유 ID",
  "published_at": "2026-08-07T12:30:00Z",
  "reference_period": "2026-07",
  "vintage": "first|second|third|revised|current",
  "source_url": "https://...",
  "artifact_sha256": "...",
  "quality": "observed|parsed|manual_review|missing",
  "retrieved_at": "2026-08-07T12:35:00Z"
}
```

- `published_at`은 **데이터 사용 가능 시점**이며 기준월/분기가 아니다.
- 수치가 개정되면 새 release를 추가하고 기존 release를 덮어쓰지 않는다.
- parser는 `quality=parsed`; 표·페이지가 불명확하면 `manual_review`로 낮춘다.

## 4. 모듈 A — FOMC 표결과 공개 소수의견

### 데이터 모델

```json
{
  "meeting_date": "2026-06-17",
  "decision": {"target_range": [4.25, 4.50], "change_bp": 0},
  "eligible_voters": ["..."],
  "votes": [
    {"person_id": "...", "name": "...", "role": "governor", "vote": "for"},
    {"person_id": "...", "name": "...", "role": "president", "vote": "against", "dissent_direction": "easier|tighter|other|unknown", "evidence": "minutes"}
  ],
  "vote_summary": {"for": 10, "against": 1, "dissent_count": 1},
  "roster_changes": [{"person_id": "...", "change": "new_voter|lost_vote|new_member|departed"}]
}
```

### 해석 규칙

- "동결 → 인상 주장"은 **공개 표결 또는 공식 발언으로 증거가 있는 경우에만** 표시한다.
- 회의록의 개인 표결은 기록하지만, 공개되지 않은 참가자의 매파·비둘기파 성향을 추정하지 않는다.
- 소수의견은 `easier`, `tighter`, `other`, `unknown`으로만 분류한다.
- `dissent_count` 변화와 `roster_changes`를 항상 함께 표시해 인원 교체를 정책 전환으로 오독하지 않게 한다.
- FOMC minutes는 회의 약 3주 후 공개되므로, 회의 당일 카드에는 statement 기준 결정만, minutes 공개 후에만 표결 상세를 붙인다.

### UI

- Rates 탭의 `Policy committee` 보조 카드.
- 회의별: 결정·찬성/반대 수·소수의견 방향·투표권 변화·원문 링크.
- 개인별 이력은 "공개 표결 이력"으로 라벨링하고 성향 점수는 v1에서 만들지 않는다.

## 5. 모듈 B — 고용의 질

### 소스와 역할

| 소스 | 역할 | 처리 |
|---|---|---|
| BLS CES Employment Situation | 정본: 비농업·민간·정부·산업별 고용, 평균 주당시간, 평균 시간당 임금 | 월별 point-in-time release 저장 |
| ADP National Employment Report | BLS 이전의 민간 고용 보조 신호 | 별도 패널, BLS와 합산 금지 |
| BLS household survey | 실업률·참가율·고용률 보조 | 헤드라인 교차 확인 |

### 산업 버킷 (초기 고정)

```text
private_cyclical = construction + manufacturing + retail + leisure_hospitality + temp_help
private_defensive = health_care_social_assistance + education + utilities
government = federal + state + local
other_private = information + finance + professional_business + transportation_warehousing + other_services
```

각 bucket에는 CES 원시 series ID 목록을 명시적으로 설정 파일에 둔다. 산업 분류가 바뀌면 설정 버전을 올린다.

### 표시값

- `total_nfp_k`, `private_k`, `government_k`, `private_cyclical_k`, `private_defensive_k`
- `government_share_pct = government_k / total_nfp_k`
- `health_share_pct`, `three_month_diffusion_pct`, `avg_weekly_hours`, `ahe_yoy`
- `adp_private_k`는 별도 source badge와 함께 표기

`employment_quality`는 투자 신호나 단일 점수가 아니라 아래 상태 중 하나로만 표시한다.

```text
private_broadening | private_narrowing | government_supported | defensive_services_led | mixed | insufficient_data
```

상태마다 반드시 해당 월의 구성표와 문장 근거를 연결한다.

## 6. 모듈 C — CPI 구성과 시차 가설

### 초기 대상

| driver/target | 목적 |
|---|---|
| new vehicles → motor vehicle insurance | 보험료의 비용·차량가 시차 가설 |
| used cars and trucks → motor vehicle insurance | 중고차 가격 전이 가설 |
| motor vehicle insurance | 서비스 물가의 후행성 관찰 |
| shelter / OER / rent | CPI 내 후행성이 큰 구성요소 분리 |
| core goods / services ex shelter | 헤드라인 대비 확산 여부 |

### 가설 저장 형식

```json
{
  "hypothesis_id": "new_vehicles_to_auto_insurance",
  "feature_series": "cpi_new_vehicles_mom",
  "target_series": "cpi_motor_vehicle_insurance_mom",
  "candidate_lags_months": [1, 2, 3, 4, 5, 6, 9, 12],
  "direction": "positive|negative|unknown",
  "status": "hypothesis_not_claim",
  "rationale_ko": "가격 전이 가능성의 검증 대상이며 인과 주장 아님"
}
```

가설이 유의하지 않거나 불안정하면 UI는 "관계 불안정"으로 표시한다. 최적 lag 하나만 강조하지 않는다.

## 7. 모듈 D — GDP의 질

BEA의 지출측 기여도를 원문 그대로 보관한다.

```text
personal_consumption
fixed_investment: residential | structures | equipment | intellectual_property
inventory_change
government: federal_defense | federal_nondefense | state_local
exports
imports
final_sales_to_private_domestic_purchasers
```

표시 순서:

1. 실질 GDP 성장률(발표 vintage 포함)
2. 민간 내수 최종판매
3. 기여도 워터폴
4. 재고·정부·순수출의 일회성 기여도

라벨은 `private_demand_led`, `government_inventory_supported`, `external_trade_led`, `mixed`만 사용한다. "좋은 GDP/나쁜 GDP" 단정은 하지 않는다.

## 8. 모듈 E — Fed 공식 문서

| 문서 | 갱신 | 저장할 핵심 |
|---|---|---|
| FOMC statement / minutes | 회의별 | 결정·표결·문구 변화 |
| SEP | 분기별 회의 | 성장·실업·PCE·Core PCE·정책금리 중앙값 및 이전 SEP 대비 변화 |
| Beige Book | 정례 FOMC 약 2주 전 | 전국 요약 + 12개 District의 고용·임금·가격·수요·리스크 태그 |
| Monetary Policy Report | 반기 | 공식 진단·리스크·기준 전망 |

문서 요약은 추출된 문장과 원문 페이지를 같이 저장한다. LLM 요약은 `derived_summary`로 구분하고 원문 사실을 덮어쓰지 않는다.

## 9. 시차 백테스트 프로토콜

### 목적

선행 지표가 이후 CPI 구성요소를 **안정적으로 설명하는지** 검증한다. 인과관계 또는 정책 예측을 증명하지 않는다. QRA의 계획상 기말 현금과 실제 TGA의 차이는 이 백테스트의 target이 아니며, 별도의 사후 설명 기록이다.

### 데이터 규칙

1. feature는 target 발표 전 가장 최근에 공개된 vintage만 사용한다.
2. CPI release와 reference month를 분리한다.
3. 수정값은 처음 공개값(`vintage=first`)과 최신 수정값을 별도 실험으로 보고 섞지 않는다.
4. 결측·정부 셧다운·분류 변경·팬데믹 구간은 명시적 flag로 남긴다.

### 실험

```text
frequency: monthly
horizons: 1, 3, 6, 9, 12 months
validation: expanding-window walk-forward
minimum training observations: 60
baselines: last value, seasonal-naive, AR(1)
models v1: univariate lag regression + regularized distributed lag
```

### 필수 보고 지표

- OOS 표본 수, MAE, RMSE, 방향 적중률, 상관계수
- baseline 대비 개선률
- lag별 성과와 95% bootstrap interval
- 2020년 이전/이후 또는 고물가 국면별 분리 결과
- 데이터 사용 가능 시점 감사표(`feature_published_at <= prediction_at`)

### 통과 기준

- 누수 테스트 100% 통과
- 최소 36개 OOS 관측치
- 단일 lag만 우연히 좋은 경우 채택하지 않음
- baseline 대비 개선이 여러 rolling window와 인접 lag에서 재현될 때만 `supported` 표시
- 그렇지 않으면 `inconclusive` 또는 `unstable` 표시

## 10. 통합 JSON 최소 스키마

```json
{
  "schema_version": "us-macro-quality-v1",
  "as_of": "2026-08-11T00:00:00Z",
  "source": {"kind": "official_releases", "quality": "observed"},
  "policy_committee": {"meetings": [], "latest": {}},
  "employment_quality": {"releases": [], "latest": {}},
  "inflation_quality": {"components": [], "hypotheses": []},
  "gdp_quality": {"releases": [], "latest": {}},
  "official_documents": {"items": []},
  "limitations": []
}
```

`macro_monitor_v1.json`에는 처음에는 각 모듈의 latest summary와 `detail_url`만 연결한다. 대용량 release history와 backtest 결과는 별도 JSON으로 유지한다.

## 11. 구현 순서와 완료 기준

1. **공통 release envelope + fixtures + tests**
2. **FOMC 표결/SEP/문서 목록** — 원문 링크, release time, roster 변화
3. **BLS CES 고용 구성 + ADP 분리 표시**
4. **BEA GDP 기여도 + 민간 내수 라벨**
5. **CPI 구성 데이터** — 아직 예측 카드는 만들지 않음
6. **시차 백테스트** — leakage audit과 baseline을 통과한 가설만 연결
7. **UI** — 기존 growth/inflation/rates 탭에 요약 카드, 상세는 별도 drawer

각 단계는 fixture unit test, schema validation, source URL 검증을 통과해야 한다. 원문 수집 실패 시 기존 매크로 엔진은 성공해야 하며 해당 카드만 `missing`으로 표시한다.

## 12. Cursor 구현 요청의 최소 단위

각 PR은 하나의 모듈만 다룬다.

1. `feat(macro): add point-in-time US release envelope and fixtures`
2. `feat(macro): add FOMC vote and official-doc index`
3. `feat(macro): add BLS/ADP employment-quality panel`
4. `feat(macro): add BEA GDP-contribution quality panel`
5. `feat(macro): add CPI component vintages and lag backtest`

백테스트 PR은 결과가 좋아도 정책·가격 예측 문구를 추가하지 않는다. 먼저 데이터 시점 감사와 baseline 비교 결과를 공개한다.
