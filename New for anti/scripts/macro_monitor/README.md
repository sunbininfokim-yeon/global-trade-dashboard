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
- `lag_diagnostics`는 학습 마감일(기본 7월)까지의 과거만 사용해 시차별 후보를 비교한다. 기본 72개월 이상을 학습한 뒤 한 달씩 순차 검증하며, 모든 시차가 같은 검증월을 쓰고 검증월이 24개 이상일 때 RMSE가 가장 낮은 시차를 선택한다. 식품처럼 여러 입력을 묶는 경로는 동일 시차로 함께 검사하므로 요인별 최적 시차는 아니다.
- 선택한 시차 하나만 사용해 마감 전 자료로 다시 적합하고, 마감 후 오차를 별도로 기록한다. 과거 두 구간(2021년까지, 2022년부터)의 최우수 시차 및 순차 적합 계수의 양수 비율은 재현성 참고용이다. 독립적인 유의성 검정이나 단계 판정으로 해석하지 않는다. 식품과 항공료의 당월 모형은 관측 가능한 에너지만 추가한 별도 진단이다.
- 당월 EIA 항공유·브렌트는 나우캐스트 입력으로만 분류한다. PPI·산업생산은 최소 1개월 시차를 둔다. 날짜별 발표 가능 여부와 최초 발표본을 복원한 검증은 아니므로 후보를 자동 승격하지 않는다.
- 전월이 빠졌으면 MoM을 계산하지 않는다. 시차 입력이 하나라도 빠지면 그 달은 채점하지 않고 누락된 계열과 기준월을 남긴다. `--through YYYY-MM`으로 예상 기준월의 BLS 이력 존재 범위를 검사할 수 있다. 기본 실행은 누락도 포함해 결과를 쓰고, `--require-complete`는 채점 공백이 하나라도 있으면 기존 결과 파일을 보존하고 종료 코드 2를 낸다. 알려진 2025-10 관측 공백이 포함된 검증에서는 이 옵션을 정기 잡의 성공 조건으로 쓰지 않는다.
- 정기 작업에 붙일 때는 CPI 이력 갱신 뒤 실행하고 결과를 CI 아티팩트 한 개로 보관한다. 기존 기여도·관계맵·공개 JSON은 그대로 유지한다. 이 명령 자체는 예약을 등록하지 않는다.

### 미국 CPI 검토 화면 인수

`python3 build_us_cpi_watch.py`는 오른쪽 검토 칸과 순위 그림에 쓸 별도 JSON을
표준출력으로 생성한다. `--offline`은 외부 수집 없이 계약을 확인하는 옵션이다.
메인 화면과 정기 배포에는 아직 연결하지 않았다.

- 본문 순위는 `movers.mom` 또는 `movers.yoy`를 0선 중심 가로 막대로 그린다. 공통 절댓값 눈금은 `max_abs_pct`. 상승 3·하락 3 중 관측된 것만 그리고, 빈 자리를 작은 상승값으로 채우지 않는다. 현재 순위 범위는 대시보드 추적 항목이며 전체 CPI 구성품이나 가중 기여도 순위가 아니다. 기존 기여도 탭은 유지하고 선택 기준월 또는 MoM/YoY를 바꿀 때 대상 자료가 없으면 이전 값으로 채우지 않는다.
- 기존 CPI 관계 본문에는 `internal_pathways`를 사용한다. 선택 항목 ID가 `source_ids` 또는 `target_ids`에 있는 경우만 붙이고, 공통 요인·측정상 연결을 인과 방향으로 그리지 않는다.
- Claude UI 연결 지점은 `macro.js`의 `mmMoversView`와 오른쪽 `mmNewsRail` 분기다. 미국 CPI 화면에 한해 우측 상단에 ‘다음 발표에서 볼 외부 가격’을 두고 관련 뉴스는 그 아래에 둔다. `external_prices[].item_ids`와 선택 항목을 대조한다. 헤드라인에서는 관심 경로 목록을 볼 수 있게 하고, 임차료나 OER 선택 시 Zillow를 우선 표시한다. 데이터 기준월과 CPI 기준월을 따로 적는다.
- Zillow만 관측값을 공급하고 나머지는 출처 링크로 보낸다. 숫자는 `observation.status == "observed"`일 때만 표시한다. Zillow는 시장 임대료 참고이지 CPI 입력·기여도가 아니며, 정확한 발표일은 이 CSV에 없다. Zillow 공개 재배포 조건은 UI 배포 전에 확인한다.
- Zillow 진단은 최신 개정 이력으로 CPI 주거 임차료 SA MoM을 대상으로 한 탐색이다. 1~12개월 시차 중 최대값인 12개월이 선택되더라도 ‘12개월 뒤 전이’라고 표시하지 않는다. 진단 수치와 예측은 UI 기본 카드에 쓰지 않는다.

### 비식료 CPI 주간 및 발표 D-3 운영 인수 (#1149)

**내부 파급 감시는 순위에서 독립한다.** 월간 BLS 이력이 갱신되면
`python3 -B build_us_cpi_internal_watch.py`를 실행한다. 외부 시세·캘린더·TOP3 없이 실행되며
`--month YYYY-MM`으로 당시까지의 월만 선택할 수 있다(최신 개정본). 주간 JSON에도 동일한
`internal_monitor`가 들어간다. 본문 기본 보기는 전체 감시 결과이고, 칩 클릭은 필터일 뿐이다.
모든 저장된 SA 계열의 전월비를 자기 과거 36개월 P90과 비교(최소 유효 24개월).
이력이 없는 경로 구성은 missing_ids에 남기고 추정하지 않는다. 자동차만 단계 규칙을 갖고,
그 밖의 공통요인·측정 관계는 파급 신호가 아니다. 차량 상태의 `check_next`는 관찰 대상이지 전망이 아니다.
vehicle_replay는 미래 3개월이 모두 관측된 과거 월에서 [조건 충족 결과 건수, 평가 가능 월수]를
집계한다. 신차: 중고차·부품·정비 중 2개 이상이 이후 3개월 평균 양수이며 직전 3개월보다 빨라졌는지,
비교군은 신차 비급등 월. 잔류 압력: 보험료 이후 3개월 평균 MoM이 직전 3개월보다 낮아졌는지,
비교군은 다른 보험료 급등 월. 겹치는 월·개정 이력을 사용한 기술통계이며 인과·예측 확률이 아니다.

운영 명령은 위의 연구용 미리보기 대신 아래 하나를 쓴다. API 키·LLM·주간 재학습 없이
기존 본문 데이터와 외부 시세를 한 JSON으로 조립한다. 공용 UI/Actions는 Claude 소유이며 이 PR에서 활성화하지 않는다.

```bash
cd "New for anti/scripts/macro_monitor"
python3 -B refresh_us_cpi_watch.py --out ../../public/data/us_cpi_watch_v1.json
```

- Actions: 매일 UTC 21:17 (`17 21 * * *`) 위 명령 실행. 실제 수집은 미국 동부 금요일과 공식 발표 D-3~D-1에만 한다(기타 날짜는 캘린더만 확인). 수동 실행은 `--force`. CPI 기존 Python 의존성을 설치하고 성공한 경우에만 변경된 파일 하나를 게시한다. 동시 실행은 직렬화한다. 실패·예약일 아님은 기존 파일을 보존한다.
- 기간은 BLS 일정의 **Reference Month**에서 읽는다. 공식 페이지가 차단되면 출처 확인일로부터 21일간만 `config/cpi_release_fallback.json`을 사용한다. 만료 시 일정을 추측하지 않고 실패한다. 실패 알림을 연결하고 공식 일정 재확인 후 갱신할 것.
- 본문 TOP/BOTTOM 선택 시 `internal_pathways`만 사용한다. `monitor_status`별로 측정·비교·가설을 구분하며 미지지 중고차→수리비 알림은 만들지 않는다. `reference_period`는 **이미 발표한 CPI**의 기준월이다.
- 우측 `mmNewsRail`은 미국 CPI에서만 `briefing.news_ids` 순서로 `external_prices`를 조회한다. 해당 CPI 품목·출처 기준월/관측일·발표예정일을 함께 표시한다. `briefing.target_reference_period`는 **앞으로 발표할 CPI**다. 그 CPI가 게시됐거나 동부 날짜가 `hide_on_or_after_eastern`에 도달하면 숨긴다. 과거 선택월에 최신 뉴스를 붙이지 않는다. 근원 CPI에서는 휘발유·유틸리티 자체 항목을 제외한다. 기존 계란 알림은 별도 계약.
- EIA는 동일 월 주차끼리 비교한 원자료(비계절조정 $/갤런), 전주비는 정확히 7일 전 값이 있을 때만 표시. 기준월 이후 데이터는 제외한다. 월말 또는 오늘 기준 10일 넘게 뒤진 값은 뉴스에서 제외한다. Zillow 관측월/추세는 별도 표시(재배포 조건 확인 전 외부 공개 보류). Manheim은 링크 전용이다.
- 요율은 전국 자동 수집기가 아니다. `config/cpi_reviewed_rate_orders.json`의 `orders`에 담당자가 검토한 주별 공식 문서만 등록한다. 필드: source_id(해당 *_rate_actions), jurisdiction, provider, applies_to(신규/갱신 또는 가정용 청구대상), approved_on, effective_on, source_url(정부 HTTPS 원문). 적용일이 지난 대상월 건만 지역 사례로 표시한다. 빈 목록은 ‘검토된 사건 없음’이지 ‘전국 요금 동결’이 아니다.

### USDA 계란 도매가 감시 자동화 인수

`build_us_cpi_food_watch.py`는 USDA AMS 2843 공개 최신 PDF에서 전국 FOB 흰색 대란(일반 사육·등급 규격·5일 가중평균)의
같은 행만 읽는다. API 키는 사용하지 않는다. 직전 보고와 비교해 **3% 이상이면서 다스당 3센트 이상 상승**했을 때만
우측 뉴스 상단에 놓을 `alerts[]`을 낸다. 3%/3센트는 편집 기준이며 전이율이나 통계 모델은 아니다.
대상은 가정식 전체가 아니라 **BLS 세부 품목 계란(SEFH)**만이다. 이전 CPI의 전월비·가중치는 기존 기여도 파일에서 읽는다.

```bash
# New for anti/scripts/macro_monitor 에서, pypdf 6.14.2를 사용
python -B -m unittest discover -s tests -p 'test_cpi_food_watch.py'
python build_us_cpi_food_watch.py --out ../../public/data/us_cpi_food_watch_v1.json
```

Claude 연결 사항:

1. 영업일 오후 USDA 발행 이후 GitHub Actions에서 하루 한 번 실행. 평일 예시 `15 19 * * 1-5`(UTC). 수동 실행도 열어둔다.
   기존 CPI 월간 갱신과 별도이며 `us_cpi_food_watch_v1.json` 한 파일만 게시한다. 보고서가 같으면 결과 파일도 바뀌지 않는다.
2. 실행 실패 시 기존 결과를 게시 파일에 덮어쓰지 않는다. 경보는 `expires_on_us_eastern`이 지났거나 대상월 BLS CPI가 이미
   게시됐다면 렌더링하지 않는다. 배포 재실행으로 새 뉴스가 중복되지 않도록 `observation_id`로 구분하되 슬롯 `id`는 고정이다.
3. `mmNewsRail` 앞 미국 헤드라인 CPI 전용 슬롯에서 `alerts[]`을 먼저 그린다. NaN`다음 발표에서 볼 CPI` 계란 → 직전 CPI 수치 → USDA 원문 순으로 표시한다. 근원 CPI 우측에는 띄우지 않는다.
   계란이 탑·바텀 순위에 없더라도 이 슬롯은 독립적으로 표시한다. 텍스트는 시장 관찰로 표시하고 CPI 전망값은 만들지 않는다.

## 프로토타입 UI (기존 app.js 미수정)

```bash
cd "New for anti"
python3 -m http.server 8765
# open http://localhost:8765/macro_monitor.html
```

파일: `macro_monitor.html` · `macro_monitor.css` · `macro_monitor.js`

## 소유

엔진·스냅샷 = Cursor. 메인 대시보드(`app.js` 등) 연결 = Claude 별도.
