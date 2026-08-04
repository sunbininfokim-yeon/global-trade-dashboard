# CLAUDE.md — Claude Code

당신은 이 레포에서 **기본 코드 리뷰어**다.  
대형 UI·워커 구조 변경은 `docs/ops/TASKS.md` 에 **명시 claim** 했을 때만 구현 리드를 맡는다.

> 2026-08-04 이후: App/UI **기본 소유는 Cursor**.  
> 예전 “Claude = UI 영구 리드” 문구는 폐기. 정본은 `docs/ops/OWNERS.md`.

## 시작

```bash
cd "/Users/yeoninair/Documents/New for anti"   # 또는 clone 경로
./tools/ops/status.sh
```

읽고 따를 것: `docs/ops/README.md`, `OWNERS.md`, `TASKS.md`, `HANDOFF.md`.

## 소유

- **기본:** PR 리뷰, 품질·보안·계약(`DATA_LAYOUT`) 위반 지적
- **Claim 시:** `TASKS`에 배정된 UI/워커 티켓의 파일만 구현
- **금지:** claim 없이 Cursor가 잡고 있는 UI 파일 수정, `docs/ops` 구조 임의 개편, `cache/`·시크릿 커밋

## 데이터 계약

대시보드가 읽는 예측 JSON 규격은  
`New for anti/scripts/yield_model/DATA_LAYOUT.md`  
를 깨지 말 것. UI 리뷰 시 필드 정규화·`forecast_available: false` 처리를 확인.

## 브랜치

`claude/<주제>` · main 직접 push 금지 · 끝나면:

```bash
./tools/ops/handoff.sh claude "한 줄 요약과 남은 TODO"
```

## UI 작업 시

`TASKS.md` 해당 행을 `in_progress` + owner=claude 로 유지해 Cursor/Codex가 겹치지 않게 한다.  
작업 끝나면 `review`/`done` + handoff.
