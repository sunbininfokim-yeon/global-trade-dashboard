# 미국 선거 UI #271 데이터 후속

작업 브랜치: `codex/us-election-data-gaps` (main b75f6ac0 기준 별도 worktree).

상세: [데이터 인수 문서](../../New%20for%20anti/scripts/election_watch/HANDOFF_CLAUDE_ELECTION_DATA_GAPS.md).

CA 2026 주지사 Form 496 실자료 213항목 + 공식 경선 후보 61명, FEC 지역 코드 보정/감사 필드, 원본·UI 인덱스 역할 분리, 하원 공석 2석 및 근거 있는 경합 역사 5석을 준비했다. 주지사 48개 주와 전국 경합 역사 수집은 미완료다. 실제 UI는 주 독립지출 분류를 읽어야 하며 공석 자동화 실행/발행 스텝은 Claude 인수가 필요하다. 활성 workflow·UI·지도 경계는 수정하지 않았다.

기존 FEC API 비밀값은 소스·명령·산출물에 기록하지 않았다. 추가 API 키 없이 CA 공식 공개 ZIP을 사용했다.
