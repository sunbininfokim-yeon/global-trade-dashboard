# TASKS — 현재 할 일 보드

Cursor가 주기적으로 재배치한다.  
각 터미널은 **자기 owner 행만** `status`/`note`를 갱신한다 (`claim.sh` 사용 권장).

상태: `ready` | `in_progress` | `blocked` | `review` | `done`

| id | task | owner | files / scope | branch | status | note |
|----|------|-------|---------------|--------|--------|------|
| T01 | UI 개선 마무리 | claude | `New for anti/app.js` 등 UI | `claude/ui-climate-generic` | **review** | PR #2 올림. `app.js` 로컬 WIP 해소됨 → **타 도구 UI 수정 잠금 해제**. 머지 전 실제 브라우저 육안 확인 1회 요망 |
| T02 | ops 문서·터미널 스크립트 정착 | cursor | `docs/ops/**`, `tools/ops/**` | `cursor/ops-bootstrap` 권장 | in_progress | 본 문서 세트 |
| T03 | 데이터 계약 재확인 (Codex 목표 공유) | codex | `DATA_LAYOUT.md`, `HANDOFF_PROMPT.md` 읽기 | — | ready | 코드 수정 전 필독. 좁은 국가 1개만 claim |
| T04 | (대기) 지역 모델 개선 — Cursor 담당 후보 | cursor | `scripts/yield_model/**` | `cursor/ml-…` | ready | **T01 done 후** 또는 UI와 파일 무겹침 확인 후 |
| T05 | 논문/사전 자료 검토 | anti | `docs/literature/**` + `~/Documents/기후 모델링` | `anti/lit-…` | ready | 코드 금지. Model_Config 요약만 |
| T06 | Claude UI 완료 후 코드 리뷰 루틴 | claude | PR diff | — | ready | Cursor PR도 Claude가 리뷰 |

## 백로그 (아직 id 없음)

- GitHub homepage / 커스텀 도메인 문서화 → `CLOUDFLARE.md`
- `icrisat_crop_production.json` (6MB) 공개 자산 부담 — Actions/CF 전략 재검토
- 인도·브라질 등 지역별 지시서(`~/Documents/기후 모델링/클로드_작업지시서`) ↔ 레포 스크립트 정합

## 갱신 규칙

1. 작업 시작: `status=in_progress`, branch 칸 채움  
2. 막히면: `blocked` + note에 이유  
3. 끝: `review` 또는 `done` + `./tools/ops/handoff.sh`  
4. done 행은 7일 후 “아카이브” 섹션으로 옮겨도 됨
