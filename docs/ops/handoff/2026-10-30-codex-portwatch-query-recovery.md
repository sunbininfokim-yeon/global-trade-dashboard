# PortWatch 수집 재시도와 게시 차단

- 작업: SHIPPING-PORTWATCH-RECOVERY-20261030
- 브랜치: `codex/portwatch-query-recovery-20261030`
- 기준 main: `9681e4116`
- 범위: 해운 Python 클라이언트·빌더·회귀 테스트. UI·워크플로·공개 JSON 변경 없음.

## 확인한 원인과 실제 복구 경계

10월 30일 배포 JSON은 조회 오류 5건, fallback 5개였다. 자동 실행은 성공해도
빌더가 예외를 수집한 뒤 산출물을 게시하므로 전체 수집 성공을 뜻하지 않았다.

현재 원본은 정상 쿼리 및 최소 `where=1=1` 조회에도 HTTP 200 안에
`400 Invalid URL` 또는 `400 Cannot perform query. Invalid query parameters.`를 반환했다.
레이어 메타데이터 조회는 `Layer ... does not exist or is inaccessible`,
`Cannot update time extent`, `Object reference not set to an instance of an object.`를 반환했다.
서비스 루트에는 여전히 `Daily_Chokepoints_Data` 테이블 ID 0이 존재한다.
따라서 잘못된 항로 ID나 페이지 크기만으로 원인을 단정하지 않았다.

GET/POST, json/pjson, 기본 페이지 크기/250개/1개, 경로 대소문자를 비교해도
원본 장애가 이어졌다. 수정 클라이언트로 파나마(`chokepoint2`)와
호르무즈(`chokepoint6`)를 각각 3회 시도했으나 `400 Invalid URL`로 실패했다.
**새 관측 확보·실수집 복구는 미확인이다.** 오류 데이터 산출물을 만들거나 배포하지 않았다.

공식 참조:

- https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0
- https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/

## 수정

- HTTP 상태 오류뿐 아니라 HTTP 200에 담긴 ArcGIS 오류도 최대 3회 시도.
  1초·2초 대기, JSON/pJSON 표현 교대, no-cache 헤더. 401/403 등은 재시도하지 않음.
- 응답 구조·해협 ID·날짜·총 물량을 검증. 빈 결과·불완전한 이력은 최신값으로 채택하지 않음.
- 짧은 페이지라도 `exceededTransferLimit=true`이면 다음 페이지를 조회.
  도중 실패하면 부분 이력을 성공값으로 반환하지 않음.
- 원본 관측일이 캐시보다 후퇴하면 캐시를 유지하고 오류로 기록.
- 기존 `--fetch-portwatch` 자동 실행은 하나라도 최종 수집 오류가 있으면
  공개 산출물 4종을 쓰기 전에 종료 코드 1로 중단.
  기존 workflow는 이 종료 코드에서 멈추므로 커밋·게시도 진행되지 않는다.
  Actions error와 step summary에 실패 해협을 표시.
- 진단 목적의 부분 산출이 꼭 필요한 경우만 `--allow-partial-portwatch`로 명시적 허용.
  기존 워크플로에는 이 옵션을 추가하지 않는다.

이 정책에서는 일부 해협만 복구돼도 전체 일일 bundle 게시가 보류된다.
정상 관측과 오류가 섞인 bundle을 전체 정상 갱신으로 게시하지 않기 위한 선택이다.
기존 `build_snapshot()` 내부의 부분 실패·캐시 유지 계약은 유지한다.

## 검증 및 다음 단계

회귀 테스트는 재시도 회복·소진, HTTP 400/503·타임아웃, 403,
빈/잘못된 응답·다른 해협, 짧은 페이지·중간 페이지 실패,
관측일 후퇴, 실패 시 4종 파일 무변경, 정상 시 4종 게시를 검사한다.
테스트의 합성 응답은 네트워크 오류를 재현하는 fixture이며 공개 데이터로 쓰지 않는다.

검증 결과: 기존+신규 Python 전체 180개 실행에서 178개 통과·2개 h5py 미설치 skip.
이후 관측일 후퇴 검사를 추가해 전용 회귀 12개를 다시 실행, 모두 통과.
따라서 현재 테스트 181개 중 179개 통과·2개 skip을 확인했다.
Node UI 17개, JSON Schema 4종, golden screen/diagnostics 계약도 통과.

병합 후 기존 일일 workflow가 수정된 빌더를 사용한다. 원본이 계속 실패하면
실행 실패가 보이고 종전 산출물이 보존된다. 원본 복구 후 9개 해협 모두
`live_fetch_errors=[]`, `fallback_count=0`인지 확인해야 수집 복구로 판정한다.
병합·workflow dispatch·운영 배포는 이번 작업에서 실행하지 않았다.
