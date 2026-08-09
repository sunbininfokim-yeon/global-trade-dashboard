# OWNERS — 역할과 폴더 소유권

충돌을 줄이려면 **경로 단위 소유** + **`TASKS.md` claim** 을 함께 본다.  
같은 파일을 둘 이상 도구가 동시에 잡지 않는다. 예외는 리뷰 코멘트 반영 + 당사자 합의.

> **2026-08-05 핸드오프 (현행):** 사용자 지시로 소유권 이전.
> **UI + 배포 파이프라인(GitHub Actions · Cloudflare Worker) 전체 소유 = Claude Code.**
> Cursor는 이 경로들에서 손을 뗀다 — 에디터 탭도 닫아 둘 것.
> 2026-08-04자 “기본 제품 소유 = Cursor” 문구는 폐기.
>
> 이유: 08-05 작업 중 Cursor가 열어 둔 `app.js` 버퍼가 저장되면서 진행 중이던
> 수정을 통째로 덮어썼다. 같은 파일에 두 편집 주체가 붙어 있는 한 재발한다.

## 역할 매트릭스

| 역할 | 도구 | 주요 산출물 | 리뷰어 |
|------|------|-------------|--------|
| **UI + 배포 전체** | **Claude Code** | `New for anti/{app.js,style.css,index.html,data.js}`, `_worker.js`, `wrangler.jsonc`, `.github/workflows/**`, 배포 검증 | 사람 |
| ML / 학습 실험 | **Cursor** | `scripts/yield_model/**` 실험, `docs/literature` 연결, 목표 재배치 | Claude (품질) |
| Scoped model/data tasks | **Codex** | `scripts/yield_model/**` 지정 국가, `public/data/*_forecast.json` | Claude → Cursor |
| Literature only | **Antigravity** | `docs/literature/**`, Obsidian 요약 링크 | 사람 |
| **데이터 검증** | **Grok** | `docs/audit/**` — 표시된 숫자 대 현실 대조. 코드 수정 안 함 | Claude |

Obsidian 연구 노트 원본: `~/Documents/기후 모델링/`  
코드 레포에 넣을 때는 **요약·Model_Config만** `docs/literature/` 또는 별도 PR로 반영 (대용량 PDF 금지).

## 경로 소유권 (기본값)

| 경로 | Owner (기본) | 비고 |
|------|--------------|------|
| `docs/ops/**` | **Claude** | 다른 도구는 TASKS/HANDOFF 갱신만 허용 |
| `tools/ops/**` | **Claude** | |
| `New for anti/app.js` | **Claude** | 단독. Cursor/Codex 편집 금지 |
| `New for anti/style.css` | **Claude** | 단독 |
| `New for anti/index.html` | **Claude** | 단독 |
| `New for anti/data.js` | **Claude** | ML은 JSON 스키마 준수 시 data 계약만 |
| `New for anti/shipping.js` | **Claude** | |
| `_worker.js`, `wrangler.jsonc` | **Claude** | 배포 깨지면 즉시 중단 후 사람에게 보고 |
| `New for anti/scripts/yield_model/**` | Codex 또는 Cursor (`TASKS` 담당란) | 동시에 같은 국가 폴더 X |
| `New for anti/public/data/*_yield_forecast.json` | 해당 모델 담당 | DATA_LAYOUT 준수 |
| `New for anti/public/data/live_override.json` 및 뉴스·유동성·보고서 JSON | Cursor / 해당 파이프라인 담당 | |
| `.github/workflows/**` | **Claude** | 예측 JSON 생성 워크플로는 담당 모델과 협의 |
| `docs/literature/**` | Antigravity | 코드 import 금지 |
| `docs/audit/**` | **Grok** | 유일한 쓰기 허용 경로. `grok/*` 브랜치는 그 밖을 못 건드린다 (CI 강제) |
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

## 편집 충돌 방지 (2026-08-05 추가)

동시 편집은 규칙이 아니라 **에디터 상태**로 깨진다. Cursor가 파일을 열어 두면
버퍼가 오래된 채로 저장되면서 다른 주체의 수정을 되돌린다. 실제로 발생했다.

UI/배포 작업을 시작하기 전에:

1. Cursor에서 `New for anti/app.js`, `style.css`, `index.html`, `data.js` 탭을 닫는다.
2. Cursor의 Agent/Composer가 이 레포를 대상으로 돌고 있으면 중지한다.
3. 가장 확실한 방법 — Cursor에서 이 폴더 자체를 닫는다 (File › Close Folder).

되돌아간 것 같으면 `git diff` 로 먼저 확인하고, 원인을 찾기 전에 다시 쓰지 않는다.
