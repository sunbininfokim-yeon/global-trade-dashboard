# 핸드오프: 선거 UI · 정책&정치 공동 데이터 (Claude 요청 #284에 대한 Cursor 응답)

작성: Cursor · 2026-09-11
원 요청: PR https://github.com/sunbininfokim-yeon/global-trade-dashboard/pull/284
대상: `public/data/elections_board_v1.json`, `public/data/elections_ui_manifest_v1.json`,
`data/policy/committee-memberships.json`, `data/policy/committee-agency-jurisdictions.json`

**공동 사용.** 아래 JSON은 홈페이지 **정책&정치**와 **선거 모듈**이 같이 읽는다.
의원 신원(이름/정당/주/원)은 Congress.gov API가 이미 채우므로 Cursor가 다시 긁지 않는다.
사람이 공식 규칙·로스터를 대조해야 하는 필드만 이 PR에 넣는다.

`scripts/sync-us-legislators.js`는 `elections_board_v1.json`의 House/Senate 명단을
`us_legislators`로 적재한다. 정책 상임위 카드는 `committee_members`와
`committee_agency_jurisdictions`를 읽는다.

## 이 PR에서 채운 것

### C. USA 연방의회 상임위 — 완료 (선거 보드)

Clerk of the House `MemberData.xml` + Senate CVC JSON으로
`config/extracted/usa_committees.json`을 만들고 board의
`ui_ready.congress.committees`에 위원장·위원 명부를 붙였다.
`missing_fields`는 데이터가 있을 때만 비운다.

### C2. 상원 임기 클래스 I/II/III — 완료

Congress.gov member list에는 class가 없다. `usa_senate_terms.json`을
`usa_congress.json` 상원의원 행에 overlay한다.

- `senate_class` / `senate_class_roman` / `term_end` / `next_election_year` / `up_in_2026`
- 100명 전원 class 부여. Class II 33명이 2026-11-03 개선, 임기 만료 2027-01-03.
- 출처: unitedstates/congress-legislators `legislators-current.yaml` (`grade: public_secondary`).
  좌석 class 자체는 헌법 사항이다.

### C3. "Graham, Darline" — 파싱 오류 아님. 고치지 않음

`bioguideId` G000608, South Carolina 상원의원 이름은 **Darline Graham**이
Congress.gov 현직 레코드다. Lindsey Graham으로 되돌리지 않는다.
Class II, `term_end` 2027-01-03, `up_in_2026: true`.
100명 overlay 이름과 congress-legislators YAML은 불일치 0건.

### F. committee_agency_jurisdictions — 부분 시드

파이프라인이 없어서 테이블만 있던 매핑을
`data/policy/committee-agency-jurisdictions.json` +
`scripts/sync-committee-agency-jurisdictions.js`로 넣었다.
House Rule X / Senate Rule XXV에서 **내각급 부처 이름을 조항이 직접 적은** 행만.
법안 건수로 추정하지 않음. `coverage.complete: false`.
`agencies`에 FR 슬러그가 없으면 동기화는 실패하고 행을 넣지 않는다.

### G. committee-memberships.json — 하원 소위 추가, complete는 false 유지

하원 Clerk 소위원회 comcode → congress.gov systemCode가 목록에 있을 때만 행을 추가한다.
상원 소위원회 bioguide는 CVC에 없어서 빠진다.
`coverage.complete`는 **false**로 둔다 (자동 비활성화 안전장치).
코드 기준: member 포함 완전 스냅샷 ≥250행, 리더십만 ≥20행 — 못 채우면 false.

## 아직 이 PR 밖 (원 #284 A/B/D/E)

- A. IND/TWN/ZAF/NGA/IDN/TUR/SAU/ARE 의회 live_composition
- B. IRN majlis
- D. KOR 해수부·중기부 장관 소스 충돌
- E. 50개 주 `state_legislature.raw` 위키 잔재

## 확인

```bash
cd "New for anti/scripts/election_watch"
python3 -m election_watch.extract_usa_committees
python3 -m election_watch.extract_usa_senate_terms
python3 run_refresh_cycle.py --build-derived
python3 -m unittest tests.test_extract_usa_senate_terms

cd ../../..
node scripts/lib/committee-membership-roster.test.js
node scripts/lib/committee-agency-jurisdiction-source.test.js
node scripts/build-committee-memberships.js
```

매니페스트: USA `screens.legislature_detail.missing`가 비고,
`ui_ready.congress.missing_fields`가 비면 C 완료.
상원 행에 `senate_class`가 있으면 C2 완료.

## 지켜줄 것

- UI 파일(`New for anti/{app.js,index.html,style.css}`, `js/elections/**`)은 건드리지 않음.
- 클라이언트 조인 금지. 정당명/의석/class는 board JSON에 미리 붙인다.
- 확보 못 한 필드는 null + missing. 추정치로 채우지 않음.
