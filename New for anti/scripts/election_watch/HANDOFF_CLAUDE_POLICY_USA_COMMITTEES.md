# HANDOFF → Claude — 정책-미국 상임위 화면

**날짜:** 2026-09-15  
**소유:** 데이터·조인 = Cursor (`scripts/election_watch/**`, `data/policy/**`) · UI = Claude · `.github/workflows/**` = Claude  
**요청:** 선빈. 정책-미국 각 상임위 카드가 위원장·간사·공식 소관 부처·공식 URL을 바로 읽게 할 것. `app.js` 하드코딩 금지.

Cursor `cursor/*` 브랜치는 `ownership_guard.yml` 때문에 `.github/workflows/*`를 넣으면 PR이 실패한다. 아래 YAML을 **Claude 브랜치에서 루트로 복사**하면 분기(1분기는 월 1회) 잡이 돈다.

## 정책-미국이 읽는 JSON 경로

브라우저 fetch 정본은 선거 보드 하나다. `config/extracted/**` 는 읽지 않는다.

파일: `/public/data/elections_board_v1.json`

```js
const usa = byIso3.get('USA')
const cards = usa.ui_ready.congress.standing_committee_cards
```

매니페스트 게이트: `countries.USA.screens.legislature_detail`

| 화면 요소 | 경로 | 비고 |
|---|---|---|
| 상임위 목록 | `cards.standing[]` 또는 `cards.house` / `cards.senate` | 119대 하원 20 + 상원 16. 배열을 `app.js`에 다시 적지 말 것 |
| 위원회 id | `card.committee_id` | `119-house-hsag00` 형식. Congress.gov system code |
| 위원장 | `card.chair` | `role_ko` = 위원장 |
| 간사 | `card.ranking_member` | ranking member. `role_ko` = 간사 |
| 소관 부처 | `card.agencies[]` | **비어 있으면 비워 둔다.** Ways and Means↔Treasury 같은 추정을 UI가 채우면 안 된다 |
| 상임위 홈 | `card.committee_url` | 하원 = Clerk `Committees/{comcode}`, 상원 = congress.gov system code |
| 의원실 | `card.chair.member_office_url` 등 | 하원 = `clerk.house.gov/members/{bioguide}`. 상원 = bioguide (lastname.senate.gov 발명 금지) |
| URL 템플릿 | `cards.url_templates` | 호스트를 UI에 하드코딩하지 말고 이 객체를 쓴다 |
| 전체 명단(필요 시) | `usa.ui_ready.congress.committees.{house,senate}.standing_committees[].members` | 정책-미국 상임위 **카드**에는 쓰지 말 것. 이미 조인된 cards를 쓴다 |

`url_templates` 정본:

- `house_member_office`: `https://clerk.house.gov/members/{bioguide}` (HTTP 200 확인)
- `member_bioguide`: `https://bioguide.congress.gov/search/bio/{bioguide}`
- `house_committee`: `https://clerk.house.gov/Committees/{clerk_code}` (HTTP 200 확인)
- `congress_committee`: `https://www.congress.gov/committee/{system_code}`

`agriculture.house.gov`, `armed-services.senate.gov`, `walberg.house.gov` 같은 이름 슬러그는 Clerk/CVC에 없어서 **만들지 않았다.** 화면에서도 조립하지 말 것.

## 하지 말 것

- `app.js` / `CLIMATE_COUNTRIES` 식 상임위 목록 하드코딩
- `committees.members[]`에서 chair/ranking/agency를 클라이언트가 다시 조인
- 빈 `agencies[]`를 키워드·법안 수로 채우기
- lastname 기반 의원 홈페이지 URL 발명

## 파이프라인 (Cursor가 돌림)

원천은 PR #290과 같다. 공식 House Clerk XML + Senate CVC + Rule X/XXV 부처명 행만.

```bash
# repo root
node scripts/fetch-committee-membership-rosters.js
node scripts/build-committee-memberships.js
node scripts/lib/committee-membership-source.test.js
node scripts/lib/committee-agency-jurisdiction-source.test.js

# election_watch
cd "New for anti/scripts/election_watch"
python3 -m election_watch.extract_usa_committees
python3 -m election_watch.usa_committee_cards
python3 -m unittest tests.test_usa_committee_cards -v
python3 build_board.py --no-betting --print-stats
python3 build_ui_manifest.py
```

한 줄 래퍼:

```bash
bash "New for anti/scripts/election_watch/ci/run_usa_committees_quarterly.sh"
```

Senate CVC(`https://www.senate.gov/legislative/LIS_MEMBER/cvc_member_data.xml`)가 403이면 브라우저로 XML을 `.cache/official-rosters/cvc_member_data.xml`에 저장한 뒤 fetch 스크립트를 다시 실행한다. `raw/`·`.cache/`·`.venv/`·`.verify_live/` 는 커밋하지 않는다.

## 할 일 (Claude) — GitHub Actions 복사

1. `New for anti/scripts/election_watch/ci/elections_committees_quarterly.yml` 내용을  
   **`.github/workflows/elections_committees_quarterly.yml`** 로 그대로 복사 (내용 변경 없이).
2. `main`에 merge. cron: `0 10 1 1,2,3,4,7,10 *` (1분기 매월 1일 + 나머지 분기 시작월 1일, 10:00 UTC) + `workflow_dispatch`.
3. 정책-미국 상임위 화면은 위 JSON 경로만 읽는다. UI 국가 목록을 `app.js`에 하드코딩하지 말 것.

기존 계약(`docs/us-legislator-and-committee-data.md`): 상임위는 **분기 1회**, **1분기(1–3월)는 월 1회**.

## Cursor vs Claude

| 누가 | 무엇을 |
|---|---|
| Cursor | Clerk/CVC extract, `committee-memberships.json` 재생성, Rule X/XXV 부처 행 유지, `standing_committee_cards` 조인, 테스트, `ci/*.yml` 초안, 로컬에서 래퍼 스크립트 실행 |
| Claude | YAML을 `.github/workflows/`로 복사, 정책-미국/선거 UI가 `standing_committee_cards`를 읽게 연결. `app.js`에 위원회를 적지 말 것 |

Cursor Automations / IDE `/loop`는 채팅이 열려 있어야 해서 월·분기 cron을 대체하지 못한다. 스케줄의 정본은 Claude가 복사하는 GitHub Actions다. Cursor는 같은 명령을 로컬에서 재실행할 수 있다.

## 커밋되는 파일 (잡·로컬 갱신)

- `data/policy/committee-memberships.json`
- `scripts/election_watch/config/extracted/usa_committees.json`
- `scripts/election_watch/config/extracted/usa_committee_cards.json`
- `public/data/elections_board_v1.json`
- `public/data/elections_ui_manifest_v1.json`

`committee-agency-jurisdictions.json`은 규칙 조항이 부처 이름을 새로 적지 않는 한 자동으로 늘리지 않는다. 2026-09-15 Senate Rule XXV 원문 확인: 번호 관할 목록이 부처 이름을 적은 것은 Armed Services↔Department of Defense 뿐이다. HSGAC↔DHS는 기존 S.Res. 445 편찬 행을 유지한다.
