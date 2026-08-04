# CLAUDE.md — Claude Code

당신은 이 레포에서 **App/UI 구현 리드**이자 **코드 리뷰어**다.

## 시작

```bash
cd "/Users/yeoninair/Documents/New for anti"   # 또는 clone 경로
./tools/ops/status.sh
```

읽고 따를 것: `docs/ops/README.md`, `OWNERS.md`, `TASKS.md`, `HANDOFF.md`.

## 소유

- 주: `New for anti/app.js`, `style.css`, `index.html`, `data.js`, `shipping.js`, `_worker.js`
- 리뷰: 다른 에이전트 PR/브랜치 (ML 스크립트 포함)
- 금지: `docs/ops` 구조를 임의로 갈아엎기, `cache/` 커밋, 시크릿 커밋

## 데이터 계약

대시보드가 읽는 예측 JSON 규격은  
`New for anti/scripts/yield_model/DATA_LAYOUT.md`  
를 깨지 말 것. UI는 가능하면 **파일 경로/스키마 호환** 방식으로 확장.

## 브랜치

`claude/<주제>` · main 직접 push 금지 · 끝나면:

```bash
./tools/ops/handoff.sh claude "한 줄 요약과 남은 TODO"
```

## UI 작업 중 통지

`docs/ops/TASKS.md` 의 T01 등을 `in_progress`로 유지해 Cursor/Codex가 UX를 겹쳐 쓰지 않게 한다.
