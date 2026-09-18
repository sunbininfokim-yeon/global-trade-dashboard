# 작업 B — 누가 나오는가 (Cursor 안내용)

**이 문서는 둘 중 하나다.** 짝이 되는 문서는
`HANDOFF_CURSOR_ELECTION_INVENTORY.md`(작업 A — 어떤 선거가 있는가)이고,
**다른 대화창에서 따로 진행한다.** 브랜치도 PR도 섞지 말 것.

- **작업 A** — 어떤 선거가 언제, 무엇을 뽑는 선거로 열리는가
- **작업 B (이 문서)** — 그 선거에 어떤 정당·후보가, 어떤 의석 현황에서 맞붙는가

B 의 모든 행은 A 의 이벤트를 `event_id` 로 참조한다. A 에 없는 선거의 대진은 만들지 않는다.

**먼저 읽을 것:** 이 저장소에서 반복된 실패는 "수집은 했는데 UI가 안 읽음"이다.
그래서 **필드명을 여기 적힌 그대로** 써야 한다. 공통 규칙(한국어 센티널, 출처 필수,
합산 금지, `id` 규칙)은 `HANDOFF_CURSOR_ELECTION_BRIEF_SCHEMA.md` 1절에 있다.

---

## 0. 지금 상태 (2026-09-18 실측)

**대진 데이터는 사실상 미국뿐이다.**

| 있는 것 | 어디에 |
|---|---|
| 미국 하원 143자리 · 상원 17자리 · 주지사 18자리 본선 대진 | `ui_ready.state_drilldown[].primary_2026.contests` |
| 미국 현재 의석 (하원·상원 정당별, 공석 포함) | `ui_ready.congress.summary` |
| 그 밖의 나라 | **없음.** `board_tracked_all_events` 109건 중 `candidates` 3건 · `parties_running` 7건 |

미국 중간선거 창은 이미 이 데이터로 서 있다(주지사·하원·상원 3열, 주별 대진).
**나머지 나라는 창을 채울 것이 없어 일정 줄이 눌리지도 않는다.** 이 작업이 그걸 채운다.

### 미국도 결국 이 형식으로 온다 — 다만 순서가 있다

미국이 지금 다른 구조인 것은 **화면을 먼저 만들려고 급히 세운 과도기**다. 목표는
모든 나라가 한 형식을 쓰는 것이고, 미국도 예외가 아니다.

순서를 두는 이유는 하나다. **스키마가 아직 미국 하나만 겪어 봤다.** 다당제, 2라운드,
간선, 권역 비례 같은 것들이 이 형식에 들어오면 형식이 한 번은 바뀐다. 그때 미국까지
새 형식에 올라가 있으면 **지금 돌아가는 유일한 화면이 같이 깨진다.**

그래서:

1. **먼저** 미국 외 한 나라를 `status: "complete"` 까지 만든다 (일본 또는 한국 권장).
   그 과정에서 이 문서의 형식에 손볼 곳이 나오면 **형식을 고친다.** 형식이 굳는다.
2. **그다음** 미국을 같은 형식으로 낸다 — `elections_contests/usa-2026-midterms.json`.
   - 기존 미국 파일(`usa_elections_ui_ready_*`, `state_drilldown`)은 **그대로 둔다.**
     지우거나 고치지 않는다. 화면이 아직 그걸 읽고 있다.
   - 값은 **원 출처에서 다시 만든다.** 기존 JSON 을 형식만 바꿔 옮겨 붙이면 그쪽의
     오류까지 같이 복사된다 (예: 지금 NJ 상원 공화당 후보가
     `Justin Michael Ll.m. Murphy` 로 들어가 있다 — 학위 표기가 이름에 섞였다).
   - 다 되면 **두 벌을 대조한 결과를 PR 에 적는다.** 하원 143자리·상원 17자리·주지사
     18자리, 현재 의석 하원 214/218·상원 45/53·주지사 24/26 이 일치하는지.
3. **그러면** 화면을 새 형식으로 옮기고 레거시 읽기를 걷어내는 것은 Claude Code 가 한다.
   두 벌이 공존하는 기간은 그 사이뿐이다.

지금 1단계를 건너뛰고 미국부터 하면, 형식이 바뀔 때마다 미국을 다시 만들어야 한다.

---

## 1. 만들 것 — 이벤트 하나에 파일 하나

**한 파일에 다 몰지 않는다.** 선거는 제각기 갱신 주기가 다르다. 한국 지방선거 후보가
확정될 때마다 영국 데이터까지 다시 받게 만들 이유가 없다.

```
New for anti/public/data/
  elections_contests_index_v1.json          ← 목차 (이것만 항상 읽는다)
  elections_contests/
    jpn-2026-sangiin.json                   ← 이벤트당 한 파일
    kor-2026-local.json
    gbr-2026-holyrood.json
```

### 목차 파일

```json
{
  "schema": "elections_contests_index_v1",
  "as_of": "2026-09-20",
  "events": [
    { "event_id": "jpn-2026-sangiin", "iso3": "JPN", "date": "2026-07-25",
      "path": "elections_contests/jpn-2026-sangiin.json",
      "status": "partial", "as_of": "2026-09-20" }
  ]
}
```

`event_id` 는 작업 A 의 `board_tracked_all_events[].id` 와 **같은 문자열**이어야 한다.
`status` 는 `partial`(수집 중) · `complete`(후보 확정까지 끝) · `pending`(파일만 있고 내용 대기).

---

## 2. 이벤트 파일 형식

```json
{
  "schema": "elections_contest_v1",
  "event_id": "jpn-2026-sangiin",
  "iso3": "JPN",
  "date": "2026-07-25",
  "system_id": "jpn-sangiin",
  "as_of": "2026-09-20",
  "sources": ["https://www.soumu.go.jp/..."],
  "parties": [
    { "abbr": "LDP", "name_ko": "자유민주당", "name_en": "Liberal Democratic Party",
      "color": "#c8102e", "leader_ko": "…", "note_ko": "" }
  ],
  "columns": [
    {
      "key": "sangiin",
      "label_ko": "참의원",
      "current": { "by_party": { "LDP": 101, "CDP": 38 }, "total": 248,
                   "as_of": "2025-07-21", "note_ko": "회파 기준 공개 집계", "vacancies": 0 },
      "contested_ko": "124석 개선 (절반)",
      "seat_note_ko": "비개선 124석은 이번 선거와 무관합니다",
      "districts": [
        { "id": "13", "name_ko": "도쿄도", "group_ko": "선거구", "seats": 6,
          "status": "scheduled",
          "candidates": [
            { "party_abbr": "LDP", "name": "…", "incumbent": true,
              "status": "nominated", "note_ko": "", "source": "https://…" }
          ] }
      ]
    }
  ]
}
```

### 필드

| 필드 | 필수 | 설명 |
|---|---|---|
| `parties[]` | ✅ | 이 선거에 나오는 정당. `abbr` 가 아래 모든 정당 키의 정본이다 |
| `parties[].color` | | 없으면 화면이 회색으로 그린다. **모르면 넣지 말 것** |
| `columns[]` | ✅ | 화면의 열 하나 = 선거 종류/원 하나. 참의원·중의원, 광역단체장·광역의원처럼 성격이 다르면 열을 나눈다 |
| `columns[].key` | ✅ | 영문 소문자 슬러그. 파일 안에서 유일 |
| `current.by_party` | ✅ | **현재(선거 전) 의석.** 키는 `parties[].abbr` |
| `current.total` | ✅ | 원문 총수. **정당별 의석을 더해 만들지 말 것** |
| `current.as_of` | ✅ | 이 의석이 언제 기준인지 |
| `current.vacancies` | | 공석 수. 모르면 키를 뺀다 (0 은 "공석 없음"이라는 주장이다) |
| `contested_ko` | ✅ | 이번에 몇 석을 뽑는지 한 줄 |
| `districts[]` | ✅ | 선거구·지역 단위 행 |
| `districts[].id` | ✅ | 공식 선거구 코드나 번호 |
| `districts[].group_ko` | | 묶음 이름(주·권역·선거구 종류). 행이 수십 개를 넘으면 화면이 이걸로 접는다 |
| `districts[].seats` | ✅ | 그 선거구에서 뽑는 수 (소선거구면 1) |
| `districts[].status` | ✅ | `scheduled`(후보 확정 전) · `nominated`(확정) · `uncontested`(무투표) · `completed` |
| `candidates[]` | ✅ | 빈 배열 허용. **빈 배열 = 아직 확정 안 됨이지 후보가 없다는 뜻이 아니다** |
| `candidates[].status` | ✅ | `nominated` · `presumptive`(유력 보도) · `withdrawn` · `불명` |
| `candidates[].incumbent` | | 현직 여부. 모르면 키를 뺀다 |

### 파일이 커지면 쪼갠다

영국 650, 인도 543 처럼 선거구가 많은 선거는 이벤트 파일 하나가 금방 커진다.
**1MB 를 넘으면** 열 단위로 쪼개고 `districts` 대신 경로를 준다.

```json
{ "key": "commons", "label_ko": "하원", "districts_path": "elections_contests/gbr-2026-commons.districts.json" }
```

쪼갠 파일은 `{ "schema": "elections_contest_districts_v1", "districts": [ … ] }` 하나만 담는다.

---

## 3. 판정하지 않을 것

화면이 이미 지키고 있는 선이다. 데이터도 같은 선을 지킨다.

- **양당 대결로 접지 않는다.** 정당이 여섯이면 여섯을 다 준다. "주요 2당 + 기타"로
  줄이는 것은 화면이 할 일이고, 데이터가 미리 줄이면 되돌릴 수 없다.
- **무소속을 어느 정당·연립에도 더하지 않는다.** `IND` 로 따로 세운다.
- **연립 합계를 만들지 않는다.** 연립 관계는 `parties[].note_ko` 에 적고 숫자는 정당별로 둔다.
- **득표율을 의석으로 환산하지 않는다.**
- **"후보 미정"과 "무투표 당선"을 섞지 않는다.** 전자는 `candidates: []` + `status: "scheduled"`,
  후자는 `status: "uncontested"` 로 명시한다.
- **출처가 어긋나면 하나를 고르지 말고 둘 다 남긴다** (`note_ko` 에 병기).

---

## 4. 우선순위 — 여론조사가 붙는 나라와 아닌 나라

전망(여론조사) 파이프라인은 **주요국에만** 연결한다: **미국 · 일본 · 한국 · 대만 ·
영국 · 폴란드** 등. 나머지 국가에는 붙지 않는다.

그래서 두 경우의 요구가 다르다.

| | 여론조사 연결 (주요국) | 나머지 |
|---|---|---|
| 화면 구성 | 전망 칸 + 현재 의석 + 대진 | **현재 의석 + 대진이 전부** |
| 이 데이터가 비면 | 전망만 뜨고 근거가 없는 화면 | **창이 아예 안 열린다** |

즉 **여론조사가 안 붙는 나라일수록 이 데이터가 화면의 전부다.** 주요국이 아니라고
뒤로 미룰 이유가 없다.

순서:

1. **일본 · 한국 · 대만 · 영국 · 폴란드** — 이 중 한 나라를 `complete` 까지
   끝내 형식을 굳힌다
2. **미국** — 형식이 굳은 뒤 (위 2단계)
3. `summary.board_countries` 의 나머지 중 표시 창 안에 선거가 있는 나라
4. 그 밖

한 나라를 끝내고 다음으로 간다. **다섯 나라를 30%씩 채우지 말 것** — 30% 짜리 창은
열리지 않는 창과 같다.

---

## 5. 완료 판정

- [ ] `elections_contests_index_v1.json` 이 존재하고, 모든 `path` 가 실제 파일로 풀린다
- [ ] 모든 `event_id` 가 `board_tracked_all_events[].id` 에 있다
- [ ] 모든 `current.by_party` 키가 그 파일의 `parties[].abbr` 에 있다
- [ ] `current.total` 이 `by_party` 합계와 다르면 `note_ko` 에 사유가 있다 (다른 것 자체는 정상)
- [ ] 미국 외 국가 중 최소 한 나라가 `status: "complete"` 다 (형식을 굳히는 단계)
- [ ] 미국을 낸 경우, 기존 구조와 대조한 수치가 PR 본문에 있다
- [ ] 모든 파일에 `sources` 가 있다
- [ ] `null` / `""` / 의미 없는 `0` 이 한 곳도 없다

### 자가 검증 스니펫

```python
import json, pathlib
B = pathlib.Path("New for anti/public/data")
idx = json.load(open(B / "elections_contests_index_v1.json", encoding="utf-8"))
cal = json.load(open(B / "elections_calendar_master_v1.json", encoding="utf-8"))
event_ids = {r.get("id") for r in cal["board_tracked_all_events"]}

for row in idx["events"]:
    p = B / row["path"]
    assert p.exists(), f"경로 없음: {row['path']}"
    assert row["event_id"] in event_ids, f"달력에 없는 이벤트: {row['event_id']}"
    d = json.load(open(p, encoding="utf-8"))
    abbrs = {x["abbr"] for x in d["parties"]}
    for col in d["columns"]:
        cur = col["current"]
        bad = set(cur["by_party"]) - abbrs
        assert not bad, f"{row['event_id']}/{col['key']}: parties 에 없는 정당 키 {bad}"
        summed = sum(v for v in cur["by_party"].values() if isinstance(v, int))
        if summed != cur["total"] and not cur.get("note_ko"):
            print(f"  확인 필요 {row['event_id']}/{col['key']}: 합계 {summed} ≠ total {cur['total']} (사유 미기재)")
        districts = col.get("districts")
        if districts is None:
            assert (B / col["districts_path"]).exists(), col.get("districts_path")
            districts = json.load(open(B / col["districts_path"], encoding="utf-8"))["districts"]
        for dist in districts:
            for c in dist["candidates"]:
                assert c["party_abbr"] in abbrs or c["party_abbr"] == "IND", (dist["id"], c)
            if not dist["candidates"]:
                assert dist["status"] == "scheduled", f"{dist['id']}: 후보 0인데 status 가 scheduled 가 아니다"
    print(f"{row['event_id']}: 열 {len(d['columns'])} · 정당 {len(abbrs)} · {row['status']}")
```

---

## 6. 범위 밖 (하지 말 것)

- **기존 미국 파일 수정.** 미국을 새 형식으로 내는 것은 위 2단계에서 하되,
  `usa_elections_ui_ready_*` 와 `state_drilldown` 은 건드리지 않는다. 화면이 아직
  그걸 읽는다.
- **선거 일정·제도.** 작업 A 다. 여기서는 이미 있는 이벤트를 참조만 한다.
- **여론조사·예측·승률.** PR #293 과 별도 계약이 있다. 이 파일에 `win_prob` 같은
  추정치를 넣지 않는다. **현재 의석과 대진은 확정된 사실만 담는 자리다.**
- **UI 코드.** `New for anti/js/elections/**` 와 `style.css` 는 Claude Code 소유다.
  이 형식을 읽는 일반 브리핑 화면은 이쪽에서 만든다.
