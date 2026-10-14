# 미국 선거 조사 세션 공통 규칙 — 2026-10-11

사용자 요청: 매번 발생하는 충돌을 반영해 이후 주별 조사에 규칙을 적용하고 다른 조사 세션에도 전달한다.

## 현재 작업과 의존성

- checkout: `/Users/yeoninair/Documents/해운 데이터/us-nh-state-evidence-20261009`
- branch: `codex/election-research-rules-20261011`
- 확인한 main: `82c29fe32f8ec5bd433da33ed811869bb278e86a`
- PR base: 공용 기반 #524, `codex/election-b-foundation-20261011`, `32fa4760ded80b83ed93c80d8d627c3231a9e92d`. 시작 base는 `96d2de79`이며 독립 검토 후 공용 JS 날짜 fixture를 기반으로 이관했다.
- #518은 main에 병합됨. #524·AK #525·KS #526은 확인 당시 OPEN/미병합이다. 이 규칙 PR도 #524를 기반으로 하며 주별 PR 위에 쌓지 않는다. #524 반영 후 main으로 base를 변경해 검증한다.
- NE 중지·미커밋 자료 보존을 유지한다. 이번에 신규 주 조사·API 수집·전국 JSON 생성/커밋·main 병합·배포·production dispatch는 하지 않았다.

## 재발 경로와 변경

기존 #518이 주별 packet을 분리했지만, 검사 대상이 packet/특정 Codex 브랜치에 치우쳐 있었다. 원문·공시 감사 자료만 수정하는 PR은 검사에서 빠질 수 있었고, polling workflow의 PR paths에도 빠져 있었다. 다른 주의 명명된 테스트/어댑터/인수 문서 혼입 및 미병합 주별 PR base도 검사하지 않았다. 오래된 대화/checkout 지시로 같은 스택을 다시 통합할 위험도 있었다.

- AGENTS·CLAUDE·선거 입력 가이드·도구 공통 시작 프롬프트에 최신 main/PR/세션/PID/잠금 확인, 한 주·전용 worktree·독립 PR, 공용 코드 별도 기반 PR, 원래 수집일/영수증 보존, 담당/의존성/다음 주 인수 항목을 명시했다.
- source-only 연구도 state-owned 검토/감사/접근 경로로 식별하며 임의 브랜치 이름에서도 검사한다. 공용 config/전국 public data·다른 주 입력/명명된 테스트/어댑터/인수 문서·공용 규칙·workflow/선거 UI 동반 변경을 차단한다.
- 실제 Git base를 origin/main과 비교한다. 미병합 주별 입력이 든 base는 거절하고, 주별 검토 입력이 없는 공용 기반은 허용한다. 같은 주의 새 main 검토와 충돌하면 기존 before-hash 계약에 따라 보류한다.
- 이미 병합된 #518의 일회성 다주 통합 브랜치 우회는 종료했다.
- 기존 polling workflow에 7개 원문/감사/접근 경로의 PR 검증 trigger만 추가했다. 일일 주기·수집/게시 job·deploy.yml은 바꾸지 않았다. 이 규칙 브랜치의 소유권 예외는 그 polling workflow 한 파일뿐이며 접미사/다른 workflow/UI는 허용하지 않는다.

## 검증

- 공용 기반 #524 적용 후 polling 420개, finance 68개, 선거 JS 51개, ops/소유권 11개 통과. deploy-chain 39개 연결 통과.
- 최종 검사 변경의 회귀는 `test_poll_state*.py`로 추가 검증한다. source-only PR trigger 일치, 타주 혼입, legacy branch 우회 차단, 실제 임시 Git 저장소의 main/공용 기반/주별 스택 구분을 검사한다.
- 새 검사로 기존 AK #525·KS #526의 실제 diff/base 범위도 각각 통과했다. 이것은 해당 PR의 새 데이터 수집이나 전체 재검증을 뜻하지 않는다.
- 최초 main 기반 polling 검사에서는 IA/NH fixture 날짜 오류 2개가 재현됐다. 이미 #524에 있는 수정과 중복 편집하지 않고 공통 기반을 사용해 해결했다.
- 최종 GitHub 검사 링크와 타 세션 실제 전달 결과는 이 PR 본문에 기록한다.

## 세션 전달

현재 다른 선거 세션 `슈퍼팩 선거 분석 파이프라인 구축 (2)` (`01a11ee3-df39-77d2-a1d0-5201c358636e`)가 idle이고, 마지막 작업 요약에는 옛 A 스택 통합을 재개하려던 내용이 남아 있었다. 이 세션에는 사용자 요청에 따라 새 규칙과 #518/#524/#525/#526의 현재 상태, NE 중지, 중복 통합/수집 금지를 전달한다. 메시지는 규칙 동기화용이며 새 주 조사나 배포를 시작하라는 지시가 아니다.

Claude 등 외부 도구는 이 앱의 메시지 도구로 직접 수신 여부를 확인할 수 없다. 저장소의 CLAUDE.md·AGENTS.md 및 `docs/ops/START_PROMPTS.md`의 공통 프롬프트를 사용한다. PR이 병합되기 전에는 이 브랜치의 가이드를 읽고, 그 뒤에는 최신 main을 읽는다. 타 세션 checkout 파일을 직접 덮어쓰지 않는다.

## 남은 적용 단계

사용자/통합 담당이 #524와 이 PR의 순서를 확정해 main에 반영해야 새 CI 범위 검사가 전체 저장소에 적용된다. 독립 AK/KS 입력 PR은 공통 기반 의존성을 유지하며 서로 위에 쌓지 않는다. 동일 주·동일 공용 코드의 동시 변경은 담당 조율이 필요하다. 파일 분리는 모든 종류의 충돌을 없앤다는 보장이 아니다.

## 독립 검토 보완

다른 선거 세션이 #529에서 공용 Python fixture/helper/test와 공용 JS test를 주별 packet과 함께 바꿔도 검사에서 빠지는 것을 지적했다. 해당 주 이름의 Python test만 허용하고 공용 Python 테스트 자산 및 선거 JS 테스트는 별도 기반 PR로 분리하도록 차단·회귀 검사를 추가했다. 기존 AK #525의 공용 JS 날짜 fixture 변경도 공용 기반 #524로 이동해 같은 규칙을 적용한다.

이관 후 AK head `c68e8721`의 전체 파일 트리는 종전 `abbdf8c5`와 동일하며 변경된 것은 기반 ancestry뿐이다. #524 대비 AK PR diff에는 이제 공용 JS 테스트가 없다. 새 범위 검사로 AK/KS 모두 통과했고, 공용 fixture의 JS 51개 및 최종 범위 회귀 10개가 통과했다.

`us_superpac_refresh.yml`과 `elections_eop_monthly.yml`의 별도 concurrency 및 공용 board 게시의 `git pull --rebase --autostash` 사용을 원문에서 재확인했다. polling 게시기만 안전 재생성 방식이므로 자동 게시 전체 충돌 해결이라고 표현하지 않는다. 두 workflow 보강은 해당 소유자의 별도 후속 범위이며 이번에 수정/dispatch/배포하지 않는다.
