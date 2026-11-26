# Macro Monitor

작황 모니터 같은 **지도 → 국가 → 지표 칩 → 시계열** 플로우.
좌우 대시보드 없음. 지도는 배경으로 유지.

## 양식 (미국 기준 통일)

**정본:** [`KIT_TEMPLATE.md`](./KIT_TEMPLATE.md) · 벤치마크 [`US_MACRO_KIT.md`](./US_MACRO_KIT.md)

6탭 고정: `liquidity` → `rates` → `fx` → `equity` → `growth` → `inflation`  
헤드라인 6 · 한계 3(+지정학 시 4) · 공통 `m2/m3_vs_2019`

## 풀 키트: US · JP · UK · CN · EZ · RU · HK · SG · ZA · IN · KR · CA · AU · CH · BR · VN · KZ · TW

- [`TW_MACRO_KIT.md`](./TW_MACRO_KIT.md) — 반도체 · 생보 환헤지 · USD/TWD · 수출주문
- **API:** [`DATA_SOURCES.md`](./DATA_SOURCES.md) · **refresh:** [`REFRESH_TIERS.md`](./REFRESH_TIERS.md)
- **Claude UI handoff:** [`CLAUDE_UI_HANDOFF.md`](./CLAUDE_UI_HANDOFF.md)

## 실행

```bash
cd "New for anti/scripts/macro_monitor"
python3 -m unittest discover -s tests -v
python3 build_macro_monitor.py --print-stats          # fixture only
python3 build_macro_monitor.py --live --print-stats   # Yahoo + Worker FRED/BOK overlay
# → ../../public/data/macro_monitor_v1.json

# Japan growth: official ESRI + BOJ snapshot, then run build_macro_monitor.py
python3 build_japan_growth_snapshot.py
```

실데이터 범위: [`LIVE_DATA.md`](./LIVE_DATA.md)

## 미국 CPI 관계 표본외 재검증

`build_us_cpi_forward_validation.py`는 기존 자동차·외부입력 설정의 6개 경로를
연구용으로 다시 채점한다. 관계맵의 공식 산식은 예측 검정에 넣지 않는다.
기본 학습 마감은 2026-07이며 그 뒤의 발표월을 순서대로 채점한다.

```bash
# BLS 이력을 갱신한 뒤 같은 디렉터리에서 실행
python3 build_us_cpi_forward_validation.py --out /tmp/us-cpi-forward-validation.json
# 네트워크 없이 기존 BLS 이력으로 자동차 4개 경로만 재검증
python3 build_us_cpi_forward_validation.py --vehicle-only
```

- 런타임은 Python 3.9+와 NumPy·SciPy·statsmodels. 항공유는 EIA 공식 월별 표를 우선 읽고, 접근 실패 시 FRED 월별 CSV를 사용한다. 외부 계열과 BLS 이력에 없는 항공료 CPI는 공개 FRED CSV에서 읽으므로 별도 키는 필요 없다.
- 기준모델은 대상 SA MoM의 직전월 값과 기존 통제변수, 확장모델은 여기에 사전 지정한 시차 전체를 추가한다. 외부입력 모델에는 달력 월 효과를 넣는다. 두 모델에 같은 학습월과 채점월을 쓰고, 채점 결과를 보고 시차를 골라 바꾸지 않는다.
- 당월 EIA 항공유·브렌트는 나우캐스트 입력으로만 분류한다. PPI·산업생산은 최소 1개월 시차를 둔다. 날짜별 발표 가능 여부와 최초 발표본을 복원한 검증은 아니므로 후보를 자동 승격하지 않는다.
- 전월이 빠졌으면 MoM을 계산하지 않는다. 시차 입력이 하나라도 빠지면 그 달은 채점하지 않고 누락된 계열과 기준월을 남긴다. `--through YYYY-MM`으로 예상 기준월의 BLS 이력 존재 범위를 검사할 수 있다. 기본 실행은 누락도 포함해 결과를 쓰고, `--require-complete`는 채점 공백이 하나라도 있으면 기존 결과 파일을 보존하고 종료 코드 2를 낸다. 알려진 2025-10 관측 공백이 포함된 검증에서는 이 옵션을 정기 잡의 성공 조건으로 쓰지 않는다.
- 정기 작업에 붙일 때는 CPI 이력 갱신 뒤 실행하고 결과를 CI 아티팩트 한 개로 보관한다. 기존 기여도·관계맵·공개 JSON은 그대로 유지한다. 이 명령 자체는 예약을 등록하지 않는다.

## 프로토타입 UI (기존 app.js 미수정)

```bash
cd "New for anti"
python3 -m http.server 8765
# open http://localhost:8765/macro_monitor.html
```

파일: `macro_monitor.html` · `macro_monitor.css` · `macro_monitor.js`

## 소유

엔진·스냅샷 = Cursor. 메인 대시보드(`app.js` 등) 연결 = Claude 별도.
