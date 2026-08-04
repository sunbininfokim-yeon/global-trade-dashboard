# OWNERS — 역할과 폴더 소유권

충돌을 줄이려면 **경로 단위 소유**를 지킨다.  
같은 브랜치에서 소유 경로 밖을 수정하지 마세요. 예외는 PR 리뷰 코멘트 반영 + 당사자 합의.

## 역할 매트릭스

| 역할 | 도구 | 주요 산출물 | 리뷰어 |
|------|------|-------------|--------|
| Orchestrator / ML | **Cursor** | `docs/ops/*`, `tools/ops/*`, 학습 실험, 목표 재배치 | Claude (코드 품질) |
| App & UI lead + code review | **Claude Code** | `New for anti/{app,style,index,data,shipping}.js*`, `_worker.js` | Cursor (제품 관점) |
| Scoped model/data tasks | **Codex** | `scripts/yield_model/**` 지정 국가, `public/data/*_forecast.json` | Claude → Cursor |
| Literature only | **Antigravity** | `docs/literature/**`, Obsidian 요약 링크 | 사람 |

Obsidian 연구 노트 원본: `~/Documents/기후 모델링/`  
코드 레포에 넣을 때는 **요약·Model_Config만** `docs/literature/` 또는 별도 PR로 반영 (대용량 PDF 금지).

## 경로 소유권

| 경로 | Owner | 비고 |
|------|-------|------|
| `docs/ops/**` | Cursor | 다른 도구는 TASKS/HANDOFF 갱신만 허용 |
| `tools/ops/**` | Cursor | |
| `New for anti/app.js` | Claude | **현재 UI WIP — 타 도구 수정 금지** |
| `New for anti/style.css` | Claude | 同上 |
| `New for anti/index.html` | Claude | 同上 |
| `New for anti/data.js` | Claude | 스키마 합의 후 Codex가 JSON만 추가하는 경우 OK |
| `New for anti/shipping.js` | Claude | |
| `_worker.js`, `wrangler.jsonc` | Claude (구조) / Cursor (캐시·cron 정책 협의) | |
| `New for anti/scripts/yield_model/**` | Codex 또는 Cursor (TASKS 담당란) | 동시에 같은 국가 폴더 X |
| `New for anti/public/data/*_yield_forecast.json` | 해당 모델 담당 | DATA_LAYOUT 준수 |
| `New for anti/public/data/live_override.json` | 데이터 서브태스크 담당 | AI_WORKFLOW 스키마 |
| `.github/workflows/**` | Cursor + Claude | 배포/CI 깨지면 우선 중단 |
| `docs/literature/**` | Antigravity | 코드 import 금지 |
| `.claude/**` | Claude | 로컬 설정, 커밋 여부 신중 |

## 브랜치 네이밍

```text
claude/ui-<짧은주제>
claude/fix-<이슈>
codex/<country>-<crop>
cursor/ops-<주제>
cursor/ml-<주제>
anti/lit-<주제>
```

예: `codex/india-wheat`, `claude/ui-climate-panels`

## 병렬 작업 규칙

1. 국가 단위로 폴더를 나눔 (`yield_model/india/` vs `brazil/`).
2. UI 작업 중이면 ML은 **forecast JSON + 스크립트만** PR.
3. `main` 리베이스 전 `./tools/ops/sync-main.sh`.
4. force-push main 금지.
