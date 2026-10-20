# 인도네시아 수집·저장 보강 (2026-10-21)

## 반영한 내용

`sync_reviewed.py`는 검토한 공식 출처를 한 번에 제한된 수만큼 재확인하고 DB에 저장하는 실행기다. 다운로드/저장을 따로 실행하다 누락하는 구간을 줄였다. 임베딩·유료 AI·메일 검토/발송·반복 예약은 호출하지 않는다.

기본 출처 레지스트리는 `sources.json`과 10월 20일 석탄 core/operations 목록이다. 총 103개 후보이며 석탄 단계 42개다. 확보된 73문서, 최신 유효 법규 수, 전국 전수 목록과는 다르다. `idn-esdm-permen-6-2026`은 동일 발행기관·관할·유형·번호·연도를 확인한 특정 파일 조합에 한해 후속 복구 출처를 사용한다. 다른 중복은 오류로 중단하며 임의의 마지막 파일 우선 처리는 없다. 기관별 목록의 미검토 신규 후보를 자동으로 법령으로 승격하지 않는다.

상태 디렉터리의 파일 잠금은 Mac/Linux의 동시 실행을 막는다. 한 문서의 원본 수집 결과를 비공개 파일로 먼저 고정하고 DB 저장·출처 확인 로그가 모두 기록된 뒤에만 커서를 이동한다. DB/네트워크가 중간에 실패하면 같은 파일을 다시 저장하며 원문을 다시 받지 않는다. DB의 해시/출처 로그 중복 키를 이용한다. `STOP` 파일은 다음 작업 경계에서 중단하며, 프로세스를 강제 종료해도 다음 실행에서 체크포인트를 보존한다.

403/429·점검·차단은 호스트를 24시간, 기타 수집 실패는 1시간 쉬게 한다. PDF 첨부 호스트가 막혔을 때도 같은 실행/다음 실행에서 그 호스트로 다시 PDF를 요청하지 않는다. 만료 시 재시도한다. 한 번 실행은 기본 5개, 최대 20개이며 종료한다. 원본/상태는 저장소 밖에 보관한다. 같은 상태 경로를 유지해야 순서와 차단 이력이 이어진다. manifest/검토 태그가 바뀌면 중단하고 기존 상태를 보존한 새 디렉터리에서 검토한 구성을 시작한다.

**파일 잠금은 같은 상태 경로를 사용하는 한 호스트 범위다.** Mac과 GitHub를 동시에 돌리지 않는다. 다른 국가의 수집기 잠금/설정은 변경하지 않았다. GitHub 전환 시 Mac 중단, 단일 concurrency 그룹, 체크포인트 영속 보관을 별도로 구성해야 한다. 이번 작업에서 예약을 켜지 않았다.

## DB의 기존 원문 보호

`20261020215056_indonesia_preserve_source_text.sql`은 이미 완전한 공식 원문이 있으면 메타데이터/초록/잘린 본문으로 교체하지 않는다. 문서 갱신 시각과 기존 검색 원문도 유지하고 실패 확인 로그만 남긴다. 자료를 처음 확보할 때의 명시적인 메타데이터 저장, 정상적인 원문 승격은 계속 허용한다.

`20261020230106_indonesia_ingest_serialization.sql`은 서비스 전용 저장 RPC에 문서별 트랜잭션 잠금을 추가한다. 처음 저장하는 문서가 아직 없어도 동시 요청을 직렬화한다. 기존 행만 잠그는 것으로 최초 저장 경쟁을 보호했다고 주장하지 않는다. 이 잠금은 한 번의 저장 RPC 범위이며, 전체 수집 주기/여러 호스트의 HTTP 요청을 잠그는 분산 수집 lease는 아니다.

두 migration은 운영에 반영했고 로컬 SQL과 운영 이력의 MD5를 대조했다. 원문 보호 SQL은 최초 적용 이력을 덮어쓰지 않고, 잠금은 별도 후속 파일로 분리했다. 적용 전 함수와 관측 집계는 비공개 로컬 백업에 보존했다. 적용 전 이미 원문이 메타데이터로 대체된 문서는 0건이었다. 이번 보호를 이미 발생한 데이터 손상 복구라고 표현하지 않는다.

## 실제 점검 결과

공식 석탄 출처 `idn-kemendag-permendag-15-2026`, `idn-pmk-51-2025` 두 건으로 다운로드→DB 저장→출처 확인을 실행했다. 성공 2건, 새 버전 0건, 실패/메타데이터 대체 0건이었다. 내용이 동일해서 메일 후보도 추가되지 않았다. 운영 DB의 기존 완전 원문을 메타데이터로 갱신하려는 제한된 롤백 트랜잭션에서도 원문·갱신 시각·버전 수 보존을 확인했다.

Python 수집기/재개 검사 41개, 메일링 검사 56개, 브라우저 검사 6개와 타입 검사를 통과했다. 체크포인트의 DB 실패 재개·변조 거부·STOP·잠금·호스트 보류·첨부 재요청 차단·응답 크기/리다이렉트 제한·원문 보존·구독 선택 지역 유지가 포함된다. 원문 보호는 운영에도 적용됐지만 UI 변경과 새 실행기는 PR 배포/운영 연결 전이다.

구독 화면은 저장/해제 후 선택 지역을 유지하며, 연결 실패 후 재시도 때 Auth 클라이언트·이벤트 리스너를 중복 생성하지 않는다. 검토 CLI의 예전 “not enqueued” 문구도 현재 자동 대기열 동작에 맞게 고쳤다.

## Mac에서 실행

Python 3.12/OpenSSL 3.5 전용 환경을 `policy-runtimes/idn-sync`에 준비했다. 시스템 Python이나 기존 수집 환경은 수정하지 않았다. 고정한 직접 의존성은 `scripts/indonesia_policy/requirements-sync.txt`다. 새 Mac/GitHub는 지원되는 Python 환경에 이 파일을 설치한다.

```bash
cd /Users/yeoninair/Documents/policy-indonesia-20261017
# 계획만 확인: 네트워크/DB 쓰기 없음
/Users/yeoninair/Documents/policy-runtimes/idn-sync/bin/python scripts/indonesia_policy/sync_reviewed.py \
  --stage coal --limit 10 \
  --state-dir /Users/yeoninair/Documents/policy-downloads/indonesia-sync/coal

# 실제 한 차례 수집·저장. 다음 실행도 같은 상태 경로 사용
caffeinate -i /Users/yeoninair/Documents/policy-runtimes/idn-sync/bin/python scripts/indonesia_policy/sync_reviewed.py \
  --stage coal --limit 10 --write \
  --state-dir /Users/yeoninair/Documents/policy-downloads/indonesia-sync/coal \
  --env-file /Users/yeoninair/Documents/global-trade-dashboard-local/.env.local
```

모든 단계는 `--stage all`, 또는 coal/nickel_mining/palm_oil/biofuel/mineral_mining을 선택한다. 단계별로 다른 상태 경로를 사용한다. 모든 요청이 실패/보류된 경우에도 커서가 진행할 수 있으므로 `attempted`, `source_failures`, `metadata_only`, `cooldown_skips`를 함께 본다. 커서 완료나 상태 갱신 시각은 최신 법령 전수 확인 성공의 증거가 아니다.

현재 IDN 발송 게이트는 꺼져 있고, 구독 0건·알림 0건이다. Claude의 UI/메일 Worker 배포, 수집 예약의 주기/담당 결정, 실제 로그인 계정 구독과 신규 변화 수신 검증은 계속 남는다. 자동 수집으로 아직 등록하지 않은 법령의 누락이 모두 해소되는 것은 아니다.
