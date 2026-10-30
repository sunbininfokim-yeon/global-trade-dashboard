# NC 신규 SurveyUSA 발표의 주별 검토 입력

- 사용자 10/14 자동수집 문제→보류 원문 검토→ME 순서 재진행의 최근 발표 검토분이다. ME PR과 공용 수집 수정에 섞지 않고 NC만 독립 분리했다.
- checkout `/Users/yeoninair/Documents/해운 데이터/us-nc-poll-input-20261014`, branch `codex/nc-evidence-20261014`, base packet 없는 #554 `fbe255ba`. 기존 main 규칙과 같은 주 열린 PR을 먼저 확인했다.
- 실제 API 캡처 `2026-10-14T05:14:02.840821+00:00`의 NC41행을 입력에 보관한다. 과거 원문 보완 기록은 공용 기본 입력에서 유지한다. 재생성은 신규 수집이 아니다.
- SurveyUSA #28047은 10/7–11, 발표10/13, Q3 LV643의 Cooper54/Whatley40이다. 성인900·RV778과 구분했다. WRAL-TV/WSOC-TV 의뢰, Lucid 비확률 온라인 패널, ACS+NC 정당 등록 가중을 대조했다. 발표 credibility interval5pp를 sampling MOE나 후보 격차 유의성으로 변환하지 않았다.
- [발표](https://results.surveyusa.com/client/PollReport.aspx?g=0a876c84-9a95-4995-9218-82b1015f5d77)는 frameset이므로 실제 main/left/methodology 문서까지 저장·대조했다. 각 URL/SHA256은 packet의 정확한 review operation에 있다. `us-202surbcf9e1be`의 provider 메타데이터/수치 지문을 모두 결합한다. 수정된 표본이나 후속 파동을 자동 승인하지 않는다. 기관 정확도 등급은 미평가다.
- capture 영수증·전국 날짜·타주 race/누적 이력과 타주 house_poll_focus를 보존하고 NC focus는 새 관측 시각으로 재계산한다. 전국 live/history/board/index/공용 목록·코드·TASKS·workflow·UI를 커밋하지 않는다. 금융은 기존 경로를 유지하며 이 PR에서 새 FEC/주지사 IE 금액을 조회하지 않는다.
- NC 최근 발표 계약3개 및 polling/CI 결과는 PR에 기록한다. 공용 검증은 #554/#557 결과를 참조한다. main 병합·production dispatch·배포 없음. #554 기반 뒤 이 PR은 다른 주 PR들과 독립 반영한다. 다음 주 자동 시작 없음.
