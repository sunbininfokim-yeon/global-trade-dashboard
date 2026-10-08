# 미국 여론조사 우선 보강·전국 공백 점검 (2026-10-08)

`T-POLL-GAPS-20261008` · `codex/us-poll-gaps-20261008` · 사용자 요청: 여론조사 우선, 새 API 키 필요 시 해당 경로 중단·요청, 무투표 가능 별도 확인. UI·Actions 파일 편집·병합·배포 없음.

## 실제 갱신 결과

실제 공개 API 수집 성공: `2026-10-08T00:22:26.973242+00:00` · 기준일 `2026-10-08`. API 레코드 66건 편입: 집계 가능 55, 참고 전용 11. 제공 API 밖 조사를 모두 발견한다는 뜻은 아니다.

| 직위 | 전국 예정 선거 | 누적 관측 있는 선거 | 관측 없음 | 7일 내 집계 가능 | 14일 내 집계 가능 | 회기 누적 연방 Super PAC 관측 |
|---|---:|---:|---:|---:|---:|---:|
| 하원 | 435 | 10 | 425 | 0 | 2 | 314 |
| 상원 | 35 | 12 | 23 | 1 | 5 | 34 |
| 주지사 | 36 | 18 | 18 | 1 | 7 | 0 |

관측에는 참고 전용·오래된 자료도 포함한다. 최근 7일 자료는 ME 상원·주지사만 각 1기관이며 전국 승패 전망이나 확정 결과가 아니다. 14일에는 단일 기관 11, 복수 기관 2, 동률 1개 선거. 올해 상원은 33 Class II + FL·OH 보궐 2석; 비선거 65석은 이 발견 대상에 넣지 않는다.

공시 비교 기준은 활성 2026 지도 인덱스(`2026-10-07T12:17:06.473357+00:00`). 하원 121곳·상원 ID 1곳에 누적 Super PAC 관측 없음. 주지사 CA·NY만 주별 독립지출 관측, 다른 선거 주 34곳은 미연결. WA는 소스가 구현돼 있어도 2026 주지사 선거가 없다. 연방 FEC 자료 재수집은 하지 않았다. 본선 G2026 지출과 회기 누적·경선·UNKNOWN 지출은 JSON에서 계속 분리한다.

## 이번에 연결한 자료

- UNH 대학 공식 저장소: NH-01·NH-02 하원 및 VT 주지사 등. 자동 집계값은 부분 검증; 원문 수치·문항별 표본 검토 범위는 별도.
- SurveyUSA/KOB-TV: NM-02 하원 LV 554명, 46/43 원문 대조. 공식 경선 일정을 확인해 6월 3일 이후 본선 대진 발견을 허용.
- SurveyUSA/ABC 10News·San Diego Union Tribune: CA-48 하원 LV 522명 45/42, CA 주지사 LV 742명 55/33 원문 대조. 본선 조사 기간·모집단·표본 분리.
- SurveyUSA/Grant Forbes LLC: NE-02 182명 46/42. 의뢰자 정치 관계 미확인·소규모 하위 표본 때문에 참고 전용.
- SurveyUSA/KOB-TV: NM 상원 54/36은 원문 대조했으나 API 576명과 원문 LV 567명이 달라 참고 전용.
- NY-21 발견 경로·세 후보 명부 추가. WNYT/SurveyUSA 원문은 LV 612명인데 API는 성인(a) 800명으로 등록하여 편입 보류. 숫자를 임의로 고쳐 최신 우세로 쓰지 않는다.
- FL-13 기존 Hart 정당 의뢰 조사: 공식 후보 명부로 제3후보 IND 소속을 확인해 검토 fingerprint를 갱신. 경선 전 대진·정당 의뢰 참고 전용 지위는 유지.

## 자동 연결 범위와 키

기존 월요일 06:10 KST 주간 Actions가 변경된 기본 수집기를 읽는다. 새 workflow·일일 실행·수동 dispatch는 추가하지 않았다. 이 브랜치가 병합되기 전에는 이번 확장이 정기 작업에 설치된 것이 아니다. 배포도 별도다.

공개 API https://api.votehub.com/polls · 문서 https://votehub.com/polls/api/ · CC BY 4.0 출처 표시. 이 여론조사 경로와 FL 공식 후보 명부에는 새 API 키가 필요 없다. FEC 기존 키는 이번 여론조사에서 사용하지 않는다. 미국 전체 여론조사를 보장하는 연방 선관위 통합 API를 만든 것은 아니다.

전국 506개 선거를 발견 대상으로 등록. 검토된 본선 대진은 191개다. 공식 본선 무경쟁 1곳은 비교 예외이며, 나머지 314곳은 대진 심사가 필요하다. 출처·의뢰자·본선 대진·날짜·LV/RV·표본·중복·개별 검토 fingerprint를 통과한 새 레코드만 자동 편입한다. 미등록 기관, 검토되지 않은 의뢰자, 후보 변경, 자료 모순은 검토 대기다. 조사 자체의 미발표·API 미등재·유료 제한을 API 키 하나로 해결할 수 없다. KSTP 원문은 접근 제한으로 이번에 자동 승인하지 않았다.

`usa_election_live_polls_v1.json.data_gaps`에 주별·지역구별 공백, 미편입 사유, 실제 공시 링크, 단독 출마 검토를 함께 싣는다. 기존 주간 publish 대상 파일 안에 있으므로 workflow 수정이 필요 없다. API 오류에는 마지막 정상 자료와 원래 기준일을 보존하고 별도 실패 상태를 발행한다. 예전 snapshot을 새 조사로 표기하지 않는다.

## 무경쟁·임명 구분

FL 공식 본선 후보 명부 30개 선거(28 하원+상원+주지사)를 자동 읽는다. Qualified/Unopposed 현재 후보와 기입 후보까지 포함하며 Primary Status와 General Status를 분리한다. 표 구조·상태·지역구 목록이 달라지면 이전 명부를 보존한다.

- FL-10 Maxwell Alejandro Frost(DEM): 공식 명부 General Status=Unopposed. Florida 101.151(7)의 무경쟁 후보 일반 투표지 미표시 법령과 함께 기록. 공식 인증된 당선 결과는 아니며 결과·득표율을 생성하지 않는다. 여론조사 비교 불필요 예외를 별도로 기록.
- 전체 명부가 아니거나 DEM/GOP 한쪽만 확인돼도 무투표로 판단하지 않는다. CA 같은 당 후보끼리의 9개 선거, 무소속·제3당 상대 3개 선거를 무경쟁과 분리한다. 전체 후보 명부 검토 미완료 349개 선거는 무투표 여부 미확인이다. 이는 검토된 주요 본선 대진이 없다는 의미와 다르다.
- 임명은 상원 공석을 주지사가 임명으로 보충한 현직 취임 경로. 선거 승리·재선 횟수로 계산하지 않는다. 임명자는 다음 본선 후보와 같거나 다를 수 있다.

공식 근거: https://dos.elections.myflorida.com/candidates/CanList.asp?elecid=20261103-GEN&status=All · https://leg.state.fl.us/STATUTES/index.cfm?App_mode=Display_Statute&URL=0100-0199%2F0101%2FSections%2F0101.151.html · https://www.senate.gov/senators/NewSenators.htm

## 요청 지역의 현재 상태

| 지역 | 하원 누적 관측 지역구 | 상원 | 주지사 | 7일 내 집계 가능한 자료 |
|---|---|---|---|---|
| NY New York | 17 | 2026 비선거 | older_polls_only | 없음 |
| TN Tennessee | 없음 | reference_only | reference_only | 없음 |
| GA Georgia | 없음 | reference_only | reference_only | 없음 |
| FL Florida | 13 | older_polls_only | older_polls_only | 없음 |
| AZ Arizona | 없음 | 2026 비선거 | reference_only | 없음 |
| MI Michigan | 없음 | recent_14d_only | recent_14d_only | 없음 |
| NV Nevada | 없음 | 2026 비선거 | recent_14d_only | 없음 |
| NC North Carolina | 없음 | older_polls_only | 2026 비선거 | 없음 |
| PA Pennsylvania | 07, 10 | 2026 비선거 | older_polls_only | 없음 |
| WI Wisconsin | 없음 | 2026 비선거 | older_polls_only | 없음 |
| TX Texas | 없음 | recent_14d_only | recent_14d_only | 없음 |

`reference_only`=참고 전용, `older_polls_only`=집계 가능 자료가 있으나 최근 기간 밖, `review_required`=API 기록은 있지만 검토 보류, `no_provider_record`=API에서 미발견. 그룹 간 중복 포함: {'requested_states': {'race_count': 196, 'with_observations': 20, 'recent_7d': 0, 'recent_14d': 6}, 'cook_toss_up_and_lean': {'race_count': 64, 'with_observations': 27, 'recent_7d': 1, 'recent_14d': 13}, 'korean_company_facilities': {'race_count': 15, 'with_observations': 6, 'recent_7d': 0, 'recent_14d': 2}}

## 50개 주별 미확보 목록

하원은 공식 435개 투표권 의석만 사용. AK·DE·ND·SD·VT·WY 전역구 지도/FEC는 00, VoteHub의 01은 검토된 전역구 전송 별칭. DC·미국령·과거 회기 유령 번호는 이 표의 선거 대상이 아니다. CT/IL/NH 일부 기존 도형의 과다 번호를 공식 의석수로 쓰지 않았으며 도형 수정은 이번 범위 밖이다.

아래 하원 번호는 해당 주의 지역구다. 여론조사 없음에는 FL-10 공식 본선 무경쟁 예외 1곳 포함. 공시 없음은 관측·연결 실패이며 0달러가 아니다. 누적 관측이 있어도 최근 7일 자료가 없는 곳은 JSON의 `polls_without_7d`로 별도 확인한다.

| 주 | 하원 여론조사 관측 없는 번호 | 하원 누적 Super PAC 관측 없는 번호 | 상원 여론조사 없음 | 주지사 여론조사 없음 | 주지사 지출 연결 상태 |
|---|---|---|---|---|---|
| AK | 00 | — | 없음 | 없음 | source_unsupported |
| AL | 01, 02, 03, 04, 05, 06, 07 | 03, 04, 05, 06, 07 | 없음 | 없음 | source_unsupported |
| AR | 01, 02, 03, 04 | 01, 03, 04 | 없음 | 없음 | source_unsupported |
| AZ | 01, 02, 03, 04, 05, 06, 07, 08, 09 | 08, 09 | 비선거 | 관측 있음 | source_unsupported |
| CA | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 49, 50, 51, 52 | 20 | 비선거 | 관측 있음 | observed_partial |
| CO | 01, 02, 03, 04, 05, 06, 07, 08 | 02, 06, 07 | 없음 | 없음 | source_unsupported |
| CT | 01, 02, 03, 04, 05 | — | 비선거 | 없음 | source_unsupported |
| DE | 00 | — | 없음 | 비선거 | 비선거 |
| FL | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28 | 08, 12, 15, 17, 18, 20, 28 | 관측 있음 | 관측 있음 | source_unsupported |
| GA | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14 | 02, 03, 04, 05, 06, 07, 08, 12 | 관측 있음 | 관측 있음 | source_unsupported |
| HI | 01, 02 | — | 비선거 | 없음 | source_unsupported |
| IA | 01, 02, 03, 04 | — | 관측 있음 | 관측 있음 | source_unsupported |
| ID | 01, 02 | 01, 02 | 없음 | 없음 | source_unsupported |
| IL | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17 | 01, 03, 04, 10, 15 | 없음 | 없음 | source_unsupported |
| IN | 01, 02, 03, 04, 05, 06, 07, 08, 09 | 02, 03, 07, 09 | 비선거 | 비선거 | 비선거 |
| KS | 01, 02, 03, 04 | 01, 02, 03, 04 | 관측 있음 | 관측 있음 | source_unsupported |
| KY | 01, 02, 03, 04, 05, 06 | 02, 03, 05 | 없음 | 비선거 | 비선거 |
| LA | 01, 02, 03, 04, 05, 06 | 01, 02, 03, 04 | 없음 | 비선거 | 비선거 |
| MA | 01, 02, 03, 04, 05, 06, 07, 08, 09 | 01, 03, 08, 09 | 없음 | 없음 | source_unsupported |
| MD | 01, 02, 03, 04, 05, 06, 07, 08 | — | 비선거 | 없음 | source_unsupported |
| ME | 01, 02 | — | 관측 있음 | 관측 있음 | source_unsupported |
| MI | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13 | — | 관측 있음 | 관측 있음 | source_unsupported |
| MN | 01, 02, 03, 04, 05, 06, 07, 08 | 03, 06, 07, 08 | 없음 | 없음 | source_unsupported |
| MO | 01, 02, 03, 04, 05, 06, 07, 08 | 04, 07, 08 | 비선거 | 비선거 | 비선거 |
| MS | 01, 02, 03, 04 | 01, 03, 04 | 없음 | 비선거 | 비선거 |
| MT | 01, 02 | 02 | 없음 | 비선거 | 비선거 |
| NC | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14 | 03, 05, 06, 08, 09, 10, 13 | 관측 있음 | 비선거 | 비선거 |
| ND | 00 | 00 | 비선거 | 비선거 | 비선거 |
| NE | 01, 03 | — | 없음 | 없음 | source_unsupported |
| NH | — | — | 관측 있음 | 관측 있음 | source_unsupported |
| NJ | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 04 | 없음 | 비선거 | 비선거 |
| NM | 01, 03 | — | 관측 있음 | 없음 | source_unsupported |
| NV | 01, 02, 03, 04 | — | 비선거 | 관측 있음 | source_unsupported |
| NY | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 26 | 01, 02, 11, 23, 26 | 비선거 | 관측 있음 | observed_partial |
| OH | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15 | 02, 04, 05, 06, 08, 10, 12 | 관측 있음 | 관측 있음 | source_unsupported |
| OK | 01, 02, 03, 04, 05 | 02, 03, 05 | 없음 | 없음 | source_unsupported |
| OR | 01, 02, 03, 04, 05, 06 | 01, 02, 03 | 없음 | 관측 있음 | source_unsupported |
| PA | 01, 02, 03, 04, 05, 06, 08, 09, 11, 12, 13, 14, 15, 16, 17 | — | 비선거 | 관측 있음 | source_unsupported |
| RI | 01, 02 | 01, 02 | 없음 | 없음 | source_unsupported |
| SC | 01, 02, 03, 04, 05, 06, 07 | 02, 03, 05, 06, 07 | 없음 | 없음 | source_unsupported |
| SD | 00 | — | 없음 | 없음 | source_unsupported |
| TN | 01, 02, 03, 04, 05, 06, 07, 08, 09 | 01, 03, 04, 05, 08 | 관측 있음 | 관측 있음 | source_unsupported |
| TX | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38 | 07, 16, 20, 25, 36 | 관측 있음 | 관측 있음 | source_unsupported |
| UT | 01, 02, 03, 04 | 04 | 비선거 | 비선거 | 비선거 |
| VA | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11 | 03, 04, 06, 08, 09 | 없음 | 비선거 | 비선거 |
| VT | 00 | — | 비선거 | 관측 있음 | source_unsupported |
| WA | 01, 02, 04, 05, 06, 07, 08, 09, 10 | — | 비선거 | 비선거 | 비선거 |
| WI | 01, 02, 03, 04, 05, 06, 07, 08 | 01, 05, 06, 08 | 비선거 | 관측 있음 | source_unsupported |
| WV | 01, 02 | 02 | 없음 | 비선거 | 비선거 |
| WY | 00 | — | 없음 | 없음 | source_unsupported |

## 주지사 미연결 34개 주 공시 점검

36개 선거 주를 모두 활성 지도 자산과 대조했다. CA·NY의 관측만 유지. 다음 34개 주는 후보별 S/O 독립지출 어댑터 미연결 상태로 남긴다. 기존 검토 소스가 있는 곳도 단순 모금액·총지출·광고 구매를 주지사 독립지출로 바꾸지 않는다. 공식 전체 출처 카탈로그 완성도 이 표와 구분한다.

| 주 | 기존 검토 출처·접근 방식 | 남은 작업 |
|---|---|---|
| AK | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| AL | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| AR | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| AZ | [Arizona Secretary of State Spotlight](https://spotlightv2.arizona.vote/Reporting/Api) · public_json_api_documented | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| CO | [Colorado Secretary of State TRACER](https://tracer.sos.colorado.gov/PublicSite/SearchPages/PublicNonScheduledFilingsSearch.aspx) · public_reporting_search | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| CT | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| FL | [Florida Division of Elections](https://dos.fl.gov/elections/candidates-committees/campaign-finance/campaign-finance-database/) · search_tsv_export | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| GA | [Georgia Government Transparency and Campaign Finance Commission](https://media.ethics.ga.gov/search/Campaign/Campaign_ByExpenditures.aspx) · public_search_export | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| HI | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| IA | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| ID | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| IL | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| KS | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| MA | [Massachusetts OCPF](https://api.ocpf.us/developers) · public_json_api | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| MD | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| ME | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| MI | [Michigan Secretary of State MiTN](https://www.michigan.gov/sos/elections/disclosure/cfr) · public_search_and_annual_transaction_zip | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| MN | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| NE | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| NH | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| NM | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| NV | [Nevada Secretary of State](https://www.nvsos.gov/SOSCandidateServices/AnonymousAccess/CEFDSearchUU/Search.aspx) · public_campaign_finance_search | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| OH | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| OK | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| OR | [Oregon Secretary of State ORESTAR](https://sos.oregon.gov/elections/campaign-finance/Pages/search-campaign-finance.aspx) · public_reporting_search | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| PA | [Pennsylvania Department of State](https://www.pa.gov/agencies/dos/resources/voting-and-elections-resources/campaign-finance-data) · annual_full_export_zip | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| RI | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| SC | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| SD | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| TN | [Tennessee Registry of Election Finance](https://apps.tn.gov/tncamp/) · public_search_csv_export | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| TX | [Texas Ethics Commission](https://webservices.ethics.state.tx.us/search/cf/) · bulk_csv_and_search | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| VT | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| WI | [Wisconsin Ethics Commission Sunshine](https://campaignfinance.wi.gov/) · public_reporting_search | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |
| WY | [FEC 주별 공시 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/) · 주별 구체 경로 미검토 | 후보·위원회 유형·지지/반대·정정·선거 단계 검증 후 어댑터 필요 |

## 검증·인수

- Python 여론조사 계약 109개, JS 선거 계약 51개 통과. 신규 테스트는 전국 의석수·비선거·전역구·미검토 대진·신규 발표 자동 반영·별칭 중복·의뢰자 제한·본선 무경쟁·기입 후보·공시 결측 보존·잘못된 검토 파일 실패 보존·선거 후 API 장애 시 공백 감사의 조사 수치도 종료됨을 확인한다.
- 실제 API/공식 FL 명부 수집 및 saved API replay 모두 검증. Replay는 산출물에서 replay로 표시하며 운영 데이터 대신 발행하지 않는다.
- 주간 workflow는 변경하지 않았다. PR validation 성공은 수집·main 설치·배포의 증명이 아니다.
- 선거 후 live 누적 목록·우세는 기존 날짜 기준으로 비우고 역사 파일은 검증용으로 보존. 공식 인증 결과 파일이 들어오면 우선 표시하되 결과 자동 수집기가 설치된 것은 아니다.
- 기존 주지사 PR #478은 이번 확인 시 이미 병합돼 있었다. 작업 중 UI PR #483도 main에 병합되어, 검토 브랜치에 최신 main을 반영했다. 기존 UI·다른 변경을 보존했으며 PR #485의 diff는 데이터와 인수 문서만 포함한다.
- 자동 선거구 경계 갱신, 각 주 공시 어댑터, 미등재/유료 조사 원문 수집, 전국 무투표 검증은 남은 작업이다. 현재 새 API 키 요청 없음.
