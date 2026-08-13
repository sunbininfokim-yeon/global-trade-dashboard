# Official reports intel — 미·일·중 등 공식 보고서 파이프라인

**Dropbox 대량 수집은 범위에서 제외.**  
공개 기관 RSS/리스트 HTML만 보고, 의미 있는 것만 속보 + 지표 슬롯으로 내린다.

## 목표

| 산출 | 용도 |
|------|------|
| `ticker_items` | 속보창 병합 (`category=official_report`) |
| `indicators` / `dashboard_fields` | 금융·거시 창 수치·플래그 |
| `pending_review` | 애매 건 — 이후 라벨 학습 |
| `series_catalog.json` | “주요 보고서” 정의 (함께 늘려감) |

도메인: **경제 · 금융 · 외교 · 안보 · 농업(수출통제 포함)**

## 학습 모델 (협업형)

완전 자동 ML이 아니라 **카탈로그 + 사람 라벨** 루프:

```text
공식 피드 수집
   → 도메인 점수 + series_catalog 매칭
   → (선택) QRA 등 구조화 추출
   → official_reports_v1.json
   → 네가 promote/keep/drop 라벨
   → cache/label_history.jsonl 이 다음 빌드 가중치 반영
```

### 라벨 기록

```bash
python3 build_reports.py label \
  --series-id US_FED_FOMC \
  --url "https://..." \
  --title "FOMC statement" \
  --label promote \
  --note "금리 결정은 항상 속보"
```

- `promote` → 가중치 ↑  
- `keep` → 유지  
- `drop` → 가중치 ↓  

**새 종류의 중요 보고서**가 보이면 `config/series_catalog.json`에 `series_id`를 추가하는 것이 “학습 정의”의 정본이다.

## 실행

```bash
cd "New for anti/scripts/official_reports"
python3 -m unittest discover -s tests -v
python3 build_reports.py build --print-stats
python3 build_reports.py build --fixtures tests/fixtures --no-fetch --print-stats
```

출력: `public/data/official_reports_v1.json`  
API: `GET /api/official-reports` (Worker)

## 소스

`config/sources.json`

- 활성화: Fed, White House, Treasury 리스트, EIA, BOJ, ECB, BoE, China NBS EN hub  
- 비활성(403/불안정): USDA RSS, MOFA RSS, METI 등 — **IP/에이전트 이슈 해결되면 enable**

중국·일본 일부는 HTML 허브라 셀렉터가 거칠다. 쓰는 페이지만 골라 같이 다듬으면 된다.

## 사이트 연동 (나중 / T01 이후)

```js
const r = await fetch('/api/official-reports');
const { ticker_items, dashboard_fields, indicators } = await r.json();
// 속보: commodity ticker + liquidity ticker_items + 여기 ticker_items 병합
// 금융: dashboard_fields.qra_* , beige_tone 등
```

## 안 하는 것

- Dropbox/사내 리포트 전량 인제스트  
- 전 보고서 PDF LLM 요약  
- 미합의 소스 무단 스크레이핑

## 다음 소통으로 키울 것

1. 국가·기관 우선순위 (예: USTR, METI 수출통제, USDA WASDE HTML)  
2. `series_catalog`에 넣을 보고서 이름 목록  
3. 어떤 `site_slot`을 금융/안보/농업 창에 붙일지
