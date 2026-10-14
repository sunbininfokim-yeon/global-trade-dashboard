# 위원회·메일링과 정책 JS 검사 점검 — 2026-10-11

선거 PR과 분리한 테스트 전용 수정이다. 운영 코드·워크플로·DB·발송·배포는 바꾸지 않는다.

위원회·메일링 테스트는 PGlite가 설치되지 않은 환경에서 모듈 로드 단계에 실패했다. 저장소 `services/mailing/package.json`의 `@electric-sql/pglite` 0.5.8을 임시 폴더에 설치하고 작업공간의 로컬 모듈 경로를 연결하니 관련68검사가 통과했다. 커밋에는 패키지 설치물이나 심볼릭 링크를 넣지 않는다.

정책 `scripts/lib` 전체 검사도 추가 실행했다. main 기준 145개 중143통과/2실패였다. 두 실패는 같은 `congress-status-history.test.cjs`의 VM fixture가 현재 `saveBundle`에서 호출하는 `prepareEmbedding`을 주입하지 않아 발생했다. 해당 함수는 운영 모듈에서 정상 정의·export돼 있다. 제품 수집기가 함수 미정의로 고장났다는 증거가 아니다.

실제 export된 함수를 테스트 VM에 주입하고 실제 row 구조의 title/summary/raw_source를 fixture에 제공했다. 임시 no-op이나 실패 무시로 우회하지 않았고, 기존 공식 action 저장·동일일 상태 변화·중간 실패 후 이력 복구 assertions는 유지한다. 수정 후 정책 JS 전체145개 통과, 위원회·메일링 관련68검사도 별도로 통과했다. 네트워크 API나 운영 DB/실제 메일은 호출하지 않았다.

이 수정은 선거 기반 #524 및 AK/KS #525/#526과 독립이다. #496 원자재 workflow 수정은 이번 범위에 포함하지 않는다. 병합·배포 없음.
