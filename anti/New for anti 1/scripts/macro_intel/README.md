# Macro / Liquidity Official Intel

QRA·베이지북 등 공식 신호 + **지정 기자 기사의 유동성 지표 추출**.

- 양영빈 등 기자는 **속보로 기사를 나열하지 않음**
- 제목·요약(선택: 본문)에서 FIMA, TGA, RRP, ESF, 외환개입, 연준 BS 등 지표를 뽑아  
  `finance_panel_fields` / `reporter_liquidity` 로 내린다
- 속보에는 지표 요약 1줄만 선택적으로: `[유동성지표·양영빈] FIMA · TGA …`

## 지정 기자 → 지표 분석

`config/reporter_liquidity.json` 사전 + `macro_intel/reporters.py`

```bash
python3 build_liquidity.py --print-stats
# 본문까지 긁을 때(느림):
python3 build_liquidity.py --enrich-reporter-bodies --print-stats
```

산출 필드 예:
- `liquidity.reporter_liquidity[].top_indicators`
- `finance_panel_fields.reporter_liquidity_primary_ko`
- `finance_panel_fields.reporter_liquidity_themes`

- LLM으로 PDF 전체를 매일 넣지 않음 → 토큰 폭주 방지  
- FRED `TGA` / `WALCL` 타일(기존 금융 창)과 **병치**할 필드 제공  
- 속보 합치기용 `ticker_items[]` (commodity ticker와 동일 계열 스키마)

`app.js` 연결은 T01 잠금으로 보류. 스냅샷 + `/api/liquidity` 만.

---

## 검토 요약 (학습·속보 모델)

| 접근 | 판정 | 이유 |
|------|------|------|
| 매일 수백 리포트 / PDF 전문 LLM | ❌ | 토큰·지연·환각 |
| QRA HTML 정규식 + Sources/Uses PDF 링크 보존 | ✅ v1 | [sb0584](https://home.treasury.gov/news/press-releases/sb0584) 실제 문장 패턴이 안정적 |
| 베이지북 전문 감성 ML | △ 이후 | 우선 최신 링크 + 거친 soft/firm 키워드, 본문 톤은 옵션 |
| 양영빈 기사 전량 요약 LLM | △ 선택 | 리스트 스니펫·제목만 속보. 깊이 요약은 클릭/요청 시 1건 |
| 시계열 “학습” | ✅ 축적형 | `cache/qra_history.jsonl`에 quarter 행 append → 나중 TGA/연준 BS와 회귀 |

**권장 로드맵**

1. **지금**: 추출 → `liquidity_intel_v1.json` + 티커 병합  
2. **단기**: QRA 발표 주 캘린더 알림, finance 패널 카드 3~4칸  
3. **중기**: 저장 quarter ≥ 20이면 단순 회귀/룰 보정 (still no LLM)  
4. **LLM**: 사람/UI가 고른 1~3건 제목+수치표만 요약

---

## 실행

```bash
cd "New for anti/scripts/macro_intel"

python3 -m unittest discover -s tests -v

# 라이브 (Treasury + Fed + economy21)
python3 build_liquidity.py --print-stats

# 특정 QRA URL 고정
python3 build_liquidity.py \
  --qra-url "https://home.treasury.gov/news/press-releases/sb0584" \
  --print-stats

# 오프라인
python3 build_liquidity.py --fixtures tests/fixtures --no-fetch --print-stats
```

출력: `New for anti/public/data/liquidity_intel_v1.json`

---

## finance 창 필드 계약

`liquidity.finance_panel_fields`:

| 키 | 의미 |
|----|------|
| `qra_next_net_borrowing_bn` | 다음 분기 민간보유 순발행 추정 ($B) |
| `qra_end_cash_bn` | 가정 기말 현금 (= TGA 관련 가정치) |
| `qra_vs_prior_bn` | 직전 발표 대비 증감 ($B) |
| `liquidity_bias` | tightening / easing / mixed / neutral |
| `liquidity_headline_ko` | 한 줄 헤드라인 |
| `beige_tone` | soft / firm / mixed / unknown |
| `reporter_liquidity_primary_ko` | 지정기자 기사에서 가장 자주 다룬 지표명 |
| `reporter_liquidity_themes` | 상위 유동성 테마 문자열 목록 |
| `reporter_liquidity_signals` | 엔진용 신호 플래그 |

기존 타일: FRED `WTREGEN`(TGA), `WALCL`(연준 BS) — 수치; 본 모델은 **이벤트·해석 + 지정기자 지표 테마**.

---

## API

`GET /api/liquidity` → 스냅샷 JSON 그대로 (+ optional IP locale later)

`ticker_items` 를 commodity `/api/ticker` 결과와 프론트에서 concat 하거나  
추후 Worker에서 merge.

---

## PDF

v1은 **보도자료 HTML 문장**에서 수치 추출 (안정·무료).  
페이지 내 `Sources-Uses-*.pdf` 링크는 `qra.pdf_urls`에 보관.  

---

## 지정 기자 (유동성 지표 분석)

`priority_authors` = 감시 대상 **작문 소스**. 기사 제목을 속보에 쌓지 않는다.

1. economy21 리스트에서 해당 기자 글 수집  
2. 제목+요약(+옵션 본문)에서 FIMA/TGA/RRP/ESF/외환개입 등 매칭  
3. `liquidity.reporter_liquidity` + `finance_panel_fields.reporter_*` 출력  
4. 속보는 **지표 요약 1줄**만 (있을 때)

사전 확장: `config/reporter_liquidity.json`  
라벨/가중 조정은 이후 소통으로 학습.
