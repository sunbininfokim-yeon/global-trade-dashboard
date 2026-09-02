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
  ]
}
```

태깅에 실패한 발표(추적 안 하는 상품이거나, off-topic으로 걸러진 것)는 **그냥 버린다** —
지금은 리뷰 큐도, 별도 저장도 없다. 별칭 누락을 찾아내는 루프는 아직 안 만들었다.

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

## 소스 상태 (2026-09-02, 첫 라이브 Actions 실행 결과 반영)

레포 작업 환경(이 세션)은 일반 웹 egress 자체가 대부분 막혀 있어 (github.com·npm·PyPI 류
개발 인프라만 허용 — google.com도 안 열린다) URL을 여기서 직접 검증할 수 없었다.
GitHub Actions 러너에는 이 제약이 없어서, 머지 후 `workflow_dispatch`로 한 번 실제로
돌려 진짜 결과를 얻었다 ([run #1](https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/33589460784)).

**enabled (7/14, 라이브 확인됨):**

| 소스 | 결과 |
|---|---|
| `us_usda_newsroom` | 10 items |
| `us_nass_todays_reports` | 4 items — 이름대로 "오늘 발표된 것"만이라 적음 |
| `us_nass_asb` | 40 items — 실제로는 2023~2024년까지 거슬러 올라가는 롤링 공지 아카이브. 최신성 감쇠(recency decay)가 여기서 진짜로 작동해야 함 |
| `us_nass_news` | 40 items — 같은 아카이브 형태 |
| `us_eia_today_in_energy` | 11 items |
| `us_eia_press` | 10 items |
| `in_pib_agriculture` | 20 items |

실제 태깅 결과도 확인됨 — 예: "USDA Forecasts U.S. Corn Production Up and Soybean Production
Down" → `corn`+`soybeans`·`USA`, `USDA_CROP_PRODUCTION` 시리즈로 정확히 매칭.

**disabled (URL 사망 확인, 사유별):**

- **HTTP 404** (URL 자체가 죽음): `us_usda_ers_newsroom`, `us_usda_ers_charts`,
  `us_fas_newsroom`, `ca_statcan_daily`, `int_fao_newsroom`, `eu_agri`
- **`not_a_feed_payload`** (주소는 살아있지만 RSS가 아닌 응답 — URL/쿼리 파라미터만
  고치면 될 가능성): `br_conab`
- **URL/구조 미검증** (아직 시도 안 함): ABARES, OPEC, LME 마켓 공지(`int_lme_notices`),
  우크라이나 농업정책부
- **IGC는 별도 판정 — RSS가 아예 없을 가능성**: 2026-09-02에 다시 파봤지만 Grain Market
  Report(GMR) 본체는 구독자 전용(subs@igc.int)이고, 공개된 페이지(`gmr_summary.aspx`)는
  짧은 요약 하나뿐이라 RSS를 뒷받침할 근거 자체가 없었다. 근거 없이 URL만 바꿔 넣지
  않고 그대로 disabled 유지 — 다른 미검증 소스들과 달리 "아직 못 찾은" 게 아니라
  "애초에 없을 수도 있는" 케이스로 다르게 기록해둔다.

**enabled, 아직 라이브 미확인:**

- `us_fas_gain_reports` (`kind: fas_gain_cards`) — USDA GAIN 주재관 보고서. 2026년에
  `gain.fas.usda.gov`에서 `fas.usda.gov/data/search?reports[0]=report_type:10251`로
  이전됐고, 운영자가 직접 붙여준 실제 페이지 소스로 구조를 확인했다: Drupal 10
  Views/Facets 목록이라 `.c-card__date`/`__url`/`__title`/`__content`에 날짜·링크·제목·
  요약이 이미 서버 렌더링돼 있다 — 별도 JS/XHR API가 필요 없는, 진짜 스크레이프 가능한
  페이지. `parse_fas_gain_cards`(`commodity_reports/feeds.py`)가 `<time datetime="` 경계로
  카드를 잘라 각각에서 네 필드를 뽑는다. 미해결 위험: 페이지에 Akamai Bot Manager
  스크립트(`akam/13/...`)가 붙어 있어 실제 브라우저 세션은 통과해도 GitHub Actions 같은
  비-브라우저 정기 스크레이퍼는 차단될 수 있다 — 이 세션은 fas.usda.gov 자체를 못 열어서
  라이브로 확인 불가. 다음 Actions 실행의 `feed_status`가 진짜 판정.
- `int_fao_giews` — 죽은 `int_fao_newsroom`(일반 보도자료) 대신, 이 파이프라인이 정말
  원하는 세계 수급표 콘텐츠(Crop Prospects and Food Situation, 국가별 흉작 경보)를 내는
  GIEWS 쪽으로 다시 시도. URL(`fao.org/giews/news/rss/en`)은 근거 있는 추정이다 — FAO
  뉴스룸 자체의 `/newsroom/rss/en/`은 첫 라이브 실행에서 404 확인됐지만, 검색으로
  fao.org의 다른 두 사이트(`fao.org/nigeria/news/rss/en`, `fao.org/uruguay/noticias/rss/ar`)가
  실제 XML을 서빙하는 게 구글에 그대로 인덱싱된 걸 찾았다 — 같은 CMS, 같은
  `<섹션>/<news 계열 단어>/rss/<언어>` 패턴. GIEWS 인스턴스 자체가 그 패턴을 따르는지는
  이 세션에서 fao.org를 못 열어서 확인 불가 — 다음 Actions 실행이 판정.
- `us_usgs_news` — 기존 `/news/rss` 추정(한 번도 테스트 안 됨)을
  `/programs/mineral-resources-program/news/feed`로 교체하고 활성화. USGS 사이트도
  FAS GAIN 검색 페이지와 같은 Drupal Views 목록이라, Views의 RSS 표시는 관례적으로
  `<경로>/feed`에 있다 — 검색 중 실제로 그 접미사로 끝나는 usgs.gov URL
  (`gallery.usgs.gov/news/national-news-release/feed`)이 나온 게 이 관례의 근거다(추측이
  아니라). 이 경로 자체는 여전히 미확인 — usgs.gov도 이 세션에서 fas.usda.gov처럼
  못 연다. 다음 Actions 실행이 판정. 금속 15종(금·은·구리·알루미늄 등)이 지금
  소스가 하나도 없는 가장 큰 공백이라 우선순위가 높다.

FAO가 6개 중 가장 아쉬웠다 — 세계 수급표(`_global`)를 내는 유일한 확인 소스였다.
그래서 `int_fao_giews`로 바로 재시도했다. 나머지 재탐색 우선순위: FAS(타국 작황 보고,
US 소스들과 안 겹침) > CONAB(파라미터만 고치면 될 수도) > 나머지.

다음 Actions 실행(`workflow_dispatch` 수동 또는 4시간 주기)의 `failed feeds:`가 계속
정답지다. 새 URL을 찾으면 `enabled: true` + 발견 경위를 notes에 남긴다.

## 후보 (아직 설정에 없음)

- **CASDE** (China Agricultural Supply and Demand Estimates, 중국 농업농촌부) —
  중국판 WASDE. 매월 발표하지만 중국어 PDF/표 형식이라 영문 RSS 유무부터 불확실하다.
  접근 난도가 다른 소스보다 훨씬 높아서 지금은 후보로만 남겨둔다 — `config/sources.json`에
  아직 넣지 않았다.

## 아직 안 한 것

- **USDA GAIN 검색 결과 페이지네이션/국가·상품 필터**: 지금 `us_fas_gain_reports`는
  `report_type:10251`(GAIN 전체) 목록의 1페이지만 긁는다. Drupal Facets URL 패턴
  (`reports[1]=report_regions:<id>`, `report_commodities:<id>`)으로 국가/상품별 필터나
  `&page=N` 페이지네이션(전체 48000여 건)을 걸 수 있지만, 지금 태깅 엔진이 필터 없는
  일반 목록도 본문에서 직접 국가/상품을 뽑아내므로 아직 필요하지 않다.
- PDF 본문 파싱 (WASDE 표 숫자 추출). 지금은 피드가 준 발췌까지만 — 이건 "뉴스처럼 붙이기"가
  아니라 "표의 수치를 카드에 찍기"라 범위가 다른 작업이다 (`official_reports`의 QRA
  추출 방식과 같은 종류). 필요해지면 별도로 붙인다.
- 한국어 번역 상시화 — 무료 쿼터로는 하루 수백 건을 감당하지 못한다.
