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

# U.S. quality decision layer (empty contract or extracted point-in-time input)
python3 build_us_macro_quality.py --print-stats
python3 build_us_macro_quality.py --input cache/us_macro_quality/input.json --print-stats
# → ../../public/data/us_macro_quality_v1.json

# U.S. CPI release structure: use Table 6/7 effects for contribution ranking.
# BLS may block unattended requests, so saved HTML from the SAME release is a
# first-class input path. Table 2 is optional detail only, never a driver rank.
python3 build_us_cpi_structure.py \
  --table2-html cache/cpi/2026-07/cpi.t02.htm \
  --table6-html cache/cpi/2026-07/cpi.t06.htm \
  --table7-html cache/cpi/2026-07/cpi.t07.htm \
  --print-stats
# → ../../public/data/us_cpi_structure_v1.json

# BLS API observed CPI index history (keep the key outside Git and this repo)
BLS_API_KEY='...' python3 build_us_cpi_api_history.py --start-year 2011 --print-stats
# → ../../public/data/us_cpi_api_history_v1.json

# Official external Fed indicators: display provider values separately from
# our own CPI relationship evidence. No API key is required.
python3 build_us_official_inflation_sources.py --print-stats
# → ../../public/data/us_official_inflation_sources_v1.json
```

`us_cpi_structure_v1.json`은 같은 발표 빈티지의 All Items 기여도 상·하위 3개와
CPI 내부 관계 카탈로그를 분리한다. 관계는 신호·인과·예측이 아니며, 시차 검증 전에는
`market_hypothesis`도 활성 경로에 표시되지 않는다.

`us_official_inflation_sources_v1.json`은 Cleveland Fed가 직접 공개한 나우캐스트·
Median/Trimmed-Mean CPI와 SF Fed의 주거비 선행지표 연구를 **출처·방법론·갱신시각과
함께** 보관한다. 이 값은 대시보드 자체 예측이나 항목간 인과판정으로 재표기하지 않는다.

실데이터 범위: [`LIVE_DATA.md`](./LIVE_DATA.md)

## 프로토타입 UI (기존 app.js 미수정)

```bash
cd "New for anti"
python3 -m http.server 8765
# open http://localhost:8765/macro_monitor.html
```

파일: `macro_monitor.html` · `macro_monitor.css` · `macro_monitor.js`

## 소유

엔진·스냅샷 = Cursor. 메인 대시보드(`app.js` 등) 연결 = Claude 별도.
