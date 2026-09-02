# Commodity reports — 공식 기관 보고서를 상품 × 국가 창에 붙이기 (Phase 2-2)

USDA·CONAB·FAO·EIA 같은 **공식 기관이 하루 수십 건씩 내는 발표**를 수집해서,
그 보고서가 **어느 상품 · 어느 나라 이야기인지** 태깅하고,
대시보드 2단계(상품 → 국가 포커스) 창에 뉴스처럼 붙인다.

```
공식 RSS/리스트 페이지
  → 상품 태깅 (다국어 별칭)
  → 국가 태깅 (본문 우선, 발간 기관은 폴백일 뿐)
  → 중요도 순위 (시리즈 카탈로그 × 최신성 × 사람 라벨)
  → public/data/commodity_reports_v1.json
  → GET /api/commodity-reports?commodity=soybeans&country=USA
  → trade.js  renderCommodityReports()  → #reports-slot
```

## 핵심 규칙: **본문이 창을 정한다**

발간 기관이 아니라 **보고서가 말하는 나라**로 간다.

| 보고서 | 가는 창 |
|--------|---------|
| USDA "U.S. soybean production 상향" | **USA · 대두** |
| USDA "Brazil wheat production 하향" | **BRA · 밀** ← USDA가 냈어도 브라질 창 |
| CONAB "Acompanhamento da safra" (나라 언급 없음) | **BRA · 대두** (`default_country` 폴백) |
| FAO "World wheat production 사상 최대" | **`_global`** — 모든 나라의 밀 창에 「세계」 태그로 표시 |

`default_country`는 **본문에 나라가 하나도 없을 때만** 쓰인다.
`scope_hint: "global"` 인 발간처(FAO·IGC·IEA·OPEC)는 그 폴백도 쓰지 않는다 —
FAO의 무국적 발표는 FAO라는 나라의 뉴스가 아니라 세계 수급표다.

제목에 나온 나라가 본문에만 나온 나라보다 앞선다.
"Argentina's drought lifts US soybean exports" 는 아르헨티나를 언급한 **미국** 보고서다.

## 실행

```bash
cd "New for anti/scripts/commodity_reports"

# 단위 테스트 (네트워크 불필요)
python3 -m unittest discover -s tests -v

# 오프라인 픽스처 빌드
python3 build_reports.py build --fixtures tests/fixtures --print-stats

# 라이브 (네트워크 필요)
python3 build_reports.py build --print-stats

# 한국어 헤드라인 (MyMemory 무료 쿼터, 느림 — 기본 off)
python3 build_reports.py build --translate --translate-limit 60
```

출력: `New for anti/public/data/commodity_reports_v1.json`
자동 갱신: `.github/workflows/commodity_reports.yml` (4시간마다 :40)

## 산출 스키마

`schemas/commodity_reports_v1.schema.json`

보고서 본문은 **한 번만** 저장하고, 창별로는 id만 들고 있다.
한 보고서가 밀·옥수수 두 창에, 또는 브라질·아르헨티나 두 나라에 동시에 걸리는 게
정상이라(그게 이 기능의 요점) 복사본을 창마다 두면 파일이 몇 배로 커진다.

```jsonc
{
  "index": {
    "wheat": {
      "BRA": ["cb1dc5add…"],   // ISO3 = 대시보드 countryCode() 가 이미 계산하는 값
      "_global": ["ce9b4103…"] // 나라를 특정하지 않은 세계 수급 보고서
    }
  },
  "items": [
    {
      "id": "cb1dc5add…",
      "title": { "original": "…", "original_lang": "en", "ko": null },
      "summary": "피드가 함께 배포한 본문 발췌 (≤600자)",
      "url": "발간처 원문 — 카드 제목이 여기로 링크",
      "agency_ko": "미 농무부",
      "commodities": ["wheat"], "countries": ["BRA"],
      "scope": "country", "country_source": "text",
      "series_id": "USDA_WASDE", "importance": 5.38,
      "reasons": ["series:USDA_WASDE", "has_figure", "revision_language"]
    }
  ],
  "pending_review": [ /* 태깅에 실패한 발표 — 별칭 누락을 눈에 보이게 */ ]
}
```

## API

```
GET /api/commodity-reports                                  # 어떤 창에 몇 건 있는지
GET /api/commodity-reports?commodity=soybeans               # 세계 → 나머지
GET /api/commodity-reports?commodity=soybeans&country=USA   # 그 나라 먼저, 세계는 뒤
```

로컬 정적 서버에는 `/api`가 없으므로 404가 정상이다.
`trade.js`가 `public/data/commodity_reports_v1.json`을 직접 읽어 **같은 순서로** 폴백한다.

## 저작권

제목 + 피드가 스스로 배포한 요약 발췌 + 원문 링크까지만. **전문 재배포는 하지 않는다.**
뉴스 티커(`commodity_news`)와 같은 자세다.

## 설정 파일

| 파일 | 역할 |
|------|------|
| `config/sources.json` | 발간처 레지스트리 (`default_country`, `scope_hint`, `commodity_hint`, `weight`) |
| `config/commodities.json` | 상품 다국어 별칭. **키는 `index.html`의 `data-target` 과 반드시 같아야 한다** |
| `config/countries.json` | ISO3 별칭 + 형용사형 + 산지(주·지방) |
| `config/series_catalog.json` | "주요 보고서" 정의 (WASDE, safra, STEO, MOMR…) |

### 태깅에서 조심한 것들

- `oil` 에 맨 `oil`은 안 넣는다 — palm/soybean oil은 다른 시장이고 각자 창이 있다.
- `lead`는 **구절 별칭만** (`refined lead`, `lead smelter`…). 맨 `lead`는 동사일 때가 훨씬 많고,
  시장 문맥을 요구해도 "talks led by"를 못 거른다.
- `gold`·`silver`·`sugar`·`coffee`·`tin`은 `require_context: true` —
  생산/수출/재고/가격 같은 시장 용어가 같이 나와야 인정한다.
- 나라는 **가장 긴 별칭이 자리를 먼저 차지한다**. `North Korea`가 `Korea`를,
  `Papua New Guinea`가 `Guinea`를 이긴다. 별칭을 추가할 때 순서는 신경 쓰지 않아도 된다.
- `US`/`UK`/`UAE`/`DRC`는 `cased_aliases` — 대소문자를 구분해야 "told us"가 미국이 되지 않는다.

## 학습 (사람 라벨 루프)

`official_reports`와 같은 방식이다. 자동 ML이 아니라 **카탈로그 + 라벨**.

```bash
python3 build_reports.py label --series-id USDA_WASDE --label promote --note "월간 수급 상향은 항상 톱"
python3 build_reports.py label --series-id USDA_CROP_PROGRESS --label drop
```

`cache/label_history.jsonl` 에 쌓이고 다음 빌드의 시리즈 가중치에 반영된다
(promote 1.35 · keep 1.0 · drop 0.25, 시리즈별 평균).

**새 종류의 중요 보고서**가 보이면 `config/series_catalog.json` 에 `series_id`를 추가하는 것이
"학습 정의"의 정본이다.

## 소스 상태 (2026-09-01)

레포 작업 환경은 일반 웹 egress 자체가 대부분 막혀 있다 (github.com·npm·PyPI 류 개발
인프라만 허용 — google.com도 안 열린다). usda.gov·lme.com 등을 콕 집어 막는 게 아니라
**이 세션 전체가 그 정책 아래라서 여기서는 어떤 방법으로도 라이브 검증이 안 된다.**
GitHub Actions 러너에는 이 제약이 없다.

- **enabled**: USDA(뉴스룸·ERS·FAS), EIA(Today in Energy·press), CONAB, Statistics Canada,
  FAO, EU DG AGRI, PIB India
- **disabled (URL/구조 미검증)**: ABARES, IGC, OPEC, USGS(= "미국 광물부", 매핑 확인됨),
  LME 마켓 공지(`int_lme_notices` — 가격·재고 데이터 아님, 공지문만), 우크라이나 농업정책부

첫 Actions 실행 로그의 `failed feeds:` 목록이 정답지다.
살아 있는 것은 `enabled: true`로, 죽은 것은 사유·날짜와 함께 `false`로 바꾼다.

## 후보 (아직 설정에 없음)

- **CASDE** (China Agricultural Supply and Demand Estimates, 중국 농업농촌부) —
  중국판 WASDE. 매월 발표하지만 중국어 PDF/표 형식이라 영문 RSS 유무부터 불확실하다.
  접근 난도가 다른 소스보다 훨씬 높아서 지금은 후보로만 남겨둔다 — `config/sources.json`에
  아직 넣지 않았다.

## 아직 안 한 것

- **USDA GAIN 원문 API**: 서술형 주재관 보고서(attaché report) 자체는 `gain.fas.usda.gov`
  검색 포털에서 PDF로 배포된다. 이미 이 레포가 쓰고 있는 `USDA_FAS_API_KEY`는 PSD Online
  (숫자 수급표, `/api/usda-fas`)과 ESR(주간 수출판매, `/api/usda-esr`)에 연결돼 있을 뿐,
  GAIN 자체의 JSON 엔드포인트는 아니다 — 검색 포털 뒤에 API가 있는지조차 라이브로
  확인해야 한다.
- PDF 본문 파싱 (WASDE 표 숫자 추출). 지금은 피드가 준 발췌까지만 — 이건 "뉴스처럼 붙이기"가
  아니라 "표의 수치를 카드에 찍기"라 범위가 다른 작업이다 (`official_reports`의 QRA
  추출 방식과 같은 종류). 필요해지면 별도로 붙인다.
- 한국어 번역 상시화 — 무료 쿼터로는 하루 수백 건을 감당하지 못한다.
