# P0 Worker handoff — 금융기관 DART와 과거 시계열

이 문서는 Python 재무 엔진에서 안전하게 확정할 수 없는 Worker/API
반영 항목의 명세다. 계정 태그는 실시간 OpenDART 응답을 확인하지 않은
상태에서 추측으로 추가하지 않는다.

## 1. 은행·금융지주 DART 손익계정

### 엔진에서 확정한 정책

- `entity_policy.classify_entity()`는 DART corp code override, KSIC `K64`/`K65`/`K66`,
  또는 금융업 이름 힌트로 금융기관을 fail-closed 분류한다.
- 금융기관의 `REVENUE`는 산업기업 매출이 아니므로 `null`과
  `not_applicable:financial_entity_industrial_revenue`을 반환한다.
- FCF, EBITDA 대용, 순차입금, 산업기업 DCF/EV/PE 모델은 표시하지 않는다.
- 보고된 `OPERATING_INCOME`, 순이익, 자산·자본, ROE/ROA만 금융기관 안전
  표면에 남긴다. 은행식 이자수익·수수료수익을 일반 제조업 매출로 합산하지
  않는다.

### Worker 조사/반영 절차 (Claude 소유)

아래 종목을 각각 **CFS, 연간 사업보고서(11011)** 로
`fnlttSinglAcntAll.json`에서 확인한다.

| 대상 | stock code | 확인할 항목 |
|---|---:|---|
| KB금융 | 105560 | 손익계산서 수익·비용·이익 계정 ID/명칭 |
| 신한지주 | 055550 | 동일 |
| 하나금융지주 | 086790 | 동일 |
| 우리금융지주 | 316140 | 동일 |
| 삼성생명 | 032830 | 보험사 구조 비교용 |

검증 기록에는 `corp_code`, `rcept_no`, `reprt_code`, `fs_div`, `sj_div`,
`account_id`, `account_nm`, `thstrm_amount`, `currency`를 보존한다.

그 결과가 나오기 전에는 `_worker.js`의 일반 `revenue` fallback에 은행식
이자수익·수수료수익 태그를 추가하지 않는다. 합산이 필요해도 다음 조건을
모두 만족해야 한다.

1. 같은 연결 기준·같은 기간·같은 통화인 확인된 구성 계정이 있다.
2. 공시상 해당 구성의 합이 금융지주의 공시 수익 정의와 일치함을 확인한다.
3. 결과 키는 `financial_operating_income` 등 금융 전용 키로 두며,
   산업기업 `revenue`/FCF/DCF 체인에 연결하지 않는다.
4. 원문 `rcept_no`와 합산 규칙 버전을 응답 provenance에 넣는다.

현재 Worker가 일반 매출을 못 찾을 경우 반환할 최소 계약은 다음이다.

```json
{
  "value": null,
  "reason": "not_applicable:financial_entity_industrial_revenue",
  "entity_policy": {"is_financial_entity": true}
}
```

## 2. SK하이닉스(000660) 과거 추이 누락

현재 정적 배포 샘플 `New for anti/public/data/kfa_000660_v1.json`은
`basic_cards.revenue`, `operating_income`, `net_income`, `cfo`, `fcf`가
2025년 한 점만 가진다. 같은 형식의 삼성 샘플은 3개 연도 점을 가진다.
이는 UI 차트 정렬 문제가 아니라 **Worker가 만든 JSON의 데이터 계약 부족**이다.

Python `scripts/dart/`의 기존 `analyze_rows()`는 하나의 OpenDART 응답에 있는
`thstrm_amount`/`frmtrm_amount`/`bfefrmtrm_amount`를 3년 추이로 계산할 수 있다.
하지만 Worker 출력은 현재 2025 value만 materialize했다. 따라서 Python 엔진만
수정해서 이미 배포된 JSON의 과거 추이를 복구할 수 없다.

### Worker 완료 기준

1. 000660에 대해 연도별 2023·2024·2025의 CFS 연간(11011) 응답을 각각 요청한다.
2. 각 연도에서 동일한 계정 매핑·원단위·연결 기준을 적용한다.
3. `basic_cards`의 money 카드마다 최소 두 개 이상의 `{year, end, value}`를
   오름차순 또는 내림차순으로 저장한다. 없는 값은 억지 보간하지 않고
   `null + reason`으로 남긴다.
4. 삼성(005930), 하이닉스(000660), 금융기관 1개를 fixture로 하여 API 응답과
   정적 JSON 모두에 대한 회귀 테스트를 추가한다.
5. 출력에 `series_source: annual_filings` 및 각 점의 `rcept_no` 또는 원문 연도
   provenance를 추가해 UI가 실제 보고서 시계열임을 알 수 있게 한다.

## 3. 통화 handoff

Python 엔진은 `unified_views.currency.calculation_currency`를 모델 통화로,
`display_currency`를 카드 표시 통화로 명시한다. Worker도 다음을 지켜야 한다.

- 미국 SEC 원문 금액·모델 = USD.
- KRW 표시는 `fx.rate`, `fx.source`, `fx.as_of`가 모두 있는 경우에만 변환.
- 외부 시가총액·SOTP 사업부 가치에는 `currency`가 필수다. 라벨 없는 숫자는
  EV/DCF에 투입하지 않는다.
- 한국 DART 기업은 KRW만 허용한다.
