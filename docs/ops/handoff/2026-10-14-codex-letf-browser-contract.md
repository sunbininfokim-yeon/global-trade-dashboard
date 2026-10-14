# 2026-10-14 — Codex: 해외 LETF 브라우저 기대값 수정

- 사용자 지적: #480 validate가 `tests/overseas-letf/browser.test.cjs`의 `/선물/` 기대값에서 실패.
- 기준 main: `9d7e79d194d0143ad54c9c0b8050c22393d01c85`. 브랜치 `codex/letf-browser-contract`, 독립 sparse worktree `letf-browser-contract-20261014` (디스크 부족으로 전체 checkout 대신 필요한 파일만 펼침).
- #480은 작황상태 수집 PR이며 이미 병합됨. 실패 job: https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/37706806373/job/113082993005 . 실패는 작황 코드가 아닌 공통 해외 LETF validate의 브라우저 검사에서 발생.
- 앞선 #456도 같은 삼성전자 기대값을 고쳤지만 2026-10-06 병합 없이 닫혔고 최신 main에는 원래 기대값이 남아 있었음. #456을 재개하거나 다른 세션의 브랜치를 편집하지 않고 최신 main에서 후속 수정.
- 실제 커밋된 `XS3388190301` 상품 구조는 `physical_margin`, 화면은 `현물·차입`. 수정 전 실제 Chromium에서 `/선물/` 실패 재현.
- 수정: 선택된 상품 ID·이름과 바로 뒤 구조 설명을 검증. 삼성전자 `physical_margin` → `구조 현물·차입`, TQQQ `derivatives_and_collateral` → `구조 파생·담보`. 다른 상품 행에 같은 문구가 있는 것만으로 통과하지 못하도록 상세 섹션에 한정.
- 보존된 검사: 15상품/1,106개 이력 gzip 읽기, ADR 이력 부족 안내, 원시 구조 enum 비노출, 차트 3개 이상, 736/360px 가로 넘침 없음, 이미 압축 해제된 HTTP JSONL 읽기, JS 오류 없음.
- 검증: 실제 Chromium 브라우저 검사 전체 통과, Node 문법 검사 통과, 해외 데이터 계약 Python 16개 통과, diff whitespace 통과.
- 변경 범위: 테스트 파일과 이 인수 문서만. 운영 UI·상품/시세 데이터·수집기·workflow 편집 및 수집 dispatch 없음.
- 인수 시점: 로컬 검증 후 후속 PR 준비. 병합/배포/자동 수집 복구는 미확인이며 PR validate 통과와 운영 갱신 성공을 구분할 것.
