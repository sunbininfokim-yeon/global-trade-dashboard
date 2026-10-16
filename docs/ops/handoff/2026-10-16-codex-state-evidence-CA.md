# CA-48 최신 조사 보류 원인과 특정 발표 검토

담당 Codex. 사용자 CA48/22 수치·합계 불일치 수정 및 검토 강화 요청. Worktree `/Users/yeoninair/Documents/해운 데이터/us-ca48-primary-review-20261016`, 브랜치 `codex/ca48-primary-review-20261016`, main/base `68089ef8`. CA packet·CA 전용 검사·이 문서만 변경. UI는 독립 #588. 공용 코드·목록·TASKS·workflow·전국 JSON 변경 없음.

## 원인 및 원문

main live as_of10/11, fetched_at `2026-10-11T00:16:19.749666+00:00`. 기존 CA48 DEM45/GOP42는 8/27~9/1이라 기간 밖. 그러나 10/15 실제 API 체크포인트의 `us-202sur70c7e750`는 의뢰기관 미검토로 보류됐다. 의뢰자 표기 차이를 기관 전체 허용으로 해결하지 않고 발표 하나를 검토했다.

https://results.surveyusa.com/client/PollReport.aspx?g=01471c0a-ab87-499e-8974-8526fea475d2 의 frameset에 명시된 main·left·methodology 세 문서를 10/15UTC(한국10/16)에 직접 요청했다. URL·SHA256·검토 시각은 packet에 기록.

- 조사10/1~7, 공식 발표10/8, API 기록10/9를 구분.
- 일반 후보 순서 회전 문항: Marni von Wilpert DEM47 / Jim Desmond GOP38 / 미정15. 미정층 재배분 없음.
- LV518; 성인685·RV589와 분리. Cint 비확률 패널47%, Aristotle 확률 기반 유권자 전화표본 SMS-to-web53%. 인구통계·CA48 정당 등록 비중 가중.
- KGTV-TV San Diego / San Diego Union-Tribune 의뢰. 과거 정확도·독립성을 추정 등급화하지 않음.
- credibility interval ±5.2는 sampling MOE·격차 유의성·당선확률로 바꾸지 않음.
- provider 전체 fingerprint·normalized fingerprint로 묶는다. 의뢰자·표본·URL·수치 변경은 보류, 새 ID는 승인 상속 없음.

CA22 Tulchin 6/15~21 DEM48/GOP44는 방법론 미확인·정파 의뢰/내부 참고 전용 유지. 이번 검색 범위에서 더 최신 원문을 확보하지 못했으며, 최신 조사가 전혀 없다는 뜻은 아니다. CA 전체 선거/금융 완결 조사 아님. FEC·주지사 IE 재수집 안 함. 새 키 불필요.

## 입력과 보존

신규 API 수집이 아니라 #557 검증에서 실제 확보한 10/15 체크포인트의 CA13개 provider 기록 재검토다. captured_at `2026-10-15T06:36:49.172887+00:00`, 전체 응답 지문·선택 레코드 지문·체크포인트 지문·source URL을 보존한다. 같은 체크포인트에서 실제 원문을 재확인한 기존 CA 주지사 PPIC2건·IVC1건의 원문 영수증도 보존했다. 이들을 빼면 누적 자료가 사라지므로 회귀 검사로 방지한다.

원래 `/private/tmp/us-poll-expansion-20261015/us-polls-capture.provider.json` 및 `us-polls-capture.json`; 재생성/검사/원문은 `/private/tmp/ca-poll-summary-20261016/`. 전국 생성물 커밋 없음.

## 결과와 운영 경계

실제 UI 함수에10/16 현재 기간 적용: CA48 7일 없음 / 14일 DEM 수치상 우세, CA22 두 기간 없음. 단일 기관·유의성 미판정. 전국 기준일10/11을 재생성으로 최신 날짜로 바꾸지 않으므로 현재 전망으로 복구하려면 정상 전국 capture/validation/publication이 필요하다. #557 병합은 확인했지만 이후 main 게시 성공 run은 이번 작업에서 아직 관측하지 못했고 직접 실행하지 않았다. 공개 자산 요청403이므로 배포 자산 동일성 미확인.

다른 주 race/history/원래 날짜·house_poll_focus104석 및 기존 CA 누적 자료 보존을 검사한다. 표본/의뢰자/URL 변경과 미래 발표 승인 상속도 검사한다. 검사 결과는 아래와 PR에 기록.

병합·배포·main workflow 실행·재설정 안 함. 다음 주 자동 시작 안 함.

검증: polling 520개, finance 68개, 선거 JS74개, ops/소유권 단위14개 통과. deploy-chain39개 workflow 연결 통과. 실제 UI 함수 7일/14일·낡은 전국 기준일 보존 검사 통과. 첫 로컬 시도는 sparse fixture 누락과 잘못된 시스템 Python 경로로 실패했으며 현행 HEAD의 작은 JSON 복원 및 번들 Python3.12로 재검증했다. 전체 지도 복원은 디스크 부족으로 중단하고 이번 작업에서 만든 지도 사본만 제거했다. 광범위 재복원은 자동 승인 검토가 용량 위험으로 거절해 실행하지 않았다.
