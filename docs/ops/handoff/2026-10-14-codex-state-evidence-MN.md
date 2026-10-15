# MN-01 신규 SurveyUSA 발표 입력

- 최근 보류 원문 검토를 MN만 독립 입력 PR로 분리한다. checkout `/Users/yeoninair/Documents/해운 데이터/us-mn-poll-input-20261014`, branch `codex/mn-evidence-20261014`, 2026-10-15 재검증 base: packet-free 공용 #557 `687b8da2` (최신 main `57941ec0` 포함). 다른 주 PR 위에 쌓지 않으며 전국 산출물·공용 코드/목록·TASKS·UI·workflow diff가 없다.
- 실제 API 체크포인트 `2026-10-14T05:14:02.840821+00:00`의 MN28행. SurveyUSA #28043 [발표](https://results.surveyusa.com/client/PollReport.aspx?g=3605b38b-d541-4db4-9d70-f6d4875faeb8)는10/4–9, 발표10/12, KAAL-TV 의뢰 Q7 LV/이미 투표자565명: Jake Johnson46 / Brad Finstad44. 성인725·RV664와 구분했다.
- 표본은49% Cint 비확률 panel,24% Aristotle landline IVR,27% Aristotle SMS-to-web. Census gender/age/ethnicity/homeownership 가중. 발표 credibility interval4.6pp를 sampling MOE/격차 유의성으로 바꾸지 않는다. frameset뿐 아니라 main/left/methodology 원문을 내려받고 URL/SHA256을 packet에 보존했다.
- 기존 명부 `Jacob "Jake" Johnson`에 정확한 조사 별칭 `Jake Johnson`을 추가했다. 정당/지역구/명부의 법적 이름을 바꾸거나 FEC 이름 fuzzy match를 하지 않는다. 공식 ballot 완결이나 당선 인증으로 승격하지 않는다.
- 정확한 `us-202sur83d49b6b`의 메타데이터·답변·표본·수집 지문만 검토한다. 새 파동이나 변경된 sample을 자동 승인하지 않는다. source quality는 원문 대조이며 정확도 등급은 미평가다.
- 재생성은 원래 캡처로 실시하며 타주 race/이력/날짜와 타주 house_poll_focus를 보존한다. MN 관심 지역구 항목은 새 관측 기준으로 재계산한다. 새 금융 금액을 수집하거나 기존 금융 시각을 바꾸지 않는다.
- MN 계약3개와 전체 polling/CI 결과는 PR에 기록한다. #554는 이미 main에 포함됐다. #557의 main NC 날짜 검사 복구를 먼저 반영하고, 그 뒤 이 MN 입력을 독립 반영한다. #557 병합 후 PR base를 main으로 맞춘다. 병합·production dispatch·배포 없음. 다음 주 자동 시작 없음.

- 10/15 통합 재검증: native pending/projection 성공, polling504·finance68·선거 JS74·deploy-chain39 통과. 주별/전국 날짜·타주 이력·타주 house_poll_focus 보존은 MN3개 계약 검사가 확인한다. MN을 넣었을 때의 WA 과거 fixture/현행 명부 날짜 충돌은 공용 #557에서 수정했고 이 주별 PR에 공용 수정을 포함하지 않는다. 새 API 수집은 추가하지 않았으며 원래10/14 수집일을 보존한다.
