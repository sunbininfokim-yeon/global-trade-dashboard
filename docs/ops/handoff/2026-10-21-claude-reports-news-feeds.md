# 인수인계 2026-10-21 — claude (보고서: 사용자 제공 RSS + 아프리카 광물 + 뉴스 헤드라인 구분)

## 한 일 (브랜치 `claude/reports-user-feeds`)

1. **사용자 RSS 목록 28곳 중 19곳 붙임, 아프리카 광물 14곳 추가** (소스 표는 PR 본문).
   - `config/sources.json`: 뉴스 매체는 `publisher_type: "news"` + `retention_days: 14`, 구글 뉴스 경유 소스는 `item_publisher: true`(기사마다 매체 이름), `commodity_scope`(소스가 다루는 원자재로만 태깅), `max_items`.
   - 국가 표에 자메이카·가봉·니제르·나미비아·수리남·가이아나·시에라리온·말리·보츠와나·마다가스카르·모리타니·르완다·수단·말라위·카메룬 추가. 맨 `Congo`는 DRC로 해석(코트디부아르·콩고공화국은 명시된 경우만).
2. **뉴스는 헤드라인 + 링크만** (사용자 지시: "뉴스를 다 저장하지 말고 URL 정도와 헤드라인만, 가짜·무관 기사 금지, 클릭하면 바로 그 URL").
   - 요약·scoring 사유 미저장, 원자재는 제목만 보고 판정(`commodity_from: title`).
   - 구글 뉴스 링크는 기사 원문 주소로 풀어서 저장(`newsfilter.resolve_google_news_url`, 구글 페이지가 쓰는 batchexecute 호출). 매체 도메인과 다르면 버림, 못 풀면 버림. 구글 URL은 화면에 나오지 않는다.
   - 신뢰 매체 목록 `config/news_outlets.json`(104곳)에 없는 매체의 구글 경유 기사는 분류 전에 버림(보도자료 배포 서비스·Yahoo Finance는 일부러 제외).
   - 같은 사건을 다룬 여러 매체 헤드라인은 한 줄로 합침(`merge_stories`: 공통 단어 4개 이상·75%·같은 원자재·4일 이내), 행에 `also` 건수. 공식 보고서는 합치지 않음.
   - 한 번 푼 링크는 `src_ref`로 기억, 합쳐지거나 도메인이 어긋난 링크는 `news.skip_refs`에 기억. 한 빌드에 새로 묻는 링크는 `RESOLVE_BUDGET=150`까지.
3. **UI/Worker**: `/api/commodity-reports?kind=official|news`(offset/limit/total 앞에서 필터), 응답에 `kind_counts`. 보고서 패널에 "공식 보고서 | 뉴스 헤드라인" 토글(공식 기본, 선택은 국가를 바꿔도 유지, 한쪽이 비면 다른 쪽, 뉴스 없는 창은 토글 없음). 정적 서버용 스냅샷 폴백도 같은 분리. `trade.js?v=agg-603`, `style.css?v=agg-604`.
4. **DB/소비자**: `commodity_digest_source_prefs`는 꺼진 source_id만 저장 → 새 소스는 기본 ON. 주간 다이제스트는 뉴스를 상품당 최대 2건, 메일에 "뉴스 매체 · 매체명". 마이페이지 출처 체크박스는 `source_agency`로 이름 표시.

## 검증

- 파이썬 테스트 123개, 다이제스트 노드 테스트 4개.
- 구글 뉴스 링크 해석: Actions 러너에서 16/16 성공(건당 0.2초, 매체 도메인 일치) — feed_probe `gnresolve` 대상(2026-10-21).
- 브라우저(Chromium, CDN 라이브러리는 스텁)에서 니켈 창이 공식 2 / 뉴스 48로 나뉘고 토글 전환·복귀 확인. Worker `kind` 필터는 스냅샷으로 직접 호출해 확인(공식+뉴스=전체, 페이지 이어붙임, 모르는 kind는 전체).

## 남은 것 / 주의

- Worker는 요청마다 스냅샷 전체를 파싱한다(2MB ≈ 18~34ms). 스냅샷이 더 커지면 모듈 수준 캐시를 고려.
- 뉴스 비중이 큰 창(니켈·팜유·석탄·구리·리튬)은 이제 기본이 공식이라 덜 눈에 띈다. 공식이 0건이면 뉴스가 자동으로 열린다.
- 못 붙인 곳: Mining Weekly·Engineering News·Mining Review·The Herald(Cloudflare 403), African Mining Brief(도메인이 도박 사이트로 넘어감), TLS 체인이 깨졌거나 DNS가 없는 정부 사이트(DRC·잠비아·탄자니아·나미비아·짐바브웨).
- 우라늄 창에 농축·연료 기사가 들어오는 문제는 사용자 결정 대기(범위를 천연우라늄으로 좁힐지).
- 병합·배포는 하지 않았다(사용자 확인 대기).
