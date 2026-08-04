# OWNERS — 역할과 폴더 소유권

충돌을 줄이려면 **경로 단위 소유** + **`TASKS.md` claim** 을 함께 본다.  
같은 파일을 둘 이상 도구가 동시에 잡지 않는다. 예외는 리뷰 코멘트 반영 + 당사자 합의.

> **2026-08-04 핸드오프:** T01(UI 공용화) 완료 후  
> **기본 제품·통합 소유 = Cursor** · **기본 코드 리뷰 = Claude**.  
> UI “영구 락”은 해제. 큰 UI 작업은 `TASKS`에 claim 한 쪽만 수정.

## 역할 매트릭스

| 역할 | 도구 | 주요 산출물 | 리뷰어 |
|------|------|-------------|--------|
| Orchestrator / product / ML | **Cursor** | `docs/ops/*`, `tools/ops/*`, 학습 실험, `CLIMATE_COUNTRIES`·소규모 프론트 통합, 목표 재배치 | Claude (품질) |
| Code review + 대형 UI/아키텍처 (claim 시) | **Claude Code** | PR 리뷰, `TASKS`로 맡은 대규모 `app.js`·워커 작업 | Cursor (제품) |
| Scoped model/data tasks | **Codex** | `scripts/yield_model/**` 지정 국가, `public/data/*_forecast.json` | Claude → Cursor |
| Literature only | **Antigravity** | `docs/literature/**`, Obsidian 요약 링크 | 사람 |

Obsidian 연구 노트 원본: `~/Documents/기후 모델링/`  
코드 레포에 넣을 때는 **요약·Model_Config만** `docs/literature/` 또는 별도 PR로 반영 (대용량 PDF 금지).

## 경로 소유권 (기본값)

| 경로 | Owner (기본) | 비고 |
|------|--------------|------|
| `docs/ops/**` | Cursor | 다른 도구는 TASKS/HANDOFF 갱신만 허용 |
| `tools/ops/**` | Cursor | |
| `New for anti/app.js` | **Cursor** (기본) | Claude가 `TASKS`에 UI 티켓 claim 시 그 기간만 Claude 단독 |
| `New for anti/style.css` | Cursor | 同上 |
| `New for anti/index.html` | Cursor | 同上 |
| `New for anti/data.js` | Cursor | Codex/ ML은 JSON 스키마 준수 시 data 계약만 |
| `New for anti/shipping.js` | Cursor | |
| `_worker.js`, `wrangler.jsonc` | Cursor (일상) / Claude (claim 시 구조 변경) | 배포 깨지면 즉시 중단 |
| `New for anti/scripts/yield_model/**` | Codex 또는 Cursor (`TASKS` 담당란) | 동시에 같은 국가 폴더 X |
| `New for anti/public/data/*_yield_forecast.json` | 해당 모델 담당 | DATA_LAYOUT 준수 |
| `New for anti/public/data/live_override.json` 및 뉴스·유동성·보고서 JSON | Cursor / 해당 파이프라인 담당 | |
| `.github/workflows/**` | Cursor | Claude claim 가능 |
| `docs/literature/**` | Antigravity | 코드 import 금지 |
| `.claude/**` | Claude | 로컬 설정, 커밋 여부 신중 |

### Claim이 있으면 claim 우선

`TASKS.md` 에서 어떤 경로가 `in_progress` + owner=claude|cursor|codex 이면,  
**그 행의 files 범위는 담당 도구만 수정**. 기본 Owner 표보다 우선한다.

## 브랜치 네이밍

```text
claude/ui-<짧은주제>
claude/fix-<이슈>
codex/<country>-<crop>
cursor/ops-<주제>
cursor/ml-<주제>
cursor/ui-<주제>
anti/lit-<주제>
```

## 병렬 작업 규칙

1. 국가 단위로 폴더를 나눔 (`yield_model/india/` vs `brazil/`).
2. UI를 누가 `in_progress`로 잡고 있으면 다른 도구는 그 파일 금지.
3. UI 잠금이 없을 때 ML은 forecast JSON + 스크립트 PR이 기본, `CLIMATE_COUNTRIES` 연결도 Cursor 가능.
4. `main` 리베이스 전 `./tools/ops/sync-main.sh` (clean tree).
5. force-push main 금지.
6. **작업 브랜치 커밋 후 main만 push → 배포 안 됨** — PR merge 필수.
