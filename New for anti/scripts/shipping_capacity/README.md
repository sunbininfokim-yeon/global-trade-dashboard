# 글로벌 선복량 데이터 프레임워크 v1

이 폴더는 유료 AIS/Clarksons 단말 없이 다음 세 질문에 답하기 위한 계산 계층입니다.

1. 전 세계 선대의 선종별 총 선복량은 얼마인가?
2. 특정 항로의 화물 흐름을 유지하려면 얼마의 DWT가 그 항로에 계속 묶여 있어야 하는가?
3. 수에즈·파나마·보스포루스·호르무즈가 막힐 때 우회·대기·취소로 선복량과 트래픽이 얼마나 변하는가?

## 숫자의 세 등급

- `observed`: UNCTAD의 연간 세계 선대 DWT, IMF PortWatch의 일일 초크포인트 통항 capacity.
- `estimated`: 연간 화물톤, 왕복주기, 적재율로 역산한 항로 필요 선복량.
- `scenario`: 봉쇄율, 지속일, 우회/대기/취소 비율.

초기 `config/routes.json`의 연간 화물톤은 모델 작동을 보여주기 위한 시드입니다. 사이트에 공개하기 전 기존 UN Comtrade 파이프라인의 `netWeight` 집계로 교체해야 합니다. JSON의 `input_status`가 이 사실을 명시합니다.

## 핵심 산식

```text
왕복주기(일) = 2 × 편도거리(NM) ÷ 선속(kn) ÷ 24 + 왕복 항만일
항로 필요 DWT = 연간 화물톤 × 왕복주기 ÷ (365 × 유효 적재율)
추가 선복량 = 연간 화물톤 ÷ (365 × 적재율)
             × (우회대상비율 × 우회추가일 + 대기대상비율 × 대기일)
```

`duration_days / horizon_days`가 단기 사건의 노출도를 제한합니다. 따라서 28일 분석창에서 7일 봉쇄는 같은 강도의 28일 봉쇄보다 노출 항차가 1/4입니다.

## 무료 데이터 파이프라인

- 세계 선대 기준: UNCTAD Review of Maritime Transport 2025, Table II.5.
- 항로 화물톤: 기존 Cloudflare Worker의 UN Comtrade 응답 중 `netWgt`를 원산지-도착지-품목별로 집계.
- 현재 초크포인트 이상: IMF PortWatch ArcGIS REST API의 `capacity_container`, `capacity_dry_bulk`, `capacity_tanker`. 최근 7일 평균을 직전 28일 평균과 비교.
- 거리·선속·적재율: 모델 가정 테이블. 나중에 검증된 공개 거리 테이블이 생기면 설정값만 교체.

IMF PortWatch는 24개 이상 주요 통로의 일일 AIS 통항척수와 추정 capacity를 공개하지만, 이것은 개별 선박 원장이 아닙니다. UN Comtrade의 `netWeight`에도 추정 플래그가 있을 수 있으므로 향후 어댑터에서 `isNetWgtEstimated`를 품질 점수에 반영해야 합니다.

## 실행

외부 패키지가 필요 없습니다.

```bash
python3 build_snapshot.py
python3 -m unittest discover -s tests -v
```

실시간 PortWatch를 포함하려면 네트워크 가능한 환경에서 실행합니다.

```bash
python3 build_snapshot.py --fetch-portwatch \
  --output "../New for anti/public/data/shipping_capacity_v1.json"
```

생성 JSON의 주요 경로:

- `fleet.fleet_by_type[]`: 세계 선대 관측 기준.
- `routes[].baseline`: 항로별 필요 DWT와 P10/P50/P90.
- `routes[].stress_tests[]`: 해당 항로가 노출된 시나리오만 수록.
- `routes[].live_observed[]`: PortWatch를 조회했을 때만 생성. 최근 7일 capacity가 직전 28일보다 낮은 정도를 **봉쇄 프록시**로 넣은 것이며 실제 물리적 봉쇄율이라는 뜻은 아닙니다.
- `scenario_summary[]`: 봉쇄별 전체 영향 합계.

## 대시보드 계약

프런트엔드는 `/data/shipping_capacity_v1.json` 하나만 읽으면 됩니다. 페이지를 만들 때는 반드시 다음 문구를 구분해 표시합니다.

- `세계 선대`: 관측 DWT.
- `항로 필요 선복량`: 모델 추정 DWT-equivalent.
- `봉쇄 충격`: 사용자 시나리오 또는 PortWatch 관측 이상.

TEU와 DWT는 직접 합산하지 않습니다. v1의 공통 비교 단위는 DWT-equivalent이며, 컨테이너 페이지에 TEU가 필요하면 별도의 TEU 선대 관측 시계열을 추가해야 합니다.

## 다음 단계

1. 기존 UN Comtrade API 응답을 항로 입력으로 변환하는 어댑터를 붙인다.
2. GitHub Action에서 PortWatch를 매일 갱신하고 생성 JSON만 커밋한다.
3. 화면에서 봉쇄율·지속기간·우회/대기/취소 비율을 조절하는 시뮬레이터를 만든다.
4. 실제 사건 이후 PortWatch 통항 capacity로 예측 오차를 저장해 Model 1의 가정을 보정한다.
