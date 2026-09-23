# 작업 A — 어떤 선거가 있는가 (Cursor 안내용)

**이 문서는 둘 중 하나다.** 짝이 되는 문서는
`HANDOFF_CURSOR_ELECTION_CONTESTS.md`(작업 B — 누가 나오는가)이고, **다른 대화창에서
따로 진행한다.** 브랜치도 PR도 섞지 말 것.

- **작업 A (이 문서)** — 주요국의 **대선 · 총선 · 지방선거 · 재보궐 · 당권**이 언제
  열리고 무엇을 뽑는가. 달력과 제도.
- **작업 B (짝 문서)** — 그 선거에 어떤 정당·후보가, 어떤 의석 현황에서 맞붙는가

A 가 먼저다. B 의 모든 행은 A 의 이벤트를 참조한다.

**먼저 읽을 것:** 이 저장소에서 반복된 실패는 "수집은 했는데 UI가 안 읽음"이다.
그래서 **필드명을 여기 적힌 그대로** 써야 한다. 공통 규칙(한국어 센티널, 출처 필수,
합산 금지, `id` 규칙)은 `HANDOFF_CURSOR_ELECTION_BRIEF_SCHEMA.md` 1절에 있다.

---

## 0. 지금 상태 (2026-09-18 실측)

### 0-1. 가장 큰 문제 — 모은 일정의 3분의 1만 화면에 있다

화면의 `세계 선거 일정`이 읽는 블록은 **`world_by_month` 하나뿐이다**
(`js/elections/data/selectors.js`). 그런데

| 블록 | 행 수 | 생성 방식 |
|---|---|---|
| `board_tracked_all_events` | **109건** | `build_calendar_master.py` 가 `config/calendars/*.json` 에서 **자동 생성** |
| `party_leadership_and_conventions` | 23건 | 위에서 자동 파생 |
| `world_by_month` | **38건** | **아무도 생성하지 않는다. 수기로 남아 있는 블록이다** |

`build_calendar_master.py` 를 읽어 보면 `board_tracked_all_events` 와
`party_leadership_and_conventions` 만 다시 쓰고 `world_by_month` 는 손대지 않는다.
**그래서 달력을 아무리 채워도 화면에는 안 나타난다.** 이게 이 작업의 1번이다.

### 0-2. 주요국 × 선거 종류 (board_tracked_all_events 실측)

여론조사가 붙을 주요국 여섯 나라다. 괄호 안은 날짜 상태.

| 국가 | 대선 | 총선 | 지방 | 재보궐 | 당권 | **타임라인 노출** |
|---|---|---|---|---|---|---|
| USA | 0 | 1 | 1 | 15 | 1 (전당대회) | **2 / 18** |
| JPN | 0 | 4 | 15 | 3 | 2 | **1 / 24** |
| KOR | 1 (날짜 `"없음"`) | 1 (`2028-04`) | 1 | 2 (1건 `"불명"`) | 3 | **2 / 9** |
| TWN | 0 | 1 (날짜 `"없음"`) | 1 (`"불명"`) | 0 | 2 (1건 `"불명"`) | **0 / 4** |
| GBR | 0 | 1 (날짜 `"없음"`) | 3 | 0 | 3 | **3 / 7** |
| POL | 0 | 0 | 0 | 0 | 0 | **0 / 0** |

읽는 법:

- **POL 은 달력에 아예 없다.** `country_seed.json` 의 board 국가 19개국에도 없다.
- **TWN 은 4건 전부 날짜가 `"불명"` 또는 `"없음"`** 이라 타임라인에 한 줄도 못 뜬다.
- **`"없음"` 이 두 가지 뜻으로 섞여 쓰이고 있다.** 대선·총선 행 중 `date: "없음"` 이
  **15건**이다:

  | 뜻 | 해당 행 | 맞는 표기 |
  |---|---|---|
  | 제도상 경쟁 선거가 없다 | ARE · SAU · IRN · NGA · IDN 등의 `전국 총·대선` | `"없음"` + `notes` 에 사유 — **지금이 맞다** |
  | 올해 회차가 아닐 뿐이다 | KOR·FRA·RUS 대선, JPN·DEU·GBR·TWN·IND·ZAF 총선 | **다음 회차 연월 + `date_note`** — 고쳐야 한다 |

  둘을 같은 글자로 적으면 "한국엔 대통령 선거가 없다"와 "올해는 아니다"가 구분되지
  않는다. 화면은 `"없음"` 을 보고 칸을 지우므로, 후자는 **선거가 사라진 것처럼 보인다.**
- **USA 재보궐 15건, JPN 지방 15건이 화면에 없다.** 수집은 돼 있다.

### 0-3. 제도 파일 (PR #320, 미머지)

`elections_system_v1.json` 28행: USA · JPN · DEU · FRA · RUS · KOR · GBR · IND · BRA.
**TWN · POL 없음.** 이 파일은 #320 이 만들었으니 그 위에서 이어서 한다.

---

## 1. A-1 · `world_by_month` 를 생성물로 바꾼다 (최우선)

수기 블록으로 두는 한 계속 어긋난다. `build_calendar_master.py` 가
`board_tracked_all_events` 에서 파생시키도록 고친다.

파생 규칙:

- **날짜가 `YYYY-MM-DD` 로 확정된 모든 행**을 그 달 키에 넣는다. 종류를 가려 빼지 않는다
  — 재보궐 15건이 많아 보여도, **화면에서 접는 건 UI 가 할 일이다.** 데이터가 화면
  사정을 판단해 누락시키면 되돌릴 방법이 없다.
- `YYYY-MM` 까지만 있는 행은 그 달의 끝에 넣고 `date_note` 를 함께 넘긴다.
- `"불명"` · `"없음"` 인 행은 넣지 않는다. 대신 **왜 안 들어갔는지 목록으로 출력**해서
  수집이 빠진 건지 제도상 없는 건지 매번 보이게 한다.
- 각 행이 지금 타임라인이 쓰는 5개 필드(`date` `iso3` `type` `label_en` `label_ko`)를
  반드시 갖게 한다. 나머지 필드는 같이 넘어와도 된다 — 화면이 무시한다.
- 기존 수기 38건 중 board 에 없는 행이 있으면 **지우지 말고** board 쪽에 올린 뒤
  파생시킨다 (작업 A-3).

결과 검증: 파생 후 `world_by_month` 행 수가 **38 → 90 안팎**으로 늘고, 못 들어간 행
목록에 `"불명"`/`"없음"` 만 남아야 한다.

> UI 쪽은 이쪽에서 맡는다. 한 달에 수십 줄이 뜨면 종류별로 묶고 접는 것은 Claude Code
> 몫이다. 데이터를 줄여서 맞추지 말 것.

## 2. A-2 · 주요국 6개국 × 선거 종류 5종을 확정한다

**미국 · 일본 · 한국 · 대만 · 영국 · 폴란드**, 그리고 **대선 · 총선 · 지방 · 재보궐 ·
당권** — 30칸을 전부 아래 셋 중 하나로 만든다. 빈칸을 남기지 않는다.

1. **확정 일자** — `date: "2026-06-03"`
2. **예정** — `date: "2027-03"` + `date_note: "임기 만료에 따른 통상 시기, 공고 전"`
   (해산·조기선거 가능성이 있으면 그것도 `date_note` 에)
3. **제도상 없음** — `date: "없음"` + `notes` 에 **왜 없는지**
   (예: 의원내각제라 대통령 선거가 없음)

종류별 `type` 어휘는 **이미 쓰이는 것을 그대로 쓴다. 새로 짓지 말 것.**

| 선거 | `type` |
|---|---|
| 대선 | `presidential` |
| 총선 | `general` |
| 지방선거 | `local` |
| 재보궐 | `by_election` |
| 당권 (전당대회·당대표 경선) | `party_leadership` · `party_convention` · `leadership_review` |
| (의장 선출 등) | `speaker_election` |

주의할 점:

- **재보궐은 상시 발생한다.** 전수를 목표로 하지 말고 **앞으로 12개월 안**에 확정된
  건만 올린다. 지나간 건 그대로 두되 `status` 로 구분한다.
- **당권은 국가 단위가 아니라 정당 단위다.** 주요 정당별로 행을 만들고 `label_ko` 에
  정당명을 적는다 (예: `자민당 총재 선거`). 여당/제1야당은 반드시 포함한다.
- **POL 은 처음부터 만든다.** `config/calendars/pol_2026.json` 을 새로 만들고
  `config/country_seed.json` 에 POL 을 추가해야 `build_calendar_master.py` 가 읽는다.
  (seed 에 없으면 파일이 있어도 무시된다 — 스크립트가 seed 를 먼저 본다.)
- **TWN 4건의 `"불명"`/`"없음"` 을 먼저 없앤다.** 지금 대만은 화면에 한 줄도 없다.

**대만 표기 주의.** 국가명·기관명은 공식 명칭 그대로 적고, 정치적 판단이 들어가는
표기를 이쪽에서 정하지 않는다. 판단이 필요한 지점은 `notes` 에 그대로 남긴다.

## 3. A-3 · 이벤트가 "무엇을 뽑는 선거인지" 말하게 한다

날짜만으로는 창이 한 줄밖에 못 쓴다. 각 이벤트 행에 아래를 채운다.
**생성원인 `config/calendars/{iso3}_{year}.json` 을 고친다.**
`elections_calendar_master_v1.json` 을 직접 손대지 않는다(재생성 시 덮어써짐).

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `system_id` | string | ✅ | `elections_system_v1.json` 의 `id`. 이게 있어야 제도 설명이 붙는다 |
| `contested_ko` | string | ✅ | **한 줄.** 무엇을 얼마나 뽑는지. 예: `연방하원 435석 전원 + 상원 33석` / `광역단체장 17곳 + 기초단체장 226곳` / `자민당 총재 1인 (국회의원 + 당원 표)` |
| `level` | string | ✅ | `national` / `subnational` / `party` |
| `chamber` | string | | 해당 원. 단원제·해당 없음이면 `"없음"` |
| `date_end` | string | | 며칠에 걸쳐 치르면 종료일 |
| `first_round_date` / `runoff_date` | string | | 2라운드제 |
| `date_note` | string | | 날짜가 월까지만인 이유, 해산 가능성 |
| `electorate_ko` | string | | **당권 전용.** 누가 투표하는지 (예: `국회의원 295표 + 당원 295표`) |
| `previous` | object | | `{ "date": "...", "by_party": { "LDP": 191, ... }, "turnout_pct": 53.8, "source": "..." }` |
| `government_formed_ko` | string | | 직전 선거 뒤 어떤 정부가 섰는지 한 줄 |

`previous.by_party` 는 **원문 그대로** 넣는다. 정당별 의석을 더해 총계를 만들지 않고,
연립 합계를 따로 만들지 않는다. 그건 화면의 판정이지 수집된 사실이 아니다.

## 4. A-4 · 제도 파일을 주요국 기준으로 메운다

`elections_system_v1.json` 에 **TWN · POL** 을 추가하고, 주요국 6개국의 **선거 종류별**
행이 다 있는지 확인한다 (일본은 중의원·참의원, 한국은 국회·대통령·지방 등).
행 형식은 #320 이 만든 28행과 같고, 필드 정의는
`HANDOFF_CURSOR_ELECTION_BRIEF_SCHEMA.md` 2절에 있다.

당권(`party_leadership`)은 국가 제도가 아니라 당헌이다. 제도 행을 억지로 만들지 말고
이벤트 행의 `electorate_ko` 와 `rules_summary` 로 설명한다.

### 우선순위

1. **미국 · 일본 · 한국 · 대만 · 영국 · 폴란드** — 여섯 나라 30칸
2. `summary.board_countries` 의 나머지 (ARE BRA CHN DEU FRA IDN IND IRN ISR NGA RUS SAU TUR ZAF)
3. 그 밖의 `world_by_month` 국가 — 최소 행만 있어도 된다

**전 세계를 채우려 하지 말 것.** 1군을 끝내고 멈추는 편이, 전부 절반씩 채우는 것보다 낫다.

---

## 5. 완료 판정

- [ ] `world_by_month` 가 `build_calendar_master.py` 의 생성물이다 (수기 유지 아님)
- [ ] 파생 후 타임라인 행 수가 38건보다 **크게** 늘었고, 빠진 행은 `"불명"`/`"없음"` 뿐이며 그 목록이 출력된다
- [ ] 주요국 6개국 × 5종류 30칸이 **확정 일자 / 예정+`date_note` / `"없음"`+사유** 중 하나로 채워졌다
- [ ] POL 이 `country_seed.json` 과 `config/calendars/pol_2026.json` 에 있다
- [ ] TWN 이벤트에 `"불명"`/`"없음"` 날짜가 남아 있지 않다
- [ ] 대선·총선의 `date: "없음"` 15건이 정리됐다 — 제도상 부재만 `"없음"`(+`notes`),
      회차가 아닐 뿐인 행은 다음 회차 연월 + `date_note`
- [ ] 1군 국가 이벤트에 `system_id` · `contested_ko` · `level` 이 전부 있다
- [ ] `elections_system_v1.json` 에 TWN · POL 이 있다
- [ ] 모든 신규·수정 행에 `sources` 가 있다

### 자가 검증 스니펫

```python
import json, collections, datetime
B = "New for anti/public/data/"
d = json.load(open(B + "elections_calendar_master_v1.json", encoding="utf-8"))
bt = d["board_tracked_all_events"]
rows = [r for m in d["world_by_month"].values() for r in m]
print(f"타임라인 {len(rows)}건 / board {len(bt)}건")

# 1) 확정 일자인데 타임라인에 없는 행 = 파생 누락
idx = {(r.get("iso3"), r.get("date")) for r in rows}
dated = [r for r in bt if len(str(r.get("date") or "")) == 10]
missing = [r for r in dated if (r.get("iso3"), r.get("date")) not in idx]
print("파생 누락:", len(missing))
for r in missing[:10]: print("   ", r.get("iso3"), r.get("date"), r.get("label_ko"))

# 2) 주요국 × 선거 종류 매트릭스
MAJOR = ["USA", "JPN", "KOR", "TWN", "GBR", "POL"]
KINDS = {"대선": {"presidential"}, "총선": {"general"}, "지방": {"local"},
         "재보궐": {"by_election"},
         "당권": {"party_leadership", "party_convention", "leadership_review"}}
for iso in MAJOR:
    ev = [r for r in bt if r.get("iso3") == iso]
    cells = []
    for ko, types in KINDS.items():
        hit = [r for r in ev if r.get("type") in types]
        dated_n = sum(1 for r in hit if len(str(r.get("date") or "")) >= 7)
        cells.append(f"{ko} {len(hit)}({dated_n}확정)")
    print(f"{iso}: " + " · ".join(cells))

# 3) 규칙 위반 — 대선/총선에 "없음"(제도상 없음)이 붙어 있는가
bad = [(r["iso3"], r["type"], r.get("label_ko")) for r in bt
       if r.get("type") in {"presidential", "general"} and r.get("date") == "없음"
       and not r.get("notes")]
print("사유 없이 '없음' 인 대선·총선:", len(bad))   # 0 이어야 한다
for x in bad[:10]: print("   ", *x)

# 4) 제도 파일 (PR #320 이 머지되기 전에는 없을 수 있다)
try:
    sysd = json.load(open(B + "elections_system_v1.json", encoding="utf-8"))
except FileNotFoundError:
    print("제도 파일 없음 — PR #320 머지 전이면 정상")
else:
    ids = {s["id"] for s in sysd["systems"]}
    print("제도", len(ids), "행 · 국가", sorted({s["iso3"] for s in sysd["systems"]}))
    print("깨진 system_id:", [r["id"] for r in bt if r.get("system_id") and r["system_id"] not in ids])
```

---

## 6. 범위 밖 (하지 말 것)

- **후보·정당 대진.** 작업 B 다. 여기서는 `previous`(직전 결과)까지만 다룬다.
- **여론조사.** PR #293 과 `HANDOFF_CODEX_USA_MIDTERMS_FORECAST.md` 가 따로 다룬다.
- **UI 코드.** `New for anti/js/elections/**` 와 `style.css` 는 Claude Code 소유다
  (`docs/ops/OWNERS.md`). 타임라인이 길어질 때 묶고 접는 것도 이쪽 몫이다.
- **선거구 경계 파일.** 미국(`public/data/congressional_districts/`) 말고는 없다.
  admin1(주·도) 경계는 26개국 있으니 현재 한계는 주 단위다. 수집은 별건이다.
