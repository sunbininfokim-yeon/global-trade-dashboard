# 전체 코드 재검토 — 초안 (2026-08-05, Claude Code)

이 문서는 **결정문이 아니라 초안**이다. 사람이 읽고 자르거나 순서를 바꾸라고 쓴 것이다.

대상: UI(`New for anti/*`) · 국가별 예측 모델(`scripts/yield_model/**`) ·
데이터 파이프라인(`scripts/**` → `public/data/*.json`) · 배포(GitHub Actions → Cloudflare Worker).

---

## 0. 지금 구조를 한 장으로

```
                    ┌──────────────── 다른 터미널들 ────────────────┐
                    │  Cursor(ML)   Codex(국가모델)   news_api 등    │
                    └───────────────────┬──────────────────────────┘
                                        │ commit
                    ┌───────────────────▼──────────────────────────┐
   GitHub Actions   │  scripts/{yield_model,commodity_news,...}     │
   (cron 14개)      │       ↓ 실행                                  │
                    │  New for anti/public/data/*.json  ← 산출물     │
                    └───────────────────┬──────────────────────────┘
                                        │ main merge
                    ┌───────────────────▼──────────────────────────┐
   Cloudflare       │  _worker.js  (/api/* 프록시 + KV 캐시)         │
   Worker           │  assets = New for anti/                       │
                    └───────────────────┬──────────────────────────┘
                                        │
                          app.js / data.js / shipping.js
                          (지도 · 기후 · 해운 · 거시)
```

산출물은 **두 갈래**로 화면에 닿는다:

| 경로 | 예 | 갱신 |
|---|---|---|
| ① 커밋된 JSON → 정적 fetch | `brazil_yield_forecast.json`, `ticker_v1.json` | Actions cron |
| ② Worker API 프록시 → KV 캐시 | `/api/comtrade`, `/api/macro`, `/api/usda-esr` | 요청 시 + 야간 warm-up |

**진단: 이 두 갈래가 규격도 다르고 관리 주체도 다르다.** 아래 문제 대부분이 여기서 나온다.

---

## 1. 지금 당장 깨져 있는 것 (초안 이전에 고쳐야 함)

| # | 증상 | 원인 | 영향 |
|---|---|---|---|
| B1 | 인도 기후 패널이 빈 화면 | `app.js`가 `india_yield_forecast.json`을 fetch하는데 **파일 없음** | 인도 클릭 시 무응답 |
| B2 | MENA 동일 | `mena_yield_forecast.json` 없음 (작업 중) | 메뉴에 없어 노출은 안 됨 |
| B3 | 첫 로딩 6.1MB | `icrisat_crop_production.json`을 브라우저가 통째로 받음 | 모바일·저속 회선에서 체감 큼 |
| B4 | 레포 455MB | `모델링 결과/` 안에 레포 **중첩 복사본 2개** (`모델링 결과/New for anti/`, `모델링 결과/파일/New for anti/`) | clone·CI 매번 비용 |
| B5 | 워크플로 중복 | `fetch_icrisat.yml` ↔ `india_icrisat_fetch.yml` | 같은 작업 2번 |

B1은 실사용 버그다. B4는 한 번 지우면 끝난다.

---

## 2. 핵심 진단 — 문제는 "조율"이 아니라 **하드코딩**이다

여러 터미널이 부딪히는 진짜 이유는 규칙을 안 지켜서가 아니라,
**국가를 하나 추가할 때 `app.js`를 반드시 열어야 하기 때문**이다.

```js
// app.js — 국가를 늘릴 때마다 여기를 고쳐야 한다
const CLIMATE_COUNTRIES = {
  'United States': { dataFile: 'yield_forecast.json', regions: [...] },
  'Brazil':        { dataFile: 'brazil_yield_forecast.json', regions: [...] },
  ...
};
```

Codex가 베트남을, Cursor가 MENA를 동시에 붙이면 **둘 다 `app.js` 같은 줄**을 건드린다.
소유권 문서로는 못 막는다 — 실제로 오늘 그래서 작업이 한 번 날아갔다.

> 오늘 무역 지도에서 같은 문제를 이미 한 번 풀었다.
> 65개 국가 좌표를 수기로 적어 두고 없으면 버리던 것을 → GeoJSON에서 중심점을 계산하는
> 레지스트리로 바꿨더니, **새 국가가 데이터에만 들어오면 코드 수정 없이 동작**한다.
> 기후 쪽에도 같은 수술이 필요하다.

---

## 3. 제안 ① — 국가 모델 폴더 규격 통일 + 매니페스트

### 지금 (국가마다 제각각)

```
argentina/  README __init__ climate_ar.py collect.py magyp.py models/
australia/  README __init__ abares.py      collect.py climate.py models/
india/      README __init__ backtest.py    collect.py climate.py data/
west_africa/ COCOA_REFERENCE_KO.md reference/      ← 코드 없음 (참고 전용)
```

기후 파일명이 `climate.py` / `climate_ar.py`로 갈리고, 데이터가 `data/` / `data.py`로 갈린다.
새 터미널이 들어오면 **매번 남의 폴더를 읽어야** 규칙을 안다.

### 제안

```
scripts/yield_model/{country}/
  model.yaml      ← 신규. 이 폴더의 유일한 계약
  collect.py      원본 수집  (캐시는 커밋 안 함 — DATA_LAYOUT 유지)
  climate.py      기상 피처
  labels.py       공식 통계 라벨
  train.py        적합 + 백테스트
  predict.py      public/data/{country}_yield_forecast.json 생성
  models/         모델 아티팩트
  README.md       방법론 + 논문 출처
```

`model.yaml` 예시:

```yaml
country: india
iso: IND
label_ko: 인도
panel_mode: forecast          # forecast | reference (서아프리카는 reference)
data_file: india_yield_forecast.json
view: { longitude: 78.0, latitude: 23.5, zoom: 3.8 }
regions:
  - key: punjab_wheat
    label_ko: 펀자브·하리아나 (밀)
    coordinates: [75.8, 30.4]
    crops: [wheat]
sources:
  labels:  { name: "ICRISAT / Agri Ministry", url: "...", updated: "2026-07-30" }
  climate: { name: "NASA POWER", url: "..." }
method_refs: "Lobell & Burke (2010) · ..."
```

**왜 YAML 한 장이 조율 문제를 푸는가**

- 새 국가 = **자기 폴더 안에서 끝난다.** `app.js` 안 건드림 → 머지 충돌 구조적으로 소멸
- Cursor/Codex에게 줄 지시가 "이 스키마대로 `model.yaml`을 채워라" 한 줄로 압축됨
- 서아프리카처럼 예측 없는 국가도 `panel_mode: reference`로 같은 규격 안에 들어옴

---

## 4. 제안 ② — UI 레지스트리 (app.js 탈하드코딩)

```
scripts/yield_model/*/model.yaml
        │  GitHub Action (신규: build_registry.yml)
        ▼
New for anti/public/data/climate_registry_v1.json
        │  app.js가 시작 시 1회 fetch
        ▼
CLIMATE_COUNTRIES 를 이걸로 대체
```

`app.js` 변경은 사실상 이 한 줄:

```js
// 하드코딩 객체 → 레지스트리 fetch
const CLIMATE_COUNTRIES = await loadClimateRegistry();
```

효과:
- 국가 추가·수정이 **UI 배포와 분리**된다
- 레지스트리에 `updated` 필드가 있으니 화면에 데이터 신선도를 그대로 띄울 수 있다
- B1(인도 파일 없음) 같은 사고를 CI가 **머지 전에** 잡는다 — 레지스트리에 선언됐는데 JSON이 없으면 빌드 실패

---

## 5. 제안 ③ — 데이터 소스 다중화 (실시간 개편 대비)

### 지금

`data.js`에 상품 → HS코드 1:1, 소스는 UN Comtrade 하나뿐. **연 단위 데이터**라 실시간이 아니다.

```js
corn: { hsCode: "1005", colorScheme: {...} }   // 소스가 하나로 못 박혀 있음
```

`_worker.js`에는 이미 `/api/usda-esr`(주간 수출판매), `/api/psd`, `/api/usda-fas` 라우트가
**있는데 UI가 안 쓴다.** 배선만 안 된 상태다.

### 제안 — `public/data/sources_v1.json`

```json
{
  "corn": {
    "hs": "1005",
    "flows": [
      { "id": "usda_esr",  "priority": 0, "cadence": "weekly",
        "endpoint": "/api/usda-esr?commodity=corn",
        "label_ko": "USDA 주간 수출판매", "coverage": "미국 수출만" },
      { "id": "comtrade",  "priority": 1, "cadence": "annual",
        "endpoint": "/api/comtrade?hs=1005&period=2023",
        "label_ko": "UN Comtrade", "coverage": "전세계 양자" }
    ]
  }
}
```

규칙:
1. UI는 `priority` 순으로 시도하고 **첫 성공을 쓴다**
2. 화면에 **어느 소스·기준일**인지 배지로 항상 표기 (지금도 desc에 한 줄 있는데 소스가 하나라 의미가 없음)
3. 커버리지가 다른 소스를 **합치지 않는다** — "미국 수출만"과 "전세계 양자"를 더하면 숫자가 거짓이 된다.
   겹치면 우선순위 높은 쪽만 쓰고, 나머지는 툴팁에 병기

이 파일 하나로 "같은 종목에 다른 데이터를 실시간으로 붙이는" 요구가 코드 수정 없이 해결된다.

---

## 6. 제안 ④ — 산출물 스키마 + CI 게이트

지금 스키마가 있는 것: `ticker_v1`, `elections_board_v1` (`scripts/*/schemas/`)
없는 것: **yield forecast 전부** (국가별 9개 JSON)

제안:
- `scripts/yield_model/schemas/yield_forecast_v1.schema.json` 신설 (DATA_LAYOUT.md를 스키마로 옮김)
- PR CI에서 `public/data/*_yield_forecast.json` 전부 검증
- 레지스트리 ↔ 실제 파일 존재 여부 교차 검증

효과: **다른 터미널이 만든 JSON이 UI를 깨는 일이 머지 전에 막힌다.**
지금은 깨진 걸 화면 보고 알아낸다.

---

## 7. 제안 ⑤ — 멀티 터미널 운영 (문서 → 강제)

`OWNERS.md`는 사람이 읽는 글이라 프로세스를 못 막는다. 오늘 증명됐다
(Cursor가 `claude/ui-globe`에서 `cursor/ml-ukraine-yield`로 checkout).

| 수단 | 막는 것 | 비용 |
|---|---|---|
| **worktree 분리** (오늘 적용) | 브랜치 전환이 남의 작업을 덮어쓰는 것 | 없음 |
| **CODEOWNERS** | 남의 경로 PR이 리뷰 없이 머지되는 것 | 5분 |
| **branch protection (main)** | main 직접 push | 5분 |
| **pre-commit hook** | `.verify_live/`·대용량 파일 커밋 | 15분 |
| **경로 격리** (제안 ①+②) | `app.js` 동시 편집 자체 | 위 작업량 |

권장 워크트리 배치:

```
New for anti/                      ← main 확인용 (아무도 작업 안 함)
  .worktrees/claude-ui/            ← Claude: UI + 배포
  .worktrees/cursor-ml/            ← Cursor: scripts/yield_model/{ukraine,mena}
  .worktrees/codex-<country>/      ← Codex: 국가 1개
```

각자 자기 워크트리 밖으로 안 나가면 물리적으로 안 부딪힌다.

### 다른 터미널 결과물을 흡수하는 절차

사용자가 지적한 "다른 터미널에서 완성하면 반영" 부분.

1. 그쪽 터미널은 **자기 폴더 + `model.yaml`까지만** 만들고 PR
2. CI가 스키마·레지스트리 교차 검증
3. Claude(UI 소유)는 **PR 리뷰만** 한다 — 레지스트리 방식이면 UI 코드 수정이 필요 없다
4. UI 코드 변경이 필요하다면 그건 **규격이 부족하다는 신호**다. 코드를 고치지 말고 규격(`model.yaml`)을 넓힌다

`news_api/`(별도 터미널 작업)도 같은 규격으로 흡수 가능:
이미 `ticker_v1.schema.json`이 있으므로 3·4단계만 적용하면 된다.

---

## 8. 정리 대상 (필요 없는 것)

| 대상 | 크기 | 처리 |
|---|---|---|
| `모델링 결과/` 중첩 복사본 2개 | **455MB** | 삭제. 원본은 레포 루트에 있음 |
| `.verify_live/` Chrome 프로필 | 1045 파일 | PR #4에서 제외 + gitignore 완료. `origin/cursor/*` 3개 브랜치엔 아직 남음 |
| `yield_model/` 루트의 US 아티팩트 | 10개 | `yield_model/us/`로 이동 — 미국만 규격 밖에 있음 |
| `india_icrisat_fetch.yml` | — | `fetch_icrisat.yml`과 중복. 하나 삭제 |
| `icrisat_crop_production.json` | 6.1MB | 브라우저 전송 대신 Worker API + KV로 이동, 또는 필요한 축 요약본만 |

---

## 9. 순서 제안

시간이 아니라 **의존 관계** 기준.

**1단계 — 청소 (반나절, 위험 없음)**
B4 455MB 삭제 · B5 중복 워크플로 · US 아티팩트 이동 · pre-commit hook · CODEOWNERS

**2단계 — 계약 (여기가 핵심)**
`model.yaml` 스키마 확정 → 국가 1개(인도)로 시범 → `yield_forecast_v1.schema.json` → CI 게이트
※ 인도로 시작하는 이유: B1이 지금 깨져 있어서 고치는 김에 규격도 검증된다

**3단계 — 레지스트리**
`build_registry.yml` → `climate_registry_v1.json` → `app.js`의 `CLIMATE_COUNTRIES` 제거
여기까지 오면 **국가 추가에 UI 수정이 필요 없어진다** → 터미널 충돌 종료

**4단계 — 소스 다중화**
`sources_v1.json` → 이미 있는 `/api/usda-esr` 배선 → 화면에 소스·기준일 배지

**5단계 — 나머지**
icrisat 6.1MB 처리 · MENA/우크라이나 흡수

---

## 10. 열린 질문 (사람이 정해야 함)

1. **`모델링 결과/` 455MB** — 안에 레포에 없는 원본이 있나? 없으면 바로 삭제, 있으면 먼저 추출
2. **실시간의 정의** — 주간(USDA ESR)이면 지금 구조로 충분. 일간/장중이면 Worker 캐시 전략을 다시 짜야 함
3. **Antigravity** — 거의 안 쓴다고 하셨으니 `OWNERS.md`에서 행을 빼도 되나
4. **`news_api/`** — 레포 안에 둘 건지, 별도 레포로 분리하고 산출 JSON만 받을 건지
5. **2단계 `model.yaml`을 누가 채우나** — 국가별로 해당 터미널이? 아니면 Claude가 기존 9개국 일괄 변환 후 넘기나

---

## 부록 — 이번 세션에서 확인된 기술 제약 (재발 방지)

deck.gl 9.3.7 `_GlobeView`에서 **에러 없이 렌더 안 되는 레이어**:
`ArcLayer` · `LineLayer` · `TextLayer` · `IconLayer` (모두 MapView에서는 정상).

대체 수단은 `CLAUDE.md`에 기록해 뒀다. 다른 터미널이 지도에 손대기 전에 반드시 읽어야 한다 —
모르면 "코드는 맞는데 화면에 안 나오는" 디버깅에 시간을 통째로 태운다.
