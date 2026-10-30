# 미국 주지사 후보·독립지출 데이터 보강 (2026-10-07)

TASKS: `T-GOVERNOR-COVERAGE-20261007` · branch: `codex/governor-coverage-20261007`.
사용자 지시: 데이터 보강, 이번 변경 배포 금지. UI·Actions·Worker 변경 없음. 병합·배포·수집 workflow 수동 실행도 하지 않는다.

## 결과와 범위

- 주지사 본선 대진이 검토된 주: 13 → **36개 선거 주**. NGA 33개 주 + 공식 주 선거관리기관 명부 보완 OK·RI·SC. 50개 주 모두 올해 선거한다는 뜻이 아니다.
- 명부를 지도 선거자금 read model과 기존 주간 여론조사 수집기에 함께 연결했다. 신규 API가 발행한 수치도 기존 기관·원문 호스트·선거 단계·대진·표본·중복·품질 검사를 거쳐야 표시된다.
- 실제 여론조사 갱신: 100개 감시 선거, 채택 55건(집계 가능 46, 참고 전용 9), 이전 산출물 대비 신규 관측 6건. OR·ME·NH 주지사 대진 확장뿐 아니라 NV 주지사·ME 상원의 새 발표도 포함한다. 모든 주에 최근 조사가 생겼다는 뜻이 아니다.
- 최근 7일: 단일 기관 수치상 우세 4개 선거. 14일: 여러 기관 수치상 우세 2, 단일 기관 우세 11, 동률 1. 확률·공식 승자·여론조사 품질 등급으로 해석하지 않는다.
- **NY 지출 75건**이 원천 파일에 있었지만 활성 지도 인덱스가 이를 읽지 않았다. 지도 계약을 재생성해 누적 후보별 지지·반대 금액과 원본 근거를 복구했다.
- **CA Form 496**은 `CVR.ELECT_DATE`가 검토한 선거일과 정확히 일치할 때만 `P2026`/`G2026`으로 분리한다. 신고일·지출일로 선거 단계를 추정하지 않는다.

## 주지사 대진 근거

자동으로 읽는 NGA 후보 표: https://www.nga.org/governors/elections/ . 2026 링크가 있는 주 패널만 읽고 과거 결과·미국령·결선 승자 자리표시자를 제외한다. 표의 주 목록이 Cook에 검토된 36개 선거 주와 다르거나 후보 ID가 중복되면 이전 명부를 보존하고 실패한다.

NGA 명단은 주 선거관리기관의 인증 후보 전체 명부가 아니다. 제3당·기입 후보 누락 가능성을 그대로 표시한다. 기존 CA·NY 공식 후보 ID는 정당·회기·직위·전체 이름 또는 검토된 별칭이 정확히 일치할 때만 재사용한다. 공식 ID·원본 근거를 NGA 자료로 낮추지 않는다. 별명·중간이름 차이는 자동 추정하지 않는다.

NGA가 비어 있던 3개 주는 `config/governor_matchups/2026_ballot_reviews.json`의 수동 검토 스냅샷으로 보완한다. **이 3개 사이트의 새 자동 수집기를 설치한 것은 아니다.**

| 주 | 본선 명부의 후보 수 | 검토한 공식 근거·필터 |
|---|---:|---|
| OK | 5 | https://hosting.okelections.gov/electionlist.html · NOVEMBER / 2026 LIST OF ELECTIONS, GOVERNOR. 카운티별 반복된 주 전체 명단을 1회 사용 |
| RI | 5 | https://vote.sos.ri.gov/Candidates/CandidateSearchSummary?Election=18144&OfficeType=549 · GOVERNOR/Statewide, On Election Ballot=Y만 사용. N 및 미등재 후보 제외 |
| SC | 4 | https://vrems.scvotes.sc.gov/Candidate/CandidateSearch?electionId=22596 · 11/3/2026 Statewide General Election, Governor and Lieutenant Governor, Active, 4 of 4 entries. 러닝메이트는 별도 주지사 후보로 넣지 않음 |

OK의 NGA `Cydni Munson` 및 `Primary Runoff Winner`는 사용하지 않는다. 공식 본선 명단의 `Cyndi Munson`·`Mike Mazzei` 및 무소속 3명을 사용한다. SC의 United Citizens/Green, RI 무소속 3명, AK 4인 대진, ME 무소속 후보를 민주·공화 두 명으로 축소하지 않는다. 전 후보 대진을 충족하지 않은 조사는 현재 집계 검사에서 제외될 수 있다.

명부 검토 날짜가 실행 날짜보다 미래이거나 회기·주·직위·선거일·후보 ID·커버리지 합계가 맞지 않으면 발행하지 않는다. 여론조사 실패 상태를 기록하고 마지막 정상 스냅샷을 유지한다.

## 금액 근거와 남은 공백

독립지출은 외부 단체가 후보를 지지/반대하려고 쓴 돈이며 후보 캠프가 받은 모금액과 다르다. 주 지출자를 연방 FEC 슈퍼팩으로 분류하지 않는다.

NY 공식 일일 자료: https://data.ny.gov/resource/e9ss-239a.json · metadata: https://data.ny.gov/api/views/e9ss-239a.json . 검토된 8개 IE 지출자 명부 및 후보별 고유 연결만 사용한다. 입력 101건 중 75건 포함; 제외는 미검토 지출자 14, 복수 후보/버전 중의성 11, 후보 또는 지지/반대 방향 미확인 1.

| NY 후보 | 누적 지지 독립지출 | 누적 반대 독립지출 |
|---|---:|---:|
| Kathy C. Hochul | $13,014,850.23 | $0 |
| Bruce A. Blakeman | $3,016,811.10 | $2,380,037.00 |

**NY 75건 모두 선거 단계 UNKNOWN**이다. 보고 창 이름/신고 날짜를 본선으로 바꾸지 않는다. 본선 후보 옆 G2026 전용 금액 상자는 미확인이고, 위 금액은 누적/단계 미확인 공시에서만 표시된다. 포함된 행 안의 $0은 관측된 방향 합계이고 주 전체 완전성을 의미하지 않는다.

CA 공식 원천: https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip · 필드 설명: https://campaignfinance.cdn.sos.ca.gov/calaccess-documentation.zip . CalFormat 2.20 Cover의 Elect_Date(필드 15), CVR→DB `ELECT_DATE` 매핑을 확인했다. 최신 정정본 전체 교체, memo·범위 밖·삭제 검사, 동일 ETag를 고정한 범위 읽기를 유지한다. 연결 범위는 Form 496이며 Form 460/465 등은 별도 미구현이다.

CA 수집 233건: **G2026 2 / P2026 14 / UNKNOWN 217**. Steve Hilton의 확인된 G2026 지지 지출 $10,648.49, 반대 $0을 본선 상자에 표시한다. Xavier Becerra의 큰 누적 금액은 UNKNOWN이므로 본선 상자로 이동시키지 않는다. 1900년 기본값·빈 날짜·다른 선거일도 UNKNOWN이다.

지도의 50개 주 슬롯은 CA·NY·WA `partial` 3, `unsupported` 47이다. WA에는 올해 주지사 선거 및 2026 포함 지출이 없다. **올해 선거하는 36개 주 중 지출이 관측된 곳은 CA·NY 2개, 나머지 34개는 미연결**이다. 명부 36개를 지출 커버리지 36개로 부르면 안 된다.

- AZ: 공개 Spotlight API 문서는 있으나 실제 `/api`·`/api/cycles`가 2026-10-07에도 HTTP 403. API 키를 새로 넣으면 해결된다는 근거는 없다.
- TX: 기존 CAND 자료는 지지/반대 방향과 독립지출 후보 배분을 확인하지 못해 감사 전용이다. 수집 성공 금액으로 승격하지 않는다.
- GA·FL·TN 등: 공식 검색/공시 경로는 출처 디렉터리에 있으나 후보 대상 지지/반대·정정 규칙이 검증된 어댑터는 아직 없다.
- 0으로 채우지 않는다. 자료가 공개되어 있어도 후보 캠프 모금·단체 총지출·광고 지출을 독립지출 후보별 S/O로 치환하지 않는다.

## 실행·검증·운영

```
cd 'New for anti/scripts/election_watch'
python3 refresh_governor_matchups.py
python3 build_governor_finance.py --cycle 2026 --state NY
python3 build_governor_finance.py --cycle 2026 --state CA
python3 build_superpac_map.py
python3 validate_superpac_map.py
python3 refresh_live_polls.py
```

기존 여론조사 Actions는 월요일 06:10 KST 주간 실행이고 새 명부를 기본 적용한다. 명부 수집 명령 자체를 Actions에 새로 넣지는 않았다. 연방 FEC 자료는 이번에 재수집하지 않았다. 주 소스와 명부 수집에는 새 API 키가 필요 없었다.

테스트: Python 여론조사/대진 94, 슈퍼팩/주 공시 50, JS 전체 선거 계약 44 통과. 지도 validator는 2026 원천 16,171건과 577개 선거 파일의 정수 센트·건수·후보별/선거 단계별/주별 합계·참조를 대조한다. 2024 원천 11건도 보존한다. 후보 대진 추가로 연방 선거 파일 전체를 복제하지 않았다.

로컬 브라우저에서 CA 본선 대진과 $10,648.49, NY 누적 금액, 미확인 단계 분리를 확인한다. 공식 사이트/로컬 검증은 배포 확인을 뜻하지 않는다. **이 브랜치는 검토용으로만 남기고 병합·배포하지 않는다.**
