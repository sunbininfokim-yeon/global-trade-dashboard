# 인도네시아 공식 목록 수집·DB 누락 대조

2026-10-19. 개별 검색으로 찾은 법령만 쌓는 방식에서 벗어나 공식 목록을 먼저 수집한다. 운영 DB 저장·대조와 새 원문 2건 확인을 완료했다. 코드/API는 PR #633의 검토 대상이며 사이트 배포는 별도다.

## 실제 확보 범위

| 출처 | 수집 범위 | 페이지 | 출처별 후보 행 |
|---|---|---:|---:|
| 중앙자바 ESDM | 공개 규정 표 전체. 중앙 법령 재게시와 지방 규정 혼재 | 1 | 70 |
| 서술라웨시 JDIH | 해당 PP 분류의 공개 표 전체. 지방 조례 목록이 아님 | 1 | 1,827 |
| 관세청 DJBC | 무역부 분류 목록의 링크된 페이지 | 5 | 113 |
| 관세청 DJBC | 산업부 분류 목록의 링크된 페이지 | 2 | 28 |
| 합계 | 해당 4개 게시 목록 범위 | 9 | 2,038 |

**2,038행은 법령 고유 건수·원문 확보 수·전국 완전성이 아니다.** 중복 재게시, 원래 관심 산업과 무관한 자료, 잘못 분류된 자료도 포함한다. DJBC의 산업부 분류에는 BPOM 자료가 섞여 있어 목록 분류를 문서 발행기관으로 복사하지 않는다. 중앙 법령을 지방정부가 재게시해도 중앙 법령으로 남긴다.

원 발행기관 ESDM·무역부·농업부·산업부·재무부 5곳은 `held/adapter_not_verified`로 등록했다. 앞의 세 곳에는 점검·접근 차단 관측이 있지만, 다섯 곳 모두의 목록 API가 없거나 항상 차단되었다는 뜻은 아니다. 이번 실행은 보류 출처에 재요청하지 않았다. 기관 전체·연도 전체를 수집했다고 표시하지 않는다.

## 구현 구조

1. `catalogue-sources.json`: 공식 목록 URL, 출판 기관, 목록 범위와 어댑터를 등록한다. 출판 기관과 법령 발행기관은 별도다.
2. `catalogue.py`: 목록 전체 행과 실제 페이지 링크를 순차 수집한다. 이번에는 HTML 목록 어댑터 3종을 실제 실행했다. ILDIS 공개 JSON 규격 어댑터도 검사했지만, 실제 기관의 JSON 피드 주소는 아직 검증·등록하지 않았다. 미국 같은 단일 전국 API 연결 완료가 아니다. [BPHN 연동 규격](https://ildis.bphn.go.id/v4/integrasi/jdihn/)
3. `import-catalogue.cjs`: 미리보기 후 명시적으로 저장한다. 후보를 검토된 법령 본문·개요 임베딩으로 자동 승격하지 않는다.
4. `idn_catalogue_gaps`: 본문 DB의 실제 출처 URL 및 식별자와 대조한다. URL 일치, 식별 후보, 모호함, 미연결을 구별한다. 식별 후보는 같은 종류·번호·연도만으로 자동 병합하지 않는다.
5. `catalogue_queue.py`: 관련 단어는 우선 검토 힌트로만 쓴다. 제목에 단어가 없는 행도 대기열에서 제거하지 않는다. 검토한 후보만 별도 수집 manifest를 만들고 원문을 수집한다.

## 재개·변경·공백의 의미

- 원본 응답은 SHA256으로 보관한다. 페이지를 완전히 파싱·검증·병합한 다음에만 행과 커서를 한 체크포인트로 원자 저장한다. 같은 출력 폴더는 잠금으로 동시 실행을 막는다.
- 기본 최대20페이지/실행, 출처별 최대5,000행, 정부 요청 간3초 간격이다. 한도에 걸리면 `partial`과 남은 URL을 남긴다. `--resume`은 완료 페이지를 재요청하지 않는다.
- 403/429·점검·빈 응답·알 수 없는 구조는 실패/보류다. 실패 URL을 방문 완료로 바꾸지 않는다. 같은 호스트 차단 후 남은 요청을 중단한다. 실패한 출처를 `--resume`으로 자동 재시도하지 않으며, 새 검토 실행을 사용한다. `STOP` 파일도 존중한다.
- 표의 공시 건수와 추출 행수가 다르거나 새 페이지 구조가 나타나거나 페이지가 같은 행만 반복하면 완료로 표시하지 않는다. `enumerated_scope`는 등록된 게시 목록에서 확인한 행·페이지를 읽었다는 뜻이다.
- DB의 후보 키는 `(source_id, source_record_id)`이고 메타데이터 버전은 해시로 중복 방지한다. 체크포인트 저장은 출처별 트랜잭션이며 동일 입력은 추가0건이다. 늦게 도착한 옛 관측이 최신 메타데이터를 덮어쓰지 않는다.
- 성공 목록에서 이전 행이 보이지 않으면 `not_seen_in_latest_enumeration`으로만 표시한다. 원문 삭제·법령 폐지로 해석하지 않는다. 불완전한 실행은 그 판정의 기준이 될 수 없다.
- 외부 Drive 첨부 주소는 목록 메타데이터로 보존하지만 자동 다운로드하지 않는다. 실제 수집은 기존 HTTPS `.go.id` 경계를 유지한다.

## 현재 DB 대조와 검토 대기열

| 구분 | 첫 대조 | 원문 2건 추가 후 |
|---|---:|---:|
| 실제 본문 출처 URL 일치 | 3 | 5 |
| 식별자 일치, 출처 대조 필요 | 17 | 17 |
| 미연결 | 2,018 | 2,016 |
| 모호한 다중 일치 | 0 | 0 |

미연결2,016행을 관련 법령2,016개 누락이라고 세면 안 된다. 다른 산업·과거 규정과 중복 재게시가 포함된다. 전체 검토 대기열은2,033행이고 그중891행에 석탄·광물·팜유·환경·토지·세금·무역 등 단어 힌트가 있다. 해당 행들이 사업에 적용된다는 판정이 아니다. 힌트가 없는 행도 남겼다.

## 목록에서 발견해 원문까지 검증한 2건

- **PP18/2025**: PP15/2022 석탄 광업 세금·비조세 국가수입 체계 개정. [공식 재게시 PDF](https://ppidnew.esdm.jatengprov.go.id/pdf/regulasi/regulasi-6a1144463b7b3.pdf), 추출27,319자, 잘림 없음. 세금 일반 규정을 모든 세금감면 혜택으로 분류하지 않는다.
- **중앙자바 Perda11/2024**: 광물·석탄 광업 행정권한 행사. [공식 PDF](https://ppidnew.esdm.jatengprov.go.id/pdf/regulasi/regulasi-6a117242b16e9.pdf), 추출141,472자, 잘림 없음. 목록은 `Pelimpahan`이지만 원문 표제는 `Pelaksanaan`이므로 문서 표제를 원문 기준으로 보정했다. 목록의 원래 표제·행 ID·원본 해시는 보존했다. 중앙의 일반 규정이나 다른 지방의 조례로 확장하지 않는다.

검토 manifest는 `sources-catalogue-reviewed-20261019.json`이다. 기존 기본 목록99개와 별도로 관리한다. 본문 provenance에 `catalogue_review`의 목록 ID·행 ID·출처 URL·응답 해시를 남긴다. 최초 관측 본문의 메타데이터와 보정 후 문서 표제는 구별된다. 현행 효력은 여전히 `unverified`다.

운영 본문 DB는 **68문서·76버전·143출처 확인**이다. 현재 입력과 일치하는 개요 벡터68개, 대기0개다. 이번에는 새 문서개요2개·입력7,388자만 Gemini로 처리했다. 목록2,038행에 유료 AI를 호출하거나 전체 조문을 임베딩하지 않았다. 실제 과금 토큰·금액은 측정하지 않았다.

실제 DB API에서 `석탄, 세금`+중앙+모든 조건은 PP18/2025를 반환한다(총2개). `석탄, 허가`+지방+모든 조건은 새 중앙자바 규정을 반환한다(총4개). 최초 검사에서 ‘세금감면’으로 일반 세금 개정을 기대한 조건은 맞지 않아 검색 로직을 넓히지 않고 일반 세금 질의로 확인했다.

## DB·API·검증

- 새 테이블은 `policy_idn.catalogue_runs/catalogue_entries/catalogue_versions`다. 합계3,792,896바이트(약3.8MB, 인덱스 포함)였다. 미국 테이블과 별도이며 본문 검색에도 후보를 UNION하지 않는다.
- 마이그레이션 `20261019095306_indonesia_policy_catalogue_inventory.sql` 적용. CLI로 파일 생성 후 운영 이력 버전에 파일명을 맞췄다. 파일/운영 SQL의 MD5는 `089a8f4378a3ab7ff76ee0878ca6a7d7`로 일치한다.
- 서비스 전용 저장/대조 RPC이며 모든 함수는 invoker·빈 search_path다. anon/authenticated의 테이블 조회와 anon 저장은 거부, service 저장은 허용을 확인했다.
- 보안 점검은 새 비공개 테이블3개의 의도된 RLS 정책 없음 INFO이며 관련 성능 경고는 없었다. [점검 설명](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy). 기존 Auth/메일 경고는 이 변경과 별개로 보존했다.
- 읽기 API `/api/idn/catalogue-status`, `/api/idn/catalogue-gaps?source=djbc-kemendag&limit=100&offset=0`를 추가하고 실제 DB로 확인했다. 서버 키는 응답·브라우저에 전달하지 않는다. 사이트에 API가 배포됐다는 뜻은 아니다.
- Python29개, Node DB/API/벡터20개, 소유권14개 통과. 재개·빈 응답·공시 건수 불일치·반복 페이지·새 페이지 구조·원문 보존·권한 거부·원자 롤백·옛 관측·미국 sentinel 보존을 포함한다. 실제 목록 동일 import 재실행은 후보/버전/실행 추가0개이며 완료 목록 resume는 새 네트워크 요청이 없었다.

## 실행·보관·남은 범위

```bash
python3 scripts/indonesia_policy/catalogue.py --output-dir /ABS/NEW-RUN --max-pages 20
# 부분 수집의 나머지 페이지
python3 scripts/indonesia_policy/catalogue.py --output-dir /ABS/SAME-RUN --max-pages 20 --resume
node scripts/indonesia_policy/import-catalogue.cjs /ABS/RUN/catalogue.json --env-file /ABS/SUPABASE_ENV
# 미리보기 뒤 --write --report-dir /ABS/PRIVATE-REPORT 추가
# DB 변경 없이 대조 보고서만 새로 생성: --report-only --report-dir /ABS/NEW-REPORT
python3 scripts/indonesia_policy/catalogue_queue.py /ABS/REPORT/reconciliation.json --output /ABS/NEW-review-queue.json
```

비공개 루트는 `policy-downloads/indonesia-20261019/`이며 `catalogue-inventory-1/`에 목록·원본·상태·최초/원문추가후 대조 보고서·대기열이 있다. `catalogue-reviewed-texts/`는 실제 원문 수집, `catalogue-reviewed-texts-linked/`와 `catalogue-reviewed-texts-title-reviewed/`는 원본·해시·관측 시각을 보존한 검토 import다. 초기 상태는 `catalogue-inventory-1/before-migration-status.json`에 보관했다. 원본·키·전체 후보 데이터는 Git에 넣지 않았다.

다음 공백은 원 부처5곳의 검증된 전체 목록/피드 연결, 관심 사업지역 원 발행기관 목록 확대, 후보의 추가 원문·시행일·개정 검토다. 이 구현은 반복 실행 가능한 명령이며 **정기 수집 예약은 아직 활성화하지 않았다**. 공유 Worker·UI·메일·미국 경로·배포 설정은 변경하지 않았고 병합·사이트 배포는 Claude가 담당한다.
