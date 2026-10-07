# 인수인계 2026-10-07 — codex-chokepoint-history-2y

## 2026-10-07 — codex-chokepoint-history-2y

### Goal / summary
SHIPPING-HISTORY-20261007: 선종별 추정 교역량 1년·2년 토글 및 730일 이력 계약 완료. #454 병합 후속 별도 PR. 배포는 Claude 담당.

### Meta
- branch: `codex/chokepoint-history-2y`
- base main: `ab0dbf94` (#454 병합 이후)

### Files (working tree at handoff time)
```
"New for anti/public/data/shipping_capacity_backtests_v1.json"
"New for anti/public/data/shipping_capacity_diagnostics_v1.json"
"New for anti/public/data/shipping_capacity_scenario_grid_v1.json"
"New for anti/public/data/shipping_capacity_v1.json"
"New for anti/scripts/shipping_capacity/refresh_traffic_summary.py"
"New for anti/scripts/shipping_capacity/shipping_capacity/artifacts.py"
"New for anti/scripts/shipping_capacity/tests/chokepoint-ui.test.cjs"
"New for anti/scripts/shipping_capacity/tests/test_observation_routing_contract.py"
"New for anti/scripts/shipping_capacity/tests/test_traffic_summary.py"
"New for anti/shipping.js"
docs/ops/TASKS.md
docs/ops/handoff/2026-10-07-codex-chokepoint-history-2y.md
```

### Not done / risks
- 미병합·미배포. Claude가 소유권 검사와 shipping.js 캐시 버전 갱신을 정식 통합 절차로 처리. 공용 UI·Worker·workflow 변경 및 guard 우회 없음.
- 호르무즈 선종 구성 의미/표시 위치는 이번 범위에서 변경하지 않음. 이 작업은 그래프 기간 확장만.
- 공개 screen JSON은 2.32MB → 4.67MB, 로컬 gzip 측정 449,428 bytes. 데이터 크기를 검토했고, chart용 전체/컨테이너/벌크/탱커만 730일로 확장했음. 일반화물선 및 대표 history는 180일 유지. 실제 배포 압축 전송은 배포 후 점검 필요.
- 2년 실선을 그리는 데 3년 자료가 생기는 것은 아님. 전년 점선은 관측자료가 있는 부분만 표시하고 결측은 null 유지.

### Next
- 이미 병합된 #454를 다시 수정/재병합하지 말고 이 후속 브랜치의 제한된 diff를 검토·통합.
- 그래프 선택: **3개월(90) / 6개월(180) / 1년(365) / 2년(730)**. 기본 3개월 유지. 실제 표시 시작일·종료일·지점 수를 안내하며 긴 기간의 축은 연-월, tooltip은 연-월-일.
- `artifacts.py`의 `SCREEN_METRIC_HISTORY_POINT_LIMIT=730`을 함께 반영. 버튼만 가져오면 기존 180일만 보임. 기존 일일 파이프라인이 이력을 자동 포함하므로 새 API 키·수집·ML 학습·workflow 변경 불필요.
- 현재 관측 이력 **2024-10-05~2026-10-04**, generated_at **2026-10-06T22:46:53.329077+00:00** 유지. JSON 4종 bundle_id **afe226be3ac6ed47a90e** 일치. 진단·격자·백테스트는 bundle_id 외 기존 값 동일.
- 병합 시 main 데이터가 더 최신이면 최신 diagnostics로 `refresh_traffic_summary.py`를 실행해 4종을 함께 재생성. 이 PR의 오래된 JSON으로 최신 관측치를 덮지 말 것.
- 검증: Python **169 실행, 167 통과·2 skip**(변경 범위 밖 Panama h5py 미설치), Node **17 통과**, 스키마 **4종/golden 통과**. 실자료 수에즈 전체/컨테이너 1년 365·2년 730개 표시와 360px 가로 넘침 없음, 콘솔 오류 없음 확인.

### Commands
```bash
./tools/ops/status.sh
node --test 'New for anti/scripts/shipping_capacity/tests/chokepoint-ui.test.cjs'
python3 'New for anti/scripts/shipping_capacity/refresh_traffic_summary.py'
python3 'New for anti/scripts/shipping_capacity/validate_schema.py'
# 전체 Python 테스트는 New for anti/scripts/shipping_capacity에서:
# python3 -m unittest discover -s tests
```

---
