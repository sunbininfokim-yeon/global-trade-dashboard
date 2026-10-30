# Montana — 공식 연방 명부·실제 원문 여론조사·FEC 감사 보강

담당 MT(C그룹) 한 주. Worktree `/Users/yeoninair/Documents/해운 데이터/us-mt-evidence-input-20261016`, branch `codex/mt-evidence-20261016`, main base `0f01e465`. PR #591의 1차 커밋 `84258711`을 보존하고 원문 검토를 후속 보강했다. 다른 선거 세션이 #591을 먼저 만든 뒤 IN으로 넘어간 것을 확인했다. MT는 여기서 이어 맡고 IN/IL/KY 파일은 편집하지 않는다. 새로운 주별 PR을 쌓거나 다른 주 입력을 섞지 않는다.

## 공식 후보 및 신원

공식 `candidatefiling.mt.gov/candidatefiling/CandidateList.aspx?e=450002987` FEDERAL GENERAL 2026의 FILED 행을 재검토했다. 상원 인쇄4명(Alme REP, Bankhead DEM, Bodnar IND, Austin LIB), 별도 기명 Jami Dee Woodman, 하원01 3명·02 4명, 인쇄11명+기명1명. FILED는 별도 투표용지 인증·당선 결과와 다르다. 세 선거 모두 복수 후보이며 무투표 당선 근거로 바꾸지 않는다. 주지사는2026 비선거다.

`ballot_mt.py`는 검토한 공식 URL·선거명·연방 직위·구역·FILED/REGULAR·정당·중복·후보 수를 검증하고 연락처/주소를 증거 입력에서 제외한다. 상원 필수 비교는 인쇄4명이며 기명 후보를 별도 보관한다. 과거 Daines 가상 대진이나 Austin 없는 비교를 현재 완전한4자 조사로 채택하지 않는다. official 이름·캠프 웹 주소·Green Papers의 명시적 이름/FEC ID와 현재 FEC 후보 마스터의 주/직위/지역구/정당을 대조해 인쇄10명의 FEC ID를 연결했다. Nick Sheedy 및 기명 Woodman 미확인 ID는 null. FEC 등록은 본선 진출 근거가 아니며 공식 명부가 우선한다.

## 실제 수집과 원문

기존 1차의 실제 공개 API27건·원래 captured_at `2026-10-16T04:05:43.023928+00:00`을 보존했다. transport와 별도로 검토한 원문을 기존 primary supplement 수집기로 재확인했다. URL·SHA256·실제 확인 영수증을 MT packet에만 추가했다.

Montana Free Press/Rutgers-Eagleton의8/27~9/7 원문 XLSX와 방법론 PDF를 확보했다. API 미편입 최초 문항3건을 보완한다. 전체 RV845와 문항별 유효 응답 n을 혼동하지 않는다.

| 선거 | 초기 문항 n(RV) | 후보 원문 비율을 %로 변환한 값(표시용 반올림) |
|---|---:|---|
| 상원 |804| Alme38.15 / Bankhead16.32 / Austin4.64 / Bodnar30.28 |
| 하원01 |377| Flint42.18 / Forstag41.46 / Sheedy5.07 |
| 하원02 |421| Downing46.75 / Miller23.60 / McCracken3.26 / Eisenhauer7.75 |

원문 `Column Valid N %`에100을 곱한 값이며 재정규화하지 않았다. Other/불투표·미응답을 후보에게 배분하지 않는다. 뒤의 P2+P2A/P3+P3A/P4+P4A leaner 합산은 별도 문항으로 남기고 중복 편입하지 않는다. 전체 조사 ±4.2%p를 문항804/지역구377·421의 오차로 대입하지 않는다. 원문에는 전체 질문 순서의 완결 검증이 없어 이를 한계로 남긴다. 기관 수·AAPOR 참여·다수 조사와의 일치로 정확도 등급을 만들지 않는다.

최근 Concord10/6~8 LV405 메모의 인쇄4명 수치는 원문 대조했으나 실제 의뢰자와 전체 문항 순서가 미공개다. mtpolling.com의 Montana Freedom PAC 게시라는 출처 맥락을 남기되 PAC가 조사 비용을 지급했다고 추정하지 않는다. **참고 전용**, 최근 우세/전망에서 제외. Bodnar를 DEM으로 합산하지 않는다. American Pulse MT01 API는 기존 검토의 참고 전용이며 정확한 원문 n/LV/방법론이 미확보다. 직접 요청은429; 웹 읽기로 수치·기간만 확인했다. Senate 원문429·Quantus3명비교·Hart404·Tavern 가상/후발 질문은 보류 사유를 남겼다.

재생성 결과 MT 관측5건(적격 누적3·참고2), 연방3선거 모두 누적 조사 보유. 적격3건의 종료9/7은10/16 기준7/14일 밖이다. 최근 Concord는 참고이므로 현재 승패·당선확률을 만들지 않는다. 최신 조사 부재는 실제 세상에 조사가 없다는 뜻이 아니다.

## 자동화 경계

MT 주별 operation은 기존 read/overlay → 공개 API+정확히 검토한 PDF/XLSX → 이름·정당·문항·표본·중복 검사 → live/history/state projection에 연결된다. 원문 변경/접근 장애는 원래 검토일의 참고 전용 이월, 후발 API 같은 파동의 표본/수치 충돌은 수집 보류다. 이미 검토된 일반 API 출처의 새 완전한 대진은 코드 변경 없이 수집한다. 새 기관·의뢰자·가상 양자·새 원문 URL 전체를 자동 승인하지 않는다. 합성 Emerson 미래 조사 테스트는 코드 검증용이며 실제 관측에 저장하지 않는다.

## FEC 독립지출

사용자 제공 키를 비표시 표준입력으로 메모리에만 사용했고 파일/문서/명령 출력에 기록하지 않았다. 공식 FEC MT 한정 Schedule E 정기 보고서218행을4요청으로 실제 확보했고 most_recent/정정·메모·고유 ID를 기존 수집기로 검증했다. 메모6 제외212행→29집계; 현행 후보23집계와 비현행 후보6집계를 분리했다. O(super PAC)·V/W(hybrid)·U(single-candidate IE) 분류, 본선 G2026·경선 P2026·미확인 유형과 지지/반대 방향을 유지했다. 캠프 수입이나 일반 비용을 IE로 바꾸지 않는다. 원시 응답 hash·공식 조회 URL(키 제외)·실제 수집일·기존 보존 기준일을 감사 자료에 남겼다.

**이번 MT 한정 FEC 수집은 감사 입력이며 전국 금융 게시기를 대체하지 않는다.** UI 금액은 기존 전국 index의 마지막 성공10/12·최신 filing10/7을 유지한다. 새 후보 ID 연결은 기존 전국 FEC 주기 갱신에 적용된다. MT02의 미관측 후보 돈은 null이며0달러로 만들지 않는다. 감사의0은 관측 행 집계 안의 반대/지지 부재이고 주 전체 완전한0이라는 뜻이 아니다. 전국 금융을 현재 날짜로 가장해 덮어쓰지 않았다.

## 검증·인수

MT 전용 검사8개: 네 정당·기명 분리/ID, 문항별 n·초기/leaner·전체 MOE 구분, 참고 메모, 미래 검토 출처의 완전 대진 연결, 구 후보/누락 후보 거절, 후발 API 중복·충돌·원문 장애 이월, FEC 행/범주 범위, 타주 race/history/날짜·104석 house_poll_focus 보존, 공식 parser 변경/중복 거절.

1차 #591 실패는 공용 FL/ME/MN/NC/TX 테스트 정책 날짜10/14 고정 때문이다. 해당 테스트만 공용 기반 `codex/poll-test-catalog-clock-20261016`에 분리하고 과거 normalize/summarize10/14와 실제 입력 날짜는 유지한다. 주별 PR에는 공용 테스트를 넣지 않는다. 전국 생성물은 `/private/tmp/mt-evidence-20261016/validation`에서만 재생성한다. 원자료/원문/검사 로그는 같은 임시 경로. 파일 보존과 최종 검사 결과는 PR에 기록한다.

병합·배포·운영 workflow 직접 실행·사용자 전용 재설정 안 함. 다음 IN은 다른 세션 담당이고 이 작업에서는 시작하지 않는다.

최종 공용 기반: PR #598 (`025fb042`), 이 기반에 없는 주별 변경만 #591 diff에 포함한다. 실제 base 기준 주별 범위 검사 통과, MT8개 통과. 기반 polling525·finance68·JS90·ops16·deploy-chain40 및 실제 main 체크포인트 재생성 통과. MT 전체 polling 재검증·원격 CI는 별도로 결과 확인한다. 새 FEC 행은 packet 감사 입력에만 보존하며 미배포다.
