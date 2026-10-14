# 터미널별 시작 프롬프트 (복붙)

저장소 루트: `/Users/yeoninair/Documents/New for anti`  
(또는 clone한 `global-trade-dashboard`)

시작 전 공통:

```bash
cd "/Users/yeoninair/Documents/New for anti"
./tools/ops/status.sh
```

---

## 미국 선거 주별 조사 — 모든 도구 공통

아래 프롬프트의 `<STATE>`는 사용자가 지정한 주 또는 현행 순서의 미담당 주로 바꾼다. 경로·PR 번호는 실제 현재 상태를 확인해 채운다.

```text
이번 범위: <STATE> 한 주의 후보 명부·실제 여론조사·연방/주별 독립지출 조사.
먼저 현재 checkout의 AGENTS.md와 최신 origin/main의 docs/ops/US_ELECTION_STATE_INPUTS.md를 읽어.
git root/worktree/branch/WIP, 최신 main, 열린 PR, 다른 세션·수집 PID/잠금·Actions를 확인해.
같은 주 담당이 진행 중이면 중복 실행/동시 편집하지 마. 다른 세션의 checkout을 바꾸거나 WIP를 reset/stash하지 마.

한 주·한 전용 worktree·한 PR. 최신 main에서 독립 분기하고 미병합 주별 PR 위에 다음 주를 쌓지 마.
공용 기능이 필요하면 packet 없는 별도 기반 PR로 분리하고, 주별 PR은 같은 기반에서 각각 분기해 의존성을 명시해.
주별 변경은 config/state_evidence/2026/<STATE>.json과 해당 주 원문/감사/접근 자료·어댑터·테스트·인수 문서에 한정해.
전국 live/history/forecast/board/index, 공용 검토 목록·수집기·JS 테스트 fixture·TASKS.md·AGENTS.md·workflow/UI는 주별 PR에서 수정하지 마.
임시 공용 검토 변경은 freeze_state_inputs.py로 packet에 담고 복구해. 생성 JSON은 임시 public/data 사본에서 재생성하며 커밋하거나 텍스트 병합하지 마.

원래 수집일·영수증·문서 지문을 보존하고 신규 수집과 재생성을 구분해.
미등록 조사도 개별 원문/방법론으로 검토하되 미래 발표 전체를 승인하지 마.
7일 기본/14일 선택, 파동 중복 제거, 경선/본선·LV/RV·연방/주별 IE 구분을 유지해.
결측·보류·출처 장애를 0이나 승패로 바꾸지 마. 실패 시 마지막 유효 자료와 원래 날짜를 유지해.
새 API 키/유료 접근이 필요하면 해당 수집만 멈추고 사용자에게 요청해. 키를 기록하거나 재설정 기능을 클릭하지 마.

check_state_packet_changes.py를 실제 PR base SHA와 브랜치로 실행하고 polling·finance·JS·소유권·deploy-chain을 검증해.
자기 주 인수 문서에 checkout/branch/PR/base SHA/기반 의존성, 출처/원래 수집일, 보존 검사, 보류/장애, 다음 주 순서를 남겨.
병합·배포·production workflow 실행은 이번 조사에 포함하지 마. 다음 주는 사용자 지시/예약 범위에 맞게 이어가.
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
