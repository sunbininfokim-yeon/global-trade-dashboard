# `model.yaml` — 국가 모델 매니페스트 규격 v1

**한 줄 요약:** 국가를 추가·수정할 때 `app.js`를 열지 않는다. 자기 폴더의 `model.yaml`만 채운다.

---

## 왜 이게 필요한가

지금은 국가 하나를 붙이려면 `app.js`의 `CLIMATE_COUNTRIES` 객체를 고쳐야 한다.
Cursor가 MENA를, Codex가 베트남을 동시에 작업하면 **둘 다 같은 파일 같은 줄**을 건드린다.
소유권 문서로는 못 막는다 — 2026-08-05에 실제로 작업이 한 번 유실됐다.

`model.yaml`이 있으면 국가 작업이 `scripts/yield_model/{country}/` 안에서 끝난다.
UI는 이 파일들로 생성된 레지스트리를 읽는다.

```
scripts/yield_model/*/model.yaml
        │  build_registry.py  (GitHub Action)
        ▼
New for anti/public/data/climate_registry_v1.json
        │  app.js가 시작 시 1회 fetch
        ▼
화면
```

---

## 폴더 규격

```
scripts/yield_model/{country}/
  model.yaml      ← 계약. 아래 스키마 준수
  collect.py      원본 수집 (캐시는 커밋 금지 — DATA_LAYOUT.md ①)
  climate.py      기상 피처
  labels.py       공식 통계 라벨
  train.py        적합 + 백테스트
  predict.py      public/data/{country}_yield_forecast.json 생성
  models/         모델 아티팩트
  README.md       방법론 + 논문 출처
```

기존 국가들이 `climate_ar.py` / `data.py` / `data/` 처럼 제각각인데,
**이름을 맞추는 것보다 `model.yaml`이 먼저다.** 파일명 통일은 나중에 해도 화면은 돌아간다.

---

## 스키마

```yaml
# ── 필수 ────────────────────────────────────────────────────────────────
country: india                    # 폴더명과 동일. 소문자 snake_case
iso: IND                          # ISO 3166-1 alpha-3
label_ko: 인도                     # 화면 표기
label_en: India                   # GeoJSON `properties.name` 과 매칭되는 이름
panel_mode: forecast              # forecast | reference
data_file: india_yield_forecast.json   # public/data/ 기준 파일명

view:                             # 국가 클릭 시 지도 카메라
  longitude: 78.0
  latitude: 23.5
  zoom: 3.8

regions:                          # 산지 핀. 최소 1개
  - key: punjab_wheat             # forecast JSON의 region key 와 일치해야 함
    label_ko: 펀자브·하리아나 (밀)
    coordinates: [75.8, 30.4]     # [경도, 위도]
    crops: [wheat]                # CROP_CANON 어휘 (wheat/corn/soy/rice/cotton/…)

# ── 출처 (화면에 노출됨. 비우지 말 것) ──────────────────────────────────
sources:
  labels:
    name: "ICRISAT District Level Database"
    url: "https://..."
    updated: "2026-07-30"         # 데이터 자체의 최신 시점 (실행일 아님)
  climate:
    name: "NASA POWER"
    url: "https://power.larc.nasa.gov/"
    updated: "2026-08-01"

method_refs: "Lobell & Burke (2010) · Schlenker & Roberts (2009)"

# ── 선택 ────────────────────────────────────────────────────────────────
model_name: "India Regional Model"   # 없으면 label_ko 사용
aliases: ["Côte d'Ivoire"]           # GeoJSON 이름이 다를 때
trade_policy:                        # 수출 통제 상태 (지도 색)
  restricted: true
  prohibited_crops: []
  note: "수출 인허가·쿼터 등 제한적 조치"
notes_ko: |
  자유 서술. 화면 좌측 모델 설명에 그대로 들어간다.
```

### `panel_mode`

| 값 | 의미 | 예 |
|---|---|---|
| `forecast` | 단수 예측을 제공한다. `data_file`의 JSON이 반드시 존재해야 한다 | 미국·브라질·인도 |
| `reference` | **예측하지 않는다.** 정부·기관 전망과 조사 메모만 보여준다 | 서아프리카 코코아 |

`reference`는 데이터가 검증된 예측을 지탱하지 못할 때 쓴다.
숫자를 만들어내는 것보다 "왜 예측하지 않는지"를 적는 편이 낫다.

---

## 검증 규칙 (CI가 막는 것)

1. `country` == 폴더명
2. `iso` 가 월드 GeoJSON에 존재
3. `panel_mode: forecast` 이면 `public/data/{data_file}` 이 **실제로 존재**
   → 2026-08-05 현재 인도가 이 규칙에 걸린다 (`app.js`가 fetch 하는데 파일 없음)
4. 모든 `regions[].key` 가 forecast JSON의 region key 에 존재
5. `sources.*.updated` 가 ISO 날짜이고 **미래가 아님**
6. `coordinates` 가 해당 국가 경계 안 (±5° 여유)

---

## 다른 터미널 작업 절차

**Cursor / Codex 는 이렇게만 하면 된다:**

1. `scripts/yield_model/{country}/` 안에서만 작업
2. `model.yaml` 작성 (위 스키마)
3. `predict.py` 가 `public/data/{data_file}` 생성
4. PR — **`app.js` 는 건드리지 않는다**
5. CI 통과하면 머지. UI 코드 변경 없이 화면에 뜬다

**UI 수정이 필요하다고 느껴지면 그건 규격이 부족하다는 신호다.**
코드를 고치지 말고 이 문서에 필드를 추가하자고 제안할 것.

---

## 이관 상태

| 국가 | model.yaml | 비고 |
|---|---|---|
| india | ☐ | 1번 시범 대상 (forecast JSON 없음 — 같이 복구) |
| united_states | ☐ | `yield_forecast.json` 이름이 국가 접두사 없음 → 전환 시 정리 |
| brazil | ☐ | |
| argentina | ☐ | |
| australia | ☐ | |
| china | ☐ | |
| indonesia | ☐ | |
| russia | ☐ | |
| vietnam | ☐ | Codex 작업 중 |
| mena | ☐ | Cursor 작업 중 — forecast JSON 아직 없음 |
| west_africa | ☐ | `panel_mode: reference` |

전환 순서는 `docs/ops/ARCHITECTURE_REVIEW_2026-08-05.md` §9 참조.
