# 플로리다 조사 원문·공식 공개 지출 감사 — 2026-10-08

A그룹 네 번째 주FL을 기존 Draft PR #492에서 보강했다. 후보 #490·전국50주/API·FEC 및 GA 변경을 보존했다. 다음 원문 검토PA, 최신 주 공시 장애 재시도GA다. FL은 `live_sources_reviewed_partial`이며 주지사 후보별 금액 완성이 아니다. 배포 보류를 유지한다.

| 직위 | 선거 수집 대상 | 누적 원문 확인 관측 | 최근7/14일 적격 | 현재 후보 Super PAC 관측 |
|---|---:|---:|---:|---:|
| 하원 | 28/28구 | 13·16·22구 각각1건 | 0 | 16/28구 |
| 상원 | 선거1석 | 3건 | 0 | 1/1석 |
| 주지사 | 선거1곳 | 3건 | 0 | 주 후보별 독립지출 미확보 |

하원 독립지출 관측은01·02·05·06·09·10·11·13·14·16·19·21·22·24·25·27구이다. 미관측03·04·07·08·12·15·17·18·20·23·26·28구는0달러나 지출 없음 확정이 아니다. 기존 Cook 검토본의 우선 하원13·14·22·25·27구 중 조사 관측은13·22구,14·25·27구는 미편입/자료 미확보 상태이며 원래 Cook 기준일을 유지한다.

실제 FL API57개 레코드에서 누적9건을 연결했다. 원문 검토9건 중 이번에3건을 추가 편입했다. 전국 누적76건 = 집계 적격59 + 참고17이다. 추가3건은 모두 참고 전용이며 최근7·14일 우세/색/의석 전망에 쓰지 않는다. 조사 수집 경로와 실제 최근 자료 확보를 구분한다. 다른 주476레이스, 누적 이력, 주별index 항목, 기존 금융/감사/접근 상태2953파일 및 전역 원래 조사일·수집 시각을 보존했다.

## 추가·재확인한 원문

- [Tavern Research FL22 PDF](https://242750075.fs1.hubspotusercontent-na2.net/hubfs/242750075/FL-22%20General%20Toplines%20%E2%80%94%20Aug%2019_NEW.pdf):8/10–12 온라인551명.1쪽 방법·4쪽Q13을 시각 대조했다. Askar50/Dandiya50은 **with leaners**이고 경선 전 가상 본선 구도다. 원문은전체 voters로 기술하며 API LV 판별 기준·LV 문항 표본은 미확인이다. 가중 변수·발표 오차4.9pp 기록, 의뢰자·신뢰수준 미공개. `historical_matchup_reference`, 참고 전용으로만 편입한다. 공유HubSpot 도메인 전체를 허용하지 않는다.
- [Change Research 9/10 발표](https://changeresearch.com/research/2026/2026-09-10-an-emerging-florida-blue-wave) 및 [방법·문항](https://changeresearch.com/research/2026/2026-09-10-florida-aapor-methodology-statement):9/7–9 LV1107/RV1317. 상원Moody47/Nixon47, 주지사Jolly47/Donalds44. 온라인 광고·유권자명부 문자, 투표 의욕8–10 LV, 가중 변수·모형 오차2.8pp를 기록했다. 메시지 노출 이후50/45는 제외한다. Freedom Project USA 의뢰자 성격 미검토로 두 건 모두 참고 전용이다. 로컬HTTP403과 공개웹 도구로 읽은 원문을 구분하고 HTML SHA를 만들었다고 주장하지 않는다.
- 주지사9/7 조사 API의 URL은 `[null]`이다. 위 기관 발표의 동일 후보·직위·기간·표본·응답을 확인해 `provider_source_correction`으로 연결했다. 원래 URL과 전체 응답 지문을 보존하며 날짜·후원자·내부/정파·수치·표본·기관·URL이 변하면 재검토 전 보류한다. 임의 링크 교체·공유 호스트 자동 허용은 하지 않는다.
- 기존 Stetson2건·Change Research9/25–27의2건·Hart FL13·PPP FL16을 재대조했다. Stetson9/14–21의830명은 전체 성인 표본이며 LV문항N 미공개, 온라인 비확률 표본·미정층 재질문 포함51/39·51/40을 그대로 구분한다. Change9/25–27 원문은 LV1063/1107 상충이 여전히 있어 참고 전용이다. Hart의3후보44/43/7과2후보51/46을 혼합하지 않는다. PPP FL16 RV530·10/1–2 Q7의39/43은 당파성/의뢰자 미확인 참고 전용이며 주 전체 조사로 확대하지 않는다.

`usa_election_poll_release_reviews/2026/FL-primary-20261008.json`에 실제 API 응답·수정 전 검토·기관 원문·방법·쪽수·PDF SHA·접근 실패를 보존했다. 출처 대조는 기관 정확도 등급·통계적 유의성·당선확률 평가가 아니다.

InsiderAdvantage9/20–21은 기관 본문이Moody49/Nixon42/Other2/Undecided7이지만 API는NeilGillespie2.4로 제3후보를 명명한다. 별도 결과표 이미지 접근이 시간 초과여서 대응을 확인하지 못했다. `provider_third_candidate_attribution_unverified`로 **편입 보류**한다. Other를 후보 지지로 추정하지 않는다. StPetePolls2건의 의뢰 매체 원문 접근 실패와 FL27 Tulchin의 방법론 미확인은 별도 로그로 남겼다. API 밖 모든 조사·미등록 발표의 발견을 보장하지 않는다.

## 주지사 공시 — 공개 조회는 가능, 후보별 금액은 보류

[공식 데이터베이스](https://dos.fl.gov/elections/candidates-committees/campaign-finance/campaign-finance-database/)가 연결한 [공개 expenditure 조회](https://dos.elections.myflorida.com/campaign-finance/expenditures/)의 실제 form/action/필드를 확인했다. 조회POST는 신고/계정 수정이 아닌 읽기 작업이다. EFS 로그인은 신고용이며 공개 조회에 API키나 신고자 비밀번호가 필요하지 않았다. Reset은 사용하지 않았다.

ECO 선거광고 조직 범위의2026 선거 선택·일반지출TSV172행(2025년95·2026년77),공시에 기재된 단체명13종, MON166/REF2/ECC4를 실제 재수집했다. 동일8필드가 반복된7개 행도 실제 복수 지급/정정을 판별하지 못해 합산하지 않는다. 지급 날짜 범위2025-01-06~2026-10-01은 **신고일이나 본선 집계 기준일이 아니다**.1000행 제한 미도달도 공시 전수 대조·완전 수집 증거가 아니다. 날짜 필터 조회는Invalid Date Range 오류를 반환해 금액 수집에 쓰지 않았다.

export는 후보 대상·직위·S/O·거래ID·정정 관계를 제공하지 않는다. ECO 일반 지출을 주지사 독립지출로 간주하거나 Purpose/단체명/Type/음수 반환으로 후보 지지·반대를 추정하지 않는다. 후보별 지지·반대액과 대상 건수는null이고 기존금융index·파일·날짜를 변경하지 않았다. PAC·독립지출 신고자 전체 조회, 신고 원문·후보 대상/S/O·정정 식별 연결이 다음 FL 금액 보강 단계다.

`usa_governor_finance_audits/2026/FL.json`은 쿼리·8필드·SHA·범위·유형·후보별 보류를 기록한다. 수집기는 빈 결과·HTML 오류·스키마/직위/선거 범위 변경·1000행 도달·비정상 금액·리디렉션·네트워크 실패를 오류로 처리하고 마지막 감사/금융 파일을 보존한다.

## 재실행과 검증

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_governor_finance_audit.py --state FL
python3 refresh_state_polls.py --state FL --as-of YYYY-MM-DD
python3 refresh_state_evidence.py --state FL --as-of YYYY-MM-DD
```

기준일은 실제 실행일을 넣는다. CLI재수집만으로 새 원문 전수검토가 완료되는 것은 아니다. `primary_rechecked_ids`·`primary_review_data_file`·`governor_audit_captured_at`은 확인한 현재 자료에만 연결한다. 검토 레코드가 변하거나 없어지면 기존 검토 완료 표시를 상속하지 않는다. 주 공시 감사는 정기workflow에 설치하지 않았으며 후보 금액/UI 추가도 하지 않았다. 전국 API 정기수집은 기존 경로, 일일 전환은 별도 Draft #489다.

Python polling198·금융58·연방6·JS51 =313개 통과. FL 추가13검사는 원문 누락 복원·변경 응답 보류·기간/모집단·참고 조사 제외·Other를 후보로 바꾸는 오류·ECO 일반지출 오분류·0원 오판·1000행 상한·스키마/금액/날짜/리디렉션 경계를 검증한다. UI/workflow/LETF 변경·병합·배포·배포workflow dispatch는 없다.
