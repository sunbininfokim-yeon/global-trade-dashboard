# 아이오와 후속 — 누락 Suffolk 원문 및 공개 IE 재점검

사용자 “아이오와 492 다시” 요청과 “어제 아이오와 하다가 토큰 다 쓴 거 아니야?” 확인에 따라 현재 상태를 먼저 점검했다. #492는 OPEN Draft / 061c8f72, IA 후속 #498은 OPEN Draft / 99add883이며 두 선거 검증은 SUCCESS였다. 기록으로 토큰 한도 중단 여부는 확인할 수 없다. #498에 저장된 보강과 하원 조사·주지사 거래 매핑의 미완료를 구분했다.

기존 PR들을 변경하지 않고 `codex/ia-followup-20261009`를 최신 #502 / ce7c0bdd 기반으로 만들었다. #502 → #501 → #500 → #499 → #498 → #492 의존 관계다. UI/workflow/LETF, 병합·배포·workflow dispatch, 다음 주 작업은 제외했다. 실행 중인 선거 수집 PID·현재 PR·깨끗한 checkout을 확인했다. 실제 수집 UTC 2026-10-08 / 한국시간 10-09이며 공통 as_of 2026-10-08과 기존 전국 날짜는 보존했다.

## 이전 완료와 이번 추가

#498은 공식 후보 6선거와 기존 여론조사 7관측, 공개 IE API 최신 100건 부분 목록, 당시 365검사까지 저장했다. 이번 공개 API 재점검은 IA 39레코드(주 전체 subject 및 IA-01/02 subject)를 확인했다. 실제 API schema에는 state 필드가 없어 subject/정책별 조인을 사용하며 임시 초기 state 필터의 0건 결과를 실제 관측 부재로 사용하지 않았다. 기존 39 ID가 모두 남아 있고 Suffolk 10/1–4 파동은 아직 provider feed에 없다.

Suffolk 대학의 기관 페이지·marginals·tables·press release를 직접 수집하고 marginals p2 / release p2를 렌더링해 숫자·모집단·방법을 확인했다. 주 전체 500명과 Muscatine 카운티 300명을 구분한다. Q7 첫 선택 상원 Hinson43.6/Turek48.0/Laehn2.2, 미정5.6/거부0.6. Q8은 Laehn선택자 11명의 2순위이므로 합산하지 않는다. Q9 주지사는 Lahn42.8/Sand54.8, 미정2.2/거부0.2이고 문구상 vote/lean이다. 정수 보도 44/48·43/55로 덮어쓰지 않았다.

조사 10/1–4, 발표10/7, statewide LV500, live landline/cell telephone, very470/somewhat30 likely screen. 기관 방법 공개는 area adult-population PPS 및 gender/race/education/age/party quotas와 Census2020/ACS2022/exit polling/current registration이다. 본문은99county를4regions라 하지만 표는 Central/Polk 포함5regions여서 표의5regions를 보존한다. full weight 계산·설계효과·응답률·전화유형비율은 미공개다. 기관 문서의 registered-voter 표현과 Q2 self-described not registered3명을 같이 기록해 500명 전원의 등록을 검증했다고 쓰지 않는다. 발표문 보고오차4.4pp/95%와 그 검증 미실시를 표시한다. 기관 수/AAPOR 참여를 정확도 등급으로 만들지 않는다.

특정 기관 원문 `primary-suffolk-ia-senate-20261007`, `primary-suffolk-ia-governor-20261007` 두 관측을 finite record/document SHA 계약으로 추가했다. 총 누적9 = 상원4/주지사5, 하원4곳 표시관측0. 기존 승인 기관의 모든 미래 발표를 새로 허용한 것이 아니다.

| 직위 | 기간 | 기관 수 | 상태 | 정당 | 후보별 앞선 조사 수 |
|---|---|---|---|---|---|
| senate | 7 | 2 | tie | None | {'Ashley Hinson': 1, 'Josh Turek': 1} |
| senate | 14 | 3 | poll_lead | DEM | {'Josh Turek': 2, 'Ashley Hinson': 1} |
| governor | 7 | 2 | poll_lead | DEM | {'Rob Sand': 2} |
| governor | 14 | 4 | poll_lead | DEM | {'Rob Sand': 4} |

7일 상원은 CNN Hinson / Suffolk Turek로 tally 동률이며 지지율을 단순 평균한 결과가 아니다. 14일에는 Fox·Suffolk Turek2 / CNN Hinson1, MaristRV는 LV와 합산하지 않는다. 주지사7일 CNN·Suffolk2 /14일 CNN·Suffolk·Fox·Siena4. 승자·당선확률·확정의석·격차 유의성은 생성하지 않는다.

원문 PDF 세 건은 기존 허용된 Suffolk 호스트와 query 포함 URL에서 매번 지문을 검증한다. 나중 API에 동일 파동이 오면 수치/표본/의뢰자까지 정확히 일치해야 중복 제외한다. 반올림·의뢰자·문항 차이는 충돌 보류 대상으로 마지막 유효 자료를 지킨다. 원문 변경/장애는 원래10/4 날짜의 참고 전용으로 남긴다. API 밖 모든 새 조사 발견과 검토의 자동 완료는 보장하지 않는다.

## 하원 조사·주지사 공시

하원 3개 provider 레코드의 기존 보류를 유지했다. IA01 PPP2025는 최근 본선 조사 아님, Bullfinch7월은 검증할 의뢰기관 방법 원문 미확보, IA02 HMP/GSG는 초기46/45를 확인할 수 있으나 표본/모집/가중 미확보다. 집계 사이트의600명 수치를 원문 확인 없이 채우지 않았다. 최근 IA03/04 검증 가능한 공개 초기 본선 조사를 이번 검색에서 확보하지 못했다. 전체 부재 판정이 아니다. 기존 모든 후보 명부와 연방 O 누적(하원4/4·상원1/1)은 변경하지 않았다. 새 FEC 금액을 수집하지 않았다.

Iowa Ethics 공시 API를 동일 bounded 요청으로 실제 재점검해 all-year1510→1515를 관측했다. 현재 페이지100건/전수아님을 유지한다. 높은 신규 ID5 + 경계날짜 동률에 새로 보인 과거 ID1을 이전 목록과 구분했다. 이전 페이지의6 ID가 현재100건에 없다는 사실은 신고 철회가 아니다.

새로 관측한6 PDF를 다운로드·지문 확인·정확 후보 이름 텍스트 검사했다. RobSand/ZachLahn 정확 문자열은 미발견이다. 두 PDF는 House 대상이 명시됐으나 다른4개의 위원회 별명/직위는 미확인이다. 최신100건 목록, 이전10개 PDF 검토 및 원래 시각을 함께 보존하고 이번6개 검토만 별도 파일로 남겼다. 주지사 지출0/전수 부재로 판정하지 않고 후보별 support/oppose는null 및 mapping_required다. 공개 API에 키가 필요하지 않았고 인증/보안 우회·재설정 없음.

## 산출과 검증

- `usa_election_state_evidence/2026/IA-29e18f8a4d950e0b.json`, 상태 `live_poll_sources_reviewed_finance_mapping_required`.
- `usa_election_poll_release_reviews/2026/IA-suffolk-20261009.json` 추가; 이전 IA-primary 감사 보존.
- `usa_governor_ie_report_indexes/2026/IA.json` 최신100건과 status 갱신, `usa_governor_ie_report_reviews/2026/IA-followup-20261009.json` 추가.
- polling283 + finance63 + federal6 + JS51 = **403 검사 통과**. 신규8개는 statewide500/county300/2순위11 분리, 소수 후보·미정 및 소수점, gov lean문항,7일동률/14일기관tally,후발API중복·충돌,변경원문참고이월,새metadata재검토,하원결측/IE금액null을 확인한다.
- 타주 500 poll레이스 / 47 누적 이력 / 49 index / 기존 금융 4644 파일 및 전체 후보 명부·전국 as_of/fetched_at 보존 검사 통과.

남은 것은 하원 실제 조사 원문·방법 확보와 주지사 PDF 거래/위원회 신원·직위·정정·중복·S/O 매핑이다. 공시 목록 수집이 후보별 금액 구현 완료를 뜻하지 않는다. 기존 Actions 설치 작업은 별도 PR 범위이며 이번에 workflow를 바꾸지 않았다.

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state IA --as-of 2026-10-08
python3 refresh_iowa_ie_reports.py
python3 refresh_state_evidence.py --state IA --as-of 2026-10-08
```
