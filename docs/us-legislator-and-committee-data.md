# 미국 의원·상임위 보강

## 지금 채우는 데이터

`scripts/sync-us-legislators.js`는 이미 같은 저장소에서 정치-미국 화면이 사용하는 `New for anti/public/data/elections_board_v1.json`의 현재 House/Senate 명단을 `us_legislators`로 적재한다. 보존 필드는 바이오가이드 ID, 이름, 정당, 주, 선거구, 원(하원·상원)이다. 따라서 `bills.sponsor_bioguide_id` 및 `bill_vote_members.bioguide_id`와 정확히 연결할 수 있다. 매 실행은 `data_sync_runs`와 `data_sync_state`에 원본 생성 시각·행 수를 남기며, 새 완전 로스터가 모두 upsert된 뒤에만 명단에서 빠진 의원을 `current_member=false`로 전환한다.

원본에서 유효 의원이 400명 미만이면 동기화는 실패하고 기존 의원 행을 바꾸지 않는다. 비어 있거나 부분 생성된 파일이 기존 537명을 한꺼번에 비활성화하는 사고를 막기 위한 가드다.

```bash
node scripts/sync-us-legislators.js
```

## 상임위·소위원회

`scripts/sync-committees.js`는 공식 Congress.gov의 committee directory와 committee detail을 읽어 `committees`를 보강한다. detail 응답이 child committee 목록을 제공하면 `parent_committee_id`를 채운 소위원회 행도 적재한다.

```bash
node scripts/sync-committees.js
```

이 스크립트는 `CONGRESS_API_KEY`(또는 `DATA_GOV_API_KEY`), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`를 사용한다. API 속도 제한을 위해 기존 Congress 동기화와 같은 요청 간격을 적용한다.

## 자동화 계약

스케줄러가 호출할 진입점은 아래 하나다. 내부에서 **정치-미국 최신 명단 → Supabase 의원 테이블 → 공식 Congress.gov 상임위/소위원회** 순으로 실행한다. 각 하위 작업은 개별 상태·실패 기록을 남기므로 한 소스가 실패해도 원인을 분리해 재실행할 수 있다.

```bash
node scripts/sync-policy-reference-data.js
```

초기 백필 기간에는 로컬 Mac에서 필요할 때 이 명령을 실행하고, 백필이 끝난 뒤 GitHub Actions의 주기 작업은 이 명령을 호출하면 된다. `.github/workflows/**`는 Claude 소유이므로, 스케줄·Secrets 연결은 아래 실행 계약을 그대로 Claude가 워크플로에 연결한다.

```text
node scripts/sync-policy-reference-data.js
필수: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, CONGRESS_API_KEY 또는 DATA_GOV_API_KEY
선행: 정치-미국 파이프라인이 elections_board_v1.json을 최신 상태로 생성
```

## 위원장·구성원: 공식 roster 검증 파이프라인

정치-미국 파일에는 상임위 구성원·위원장·부위원장·ranking member 데이터가 없다. 따라서 이 데이터는 Cursor가 공식 House/Senate roster를 확인해 버전 관리 파일에 추가하고, 동기화 스크립트가 **검증 후에만** Supabase로 적재한다. Cursor가 이름을 알아낸 것만으로 DB를 직접 수정하지 않는다.

미국 상임위 사보임은 한국 국회처럼 자주 일어나지 않는다. 기본 갱신 주기는 **분기 1회**다. 다만 **1분기**(새 의회 조직 기간, 보통 1–3월)에는 배정이 확정되는 동안 **월 1회** 확인한다. `.github/workflows/**`는 Claude 소유이므로 이 주기를 워크플로에 넣는 변경은 이 문서의 실행 계약만 따른다.

1. 공식 원천을 로컬 캐시에 받는다. 캐시 디렉터리 `.cache/official-rosters/` 는 커밋하지 않는다.

```bash
node scripts/fetch-committee-membership-rosters.js
node scripts/build-committee-memberships.js
git diff --exit-code -- data/policy/committee-memberships.json
node scripts/lib/committee-membership-source.test.js
```

2. 각 행에는 `committee_id`, `bioguide_id`, 역할, HTTPS 공식 House/Senate/Congress.gov URL을 넣는다.
3. Cursor는 공식 페이지의 표기와 바이오가이드 ID를 대조하고, 변경 내용을 PR로 남긴다.
4. 월간 GitHub Actions가 `node scripts/sync-policy-reference-data.js`를 실행한다. 이 명령은 의원 명단·상임위 디렉터리를 먼저 갱신한 뒤, 위 파일의 외래키와 공식 URL을 확인하고 적재한다.

`coverage.complete: true`는 해당 역할군의 **완전한 스냅샷**일 때만 쓴다. `member`가 포함된 완전 스냅샷은 최소 250행, 리더십 완전 스냅샷은 최소 20행이 아니면 실패한다. 검증과 upsert가 모두 끝난 뒤에만 이번 달에 보이지 않은 기존 행을 `current=false`로 바꾼다. 부분 파일·빈 Cursor 결과가 현직 위원장을 지우지 못하게 하기 위한 안전장치다.

현재 커밋된 `data/policy/committee-memberships.json`은 **parent committee만** 넣고 subcommittee는 빼 두었으므로 `coverage.complete` 는 **false**다. 월간 동기화는 신규·변경 행을 upsert하지만, 명단에서 사라진 기존 의원을 자동 비활성화하지 않는다. parent committee 범위만 안전하게 reconcile하려면 별도 스키마/파이프라인 개선이 필요하다.

### 캐시 재현 (API 키 없음)

| 캐시 파일 | 공식 URL | 받는 방법 |
|---|---|---|
| `.cache/official-rosters/MemberData.xml` | https://clerk.house.gov/xml/lists/MemberData.xml | `fetch-committee-membership-rosters.js`가 HTTPS로 저장. `<MemberData>`와 `<bioguideID>`가 있어야 한다. |
| `.cache/official-rosters/cvc_member_data.xml` | https://www.senate.gov/legislative/LIS_MEMBER/cvc_member_data.xml | 같은 스크립트가 HTTPS로 시도한다. Senate가 자동 요청을 403으로 막으면 브라우저에서 원문을 열어 이 경로로 저장한 뒤 스크립트를 다시 실행한다. `<senators>`와 `<bioguideId>`가 있어야 하며 HTML Access Denied 페이지는 안 된다. |
| `.cache/official-rosters/senate-cvc-memberships.json` | 위 Senate XML을 변환한 결과. 별도 원천이 아니다. | 각 `<senator>`의 `<bioguideId>`와 `<committee code="..." position="...">`만 JSON 행으로 옮긴다. 의원 이름은 매칭 키가 아니다. |

committee_id의 House clerk 코드 ↔ Congress.gov system code 대응은 https://www.congress.gov/committees 목록으로 확인한다. 목록에 없는 위원회(예: House `QJ00`, Senate `JSIK00`)는 넣지 않는다.

환경 변수로 캐시 경로를 바꿀 수 있다. `HOUSE_MEMBER_DATA_XML`, `SENATE_CVC_JSON`, `SENATE_CVC_XML`, `COMMITTEE_ROSTER_CACHE_DIR`.

공식 또는 검증된 수동 매핑이 없는 `committee_agency_jurisdictions`는 계속 빈 값으로 남긴다. 법안 수나 키워드로 기관 소관을 추정해 넣지 않는다.
