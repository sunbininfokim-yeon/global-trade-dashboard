# 인수인계 → Cursor: 국가별 수출통제 월간 조사 (농산물·에너지·금속광물)

작성: Claude, 2026-09-24. 대상: Cursor. 관련 작업: TASKS T46.

## 1. 목표
매월 한 번, 주요 수출국이 농산물·에너지·금속광물에 건 **수출 금지·쿼터·수출세·허가제·국영 단일창구** 조치를 조사한다. 결과는 `New for anti/public/data/export_controls_v1.json` 하나에 반영한다.
이 파일을 화면 두 곳이 그대로 읽는다.
- **무역 지도:** 원자재를 선택하면 국가 색이 칠해지고, 국가를 클릭하면 조치 카드가 뜬다 (`app.js controlsFor`).
- **작황 모니터:** 국가 색과 무역·수출통제 배너, 그리고 좌측 "주요 농산물 수출국 · 수출통제" 목록 (`app.js agriControlsCardHtml`, `policyFromControls`).

지금 파일은 Claude가 2026-09-24에 웹으로 확인한 **수기 정리본(19건)**이다. 농산물 11건은 확인을 마쳤고, 금속광물 5건은 2026-08 이후 재확인하지 않았다.

## 2. 데이터 계약 (깨지 말 것)
```jsonc
{
  "schema_version": "export-controls-v1",
  "as_of": "YYYY-MM",               // 마지막 월간 조사 월
  "status": "curated_seed" | "monthly_survey",
  "levels": { "prohibited": {...rank 3}, "restricted": {...2}, "watch": {...1}, "lifted": {...0} },
  "categories": { "agri": "농산물", "energy": "에너지", "minerals": "금속·광물" },
  "controls": [{
    "id": "idn-palm-oil",            // 고정 id. 한 번 정하면 바꾸지 않는다 (Codex export_control_screen.py가 id로 조인)
    "country": "Indonesia", "iso": "IDN",
    "category": "agri" | "energy" | "minerals",
    "commodities": ["palm_oil"],     // 아래 §3 키만 사용
    "hs_prefixes": ["1511"],         // 통제 대상 HS. 모르면 빈 배열 (추정 금지)
    "level": "prohibited" | "restricted" | "watch" | "lifted",
    "measure_type": "ban" | "quota" | "duty" | "licensing" | "state_trading" | "levy" | "min_price",
    "since": "YYYY-MM", "effective_from": "YYYY-MM-DD",
    "until": "YYYY-MM-DD",           // 공표된 종료일이 있을 때만
    "lifted_at": "YYYY-MM-DD",       // level=lifted일 때 필수
    "effective_to": "YYYY-MM-DD",    // until 또는 lifted_at과 같게
    "measure_ko": "한 줄 요약: 무엇을, 얼마나, 언제까지",
    "source": "발행 기관", "url": "원문 URL (정부 고시 우선)",
    "confidence": "high" | "medium" | "low",
    "verified_at": "YYYY-MM-DD", "verified_as_of": "YYYY-MM-DD"
    // 선택 (Codex screen 호환): destinations[], conditions[], product_form,
    //   scope_verified, official_document_verified, review_valid_until
  }]
}
```
- **level 기준**
  - `prohibited`: 전면 금지.
  - `restricted`: 쿼터·수출세·허가제·국영 단일창구·최저수출가. 수출은 되지만 비용이나 물량이 제한된다.
  - `watch`: 공식 검토·입법 예고.
  - `lifted`: 최근 12개월 안에 해제된 조치. 지도에는 칠하지 않고 목록에만 흐리게 남긴다. 12개월이 지나면 삭제한다.
- 작황모니터 색은 `prohibited` 개수로 정한다 (2개 이상 빨강, 1개 주황, restricted만 있으면 노랑). **수출세를 금지로 올리지 않는다.** 예전 seed가 아르헨티나 옥수수 수출세를 "금지"로 표시해 틀렸다.
- 뉴스 기사만 있으면 `confidence` 최대 `medium`. `high`는 정부 고시나 공식 발표 원문을 확인한 경우에만 쓴다.

## 3. 대상 범위
**원자재 키** (대시보드 `data-target`과 같아야 색이 칠해진다):
- 농산물: `wheat corn barley soybeans rice sugar coffee cocoa palm_oil rubber rapeseed sunflower_oil sunflower_seed fertilizer urea phosphate`
- 에너지: `oil gas lng thermal_coal met_coal coal`
- 금속광물: `copper aluminum bauxite zinc nickel cobalt lithium graphite rare_earths gallium germanium antimony tungsten iron_ore manganese chromium tin lead gold silver platinum ferroalloys`
- 새 키가 필요하면 Claude에게 알린다. `app.js CONTROL_ALIASES`와 `CONTROL_COMMODITY_KO`에 추가해야 화면에 나온다.

**국가:** 원자재별 수출 상위 5개국이 기본이다. 목록은 운영 `/api/comtrade?hs=…`(연간, 워커가 최신 완결 연도를 고른다)의 수출 합계로 매달 다시 만든다. 여기에 공급 충격 이력이 있는 나라를 고정 포함한다: IND, RUS, UKR, KAZ, ARG, IDN, MYS, CHN, COD, MMR, VNM, THA, EGY, PAK, TUR.

## 4. 매월 확인할 출처
| 분류 | 출처 | 주기 |
|---|---|---|
| 종합 | IFPRI Food & Fertilizer Export Restrictions Tracker (foodsecurityportal.org, 다음 갱신 2026-10-15) | 월 |
| 종합 | Global Trade Alert state acts (export tax / ban / quota 필터) | 수시 |
| 종합 | AMIS Market Monitor 정책 섹션, USDA FAS GAIN 보고서 | 월 |
| 금속광물 | OECD Inventory of Export Restrictions on Industrial Raw Materials | 연 |
| 인도 | DGFT Notifications (dgft.gov.in), DFPD 설탕 쿼터 | 수시 |
| 러시아 | government.ru 결정문, 농업부 주간 곡물·해바라기 수출세율 | 주 |
| 아르헨티나 | Boletín Oficial (retenciones 고시) | 수시 |
| 인도네시아 | 무역부 월별 기준가(팜유·코코아), BPDP 부담금, Danantara/DSI 공지 | 월 |
| 말레이시아 | MPOB / 관세청 월별 CPO 기준가·수출세 | 월 |
| 우크라이나 | 내각·의회 결정 (대두·유채 수출세) | 수시 |
| 중국 | MOFCOM·해관총서 수출통제 공고 (비료, 갈륨·게르마늄·안티몬·흑연·희토류) | 수시 |
| DR콩고 | ARECOMS 코발트 쿼터 | 수시 |

## 5. 월간 절차
1. **후보 수집:** 위 추적기에서 지난달 이후 바뀐 조치를 모은다. 이 단계는 스크립트로 자동화할 수 있다.
2. **원문 확인:** 후보마다 정부 원문을 연다. 원문을 못 찾으면 `watch`로 두거나 `confidence: low`로 표시한다.
3. **파일 반영:**
   - 새 조치는 새 `id`로 추가한다.
   - 바뀐 조치는 `measure_ko`, `verified_at`, 날짜를 갱신한다.
   - 해제된 조치는 `level: lifted`와 `lifted_at`을 넣는다. 삭제하지 않는다.
   - 12개월 넘은 `lifted`는 삭제한다.
4. `as_of`를 조사 월로 바꾼다.
5. **검증 스크립트:** `scripts/export_controls/validate.py` (신규, Cursor 작성)
   - 스키마, ISO3, level·measure_type·category 값, 날짜 형식, https URL, id 중복 없음, hs_prefixes는 숫자만.
   - `lifted`에는 `lifted_at` 필수.
   - `high`인데 `verified_at`이 60일을 넘었으면 경고.
   - Codex 테스트도 통과해야 한다: `python3 -m unittest discover -s 'New for anti/scripts/commodity_trade/tests'`.
6. **PR로 올린다.** main에 직접 push하지 않는다. 데이터 PR 본문에는 이번 달 추가·변경·해제 목록과 원문 링크를 적는다.

## 6. 자동화 (역할 분담)
- **Cursor:** `New for anti/scripts/export_controls/**`에 후보 수집·검증 스크립트를 만들고, `workflow.yml.example`로 월간 실행 예시를 둔다. 제안: 매월 5일 UTC 02:00, 후보 수집 → 검증 → 데이터 PR.
- **Claude:** `.github/workflows/**` 설치와 UI 반영을 맡는다 (`OWNERS.md`에 따라 워크플로·UI는 Claude 소유).
- 사람이 원문을 확인하는 단계(§5-2)는 자동화하지 않는다. 자동 수집 결과는 후보일 뿐이고, 그대로 `high`로 올리지 않는다.

## 7. 지금 파일에서 재확인이 필요한 것 (다음 조사에서 우선 확인)
- **금속광물 5건** (`verified_at: 2026-08 (재확인 필요)`): 중국 갈륨·게르마늄, 흑연, 희토류, DR콩고 코발트, 칠레 리튬. 2025년 이후 쿼터 전환, 대미 조치, 유예처럼 형태가 바뀐 적이 있어 현재 상태 확인이 필요하다.
- **중국 비료**: 2026-08까지로 보도됐다. 9월 이후 연장 여부 확인이 필요하다.
- **인도 설탕**: 2026-09-30 종료 예정이다. 10월 새 시즌 정책을 반영해야 한다.
- **러시아 곡물 변동 수출세**: 2026년 말까지 일시 중단이다. 해제 시점을 반영해야 한다.
- **에너지**는 인도네시아 석탄 단일창구 1건뿐이라 빈약하다. 러시아 석유제품 수출 제한 같은 후보를 조사해 추가해야 한다.

## 8. 하지 말 것
- 수출세·부담금을 "금지"로 올리지 않는다.
- 추정 HS를 넣지 않는다.
- 수입 금지(예: 카자흐스탄 밀 수입 금지)를 수출통제로 넣지 않는다.
- 뉴스 한 건으로 `high`를 매기지 않는다.
- `climate_registry_v1.json`의 `trade_policy`는 더 이상 화면에 쓰이지 않는다. 수출통제 정보는 이 파일 하나로 관리한다.
