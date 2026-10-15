# CA-48·CA-22 누적 카드와 최근 우세 합계 설명

- 담당: Codex, 사용자 2026-10-16 진행·검토 강화 요청.
- Worktree: `/Users/yeoninair/Documents/해운 데이터/us-poll-count-explanations-20261016`
- 브랜치: `codex/poll-count-explanations-20261016`, 시작 main `68089ef8`.
- UI 전용 독립 PR. 수집·적격·숫자·전국 JSON·workflow·Worker·공용 스타일 변경 없음. CA 새 원문 검토는 별도 주별 PR.

## 원인과 동작

main 보유 JSON 기준일은 2026-10-11. CA-48 SurveyUSA 8/27~9/1 DEM45/GOP42는 7일·14일 밖이다. CA-22 Tulchin 6/15~6/21 DEM48/GOP44는 기간 밖이며 방법론 미확인·정파 의뢰/내부 참고 전용이다. 보유 카드의 수치상 선두와 최근 적격 합계를 혼동하기 쉬웠다.

합계를 만드는 `pollRaceAssessment`를 그대로 재사용해 각 카드에 최근 7일/14일 상태, 집계 날짜, 누적 자료 최신 종료일, 기간 밖·참고 제외 이유를 표시한다. 갱신 지연일 때 원래 수집 당시 요약임을 밝힌다. 최신 자료 제목은 보유 자료임을 명확히 한다. 상위 칩에도 선택한 7일/14일을 명시한다.

새 CA-48 10/1~7 DEM47/GOP38, LV518 발표가 10/15 API 체크포인트에 있으나 의뢰기관 미검토로 보류된 점은 별도 CA 원문 검토 입력에서 처리한다. 이 UI PR만으로 새 조사가 편입되지는 않는다. CA-22 신규 조사 발견 여부를 이 PR이 보장하지 않는다.

## 검증

- 선거 JS 77개 통과. 고정된 사건 재현, 7일 제외/14일 포함 전환, 확인된 sampling MOE 중첩 회귀 포함.
- ops/소유권 단위 검사 14개와 deploy-chain 39개 검사 통과.
- 실제 수정 모듈과 main CSS·보유 JSON의 CA48/22를 사용하는 로컬 preview에서 7일/14일 변경 및 제외 설명 확인.
- 390px viewport: 문서 너비 375px, 가로 넘침 없음. viewport 복원 완료.
- 로컬 증거: `/private/tmp/ca-poll-summary-20261016/summary-desktop.png`, 검사 로그 같은 디렉터리.
- 공개 사이트 JSON 직접 요청은 403이어서 현재 배포 파일과 동일하다는 주장은 하지 않는다. main 자료와 로컬 변경 검증이다.

병합·배포·main 수집 실행 안 함. UI와 CA 데이터 PR은 각각 main 기반 독립 검토 가능.
