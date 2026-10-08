# 일일 여론조사 Actions 및 하원 24곳 편입 보류 감사 — 2026-10-08

사용자 최신 지시: 매일 Actions 수집으로 전환하고 API 기록은 있으나 편입되지 않은 24곳의 이유와 확보 순서를 설명. PR #489에서 검토 가능한 변경을 준비했다. 기존 배포 보류에 따라 병합·main 수집 실행·배포는 하지 않았다.

## 일일 수집 변경

- 매일 06:10 한국시간(`10 21 * * *` UTC). 실제 스케줄은 main 병합 후 적용된다.
- 기존 workflow 식별자 `US election polls weekly`는 배포 구독 호환성을 위해 보존하고 실행 제목(run-name)은 `US election polls daily`로 표시. 실제 일정은 매일이다. deploy.yml은 변경하지 않는다. main 수집은 JSON을 main에 기록하며 기존 배포 연결을 촉발한다.
- 정책·게시 JSON의 수집 주기는 1일, 수집 지연 기준은 48시간. 7일 기본·14일 선택의 조사 기간과 후보별 판정 규칙은 유지.
- 본 JSON에서 변경한 것은 주기 메타데이터뿐이다. 원래 as_of·fetched_at·조사 수치·출처 검토 상태를 그대로 보존했다. 새 수집을 실행했다고 표시하지 않는다.
- 전체 공개 API 1회 수집 방식·동시 실행 잠금·실패 시 마지막 유효 자료 보존·원래 기준일 유지 계약도 유지.
- 신규 API 키·유료 접근 권한은 현재 일일 VoteHub 경로에 필요 없음.

## 24곳의 의미

감사 기준: 공개 API 저장 응답과 PR #489 실제 산출물, as_of `2026-10-08`, fetched_at `2026-10-08T03:51:18.337409+00:00`. 대상은 104석 중 `provider_record_count > 0`이면서 `accepted_count == 0`인 정확히 24곳이다. 63곳의 API 무기록과 구분한다.

- 23곳의 첫 실패 조건은 `pollster_not_selected`, VA-05는 `primary_topline_mismatch`. 첫 조건만 기록하므로 기관 등록만으로 이후 검사가 통과함을 뜻하지 않는다.
- 지역구별 최신 API 기록에 정파 표시가 있는 곳 19, 정파 표시 없는 후보 조사 4(AK·IA01·OH01·VA05), 정당 지지도만 있는 곳 1(NY04). 이는 API 라벨 감사이며 조사 정확도 등급이나 의뢰자의 실제 독립성을 보증하지 않는다.
- 최신 기록이 14일 범위 밖인 곳 22. 14일 안은 VA05(9/28)·WI01(10/1), 7일 안은 0. 과거 조사 편입이 곧 현재 전망 복구는 아니다.
- 이 24곳 중 공식 본선 대진 검토가 없는 곳은 AK00·CO03·MN01·TN09 4곳. 전체104석의 미검토44곳과 겹치는 부분이다.
- 검토되면 일부 발표는 누적 참고로 담을 수 있지만, 정당 의뢰·경선 전·가정 대진·순위선택 재배분·일반 정당 지지도는 적격 본선 후보 지지도와 구분해야 한다.

## 확보 순서

1. VA-05: WP/Schar 결과표·교차표로 API/원문 불일치 해결. 14일 안의 후보 조사이고 대진 검토는 완료되어 있다. 공개 PDF/자료실 접근 실패가 남아 있으며 유료 권한 필요로 단정하지 않는다.
2. OH-01·IA-01: API 원문 링크의 실제 결과 본문·기간·LV/RV·표본·조사 방법·의뢰자 확보. 현재 자료는 오래되었으므로 누적 검토와 신규 발표 경로를 함께 확보한다.
3. AK 전역구: 공식 본선 후보 명부와 AARP 원문/방법론. AARP의 57/43은 순위선택 재배분 결과임을 원문에서 확인; 첫 선택 결과와 분리. Bill Hill을 자동 DEM 후보로 치환하지 않는다.
4. 최신 참고 자료 WI-01·OH-09·MN-01·TN-09: 원문·방법론·공식 대진/후보명 검토. 정당 관련 의뢰를 표시하고 전망의 독립 조사 수에서 제외.
5. 나머지 주·지역구는 공식 후보 명부 → 원문 결과/방법론 → 조사기관/URL별 수집 규칙을 확보. 새 기관·후보·수치 변경을 단순 자동 승인하지 않는다.

## 24곳 전체 목록

정파 표시는 API의 `partisan` 값이며 검증된 독립성 판정이 아니다. 원문 URL은 탐색·검토 대상이지 편입 승인 또는 원문 접근 성공을 의미하지 않는다.

| 지역구 | 최신 기관·조사 종료 | API 정파 표시 | 첫 실패 조건 | 필요한 확보/검토 | 원문 링크 |
|---|---|---|---|---|---|
| AK-00 | Fabrizio, Lee & Associates/Impact Research · 2026-09-11 | 표시 없음 | 원문 검토·기관 등록 미완료 | 공식 본선 후보·소수/무소속 정당 확인 필요. AARP 57/43은 순위선택 재배분 수치로 일반 지지율과 분리. 원문 PDF·방법론 필요. | [발표/자료](https://www.aarp.org/pri/topics/voter-research/politics/2026-midterm-election-poll-alaska/) |
| AZ-06 | Normington, Petts & Associates · 2026-06-11 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 경선 전 조사·정당만 묻는 다른 문항도 섞임. 원문 검토 후 해당 발표만 참고로 검토. | [발표/자료](https://www.thehousemajoritypac.com/news/new-hmp-poll-joanna-mendoza-leads-juan-ciscomani-in-az-06) |
| CA-22 | Tulchin Research · 2026-06-21 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 2025년 성인 표본·다른 후보 조사와 분리하고 실제 원문·방법론 확보. | [발표/자료](https://www.politico.com/newsletters/playbook/2026/07/21/trump-to-hill-im-not-that-into-you-01005915) |
| CA-40 | Grassroots Targeting · 2026-09-09 | REP | 원문 검토·기관 등록 미완료 | California First Fund 의뢰·REP 표시. 실제 REP 대 REP 대진을 보존. DEM 대 GOP 전망에 강제 편입 금지. | [발표/자료](https://www.politico.com/newsletters/california-playbook/2026/09/17/paramounts-nashville-overture-01081617) |
| CO-03 | Expedition Strategies · 2026-01-12 | DEM | 원문 검토·기관 등록 미완료 | 후보 의뢰·DEM 표시. 공식 본선 후보 명부 미검토, 1월 가정 대진 여부 확인 필요. | [발표/자료](https://www.politico.com/f/?id=0000019b-dcc2-d22e-a1db-dff7de8e0000) |
| FL-27 | Tulchin Research · 2026-09-13 | DEM | 원문 검토·기관 등록 미완료 | 최신 HMP 의뢰·DEM 표시. 기존 Blueprint 경선 전 가정 대진과 2025년 발표도 분리 필요. | [발표/자료](https://x.com/cjwarnke/status/2100648029678170342) |
| IA-01 | The Bullfinch Group · 2026-07-16 | 표시 없음 | 원문 검토·기관 등록 미완료 | 최신 Bullfinch/The Independent Center 기록은 정파 표시 없음. 원 결과표·표집/방법·3번째 후보 및 본선 기준일 대조 필요. | [발표/자료](https://www.semafor.com/article/07/28/2026/independent-group-eyes-delbenes-seat) |
| IA-02 | Global Strategy Group · 2026-07-19 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. API 표본수가 null; 원문 표본·지역구 문항을 확인해야 함. | [발표/자료](https://static.notus.org/27/58/c93f2d1946c0814f583fa25c7a31/hmp-ia-02-poll.pdf) |
| MI-04 | Ragnar Research Partners · 2026-03-14 | REP | 원문 검토·기관 등록 미완료 | 최신 REP 표시 조사 문항이 후보명 없이 Dem/Rep. 이전 발표는 2025년. 후보 지지율로 변환 금지. | [발표/자료](https://www.nytimes.com/interactive/polls/michigan-us-house-4-polls-2026.html) |
| MI-07 | Global Strategy Group · 2026-08-13 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 최신 원문 후보 대진·방법론 확인. 이전 경선 후보·가정 대진과 분리. | [발표/자료](https://www.thehousemajoritypac.com/news/hmp-poll-william-lawrence-leads-tom-barrett-in-mi-07) |
| MI-10 | Global Strategy Group · 2026-08-13 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 원 발표·의뢰자·방법론과 실제 후보 대진 확인 후 참고 전용 검토. | [발표/자료](https://hub.nationaljournal.com/welcome-to-the-trump-midterms) |
| MN-01 | GBAO Strategies · 2026-09-21 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 공식 본선 대진 및 소셜 요약의 원 발표문·방법론 필요. | [발표/자료](https://bsky.app/profile/the-downballot.com/post/3mwbqbuzrn22f) |
| NJ-07 | Z to A Research · 2026-05-26 | DEM | 원문 검토·기관 등록 미완료 | 314 Action 의뢰·DEM 표시. 경선 전 발표; 실제 본선 시점의 새 조사 및 원문 필요. | [발표/자료](https://newjerseyglobe.com/polling/pro-shah-groups-poll-also-found-bennett-leading-kean/) |
| NY-01 | Public Policy Polling · 2025-12-11 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시, 2025년 성인 표본. 현재 LV/RV 본선 전망으로 사용 불가. | [발표/자료](https://www.thehousemajoritypac.com/news/new-hmp-polling-shows-nick-lalota-vulnerable-in-november) |
| NY-04 | Impact Research · 2026-02-17 | 표시 없음 | 원문 검토·기관 등록 미완료 | 정파 표시 없으나 문항은 후보명 없이 Rep/Dem. 후보 지지율로 치환 불가; 실제 후보별 본선 조사 필요. | [발표/자료](https://protectingamericanconsumers.org/wp-content/uploads/2026/02/IMPACT-NY-2026-Poll.pdf) |
| OH-01 | Quantus Insights · 2026-08-24 | 표시 없음 | 원문 검토·기관 등록 미완료 | 정파 표시 없는 Quantus 기록. 공개 페이지는 제목/탐색 영역만 수집됨; 결과 본문·방법론 확보 후 개별 발표 검토. | [발표/자료](https://quantusinsights.org/polling/f/new-quantus-insights-survey-ohio%E2%80%99s-1st-district-is-up-for-grabs) |
| OH-09 | DCCC Targeting and Analytics Department · 2026-09-23 | DEM | 원문 검토·기관 등록 미완료 | DCCC 자체 조사·DEM 표시. 전체 원문·방법론 확인 후 참고로 검토; 독립 조사로 집계하지 않음. | [발표/자료](https://dccc.org/dccc-polling-memo-oh-09-is-a-dead-heat/) |
| PA-08 | Lake Research Partners · 2026-06-23 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 6월 원 발표·방법론 확보 및 최신 독립 조사 탐색. | [발표/자료](https://www.politico.com/newsletters/playbook/2026/06/26/wes-moores-vision-for-america-00977774) |
| TN-09 | Hart Research Associates · 2026-09-03 | DEM | 원문 검토·기관 등록 미완료 | Tennessee Rise 의뢰·DEM 표시. 공식 후보 명부와 공개 Drive 발표문·방법론 대조 필요. | [발표/자료](https://drive.google.com/file/d/13E6k34GmPoJLpQuFn4E-BRFI49esOBoQ/view) |
| TX-35 | Normington, Petts & Associates · 2026-08-31 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 원 발표·방법론·후보 대진 대조 후 참고 전용 검토. | [발표/자료](https://hub.nationaljournal.com/can-democrats-school-ramaswamy-in-ohio) |
| VA-02 | Tulchin Research · 2026-07-13 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 7월 원 PDF·방법론 확인, 최신 독립 조사 우선. | [발표/자료](https://www.politico.com/f/?id=0000019f-918b-d49c-ad9f-9fbb88d00000) |
| VA-05 | The Washington Post/George Mason University Schar School of Policy and Government · 2026-09-28 | 표시 없음 | 원문/API 수치 불일치 | 원문 Perriello 45와 API 46이 불일치. 공식 결과표/교차표로 정정 여부 확인 전 보류; 지지도 임의 정정 금지. | [발표/자료](https://www.washingtonpost.com/politics/2026/10/01/shannon-taylor-has-edge-over-rob-wittman-virginia-house-district-post-poll-finds/) |
| WI-01 | Impact Research · 2026-10-01 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 소셜 요약의 원문·방법론 및 API Bryan Steil/공식 Brian Steil 명칭 확인. 별도 DCCC 조사도 참고 전용. | [발표/자료](https://bsky.app/profile/the-downballot.com/post/3mwyouhbwg22k) |
| WI-03 | FM3 Research · 2026-06-25 | DEM | 원문 검토·기관 등록 미완료 | HMP 의뢰·DEM 표시. 6월/2025년 발표 원문 검토 및 최신 독립 조사 탐색. | [발표/자료](https://x.com/cjwarnke/status/2074099699020128352?s=20) |

알래스카 구분 원문: [AARP 2026 Alaska 발표](https://www.aarp.org/pri/topics/voter-research/politics/2026-midterm-election-poll-alaska/). 원문상 처음 선택과 재배분 결과가 별개다. 검색으로 확인된 원문 설명을 사용했으며 직접 페이지 접근은 403으로 실패했다.

## 검증 및 운영 상태

- Python polling 122개, JS 선거 계약 51개, 소유권 범위 6개, 배포 수집기 연결39개 검증. 최종 실행 결과는 PR 검사에서 재확인.
- 제한적인 사용자 지시 범위 예외: 현재 브랜치의 polling workflow만 허용. deploy.yml·공용 ownership guard·다른 workflow·UI·Worker 변경 권한은 추가하지 않았다.
- 매일 수집의 운영 적용은 main 병합이 필요하다. 해당 병합과 이후 수집은 배포와 연결되므로 배포 보류 해제를 확인하기 전 실행하지 않는다.
