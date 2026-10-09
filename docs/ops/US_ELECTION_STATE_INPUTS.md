# 미국 선거 주별 입력과 전국 게시 규칙

2026-10-10 사용자 요청: 주별 증거 스택과 일일 수집의 반복 충돌을 구조적으로 방지한다.

## 소유 단위

- 주별 PR: `New for anti/scripts/election_watch/config/state_evidence/2026/<STATE>.json`, 해당 주의 원문 검토·공시 접근/감사 자료·독립 수집 어댑터·테스트·주별 인수 문서.
- 기반 PR: 공용 수집기, 원문 허용 경로, 스키마, workflow. 주별 PR에 공용 코드 보강이 필요하면 먼저 별도 기반 PR을 준비한다.
- 전국 산출물: main의 기존 polling workflow가 게시한다. 주별 PR에 live/history/forecast/board/index/공용 상태 JSON이나 공용 검토 목록을 커밋하지 않는다.
- `TASKS.md`에는 플랫폼 작업 한 행만 둔다. 개별 주 진행 기록은 주별 인수 문서에 둔다.

`check_state_packet_changes.py`가 주별 입력 또는 주별 evidence 브랜치와 공용 파일 변경의 동반을 차단한다. 기반 통합 예외는 정확한 브랜치 `codex/election-state-integration-20261010` 하나다. workflow 소유권 예외도 기존 polling workflow 하나뿐이다. deploy.yml은 변경하지 않는다.

## 주별 작업 절차

최신 main에서 시작하고 선행 작업·수집 PID·잠금을 확인한다. 다른 주의 미병합 PR을 새 주의 기반으로 쌓지 않는다.

1. 공식 후보 명부·실제 조사 원문·방법론·주별 공시를 검토한다. 임시 공용 검토 목록을 수정했다면 선택한 주만 수정한다.
2. `New for anti/scripts/election_watch`에서 실제 수집을 입력으로 저장한다.

   ```sh
   python3 refresh_state_polls.py --state CT --packet
   python3 freeze_state_inputs.py --state CT --base-ref HEAD
   ```

   두 번째 명령은 검토된 주별 변경을 입력에 담고 임시 공용 목록을 복구한다. 다른 주·공통 설정 변경이나 기존 입력의 중복 수정은 보류한다. 이미 분리된 주의 재검토는 그 주 입력의 기존 operation과 기준 해시를 명시적으로 갱신하고 검증한다.
3. 입력에는 원래 수집 영수증, 원래 시간, 해당 주 API 원자료, 검토한 원문 보완 자료, 검토 목록 변경과 변경 전 해시를 담는다. 원자료는 공개된 조사 집계이며 응답자 개인 자료가 아니다. 키를 담지 않는다.
4. 검증용 public/data 사본에서 재생성한다. finance index와 지도 등 원래 public/data 의존 파일도 사본에서 참조할 수 있어야 한다.

   ```sh
   python3 publish_state_packets.py --states CT --public /tmp/election-preview/data
   python3 publish_packet_projections.py --public /tmp/election-preview/data
   ```

   이는 원래 입력의 재검증·재생성이며 신규 수집이 아니다. 실제 요청은 2번에서 수행한다. 생성 결과는 PR에 커밋하지 않는다.
5. polling·finance·JS·소유권·deploy-chain 검사를 실행하고 주별 인수 문서에 출처, 기준일, 보류, 자료 부족을 기록한다. PR diff에 공용 생성물이나 공용 목록이 없는지 확인한다.

## 검토 목록 로딩

`election_watch.polls.read`는 공용 원본 목록 위에 주별 operation을 적용한다. 기존 JSON 구조와 UI 계약은 유지한다. 후보/공시/board 생성 경로도 이 로더를 사용한다.

같은 주의 변경 전 값이 main에서 달라졌으면 자동 덮어쓰지 않는다. 이미 같은 변경이 적용됐다면 재적용하지 않는다. 다른 주의 입력은 서로 다른 파일·키를 사용한다. 원문 지문·후보·표본·중복 판정은 기존 검증 규칙을 그대로 통과해야 한다.

## main 자동 수집과 게시

기존 일일 06:10 KST polling workflow의 식별자와 배포 연결을 유지한다. PR 검증에서는 네트워크 없이 미반영 입력을 재생성해 테스트한다. 검증 작업에서 생성한 JSON은 게시하지 않는다.

main 수집은 최신 검토 목록과 공개 API·원문으로 정상 실행한다. 성공한 전국 재생성에만 기존 주별 수집 영수증을 가져오고, 원래 수집일은 보존한다. 이전 입력을 수집 전에 공개 산출물에 덮어쓰지 않으므로 API 실패가 더 오래된 주별 자료로의 후퇴를 만들지 않는다. 최신 수집·원문 접근 실패는 기존 마지막 유효 자료와 상태 계약을 따른다.

게시 충돌 시 수집 입력과 원문 확인 영수증을 runner 임시 체크포인트로 보존한다. 최신 main을 가져와 같은 입력을 현재 코드·검토 목록으로 재검증하고 산출물을 다시 만든다. 새 수집 시각을 만들지 않는다. 더 최신 전국 수집이 이미 게시됐다면 오래된 재시도를 보류한다. 세 번 실패하면 실패를 표시하며 artifact를 보존한다. 생성 JSON을 git rebase/merge로 합치지 않는다. 체크아웃 초기화는 main Actions의 일회성 작업 공간에서만 실행한다.

workflow 직접 실행, main 병합, 배포는 사용자 결정이다. 다른 월별 EOP/선거자금 workflow의 과거 게시 절차까지 이번 예외로 변경하지 않는다. 그 작성자들이 동시에 board를 쓰더라도 polling 게시 측은 최신 main에서 다시 생성하며, 다른 workflow 자체의 재시도 방식 보강은 해당 소유자가 별도로 처리한다.

## 기존 스택 처리

A줄 #507 CT → #510 AL → #511 NJ → #513 NM → #514 NH를 새 main 위의 기반 통합 PR 하나로 대체한다. 원래 주별 원문·공시 감사 자료와 수집 영수증을 보존한다.

B줄 #508 AK → #512 KS는 A 통합이 main에 들어간 뒤 그 main에서 시작한다. AK/KS 검토 입력을 같은 계약으로 분리하고 공용 코드의 필요한 보강만 별도 검토한다. 기존 B 생성 JSON을 A 또는 main에 텍스트 병합하지 않는다. 사용자가 멈춘 NE는 재개하지 않는다.
