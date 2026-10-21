# 원 부처 4곳 재점검과 재정부 대체 목록 연결

한국시간 2026-10-20 15:50~16시대 점검. 이전 PR #639는 병합됐으며, 최신 main `4b3655d3`에서 `codex/idn-ministry-recovery-20261020`으로 분리했다. 원 부처 4곳을 다시 점검했지만 직접 목록 연결은 복구되지 않았다. 대신 관세청(DJBC)의 공식 재무장관 법령 분류를 연결해 표시 총수와 일치하는 734건을 저장했다. 재정부 원 사이트의 전수 목록과는 구분한다.

## 원 부처 실제 결과

| 원 부처 | 수집기 재점검 | 기록·남은 문제 |
|---|---|---|
| ESDM | `/dokumen/index`가 HTTP 응답으로 공식 점검 안내 반환 | 이전 DNS 오류와 구분해 `maintenance`로 갱신. 목록 데이터 아님 |
| Pertanian | 홈페이지 403 | `http_403`. 같은 호스트 재시도·차단 우회 없음 |
| Kemenperin | 연결 시간 초과 | `connection_timeout`. 공개 목록/API 검증 못 함 |
| Kemenkeu | 공식 메뉴에서 확인한 `/search?...` 읽기 시간 초과 | 표준 curl 1회 확인도 TLS 연결 시간 초과. 직접 목록의 페이지 이동 검증 못 함 |

웹 조회에서 농업부 홈페이지와 `/peraturan`는 동적 로딩 화면을 확인했다. 초기 `0` 카운터나 “Loading peraturan”를 실제 법령 0건으로 저장하지 않는다. 재정부 웹 조회의 목록 노출도 로컬 자동 수집 성공으로 대신하지 않는다. JDIHN 및 법무부 peraturan.go.id의 공식 대체 경로도 로컬 접속 시간 초과로, 사용 가능한 전수 API라고 등록하지 않았다. URL을 추측한 API나 로그인 전용 경로를 수집하지 않았다.

`scripts/indonesia_policy/ministry-verification-20261020.json`에 점검 URL·시각·결과를 기록했다. 네 원 부처의 보류 기록도 DB `policy_idn.catalogue_runs`에 적용했다. 이전 `adapter_not_verified` 일반 사유 대신 이번 실제 오류를 `stop_reason`에 남기고 `failure_count=1`로 조회된다. 기존 법령/목록 행은 삭제하거나 0으로 대체하지 않았다.

## 관세청의 재무장관 법령 분류

- 실제 [관세청 공식 디렉터리](https://peraturan.beacukai.go.id/regulasi/index.html) 메뉴에서 [Menteri Keuangan 분류](https://peraturan.beacukai.go.id/regulasi/index.html?page=penerbit/8/menteri-keuangan/1.html)를 확인했다.
- source_id=`djbc-kemenkeu`, `source_role=official_republication`, `original_source_id=kemenkeu-original`.
- 30페이지, 고유 source_record_id 734개, 모든 페이지의 표시 총수 734, 미처리 페이지 0, 실패 0을 확인했다. 같은 목록을 다시 저장해 신규 버전 0건을 검증했다.
- 이 분류의 페이지 열거가 끝났다는 뜻이다. 재정부 전체 법령·현행 유효 법령·자원개발 관련 법령 734개라는 뜻이 아니다. 세관 업무와 관련해 재게시한 과거 문서를 포함한다.
- 재무장관 결정 제목의 기관/유형도 식별하되, 원문 확보·법적 효력 판정·자동 검색 편입은 별도 검토다. 예를 들어 목록의 `31/MK/BC/2026`과 기존 문서의 번호 `31/MK/BC`+연도 2026은 현재 엄격한 대조 규칙에서 바로 연결되지 않는다. `unmatched`는 신규 법령이라는 뜻이 아니며 자동 중복 문서를 만들지 않는다.
- 새 734건은 제목 힌트 기준 529건에 검토 우선순위가 있다(세금·수출입 등 공통 526, 광업 12, 팜유 9, 석탄 2; 서로 중복). 나머지도 검토 대기열에 유지한다. 힌트는 관련성/적용성 확정이 아니다.

DB 실측: 카탈로그 행/메타데이터 버전 2,134→2,868. 본문 문서 68개·본문 버전 76개·효력 근거 17개 유지. 카탈로그 숫자는 기관별 재게시 중복을 포함하며 고유 법령 수가 아니다. DB 스키마·미국 데이터·메일·배포 설정·자동 예약은 변경하지 않았다. 유료 AI 호출은 0회다.

## 수집기 보강

`probe_catalogues.py`는 미검증 원 부처를 호스트당 한 번 점검한다. 점검/차단 화면, 동적 로딩 화면, 접속 가능하지만 열거 미검증 상태를 구분한다. 성공 HTTP나 빈 화면을 수집 완료로 승격하지 않는다. 외부 링크/리다이렉트와 원문 해시를 검증하며 Cookie·헤더·시크릿·예외의 내부 메모리 주소를 보고서에 복사하지 않는다. 원본 응답은 저장소 밖 비공개 폴더에 보관한다. 기본 동작에는 DB 쓰기·AI 호출·자동 예약이 없다.

카탈로그 수집은 DJBC도 전체 표시 건수와 누적 고유 행 수를 대조한다. 총수가 바뀌거나 페이지가 반복되면 미처리 커서를 보존하고 중단한다. 새 source는 총수 표시가 없으면 중단하도록 설정했다.

이번 실행 도중 로컬 디스크 공간 부족(ENOSPC)으로 파일 저장이 한 번 실패했다. 직전 완료 페이지 25건 체크포인트가 보존된 것을 확인했고, 시스템에서 여유 공간이 다시 확인된 뒤 그 지점에서 재개해 734건을 완료했다. 사용자 파일을 삭제하지 않았다. 수집기와 점검기에 요청 전 64MiB 여유 공간 검사를 추가했다. 여유 부족은 원 사이트 실패로 기록하지 않는다. 공간은 다른 작업에 따라 변동하므로 대규모 수집 전 사용자가 정리할 필요가 있다. 이 작업의 원본/체크포인트는 수 MiB 범위다.

검증: Python 39개, Node 13개, ownership 14개 통과. 유지 데이터 건수·실제 734건 저장·동일 파일 재실행을 DB에서 확인했다. 이번에는 UI/SQL 변경이 없으므로 브라우저 검사를 반복하지 않았다.

비공개 실행 자료:

- `policy-downloads/indonesia-20261020/ministry-recovery/`: 처음 수행한 실제 접속 기록과 원 응답, 원 부처 DB 보류 스냅샷. 새 점검 도구로 중복 네트워크 요청을 하지 않고 이미 받은 관측을 형식에 맞춰 저장했다.
- `policy-downloads/indonesia-20261020/djbc-kemenkeu/catalogue.json`: 완료 체크포인트 및 30개 원 응답 해시.
- `policy-downloads/indonesia-20261020/reconciliation-after-finance/`: 전체 대조 2,868행, 검토 대기 2,861행과 제목 힌트.

```bash
# 새로운 비공개 폴더에서만 한 차례 재점검. 자동 재시도/예약이 아님.
python3 scripts/indonesia_policy/probe_catalogues.py \
  --source esdm-original --source pertanian-original \
  --source kemenperin-original --source kemenkeu-original \
  --output-dir /ABSOLUTE/NEW-PROBE
# 결과 검토 후 기존 서비스 전용 importer로 선택 적용
node scripts/indonesia_policy/import-catalogue.cjs /ABSOLUTE/NEW-PROBE/catalogue.json \
  --env-file /ABSOLUTE/SERVER_ENV --write
```

다음은 원 부처 서비스 복구/공개 피드 확인 후 adapter 연결, 그리고 재게시 목록에서 기존 법령 동일성·실제 PDF·현행 개폐를 검토하는 순서다. 이 PR은 원 부처 네 곳의 직접 연결 완료나 수집 스케줄 활성화가 아니다. 코드 병합·배포는 Claude 인수 대상이다.
