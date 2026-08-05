# HANDOFF — 최근 인수인계

## 2026-08-05 — cursor → claude (기후 UI 우측 제거)

### Goal / summary
기후 세계/국가 뷰에서 **우측 대시보드 제거**. 무역 색 범례는 맵 **우상단 미니 프레임**. 산지 핀 클릭 → **좌측 패널** 상세. 캘린더는 좌측. 툴팁 좌표 수정·작물 identity·GAIN seed note 포함.

### Live (배포본) showed
- 미국 국가뷰: 좌 GAIN+합산+캘린더 / 우「국가 집계·전망」중복 + 지역 기상효과
- 세계뷰: 우「보유 모델 N개국」설명 리스트

### Done (로컬 **미커밋**, branch checkout was `cursor/ml-vietnam-yield`)
- 우측 pane hide (`hideClimateRightChrome`, climate `right:false`)
- 맵 우상단 `climate-legend-mini` 수출통제 색
- 핀/목록 → `renderCountryPanel` 좌측 산지 모드 (`← 국가 집계`)
- cropKey identity + US 겨울/봄밀 캘린더
- `positionMapTooltip` (중국 호버 오프셋)
- `app.js?v=18` `style.css?v=16`
- T09 claim → claude

### Next (Claude)
```bash
git checkout main && git pull
git checkout -b claude/ui-climate-panel
# copy/cherry-pick UI files from this working tree; do NOT commit on ml-* branches
```
Test: http://127.0.0.1:8766/ 농산물→기후→미국→산지 핀

### GAIN/WASDE
seed 377 MMT corn ≈ 2024/25; WASDE 2026-02 2025/26 = 17,021 mb ≈ 432 MMT. 비스크레이프.

---
## 2026-08-04 — cursor

### Goal / summary
Dinner break: climate click fixed locally (app.js?v=10). Test http://127.0.0.1:8765/ (python on 8765 still listening). Codex data/shipping commit is THEIRS — do not stage/add/commit/push; leave staged shipping_* paths alone. Residual local UI: app.js index.html style.css unstaged; argentina yield model dirs also local/unstaged — do not collide with codex commit.

### Meta
- branch: `cursor/optimize-audit`
- head: `99d8c71`

### Files (working tree at handoff time)
```
"New for anti/app.js"
"New for anti/index.html"
"New for anti/public/data/argentina_yield_forecast.json"
"New for anti/public/data/shipping_capacity_v1.json"
"New for anti/scripts/shipping_capacity/README.md"
"New for anti/scripts/shipping_capacity/build_snapshot.py"
"New for anti/scripts/shipping_capacity/config/route_catalog.json"
"New for anti/scripts/shipping_capacity/config/routes.json"
"New for anti/scripts/shipping_capacity/schemas/shipping_capacity_v1.schema.json"
"New for anti/scripts/shipping_capacity/shipping_capacity/engine.py"
"New for anti/scripts/shipping_capacity/tests/test_engine.py"
"New for anti/scripts/yield_model/argentina/models/chaco_algodon.json"
"New for anti/scripts/yield_model/argentina/models/norte_soja.json"
"New for anti/scripts/yield_model/argentina/models/pampas_maiz.json"
"New for anti/scripts/yield_model/argentina/models/pampas_soja.json"
"New for anti/scripts/yield_model/argentina/models/pampas_trigo.json"
"New for anti/scripts/yield_model/argentina/predict.py"
"New for anti/scripts/yield_model/argentina/regions.py"
"New for anti/scripts/yield_model/argentina/train.py"
"New for anti/scripts/yield_model/argentina/training/chaco_algodon.csv"
"New for anti/scripts/yield_model/argentina/training/norte_soja.csv"
"New for anti/scripts/yield_model/argentina/training/pampas_maiz.csv"
"New for anti/scripts/yield_model/argentina/training/pampas_soja.csv"
"New for anti/scripts/yield_model/argentina/training/pampas_trigo.csv"
"New for anti/scripts/yield_model/argentina/training/tucuman_cana.csv"
"New for anti/shipping.js"
"New for anti/style.css"
```

### Not done / risks
_(작성자 보완)_

### Next
_(다음 에이전트/사람 액션)_

### Commands
```bash
./tools/ops/status.sh
git push -u origin cursor/optimize-audit
```

---
## 2026-08-04 — cursor (full audit + optimize)

### Goal / summary
넘어온 코드 전수 점검 후 즉시 최적화. 보고서: `docs/ops/AUDIT_2026-08-04.md`.

### Done
- 기후 지도: ARG/AUS/CHN/IDN `CLIMATE_COUNTRIES` 연결 + 공용 산지 패널
- skill 정규화 (nested yield skill, skill<0.2, climate_gate)
- 티커 UI ↔ `/api/ticker` 연결
- icrisat 6MB assets 제외, 티커 cron 시간당
- `tools/ops/audit_forecasts.py`
- 소유권 Cursor 핸드오프 문서

### Not done / risks
- **main 미머지** (PR #2 + 이 브랜치) → 프로덕션 무변화
- india_yield_forecast.json missing
- 중국/인니 모델 품질은 미개선 (표시만 정직화)

### Next
1. 사람: PR 머지 체인
2. T04 중국 skill / T04c 인도 JSON
3. Claude: T07 PR 리뷰

### Commands
```bash
./tools/ops/status.sh
python3 tools/ops/audit_forecasts.py
```

---

## 2026-08-04 — cursor (ownership handoff + decisions)

### Goal / summary
Claude가 열어 둔 두 가지( PR #2 미머지 · OWNERS/CLAUDE UI 영구 소유 )를 정리.
권장: PR #2 **머지**, UI 기본 소유 **Cursor**, Claude **리뷰 기본**.

### Done (로컬, 아직 push/머지 전일 수 있음)
- `OWNERS.md` / `CLAUDE.md` / `AGENTS.md` / `START_PROMPTS.md` / `TASKS.md` 역할 갱신
- T04 / T04b 분석·연결 후보 등록

### Not done / risks
- **PR #2 미머지** → main=`a0f631e` 근처 유지 시 UI·티커·유동성·공식보고서 미배포
- 로컬 dirty: `argentina/regions.py` (sm_summer 호출 정리) — 의도 확인 후 별도 커밋 여부
- 인도 forecast JSON 이 이 워크트리 public/data 에 없음

### Next (사람 결정 1개)
1. PR #2 머지 여부 → Yes 권장 (Claude 또는 Cursor/`gh pr merge 2`)
2. 머지 후 Cursor: T04 모델 진단 또는 T04b 4개국 UI 연결

---

## 2026-08-04 — claude

### Goal / summary
T01 UI 완료: 기후 화면 국가 하드코딩 제거(dataFile 기반 공용 로더+정규화), 지도 클릭 복귀 버그 수정, 세계지도 프레이밍 자동화. PR #2. 다음 국가는 JSON+설정 1줄이면 붙음. 서아프리카 forecast_available:false 대응 완료.

### Meta
- branch: `claude/ui-climate-generic`
- head: `13b7702`

### Files (working tree at handoff time)
```
.DS_Store
"New for anti/AI_WORKFLOW.md"
_worker.js
.claude/
.github/workflows/commodity_news_ticker.yml
.github/workflows/macro_liquidity_intel.yml
.github/workflows/official_reports.yml
AGENTS.md
CLAUDE.md
"New for anti/public/data/elections_board_v1.json"
"New for anti/public/data/liquidity_intel_v1.json"
"New for anti/public/data/official_reports_v1.json"
"New for anti/public/data/ticker_v1.json"
"New for anti/scripts/commodity_news/"
"New for anti/scripts/election_watch/"
"New for anti/scripts/macro_intel/"
"New for anti/scripts/official_reports/"
docs/
news_api/
tools/
```

### Not done / risks
_(작성자 보완)_

### Next
_(다음 에이전트/사람 액션)_

### Commands
```bash
./tools/ops/status.sh
git push -u origin claude/ui-climate-generic
```

---
최신이 위에 오도록 추가. `./tools/ops/handoff.sh`가 자동으로 prepend 할 수 있음.

---

## 2026-08-04 — Cursor (ops bootstrap)

### Goal
멀티 에이전트용 Git 운영 문서 + 터미널 스크립트 추가. UI/모델 로직 변경 없음.

### Done
- `docs/ops/*` 골격 작성
- `tools/ops/{status,claim,handoff,sync-main}.sh`
- 루트 `AGENTS.md`, `CLAUDE.md` 포인터

### Not done / risks
- Claude **UI 미완** (`New for anti/app.js` 로컬 수정 존재). 사용량 소진으로 중단.
- `AI_WORKFLOW.md` 역할 표기가 과거(Antigravity=Main Architect)라 ops 문서와 다름 → ops가 우선, 이후 정리.
- Cloudflare **커스텀 도메인**은 아직 `CLOUDFLARE.md`에 사용자 확인 필요. Worker URL은 코드상 workers.dev 존재.

### Next
1. 사람/Claude: T01 UI 마무리 → 커밋 → handoff  
2. Cursor: ops 브랜치 PR (원하면)  
3. Codex: TASKS T03 읽기 후 **한 국가만** claim  

### Commands
```bash
./tools/ops/status.sh
git status   # app.js dirty 인지 확인
```

---

## 템플릿

```markdown
## YYYY-MM-DD — <agent>

### Goal
### Done
### Files touched
### Not done / risks
### Next
### Commands
```
