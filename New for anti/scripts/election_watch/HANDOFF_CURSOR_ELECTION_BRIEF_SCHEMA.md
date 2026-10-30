# 선거 개괄 창 — 수집 계약 (Cursor 안내용)

좌측 `세계 선거 일정`의 한 줄을 클릭하면 **그 선거가 어떤 선거인지** 보여 주는 창을
띄우려 한다. 이 문서는 그 창이 읽을 데이터의 계약이다.

**먼저 읽을 것:** 이 저장소에서 반복된 실패는 "수집은 했는데 UI가 안 읽음"이다
(`race_progress`, 슈퍼팩, 의회 공석 컨텍스트 모두 발행 후 한동안 화면에 없었다).
그래서 **필드명을 여기 적힌 그대로** 써야 한다. 뜻이 같아도 이름이 다르면 안 읽힌다.

---

## 0. 지금 있는 것 / 없는 것 (2026-09 기준 실측)

`public/data/elections_calendar_master_v1.json` 안의 블록별 상태:

| 블록 | 행 수 | 상태 |
|---|---|---|
| `world_by_month` | 38 | **타임라인이 읽는 유일한 블록. 필드 5개뿐** — `date / iso3 / type / label_en / label_ko` |
| `board_tracked_all_events` | 108 | 훨씬 두꺼움(필드 37종). **UI가 전혀 안 읽고 있음** |
| `world_national_highlights` | 48 | `significance / status / result` 보유 |
| `party_leadership_and_conventions` | 23 | `board_tracked` 의 부분집합 |

`world_by_month` → `board_tracked_all_events` 를 `(iso3, date)` 로 조인하면
**38건 중 24건이 붙는다.** 못 붙는 14건은 대부분 `summary.board_countries` 19개국
밖이지만(포르투갈·태국·스위스·콜롬비아·헝가리 등), **프랑스·러시아 2건은 추적 대상
국가인데도 빠져 있다.** 전체 목록과 원인은 4절에 있다.

**그래서 이 작업은 "새 데이터 수집"이 아니라 두 가지다.**

1. 이미 있는 두꺼운 블록에 **없는 칸만** 채운다 (아래 2·3절).
2. 조인 안 되는 14건을 `board_tracked_all_events` 에 올린다 (아래 4절).

---

## 1. 지켜야 할 규칙

### 1-1. null 대신 한국어 센티널

이 파일은 이미 `null_policy` 를 선언하고 있다. **그대로 따른다.**

```json
"null_policy": { "없음": "해당 없음", "불명": "미확정" }
```

- `"없음"` — 제도상 존재하지 않음 (예: 중국 연방하원 선거)
- `"불명"` — 있는데 아직 확인 못 함
- `null` / `""` / `0` **금지.** 0은 "0석"이라는 주장이 된다.

이 구분이 화면에서 갈린다. `"없음"` 은 칸을 지우고, `"불명"` 은 "수집 예정"으로 남긴다.
둘을 섞으면 "이 나라엔 하원이 없다"와 "아직 못 찾았다"가 같은 글자로 나온다.

### 1-2. 출처 없는 행은 받지 않는다

모든 신규·수정 행에 `sources: []` (URL 또는 공식 문서 식별자) 필수.
보도 기반 추정이면 `status` 로 표시하고 본문에 "보도"라고 적는다. 기존 관례:

```json
"status": "tentative",
"notes": "Flávio Bolsonaro 유력 보도 — 공식 전당 일자 TSE/당 공고 확인 필요"
```

### 1-3. 기존 필드명을 재사용한다

이미 쓰이고 있는 이름이다. **새로 짓지 말 것.**

`id` `type` `label_ko` `date` `date_end` `status` `iso3` `sources` `notes`
`chamber` `level` `district` `office` `party_id` `party_abbr` `venue`
`winner` `result` `result_summary` `candidates` `rules_summary`
`first_round_date` `runoff_date` `date_start` `date_span`
`market_significance_invest_lens` `interim_results` `interim_as_of`

### 1-4. 합산·추정 금지

- 정당별 의석을 더해 총계를 만들지 않는다. 원문 총계가 있으면 그것을 쓴다.
- 득표율을 의석으로 환산하지 않는다.
- 여러 출처가 어긋나면 하나를 고르지 말고 둘 다 남긴다 (`notes` 에 병기).

### 1-5. `id` 규칙

기존 관례 그대로: `{iso3소문자}-{연도}-{슬러그}`

```
deu-2026-bw-landtag    jpn-2025-sangiin    kor-2026-dpk-convention
```

---

## 2. 새 파일 — `elections_system_v1.json` (선거제도)

**경로:** `New for anti/public/data/elections_system_v1.json`

제도는 이벤트마다 바뀌지 않는다. 독일 연방하원을 2026년에 뽑든 2029년에 뽑든
"연동형 비례대표 630석"은 같다. 그래서 **국가 × 선거 종류로 1행**을 만들고,
이벤트 행에서 참조한다. (미국 EOP 조직도 `elections_us_eop_v1.json`,
중국 당 직위 `elections_cn_party_v1.json` 과 같은 성격의 파일이다.)

```json
{
  "schema": "elections_system_v1",
  "as_of": "2026-09-16",
  "null_policy": { "없음": "해당 없음", "불명": "미확정" },
  "sources": ["..."],
  "systems": [ /* 아래 행 형식 */ ]
}
```

### 행 형식

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `id` | string | ✅ | `{iso3소문자}-{기관슬러그}` 예: `deu-bundestag` |
| `iso3` | string | ✅ | 국가 코드 |
| `type` | string | ✅ | 이벤트 행의 `type` 과 같은 어휘 — `general` `presidential` `local` `referendum` `party_leadership` |
| `chamber` | string | | `bundestag` `shugiin` `house` `senate` 등. 단원제면 `"없음"` |
| `name_ko` / `name_en` | string | ✅ | 기관 이름. 예: `독일 연방하원 (분데스탁)` |
| `term_years` | number | ✅ | 임기. 고정 아니면 `"불명"` 대신 `term_note_ko` 로 설명 |
| `term_note_ko` | string | | 예: `중의원은 임기 4년이나 해산이 있어 만료일이 곧 선거일은 아님` |
| `seats_total` | number | ✅ | 정수(定數) |
| `seats_note_ko` | string | | 예: `2023 개정으로 초과·보정의석 폐지, 630 고정` |
| `method_ko` | string | ✅ | **한 줄 요약.** 예: `연동형 비례대표 (혼합비례)` |
| `method_detail_ko` | string | ✅ | 2~4문장. 유권자가 몇 표를 어떻게 던지고 의석이 어떻게 배분되는지 |
| `districts` | object | | `{ count, kind_ko, geometry_asset }` — `geometry_asset` 은 선거구 경계 파일 경로 또는 `"없음"` |
| `threshold_ko` | string | | 봉쇄조항. 예: `5% 또는 지역구 3석` |
| `rounds` | number | ✅ | 1 또는 2 |
| `runoff_rule_ko` | string | | 결선 조건. 없으면 `"없음"` |
| `voting_age` | number | ✅ | |
| `compulsory` | boolean | ✅ | 의무투표 여부 |
| `head_selection_ko` | string | ✅ | 이 선거가 행정수반을 어떻게 정하는지. 예: `총리는 연방하원이 선출` / `직선` / `"없음"` |
| `sources` | array | ✅ | |

### 채워진 예시 — 독일 연방하원

```json
{
  "id": "deu-bundestag",
  "iso3": "DEU",
  "type": "general",
  "chamber": "bundestag",
  "name_ko": "독일 연방하원 (분데스탁)",
  "name_en": "Bundestag",
  "term_years": 4,
  "seats_total": 630,
  "seats_note_ko": "2023년 선거법 개정으로 초과의석·보정의석 폐지, 정수 630 고정",
  "method_ko": "연동형 비례대표 (혼합비례)",
  "method_detail_ko": "유권자는 2표를 던진다. 제1표(Erststimme)는 299개 지역구에서 최다득표자를 뽑고, 제2표(Zweitstimme)는 주별 정당명부에 던진다. 의석 총수 배분은 제2표 득표율만으로 정해지며, 지역구 당선자는 그 정당 몫 안에서 채워진다. 2023년 개정 이후 정당 몫을 넘긴 지역구 당선자는 의석을 받지 못한다.",
  "districts": { "count": 299, "kind_ko": "소선거구", "geometry_asset": "없음" },
  "threshold_ko": "제2표 5% 이상 또는 지역구 3석 이상",
  "rounds": 1,
  "runoff_rule_ko": "없음",
  "voting_age": 18,
  "compulsory": false,
  "head_selection_ko": "총리(Bundeskanzler)는 연방하원이 선출한다. 직선 아님.",
  "sources": ["https://www.bundeswahlleiterin.de/..."]
}
```

### 채워진 예시 — 일본 중의원

```json
{
  "id": "jpn-shugiin",
  "iso3": "JPN",
  "type": "general",
  "chamber": "shugiin",
  "name_ko": "일본 중의원",
  "name_en": "House of Representatives",
  "term_years": 4,
  "term_note_ko": "임기 4년이나 해산이 있어 만료일이 곧 선거일은 아니다.",
  "seats_total": 465,
  "method_ko": "병립형 — 소선거구 289 + 비례대표 176",
  "method_detail_ko": "유권자는 2표를 던진다. 소선거구 289석은 각 구 최다득표자, 비례대표 176석은 11개 권역 정당명부에서 뽑는다. 두 배분은 서로 연동되지 않는다(병립형). 중복입후보가 가능해 지역구에서 진 후보가 석패율로 비례 부활할 수 있다.",
  "districts": { "count": 289, "kind_ko": "소선거구", "geometry_asset": "없음" },
  "threshold_ko": "없음",
  "rounds": 1,
  "runoff_rule_ko": "없음",
  "voting_age": 18,
  "compulsory": false,
  "head_selection_ko": "내각총리대신은 국회가 지명하며 중의원 의결이 우선한다(헌법 67조).",
  "sources": ["https://www.soumu.go.jp/senkyo/..."]
}
```

### 우선순위

`summary.board_countries` 19개국 × 실제 타임라인에 뜨는 선거 종류부터.
**전 세계를 채우려 하지 말 것.** 순서:

1. `USA` (하원·상원·대선) · `JPN` (중의원·참의원) · `DEU` (연방하원·주의회)
2. `KOR` `FRA` `GBR` `IND` `BRA`
3. 나머지 board_countries

---

## 3. 기존 이벤트 행에 덧붙일 것 (`board_tracked_all_events`)

**경로:** 생성원인 `config/calendars/{iso3}_2026.json` 을 고친다.
`elections_calendar_master_v1.json` 을 직접 손대지 않는다 (재생성 시 덮어써짐).

이미 있는 필드는 3절에서 다루지 않는다. **없어서 추가할 것만** 적는다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `system_id` | string | 2절 `elections_system_v1.json` 의 `id`. **이 한 줄이 제도 설명을 창에 붙인다.** 해당 제도 행이 없으면 `"불명"` |
| `previous` | object | **직전 같은 선거의 결과.** 아래 형식 |
| `contested_ko` | string | 이번에 뽑는 대상. 예: `전체 465석` / `상원 100석 중 33석` / `주지사 1인` |
| `parties_running` | array | 주요 정당. 아래 형식. 5~8개면 충분하고 군소정당은 생략 가능 |

### `previous` 형식

```json
"previous": {
  "date": "2025-02-23",
  "turnout_pct": 82.5,
  "seats_total": 630,
  "by_party": [
    { "abbr": "CDU/CSU", "name_ko": "기민·기사 연합", "vote_pct": 28.52, "seats": 208 },
    { "abbr": "AfD", "name_ko": "독일을 위한 대안", "vote_pct": 20.80, "seats": 152 },
    { "abbr": "SPD", "name_ko": "사회민주당", "vote_pct": 16.41, "seats": 120 },
    { "abbr": "GRÜNE", "name_ko": "동맹 90/녹색당", "vote_pct": 11.61, "seats": 85 },
    { "abbr": "LINKE", "name_ko": "좌파당", "vote_pct": 8.77, "seats": 64 },
    { "abbr": "SSW", "name_ko": "남슐레스비히 유권자연합", "vote_pct": 0.15, "seats": 1 }
  ],
  "government_formed_ko": "CDU/CSU–SPD 연립, 메르츠 총리 (2025-05-06 취임)",
  "sources": ["https://www.bundeswahlleiterin.de/..."]
}
```

- `vote_pct` 는 **의석 배분 기준표** 기준 (독일이면 제2표). 어느 표인지 `notes` 에 적는다.
- `seats` 와 `vote_pct` 중 하나만 있으면 있는 것만 넣는다. 나머지는 키를 **생략**한다
  (`0` 이나 `null` 을 넣지 않는다).
- 합계가 `seats_total` 과 안 맞아도 **맞추지 말 것.** 군소정당을 생략했으면 그대로 두고
  `notes` 에 "상위 N개만"이라고 적는다.

### `parties_running` 형식

```json
"parties_running": [
  { "abbr": "CDU/CSU", "name_ko": "기민·기사 연합", "leader_ko": "프리드리히 메르츠", "spectrum_ko": "중도우파", "incumbent": true }
]
```

`spectrum_ko` 는 자유 서술이되 **정치적 판정이 아니라 통용 표기**만.
확신 없으면 키를 생략한다.

---

## 4. 조인 안 되는 14건

`world_by_month` 에는 있는데 `board_tracked_all_events` 에 없는 행들이다.

```
PRT 2026-02-08 포르투갈 대선 결선      THA 2026-02-08 태국 총선·개헌
CHE 2026-03-08 스위스 국민투표         COL 2026-03-08 콜롬비아 총선
HUN 2026-04-12 헝가리 총선(보도)       COL 2026-05-31 콜롬비아 대선 1차
DZA 2026-07-02 알제리 의회             FRA 2026-09    프랑스 상원 간선   ← board_countries 안
RUS 2026-09-18 러 두마 투표 개시  ← board_countries 안
BIH 2026-10-04 보스니아 총·수장        NZL 2026-11-07 뉴질랜드 총선
CPV 2026-11-15 카보베르데 대선         PSE 2026-11-28 팔레스타인 의회
HTI 2026-12-13 아이티 총·대선
```

**두 가지를 먼저 봐야 한다.**

- `FRA` 와 `RUS` 는 이미 `board_countries` 안인데도 이 이벤트만 빠져 있다.
  추적 대상 국가이므로 **이 둘은 (A)로 올리는 게 맞다.**
- `FRA 2026-09` 는 날짜가 **월까지만** 있다(`2026-09`). `(iso3, date)` 조인이
  깨지는 직접 원인이다. 일자가 확정되면 `date` 를 채우고, 미확정이면 그대로 두되
  `date_note` 에 사유를 적는다 — 조인 쪽에서 월 단위 폴백을 따로 처리한다.

둘 중 하나를 고른다.

- **(A)** `board_tracked_all_events` 에 최소 행만 올린다 —
  `id / iso3 / type / label_ko / date / status / sources` 만 있어도 창이 뜬다.
  2·3절 필드는 나중에 채워도 된다.
- **(B)** 올리지 않는다. 화면은 "이 국가는 상세 추적 대상이 아닙니다"로 정직하게 표시한다.

**권장: (A).** 날짜와 출처만 있어도 "무슨 선거인지"는 답할 수 있다.
다만 `board_countries` 에 넣을지는 별개 판단이므로, 넣는다면 `summary.board_countries`
도 같이 갱신한다.

---

## 5. 완료 판정

아래가 전부 참이면 이 작업은 끝이다.

- [ ] `elections_system_v1.json` 이 존재하고 1절 우선순위 1군(USA·JPN·DEU)을 채웠다
- [ ] 그 국가들의 이벤트 행에 `system_id` 가 붙어 실제로 조인된다
- [ ] 직전 선거가 있는 이벤트에 `previous.by_party` 가 있다
- [ ] 모든 신규 행에 `sources` 가 있다
- [ ] `null` / `""` / 의미 없는 `0` 이 한 곳도 없다 (`"없음"` / `"불명"` 또는 키 생략)
- [ ] `world_by_month` 38건 중 조인 성공 건수가 24건보다 늘었다

### 자가 검증 스니펫

```python
import json
d = json.load(open("New for anti/public/data/elections_calendar_master_v1.json"))
idx = {(r.get("iso3"), r.get("date")) for r in d["board_tracked_all_events"]}
rows = [r for m in d["world_by_month"].values() for r in m]
hit = sum(1 for r in rows if (r["iso3"], r["date"]) in idx)
print(f"조인 {hit}/{len(rows)}")          # 현재 24/38

sysd = json.load(open("New for anti/public/data/elections_system_v1.json"))
ids = {s["id"] for s in sysd["systems"]}
bad = [r["id"] for r in d["board_tracked_all_events"]
       if r.get("system_id") not in (None, "불명") and r["system_id"] not in ids]
print("깨진 system_id:", bad)              # 비어 있어야 함
```

---

## 6. 범위 밖 (하지 말 것)

- **선거구 단위 결과 지도.** 독일 299개 선거구 같은 경계 파일은 미국
  (`public/data/congressional_districts/`) 말고는 없다. admin1(주·도) 경계는
  26개국 있으니 주 단위까지가 현재 한계다. 선거구 geometry 수집은 별건으로 다룬다.
- **여론조사.** 이 창은 "이 선거가 어떤 선거인가"를 답하는 곳이지 예측하는 곳이 아니다.
- **UI 코드.** `New for anti/js/elections/**` 와 `style.css` 는 Claude Code 소유다
  (`docs/ops/OWNERS.md`). 데이터만 채운다.

---

## 7. 화면이 이 데이터를 어떻게 쓰는지

참고용. 창은 대략 이렇게 구성된다 — 없는 칸은 접히고, 빈 칸을 만들어 두지 않는다.

```
[선거 이름]                         status 배지
언제      date · first_round_date · runoff_date · date_end
무엇을    contested_ko · chamber · level · district
어떻게    method_ko  →  펼치면 method_detail_ko
          seats_total · districts.count · threshold_ko · rounds · voting_age
누가      parties_running (정당 카드)  /  candidates
직전 결과  previous.by_party (막대 + 표) · turnout_pct · government_formed_ko
결과      winner · result · result_summary   ← status=completed 일 때만
근거      sources · notes · as_of
```
