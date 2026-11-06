# 미국 로비·사안 구현과 데이터 계약

사용자 승인: 2026-11-05 구현·자동 수집 연결, 전 국가·전 산업·전체 가용 이력 수집으로 확장. 2026-11-06 통상적인 변경·승인은 에이전트가 판단하고 Supabase 구조는 작업 후 설명하도록 추가 지시.

## 실제 구현

- `scripts/lobbying/core.py`: FARA 공식 bulk CSV와 LDA JSON 정규화. 국가·산업 수집 제한 없음.
- `scripts/lobbying/sync.py`: FARA 전체 목록 순회, LDA 공식 다음 페이지 순회·별도 refresh, FARA PDF 본문 수집.
- `.github/workflows/lobbying_policy_refresh.yml`: 4시간 주기, FARA/LDA/PDF 병렬 작업, source별 DB lease·재개, main-only 운영 쓰기.
- `scripts/lobbying/api.mjs`: 서버 측 읽기 API. 원문 payload·개인 연락처·시크릿은 공개 응답에서 제외.
- `New for anti/policy-lobbying/**`: 미국 정책 안의 로비·사안 탭, 목록/필터/페이지/원문 상세/쿠팡 사례.
- 기존 법안·행정명령 상세에서 확인된 로비 공시로 이동. 사안과 일반 로비는 명시/문맥 연결을 구분.

## Supabase 구조

기존 정책 정본을 복사하지 않고 아래 5개 전용 테이블을 추가했다.

| 테이블 | 역할 |
|---|---|
| `lobby_records` | 원천 신고·등록 정보와 최신 확보 본문. 문서/등록기관/의뢰인 관계/개인 등록의 종류를 구분 |
| `lobby_record_versions` | 관측된 원천 JSON과 PDF 추출본의 이전 버전·해시 보존 |
| `lobby_activities` | LDA 신고의 이슈 묶음과 해당 묶음에 신고된 기관. 개별 면담으로 확장하지 않음 |
| `lobby_policy_links` | 원문 식별자에서 기존 bills/public_laws/executive_orders/regulations로 가는 관계. 회기 모호/정본 미수록 별도 |
| `lobby_sync_state` | 수집 위치, 원천 목록 크기, 최근 시도·성공·완전 순회 시각, 오류, 실행 lease |

RPC는 batch 저장과 cursor 이동을 한 트랜잭션으로 처리한다. 두 번째 실행이 동일 stream을 동시에 선점할 수 없고, 실패한 batch는 일부 자료나 cursor만 남기지 않는다. 기존 정책 수집기가 나중에 정책을 확보하면 명시 식별자의 미해결 연결을 재검사한다.

모든 새 테이블은 RLS를 활성화하고 anon/authenticated의 직접 접근을 철회했다. 쓰기 RPC도 service_role만 실행 가능하다. 기존 메일/알림 대기열에는 trigger나 쓰기 경로를 추가하지 않았다.

기본 DB 전체 용량 예산은 6 GiB다. 초과 시 신규 수집을 보류하고 cursor를 보존한다. 국가·산업 일부만 남기는 제한과는 다르다. 필요하면 보관 구조·요금·용량을 검토한 뒤 예산을 변경한다.

## 실제 원천 검증

2026-11-05 확보한 FARA 공식 ZIP 4개:

| 종류 | 원천 CSV 행 | 정규화 고유 레코드 |
|---|---:|---:|
| 문서 목록 | 154,709 | 154,268 |
| 등록기관 | 7,105 | 7,104 |
| 의뢰인 관계 | 17,785 | 17,782 |
| 개인 등록 | 44,749 | 44,737 |

고유 레코드는 식별 가능한 동일 관측을 묶은 수이며 별개의 물리 문서 총수라는 뜻은 아니다. 완전히 같은 CSV 행은 중복 제거하고 상충 관측은 함께 보존한다. 의뢰인 CSV 형식 불일치 15행은 원문과 검토 표지를 남긴다. 문서 URL 27,814행은 `Available-FARA-Public-Office`로 온라인 PDF가 없어, 목록을 보존하고 본문 미확보로 둔다.

초기 검증으로 운영 DB에 실제 메타데이터 401건과 그중 PDF 1건의 17쪽 본문을 저장했다. 전체 목록·본문 수집 완료를 의미하지 않는다. 이후 수치는 `/api/us/lobbying/coverage`와 실행 로그를 조회한다.

원천/수집 산출물: `/Users/yeoninair/Documents/lobbying-source-data-20261105/manifest.json` 및 같은 폴더. 원본 ZIP·PDF는 git에 추가하지 않는다. Actions 원문 artifact는 30일 보관하며 장기 binary archive와는 구분한다.

## 검증과 배포 구분

Python 계약·실패 경로 10개, API 계약 6개, 기존 정책 Worker/검색 UI 회귀 22개, 소유권 16개를 검증했다. 실제 DB rollback 트랜잭션에서 멱등성·병렬 lease·실패한 batch/cursor의 원자성·anon 권한 차단을 확인했다. source snapshot 브라우저 검증은 1440px/390px에서 목록·페이지·검색·사안·공유 URL 재진입·원문 상세를 확인했으며 pageerror 0이었다.

브라우저 source snapshot 검증은 운영 배포 검증과 다르다. main 병합, Cloudflare 배포, 실제 Actions 성공 및 cron 활성화 여부를 최종 실행 기록에 별도로 남긴다. LDA는 로컬 실제 API 요청 403과 키 미등록을 확인했으므로 GitHub 실행·키 준비 이후 실제 응답 스키마와 수집 상태를 다시 확인한다.

## 남아 있는 범위

- FARA 본문은 순차 추출이며 이미지 PDF는 OCR 필요 상태로 남는다. 레이아웃에서 개별 접촉 표를 자동 확정하지 않는다.
- 쿠팡은 검수된 정적 사례다. 투자자 청원·한국 처분·일반 통상 로비의 관계와 검토일을 표시하며 최신 소송/집행 상태를 자동 추정하지 않는다.
- LDA 금액 합계와 수정 신고 간 현재 유효 금액 집계는 제공하지 않는다. 원본을 모두 보존하고 필요 시 개별 문서를 검토한다.
