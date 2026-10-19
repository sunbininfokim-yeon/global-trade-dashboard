# 인도네시아 정책 시범 수집기

미국과 분리된 policy_idn 전용 수집·저장·검색 경로다. [분리 계약](../../docs/indonesia-policy-isolation-contract.md)과 [검색 계약](../../docs/indonesia-policy-search.md)을 따른다. 수집/import는 검색 UI, 미국 검색, 메일, Gemini 호출, 반복 스케줄을 실행하지 않는다.

## 수집

Python 3과 requirements.txt의 requests/beautifulsoup4/pypdf가 필요하다. sources.json과 sources-expansion-*.json은 사람이 검토한 공식 URL·문서 식별자·관할·범위를 담는다. 전국 전수 목록은 아니다. 최신 확보 범위와 보류 항목은 [수집 범위 보고서](../../docs/indonesia-policy-coverage-20261018.md)에 기록한다.

```bash
cd /Users/yeoninair/Documents/policy-indonesia-20261017
python3 scripts/indonesia_policy/collect.py \
  --stage biofuel \
  --output-dir /Users/yeoninair/Documents/policy-downloads/indonesia/RUN-UNIQUE \
  --limit 9
```

stage: coal → nickel_mining → palm_oil → biofuel → mineral_mining, 또는 all. 실행마다 새 결과 디렉터리를 사용한다. 기존 collection.json을 덮어쓰지 않는다. 실패 문서만 재확인하려면 같은 stage에 `--document-id idn-esdm-permen-4-2025`를 추가하고 새 결과 디렉터리를 지정한다. 결과 JSON과 원본 SHA256 캐시는 저장소 밖에 보관한다. 매 시도 이후 체크포인트를 원자 교체한다. 실패한 실행에서도 collection.json의 성공 문서는 즉시 저장할 수 있다.

기본 sources.json은 확대·복구 결과를 합친 99개 검토 후보 목록이다(저장 64, 미저장 35). 일부는 아직 접근 실패 상태이며 99개 모두 확보됐다는 뜻이 아니다. `--stage all --limit 100`이면 현재 목록 전체가 시도 대상이다. 기본 limit 30은 일부만 시도하므로 품목별 stage·ID 또는 명시적인 limit을 사용한다. 이번에 상시 작업을 켜지는 않았다. 최신 범위는 [공식 출처 복구·산업 규정 후속](../../docs/indonesia-policy-official-recovery-20261019.md)을 따른다. 가치사슬·UI·개요 임베딩 구조는 [가치사슬 보고서](../../docs/indonesia-policy-value-chain-20261019.md)에 있다.

개별 수집을 재현할 때만 `--manifest scripts/indonesia_policy/sources-expansion-20261018.json` 등 이력 목록을 선택한다. 2026-10-19 사업법규 후보·파산/중재 원문·법전 본체 보류는 [사업법규 보고서](../../docs/indonesia-policy-business-law-20261019.md)를 따른다. 환경·복구·지방·메타데이터 목록의 결과와 공백은 [최신 보고서](../../docs/indonesia-policy-environment-and-sources-20261019.md)를 따른다. 이미 실패한 오래된 주소를 일괄 재실행하지 않는다. 현재 실행 중인 수집기와 같은 호스트를 병렬 수집하지 않는다. `metadata_only` 후보는 카탈로그만 수집해 대형/실패 PDF의 불필요한 재다운로드를 막는다.

기존 공식 Fulltext가 HTML인 경우에도 최종 법령 표식·조문·문서번호를 검증한 뒤 원문으로 저장한다. 공식 페이지의 `window.open`에는 문자열 URL만 읽고 JavaScript를 실행하지 않는다. PDF 하위 요청에서 403/429를 받으면 공식 메타데이터를 보존하고 그 호스트의 남은 요청을 중단한다.

## 관련 문서 후보 발견

```bash
python3 scripts/indonesia_policy/discover.py \
  --document-id idn-kemenkeu-pmk-69-2025 \
  --output-dir /Users/yeoninair/Documents/policy-downloads/indonesia/DISCOVERY-UNIQUE
```

기본 목록에서 선택한 공식 문서 페이지의 관련 법규 링크를 한 단계만 탐색한다. 최대 20개 출발 문서, 순차 요청·호스트 차단·원본 해시·매 시도 체크포인트를 사용한다. candidates.json의 `review_status=candidate`는 미검토 후보이며 DB에 자동 저장하지 않는다. 관련 링크에 환율 고시 등 무관한 문서도 섞이므로 제목·문서번호·발행기관·관할·품목·지원 방식과 개정 관계를 사람이 확인한 뒤 별도 manifest에 추가한다. HTML 링크만으로 현행 효력이나 보조금 수급권을 확정하지 않는다.

HTTPS 정부 도메인만 사용하며 TLS 검증을 끄지 않는다. 403/429이면 같은 호스트의 나머지 시도도 중단한다. 점검·차단·초안·문서 식별 실패를 성공으로 대체하지 않는다. 다운로드 최대 12MiB, 본문 최대 300,000자, PDF 최대 300페이지이며 추출 제한·원본 해시를 보존한다. 잘린 본문은 전체 원문으로 표시하지 않는다. 본문 링크 식별이 불확실하면 공식 메타데이터만 저장한다.

## 저장

Node.js 20 이상. 저장에는 분리 계약의 마이그레이션 1~4, 현재 검색에는 9번까지 적용해야 한다. 키는 출력하지 않고 로컬 파일에서 읽는다.

```bash
node scripts/indonesia_policy/import.cjs /ABSOLUTE/RUN-UNIQUE/collection.json \
  --env-file /Users/yeoninair/Documents/global-trade-dashboard-local/.env.local

# 미리보기 후 실제 저장
node scripts/indonesia_policy/import.cjs /ABSOLUTE/RUN-UNIQUE/collection.json \
  --env-file /Users/yeoninair/Documents/global-trade-dashboard-local/.env.local --write
```

환경 변수는 SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY다. anon/publishable 키는 쓰기 불가. importer는 IDN country/status/hash를 확인하고 원자 저장 RPC를 문서별로 호출한다. (document_id,content_hash) 및 (document_id,checked_at) 충돌은 중복을 만들지 않는다. 실패 후 동일 파일을 다시 저장하면 완료된 항목을 유지하고 남은 항목을 처리한다. 오류는 비정상 종료하며 숨은 fallback은 없다.

스키마를 Data API에 공개하지 않는다. client.cjs는 명시적으로 허용한 서비스 전용 public.idn_* 저장·상태·임베딩 RPC만 사용하며 미국 테이블·RPC·GET 요청을 거부한다. backup-before-isolation.cjs는 이전 public IDN 구조 전용 일회성 도구로, 이동 완료 후에는 실행하지 않는다.

## 검증

```bash
python3 -m unittest discover -s scripts/indonesia_policy -p 'test_*.py' -v
npm install --prefix /tmp/idn-db-tests --save-exact --no-audit --no-fund @electric-sql/pglite@0.5.10 @electric-sql/pglite-pgvector@0.0.11
IDN_TEST_NODE_MODULES=/tmp/idn-db-tests/node_modules \
  node --test scripts/indonesia_policy/test_database.cjs scripts/indonesia_policy/test_client.cjs scripts/indonesia_policy/test_search.cjs scripts/indonesia_policy/test_api.mjs scripts/indonesia_policy/test_source_links.mjs scripts/indonesia_policy/test_worker.cjs scripts/indonesia_policy/test_embeddings.mjs scripts/indonesia_policy/test_vector_database.cjs
```

원문 확보와 현행 효력 확정, 관측 변경과 법적 개정은 서로 다르다. 해시 변화만으로 단계 알림이나 법적 의무를 생성하면 안 된다.

실제 DB 검색 미리보기는 `node scripts/indonesia_policy/preview.mjs --env-file /ABSOLUTE/ENV` 후 `http://127.0.0.1:4317/indonesia-policy/`를 연다. 127.0.0.1에만 바인딩하며 쓰기 RPC는 제공하지 않는다. 운영 배포 명령이 아니다. 통합 브라우저 검사는 실행 중인 미리보기와 Playwright를 사용한다: `IDN_BROWSER_NODE_MODULES=/PATH/TO/node_modules node --test scripts/indonesia_policy/test_browser.cjs`. 기본 Chrome 경로는 macOS용이며 IDN_BROWSER_EXECUTABLE로 변경할 수 있다.

## 근거 관계·사업 범위·선택 조문

[근거 구조 및 인수 문서](../../docs/indonesia-policy-evidence-20261019.md)를 따른다. 기본 검토 후보 99개와 별도 참고 3개를 합친 102개 공백 목록, 원문 인용 관계 5건·사업범위 7건·선택 조문 12건이 있다. 문서 본문은 기존 64건이며 현행 효력/개별 사업 적용성을 확정하지 않는다. 새 설치는 `20261019081717_indonesia_policy_review_evidence.sql`까지 순서대로 적용한다. `import-review.cjs`는 기본 미리보기이며 원문이 바뀌면 새 해시의 근거를 다시 검토해야 한다. `embed-passages.mjs`는 선택 조문만 처리하며 기존 개요와 캐시/프로필을 분리한다. UI·운영 배포는 Claude 인수 대상이다.

## 문서개요 임베딩

```bash
node scripts/indonesia_policy/embed.mjs --env-file /ABSOLUTE/SUPABASE_ENV \
  --gemini-env-file /ABSOLUTE/GEMINI_ENV --limit 100
```

기본은 dry-run이다. 실제 생성·저장에는 `--write --cache-dir /ABSOLUTE/OUTSIDE/REPO`를 추가한다. 최대 100문서·문서당 입력 5400자·배치 8개로 제한한다. 벡터를 비공개 캐시에 저장한 뒤 DB에 기록하여 재실행 시 비용을 줄인다. 모델 gemini-embedding-001/1536차원/overview-v1이며 전체 조문 임베딩·번역이 아니다. 수집/import와 분리된 명시적 작업이다.

로컬 의미검색은 preview.mjs에 `--gemini-env-file /ABSOLUTE/GEMINI_ENV`를 추가할 때 활성화한다. 공개 배포는 기본 꺼짐이다. Claude가 사용량 제한·서버 Secret을 준비한 뒤 별도로 IDN_SEMANTIC_ENABLED=true를 설정한다. 브라우저에 키를 주지 않는다.

벡터 테스트는 @electric-sql/pglite@0.5.10과 @electric-sql/pglite-pgvector@0.0.11을 사용한다. 기존 Node 검사에 test_embeddings.mjs·test_vector_database.cjs를 추가한다. 브라우저 검증은 playwright@1.56.1과 로컬 Chrome을 사용했다.
