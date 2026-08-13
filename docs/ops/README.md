# 멀티 에이전트 운영 가이드 (터미널 → GitHub → Cloudflare)

이 저장소는 **Claude Code · Codex · Antigravity · Cursor**가 동시에 쓰입니다.
통합은 API 연동이 아니라 **GitHub + 이 문서 묶음 + `tools/ops` 스크립트**로 합니다.

## 한 줄 요약

1. 작업 전에 `./tools/ops/status.sh` 실행  
2. 자기 역할/`OWNERS.md` 범위만 수정  
3. 끝나면 `./tools/ops/handoff.sh`로 기록 후 **브랜치 push → PR → main 머지**  
4. main 머지/Actions 배포가 Cloudflare에 반영 (`PIPELINE.md`)

## 읽을 순서 (모든 터미널 공통)

| 순서 | 파일 | 내용 |
|------|------|------|
| 1 | [`GOAL.md`](./GOAL.md) | 프로젝트 목표·성공 기준 |
| 2 | [`OWNERS.md`](./OWNERS.md) | 역할·폴더 소유권 (충돌 방지) |
| 3 | [`TASKS.md`](./TASKS.md) | 현재 할 일 보드 |
| 4 | [`PIPELINE.md`](./PIPELINE.md) | GitHub Actions · Cloudflare 데이터 흐름 |
| 4b | [`DATA_CADENCE.md`](./DATA_CADENCE.md) | API·속보·기상·위성 폴링 주기 / 저장 / 학습 전략 |
| 5 | [`handoff/`](./handoff/) | 인수인계 — **에이전트별 파일**. 공유 파일 금지 (README 참조) |
| 6 | [`START_PROMPTS.md`](./START_PROMPTS.md) | 터미널별 시작 프롬프트 복붙 |

데이터 스키마(예측 JSON 등)는 이 문서가 아니라  
`New for anti/scripts/yield_model/DATA_LAYOUT.md` 가 정본입니다.

## 도구별 역할 (2026-08-04 이후 합의)

| 도구 | 역할 | 기본 브랜치 접두 |
|------|------|------------------|
| **Cursor** | 오케스트레이션, **제품/프론트·워커 기본 소유**, ML·ops 문서 | `cursor/` |
| **Claude Code** | **코드 리뷰 기본**, `TASKS` claim 시 대형 UI/아키텍처 | `claude/` |
| **Codex** | `DATA_LAYOUT`·`HANDOFF_PROMPT` 범위의 **좁은** 모델/데이터 작업 | `codex/` |
| **Antigravity** | 사전 자료·논문 검토 → `docs/literature/` 요약만 | `anti/` |

경로 단위 상세·claim 우선규칙은 [`OWNERS.md`](./OWNERS.md).

## 절대 규칙

1. **main에 직접 push 금지** (긴급 hotfix 제외, 사람 승인 후).
2. 다른 도구의 **소유 폴더/WIP 파일**을 무단 수정하지 않음 (`OWNERS.md`).
3. **API 키·토큰을 커밋하지 않음** — GitHub Secrets / 로컬 `.env`만.
4. 원본 API 캐시(`scripts/yield_model/cache/`)는 커밋하지 않음 — 학습 테이블·모델 JSON·`public/data/*_forecast.json`만.
5. UI를 누가 잡고 있으면 (`TASKS.md` 의 `blocked`/`in_progress`) Cursor·Codex는 그 파일을 건드리지 않음.
6. 작업 브랜치에 커밋한 뒤 **main만 push하면 배포가 안 됨** — 이미 두 번 겪은 실수. 반드시 작업 브랜치를 push하고 PR로 합친다.

## 터미널에서 바로 실행

저장소 루트 (`New for anti/` 가 아니라 **git root** = 이 폴더)에서:

```bash
# 상태 한눈에
./tools/ops/status.sh

# 작업 시작 (브랜치 생성 + TASKS 갱신 안내)
./tools/ops/claim.sh claude T01 "ui polish remaining"

# 작업 종료 기록
./tools/ops/handoff.sh claude "UI 중간 저장: 차트 라벨 수정 완료, 다크모드 미완"

# main 최신 받기 (로컬 WIP 있으면 중단됨 — 안전)
./tools/ops/sync-main.sh
```

## Cloudflare 사이트 주소

코드에 이미 쓰이는 Worker 주소:

- `https://global-trade-dashboard.sunbin-info-kim.workers.dev`

**커스텀 도메인**이 있으면 `CLOUDFLARE.md`에 적어 주세요.  
없어도 운영 문서·스크립트는 동작합니다. 배포/KV/Actions 디버깅 때 있으면 더 편합니다.
