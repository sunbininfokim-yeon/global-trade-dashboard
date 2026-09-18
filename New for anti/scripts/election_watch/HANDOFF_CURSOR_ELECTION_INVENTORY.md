# 작업 A — 어떤 선거가 있는가 (Cursor 안내용)

**이 문서는 둘 중 하나다.** 짝이 되는 문서는
`HANDOFF_CURSOR_ELECTION_CONTESTS.md`(작업 B — 누가 나오는가)이고, **다른 대화창에서
따로 진행한다.** 브랜치도 PR도 섞지 말 것.

- **작업 A (이 문서)** — 어떤 선거가 언제, 무엇을 뽑는 선거로 열리는가. 달력과 제도.
- **작업 B (짝 문서)** — 그 선거에 어떤 정당·후보가, 어떤 의석 현황에서 맞붙는가.

A 가 먼저다. B 의 모든 행은 A 의 이벤트를 참조한다.

**먼저 읽을 것:** 이 저장소에서 반복된 실패는 "수집은 했는데 UI가 안 읽음"이다.
그래서 **필드명을 여기 적힌 그대로** 써야 한다. 뜻이 같아도 이름이 다르면 안 읽힌다.
공통 규칙(한국어 센티널, 출처 필수, 합산 금지, `id` 규칙)은
`HANDOFF_CURSOR_ELECTION_BRIEF_SCHEMA.md` 1절에 있다. **그 규칙이 그대로 적용된다.**

---

## 0. 지금 상태 (2026-09-18 실측)

| 블록 | main | PR #320 (미머지) |
|---|---|---|
| `world_by_month` (타임라인이 읽는 유일한 블록) | 38건 | 38건 |
| `board_tracked_all_events` | 108건 | 109건 |
| 둘의 `(iso3, date)` 조인 | **24/38** | **26/38** |
| `system_id` 붙은 이벤트 | 0 | 63 |
| `previous` (직전 결과) 있는 이벤트 | 0 | 17 |
| `elections_system_v1.json` 제도 행 | 없음 | 28 |

PR #320 이 제도 파일과 조인을 만들어 놨다. **그 위에서 이어서 한다. 다시 만들지 말 것.**
#320 이 채운 제도 28행의 국가: USA · JPN · DEU · FRA · RUS · KOR · GBR · IND · BRA.

### 화면이 지금 이 데이터를 어떻게 쓰는가

좌측 `세계 선거 일정`의 한 줄을 누르면 개괄 창이 뜬다. **지금 열리는 줄은 딱 하나,
미국 중간선거뿐이다.** 나머지 37줄은 눌러도 아무 일이 없다 — 창을 채울 데이터가
없어서 아예 버튼으로 만들지 않는다. 이 작업이 그 37줄을 열리게 만든다.

---

## 1. A-1 · 조인 안 되는 12건을 없앤다

`world_by_month` 는 필드 5개(`date / iso3 / type / label_en / label_ko`)뿐이라
그 자체로는 창을 채울 수 없다. 두꺼운 쪽(`board_tracked_all_events`)에 같은
`(iso3, date)` 행이 있어야 한다.

PR #320 기준 26/38 이 붙는다. **남은 12건을 붙인다.**

- 생성원인 `config/calendars/{iso3}_2026.json` 을 고친다.
  `elections_calendar_master_v1.json` 을 직접 손대지 않는다(재생성 시 덮어써짐).
- 최소 행이면 충분하다: `id / iso3 / type / label_ko / date / status / sources`.
- 날짜가 월까지만 있는 행(예: `2026-09`)은 조인이 깨지는 직접 원인이다. 일자가
  확정됐으면 채우고, 미확정이면 `date_note` 에 사유를 적는다. **날짜를 지어내지 말 것.**
- 정말 추적 대상이 아닌 국가는 올리지 않아도 된다. 대신 그 판단을 `notes` 에 남긴다.

## 2. A-2 · 여론조사가 붙을 국가가 달력에 없다

전망(여론조사) 파이프라인은 **주요국에만** 연결한다: **미국 · 일본 · 한국 · 대만 ·
영국 · 폴란드** 등. 나머지 국가는 전망 칸 없이 "어떤 선거이고 누가 나오는가"만으로
화면이 선다.

그런데 지금 `world_by_month` 21개국에 **대만(TWN)과 폴란드(POL)가 아예 없다.**

해야 할 일:

1. TWN · POL 의 현재 선거 주기를 확인한다. 표시 창(앞으로 12~18개월) 안에 전국
   단위 선거가 있으면 이벤트를 올리고, 없으면 **다음 선거를 `status` 와 함께 올린다**
   — "없음"이 아니라 "언제"가 답이다.
2. 두 나라의 제도 행을 `elections_system_v1.json` 에 추가한다 (형식은 #320 이 만든
   28행과 동일, 필드 정의는 `HANDOFF_CURSOR_ELECTION_BRIEF_SCHEMA.md` 2절).
3. 주요국 6개국의 제도 행이 **선거 종류별로** 다 있는지 확인한다. 예: 일본은 중의원·
   참의원 둘 다, 한국은 국회·대통령·지방 셋 다. 빠진 원이 있으면 채운다.

**대만 표기 주의.** 국가명·기관명은 공식 명칭 그대로 적고, 정치적 판단이 들어가는
표기를 이쪽에서 정하지 않는다. 판단이 필요한 지점은 `notes` 에 그대로 남긴다.

## 3. A-3 · 이벤트가 "무엇을 뽑는 선거인지" 말하게 한다

조인이 되는 것만으로는 창이 한 줄밖에 못 쓴다. 각 이벤트 행에 아래를 채운다.
**이미 있는 필드는 손대지 않는다. 없는 것만 더한다.**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `system_id` | string | ✅ | `elections_system_v1.json` 의 `id`. 이게 있어야 제도 설명이 붙는다 |
| `contested_ko` | string | ✅ | **한 줄.** 무엇을 얼마나 뽑는지. 예: `연방하원 630석 전원` / `상원 절반 (시리즈 1)` / `광역단체장 17곳 + 기초단체장 226곳` |
| `level` | string | ✅ | `national` / `subnational` / `party` |
| `chamber` | string | | 해당 원. 단원제·해당 없음이면 `"없음"` |
| `date_end` | string | | 며칠에 걸쳐 치르면 종료일 |
| `first_round_date` / `runoff_date` | string | | 2라운드제 |
| `date_note` | string | | 날짜가 월까지만인 이유, 해산 가능성 등 |
| `previous` | object | | `{ "date": "...", "by_party": { "CDU": 197, ... }, "turnout_pct": 76.2, "source": "..." }` — 직전 같은 선거 결과 |
| `government_formed_ko` | string | | 직전 선거 뒤 어떤 정부가 섰는지 한 줄 |
| `market_significance_invest_lens` | string | | 이미 쓰이는 필드. 있으면 유지 |

`previous.by_party` 는 **원문 그대로** 넣는다. 정당별 의석을 더해 총계를 만들지 않고,
연립 합계를 따로 만들지 않는다. 그건 화면의 판정이지 수집된 사실이 아니다.

### 우선순위

1. **미국 · 일본 · 한국 · 대만 · 영국 · 폴란드** — 전망 칸이 붙을 나라다. 여기는
   제도·일정이 비어 있으면 전망만 뜨고 설명이 없는 화면이 된다.
2. `summary.board_countries` 의 나머지
3. 그 밖의 `world_by_month` 국가 — 최소 행만 있어도 된다

**전 세계를 채우려 하지 말 것.** 1군을 끝내고 멈추는 편이, 전부 절반씩 채우는 것보다 낫다.

---

## 4. 완료 판정

- [ ] `world_by_month` 38건 중 조인 성공이 **38/38**, 또는 못 붙인 행마다 `notes` 에 사유
- [ ] TWN · POL 이 달력과 제도 파일에 모두 있다
- [ ] 주요국 6개국의 제도 행이 선거 종류별로 존재한다
- [ ] 1군 국가 이벤트에 `system_id` · `contested_ko` · `level` 이 전부 있다
- [ ] 모든 신규·수정 행에 `sources` 가 있다
- [ ] `null` / `""` / 의미 없는 `0` 이 한 곳도 없다 (`"없음"` / `"불명"` 또는 키 생략)

### 자가 검증 스니펫

```python
import json
d = json.load(open("New for anti/public/data/elections_calendar_master_v1.json", encoding="utf-8"))
bt = d["board_tracked_all_events"]
idx = {(r.get("iso3"), r.get("date")): r for r in bt}
rows = [r for m in d["world_by_month"].values() for r in m]

miss = [(r["iso3"], r["date"], r.get("label_ko")) for r in rows if (r["iso3"], r["date"]) not in idx]
print(f"조인 {len(rows)-len(miss)}/{len(rows)} · 못 붙은 행:")
for m in miss: print("  ", *m)

sysd = json.load(open("New for anti/public/data/elections_system_v1.json", encoding="utf-8"))
ids = {s["id"] for s in sysd["systems"]}
print("제도 행", len(ids), "· 국가", sorted({s["iso3"] for s in sysd["systems"]}))
bad = [r["id"] for r in bt if r.get("system_id") and r["system_id"] not in ids]
print("깨진 system_id:", bad)                      # 비어 있어야 함

MAJOR = {"USA", "JPN", "KOR", "TWN", "GBR", "POL"}
for iso in sorted(MAJOR):
    ev = [r for r in rows if r["iso3"] == iso]
    sysrows = [s for s in sysd["systems"] if s["iso3"] == iso]
    full = [r for r in ev if idx.get((r["iso3"], r["date"]), {}).get("contested_ko")]
    print(f"{iso}: 일정 {len(ev)}건 (contested_ko {len(full)}건) · 제도 {len(sysrows)}행")
```

---

## 5. 범위 밖 (하지 말 것)

- **후보·정당 대진.** 작업 B 다. 이 문서에서는 `previous`(직전 결과)까지만 다룬다.
- **여론조사.** PR #293 이 따로 한다. 이 창은 "어떤 선거인가"를 답하는 곳이다.
- **UI 코드.** `New for anti/js/elections/**` 와 `style.css` 는 Claude Code 소유다
  (`docs/ops/OWNERS.md`). 데이터만 채운다.
- **선거구 경계 파일.** 미국(`public/data/congressional_districts/`) 말고는 없다.
  admin1(주·도) 경계는 26개국 있으니 현재 한계는 주 단위다. 수집은 별건이다.
