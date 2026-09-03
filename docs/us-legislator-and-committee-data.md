# 미국 의원·상임위 보강

## 지금 채우는 데이터

`scripts/sync-us-legislators.js`는 이미 같은 저장소에서 정치-미국 화면이 사용하는 `New for anti/public/data/elections_board_v1.json`의 현재 House/Senate 명단을 `us_legislators`로 적재한다. 보존 필드는 바이오가이드 ID, 이름, 정당, 주, 선거구, 원(하원·상원)이다. 따라서 `bills.sponsor_bioguide_id` 및 `bill_vote_members.bioguide_id`와 정확히 연결할 수 있다. 매 실행은 `data_sync_runs`와 `data_sync_state`에 원본 생성 시각·행 수를 남기며, 새 완전 로스터가 모두 upsert된 뒤에만 명단에서 빠진 의원을 `current_member=false`로 전환한다.

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

## 아직 비워 두는 데이터

정치-미국 파일에는 상임위 구성원·위원장·부위원장·ranking member 데이터가 없다. 따라서 `committee_members` 테이블을 만들더라도 이 단계에서는 행을 추정해 넣지 않는다. 다음 소스가 공식 URL과 바이오가이드 ID를 함께 줄 때만 적재한다.

- House Clerk 또는 House committee의 공식 roster
- Senate committee의 공식 roster

그 전까지 UI는 위원장 정보를 “준비 중”으로 표시해야 하며, `committee_agency_jurisdictions`도 공식 또는 검증된 수동 매핑이 없는 경우 빈 값이 맞다. 법안 수로 기관 소관을 추정해 채우지 않는다.
