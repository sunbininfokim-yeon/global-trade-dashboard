# 미국 중간선거 전망 — 여론조사 데이터 계약 (Codex 안내용)

화면은 이미 서 있다. 주지사·하원·상원 세 열의 **전망 칸이 비어 있고**, 지금은
"여론조사 연동 예정"이라고만 적혀 있다. 이 문서는 그 칸을 채울 파일 하나의 계약이다.

**먼저 읽을 것:** 이 저장소에서 반복된 실패는 "수집은 했는데 UI가 안 읽음"이다
(`race_progress`, 슈퍼팩, 의회 공석 컨텍스트 모두 발행 후 한동안 화면에 없었다).
그래서 **필드명을 여기 적힌 그대로** 써야 한다. 뜻이 같아도 이름이 다르면 안 읽힌다.
읽는 쪽 코드는 이미 머지돼 있으니, 아래 이름과 다르면 화면은 조용히 빈 칸으로 남는다.

읽는 코드 (고치지 말 것 — Claude Code 소유):

| 파일 | 하는 일 |
|---|---|
| `New for anti/js/elections/data/forecast-service.js` | 이 파일을 `no-store` 로 읽고, `refresh_seconds` 만큼 다시 읽는다 |
| `New for anti/js/elections/briefs/forecast-panel.js` | 읽은 값을 전망 칸 3개에 꽂는다 |

---

## 0. 만들 것

**파일 하나.** `New for anti/public/data/usa_midterms_forecast_v1.json`

**다른 파일을 건드리지 않는다.** 특히 의석·대진 데이터
(`usa_elections_ui_ready_*`, `state_drilldown`)에 전망을 섞어 넣지 말 것.
둘을 갈라 둔 이유가 있다:

- 현재 의석과 본선 대진은 **확정된 사실**이고 선거일까지 거의 안 바뀐다.
- 전망은 **추정**이고 여론조사가 들어올 때마다 바뀐다.

한 파일에 섞으면 여론조사 한 번 갱신할 때마다 수백 KB짜리 의석 데이터를 다시
받아야 하고, 캐시 정책도 하나로 묶인다. 그래서 전망만 `no-store` 로 읽는다.
**섞는 순간 화면이 느려지고, 확정 수치와 추정 수치의 경계가 지워진다.**

---

## 1. 파일 형식

```json
{
  "schema": "usa_midterms_forecast_v1",
  "as_of": "2026-09-18",
  "method_ko": "각 주 공개 여론조사 가중 평균 (표본 300 이상, 최근 21일)",
  "source_ko": "RealClearPolitics · 538 · 각 조사기관 공개 자료",
  "refresh_seconds": 3600,
  "sources": ["https://...", "https://..."],
  "chambers": {
    "house":    { "lead_abbr": "DEM", "seats": { "DEM": 219, "GOP": 216 }, "win_prob": { "DEM": 0.62, "GOP": 0.38 }, "margin_note_ko": "경합 21곳이 3%p 이내" },
    "senate":   { "lead_abbr": "GOP", "seats": { "DEM": 47, "GOP": 53 }, "win_prob": { "DEM": 0.28, "GOP": 0.72 }, "margin_note_ko": "개선 33석 중 경합 6석" },
    "governor": { "lead_abbr": "없음", "margin_note_ko": "36개 주 중 경합 9곳 — 우세 판정 보류" }
  }
}
```

### 최상위

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `schema` | string | ✅ | 고정값 `usa_midterms_forecast_v1` |
| `as_of` | string | ✅ | `YYYY-MM-DD`. 전망 칸과 바닥 줄에 그대로 찍힌다 |
| `method_ko` | string | ✅ | **한 줄.** 어떻게 계산했는지. 화면 바닥에 나간다 |
| `source_ko` | string | ✅ | 한 줄. 어느 조사를 썼는지 |
| `refresh_seconds` | number | | 재조회 주기(초). **30 미만이면 무시하고 한 번만 읽는다.** 없으면 다시 읽지 않는다 |
| `sources` | array | ✅ | URL 목록. 화면엔 안 나가지만 검증에 쓴다 |
| `chambers` | object | ✅ | 아래 |

### `chambers` — 키가 열쇠다

**키는 정확히 셋, 이 이름 그대로다.** 화면의 세 열이 이 키로 자기 칸을 찾는다
(`briefs/usa-midterms.js` 의 `column.key`).

```
house      하원
senate     상원
governor   주지사     ← "governors" 아님. "gov" 아님. 단수 governor.
```

셋을 다 채울 필요는 없다. **없는 키는 그 열만 "여론조사 연동 예정"으로 남는다.**
하원만 먼저 와도 하원 칸만 살아난다 — 나머지를 빈 값으로 채우지 말 것.

### `chambers.*` 행 형식

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `lead_abbr` | string | ✅ | `"DEM"` / `"GOP"` / `"IND"` / `"없음"`. **접전이면 `"없음"`** |
| `seats` | object | | `{ "DEM": 219, "GOP": 216 }` — 예상 의석 |
| `win_prob` | object | | `{ "DEM": 0.62, "GOP": 0.38 }` — **0~1 소수.** 62 가 아니라 0.62 |
| `margin_note_ko` | string | | 한 줄. 접전 범위·오차·전제 |

**`lead_abbr` 만 필수다.** 의석·확률 없이 "누가 앞선다"만 와도 칸은 선다.
반대로 `lead_abbr` 없이 `seats` 만 오면 화면은 "접전 · 우세 판정 보류"로 읽는다 —
의석 숫자에서 우세를 **역산하지 않는다.** 누가 앞서는지는 수집 쪽 판정이다.

정당 코드는 `D` / `R` 로 보내도 `DEM` / `GOP` 로 정규화된다
(`data/usa-midterms-model.js` 의 `normalizeParty`). 다만 **새 파일은 `DEM` / `GOP`
로 쓴다.** 기존 `state_drilldown` 이 `D` / `R` 인 것은 과거 수집 형식이다.

---

## 2. 지켜야 할 규칙

### 2-1. null 대신 한국어 센티널

기존 `null_policy` 그대로다.

- `"없음"` — 판정하지 않음 / 해당 없음 (접전이라 우세를 못 고르는 경우가 여기)
- `"불명"` — 있는데 아직 확인 못 함
- `null` / `""` / `0` **금지.** 특히 `win_prob: 0` 은 "승률 0%"라는 주장이 된다.
  모르면 **키를 아예 빼라.** 빠진 키는 그 줄이 안 그려질 뿐이다.

### 2-2. 접전을 한쪽으로 몰지 않는다

0.51 대 0.49 를 `lead_abbr: "DEM"` 으로 적으면 화면엔 "민주당 우세"라고 단정적으로
찍힌다. 유효 차이가 오차범위 안이면 `"없음"` 을 쓰고 `margin_note_ko` 에 그렇다고
적는다. 화면은 그 경우 회색으로 "접전 · 우세 판정 보류"를 낸다.

### 2-3. 무소속을 코커스에 합산하지 않는다

현재 상원 무소속 2인을 민주 쪽에 더하면 45가 47이 된다. **화면은 안 더한다.**
전망에서도 더하지 말 것. 코커스 가정이 필요하면 `seats` 에 `IND` 키를 따로 두고
`margin_note_ko` 에 "무소속 2인 민주 코커스 가정" 처럼 적는다.

### 2-4. 출처 없는 숫자는 받지 않는다

`sources` 없이는 머지하지 않는다. 자체 모델이면 `method_ko` 에 그렇다고 적고
산출 스크립트 경로를 `sources` 에 넣는다.

### 2-5. 한 번 뜬 숫자는 출처 없이 남지 않는다

파일이 사라지거나 깨지면 화면은 **"여론조사 연동 예정"으로 되돌아간다.** 의도된
동작이다. 갱신이 끊겼는데 옛 숫자가 그대로 걸려 있는 것보다 낫다. 그러니
**갱신을 못 할 바엔 파일을 지우는 것이 맞다** — 낡은 `as_of` 를 그대로 두지 말 것.

---

## 3. 이미 있는 것 — PR #293 을 먼저 볼 것

**여론조사 원자료 수집은 이미 있다.** PR #293 (`codex/us-election-polls`, 아직 draft)
이 `usa_election_polls_index_v1.json` → 전국 → 주 → 선거 순으로 관측값을 발행한다.
계약은 `HANDOFF_CLAUDE_ELECTION_POLLS.md` 에 있다. **새로 수집을 짜지 말고 그 위에 얹어라.**

다만 **그 파일들만으로는 이 전망 칸을 채울 수 없다.** 그쪽이 의도적으로 안 내는 것이 있다:

| #293 이 내는 것 | 이 화면이 필요한 것 |
|---|---|
| 선거(race) 단위 관측값 22슬롯 · 실제 자료는 8건 | 원(chamber) 단위 우세 판정 3건 |
| `poll_average_pct` = **항상 null** | 평균 또는 그에 준하는 요약 |
| `win_probability` = **항상 null** (UI 임의 계산 금지) | `win_prob` 또는 최소한 `lead_abbr` |

즉 **빠진 것은 수집이 아니라 집계 모델이다.** 개별 조사에서 하원 435석의 우세를
끌어내는 일은 가정이 필요하고, #293 은 그 가정을 데이터 쪽에서 세우지 않겠다고
명시했다. 화면도 마찬가지로 계산하지 않는다 — `lead_abbr` 없이 `seats` 만 오면
"접전 · 우세 판정 보류"로 떨어진다.

그래서 이 파일을 만드는 일은 **모델을 하나 세우고 그 가정을 `method_ko` 에 적는
일**이다. 8건 관측으로 전국 판세를 말할 수 없다면 그렇게 적고, 채울 수 있는 방부터
채워라. **세 방을 다 채우려고 없는 근거를 만들지 말 것** — 빈 칸은 "연동 예정"으로
정직하게 남는다.

순서 권장:
1. #293 을 먼저 머지한다 (지금 draft 상태다).
2. 관측이 있는 주지사 3건(NY·WI·NV)처럼 근거가 실제로 있는 범위를 확인한다.
3. 집계 규칙을 정하고 `method_ko` 한 줄로 적을 수 있는지 본다. 못 적으면 그 방은 비워 둔다.
4. `usa_midterms_forecast_v1.json` 을 낸다.

---

## 4. 파이프라인 (선택, 그러나 권장)

수기로 한 번 올리는 것도 화면은 받는다. 다만 `refresh_seconds` 를 선언했으면
그 주기로 갱신되는 것이 맞다.

- 산출 스크립트: `New for anti/scripts/election_watch/build_usa_midterms_forecast.py`
  — #293 의 `build_election_polls.py` 출력(선거 단위 관측)을 입력으로 받는다.
- 워크플로: `.github/workflows/usa_midterms_forecast.yml`

**워크플로 파일은 Claude Code 소유다** (`docs/ops/OWNERS.md`). 필요하면 스크립트만
올리고 워크플로는 요청해라. #293 이 남긴 `ops/us_election_polls_refresh.yml.example`
설치도 같은 이유로 이쪽 몫이다 — 그 PR 이 머지되면 함께 올린다. 봇 커밋은 배포를 트리거하지 않으므로
(`deploy.yml` 주석 참조) 데이터만 갱신되고 화면은 그대로다 — 그래도 된다.
이 파일은 런타임에 `no-store` 로 읽히므로 **재배포 없이 반영된다.**

---

## 5. 완료 판정

- [ ] `New for anti/public/data/usa_midterms_forecast_v1.json` 이 존재한다
- [ ] `chambers` 키가 `house` / `senate` / `governor` 중에서만 나온다
- [ ] 채운 모든 방(chamber)에 `lead_abbr` 이 있다
- [ ] `win_prob` 값이 전부 0~1 이다 (62 같은 값이 없다)
- [ ] `null` / `""` / 의미 없는 `0` 이 한 곳도 없다
- [ ] `sources` 가 비어 있지 않다
- [ ] 다른 데이터 파일에 전망 필드를 넣지 않았다

### 자가 검증 스니펫

```python
import json, datetime
p = "New for anti/public/data/usa_midterms_forecast_v1.json"
d = json.load(open(p, encoding="utf-8"))

assert d["schema"] == "usa_midterms_forecast_v1"
assert set(d["chambers"]) <= {"house", "senate", "governor"}, set(d["chambers"])
for key, ch in d["chambers"].items():
    assert "lead_abbr" in ch, key
    assert ch["lead_abbr"] in {"DEM", "GOP", "IND", "없음"}, (key, ch["lead_abbr"])
    for party, prob in (ch.get("win_prob") or {}).items():
        assert 0 <= prob <= 1, (key, party, prob)      # 62 가 아니라 0.62
    for party, seats in (ch.get("seats") or {}).items():
        assert isinstance(seats, int) and seats > 0, (key, party, seats)
assert d.get("sources"), "출처 없음"
days = (datetime.date.today() - datetime.date.fromisoformat(d["as_of"])).days
print(f"방 {len(d['chambers'])}개 · as_of {d['as_of']} ({days}일 전)")
```

화면 확인: 대시보드 좌측 `세계 선거 일정` → 2026-11 → `미국 중간선거` 클릭 →
세 열 위쪽 `전망` 칸. 파일을 바꾸고 새로고침하면 그 칸만 바뀐다 (펼쳐 둔 주는
접히지 않는다 — 슬롯만 갈아끼우기 때문이다).

---

## 6. 범위 밖 (하지 말 것)

- **UI 코드.** `New for anti/js/elections/**` 와 `style.css` 는 Claude Code 소유다.
- **주별·선거구별 전망.** 화면에 꽂을 자리가 아직 없다. 자리 없는 데이터를 올리면
  이 저장소가 반복해 온 그 실패가 한 번 더 난다. 필요하면 **슬롯부터 요청해라** —
  화면 쪽 칸과 같은 PR 에서 붙인다.
- **다른 나라 전망.** 이 계약은 미국 중간선거 하나다. 일본·독일은 각자 파일과
  각자 브리핑 모듈을 갖는다 (`js/elections/briefs/` 에 나라별로 하나씩).
  **한 파일에 몰지 말 것.**
- **현재 의석·본선 대진 수정.** 그쪽은 공식 명부와 경선 결과다. 여론조사로 덮지 않는다.
