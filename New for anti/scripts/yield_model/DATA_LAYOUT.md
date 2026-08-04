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

`app.js`가 국가별 로더를 갖고 있고, 각 로더는 `public/data/` 의 파일을 읽습니다.

```javascript
// app.js — 국가 설정
'India': {
    label: '인도',
    modelName: 'India Regional Model',   // 없으면 라벨만 표시됨 (undefined 안 뜸)
    iso: 'IND',
    view: { longitude: 78.0, latitude: 23.5, zoom: 3.8 },
    summaryKey: 'india',                 // ← 로더를 고르는 키
    regions: [ { name: '...', label: '...', coordinates: [lon, lat] } ],
}
```

`summaryKey`가 `india`면 `window.loadIndiaYieldForecast()`가 호출되고,
그 함수가 `/public/data/india_yield_forecast.json`을 읽습니다.

**즉 Codex는 그 JSON만 규격대로 써서 커밋하면 됩니다.** 렌더링 코드는 건드릴 필요 없습니다.

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
    summaryKey: 'ghana',
    regions: [
        { name: 'Ghana Cocoa Belt', label: '카카오 벨트', coordinates: [-1.6, 6.4] },
    ],
},
```

**좌표는 반드시 `coordinates`에 직접 쓰세요.** `CountriesData`에서 찾도록 두면
그 맵은 무역 노선용이라 항목이 없는 지역이 **조용히 지도에서 사라집니다**
(실제로 브라질 4개 산지 중 2개가 이 문제로 안 보였던 이력이 있습니다).

그리고 `summaryKey`에 대응하는 로더가 `data.js`에 필요합니다:
```javascript
window.loadGhanaYieldForecast = async function() { /* /public/data/ghana_yield_forecast.json */ };
```

---

## 6. 주의: 파일 크기

`public/data/` 는 **방문자가 페이지를 열 때마다 받아가는** 경로입니다.

현재 `icrisat_crop_production.json` 이 **6MB**로, 나머지 전부를 합친 것보다 큽니다.
학습용 원본을 여기 두면 사이트가 느려집니다. **집계·요약한 결과만** 넣고,
원본은 `cache/`(gitignore) 또는 `scripts/` 하위에 두세요.

기준: `public/data/` 파일 하나가 **200KB를 넘으면** 요약이 필요한지 검토.

---

## 7. 커밋 전 체크리스트

```
□ cache/ 가 커밋에 포함되지 않았는가          (git status 로 확인)
□ public/data/ 새 파일이 200KB 미만인가
□ JSON에 skill.skill_vs_trend_only 가 있는가  (없으면 신뢰도 배지가 안 뜸)
□ 예측 불가 지역에 임의값을 넣지 않았는가
□ 좌표를 coordinates 에 직접 썼는가
□ 브랜치가 main 인가                          (다른 브랜치면 배포 안 됨)
```

마지막 항목이 실제로 두 번 문제가 됐습니다. 작업 브랜치에 커밋해두고
`git push origin main` 을 하면 **"Everything up-to-date"** 가 나오면서
아무 일도 일어나지 않습니다. 배포되는 브랜치는 `main` 하나뿐입니다.
