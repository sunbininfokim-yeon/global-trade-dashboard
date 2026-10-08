# 위스콘신 WI — 2026-10-09 04:20 예약 작업

TX 기준 bd3bd6b6에서 별도 `codex/wi-state-evidence-20261009` 브랜치로 WI 한 주만 진행했다. 사용자 최신 지시대로 #492에 추가하지 않으며 #499 → #498 → #492에 의존하는 별도 Draft PR이다. 병합·배포·workflow 실행·UI·LETF 편집 없음. AZ05:00/NV06:00 예약은 유지하고 대신 실행하지 않았다. 자료 기준일은 실제 UTC 2026-10-08이고 타주 날짜를 바꾸지 않았다.

## 선거와 후보

하원8선거·주지사1선거를 점검했다. 연방상원은2026 비선거이며 슬롯·조사·전망을 새로 만들지 않았다. WEC 후보 페이지와 연결 공식 최종 명부 https://elections.wi.gov/media/39076/download 에 실제 접근했으나 DNS/transport URLError로 실패했다. 기존 검토 후보와 원래 품질을 유지하며 공식 명부 전수 재검증 완료라고 주장하지 않는다. 접근 가능한 The Green Papers 현재명부는 보조 출처로만 사용했다.

WI01의 공식 DCCC 조사 문서에 나온 Bryan Steil은 기존 후보 Bryan George Steil과 해당 지역구·정당·FEC ID가 일치하는 검토 별명으로 연결했다. API의 Brian Steil 오자는 후보 별명에 추가하지 않았다. WI02 Mark Pocan만 있는 기존 보조 명부는 무투표 당선 확정이나 승자 판정 근거가 아니다. 공식 명부를 확보하면 상대 후보 및 무경쟁 여부를 다시 확인해야 한다.

## 여론조사 원문과 발견 상태

공개 VoteHub API31레코드를 확인했고 특정 발표6건을 원문 검토했다. 관측6건은 주지사5건·WI01하원1건이다. API 운송, 원문 확인, 전망 적격, 참고 및 보류를 구분한다.

- Marquette 9/16–23 LV692: Crowley49/Tiffany46/미정5. 같은 파동 RV843:46/45/미정9를 원문 보완으로 추가했다. L2 등록표본627+SSRS 확률주소패널216, 온라인749+전화94를 방법론에 보존했다. 조사 전체·LV·문항 표본을 혼동하지 않고 가중 빈도표에서 문항 N을 역산하지 않는다. 초기D1과 미정층만 묻는 D2 lean 질문은 별도이며 후자를 두 번째 조사로 넣지 않았다.
- Marquette 8/12–20 LV738:49/44/미정7, RV891:44/44/미정12는 본선 후보 확정 이후의 과거 참고 자료이다. L2 664+패널227, 온라인797+전화94. 8월 자료를 최신 우세로 사용하지 않는다.
- Platform/WPR 8/12–13: 주전체500LV+주의회 경합지역 추가50 oversample. 주지사 초기48/44와 호감도·주의회 질문을 구분했다. 표본틀/LV선별/가중/전체 문항 등이 부족하므로 참고 전용이다.
- DCCC WI01 9/21–23 495LV: Bryan Steil48/Mitchell Berman48/미정5. 공식 공개 PDF와 SHA를 검증했다. 전화+text-to-web, 보고오차4.4pp/95%. 원문은 내부 조사지만 API internal=False였으므로 원 API와 별도 sponsor_review에 충돌을 기록했다. 전체 문항/표본틀/LV선별/가중이 없고 정당 내부 조사여서 전망 집계 제외, 참고 전용이다.

DCCC 원문 https://dccc.org/wp-content/uploads/2026/09/WI-01-DCCC-Analytics-Poll-Memo-Google-Docs.pdf 는 공개 캠페인 발표의 링크로 발견했다. 구독 기사를 우회하지 않았다. 후보 오자 API 레코드는 특정 ID·내용 지문이 일치할 때만 원문 보완으로 대체한다. 이후 수정된 API가 동일 파동·표본·수치·의뢰자와 일치하면 한 번만 남고, 변경된 오자 레코드나 수치 충돌이면 실패하여 마지막 유효 자료를 보존한다. 신규 미래 발표 전체 자동 승인 기능이 아니다.

Marquette PDF 발표문·방법론·설문지와 LV/RV 표, Platform WPR 호스팅 원문, DCCC 문서는 실제 다운로드 및 지문 검증했다. AAPOR 투명성이나 기관 수를 정확도 등급으로 변환하지 않는다. LV와 RV를 따로 보존하고 동일 파동 중복 제거 계약을 유지한다.

최근7일 기본·14일 선택에서 WI의 적격 최근 조사는 모두 부족하다. 최신 편입 조사의 종료일9/23은10/8 기준14일 밖이다. 조사 없음이 아니라 과거/참고/보류와 최근 적격 없음의 구분이다.

보류된 실제 발견3건: WI01 Impact/HMP9/28–10/1, WI03 FM3/HMP6/20–25 및 PPP2025/10/14–15. 각각 의뢰자 원문 방법 미확보 또는 역사적 경선 전 자료이며 최신 전망으로 넣지 않았다. 별도 HMP8/6–9 WI01 메모와 Google Drive 링크도 발견했지만 문서 계약 미검토 상태로 discovery_only에 남겼다. 일부 WisPolitics 구독 경로는 이용권한을 요청하고 해당 수집만 중단했다. 공개 DCCC 원문 편입에는 그 권한이 필요하지 않았다.

## 슈퍼팩·주지사 공시

새 FEC 금액을 재수집하지 않았다. 기존 O Super PAC 후보별 지지·반대 공시를 유지하며 U 단일후보 IE와 V/W hybrid 또는 주별 IE를 섞지 않는다. WI04 Gwendolynne S. Gwen Moore DEM을 기존 후보 ID H4WI04183 및 공시 이름 MOORE, GWEN S로 정확히 연결했다. 보조 명부 기반 신원 검토이며 공식 WEC 신규 검증은 아니다. 기존 관측 본선G2026 지지122.33달러/6행, 경선P2026 지지42.56달러/2행을 분리했다. 총164.89달러는 새 수집금액이나 본선 단독금액이 아니다.

현재 후보 O 지출 관측 하원5/8→6/8, 후보 ID연결19개. WI05/08 미관측을0으로 바꾸지 않았다. 후보캠프가 받은 수입이나 상대후보 지지금액으로 해석하지 않는다.

Wisconsin Ethics Commission 공식 안내의 Sunshine 공개 reports/transactions 경로를 등록하고 재실행 가능한 WI 접근 확인을 추가했다. 실제 서버 접근은 URLError로 실패했고 `source_unavailable`, `candidate_amounts_available:false`이다. 공식 안내상 거래 스프레드시트 내보내기는 있지만 후보별 방향·거래 스키마·정정 검증까지 완료하지 않았다. 주지사 지지/반대 금액은 null로 유지했다. 새 API 키가 필요한 상황은 아니며 서버 접근 복구와 거래 매핑이 남았다.

## 산출과 검증

- 주별 산출 `usa_election_state_evidence/2026/WI-5ca8e6b1275e8ae3.json`, work_status `live_poll_sources_reviewed_finance_blocked`.
- 원문 감사 `usa_election_poll_release_reviews/2026/WI-primary-20261009.json`.
- 실제 접근 영수증 `usa_governor_source_access/2026/WI.json`.
- 로컬 polling260·금융63·연방6·JS51=380검사. 신규8검사는 LV/RV 표본·초기/lean분리·과거와내부조사 제외·API오자 대체/후발 중복/충돌·Moore 선거단계별금액·상원 비선거·접근실패≠0을 검증한다.
- 타주497 poll레이스·46 누적이력·49주 index·기존 금융/감사4642파일 및 타주 후보명부/원래 날짜 보존 검사 통과.

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state WI --as-of 2026-10-08
python3 refresh_governor_source_access.py --state WI
python3 refresh_state_evidence.py --state WI --as-of 2026-10-08
```

WI 예약은 한 번 처리 후 종료한다. 다음 순서는 AZ이며 해당 예약에서 별도로 진행한다. 남은 장애는 공식 명부 접근, 주지사 거래 매핑/접근, 경합 하원 원문 방법론 확보이다. 이번 변경이 모든 미래 조사 자동 승인이나 모든 주의 완전 수집을 의미하지 않는다.
