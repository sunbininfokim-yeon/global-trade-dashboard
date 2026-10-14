# FL 주지사 강제 양자·당파 표기 참고 조사

- 최근 보류 원문 검토의 FL만 독립 입력이다. checkout `/Users/yeoninair/Documents/해운 데이터/us-fl-poll-input-20261014`, branch `codex/fl-evidence-20261014`, 실제 base main `7291079a` (#554/#555 포함). 다른 주 PR 위에 쌓지 않으며 공용 코드/목록·전국 생성물·TASKS·UI·workflow는 변경하지 않는다.
- API 실제 캡처 `2026-10-14T05:14:02.840821+00:00`의 FL64행을 보관한다. `gov202chaea67d341`만 정확한 원문 수치/표본/메타데이터 지문을 검토해 참고 자료로 편입한다. 금융 금액이나 과거 공시 날짜는 바꾸지 않는다.
- [Change Research 원문](https://changeresearch.com/research/2026/2026-10-12-florida-aapor-methodology-statement):10/8–10, 발표10/12, Freedom Project USA 의뢰. RV1106 중 투표 동기8–10의 LV920. 온라인 광고/유권자 파일 SMS, SurveyMonkey, English, post-stratification은 연령·성별·인종·교육·2024투표·media market이다. 주지사 양자 ticket 문항은 미정 응답자 후속 forced choice를 포함하며 Jolly/Graham47·Donalds/Avila47이다.
- 원문 전체 조사 modeled error3.1pp를 LV 문항 sampling MOE로 바꾸지 않는다. API의 partisan DEM flag와 의뢰자 명칭은 그대로 보존하되 의뢰자의 정당 소속을 독립 검증했다고 표시하지 않는다. 강제 양자/당파 참고로 분리하므로7일/14일 우세 기관 수·지도/의석 신호에 투표하지 않는다. 정확도 등급도 미평가다.
- 원문 페이지는 브라우저에서 재확인했다. direct HTTP는 HTML 및 실제 연결된 `/uploads/2026/10/Florida-October-2026-Crosstabs.pdf` 모두403으로 문서 byte hash는 미확보다. 이를 자동 원문 다운로드 성공이나 AAPOR 인증으로 바꾸지 않는다. API 키/유료 계정 부족으로 확인된 장애가 아니므로 새 키를 요구하지 않는다. 정확한 API 레코드/수치 hash와 수기 원문 검토일을 보존하며 기관의 다른 미래 발표를 자동 승인하지 않는다.
- 계약3개는 참고 표시/우세 미편입·변경 표본/후속 레코드 보류·타주 race/누적 이력/날짜/focus 보존을 검사한다. 전체 polling/CI 결과는 PR에 기록한다. main 병합·production dispatch·배포 없음. #557 공용 수집 안정성과 함께 독립 검토한다.
