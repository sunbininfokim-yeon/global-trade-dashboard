# 인도네시아 법령 효력·원 부처 목록 인수

이번 변경은 원문에 근거한 시행·개정·폐지·경과조치 표시와 원 부처 다섯 곳의 실제 연결 점검이다. `policy_idn`만 사용한다. 기존 PR #633은 이미 병합됐으므로 `codex/idn-legal-effect-20261020`에서 분리했다. UI·사이트 병합/배포는 Claude 인수 대상이다.

## 실제 DB 반영

- `20261019152914_indonesia_policy_legal_effect.sql` 적용. 운영 migration 본문과 로컬 파일 MD5: `9972fee2bd57b09a32e7e2328d665f62`.
- `policy_idn.legal_effect_findings`: 원문 버전·URL·문자 그대로의 발췌·날짜 발췌·검토일을 갖는 변경 불가 근거 17건, 대상 10개. 같은 pack 재실행 시 신규 0건.
- 대상 10개 중 본문 저장 문서 7개, 본문 없는 역사적 인용 대상 3개. 후자는 검색 가능한 본문을 새로 확보한 것으로 세지 않는다. 검토 후보 사전은 102→103개.
- 문서 68개 / 버전 76개 유지. 원래 `legal_status` 68개 모두 `unverified` 유지. 68개 전체를 현행법으로 인증한 작업이 아니다. 이번 작업의 유료 AI 호출은 0회다.
- 근거 테이블 크기 106,496 bytes(조회 시점, 인덱스 포함). RLS 활성화, anon/authenticated 테이블·RPC 접근 거부, 서비스 역할만 조회/추가. Supabase security advisor의 `rls_enabled_no_policy` INFO는 비공개 서비스 전용 설계와 일치한다. [공식 설명](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).

| 대상 | 원문 검토 결과 | 적용일 근거 |
|---|---|---|
| Perpres 10/2021 | 49/2021에 의한 개정 조항 | 2021-05-25 |
| PP 96/2021 | 25/2024 및 39/2025에 의한 개정 조항 | 2024-05-30, 2025-09-11 |
| Perpres 61/2015 | 132/2024 제33조 전부 폐지·관리기관 경과조치 | 2024-10-18 |
| Perpres 44/2020 | 16/2025 제28조 전부 폐지·기존 인증/시행규칙 경과조치 | 2025-03-19 |
| Perpres 191/2014 | 132/2024 제30조의 제15조 제2항 관련 부분만 폐지 | 2024-10-18 |
| Perpres 49/2021, 132/2024, 16/2025, PP 25/2024, 39/2025 | 공포일 시행 확인, 후속 개폐는 미확인 | 각 공포일 |

날짜와 분류는 검토된 입력이다. 임베딩 모델 또는 정규식이 법적 효력을 최종 판정하지 않는다. Perpres 16/2025는 추출 본문의 시행 문구 순서가 훼손되어 원 PDF 17쪽을 시각 검토했다. `reviewed_pdf` 근거는 DB에 저장된 원 PDF SHA256과 일치해야 한다. 원문을 문법상 자연스럽게 고쳐서 인용하지 않는다.

`public.idn_legal_effect(text[], date)`는 최대 50개 문서의 근거를 조회한다. 개정은 폐지와 구분하며, 시행 전/날짜 미확인/일부 폐지/전부 폐지/명시적 기간 종료/상충 근거/미확인을 구분한다. 이전 시행 후 나중에 폐지된 정상 이력은 상충으로 오인하지 않는다. 기간 종료 판정은 법령 전체에 대한 명시적 종료 근거를 검토한 경우에만 입력한다. 새 본문 버전이 저장되면 이전 해시의 근거를 제외하고 제외 건수를 보여준다. `as_of`는 법적 적용일 기준 조회이며 당시 알고 있던 정보만 재현하는 시점 데이터베이스는 아니다. 기본일은 DB 날짜이므로 자정 경계·현지 기준일이 중요한 외부 검토는 `p_as_of`를 명시한다.

`current_validity_confirmed=false`는 후속 개폐 전수 검토를 통한 현행 유효성 인증을 하지 않았다는 뜻이다. 시행일 확인만으로 ‘현재 유효’를 표시하지 않는다. 구법 폐지를 기존 인증서·허가·하위 규정 전체 소멸로 해석하지 않는다.

API는 `/api/idn/legal-effect?ids=...`와 검색/상세의 선택적 효력 근거를 제공한다. 근거 조회 실패 시 기존 검색 순서·필터·문서는 유지하고 `legal_effect_available=false`를 반환한다. 검색 카드 및 상세에서 구분된 라벨·원문·시행일·검토일·경과조치를 확인할 수 있다. 기존 공유 Worker는 수정하지 않는다.

## 원 부처 5곳 실측

체크 자료: `scripts/indonesia_policy/ministry-verification-20261019.json`. 체크는 2026-10-19 UTC / 한국시간 19일 밤~20일 새벽 작업 범위이다. 오류는 문서 0건이라는 뜻이 아니다.

| 원 부처 | 실제 결과 | 자동 목록 상태 |
|---|---|---|
| [ESDM 에너지광물자원부](https://jdih.esdm.go.id/) | 로컬 DNS 실패. 별도 공식 웹 조회는 점검 안내 반환 | 보류 |
| [Kemendag 무역부](https://jdih.kemendag.go.id/peraturan) | 원 목록·실제 페이지 이동 확인. 표시 총 2,406건 | `kemendag_pages` 연결, 10페이지/96건 저장, partial |
| [Pertanian 농업부](https://jdih.pertanian.go.id/) | HTTP 403 | 보류, 재시도/우회 없음 |
| [Kemenperin 산업부](https://jdih.kemenperin.go.id/) | 연결 시간 초과 | 보류 |
| [Kemenkeu 재정부](https://jdih.kemenkeu.go.id/) | 홈페이지 및 공식 메뉴의 `/search?bentuk=Peraturan+Menteri&order=desc&teu=Kementerian+Keuangan` 로컬 읽기 시간 초과. 웹 조회에서는 해당 필터 목록을 확인했으나 수집기 페이지 이동은 검증 못 함 | 보류 |

무역부 목록의 2,406건은 광업/팜유에 한정되지 않는 원 부처의 전체 목록 표시 숫자다. 최신/마지막 페이지 등의 실제 링크를 따라 수집한 10페이지는 연속된 최신 100건이 아니다(마지막 페이지 6건 포함). 96건 모두 제목/상세 URL/게시자 상태를 보존했으며, 긴 slug는 잘라 중복시키지 않고 상세 URL SHA256을 키로 쓴다. 원 slug도 메타데이터에 남긴다. 첫 저장의 키 길이 제약 오류는 트랜잭션 전체 롤백됐고, 받은 원문을 다시 해석해 96건을 저장했다. 동일 파일 재실행은 추가 버전 0건이다.

원본은 비공개 로컬 `policy-downloads/indonesia-20261019/kemendag-original-list/raw/`에 있고, 재해석 체크포인트는 `kemendag-original-list-reviewed/catalogue.json`이다. 캐시 재해석 시 실제 응답 관측일을 유지했다. 새 다운로드를 했다고 기록하지 않는다. 보류 4곳도 검증 사유를 source_config에 담아 DB에 기록했다.

총 기관별 카탈로그 행은 2,038→2,134개다. 서로 다른 기관의 재게시 중복을 포함한 수치이며 고유 법령 수가 아니다. 전체 원 부처 5곳 연결이 끝났다는 뜻도 아니다. DJBC의 무역/산업부 분류 목록은 원 부처 연결과 별개다. 원 목록의 `Berlaku`/`Tidak Berlaku`는 게시자 정보로 보존하고, 법령 원문과 검토 없이 현행 효력 판정에 자동 반영하지 않는다. 초안/회의록의 상태값도 시행 법령으로 승격시키지 않는다.

## 검증·다음 순서

Python 31개, Node 23개, 소유권 14개 통과. 실제 DB 연결 브라우저 검증 1개 추가 통과(1360px/390px, 상세·전부/일부 폐지·개정 조회, 가로 넘침 없음, 브라우저 오류 0개). 기존 Worker 경로 검증은 선택적 효력 RPC가 추가된 요청 흐름까지 확인하도록 갱신했다.

1. Claude: 이 PR 검토 후 전용 검색 화면/API와 migration을 main에 병합·배포. 운영 DB migration은 이미 적용됐으므로 중복 배포 시 버전을 확인한다.
2. 무역부: 체크포인트에서 이어 원 목록을 더 수집할 수 있다. 총수 변경/반복 페이지/403/429/구조 변경은 중단하며, 전수 완료 전 `partial`을 유지한다. 이번에 자동 예약이나 메일 발송을 켜지 않았다.
3. 나머지 원 부처: 공식 서비스 복구 또는 실제 공개 피드/목록 경로가 확인된 뒤 adapter를 검증한다. 상세 다운로드 API가 존재한다는 사실을 전수 목록 API 검증으로 대신하지 않는다.
4. 나머지 법령: 확보한 원문에서 후속 개폐와 공포/시행일·경과조치를 추가 검토한다. 현재 61개 저장 문서에는 이번 효력 근거가 아직 없다. 네트워크 실패나 관계 미발견을 ‘현행 유효’로 채우지 않는다.

```bash
# 읽기 전용 pack 검사
node scripts/indonesia_policy/import-legal-effect.cjs \
  scripts/indonesia_policy/legal-effect-pack-20261019.json --env-file /ABSOLUTE/SERVER_ENV
# 검토를 마친 동일 pack 적용(재실행 가능)
node scripts/indonesia_policy/import-legal-effect.cjs \
  scripts/indonesia_policy/legal-effect-pack-20261019.json --env-file /ABSOLUTE/SERVER_ENV --write
```
