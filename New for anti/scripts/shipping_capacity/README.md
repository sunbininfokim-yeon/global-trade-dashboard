# 글로벌 선복량 데이터 프레임워크 v1.7

이 폴더는 유료 AIS/Clarksons 단말 없이 다음 세 질문에 답하기 위한 계산 계층입니다.

1. 전 세계 선대의 선종별 총 선복량은 얼마인가?
2. 특정 항로의 화물 흐름을 유지하려면 얼마의 DWT가 그 항로에 계속 묶여 있어야 하는가?
3. 수에즈·파나마·보스포루스·호르무즈가 막힐 때 통항·백로그·억류·보험 제외로 상업적 가용 선복량이 얼마나 변하는가?

## 숫자의 세 등급

- `observed`: UNCTAD의 연간 세계 선대 DWT, IMF PortWatch의 일일 초크포인트 추정 교역량(metric tonnes).
- `estimated`: 연간 화물톤, 왕복주기, 적재율로 역산한 항로 필요 선복량.
- `scenario`: 실효 봉쇄율, 잔존 통항률, 지속일, 우회/대기/취소, 선적 후 억류 및 보험 제외 비율.

항로 화물톤은 `config/comtrade_route_flows.json`의 UN Comtrade 2024 입력을 우선 사용합니다. 브라질–중국 대두는 해상운송 중량 관측, 컨테이너는 HS4 표본의 kg/USD를 제조업 교역액으로 확장한 프록시, 일부 곡물·원유는 항만권 배분 프록시입니다. API 실패 또는 품질범위 이탈 항로만 `config/routes.json` 시드로 폴백하며 `input_status`와 `data_provenance`가 이를 구분합니다.

## 핵심 산식

```text
왕복주기(일) = 2 × 편도거리(NM) ÷ 선속(kn) ÷ 24 + 왕복 항만일
항로 필요 DWT = 연간 화물톤 × 왕복주기 ÷ (365 × 유효 적재율)
양방향 정기선 필요 DWT = max(방향별 연간 화물톤 ÷ 방향별 적재율)
                         × 왕복주기 ÷ 365
추가 우회 선복량 = 연간 화물톤 ÷ (365 × 적재율)
                 × 우회대상비율 × 우회추가일
선적 후 억류 DWT = 연간 화물톤 ÷ (365 × 적재율)
                 × 대기대상비율 × 선적대기비율 × 억류일
실효 봉쇄율 + 잔존 통항률 = 100%
기간 내 서비스 물량 = 100% - 미해소 backlog - 취소
계획 화물 = 직접 도착 + 우회 도착 + 우회 중 + backlog + 취소
상업적 가용 DWT = 배정 DWT - 선적 후 억류 DWT - 보험 제외 DWT
상업적 선복 갭 = max(0, 정상 서비스 유지 필요 DWT - 상업적 가용 DWT)
```

`duration_days / horizon_days`가 단기 사건의 노출도를 제한합니다. 따라서 28일 분석창에서 7일 봉쇄는 같은 강도의 28일 봉쇄보다 노출 항차가 1/4입니다.

`closure_fraction`은 사용자 시나리오에서 항로 흐름이 차단되는 비율입니다. 예를 들어 시나리오 봉쇄율 80%는 기준 항로 흐름의 20%가 처리된다고 가정합니다. 물리적 완전 봉쇄는 잔존 통항률 0%인 별도 시나리오입니다. 이 값은 PortWatch 관측값과 동일한 개념이 아닙니다.

엔진은 화물을 일별 stock-flow로 추적합니다. 대기 화물은 기간 안에 해소된 양만 서비스 물량으로 되돌리고, 우회 출항분도 추가 항해일 뒤 분석창 안에 도착한 경우만 서비스 완료로 계산합니다. 기간 말까지 남은 화물은 `backlog_cargo_tonnes_horizon`, 아직 항해 중인 화물은 `rerouted_in_transit_cargo_tonnes_horizon`입니다. 이미 선적된 대기분의 DWT는 `trapped_loaded_dwt`, 전쟁위험보험 등으로 상업 운항에서 빠진 DWT는 `insurance_excluded_dwt`로 분리합니다. 이 수치는 개별 AIS 원장이 아니라 명시된 시나리오 가정입니다.

컨테이너 정기선은 같은 선박이 두 방향을 왕복하므로 동향·서향 화물량으로 계산한 선복량을 합산하지 않습니다. 두 방향 가운데 `화물톤 ÷ 적재율`이 큰 방향이 서비스 배치 선복량을 결정합니다.

## 무료 데이터 파이프라인

- 세계 선대 기준: UNCTAD Review of Maritime Transport 2025, Table II.5.
- 항로 화물톤: 공식 UN Comtrade API의 연간 양자 `netWgt`. reporter-partner-flow-HS 셀마다 Water 운송수단을 우선하고, 없을 때만 전체 운송수단 합계를 사용해 중복을 막습니다.
- 현재 초크포인트 이상: IMF PortWatch ArcGIS REST API의 `capacity_container`, `capacity_dry_bulk`, `capacity_tanker`. 이 필드는 선박 DWT와 추정 적재율로 산출한 일일 **추정 교역량(metric tonnes)**이며 관측 DWT가 아닙니다. 최근 7일 평균을 직전 28일 평균과 비교합니다.
- 인접 항만 컨텍스트: IMF PortWatch `Daily_Ports_Data`의 선종별 입항수·추정 수출입량을 국가군별로 합산합니다. 이 공개 레이어에는 정박 대수·대기 시간·대기 선박 DWT가 없으므로 입항량을 backlog로 환산하지 않으며, `portwatch_port_context`는 진단 전용입니다.
- PDF 발간물: UNCTAD·IMO의 설정된 HTTPS PDF를 원문 URL·SHA-256·필수 문구·짧은 추출 근거로 검증합니다. PDF 원본은 저장소에 넣지 않습니다.
- LNG: UNCTAD Table II.5의 2025년 liquefied-gas carrier 100.462m DWT는 LNG와 LPG 합계입니다. LNG 전용 DWT가 아니므로 `lng_fleet.lng_only_dwt`는 검증 전 `null`이며, LNG 항로의 가용선대 분모에 자동 투입하지 않습니다.
- 운임·보험·용선료: 무료로 재배포 가능한 정량 시계열인지부터 `market_signals` 레지스트리에서 검증합니다. Baltic/Worldscale·전쟁위험보험 가격을 무단 스크래핑하거나 0으로 대체하지 않습니다.
- 거리·선속·적재율: 모델 가정 테이블. 나중에 검증된 공개 거리 테이블이 생기면 설정값만 교체.

IMF PortWatch는 주요 통로의 일일 AIS 통항척수와 추정 교역량을 공개하지만, 이것은 개별 선박 원장이나 통항 DWT가 아닙니다. Comtrade 어댑터는 `isNetWgtEstimated` 비중, Water 보고 셀 비중, 전체 운송수단 폴백 셀 수, 배분계수와 허용범위를 provenance에 저장합니다.

`chokepoints_live.*.signal_validation`은 7일/28일 이상 신호가 다음 7일에도 지속되는지 시간순 OLS로 검증합니다. 학습 구간은 앞 80%, 테스트 구간은 뒤 20%이며 테스트 R²·MAE와 단순 지속 예측 MAE를 함께 냅니다. 이는 봉쇄 확률이나 인과 효과 추정이 아니라 신호 지속성 진단입니다.

`chokepoints_live.*.multi_model_analysis`는 730일 이력에서 Linear, Ridge, Random Forest, Gradient Boosting을 비교합니다. 급등 구간의 분모 효과를 제한하기 위해 목표값은 `[-2, 2]` 대칭 변화척도를 사용합니다. 학습 구간 내부의 7표본 purge를 둔 3분할 `TimeSeriesSplit` MAE로 모델을 고릅니다. 마지막 20% 홀드아웃과 별도의 4회 expanding-window 백테스트에서 모두 지속 예측·변화 없음 중 더 강한 단순 기준보다 5% 이상 개선되고 R²가 양수일 때만 탐색적 forecast를 공개합니다. K-Means는 흐름 레짐, Isolation Forest는 현재 이상치 백분위를 제공합니다. 계산 시간과 과적합을 줄이기 위해 호르무즈는 탱커, 나머지 초크포인트는 전체 추정 교역량 대표지표만 학습합니다.

`historical_event_calibration`은 PortWatch 2019년 이후 전체 이력과 공식 사건창을 결합합니다. 사건 직전 28개 관측치를 기준선으로 사용하고, 이동블록 bootstrap 95% 구간·직전 1년 동일길이 placebo·사건 종료 후 7일 평균 90% 회복을 계산합니다. 통항 위축 강도·지속·회복은 보정하지만, 단일 초크포인트 시계열로 우회·대기·취소·보험 제외 비율을 분해할 수는 없으므로 행동 배수는 `prior_not_numerically_identified`로 유지합니다.

`scenario_summary[].behavior_sensitivity`는 우회·대기·취소·선적 후 억류·보험 제외를 독립 난수로 샘플링하지 않습니다. 대신 운영제약·물리봉쇄·상업 전쟁위험·군사적 봉쇄별로 세 개의 이름 있는 공동 경로를 계산하고, 봉쇄율과 잔존 통항률은 고정한 채 결과 최소·최대를 냅니다. 이 범위는 행동 가정의 민감도이며 P10/P90, 신뢰구간, 사건확률이 아닙니다.

보험 공개자료는 세 수준으로 구분합니다. LMA/IUA JWC Listed Areas는 추가 전쟁위험보험이 요구될 수 있는 지역을 공개하지만 실제 요율은 계약별 협상입니다. IUMI는 전 세계 보험료·손해율 집계를 공개하고 IMO는 사건·안전·통항 및 보험비용 상황을 제공합니다. 개별 항로 추가보험료, 선박별 인수 가능 여부와 거절률은 공개 시계열이 없으므로 `insurance_unavailable_share`를 관측값으로 표시하거나 자동 보정하지 않습니다.

## 실행

기본 계산 엔진은 외부 패키지가 필요 없습니다. PortWatch 다중모델 검증은 NumPy와 scikit-learn을 사용하며, 없으면 `dependency_missing`과 `descriptive_only`로 안전하게 폴백합니다.

```bash
python3 -m pip install -r requirements-ml.txt
```

```bash
python3 build_snapshot.py
python3 -m shipping_capacity.historical_calibration
python3 -m unittest discover -s tests -v
python3 validate_model.py
python3 validate_schema.py
```

공개 PDF 원천을 갱신하려면 `pypdf`가 포함된 의존성을 설치한 뒤 실행합니다.

```bash
python3 -m shipping_capacity.pdf_reports
```

PortWatch 인접 항만 관측은 초크포인트 관측과 별도로 선택 실행합니다.

```bash
python3 build_snapshot.py --fetch-portwatch-port-context
```

Comtrade 2019–2024 이력은 현재 연도 입력과 별도 파일에 저장합니다. API 키는 환경변수 또는 로컬 key file만 사용하며 결과 JSON·로그·Git에는 저장하지 않습니다. 통신 실패 후 특정 연도만 재실행해도 기존 연도를 보존합니다.

```bash
export COMTRADE_SUBSCRIPTION_KEY='...'
python3 -m shipping_capacity.comtrade_routes --history
python3 -m shipping_capacity.comtrade_routes --history --history-period 2021
unset COMTRADE_SUBSCRIPTION_KEY
```

`validate_model.py`는 공개 프리셋을 바꾸지 않고 봉쇄율·기간·보험 제외·억류와 감속·개조 휴항의 임시 경계값을 조합해 회계등식·단조성을 검사합니다. 또한 최신 스냅샷에 포함된 7표본 purge, 4회 expanding-window PortWatch 백테스트와 역사 사건 보정의 회계·신뢰구간·식별경계 검사를 `generated/validation_report.json`으로 요약합니다.

실시간 PortWatch를 포함하려면 네트워크 가능한 환경에서 실행합니다.

```bash
python3 build_snapshot.py --fetch-portwatch \
  --fetch-container-context \
  --output "../../public/data/shipping_capacity_v1.json"
```

`--fetch-portwatch`는 키 없는 공식 화물 참고(`official_cargo_monitor`)와 호르무즈 미포착 흐름 역산 원장(`hormuz_reconstruction`)도 함께 갱신합니다. 홍해 우회로 근거(`hormuz_bypass_monitor`: 얀부항 PortWatch 탱커 활동, EIA 해협별 원유 비교, `config/hormuz_bypass.json`의 출처 달린 위협 사건 기록)도 같은 실행에서 갱신됩니다. 공식 자료만 따로 갱신하려면 `--fetch-official-cargo --fetch-reconstruction`을 씁니다. 위협 사건 기록은 수기이며 `reviewed_at`이 45일을 넘기면 화면이 "기록 검토 필요"로 바뀝니다 — 사건을 추가·확인할 때 이 날짜를 갱신합니다. 역산 원장은 `HORMUZ_UNOBSERVED_FLOW_RESEARCH.md`의 오만만 질량수지·생산국/수입국 월간 대조·Sentinel-1 촬영 커버리지를 구현하며, 같은 경계·기간·품목의 배럴 입력이 모두 갖춰지기 전에는 미포착 물량을 `null`로 둡니다.

생성물은 동일 `bundle_id`를 공유하는 세 파일로 분리합니다.

- `shipping_capacity_v1.json`: 화면 전용 경량 snapshot.
- `shipping_capacity_diagnostics_v1.json`: 항로 stress timeline, 환경 반응범위, 모델 진단.
- `shipping_capacity_backtests_v1.json`: 공식 사건 관측과 역사 백테스트.

화면 JSON의 주요 경로:

- `fleet.fleet_by_type[]`: 세계 선대 관측 기준.
- `routes[].baseline`: 항로별 필요 DWT와 P10/P50/P90.
- `routes[].operational_profile`: 정상 편도 거리·항해일·왕복주기와 초크포인트별 우회 추가 거리·추가 항해일. 모두 항로 설정 가정이며 실제 선사 스케줄이 아닙니다.
- `routes[].stress_tests[]`: 진단 JSON에 해당 항로가 노출된 시나리오만 수록.
- `routes[].stress_tests[].daily_flow_timeline[]`: 직접 도착·우회 출항/도착/항해 중·대기열 유입/해소·취소의 일별 stock-flow.
- `routes[].live_observed[]`: 최근 7일 추정 교역량 감소율을 7일 항로 충격으로 적용한 결과. 관측창과 분석창이 모두 7일이며 물리적 봉쇄율이나 관측 DWT가 아닙니다.
- `routes[].live_persistence_28d[]`: 같은 최근 7일 감소율이 28일 내내 지속된다고 가정한 별도 스트레스 시나리오. 관측 결과가 아닙니다.
- `live_display[]`: UI가 그대로 읽는 관측 신호 계약. 호르무즈는 `추정 교역량 감소율 / 최근 7일 탱커 추정 교역량 기준 / 잔존 추정 교역량` 순서로 표시합니다.
- `chokepoints_live[id].history[]`: 대표 지표의 PortWatch 일자·추정 교역량 관측값입니다. `metric_histories.<all|container|dry_bulk|tanker>.history[]`에는 선종별 관측 이력이 별도로 있습니다. 화면 JSON은 각각 최근 180개 관측만 두고 `history_source_point_count`로 원본 730개 수집 여부를 표시하며, 진단 JSON에는 전체 이력을 보존합니다. 보간·예시값을 넣지 않습니다.
- `live_data_quality`: 최신 관측의 7일 freshness 기준, stale·fallback 개수. stale 관측은 화면에 기준일과 경고를 함께 표시합니다.
- `comtrade_routes`: 항로 입력 갱신 상태·기준연도·경로 수. 상세 출처와 불확실성은 각 `routes[].data_provenance`에 있습니다.
- `comtrade_routes.history`: 2019–2024 수집 상태와 연도 범위. 상세 관측·품질오류·각 항로 first-to-last 변화율은 진단 JSON `comtrade_route_history`에만 둡니다.
- `portwatch_port_context`: 호르무즈·수에즈·파나마 인접 항만의 공개 입항/수출입 관측. `waiting_anchorage_status`가 `not_published...`이면 대기·정박 수치는 이 데이터로 제공되지 않는다는 뜻입니다.
- `market_signals`: 운임·용선·전쟁보험 관련 공개 원천의 접근권·자동화 가능 여부. 현재는 허가 없는 상업 가격을 사용하지 않는 방어적 레지스트리입니다.
- `pdf_reports`: 마지막으로 성공한 공식 PDF의 checksum·문구 검증 상태. 화면에는 상태만, 추출 근거는 진단 JSON에 보관합니다.
- `lng_fleet`: UNCTAD liquefied-gas carrier 합계와 LNG 전용 DWT의 식별 경계를 함께 표시합니다.
- `ui_scenario_grid.rows[]`: 봉쇄율 0/25/50/75/80/100% × 지속일 7/14/28일의 Python 사전 계산 결과. 브라우저는 모델식을 재구현하지 않습니다.
- `ui_scenario_grid.rows[].summary`: 추가 흡수 DWT와 함께 `affected_allocated_dwt_with_reserve` 및 `relevant_global_type_fleet_dwt` 두 분모와 각각의 비율을 제공합니다. 전자는 대표 항로 모델 배치량 합, 후자는 영향 선종의 세계 선대를 선종별 한 번만 합한 값입니다.
- `event_response_profiles`: 운영제약·물리봉쇄·전쟁위험별 우회/대기/취소 행동 prior. 역사 사건으로 통항 강도는 보정했지만 이 행동 배수 자체는 관측계수가 아닙니다.
- `historical_event_calibration.events[]`: 백테스트 JSON에 수에즈 2021·파나마 2023–24·홍해 2023–24·호르무즈 2026의 사건 평균/최대 7일 통항 위축, bootstrap 구간, placebo p-value와 회복일을 둡니다.
- `scenario_signal_comparison[]`: PortWatch 추정 교역량 감소율과 시나리오 봉쇄율의 크기만 나란히 비교합니다. 두 값은 서로 다른 개념이며 경험적 보정이나 보험·억류 시드 검증으로 사용하지 않습니다.
- `event_observations[]`: IMO 등 공식 기관이 공개한 사건별 관측 타임라인. 날짜·범위·정량 여부를 보존하며, 선종별 척수/DWT가 없는 관측은 추정치로 변환하지 않습니다.
- `model_review`: Codex 모델·시드 재평가, Claude UI·PR 통합 역할과 잠정 가정 목록.
- `environment.scenarios[]`: 2026–2030 CII 감축계수와 감속·개조 휴항·퇴출 반응을 결합한 저손실/중앙/고손실 유효 서비스 DWT 범위. 개별 선박 CII 예측이 아닙니다.
- `container.context.groups[]`: World Bank 국가별 항만 TEU의 지역 합계. 항로 물량이 아니라 총량 타당성 검증용입니다.
- `routes[].stress_tests[].backlog_cargo_tonnes_horizon`: 분석 기간 말까지 운송되지 못한 화물.
- `routes[].stress_tests[].trapped_loaded_dwt`: 이미 선적된 채 대기한다고 가정한 DWT-equivalent.
- `routes[].stress_tests[].trapped_vessel_equivalent`: 대표 선형의 DWT 중간값으로 나눈 선박 환산치. 실제 AIS 척수가 아닙니다.
- `routes[].stress_tests[].insurance_excluded_dwt`: 보험·안전 제약으로 상업적 가용 선대에서 제외된 추정 DWT.
- `routes[].stress_tests[].commercially_available_dwt`: 물리적 선대 중 해당 시나리오에서 상업 운항 가능한 DWT.
- `routes[].directions[]`: 컨테이너 정기선의 양방향 화물 입력. `null` 화물량은 공공데이터 연결 대기이며 용량 계산에서 제외합니다.
- `route_catalog[]`: 대형선 중심 21개 세부 항로 정의. 모두 Comtrade 2024 품질 게이트를 통과해 `capacity_model_active`로 연결됩니다.
- `scenario_summary[]`: 봉쇄별 전체 영향 합계. 실효 봉쇄율과 잔존 통항률, backlog, 억류 DWT, 보험 제외 DWT를 함께 제공합니다.
- `scenario_summary[].behavior_sensitivity`: 사건 통항률을 고정한 상태에서 보험 유지·중앙·시장 이탈 등 행동변수 공동 경로별 결과와 최소–최대 범위.
- 진단 JSON `behavior_uncertainty`: 공동 경로 정의, 무료 보험자료의 가용·비가용 필드와 식별 한계.

## 대시보드 계약

프런트엔드는 `/public/data/shipping_capacity_v1.json` 하나만 읽으면 됩니다. 페이지를 만들 때는 반드시 다음 문구를 구분해 표시합니다.

- `세계 선대`: 관측 DWT.
- `항로 필요 선복량`: 모델 추정 DWT-equivalent.
- `관측 이상`: PortWatch 추정 교역량 변화.
- `봉쇄 충격`: 사용자가 선택한 가정 기반 시나리오.

TEU와 DWT는 직접 합산하지 않습니다. v1의 공통 비교 단위는 DWT-equivalent이며, 컨테이너 페이지에 TEU가 필요하면 별도의 TEU 선대 관측 시계열을 추가해야 합니다.

## 환경 규제와 유효 DWT

EEXI는 기술 효율 기준이며 엔진·축 출력 제한은 가능한 준수 수단 중 하나입니다. CII가 D 3년 연속 또는 E 1년이면 C 이상 달성을 위한 시정계획이 필요하지만, 규정이 선종별 감속률을 직접 지정하지는 않습니다. EU ETS와 FuelEU도 비용·연료 집약도 규제이므로 속도 제한으로 직접 변환하지 않습니다.

따라서 `config/environment_scenarios.json`의 감속·개조·퇴출 비율은 관측 사실이 아니라 민감도 시드입니다. `environment_route_profiles.json`은 선종·선형·EU 노출을 구분하되 무료 자료로 완전 관측할 수 없는 건조연도·연료·CII 등급은 `not_observed`로 남기고 유효 DWT 범위만 냅니다. 2027–2030 CII 기준 감축계수는 IMO MEPC.400(83)의 공식 값입니다.

## 현재 화면 연결 상태

- 해운 메뉴의 `글로벌 선대`, `항로별 선복량`, `초크포인트`, `봉쇄 시뮬레이터`가 이 JSON을 공통으로 읽습니다.
- URL 해시는 각각 `#/shipping_fleet`, `#/shipping_routes`, `#/shipping_chokepoints`, `#/shipping_scenarios`입니다.
- 봉쇄 시뮬레이터는 Python이 미리 계산한 봉쇄율·지속기간 격자를 읽습니다. 브라우저 자체 산식은 제거했습니다.
- 해운용 GitHub Action은 선택적 Comtrade 갱신, ML 의존성 설치, 단위테스트, 스냅샷 생성, 모델·JSON Schema 검증 순으로 실행합니다. Comtrade 자동 갱신에는 저장소 secret `COMTRADE_SUBSCRIPTION_KEY`가 필요합니다.

## 다음 단계

11번 환경규제 세분화, 12번 21개 항로 확대, 13번 산출물 분리와 golden 계약 테스트까지 완료했습니다. 다음 분석 후보는 공공 대기선박·항만 대기·운임 지표로 우회·대기·취소·보험 반응의 부분 식별 범위를 좁히는 작업입니다.
