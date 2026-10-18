# 인도네시아 정책 시범 수집기

미국과 분리된 policy_idn 전용 수집·저장 경로다. [분리 계약](../../docs/indonesia-policy-isolation-contract.md)을 따른다. UI, 미국 검색, 메일, Gemini 호출, 반복 스케줄을 실행하지 않는다.

## 수집

Python 3과 requirements.txt의 requests/beautifulsoup4/pypdf가 필요하다. sources.json은 사람이 검토한 공식 URL·문서 식별자·관할·범위를 담는다. 발견 API나 전국 전수 목록은 아니다.

```bash
cd /Users/yeoninair/Documents/policy-indonesia-20261017
python3 scripts/indonesia_policy/collect.py \
  --stage biofuel \
  --output-dir /Users/yeoninair/Documents/policy-downloads/indonesia/RUN-UNIQUE \
  --limit 9
```

stage: coal → nickel_mining → palm_oil → biofuel, 또는 all. 실행마다 새 결과 디렉터리를 사용한다. 기존 collection.json을 덮어쓰지 않는다. 실패 문서만 재확인하려면 같은 stage에 `--document-id idn-esdm-permen-4-2025`를 추가하고 새 결과 디렉터리를 지정한다. 결과 JSON과 원본 SHA256 캐시는 저장소 밖에 보관한다. 매 시도 이후 체크포인트를 원자 교체한다. 실패한 실행에서도 collection.json의 성공 문서는 즉시 저장할 수 있다.

HTTPS 정부 도메인만 사용하며 TLS 검증을 끄지 않는다. 403/429이면 같은 호스트의 나머지 시도도 중단한다. 점검·차단·초안·문서 식별 실패를 성공으로 대체하지 않는다. 다운로드 최대 12MiB, 본문 최대 300,000자, PDF 최대 300페이지이며 추출 제한·원본 해시를 보존한다. 잘린 본문은 전체 원문으로 표시하지 않는다. 본문 링크 식별이 불확실하면 공식 메타데이터만 저장한다.

## 저장

Node.js 20 이상. 분리 계약의 마이그레이션 4개를 순서대로 적용해야 한다. 키는 출력하지 않고 로컬 파일에서 읽는다.

```bash
node scripts/indonesia_policy/import.cjs /ABSOLUTE/RUN-UNIQUE/collection.json \
  --env-file /Users/yeoninair/Documents/global-trade-dashboard-local/.env.local

# 미리보기 후 실제 저장
node scripts/indonesia_policy/import.cjs /ABSOLUTE/RUN-UNIQUE/collection.json \
  --env-file /Users/yeoninair/Documents/global-trade-dashboard-local/.env.local --write
```

환경 변수는 SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY다. anon/publishable 키는 쓰기 불가. importer는 IDN country/status/hash를 확인하고 원자 저장 RPC를 문서별로 호출한다. (document_id,content_hash) 및 (document_id,checked_at) 충돌은 중복을 만들지 않는다. 실패 후 동일 파일을 다시 저장하면 완료된 항목을 유지하고 남은 항목을 처리한다. 오류는 비정상 종료하며 숨은 fallback은 없다.

스키마를 Data API에 공개하지 않는다. client.cjs는 서비스 전용 public.idn_* RPC 3개만 허용하고 미국 테이블·RPC·GET 요청을 거부한다. backup-before-isolation.cjs는 이전 public IDN 구조 전용 일회성 도구로, 이동 완료 후에는 실행하지 않는다.

## 검증

```bash
python3 -m unittest discover -s scripts/indonesia_policy -p 'test_*.py' -v
npm install --prefix /tmp/idn-db-tests --no-audit --no-fund @electric-sql/pglite@0.5.8
IDN_TEST_NODE_MODULES=/tmp/idn-db-tests/node_modules \
  node --test scripts/indonesia_policy/test_database.cjs scripts/indonesia_policy/test_client.cjs
```

원문 확보와 현행 효력 확정, 관측 변경과 법적 개정은 서로 다르다. 해시 변화만으로 단계 알림이나 법적 의무를 생성하면 안 된다.
