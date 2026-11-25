# Search contract checks

This package is only the test runtime; the dependency-free production indexer is `scripts/sync-policy-search.js`.

```sh
cd services/policy-search
npm ci
npm test
```

`corpus.test.cjs` runs the actual SQL migration twice against PostgreSQL/PGlite with the official pgvector extension and real 1536-dimension test vectors. `worker.test.cjs` executes the Worker search functions with bounded official-source fixtures. `source.test.cjs` checks official text freshness, private caching and blocked-source handling. No private environment, live DB or API key is required.

Operational contract and live verification: `docs/policy-search-corpus-20261005.md`.

## 검색 누락 우선순위

저장소 루트에서 `node scripts/policy-search-priority-sql.js --limit 25`를 실행하면 읽기 전용 미리보기 SQL이 출력됩니다. 운영 프로젝트의 SQL Editor에서 실행하면 후보 총수와 이번 배치 문서 ID를 확인할 수 있습니다.

기존 벡터 보존 패치가 배포되고 우선순위 변경을 승인한 뒤에만, 같은 명령에 `--apply`를 추가해 반영 SQL을 생성합니다. SQL Editor에서 실행하고 반환된 `promoted`를 확인합니다. 최근 90일 공포법의 문단 벡터 공백과 활성 회기 법안의 문서·문단 벡터 공백을 대상으로 합니다. 한 번에 최대 100건, 기본 25건의 대기 순서만 바꿉니다. 색인 작업은 기존 예약 실행에서 처리되며 저장 용량 검사와 실행 한도도 그대로 적용됩니다.
