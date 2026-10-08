# 조지아 원문 여론조사·주 공시 접근 검토 — 2026-10-08

기존 Draft PR #492와 전국 50주 수집/하원435구/FEC 갱신을 보존한 후 A그룹의 세 번째 주 GA를 검토했다. UI·Actions·병합·배포를 변경하지 않았다.

## 이번에 실제로 연결한 범위

| 직위 | 조사 경로 | 누적 원문 확인 관측 | 최근7/14일 | 현재 후보 Super PAC 지출 관측 |
|---|---:|---:|---:|---|
| 하원 | 14/14구 | 0 | 0 | 6/14구:01·09·10·11·13·14 |
| 연방상원 | 선거1석 | 3건 | 0 | 후보별 지지/반대 금액 부분 연결 |
| 주지사 | 선거1곳 | 3건 | 0 | 최신 주 공시 접근 차단; 금액null |

하원14구 모두 검토 후보 명부와 API 수집 대상에 연결돼 있다. 10/8 실제 VoteHub1426개 응답에 조지아 하원 조사는 발견되지 않았다. 이는 전 지역에 여론조사가 존재하지 않는다는 뜻이 아니다. API 밖 지역 매체·미등록 조사 발견은 보장하지 않는다. 지출 관측이 없는02·03·04·05·06·07·08·12도0달러/지출 없음 확정이 아니다. 연방공시는10/8 수집·마지막 포함 신고10/6의 기존 유효 자료와 후보ID를 보존했다.

## 조사 원문 검토

- [BIG DATA POLL](https://www.bigdatapoll.com/blog/peach-state-poll-jon-ossoff-opens-up-lead-over-mike-collins-in-georgia/):9/21–23 LV678·RV712. 초기LV 투표 의향은 상원 Ossoff52.2/Collins41.0, 주지사 Jackson48.7/Bottoms46.7. 기존 API에는 미정층 재질문 후 양당100% 수치가 들어 있어 참고 전용이었다. 현 응답fingerprint에 묶어 초기 응답으로 바꾸고 API 원래 값과 이전 검토를 보존했다. 동일 조사 두 문항을 별도 조사 승수로 더하지 않는다. Lucid/CINT·L2 출처 및40%온라인/60%전화·문자, 가중 변수·발표 오차4.0pp/95%는 공개 범위만 기록하며 모델 타당성·후원자 독립성은 검증하지 않았다.
- [InsiderAdvantage](https://insideradvantage.com/insideradvantage-georgia-survey-jackson-leads-by-two-in-race-for-governor-ossoff-leads-by-eight-in-senate-contest/):9/22–23 LV1200,9/25 발표. 상원50/42·주지사48/46·미정8/6을 원문과 대조했다. 문자/패널 혼합·연령/인종/성별/정당 가중을 기록했다. 숫자 오차범위·의뢰자·표집틀·패널 모집은 미공개로 남긴다. 자체 기관 인덱스에서 연결한 공개 본문은 읽었지만 로컬 직접HTTP는 시간 초과여서 HTML SHA를 만들지 않았다.
- [Wick](https://wick.io/research-georgia-election-survey-june-2026):6/27–30 LV1175. [공식 결과표](https://wick.io/assets/research-georgia-election-survey-june-2026-results.pdf)3쪽 Q9/Q11의 초기 투표 의향과 표본을 시각 대조하고 별도 방법·설문 문서를 내려받아 SHA를 기록했다. 상원46.7/42.9·주지사43.2/42.7. Q10/Q12 미정층 후속·호감도·후보 특성 문항을 합치지 않는다. 검토된 본선 수집 기간 전이므로 누적 참고 전용이며7/14일 우세에서는 제외한다. 의뢰자·모집·가중 목표·발표 오차의 통계 모델은 미확인이다.

6건 중4건이 집계 적격,2건이 과거 참고다. 모두14일 창 밖이므로 최근 우세·색·의석 전망을 생성하지 않는다. 전국 누적 표시는69→73건(적격55→59·참고14 유지)이다. 기존 GA Wedgewood2건은 기관 신원 미검증 보류를 유지한다. AARP 원문 접근403은 공개 원본 확인 전 편입하지 않았다.

InsiderAdvantage·Wick은 책임 기관과 자체 도메인을 등록했다. 이후 해당 기관의 새 조사가 VoteHub에 게시되고 후보·기간·모집단·명시적 내부/당파성·의뢰자 검사를 통과하면 자동 수집된다. 새 레코드는 `partial`로 표시하고 원문 수치 대조/정확도 등급을 자동 부여하지 않는다. 미검토 의뢰자·공유 문서 도메인은 자동 허용하지 않는다. 이번6건의 수치가 바뀌면 fingerprint 검사로 재검토 전 보류하고 과거 검토 완료 표시도 상속하지 않는다.

감사 입력: `usa_election_poll_release_reviews/2026/GA-primary-20261008.json`. 현재 공개 API6건·수정 전 검토·기관 원문 수치·문항·파일 SHA와 로컬 접근 실패를 분리했다.

## 공식 주 공시의 남은 장애

[조지아 윤리위원회 공식 홈페이지](https://ethics.ga.gov/)는 [PeachFile](https://peachfile.ethics.ga.gov/)와 Legacy Records Search를 별도로 안내한다. 최신 포털은 일반 브라우저에서도 The request is blocked 화면, 직접HTTP에서도403이다. 실제 자동 점검 시각은 2026-10-08T11:02:39.142006+00:00이다. 과거 지출 검색과 독립위원회 명부는200이지만, 이를2026 최신 공시나 후보별 금액으로 집계하지 않았다.

`refresh_governor_source_access.py --state GA`는 검토된 공식 경로만 재확인하고 `usa_governor_source_access/2026/GA.json`에 현재/과거 접근 상태를 분리한다. 접근 차단403·일시 장애429/5xx·주소 검토 필요404를 구분한다. 정상 응답도 `public_endpoint_reachable_mapping_required`이며 금융 수집 완료가 아니다. 장애 시 마지막 접근 성공 시각과 기존 유효 금융 파일/원래 기준일을 보존한다. 현재 접근 실패 종료코드1은 예상된 장애 보고다.

공식 후보별 독립지출 행·선거 단계·정정·배분·주 신고 식별을 검증하지 못해 주지사 금액은null이다. 보조 사이트 GA FastMoney가 공개한 자료에는 복수 후보 거래금액을 나누는 파생 처리가 있고 직접 확인한 주 공식 원문 링크가 없어 후보별 관측 금액으로 편입하지 않았다. 기금 수입이나 전체 집행액을 후보 지지금액으로 대체하지 않는다. 현재 장애는 FEC 키 부족이 아니며 새 주 API키/유료권한 필요 여부도 확인되지 않았다.

## 순서와 재실행

GA는 `live_poll_sources_reviewed_finance_blocked`이며 완성 처리하지 않는다. 원문/공시 검토 남은48주 = GA1주 장애 + 나머지47주 미완료. index의 `source_review_blocked_states=[GA]`, `next_state_to_retry=GA`, `next_state_to_review=FL`로 나눴다. 이후 주 검토가 GA 장애를 지우지 않는다.

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_governor_source_access.py --state GA
python3 refresh_state_polls.py --state GA --as-of 2026-10-08
python3 refresh_state_evidence.py --state GA --as-of 2026-10-08
```

날짜는 실제 실행 기준일을 사용한다. 포털 접근 성공 후에도 후보별 공시 정상화 어댑터가 추가로 필요하다. API 수집 명령은 주 공시 금액을 수집하지 않는다. daily Actions 변경은 별도 PR #489의 미병합 범위이며 이번 변경을 배포/자동 정기 실행 중이라고 표시하지 않는다.

검증: polling185·금융58·연방6·JS51, 총300개 범위 통과. 접근 장애/이동/일시 장애 구분, 실패 시 원래 날짜·금액 보존, 변경 조사 보류, 중복 미정층 문항 제외, 새 기관/API 레코드·의뢰자 검사, 최근 창에 과거 조사 사용 금지 확인. 다른 주490개 조사 레이스·전역 조사 날짜·금융 관련2952파일을 이전과 대조해 보존을 확인했다.
