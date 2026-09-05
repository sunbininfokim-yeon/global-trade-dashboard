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

## 위원장·구성원: 월간 검증 파이프라인

정치-미국 파일에는 상임위 구성원·위원장·부위원장·ranking member 데이터가 없다. 따라서 이 데이터는 Cursor가 매월 공식 House/Senate roster를 확인해 버전 관리 파일에 추가하고, 동기화 스크립트가 **검증 후에만** Supabase로 적재한다. Cursor가 이름을 알아낸 것만으로 DB를 직접 수정하지 않는다.

1. `data/policy/committee-memberships.example.json`을 복사해 `data/policy/committee-memberships.json`을 만든다.
2. 각 행에는 `committee_id`, `bioguide_id`, 역할, HTTPS 공식 House/Senate/Congress.gov URL을 넣는다.
3. Cursor는 공식 페이지의 표기와 바이오가이드 ID를 대조하고, 변경 내용을 PR로 남긴다.
4. 월간 GitHub Actions가 `node scripts/sync-policy-reference-data.js`를 실행한다. 이 명령은 의원 명단·상임위 디렉터리를 먼저 갱신한 뒤, 위 파일의 외래키와 공식 URL을 확인하고 적재한다.

`coverage.complete: true`는 해당 역할군의 **완전한 스냅샷**일 때만 쓴다. `member`가 포함된 완전 스냅샷은 최소 250행, 리더십 완전 스냅샷은 최소 20행이 아니면 실패한다. 검증과 upsert가 모두 끝난 뒤에만 이번 달에 보이지 않은 기존 행을 `current=false`로 바꾼다. 부분 파일·빈 Cursor 결과가 현직 위원장을 지우지 못하게 하기 위한 안전장치다.

공식 또는 검증된 수동 매핑이 없는 `committee_agency_jurisdictions`는 계속 빈 값으로 남긴다. 법안 수나 키워드로 기관 소관을 추정해 넣지 않는다.
