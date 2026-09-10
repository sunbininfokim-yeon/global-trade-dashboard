# PR #271 데이터 후속 인수 — 2026-09-10

## 완료 범위와 남은 범위

UI 정본은 `public/data/usa_election_finance_index_v1.json`이다. `usa_superpac_index_v1.json`은 폐기하지 않는다. FEC 수집 원본 단계로 유지하며 `pipeline_role=upstream_source_snapshot`, `consumer_index`로 용도를 명시했다. 성공 수집 뒤 남던 `reason_ko=전국 수집 전` 문구를 제거했다. 파일 개수에는 과거 불변 버전도 포함되므로 수집 상태는 인덱스의 현재 참조로 판단해야 한다.

주지사 전국 수집은 **완료되지 않았다**. 자동 어댑터는 CA·WA 2개 주이며 나머지 48개 주는 미연결이다. `unsupported`를 실제 0 또는 단순 관측 없음으로 표시하면 안 된다. 각 레이스 `coverage_note_ko`, 인덱스 `governor_source_directory`에 수집 상태와 공식 접속 경로를 제공한다.

## P1 — CA 실제 자료 추가, WA 유지

- CA 공식 일일 ZIP: https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip
- 구조·정정 규칙: https://campaignfinance.cdn.sos.ca.gov/calaccess-documentation.zip (FAQ 6번: 캠페인 정정본 전체 대체, 가장 큰 AMEND_ID 사용)
- `CVR_CAMPAIGN_DISCLOSURE_CD` 최신 표지와 `S496_CD`를 FILING_ID + AMEND_ID로 연결하고 OFFICE_CD=GOV, FORM_TYPE=F496만 사용한다. 표지 합계/설명 속 누계 대신 S496 AMOUNT를 합산한다. 메모 제외, 중복 식별자 발견 시 발행 실패, HTTP Range + If-Match/ETag로 동일 원본 버전을 고정한다.
- 2026 스냅샷: 213항목, 지지 **$51,354,808.42**, 반대 **$39,612,093.66**. 최신 포함 신고일 2026-06-30. 이는 **선택한 Form 496의 부분 합계**이며 CA 전체 외부지출 또는 캠프 후원금이 아니다. 2025–2026 지출일 기준이다.
- 공식 2026 경선 명부 61명(기명 투표용지 명부, 별도 write-in 제외)을 함께 제공한다. 출처: https://elections.cdn.sos.ca.gov/statewide-elections/2026-primary/cert-list-candidates.pdf
- Form 496 후보 ID가 비어 있어 같은 회기·직위의 전체 이름이 정확히 일치하는 경우만 공식 명부에 연결했다. 대소문자/공백 외에는 추정하지 않는다. Betty Yee, Stephen Hilton, Tony Thurmond, David DeJute 신고 17항목은 이름만 확인된 별도 대상으로 보존한다. 공식 후보와 동일인이라는 근거가 확보되면 명시적 별칭 교차표로 연결할 수 있다.
- 후보 카드 65개 = 공식 명부 61 + 미연결 신고 이름 4. 금액 없는 후보는 null. 정당을 연결한 경우 `party_basis=certified_primary_ballot`이며 신고 당시 정당/본선 진출을 뜻하지 않는다.
- CA와 WA 금액 분류는 `state_independent_spender_unclassified`. 연방 슈퍼팩 유형 O로 재분류하지 않는다. 경선·본선 용도는 UNKNOWN으로 보존한다.

**UI 변경이 1곳 이상 필요하다.** PR #271의 `usa-state-superpac.js`가 `totals.super_pac`만 읽으면 주 공시 금액은 계속 보이지 않는다. 인덱스 `display_contract.governor_independent_expenditure_categories`의 두 분류를 주지사 섹션에서 읽고, 라벨은 `governor_label_ko`를 사용한다. 둘 다 null이면 null, 한 분류라도 관측되면 관측값만 합산하되 부분 합계로 표시한다. 후보/정당별/레이스 총액 모두 같은 분류 선택을 적용해야 한다. 연방 상하원·대선 슈퍼팩 필터는 기존 `super_pac`을 사용한다.

MA는 공개 IEPAC 요약 응답은 있지만 상세 신고 endpoint가 500을 반환했고, NY 공개 검색의 직접 수집은 403이었다. CA PowerSearch는 2026 검색이 빈 응답이어서 최신성 확인 없이 0으로 쓰지 않았다. CA는 원본 ZIP 경로로 해결했다. 새 API 키는 필요하지 않았다.

## P2 — 지도 연결 보정과 원문 보존

120대 경계 데이터는 이 작업의 기준 main에 이미 병합돼 있었다. 이 PR은 경계 파일을 수정하지 않는다. 해당 선거 연도의 법적 경계와의 완전 일치는 계속 미검증이다.

- 같은 사이클·선거연도, 유일한 FEC 후보 ID 등록 위치, 존재하는 지도 도형을 모두 충족할 때만 미대응 지출을 보정한다.
- Nida Allam: ND-04 → NC-04 (1건 $298.50 지지).
- Brinker Harding: NE-06 → NE-02 (20건 $16,119.51 반대).
- Bobby Hanig: NC-00 → NC-01 (3건 $924.69 지지).
- AK/WY 01 → 00은 해당 회기 후보 명부와 전역구 코드가 뒷받침한다. DC의 00/01은 지도 delegate 코드 98과 연결한다.
- FL59, SC86/89 등 다수 이상 번호는 **지출 없는 FEC 등록 명부**에 있다. 실제 지출이 있는 레이스라는 전제는 맞지 않았다. 주의회가 섞였거나 구 회기 번호라고 단정할 근거가 없어 `invalid_fec_registration_district`로 표시한다. 이는 현행 지도와 불일치한다는 의미이다.
- 빈 district를 00으로 만들던 버그 수정: `UNKNOWN`으로 유지. 다인 지역구 주의 명시적 00도 주 전체 합계로 해석하지 않는다.
- 현재 참조 기준 미대응 하원 레이스 33개이며, 이 33개에는 현재 수집된 지출 기록이 없다. `national.district_audit`에 후보/원문 위치/보정 위치/사유/출처/금액을 기록했다. 각 allocation·registration의 `district_source`에도 같은 근거가 있다. 모든 연방 금액과 원문 기록 수는 보정 전과 동일하다.

## P4 — 공석과 경합 이력

`elections_board_v1.json`의 USA `ui_ready.congress`에 아래를 발행하고 `build_board.py`가 다음 생성에서도 유지하도록 연결했다.

- vacancies: **FL-20 (DEM, 2026-04-21)**, **TX-23 (GOP, 2026-04-14)**. 둘 다 공식 보궐일 Date TBD → null + `unannounced`. 하원 명부/요약도 같은 출처로 갱신하여 재직 433명, 공석 2석으로 일치시켰다. CA14·GA13은 이미 후임 취임했고, 예시 TX18은 2026-02-02 충원된 자리이다.
- 출처: https://clerk.house.gov/xml/lists/MemberData.xml (게시 2026-09-02), https://clerk.house.gov/Members/ViewVacancies
- swing_seats는 **검증된 부분 목록 5개**. AK 하원: 2020 GOP → 2022 DEM → 2024 GOP, 동일 전역구의 최근 3회 본선에서 2회 교체. AZ·MI·NV·WI 상원: 2024 동일 주 대선 GOP / 상원 DEM 교차 결과. 공식 Clerk 2020/2022/2024 결과 PDF와 판정 근거를 각 evidence에 제공한다.
- 상원 교차 의석은 2024년 당선 자리이며 **2026 선거 대상이라는 뜻은 아니다**. `party_basis`는 마지막 검증 본선 당선 정당이다. UI에서 현재 재직 정당이나 2026 접전 예측으로 바꾸지 않는다.
- 전국 하원 대선 지역구별 결과 및 재획정 전후 이력 대응은 미확보. `context_coverage.swing_seats=partial_verified_examples`를 표시하고, 목록에 없다고 비경합이라고 단정하지 않는다. 상원 현재 명부는 기존 2026-08-20 자료를 유지했고 그 날짜를 별도로 표시했다.

## 실행·자동화·배포

```bash
cd 'New for anti/scripts/election_watch'
python3 -m unittest discover -s tests -p 'test_superpac*.py'
python3 build_governor_finance.py --cycle 2026 --state CA
python3 build_superpac_map.py
python3 validate_superpac_map.py
python3 build_congress_context.py
```

기존 설치된 `us_superpac_refresh.yml`은 매일 08:25 UTC 실행하며 `refresh_superpac.py`를 호출한다. 이 PR 병합 후 동일 진입점에서 FEC·WA·CA를 각각 수집하고 실패한 소스의 기존 정상 파일을 보존한다. 주간 선택·새 짝수 사이클 전환·직전 사이클 월간 정정 수집도 유지한다. **CA 금액 수집에는 추가 workflow 수정이 필요 없다.** 다음 회기에도 금액은 수집되지만 공식 후보 명부는 새 회기의 검증 파일을 추가해야 한다.

**공석 자동화는 아직 설치되지 않았다.** `ops/us_congress_context_step.yml`의 실행 스텝을 실제 workflow에 넣고, `config/extracted/usa_congress.json` 및 `public/data/elections_board_v1.json` 두 경로를 git-add 목록에 추가해야 한다. 현재 파일은 검증된 스냅샷이다. 경합 역사 자체는 새 공식 결과와 경계 대응을 검토해 history 파일에 추가해야 하며, 수집 시마다 자동으로 새 당선자를 추정하지 않는다.

UI·활성 workflow·Worker·지도 경계는 이번 수정 범위에 포함하지 않았다. 배포 전 위의 주지사 조회 분류와 공석 자동화 스텝을 Claude가 반영한다. 사용자가 직접 클릭하는 재설정 기능에는 변경이 없다.
