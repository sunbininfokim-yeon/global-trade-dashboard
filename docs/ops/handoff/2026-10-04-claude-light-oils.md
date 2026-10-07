# 인수인계 2026-10-04 — claude (경질유)

## 들어간 것

- **경질유 품목 (#439, 배포 완료)**
  - 원자재 › 에너지 › "경질유 (납사·휘발유)", key `light_oils`, UN Comtrade HS 271012.
  - 납사와 휘발유는 HS 6자리에서 나뉘지 않는다. 지도는 271012 전체이고, 출처 문구(`TradeData.light_oils.hsNote`)에 그렇게 적는다.
  - 화면 안 "세부 품목"(`TradeData.light_oils.subProducts`): 납사·휘발유.
    - 국가 보고서마다 품목 배지를 단다.
    - 품목을 누르면 그 품목 보고서만 남는다(trade.js `subProductsCardHtml` / `setReportsSubFilter`).
    - 다른 품목도 `subProducts`만 달면 같은 방식으로 동작한다.
  - 수출통제 지도 별칭은 `light_oils` → naphtha, gasoline, petroleum_products. 러시아 휘발유 수출 금지와 중국 정제유 중단이 경질유 지도에 칠해진다.
  - 보고서 별칭: 납사·휘발유 관련 단어. 'petrol'은 단어 단위로만 잡히므로 petroleum, petrochemical에는 걸리지 않는다.
- **프로덕션 스모크 (feed-probe run 37189731951)**
  - 메뉴, data.js, export-controls.js 반영 확인.
  - `/api/futures?commodity=light_oils` → priced:false 안내.
  - `/api/comtrade?hs=271012` → 2024 연간 10,576행.
- **feed-probe `find=`:** 본문에 특정 문자열이 있는지 확인하는 스모크 옵션.

## 남은 것

- **경질유 국가 화면 실제 확인:** 한국 등 국가를 눌렀을 때 순위를 실제 Comtrade 데이터로 본 적이 아직 없다(로컬 확인은 목업).
- **세부 품목별 무역량:** 국가 8자리 통계(예: 한국 관세청 HSK 2710.12-xxxx)를 붙여야 가능하다. 국제 비교는 불가.
