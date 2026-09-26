# 정책 검색·원자재 메일링 점검 및 임베딩 보강

2026-09-24 운영 Supabase 읽기 전용 집계 및 origin/main 7310c272 기준.

## 확인된 범위

| 데이터 | 저장 | 벡터 |
|---|---:|---:|
| bills (모두 119대) | 18,989 | 18,989 |
| public_laws (104~118대) | 5,837 | 컬럼 없음 |
| public_laws (119대) | 111 | 컬럼 없음 |
| executive_orders | 1,536 | 1,536 |
| regulations | 180 | 180 |

119대 bills 중 current_stage=enacted는 113건. public_laws와 bills는 별도 집합이며 더해서 법률 수로 해석하지 않는다. 과거 public_laws의 bill_id 연결은 0건이다. public_laws는 현재 search_policy_corpus의 대상이 아니다. bills에서 summary가 NULL이 아닌 행은 5,703건이며, 이것은 요약 품질/전문 확보를 보증하지 않는다. 기존 backfill은 title+summary를 사용하므로 모든 벡터가 있어도 조문 검색을 보장하지 않는다. 과거법 목록은 원문 수집 완료/현행 효력 확인을 의미하지 않는다.

## RSS

원유·천연가스 즐겨찾기가 실제 DB에 저장된 것을 확인했다. 수신 제외 소스는 없고 원자재 발송 영수증 및 원자재 outbox는 0건이었다. DB 보관 보고서는 39건, 최신 발행일은 9월 17일. GitHub main의 발송 입력 파일은 9월 24일 08:06 KST 생성됐지만 최신 발행일은 역시 9월 17일이며, 점검 시 최근 8일의 원유/가스 매칭은 1건이다. 파일 생성시각을 자료 신선도로 표시하면 안 된다.

PR #321은 여전히 미병합. main의 기존 주간 발송기는 JSON+commodity favorites를 읽고 최근 8일/미발송 조건을 적용한다. 새 outbox가 비어 있다는 사실만으로 기존 GitHub 발송이 불가능하다고 판단하지 않는다. 다음 월요일 예정은 9월 28일 08:00 KST이며, 실제 GitHub 시작시각은 지연될 수 있다. 새로운 보고서가 없으면 발송이 다시 0건일 수 있다. 발송/활성화/구독 수정은 이번에 실행하지 않았다.

## 첨부 요약을 적용할 때 수정할 주장

- 200자/60자 겹침, Top-20, 91%는 첨부 자료의 특정 실험 결과다. 원영상의 데이터/평가표를 독립 재현한 결과가 아니다.
- 겹침은 경계 유실을 줄이지만 모든 긴 문장의 보존을 보장하지 않는다. 법률은 section/subsection과 법률 버전을 먼저 분리하고, 너무 긴 구간만 문장 경계 근처에서 자른다.
- Top-K 증가는 후보 누락을 줄일 수 있지만 잡음과 생성 입력 비용도 늘린다. 전체 법률 수 등의 집계는 벡터 Top-K가 아니라 DB 필터/집계로 답한다.
- 로컬 임베딩 API 과금 0은 Gemini API 사용 구조에 적용할 수 없다. 기존 gemini-embedding-001/1536 및 RETRIEVAL_DOCUMENT/RETRIEVAL_QUERY 계약을 유지한다. 다른 모델은 같은 벡터 공간에 혼합하지 않는다.
- 리랭커가 필요 없다는 결론은 일반화하지 않는다. 정책 질의 평가에서 recall, relevance, latency, 비용을 비교한다.

공식 참고: [Gemini embedding task types](https://ai.google.dev/gemini-api/docs/embeddings), [Supabase hybrid search/RRF](https://supabase.com/docs/guides/ai/hybrid-search).

## 이번에 추가한 실행 가능한 준비 도구

`scripts/policy-retrieval/prepare.cjs`는 오프라인 도구다. API 호출·DB 변경은 없다.

1. 원문 누락 없이 겹치는 청크 생성. Unicode code point offset, 출처 URL, 문서 종류/ID, 버전, section, 원문 hash, 결정적 chunk ID를 보존한다. 기본 2,400자/360자 겹침은 평가 시작값이며 토큰 제한의 보증이 아니다.
2. lexical/semantic 순위의 RRF 결합. 정확 식별자 결과 우선, 같은 문서의 중복 청크로 인한 투표 증폭 방지.
3. 라벨이 있는 후보 순위로 Top-5/10/20 문서 recall 비교. 답변 정확도라고 표시하지 않는다.
4. 청크 수 및 1536차원 float32 벡터 원시 바이트 예상. 텍스트/인덱스/DB오버헤드/호출비는 별도다.

```sh
node scripts/policy-retrieval/prepare.cjs chunks /private/tmp/policy-documents.json > /private/tmp/policy-chunks.json
node scripts/policy-retrieval/prepare.cjs evaluate /private/tmp/policy-ranked-cases.json
node --test scripts/policy-retrieval/prepare.test.cjs
```

문서 입력은 배열이며 각 항목은 `source_type`(bill/public_law/executive_order/regulation), `source_id`, `version`, `source_url`(https), `text`를 필수로 한다. `title`, `section`은 선택이다. 조항 분리는 원본 XML 파서에서 수행해 조항별 항목을 전달한다. 이 도구는 HTML/XML 파서가 아니다. 버전 ID는 법안의 introduced/enrolled 구분, 법률의 공식 package/version과 대응시켜야 한다.

평가 입력 예시(실측 성능이 아닌 형식 예시):
```json
[{"query":"HR 3633", "exact":["bill:119-hr-3633"], "lexical":["bill:119-hr-3633"], "semantic":["bill:119-hr-3633"], "expected":["bill:119-hr-3633"]}]
```

## 운영 연결에 남은 일 (이번 변경으로 배포되었다고 해석하지 않음)

1. 과거 public_laws를 bill_id 없이도 독립 검색 대상으로 추가. 번호/연도/공식명 정확 조회와 full-text 검색 구축. bills와 public_laws 동일 법률은 근거 있는 링크로 dedup.
2. GovInfo 원문 확보 현황 감사 → section 파싱 → 소수 표본에 청크 도구 적용 → token count 확인 및 재분할. 기존 벡터는 덮어쓰지 않고 별도 versioned chunk 저장소 준비.
3. 번호 질의, 한국어 정책 주제, 조항 예외, 과거 제정법, 집계 질의를 분리한 수작업 relevance 평가셋 작성. 실제 lexical/semantic 후보를 확보해 도구로 비교. 현재 4개 회귀 테스트는 코드 동작 검증이며 검색 품질 평가가 아니다.
4. DB chunk 테이블/RLS/인덱스/검색 RPC와 재개 가능한 배치 임베딩 추가. 작은 배치 비용과 저장량을 측정한 뒤 확대. HTML 요약을 전문으로 오인하지 않도록 text_kind 포함.
5. Worker에서 lexical/semantic 후보를 충분히 확보해 RRF 적용하고 최종 문서별 중복 제거. 정확 번호 경로와 모델 계약 유지. UI/배포는 기존 담당자에게 인계.
6. 캐시는 query만으로 고정하지 않고 corpus version/model/filter를 포함. 의미 캐시는 검증 이후 단계로 둔다.

검증: 원문 전체 coverage/Unicode, 결정적 ID/버전 분리, invalid 입력 거절, 정확 ID 우선/RRF 중복 방지, Top-K recall 계산 총 4개 테스트 통과. 운영 재임베딩·검색 배포·메일 발송 없음.


## 2026-09-26 적용 결과

- 운영 DB의 `public_laws` 5,948/5,948건, `bills` 18,989/18,989건에 임베딩 존재를 HEAD count로 확인했다. 과거 공법은 공식 제목+공법 번호를 입력한 메타데이터 임베딩이다. 조문 전문 임베딩 또는 현행법 전체 확보를 의미하지 않는다.
- `20260924150000_public_law_hybrid_search.sql`을 9월 25일 SQL Editor에서 적용했다. SQL Editor에는 `설정 · 과거 제정법 임베딩·통합 검색`으로 저장했다. 변경 전 공법 메타데이터 5,948건은 로컬 비공개 백업 `policy-downloads/retrieval-20260924/public-laws-before.json`에 보존했다.
- 9월 26일 실제 DB에서 `Congressional Accountability`와 해당 문서 벡터로 기존 의미검색과 새 하이브리드 RPC를 호출했다. 두 함수 모두 HTTP 200이며 1995년 공법 `104-public-1`을 첫 결과로 반환했다. 새 RPC는 service_role 전용이며 법안 번호 직접 조회는 기존 경로를 유지한다.
- Worker/UI 연결은 사용자가 이번 작업에 한해 Codex 수정을 명시 승인했다. RRF 점수는 코사인 유사도로 오인하지 않도록 `relevance_score`, `score_type: rrf`로 반환한다. 코드 커밋은 사이트 배포 완료를 의미하지 않는다.
- EIA 기사 URL의 `?id=`를 지우던 중복 제거를 수정했다. 마케팅 추적 매개변수만 제거하며 서로 다른 기사 번호는 보존한다. 공식 EIA 주간 석유 보고서 아카이브 날짜를 수집한다. 일반 EIA 피드에 일괄 원유 태그를 붙이던 기본값도 제거했다.
- 9월 25일 로컬 RSS 재생성 결과 46건이다. USDA NASS의 날짜 없는 항목이나 403을 데이터 미발행으로 간주하지 않는다. 메일 발송과 발송 활성화는 수행하지 않았다.
- 전문 청크 준비/중첩/출처 해시와 RRF recall 도구는 오프라인 준비 단계다. 전문 청크를 운영 DB에 저장·임베딩하는 단계는 아직 적용하지 않았다.
