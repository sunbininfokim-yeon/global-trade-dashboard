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

## 프로토타입 UI (기존 app.js 미수정)

```bash
cd "New for anti"
python3 -m http.server 8765
# open http://localhost:8765/macro_monitor.html
```

파일: `macro_monitor.html` · `macro_monitor.css` · `macro_monitor.js`

## 소유

엔진·스냅샷 = Cursor. 메인 대시보드(`app.js` 등) 연결 = Claude 별도.
