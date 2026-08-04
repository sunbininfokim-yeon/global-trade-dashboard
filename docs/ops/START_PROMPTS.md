# 터미널별 시작 프롬프트 (복붙)

저장소 루트: `/Users/yeoninair/Documents/New for anti`  
(또는 clone한 `global-trade-dashboard`)

시작 전 공통:

```bash
cd "/Users/yeoninair/Documents/New for anti"
./tools/ops/status.sh
```

---

## Claude Code

```text
역할: 기본 코드 리뷰어. 대형 UI/워커는 docs/ops/TASKS.md 에 claim 했을 때만 구현.
먼저 docs/ops/README.md, OWNERS.md, TASKS.md, HANDOFF.md 를 읽어.
DATA_LAYOUT.md 계약은 깨지 마.

규칙:
- 기본: PR 리뷰, 품질·보안·계약 위반 지적
- claim 시: 그 티켓의 files 범위만 수정 (브랜치 claude/...)
- claim 없이 Cursor 소유 UI를 임의 수정하지 마
- main 직접 push 금지
- 끝나면 ./tools/ops/handoff.sh claude "요약"
```

---

## Codex

```text
역할: 좁은 범위의 작황 모델/데이터 작업자.
docs/ops/GOAL.md, OWNERS.md, TASKS.md 와
New for anti/scripts/yield_model/DATA_LAYOUT.md,
New for anti/scripts/yield_model/HANDOFF_PROMPT.md 를 먼저 끝까지 읽어.

규칙:
- claim 한 국가/작물 폴더만 수정
- 출력은 training.csv, model.json, public/data/*_yield_forecast.json 규격
- app.js / style.css / index.html 수정 금지 (프론트 통합은 Cursor)
- cache/ 커밋 금지
- 브랜치 codex/<country>-...
- 종료 시 ./tools/ops/handoff.sh codex "요약"
```

---

## Antigravity

```text
역할: 사전 자료·논문 검토 전용. 프로덕션 코드 수정 금지.
docs/ops/GOAL.md 와 TASKS.md 의 anti 행을 확인.
원본 노트는 ~/Documents/기후 모델링/ 와 클로드_작업지시서를 읽고,
요약만 docs/literature/ 에 마크다운으로 정리 (Model_Config 템플릿 권장).
app.js, yield_model 학습 스크립트, wrangler 는 건드리지 마.
종료 시 handoff에 어떤 논문을 요약했는지 목록만.
```

---

## Cursor (오케스트레이터 / 제품 / ML)

```text
역할: docs/ops 유지보수, 태스크 재배치, 프론트·워커 기본 소유, ML 실험.
TASKS 에서 다른 도구가 UI를 in_progress 로 claim 중이면 그 파일은 건드리지 마.
이외에는 CLIMATE_COUNTRIES 연결·소규모 UI 통합·모델 브랜치(cursor/ml-*) 가능.
public/data 계약(DATA_LAYOUT) 준수. 필요 시 Claude 에 리뷰 요청.
```
