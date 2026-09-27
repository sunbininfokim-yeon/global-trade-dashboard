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
GET /api/commodity-reports?commodity=oil&country=USA&limit=60&offset=60   # 다음 묶음
```

창 하나에 고정 개수 상한은 없다(`--per-bucket` 500은 안전판일 뿐). 발표는 피드에서
밀려나도 `ARCHIVE_DAYS`(84일, 12주) 동안 스냅샷에 남고, 그보다 오래되면 빠진다.
응답의 `total`이 창 전체 건수, `offset`/`count`가 이번 묶음이다(`limit` 최대 100).
우측 패널은 60건씩 받아 화면 높이에 맞춰 쪽을 나누고, 마지막 쪽에서 `›`를 누르면
다음 묶음을 받아 이어 붙인다.

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

## 소스 상태 (2026-09-26 갱신 — 모든 대시보드 품목에 출처 연결)

**URL은 추측으로 켜지 않는다.** 세션 환경에서는 발간처 대부분에 접속이 안 되므로,
후보를 `tools/ops/feed_probe_targets.json` 에 적고 `claude/` 브랜치에 푸시하면
`.github/workflows/feed_probe.yml` 이 러너에서 받아 본다 (상태코드, RSS 여부, 항목 수,
최신 날짜, 페이지가 광고하는 피드, 차단 종류 — 브라우저 헤더·Chrome TLS 지문·실제 Chrome).

| 품목 | 새로 붙은 출처 |
|---|---|
| 천연고무 (`rubber`, 신규 창) | ANRPC 사무국 뉴스(월간 NR 통계), 베트남고무협회 국내·해외 뉴스 |
| 팜유 | MPOB RSS, BPDP RSS(수출부담금 규정), 인도네시아 무역부 RSS, GAIN(말레이시아·인니 Oilseeds) |
| 커피 | CONAB 뉴스 목록(브라질 커피 생산 추정), GAIN(Coffee Annual) |
| 구리·리튬 | Cochilco RSS |
| 알루미늄 / 은 / 금 | IAI / Silver Institute / WGC RSS |
| 철광석·원료탄 | worldsteel RSS (월간 조강 생산만 시리즈로 연결) |
| 핵심광물 전반 | USGS NMIC 뉴스 목록, NRCan Atom, 중국 상무부 영문 뉴스(수출통제) |
| 곡물 전반 | FAO 뉴스룸·EU DG AGRI(새 피드 주소), GAIN 복구 |

**GAIN:** `fas.usda.gov/data/search` 는 러너에서 늘 `Access Denied` (헤더·TLS·실제 Chrome
모두 — 경로 규칙). 품목 페이지(`/data/commodities/<x>`)와 국가 페이지(`/regions/<x>`)에
최신 GAIN 링크(`/data/gain/YYYY/MM/<slug>`)가 박혀 있고 보고서 페이지도 열리므로
`fas_gain_pages` 가 그 링크를 모아 각 페이지의 og:title·요약을 읽는다. 페이지에 그 달
안의 날짜가 없으면 URL의 연·월만 쓰고 `published_precision: "month"` 로 표시한다.

**2차 추가 (같은 날):** 주석 — 국제주석협회 RSS · 납/아연 — ILZSG 월간 보도자료 PDF
(`pdf_summary`: pypdf로 첫머리를 요약으로 인용) · 코발트 — Cobalt Institute 뉴스 ·
금 — WGC 보도자료 목록 · 인도네시아 ESDM(석탄·니켈 정책) · 아르헨티나 BCR 주간 보고.
**OPEC MOMR은 불가:** opec.org는 홈페이지만 열리고 MOMR 페이지·PDF·보도자료가
러너 IP에서 Cloudflare 방화벽 403 (실제 Chrome 포함). PDF 처리 기능은 이미 있으니
경로만 열리면 html_list + `pdf_summary`로 붙는다.

**메일(주간 즐겨찾기 다이제스트):** 항목마다 `first_seen_at`(처음 확인 시각)을 남긴다.
발행일 없는 목록형 출처는 이 시각으로 "이번 주 새 보고서"를 판단한다.

**출처 사전분류(commodity_hint)는 시장 기사에만 (2026-09-26):** ANRPC·ITA·MPOB·BPDP·
WGC·Silver Institute처럼 "이 출처 글은 기본적으로 X"라는 사전분류는 본문에 시장 용어
(생산·수출·가격·재고·통계·관세·거래…)가 있을 때만 적용한다. 사무총장 강연, 워크숍,
회원사 소식, 오피니언, 번역판 뉴스레터가 품목 보고서로 붙던 문제. 시장 용어가 없는
주요 보고서("Monthly NR Statistical Report")는 series_catalog로 그대로 붙는다.
기관 이름에 품목명이 든 경우(Association of Natural Rubber Producing Countries)는
`not_when`으로 품목 판단에서 뺀다.

**품목별 관련성 정리 (2026-09-26, 2차):**
- EIA 출처의 "기본 원유" 사전분류를 없앴습니다. 원유는 본문으로 판단합니다(`oil production/demand/prices…`, `OPEC`, `Hormuz`, `gasoline/diesel` 별칭). 식물성 기름 문구(`palm oil`, `soybean oil`…)는 먼저 지우고 봅니다. STEO/AEO는 시리즈로 원유·가스(·석탄)에 붙습니다.
- 출처 옵션 `market_only: true`: 시장 용어(생산·가격·재고·교역·정책·비축 매입 등)가 없는 글은 버립니다. PR성 게시판(MPOB·BPDP·IAI·Cochilco·NRCan·Cobalt·VRA·ESDM·MOFCOM·WGC·Silver·ITA·EU AGRI·NASS·CONAB)에 겁니다.
- 출처 옵션 `commodity_from: "title"`: 품목은 제목에서만 판단합니다(EU DG AGRI — 본문에 사료 대두가 스쳐 나오는 달걀 기사).
- 제목 기준 행정 공지 필터 `ADMIN_TERMS`: 보고서 지연, 추정 중단, 재조사, 입찰(T/P), 보도 예고, 인사, 협약. 시리즈 이름이 붙어 있어도 버리고, 제목에 수치가 있으면 남깁니다.

**간헐 차단과 이월:** fas.usda.gov·usda.gov는 같은 날에도 러너에 따라 403을 준다
(1회차 통과, 2회차 전부 403). 그래서 실패한 출처는 직전 결과 파일에서 그 출처의 보고서
(45일 이내)를 다시 태깅해 이어 붙이고, `feed_status`에 `carried_over`로 표시한다.
GAIN은 이미 읽은 보고서 페이지를 다시 받지 않고, 요청 사이에 1초를 쉬며,
목록 페이지 5개가 연달아 실패하면 그 회차를 멈춘다.

**안 되는 곳 (2026-09-26 확인):** ICSG·ILZSG·INSG·국제주석협회·GAPKI·MPOC·Cecafé
(JS 챌린지), IEA·말레이시아고무협의회(Cloudflare), Cobalt Institute(Sucuri),
태국 고무청(RAOT, 러너에서 타임아웃), 인도 고무청(중간 인증서 누락), ICO(RSS 비어 있음),
USGS `/news/minerals/feed`(빈 채널). 말레이시아 고무청(LGM)은 SPA라 뉴스 API를 찾아야 한다.

## 소스 상태 (2026-09-02, 첫 라이브 Actions 실행 결과 반영)

레포 작업 환경(이 세션)은 일반 웹 egress 자체가 대부분 막혀 있어 (github.com·npm·PyPI 류
개발 인프라만 허용 — google.com도 안 열린다) URL을 여기서 직접 검증할 수 없었다.
GitHub Actions 러너에는 이 제약이 없어서, 머지 후 `workflow_dispatch`로 한 번 실제로
돌려 진짜 결과를 얻었다 ([run #1](https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/33589460784)).

**enabled (8/23, 라이브 확인됨):**

| 소스 | 결과 |
|---|---|
| `us_usda_newsroom` | 10 items |
| `us_nass_todays_reports` | 4 items — 이름대로 "오늘 발표된 것"만이라 적음 |
| `us_nass_asb` | 40 items — 실제로는 2023~2024년까지 거슬러 올라가는 롤링 공지 아카이브. 최신성 감쇠(recency decay)가 여기서 진짜로 작동해야 함 |
| `us_nass_news` | 40 items — 같은 아카이브 형태 |
| `us_eia_today_in_energy` | 11 items |
| `us_eia_press` | 10 items |
| `in_pib_agriculture` | 20 items |
| `us_fas_gain_reports` | 확인됨(개별 건수 미기록) — 2026-09-02 [run #3](https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/33631914603)의 실패 목록에 없음. Akamai Bot Manager 우려와 달리 GitHub Actions 러너의 스크레이프가 그대로 통과했다 |

**enabled, 아직 라이브 미확인 (2026-09-02, 운영자가 직접 확인해준 URL):**

- `jp_meti_en` (`meti.go.jp/ml_index_en_atom.xml`) — 일본 경제산업성. 운영자가 직접
  준 URL, 검색으로 같은 명명 규칙의 자매 피드(`ml_index_release_atom.xml`, 일본어판으로
  추정)가 나와서 근거가 겹친다. Atom 포맷 -- `parse_feed()`가 RSS/Atom 둘 다 처리하니
  코드 변경 불필요. 상품 전용 기관이 아니라 SME 정책·제조업·지재권 같은 무관한
  공지가 대부분일 텐데, 그중 에너지 안보·희토류 등 전략광물 비축 정책 발표가 이
  파이프라인이 원하는 부분이다 -- 나머지는 그냥 드롭된다.
- `int_spglobal_energy` (`spglobal.com/energy/en/news-research/rss-feed`) — **"공식
  발행처만" 원칙의 유일한 의도적 예외**(2026-09-02, 운영자 판단). 원문 기사는
  유료지만 RSS 자체(헤드라인+짧은 요약)는 무료로 공개하는, 유료 트레이드 프레스의
  흔한 형태라는 근거로 추가. 가중치는 이 파일에서 가장 낮은 축(1.0)으로 잡아서,
  같은 발표를 USDA/EIA/NASS 등 공식 소스가 이미 다뤘을 때 상업 소스가 순위를
  앞지르지 않게 했다. 이건 애그리게이터 전면 허용이 아니라 이 한 건에 대한
  예외다 — 같이 검토했던 marketroro.com(정체 확인 불가)은 그대로 제외했다.

- `us_usgs_news` — 이전 URL(`/programs/mineral-resources-program/news/feed`)이 run #3에서
  SSL 인증서 오류로 실패했는데, 운영자가 그 URL을 직접 열어 실제 응답을 붙여줬다: 유효한
  RSS 채널이었고, 그 채널 자신의 `<atom:link rel="self">`가 진짜 정본 URL이
  `https://www.usgs.gov/news/minerals/feed`라고 밝히고 있었다 — 우리가 요청한 경로와
  다르다. Drupal 별칭 경로가 리다이렉트를 거치면서 인증서 체인이 다른 호스트로 갔던 게
  SSL 실패의 실제 원인이었을 가능성이 높다. 정본 URL로 바로 교체하고 재활성화했다.
  단, 운영자가 받아온 응답 자체에는 `<item>`이 하나도 없었다(에러는 아니고 그냥 빈 채널) —
  실제로 항목이 들어오는지는 다음 Actions 실행이 확인.
- `us_eia_whats_new` (`eia.gov/about/new/WNtest3.php`) — 운영자가 기존 EIA 소스 2개와
  같이 직접 준 URL. 웹서치에서도 이미 실제 XML을 서빙하는 걸로 독립 확인됐던 주소라
  근거가 겹친다. `us_eia_today_in_energy`/`us_eia_press`는 둘 다 `commodity_hint: oil`이라
  본문에 상품이 안 걸리면 오일로 취급되는데, 이 피드는 EIA가 내는 전체(석탄·천연가스
  포함) "새 소식"이라 일부러 commodity_hint를 안 걸었다 — 본문에서 안 잡히면 그냥 버려진다.

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

**추가로 disabled — 2026-09-02 [run #3](https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/33631914603)에서 확정:**

- **`int_fao_giews`** — HTTP 404. `/<섹션>/news/rss/<언어>` 패턴(fao.org/nigeria, fao.org/uruguay에서는
  실제로 작동)이 GIEWS에는 안 맞았다 — GIEWS 자체 페이지 구조는 `news`가 아니라
  `reports`(`fao.org/giews/reports/en`)라, 다음 시도는 `/giews/reports/rss/en`. 여전히
  세계 수급표(`_global`)를 내는 값어치 있는 소스라 재탐색 우선순위 유지.

(`us_usgs_news`도 이 실행에서 SSL 인증서 오류로 같이 죽었었는데, 운영자가 직접 정본 URL을
찾아줘서 위 "enabled, 아직 라이브 미확인" 표로 옮겼다 — 자세한 경위는 거기 참조.)

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
