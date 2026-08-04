# Commodity news ticker — RSS → filter → ticker_v1.json

원자재 대시보드 **속보 티커**용 수집·필터 모델입니다.  
(프런트 `app.js` 연결은 T01 UI 잠금 때문에 아직 안 함. Worker `/api/ticker` + 스냅샷 JSON만.)

## 설계 원칙

1. **서구 단일 편향 방지**: MENA · 인도 · 튀르키예 · 일본 · 중국 · 대만 · 러시아 · 상품 전문지의 지역 가중치 > BBC/Bloomberg/FT.
2. **상품 필터**: 대시보드 취급 품목(원유·LNG·석탄·곡물·금속·해운) 다국어 별칭 매칭.
3. **정치**
   - **외교+무역 브릿지** → 통과
   - **선거 (대선/총선/지선/재보궐/당대표)** → 통과 (`category: election`)
   - **주요 개각·장관 교체** → 통과 (`category: cabinet_reshuffle`, info grade 1)
   - **여론조사**: 전국 대선 경마형(horse-race) **배제** · 국정/통치 지지율 **허용** (`governance_poll`)
   - 그 외 국내 정치 가십·몸싸움 → 제외
4. **중요도 모델 (country-tier × info-grade)**  
   주요국 3급 > 비주요국 2급 가능. `config/importance.json` + `label_importance.py` 로 promote/demote 학습.
5. **대만 균형**: CNA(중도) / 자유시보·Taipei Times(녹) / 연합보(청) 슬랜트별 상한.
6. **언어**
   - 수집: 원문 언어 유지 (`title.original`, `title.original_lang`)
   - **메인 공지**: `title.ko` (빌드 시 `--translate`로 한국어 생성)
   - **방문자 IP**: Worker `/api/ticker`가 `CF-IPCountry` → 언어 맵으로 `display_title` 선택 (원문 언어가 맞으면 원문, 아니면 한국어 우선 → 없으면 원문)

## 실행

```bash
cd "New for anti/scripts/commodity_news"

# 단위 테스트 (네트워크 불필요)
python3 -m unittest discover -s tests -v

# 라이브 RSS (네트워크 필요). 한국어 번역 없이 스냅샷만.
python3 build_ticker.py --print-stats

# 한국어 제목 번역 포함 (MyMemory 무료 쿼터, 느림)
python3 build_ticker.py --translate --print-stats

# 오프라인 픽스처
python3 build_ticker.py --fixtures tests/fixtures --no-fetch --print-stats
```

기본 출력: `New for anti/public/data/ticker_v1.json`

## 스키마

`schemas/ticker_v1.schema.json`

필수 필드 요약:

| 필드 | 의미 |
|------|------|
| `items[].title.ko` | 메인 티커용 한국어 |
| `items[].title.original` | 원문 제목 |
| `items[].category` | commodity / diplomacy / commodity_diplomacy / election / cabinet_reshuffle |
| `items[].country_tier` | A/B/C (주요·준주요·기타) |
| `items[].info_grade` | 1/2/3 |
| `scores.importance` | tier×grade 최종 우선순위 입력 |
| `items[].source.region` | 지역 버킷 |
| `model.ip_lang_map` | IP 국가코드 → 언어 |

## API (Worker)

`GET /api/ticker?limit=20`

응답에 `display_lang`, `display_title`, `title_ko` 포함.  
시크릿 불필요. 스냅샷은 static `public/data/ticker_v1.json`.

## 설정 파일

| 파일 | 역할 |
|------|------|
| `config/sources.json` | RSS 소스 레지스트리 (리전·슬랜트·상품 포커스) |
| `config/commodities.json` | 품목 다국어 사전 |
| `config/diplomacy.json` | 외교/국내정치/거부 사전 |
| `config/regions.json` | 지역 가중치·쿼터·IP→언어 |
| `config/politics_extra.json` | 여론조사(경마/통치), 개각 용어 |
| `config/importance.json` | 국가 티어 A/B/C × 정보 등급 1/2/3, cap |

```bash
# 중요도 레이블 (promote|keep|demote|drop) — cache/importance_label_history.jsonl
python3 label_importance.py promote --key tier:A --note "major prior"
python3 label_importance.py demote --key grade:3
```

소스 URL이 죽으면 `enabled: false`로 끄거나 URL만 교체하면 됩니다.

**선거 배팅 시장**은 티커가 아니라 `election_watch` → `elections_board_v1.json` 의 `betting_markets` (Polymarket).

## UI 연결 (나중, Claude T01 이후)

```js
// 의사코드 — app.js 티커
const r = await fetch('/api/ticker?limit=24');
const { items } = await r.json();
// 메인 라인: item.title_ko || item.display_title
// 보조: item.source.name · item.display_title (IP 언어 원문)
```

## 한계

- 페이월 본문 전체는 읽지 않음 (RSS 제목·요약만).
- 무료 번역 쿼터/품질 한계 → `translation_status: failed` 시 원문 유지.
- CNA 일부 엔드포인트는 HTML 페이지를 돌려주어 항목 0일 수 있음 → 피드 상태 로그 확인.
- 저작권: 제목·링크 메타 수준 인용; 전문 재배포 금지.
