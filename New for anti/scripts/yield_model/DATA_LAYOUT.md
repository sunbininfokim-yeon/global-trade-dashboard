# 데이터 저장 규칙 (Codex 안내용)

작업물이 대시보드에 나타나려면 **어디에 무엇을 저장하느냐**가 정해져 있습니다.
이 규칙만 지키면 커밋하는 순간 화면에 반영됩니다. 코드를 고칠 필요 없습니다.

---

## 1. 4단계 저장 구조

| 단계 | 위치 | 예시 | git |
|---|---|---|---|
| ① **원본 API 캐시** | `scripts/yield_model/cache/` | `power_IA.csv`, `nass_corn_IA.csv` | ❌ **제외** |
| ② **학습 테이블** | `scripts/yield_model/{국가}_{작물}_training.csv` | `us_corn_training.csv` | ✅ 커밋 |
| ③ **모델 아티팩트** | `scripts/yield_model/{국가}_{작물}_model.json` | `us_corn_model.json` | ✅ 커밋 |
| ④ **사이트가 읽는 결과** | `public/data/{국가}_yield_forecast.json` | `brazil_yield_forecast.json` | ✅ 커밋 |

### ① 캐시는 왜 커밋하지 않는가

NASA POWER·NASS 원본 일별 데이터라 현재 **29MB / 104개 파일**입니다.
스크립트를 다시 돌리면 그대로 복원되므로 저장소에 넣을 이유가 없습니다.
캐시는 재실행을 빠르게 하려는 로컬 편의일 뿐입니다.

`scripts/yield_model/.gitignore` 에 이미 등록돼 있습니다.

```
cache/
__pycache__/
*.pyc
```

### ②③④는 왜 커밋하는가

- ② 학습 테이블 (파일당 12~16KB) — 모델을 재현·검증하려면 필요
- ③ 모델 아티팩트 (2~5KB) — **계수와 측정된 성능**이 들어 있음. 화면이 이걸 읽어 신뢰도 배지를 띄움
- ④ 예측 결과 — **웹사이트가 실제로 fetch 하는 파일**

---

## 2. ④번이 화면에 뜨는 방식

`app.js`는 **국가별 로더를 두지 않습니다.** 로더도 렌더러도 하나뿐이고,
설정의 `dataFile` 하나로 어느 파일을 읽을지가 정해집니다.

```javascript
// app.js — 국가 설정
'India': {
    label: '인도',
    modelName: 'India Regional Model',   // 없으면 라벨만 표시됨 (undefined 안 뜸)
    iso: 'IND',
    view: { longitude: 78.0, latitude: 23.5, zoom: 3.8 },
    dataFile: 'india_yield_forecast.json',   // ← public/data/ 기준 파일명
    regions: [ { name: '...', label: '...', coordinates: [lon, lat] } ],
}
```

**즉 Codex는 그 JSON만 규격대로 써서 커밋하면 됩니다.** 렌더링 코드도,
로더도 건드릴 필요 없습니다. 파일이 아직 없으면 패널에 "요약 데이터를
불러오지 못했습니다"가 뜰 뿐 화면이 깨지지 않으므로, 설정을 먼저 넣고
데이터를 나중에 커밋해도 됩니다.

### 필드 이름이 파일마다 달라도 됩니다

읽는 쪽(`normalizeForecast`)이 아래 표기들을 모두 받아들입니다.
기존 파이프라인이 이미 쓰고 있는 이름을 굳이 바꾸지 마세요.

| 의미 | 허용되는 표기 |
|---|---|
| 예측값 | `point`, 또는 `yield_kg_ha: { point: … }` (인도네시아 형태) |
| 라벨 | `label_ko` → `label` → `target_label` → `crop` 순으로 사용 |
| 전년 실적 | `last_actual.yield`, `.value`, `.yield_kg_ha` |
| 신뢰도 낮음 | `skill.low_confidence`, `low_confidence`, `skill.beats_trend === false` |
| 추세 대비 편차 | `weather_effect_pct`, 또는 `weather_effect` + `trend`로 계산 |
| 단위 | `unit` (없으면 `kg/ha`로 간주) |

구조도 두 가지를 모두 받습니다:

- **중첩형** `regions[키].crops[작물]` — 한 산지에 작물이 여러 개인 경우 (미국)
- **평면형** `regions[키]` 자체가 작물 — 산지 하나에 작물 하나 (브라질·아르헨티나·호주·중국)

---

## 3. ④번 JSON 규격

```json
{
  "generated_at": "2026-08-04T09:16:52+00:00",
  "season": 2026,
  "country": "India",
  "regions": {
    "punjab_wheat": {
      "label": "Punjab wheat",
      "label_ko": "펀자브 밀",
      "note": "PB HR, production-weighted",
      "crops": {
        "wheat": {
          "label_ko": "밀",
          "unit": "kg/ha",
          "point": 4820.0,
          "range_68": [4586.0, 5054.0],
          "range_95": [4361.0, 5279.0],
          "trend": 4880.0,
          "weather_effect": -60.0,
          "last_actual": { "year": 2025, "yield": 4750.0 },
          "season_progress": {
            "critical_days": { "observed": 120, "forecast": 30, "climatology": 0 },
            "observed_share": 0.8
          },
          "skill": {
            "method": "forward-chaining, trend refit inside each fold",
            "skill_vs_trend_only": 0.213,
            "detrended_r2": 0.205,
            "sigma_used": 234.0,
            "model_sigma": 210.0,
            "train_window_years": null,
            "low_confidence": false
          },
          "trained_years": [1992, 2025]
        }
      }
    }
  }
}
```

### 필수 필드의 의미

| 필드 | 역할 |
|---|---|
| `low_confidence` | `skill_vs_trend_only < 0.20` 이면 `true`. 화면에 **"신뢰도 낮음"** 배지가 자동으로 붙음 |
| `observed_share` | 생육 결정기 중 실제 관측 비율. **신뢰구간을 넓히는 근거** |
| `sigma_used` | `model_sigma × (1 + 0.5 × (1 − observed_share))`. 시즌이 진행되면 자동으로 좁아짐 |
| `train_window_years` | 이동창을 쓴 경우만 숫자, 아니면 `null`. 학습기간이 짧은 이유를 화면이 설명함 |
| `weather_effect` | 추세 대비 편차. **이게 없으면 "왜 이 값인지"를 화면이 설명할 수 없음** |

---

## 4. 예측이 불가능한 지역은 어떻게 표시하나

서아프리카처럼 **현재값만 있고 예측이 없는 경우**가 있습니다.
그럴 때 억지로 `point`를 채우지 마세요. 대신 이렇게 씁니다:

```json
{
  "regions": {
    "ghana_cocoa": {
      "label_ko": "가나 카카오",
      "forecast_available": false,
      "reason_ko": "다년생 작물로 2~3년 전 기상의 지연 효과가 지배적이라 현행 방법론으로는 예측하지 않습니다.",
      "crops": {
        "cocoa": {
          "label_ko": "카카오",
          "unit": "kg/ha",
          "last_actual": { "year": 2024, "yield": 450.0 }
        }
      }
    }
  }
}
```

`point` / `range_68` / `skill` 을 생략하면 화면은 **전년 실적만** 보여주고
예측 구간은 그리지 않습니다. `reason_ko`가 있으면 그 문구를 함께 띄웁니다.

> 값이 없을 때 0이나 임의값을 넣지 마세요. 화면이 그걸 "예측치 0"으로 표시합니다.

### 4b. 국가 단위 참고 패널 (서아프리카 코코아)

지역 forecast를 검증하지 못한 국가는 **정부·기관 전망 + 조사 메모**만 올립니다.
파일은 그대로 `public/data/{country}_yield_forecast.json` 이고, 최상위에:

| 필드 | 의미 |
|---|---|
| `forecast_available: false` | 예측 발행 안 함 |
| `panel_mode: "reference"` | 좌측을 참고 패널로 렌더 (필수 권장) |
| `title_ko` / `reason_ko` | 배지·설명 |
| `government_outlooks[]` | 기관·시즌·수치·`url` |
| `research_notes[]` | 조사 메모 + `links[].url` |
| `sources[]` | `{ name, url, supports }` |

`CLIMATE_COUNTRIES` 항목에 `panelMode: 'reference'` 와 geo 이름(`Ghana`, `Ivory Coast`)·`iso`를 맞춥니다.
가나/코트디부아르 표시 규칙은 `west_africa/COCOA_REFERENCE_KO.md` 참고.

---

## 5. 새 국가를 추가할 때 (2단계)

**Step 1 — 데이터를 규격대로 저장**
```
public/data/{country}_yield_forecast.json
```

**Step 2 — `app.js`의 `CLIMATE_COUNTRIES` 에 항목 추가**
```javascript
'Ghana': {
    label: '가나',
    modelName: 'West Africa Cocoa (관측)',   // 생략 가능
    iso: 'GHA',                              // world.geo.json 의 3자리 코드
    view: { longitude: -1.0, latitude: 7.9, zoom: 6.0 },
    dataFile: 'ghana_yield_forecast.json',
    regions: [
        { name: 'Ghana Cocoa Belt', label: '카카오 벨트', coordinates: [-1.6, 6.4] },
    ],
},
```

**좌표는 반드시 `coordinates`에 직접 쓰세요.** `CountriesData`에서 찾도록 두면
그 맵은 무역 노선용이라 항목이 없는 지역이 **조용히 지도에서 사라집니다**
(실제로 브라질 4개 산지 중 2개가 이 문제로 안 보였던 이력이 있습니다).

**`data.js`에 로더를 추가하지 마세요.** 예전에는 국가마다 로더가 하나씩
필요했지만 지금은 `dataFile`을 읽는 공용 로더 하나로 처리됩니다.

---

## 6. 주의: 파일 크기

`public/data/` 는 **방문자가 페이지를 열 때마다 받아가는** 경로입니다.

현재 `icrisat_crop_production.json` 이 **6MB**로, 나머지 전부를 합친 것보다 큽니다.
학습용 원본을 여기 두면 사이트가 느려집니다. **집계·요약한 결과만** 넣고,
원본은 `cache/`(gitignore) 또는 `scripts/` 하위에 두세요.

기준: `public/data/` 파일 하나가 **200KB를 넘으면** 요약이 필요한지 검토.

---

## 6b. 속보 티커 (`ticker_v1.json`)

- **카테고리**: `commodity` | `diplomacy` | `commodity_diplomacy` | `election` | `cabinet_reshuffle` (+ 유동성 계열)
- **선거 부가**: `election_type` ∈ presidential / general / local / by_election / party_leadership / **governance_poll** / **cabinet_reshuffle**
- **여론조사**: 전국 대선 경마형 거부 · 통치(job approval 등) 허용 (`politics_extra.json`)
- **중요도**: `country_tier` A|B|C × `info_grade` 1|2|3 → `scores.importance` / `scores.final`  
  규칙: 주요국 3급이 비주요국 2급보다 높을 수 있음. 튜닝: `commodity_news/label_importance.py` → `cache/importance_label_history.jsonl` (미커밋)
- **cap**: `importance.json` 의 `ticker_cap`, `min_importance`

| 항목 | 값 |
|------|-----|
| 생성 | `scripts/commodity_news/build_ticker.py` |
| 산출 | `public/data/ticker_v1.json` |
| 스키마 | `scripts/commodity_news/schemas/ticker_v1.schema.json` |
| API | Worker `GET /api/ticker` (IP 언어 표시 + `title.ko` 메인) |
| 문서 | `scripts/commodity_news/README.md` |

UI(`app.js` 티커)는 아직 연결 전일 수 있음. **JSON + API만 계약**으로 두고 T01 이후에 로드.

## 6c. 유동성·공식 매크로 (`liquidity_intel_v1.json`)

| 항목 | 값 |
|------|-----|
| 생성 | `scripts/macro_intel/build_liquidity.py` |
| 산출 | `public/data/liquidity_intel_v1.json` |
| API | Worker `GET /api/liquidity` |
| 포함 | QRA(순발행·기말현금), 베이지북 링크/톤, 유의 기자(양영빈 등), `finance_panel_fields`, 합치기용 `ticker_items` |
| 문서 | `scripts/macro_intel/README.md` |

금융 창 기존 FRED TGA/`WALCL` 수치는 유지하고, 이벤트 카드는 본 JSON 필드를 추가하면 됨.

## 6d. 세계 선거 보드 (`elections_board_v1.json`)

- `live_election_news`: 티커의 선거·개각·통치지지율 헤드라인
- `betting_markets`: 미국 예측시장 스냅샷 (기본 Polymarket Gamma public API)  
  - `markets[]`: question, outcomes[{outcome,price}], volume, url  
  - `ticker_hints` (선택): 상위 시장 요약
- 구성: `scripts/election_watch/` · `--no-betting` 가능

| 항목 | 값 |
|------|-----|
| 생성 | `scripts/election_watch/build_board.py` |
| 시드 | `scripts/election_watch/config/country_seed.json` |
| 산출 | `public/data/elections_board_v1.json` |
| 속보 연동 | 선거·개각·통치지지율; 전국 대선 경마 여론조사 배제 |
| 배팅 | `betting_markets` (Polymarket; `config/betting.json`) |
| 당대표 캡 | 대통령제 여+제1야 / 의원내각제 주요정당 ≤4 |

UI 선거 창은 이후. 시드에 일정만 채우면 보드가 자람.

## 6e. 공식 보고서 (`official_reports_v1.json`)

| 항목 | 값 |
|------|-----|
| 생성 | `scripts/official_reports/build_reports.py build` |
| 산출 | `public/data/official_reports_v1.json` |
| API | `GET /api/official-reports` |
| 도메인 | 경제·금융·외교·안보·농업(수출통제) |
| 학습 | `series_catalog.json` + `cache/label_history.jsonl` (promote/keep/drop) |
| Dropbox | **비범위** (공개 기관 피드만) |

속보: `ticker_items` / 지표: `indicators`·`dashboard_fields`.

---

## 7. 커밋 전 체크리스트

```
□ cache/ 가 커밋에 포함되지 않았는가          (git status 로 확인)
□ public/data/ 새 파일이 200KB 미만인가
□ JSON에 skill.skill_vs_trend_only 가 있는가  (없으면 신뢰도 배지가 안 뜸)
□ 예측 불가 지역에 임의값을 넣지 않았는가
□ 좌표를 coordinates 에 직접 썼는가
□ 설정에 dataFile 을 썼는가                   (data.js 로더는 추가하지 않음)
□ 브랜치가 main 인가                          (다른 브랜치면 배포 안 됨)
```

마지막 항목이 실제로 두 번 문제가 됐습니다. 작업 브랜치에 커밋해두고
`git push origin main` 을 하면 **"Everything up-to-date"** 가 나오면서
아무 일도 일어나지 않습니다. 배포되는 브랜치는 `main` 하나뿐입니다.
