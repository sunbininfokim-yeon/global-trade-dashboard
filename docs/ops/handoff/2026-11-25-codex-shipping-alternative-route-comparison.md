# 해운: 대안항로별 거리·운항일·선복량

- 브랜치: `codex/shipping-alternative-route-comparison`, base `cff79b211`. 품목별 누적 PR #1113과 독립.
- 새 API 키·호출·workflow 없음. 기존 해운 스냅샷 빌더가 계산한다. 운영 JSON·해운 화면·북극 해빙 엔진·시뮬레이터 격자는 수정하지 않았다.

## Claude 화면 연결

**항로 운항 선복량 → 선종별 운항 서비스**의 각 행에서 `routes[].operational_profile.detour_comparison.options[]`를 읽는다. 필드가 없거나 빈 배열이면 대안 목록을 숨긴다. 초크포인트 시뮬레이터의 특정 봉쇄율·기간 결과를 이 수치로 대체하지 않는다.

- 기본값: `operational_profile.normal`의 편도 거리·속도·항해일·왕복 회전일. 추가값: `options[].additional_nm_one_way`, `additional_sailing_days_one_way`, `additional_cycle_days_round_trip`. `cycle_days_round_trip`은 우회하는 선박의 왕복 회전일이다.
- `additional_required_dwt`와 `additional_required_dwt_pct`는 전체 서비스 기준이다. 구성된 노출 물량 비중만 우회하고 나머지는 정상 경로를 유지한다. 기존 항차 모델과 같은 연간 화물·적재율·항만 체류·일반 운항 속도를 유지한다.
- 산식: 정상 필요 DWT(예비율 제외) × `exposed_flow_share` × 왕복 추가일 / 정상 왕복일. `required_dwt_with_detour`는 정상 필요 DWT와 이 증가분의 합이다. 브라우저 재계산·TEU/m³ 임의 환산·실시간 가용 선대라고 표기하지 않는다.
- **`bypassed_chokepoint_ids`에 수에즈·바브엘만데브가 모두 있으면 한 줄**로 표시한다. `requires_open_chokepoint_ids`는 우회 중에도 반드시 지나야 하는 관문이다. 페르시아만→유럽의 희망봉 우회나 페르시아만→동아시아의 말라카 우회는 호르무즈가 열려 있다는 조건이다.
- `conditional_geometry_only`는 순다·파나마 대안의 조건부 값이다. 순다 경로 증거는 해상 네트워크의 거리 증거이지 VLCC/Q-Max 흘수나 공급 가능성을 검증한 값이 아니다. 파나마는 출발·도착항 기준의 실제 경로를 새로 확정하지 않은 기존 거리 가정이다.
- `no_same_port_sea_detour`는 우회 거리·일수·DWT가 `null`이다. 0 대신 “해상 우회 없음”을 표시한다. 원유 송유관·대체 공급처·운송 보류는 별도다.
- `warning_ko`, `distance_basis`, `distance_evidence_id`, `traffic_input_status`를 유지한다. 거래량 입력은 기존 항로 모델의 공개 자료 기반 프록시이지 정확한 항로 적재 명세가 아니다.

## 북극항로는 별도 항구쌍 비교

`arctic_route_reference`는 해빙 엔진이 기존에 생성한 `sea_route_v1.json → route_line.compare`의 부산–로테르담 비교를 재사용한다. 상태가 `conditional_port_pair_reference`일 때만 표시한다. 북극 탭의 기존 비교 화면이 이미 있으면 중복 렌더하지 않는다.

- 14노트 기준, 기존 원천의 북극 구간 8일·수에즈 통과 및 대기 1일을 그대로 사용한다. `difference_days_round_trip_transit`는 같은 경로 양방향을 가정한 왕복 통과일 차이이며 항만 체류 제외다.
- 출력은 수에즈 10,801해리·33.1일, 희망봉 14,507해리·43.2일, 북극 7,582해리·22.9일. 기존 원천 표시 자릿수를 활용한다.
- `additional_required_dwt`는 전부 `null`. 동아시아 전체 서비스 수요를 이 항구쌍에 적용하거나, 일반 대형선을 동일한 북극 빙급·적재능력으로 가정하지 않는다. 항로 이용 적격성은 [IMO Polar Code](https://www.imo.org/en/ourwork/safety/pages/polar-code.aspx) 참조. 이 비교는 현재 통항 가능 판정이 아니다.

## 재생성 확인

기존 main의 입력으로 로컬 임시 디렉터리에 4종 생성물을 빌드했다. 21개 정상 항로 결과 및 11개 시나리오 요약이 기존 스냅샷과 일치한다. 예: 동아시아↔북유럽 컨테이너의 희망봉 대안은 17노트·노출 95% 가정에서 편도 +3,500해리/+8.58일, 왕복 +17.16일, 모델상 +148.35만 DWT(+26.52%). 이 계산에 신규 PortWatch 관측·가상 화물량은 추가하지 않았다.
