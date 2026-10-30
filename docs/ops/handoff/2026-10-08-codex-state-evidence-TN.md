# 테네시 순차 연결 보강 — 2026-10-08

사용자가 뉴욕 다음 주 진행을 승인해 Draft PR #492에서 TN을 이어서 보강했다. UI·workflow·병합·배포는 변경하지 않았다. 다음 원문/공시 검토 주는 GA이며 TN의 금액 보류를 완료된 전국 수집으로 표시하지 않는다.

## 확인한 범위

| 직위 | 선거 대상 | 누적 조사 | 현재 후보 지출 연결 | 남은 범위 |
|---|---:|---:|---:|---|
| 하원 | 9구 | TN-09 1건 | 4개 지역구 | 나머지8구 API 관측 미발견, 나머지5구 현재 후보 대상 지출 미관측/미연결 |
| 상원 | 1석 | 1건 | 1석 | 최근7/14일 조사 미확보 |
| 주지사 | 1곳 | 2건 | 금액 보류 | 공식 CSV 거래 식별·정정 관계·대상 직위/선거연도 추가 검증 |

TN 전체4건은 최근7일/14일 밖 누적 참고다. 기관 수나 새 수집 실행일을 최신 조사·당선확률로 바꾸지 않는다. 하원 후보9구를 기존 검토 공개 명부에서 ballot review 계약에 편입했으며 공식 전체 투표용지 인증으로 표시하지 않는다. API는6건 발견해4건 편입했고 다른 주의 기존 poll race와 전역 기준일을 그대로 보존했다.

## 여론조사 원문

- [Hart TN-09 메모](https://drive.google.com/file/d/13E6k34GmPoJLpQuFn4E-BRFI49esOBoQ/view):9/1–3, LV400명, 초기 투표 의향 Pearson44/Taylor48. `Justin J. Pearson`의 원문 표기 `Justin Pearson`을 출처와 함께 명시적으로 연결했다. 뒤의 호감/메시지 반응 수치는 투표 의향으로 사용하지 않는다. 방법·가중·표본틀·오차범위 미공개, API DEM 의뢰 표시는 참고 전용 사유로 남긴다.
- [TargetSmart 의뢰기관 발표](https://www.tnprogressfund.com/polling)와 [원문 표](https://www.tnprogressfund.com/s/TSmart_TN-Statewide-Baseline_Toplines_20260914.pdf):9/9–12, LV600명, Q12 Blackburn45/Green36/Hatley10/Pinkston2. API Hatley19를 원문10으로 정정했다. API 전체 레코드 SHA와 정정 전·후 값, PDF SHA·문항/방법론 쪽수를 보존하며 레코드가 바뀌면 정정을 다시 검토한다. 임의 이름 변경/후보 추가는 허용하지 않는다. 의뢰·당파성 참고 자료여서 우세 집계에는 사용하지 않는다.
- [Targoz/Beacon 원문](https://tennsight.com/wp-content/uploads/2026/08/Beacon-Poll-of-TN-August-2026-Crosstabs-Party-Ideology-and-Region-1.pdf):8/15–26, RV 표44·47쪽을 시각 대조했다. 주지사 문항1149명·46/33, 상원 문항1157명·51/31. 발표 페이지의 LV55/34·58/33을 RV 값과 합치지 않는다. 원문 PDF SHA를 검토 기록에 추가했다.

두 신규 관측은 원문 검토된 개별 레코드만 편입하며 Google Drive 같은 공유 도메인 전체를 기관 허용 목록에 넣지 않는다. 원문 공개 수준과 기관 정확도 등급은 구분하며 검증하지 않은 정확도 등급은 null이다.

## 테네시 공식 공시 수집

[TNCAMP 공개 독립지출 검색](https://apps.tn.gov/tncamp/public/cesearch.htm)의 폼·공개 세션·CSV 내보내기를 사용한다. 로그인이나 API 키가 필요하지 않았다. 2025년2건·2026년399건의 전체 CSV 행 수를 공식 검색 결과 건수와 대조하고 원본 SHA 및 공식 인코딩을 보존했다. 주지사 명부와 일치하는 후보명 발견27건(Blackburn26·Green1), 이 중 같은 내역으로 반복된 Blackburn3건을 확인했다.

검색 CSV에는 거래 고유번호, 정정 전후 관계와 대상 직위가 없으며 선거연도도 비어 있다. 같은 내역을 임의로 중복 제거하거나 복수 지급으로 합산하지 않는다. 신고 원문은 공개 검색 세션에서 접근할 수 있으므로 API 키로 해결할 문제가 아니라 신고 구조/정정 관계의 추가 검증 작업이다. **후보별 지지·반대 금액은 모두 null**로 유지했다. 이 자료는 주 독립지출이며 연방 Super PAC 분류가 아니다.

수집 감사 파일은 `public/data/usa_governor_finance_audits/2026/TN.json`이다. 기존 정상화 금융 `usa_governor_finance/`와 분리했고 주별 evidence에서 `collected_normalization_held`로 연결했다. API/CSV 오류·형식/건수 변경 때 마지막 정상 감사 파일을 덮어쓰지 않는다.

연방 FEC는 이번 작업에서 새 요청을 하지 않았다. 기존 마지막 유효10/5 수집·10/2 신고 자료에 현재 후보 ID를 연결한 범위이며, 로컬 FEC 키가 없는 상태에서 전국 최신 수집으로 표시하지 않는다.

## 실행과 인수

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state TN --as-of 2026-10-08
python3 refresh_governor_finance_audit.py --state TN --cycle 2026
python3 refresh_state_evidence.py --state TN --as-of 2026-10-08
```

원문 검토 기록은 수집 실행과 별개이며 자동 API 실행이 원문 재검토 날짜를 새로 만들지 않는다. NY·TN의 검토된 부분 연결과 나머지48주를 구분하고 `next_state_to_review=GA`로 저장한다. 이 실행기를 Actions에 설치하거나 자동으로 다음 주의 원문 검토를 수행하는 일정은 이 변경에 포함하지 않았다. 일일 전체 여론조사 Actions는 별도 Draft PR #489이며 병합 보류 중이다. #489의 메타데이터 정정과 이 변경의 답변값 정정은 통합 시 원시 API 레코드 기준 SHA를 각각 유지해야 한다.

## 검증

Python polling162·금융58·연방6·JS51(총277) 통과. API 실제6건/편입4건, CSV 실제401건 및 이름 발견27건, 후보별 금액null·최근7/14일 중립·TN 밖 관측/기준일 보존을 확인했다. 정정 값의 원문 일치·변경 API 보류·후보 추가 금지, 단일 주 게시의 기존 자료 보존 및 실물 poll builder 계약 호환, 공개 CSV 건수·열·인코딩 검사를 포함한다.
